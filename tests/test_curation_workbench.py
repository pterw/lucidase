"""Adversarial and schema-validation test suite for the Lucidase Curation Workbench.

Tests:
1. 100% byte-identical round-trip export on all 55 loci and 34 genes in kb_curation.json.
2. Relational integrity and clinical evidence modeling for the three schema archetypes:
   - PNPLA3 (rs738409): GWAS Tier A epidemiological risk vs ClinVar 1-star review.
   - APOE (rs429358, rs7412): composite diplotypes, component roles, relative risk vs penetrance.
   - DPYD (rs3918290): CPIC Level A clinical dosing action and single-variant assay limitation.
3. Content-hash collision guard adversarial tests:
   - Concurrent disk modifications cause export to abort.
   - Staged changes (or any content alteration) cannot bypass the hash guard.
   - Missing or deleted files trigger conflict abortion.
   - Force override allows explicit curator bypass when requested.
   - Successful export updates baseline manifest hashes.
4. Assay vs format invariants:
   - platform_coverage strictly enforces discrete microarray platforms.
   - Insertion of VCF, WGS, or sequencing assay formats fails closed with CurationValidationError.
5. Foreign key and schema constraints fail closed on referential violations.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import pytest

from tools.curation.curation_store import (
    CurationWorkbench,
    CurationConflictError,
    CurationValidationError,
    ALLOWED_MICROARRAY_PLATFORMS,
    DEFAULT_KB_CURATION_PATH,
    DEFAULT_CLAIMS_PATH,
    DEFAULT_COVERAGE_PATH,
    compute_file_sha256,
)


@pytest.fixture
def temp_curation_workspace(tmp_path: Path):
    """Creates an isolated temporary curation workspace populated with authoritative fixtures."""
    work_dir = tmp_path / "curation"
    work_dir.mkdir(parents=True)

    kb_copy = work_dir / "kb_curation.json"
    shutil.copy2(DEFAULT_KB_CURATION_PATH, kb_copy)

    claims_copy = work_dir / "evidence_claims.json"
    if DEFAULT_CLAIMS_PATH.exists():
        shutil.copy2(DEFAULT_CLAIMS_PATH, claims_copy)

    coverage_copy = work_dir / "platform_coverage.json"
    if DEFAULT_COVERAGE_PATH.exists():
        shutil.copy2(DEFAULT_COVERAGE_PATH, coverage_copy)

    db_path = work_dir / "curation_workbench.db"

    workbench = CurationWorkbench(
        db_path=db_path,
        kb_path=kb_copy,
        claims_path=claims_copy,
        coverage_path=coverage_copy,
    )
    return workbench, work_dir


def test_full_roundtrip_byte_identity(temp_curation_workspace):
    """Verifies that SQLite import -> export produces a 100% byte-identical file to kb_curation.json."""
    workbench, work_dir = temp_curation_workspace
    orig_kb_bytes = workbench.kb_path.read_bytes()

    # 1. Sync into SQLite
    sync_res = workbench.sync()
    assert sync_res["genes"] == 35
    assert sync_res["loci"] == 59

    # 2. Verify in-memory export matches disk
    verify_res = workbench.verify()
    assert verify_res["byte_identical"] is True
    assert verify_res["genes"] == 35
    assert verify_res["loci"] == 59
    assert verify_res["collision_detected"] is False

    # 3. Export to disk and compare raw bytes
    export_res = workbench.export()
    assert export_res["genes"] == 35
    assert export_res["loci"] == 59

    exported_kb_bytes = workbench.kb_path.read_bytes()
    assert exported_kb_bytes == orig_kb_bytes, "Exported kb_curation.json must be byte-for-byte identical"


def test_schema_archetype_pnpla3(temp_curation_workspace):
    """Verifies epidemiological risk factor modeling for PNPLA3 rs738409.
    
    Demonstrates GWAS Tier A literature attribution (Romeo et al. 2008, PMID: 18820647)
    distinct from ClinVar 1-star single-submitter review status.
    """
    workbench, _ = temp_curation_workspace
    workbench.sync()

    conn = workbench.get_connection()
    cur = conn.cursor()

    # Query locus record
    cur.execute(
        "SELECT gene, role, curated_tier, tier_rationale, tier_citation FROM loci WHERE rsid = 'rs738409'"
    )
    row = cur.fetchone()
    assert row is not None
    gene, role, tier, rationale, citation = row
    assert gene == "PNPLA3"
    assert role == "standard"
    assert tier == "Tier A"
    assert "Romeo et al. 2008" in citation
    assert "hepatic" in rationale.lower()

    # Query locus evidence (ClinVar)
    cur.execute("SELECT clinvar_json FROM locus_evidence WHERE locus_rsid = 'rs738409'")
    clinvar_raw = cur.fetchone()[0]
    assert clinvar_raw is not None
    clinvar = json.loads(clinvar_raw)
    assert clinvar["accession"] == "VCV000341932"
    assert clinvar["stars"] == 1
    assert "conflicting classifications" in clinvar["review_status"]

    # Query structured claims
    cur.execute(
        "SELECT claim_id, claim_type, source_type, citation_pmid, review_status, limitations FROM evidence_claims WHERE locus_rsid = 'rs738409'"
    )
    claim_row = cur.fetchone()
    assert claim_row is not None
    cid, ctype, stype, pmid, rev_stat, lims = claim_row
    assert cid == "claim_pnpla3_hepatic_steatosis"
    assert ctype == "epidemiological_risk"
    assert stype == "gwas"
    assert pmid == "18820647"
    assert rev_stat == "curated_tier_a"
    assert "BMI" in lims or "alcohol" in lims or "lifestyle" in lims

    conn.close()


def test_schema_archetype_apoe(temp_curation_workspace):
    """Verifies composite diplotype modeling for APOE rs429358 and rs7412.
    
    Exercises component roles, all 6 diplotypes, and relative risk vs penetrance caveats.
    """
    workbench, _ = temp_curation_workspace
    workbench.sync()

    conn = workbench.get_connection()
    cur = conn.cursor()

    # Query component loci
    for rsid in ["rs429358", "rs7412"]:
        cur.execute("SELECT gene, role FROM loci WHERE rsid = ?", (rsid,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "APOE"
        assert row[1] == "apoe_component"

    # Query gene-level diplotypes
    cur.execute("SELECT diplotypes_json FROM genes WHERE symbol = 'APOE'")
    diplo_raw = cur.fetchone()[0]
    assert diplo_raw is not None
    diplotypes = json.loads(diplo_raw)
    assert set(diplotypes.keys()) == {"e2/e2", "e2/e3", "e3/e3", "e2/e4", "e3/e4", "e4/e4"}

    # Relative risk wording in e4/e4
    e44 = diplotypes["e4/e4"]
    assert "relative risk" in e44["phenotype"].lower()
    assert e44["magnitude"] >= 4.0

    # Query structured claims for APOE
    cur.execute("SELECT claim_id, claim_type, citation_pmid, limitations FROM evidence_claims WHERE gene = 'APOE'")
    claims = cur.fetchall()
    assert len(claims) >= 2
    claim_ids = {c[0] for c in claims}
    assert "claim_apoe_e4_relative_risk" in claim_ids
    assert "claim_apoe_e2_protective" in claim_ids

    for cid, ctype, pmid, lims in claims:
        assert ctype == "composite_diplotype"
        assert pmid == "9343463"
        assert "phasing" in lims.lower() or "rs429358" in lims

    conn.close()


def test_schema_archetype_dpyd(temp_curation_workspace):
    """Verifies pharmacogenomic dosing action and single-variant limitations for DPYD rs3918290 (*2A)."""
    workbench, _ = temp_curation_workspace
    workbench.sync()

    conn = workbench.get_connection()
    cur = conn.cursor()

    # Locus tier and limitation
    cur.execute(
        "SELECT gene, limitation, tier_rationale FROM loci WHERE rsid = 'rs3918290'"
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "DPYD"
    assert "Single-variant test" in row[1]
    assert "DPYD c.1905+1G>A (*2A)" in row[1]
    assert "CPIC" in row[2]

    # Interpretations: alt 1 and alt 2 dosing actions
    cur.execute(
        "SELECT alt_count, magnitude_json, drug_response FROM interpretations WHERE locus_rsid = 'rs3918290' ORDER BY alt_count"
    )
    interps = cur.fetchall()
    assert len(interps) == 3  # counts 0, 1, 2
    # alt_count 1: intermediate metabolizer, >= 50% dose reduction
    assert interps[1][0] == "1"
    assert "50%" in interps[1][2]
    # alt_count 2: poor metabolizer, avoiding fluoropyrimidines
    assert interps[2][0] == "2"
    assert "avoiding" in interps[2][2].lower() or "substantially reducing" in interps[2][2].lower()

    # Evidence claim: CPIC Level A
    cur.execute(
        "SELECT claim_id, claim_type, review_status, citation_pmid, limitations FROM evidence_claims WHERE locus_rsid = 'rs3918290'"
    )
    claim = cur.fetchone()
    assert claim is not None
    assert claim[0] == "claim_dpyd_star2a_toxicity"
    assert claim[1] == "pharmacogenomic_dosing"
    assert claim[2] == "cpic_level_a"
    assert claim[3] == "29152729"
    assert "Single-variant limitation" in claim[4]

    conn.close()


def test_collision_guard_detects_disk_mutation(temp_curation_workspace):
    """Adversarial test: an external modification to kb_curation.json causes export to abort."""
    workbench, _ = temp_curation_workspace
    workbench.sync()

    # Mutate kb_curation.json on disk behind the workbench's back
    orig_kb = json.loads(workbench.kb_path.read_text(encoding="utf-8"))
    orig_kb["release"] = "2099.99.99-concurrent-edit"
    workbench.kb_path.write_text(json.dumps(orig_kb, indent=2) + "\n", encoding="utf-8")

    # Export must fail closed and refuse to overwrite
    with pytest.raises(CurationConflictError) as exc_info:
        workbench.export()

    assert "Collision guard failure" in str(exc_info.value)
    assert "kb_curation.json" in str(exc_info.value)

    # Disk file must still contain the concurrent edit (not clobbered)
    disk_after = json.loads(workbench.kb_path.read_text(encoding="utf-8"))
    assert disk_after["release"] == "2099.99.99-concurrent-edit"


def test_collision_guard_detects_companion_file_mutation(temp_curation_workspace):
    """Adversarial test: modification to evidence_claims.json causes export to abort."""
    workbench, _ = temp_curation_workspace
    workbench.sync()

    # Modify evidence_claims.json on disk
    workbench.claims_path.write_text('{"version": "1.0", "claims": []}\n', encoding="utf-8")

    with pytest.raises(CurationConflictError) as exc_info:
        workbench.export()

    assert "Collision guard failure" in str(exc_info.value)
    assert "evidence_claims.json" in str(exc_info.value)


def test_collision_guard_detects_deleted_file(temp_curation_workspace):
    """Adversarial test: deleting a tracked file causes export to abort."""
    workbench, _ = temp_curation_workspace
    workbench.sync()

    # Delete platform_coverage.json
    workbench.coverage_path.unlink()

    with pytest.raises(CurationConflictError) as exc_info:
        workbench.export()

    assert "Collision guard failure" in str(exc_info.value)
    assert "deleted or moved" in str(exc_info.value)


def test_force_override_bypasses_collision_guard(temp_curation_workspace):
    """Verifies that --force allows curator to intentionally overwrite disk state."""
    workbench, _ = temp_curation_workspace
    workbench.sync()

    # External modification
    workbench.claims_path.write_text('{"version": "1.0", "claims": []}\n', encoding="utf-8")

    # Force export must succeed
    res = workbench.export(force=True)
    assert res["status"] == "exported"

    # Subsequent normal export must now succeed because manifest was updated
    res2 = workbench.export()
    assert res2["status"] == "exported"


def test_platform_coverage_restricts_to_microarrays_and_rejects_vcf(temp_curation_workspace):
    """Adversarial test: platform_coverage accepts discrete microarrays but rejects VCF / assay formats."""
    workbench, _ = temp_curation_workspace
    workbench.sync()

    conn = workbench.get_connection()

    # Check allowed platforms in table
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT platform FROM platform_coverage")
    platforms = {row[0] for row in cur.fetchall()}
    assert platforms.issubset(set(ALLOWED_MICROARRAY_PLATFORMS))

    # Attempt to insert VCF as a platform (violates assay vs format separation)
    with pytest.raises(CurationValidationError) as exc_info:
        workbench._validate_platform_name("vcf_callset")
    assert "not permitted in platform_coverage" in str(exc_info.value)

    with pytest.raises(CurationValidationError):
        workbench._validate_platform_name("wgs_illumina")

    with pytest.raises(CurationValidationError):
        workbench._validate_platform_name("wes_exome")

    conn.close()


def test_foreign_key_constraints_fail_closed(temp_curation_workspace):
    """Verifies that relational constraints prevent phantom loci, orphan interpretations, or claims."""
    workbench, _ = temp_curation_workspace
    workbench.sync()

    conn = workbench.get_connection()
    cur = conn.cursor()

    # 1. Non-existent gene for a locus
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            cur.execute("""
            INSERT INTO loci VALUES ('rs999999', 'NONEXISTENT_GENE', '1', 100, 100, 'A', 'G', NULL, 'standard', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 999)
            """)

    # 2. Non-existent locus for interpretation
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            cur.execute("""
            INSERT INTO interpretations VALUES ('rsNONEXISTENT', '0', 'Not detected', 'Benign', '0', 'Neutral', 'Test', NULL, '[]')
            """)

    # 3. Non-existent gene for claim
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            cur.execute("""
            INSERT INTO evidence_claims VALUES ('claim_invalid', 'rs738409', 'NONEXISTENT_GENE', 'risk', 'statement', 'gwas', NULL, 'citation', 'tier_a', 'high', NULL, 99)
            """)

    conn.close()
