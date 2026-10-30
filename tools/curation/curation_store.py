"""Curation Store & Workbench for Lucidase.

Provides a reproducible, rebuildable SQLite projection of Git-tracked curation data
(tools/curation/kb_curation.json, evidence_claims.json, platform_coverage.json)
with an unforgeable SHA-256 content-hash collision guard.

Architecture invariants:
1. SQLite is a rebuildable local projection for curator workflows; Git-tracked files
   are the single source of truth.
2. Lossless round-tripping: importing kb_curation.json into SQLite and exporting it back
   must reproduce the original file 100% byte-for-byte.
3. Content-hash collision guard: export fails closed if any tracked curation file
   was modified on disk (staged or unstaged) since the session baseline was established.
4. Assay vs format: VCF is an assay/file format, not a fixed microarray chip manifest.
   platform_coverage strictly models discrete microarray platforms.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CURATION_DIR = PROJECT_ROOT / "tools" / "curation"
DEFAULT_KB_CURATION_PATH = DEFAULT_CURATION_DIR / "kb_curation.json"
DEFAULT_CLAIMS_PATH = DEFAULT_CURATION_DIR / "evidence_claims.json"
DEFAULT_COVERAGE_PATH = DEFAULT_CURATION_DIR / "platform_coverage.json"
DEFAULT_DB_PATH = DEFAULT_CURATION_DIR / "curation_workbench.db"

ALLOWED_MICROARRAY_PLATFORMS = (
    "23andme_v3",
    "23andme_v4",
    "23andme_v5",
    "ancestry_v1",
    "ancestry_v2",
    "myheritage_standard",
)

DISALLOWED_PLATFORM_KEYWORDS = ("vcf", "wgs", "wes", "ngs", "fastq", "bam", "cram")


class CurationConflictError(Exception):
    """Raised when an unapproved disk or index modification conflicts with the session baseline."""
    pass


class CurationValidationError(Exception):
    """Raised when schema validation or referential integrity fails."""
    pass


def compute_file_sha256(path: Path) -> str:
    """Computes the SHA-256 hex digest of a file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_newline(path: Path) -> str:
    """Detects whether an existing file uses CRLF or LF line endings."""
    if path.exists():
        with open(path, "rb") as f:
            chunk = f.read(8192)
            if b"\r\n" in chunk:
                return "\r\n"
    return "\n"


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8", newline: Optional[str] = None) -> None:
    """Writes text atomically using a temporary file and atomic replace."""
    if newline is None:
        newline = detect_newline(path)
    if newline == "\r\n":
        content = content.replace("\r\n", "\n").replace("\n", "\r\n")
    tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding=encoding, newline="") as f:
            f.write(content)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def get_default_seed_claims() -> List[Dict[str, Any]]:
    """Returns baseline structured evidence claims for the three schema-validation archetypes."""
    return [
        {
            "claim_id": "claim_apoe_e2_protective",
            "locus_rsid": "rs7412",
            "gene": "APOE",
            "claim_type": "composite_diplotype",
            "statement": "APOE epsilon2 allele confers reduced relative risk for late-onset Alzheimer disease compared to epsilon3/epsilon3 baseline.",
            "source_type": "meta_analysis",
            "citation_pmid": "9343463",
            "citation_label": "Farrer et al. 1997 JAMA",
            "review_status": "curated_tier_a",
            "confidence_score": "definitive",
            "limitations": "Composite finding requiring both rs429358 and rs7412; homozygosity for e2/e2 is also associated with type III hyperlipoproteinemia with variable penetrance."
        },
        {
            "claim_id": "claim_apoe_e4_relative_risk",
            "locus_rsid": "rs429358",
            "gene": "APOE",
            "claim_type": "composite_diplotype",
            "statement": "APOE epsilon4 allele in homozygous (e4/e4) or heterozygous (e3/e4) configuration increases late-onset Alzheimer disease relative risk (~12-15x for e4/e4, ~3-4x for e3/e4 versus e3/e3 baseline).",
            "source_type": "meta_analysis",
            "citation_pmid": "9343463",
            "citation_label": "Farrer et al. 1997 JAMA",
            "review_status": "curated_tier_a",
            "confidence_score": "definitive",
            "limitations": "Requires phasing of both rs429358 and rs7412 to determine isoform; not a deterministic monogenic diagnostic test. Significant proportion of e4/e4 individuals do not develop dementia."
        },
        {
            "claim_id": "claim_dpyd_star2a_toxicity",
            "locus_rsid": "rs3918290",
            "gene": "DPYD",
            "claim_type": "pharmacogenomic_dosing",
            "statement": "DPYD c.1905+1G>A (*2A) results in complete loss of dihydropyrimidine dehydrogenase activity; heterozygous carriers require at least 50% initial fluoropyrimidine dose reduction, and homozygotes require complete avoidance or severe reduction.",
            "source_type": "cpic_guideline",
            "citation_pmid": "29152729",
            "citation_label": "Amstutz et al. 2018 Clin Pharmacol Ther",
            "review_status": "cpic_level_a",
            "confidence_score": "definitive",
            "limitations": "Single-variant limitation: testing rs3918290 alone cannot rule out DPYD deficiency caused by *13 (rs55886062), c.2846A>T (rs67376798), or HapB3 (rs75017182). Full activity score requires comprehensive multi-variant panel."
        },
        {
            "claim_id": "claim_pnpla3_hepatic_steatosis",
            "locus_rsid": "rs738409",
            "gene": "PNPLA3",
            "claim_type": "epidemiological_risk",
            "statement": "PNPLA3 p.I148M (rs738409[G]) is strongly associated with hepatic steatosis, non-alcoholic fatty liver disease (NAFLD/MASLD), and elevated liver transaminases across diverse ancestry groups.",
            "source_type": "gwas",
            "citation_pmid": "18820647",
            "citation_label": "Romeo et al. 2008 Nat Genet",
            "review_status": "curated_tier_a",
            "confidence_score": "definitive",
            "limitations": "GWAS epidemiological association; ClinVar review status is 1-star (single submitter) because it is a common susceptibility allele rather than monogenic determinant. Effect is strongly modified by BMI, alcohol consumption, and metabolic factors."
        }
    ]


def get_default_seed_coverage() -> Dict[str, Any]:
    """Returns baseline platform probe coverage for the validation archetypes across microarrays."""
    return {
        "version": "1.0",
        "platforms": list(ALLOWED_MICROARRAY_PLATFORMS),
        "loci": {
            "rs738409": {
                "gene": "PNPLA3",
                "coverage": {
                    "23andme_v3": {"is_covered": True, "probe_id": "rs738409", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "23andme_v4": {"is_covered": True, "probe_id": "rs738409", "strand_design": "plus", "notes": "Custom Illumina chip"},
                    "23andme_v5": {"is_covered": True, "probe_id": "rs738409", "strand_design": "plus", "notes": "Illumina Global Screening Array"},
                    "ancestry_v1": {"is_covered": True, "probe_id": "rs738409", "strand_design": "plus", "notes": "Illumina OmniExpress"},
                    "ancestry_v2": {"is_covered": True, "probe_id": "rs738409", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "myheritage_standard": {"is_covered": True, "probe_id": "rs738409", "strand_design": "plus", "notes": "Illumina Global Screening Array"}
                }
            },
            "rs429358": {
                "gene": "APOE",
                "coverage": {
                    "23andme_v3": {"is_covered": True, "probe_id": "rs429358", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "23andme_v4": {"is_covered": True, "probe_id": "rs429358", "strand_design": "plus", "notes": "Custom Illumina chip"},
                    "23andme_v5": {"is_covered": True, "probe_id": "rs429358", "strand_design": "plus", "notes": "Illumina Global Screening Array"},
                    "ancestry_v1": {"is_covered": True, "probe_id": "rs429358", "strand_design": "plus", "notes": "Illumina OmniExpress"},
                    "ancestry_v2": {"is_covered": True, "probe_id": "rs429358", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "myheritage_standard": {"is_covered": True, "probe_id": "rs429358", "strand_design": "plus", "notes": "Illumina Global Screening Array"}
                }
            },
            "rs7412": {
                "gene": "APOE",
                "coverage": {
                    "23andme_v3": {"is_covered": True, "probe_id": "rs7412", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "23andme_v4": {"is_covered": True, "probe_id": "rs7412", "strand_design": "plus", "notes": "Custom Illumina chip"},
                    "23andme_v5": {"is_covered": True, "probe_id": "rs7412", "strand_design": "plus", "notes": "Illumina Global Screening Array"},
                    "ancestry_v1": {"is_covered": True, "probe_id": "rs7412", "strand_design": "plus", "notes": "Illumina OmniExpress"},
                    "ancestry_v2": {"is_covered": True, "probe_id": "rs7412", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "myheritage_standard": {"is_covered": True, "probe_id": "rs7412", "strand_design": "plus", "notes": "Illumina Global Screening Array"}
                }
            },
            "rs3918290": {
                "gene": "DPYD",
                "coverage": {
                    "23andme_v3": {"is_covered": True, "probe_id": "rs3918290", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "23andme_v4": {"is_covered": True, "probe_id": "rs3918290", "strand_design": "plus", "notes": "Custom Illumina chip"},
                    "23andme_v5": {"is_covered": True, "probe_id": "rs3918290", "strand_design": "plus", "notes": "Illumina Global Screening Array"},
                    "ancestry_v1": {"is_covered": True, "probe_id": "rs3918290", "strand_design": "plus", "notes": "Illumina OmniExpress"},
                    "ancestry_v2": {"is_covered": True, "probe_id": "rs3918290", "strand_design": "plus", "notes": "Illumina OmniExpress Plus"},
                    "myheritage_standard": {"is_covered": True, "probe_id": "rs3918290", "strand_design": "plus", "notes": "Illumina Global Screening Array"}
                }
            }
        }
    }


class CurationWorkbench:
    """Manages local SQLite curation operations with SHA-256 session collision protection."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        kb_path: Optional[Path] = None,
        claims_path: Optional[Path] = None,
        coverage_path: Optional[Path] = None,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.kb_path = Path(kb_path or DEFAULT_KB_CURATION_PATH)
        self.claims_path = Path(claims_path or DEFAULT_CLAIMS_PATH)
        self.coverage_path = Path(coverage_path or DEFAULT_COVERAGE_PATH)

    @property
    def tracked_files(self) -> Dict[str, Path]:
        return {
            "kb_curation.json": self.kb_path,
            "evidence_claims.json": self.claims_path,
            "platform_coverage.json": self.coverage_path,
        }

    def get_connection(self) -> sqlite3.Connection:
        """Opens or creates the SQLite connection with foreign keys and WAL mode."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        if self.db_path.name != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_schema(self, conn: sqlite3.Connection) -> None:
        """Defines all workbench tables, indices, and constraints."""
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS _session_manifest (
                file_name TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS curation_meta (
                release TEXT NOT NULL,
                acmg_sf_version TEXT NOT NULL
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS genes (
                symbol TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                top_level_model TEXT,
                inheritance_model TEXT NOT NULL,
                mendelian_disease INTEGER NOT NULL,
                disease TEXT,
                omim TEXT,
                penetrance_json TEXT,
                acmg_sf INTEGER NOT NULL,
                insights_json TEXT,
                insights_provenance_json TEXT,
                diplotypes_json TEXT,
                row_order INTEGER NOT NULL
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS loci (
                rsid TEXT PRIMARY KEY,
                gene TEXT NOT NULL,
                chrom TEXT NOT NULL,
                pos_grch37 INTEGER NOT NULL,
                pos_grch38 INTEGER NOT NULL,
                ref TEXT NOT NULL,
                alt TEXT NOT NULL,
                allele_codes_json TEXT,
                role TEXT NOT NULL,
                limitation TEXT,
                limitation_ref TEXT,
                curated_tier TEXT,
                tier_rationale TEXT,
                tier_citation TEXT,
                tier_position TEXT,
                limitation_position TEXT,
                row_order INTEGER NOT NULL,
                FOREIGN KEY (gene) REFERENCES genes(symbol)
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS interpretations (
                locus_rsid TEXT NOT NULL,
                alt_count TEXT NOT NULL,
                category TEXT NOT NULL,
                significance TEXT NOT NULL,
                magnitude_json TEXT NOT NULL,
                repute TEXT NOT NULL,
                phenotype TEXT NOT NULL,
                drug_response TEXT,
                caveats_json TEXT NOT NULL,
                PRIMARY KEY (locus_rsid, alt_count),
                FOREIGN KEY (locus_rsid) REFERENCES loci(rsid)
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS locus_evidence (
                locus_rsid TEXT PRIMARY KEY,
                clinvar_json TEXT,
                gnomad_json TEXT,
                hpa_json TEXT,
                cpic_json TEXT,
                FOREIGN KEY (locus_rsid) REFERENCES loci(rsid)
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence_claims (
                claim_id TEXT PRIMARY KEY,
                locus_rsid TEXT,
                gene TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                statement TEXT NOT NULL,
                source_type TEXT NOT NULL,
                citation_pmid TEXT,
                citation_label TEXT NOT NULL,
                review_status TEXT NOT NULL,
                confidence_score TEXT NOT NULL,
                limitations TEXT,
                row_order INTEGER NOT NULL,
                FOREIGN KEY (gene) REFERENCES genes(symbol),
                FOREIGN KEY (locus_rsid) REFERENCES loci(rsid)
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS platform_coverage (
                locus_rsid TEXT NOT NULL,
                platform TEXT NOT NULL,
                is_covered INTEGER NOT NULL,
                probe_id TEXT,
                strand_design TEXT NOT NULL,
                notes TEXT,
                PRIMARY KEY (locus_rsid, platform),
                FOREIGN KEY (locus_rsid) REFERENCES loci(rsid)
            )
            """)

    def check_collision(self, conn: sqlite3.Connection) -> None:
        """Verifies that all tracked files match their recorded SHA-256 baseline.
        
        Raises CurationConflictError if any file has been modified on disk or deleted.
        """
        cur = conn.cursor()
        cur.execute("SELECT file_name, file_path, sha256 FROM _session_manifest")
        rows = cur.fetchall()
        if not rows:
            return  # No manifest recorded yet

        for file_name, file_path_str, expected_hash in rows:
            path = Path(file_path_str)
            if not path.exists():
                raise CurationConflictError(
                    f"Collision guard failure: tracked file '{file_name}' ({path}) was deleted or moved on disk."
                )
            current_hash = compute_file_sha256(path)
            if current_hash != expected_hash:
                raise CurationConflictError(
                    f"Collision guard failure: tracked file '{file_name}' ({path}) was modified on disk since "
                    f"session baseline was established.\n"
                    f"  Expected SHA-256: {expected_hash}\n"
                    f"  Current SHA-256:  {current_hash}\n"
                    f"Export aborted to prevent overwriting concurrent disk or Git changes."
                )

    def _update_manifest(self, conn: sqlite3.Connection) -> None:
        """Updates the _session_manifest with the current hashes of all tracked files."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            for file_name, path in self.tracked_files.items():
                if path.exists():
                    sha = compute_file_sha256(path)
                    conn.execute(
                        "INSERT OR REPLACE INTO _session_manifest VALUES (?, ?, ?, ?)",
                        (file_name, str(path), sha, now_iso),
                    )

    def sync(self, seed_if_missing: bool = True) -> Dict[str, Any]:
        """Reconstructs the SQLite database from tracked JSON files and establishes the session baseline."""
        if not self.kb_path.exists():
            raise FileNotFoundError(f"Authoritative KB curation file not found: {self.kb_path}")

        # Ensure companion files exist (or seed them)
        if not self.claims_path.exists() and seed_if_missing:
            claims_data = {"version": "1.0", "claims": get_default_seed_claims()}
            atomic_write_text(self.claims_path, json.dumps(claims_data, indent=2) + "\n")

        if not self.coverage_path.exists() and seed_if_missing:
            coverage_data = get_default_seed_coverage()
            atomic_write_text(self.coverage_path, json.dumps(coverage_data, indent=2) + "\n")

        with open(self.kb_path, "r", encoding="utf-8") as f:
            kb_data = json.load(f)

        claims_list: List[Dict[str, Any]] = []
        if self.claims_path.exists():
            with open(self.claims_path, "r", encoding="utf-8") as f:
                claims_payload = json.load(f)
                claims_list = claims_payload.get("claims", [])

        coverage_loci: Dict[str, Any] = {}
        if self.coverage_path.exists():
            with open(self.coverage_path, "r", encoding="utf-8") as f:
                cov_payload = json.load(f)
                coverage_loci = cov_payload.get("loci", {})

        conn = self.get_connection()
        self.init_schema(conn)

        with conn:
            # Clear existing data
            conn.execute("DELETE FROM platform_coverage")
            conn.execute("DELETE FROM evidence_claims")
            conn.execute("DELETE FROM locus_evidence")
            conn.execute("DELETE FROM interpretations")
            conn.execute("DELETE FROM loci")
            conn.execute("DELETE FROM genes")
            conn.execute("DELETE FROM curation_meta")

            # Meta
            conn.execute(
                "INSERT INTO curation_meta VALUES (?, ?)",
                (kb_data["release"], kb_data["acmg_sf_version"]),
            )

            # Genes
            for order, (sym, g) in enumerate(kb_data["genes"].items()):
                inh = g["inheritance"]
                conn.execute(
                    """
                    INSERT INTO genes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym,
                        g["topic"],
                        g.get("model"),
                        inh["model"],
                        1 if inh["mendelian_disease"] else 0,
                        inh.get("disease"),
                        inh.get("omim"),
                        json.dumps(inh.get("penetrance")) if inh.get("penetrance") is not None else None,
                        1 if g["acmg_sf"] else 0,
                        json.dumps(g.get("insights")) if g.get("insights") is not None else None,
                        json.dumps(g.get("insights_provenance")) if g.get("insights_provenance") is not None else None,
                        json.dumps(g.get("diplotypes")) if g.get("diplotypes") is not None else None,
                        order,
                    ),
                )

            # Loci
            for order, (rsid, loc) in enumerate(kb_data["loci"].items()):
                keys = list(loc.keys())
                tier = loc.get("tier") or {}
                tier_pos = None
                if "tier" in loc:
                    tier_pos = "before_interp" if keys.index("tier") < keys.index("interpretations") else "after_evidence"

                lim_pos = None
                if "limitation" in loc:
                    lim_pos = "before_interp" if keys.index("limitation") < keys.index("interpretations") else "after_evidence"
                elif "limitation_ref" in loc:
                    lim_pos = "before_interp" if keys.index("limitation_ref") < keys.index("interpretations") else "after_evidence"

                conn.execute(
                    """
                    INSERT INTO loci VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rsid,
                        loc["gene"],
                        loc["chrom"],
                        loc["pos_grch37"],
                        loc["pos_grch38"],
                        loc["ref"],
                        loc["alt"],
                        json.dumps(loc.get("allele_codes")) if loc.get("allele_codes") is not None else None,
                        loc["role"],
                        loc.get("limitation"),
                        loc.get("limitation_ref"),
                        tier.get("curated_tier"),
                        tier.get("rationale"),
                        tier.get("citation"),
                        tier_pos,
                        lim_pos,
                        order,
                    ),
                )

                for cnt, interp in loc["interpretations"].items():
                    conn.execute(
                        """
                        INSERT INTO interpretations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rsid,
                            cnt,
                            interp["category"],
                            interp["significance"],
                            json.dumps(interp["magnitude"]),
                            interp["repute"],
                            interp["phenotype"],
                            interp.get("drug_response"),
                            json.dumps(interp.get("caveats", [])),
                        ),
                    )

                ev = loc.get("evidence", {})
                conn.execute(
                    """
                    INSERT INTO locus_evidence VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        rsid,
                        json.dumps(ev.get("clinvar")) if ev.get("clinvar") is not None else None,
                        json.dumps(ev.get("gnomad")) if ev.get("gnomad") is not None else None,
                        json.dumps(ev.get("hpa")) if ev.get("hpa") is not None else None,
                        json.dumps(ev.get("cpic")) if ev.get("cpic") is not None else None,
                    ),
                )

            # Claims
            for c_order, claim in enumerate(claims_list):
                conn.execute(
                    """
                    INSERT INTO evidence_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim["claim_id"],
                        claim.get("locus_rsid"),
                        claim["gene"],
                        claim["claim_type"],
                        claim["statement"],
                        claim["source_type"],
                        claim.get("citation_pmid"),
                        claim["citation_label"],
                        claim["review_status"],
                        claim["confidence_score"],
                        claim.get("limitations"),
                        c_order,
                    ),
                )

            # Platform Coverage
            for rsid, l_data in coverage_loci.items():
                cov_map = l_data.get("coverage", {})
                for plat_name, plat_info in cov_map.items():
                    self._validate_platform_name(plat_name)
                    conn.execute(
                        """
                        INSERT INTO platform_coverage VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rsid,
                            plat_name,
                            1 if plat_info.get("is_covered") else 0,
                            plat_info.get("probe_id"),
                            plat_info.get("strand_design", "plus"),
                            plat_info.get("notes"),
                        ),
                    )

        # Baseline manifest recorded after successful sync
        self._update_manifest(conn)
        conn.close()

        return {
            "status": "synchronized",
            "genes": len(kb_data["genes"]),
            "loci": len(kb_data["loci"]),
            "claims": len(claims_list),
            "coverage_loci": len(coverage_loci),
        }

    def _validate_platform_name(self, platform: str) -> None:
        """Validates that a platform is a recognized discrete microarray, not an assay or file format."""
        plat_lower = platform.lower()
        for kw in DISALLOWED_PLATFORM_KEYWORDS:
            if kw in plat_lower:
                raise CurationValidationError(
                    f"Invalid platform '{platform}': assay/format keywords ({DISALLOWED_PLATFORM_KEYWORDS}) "
                    f"are not permitted in platform_coverage. Microarray chips must be discrete manifests."
                )
        if plat_lower not in ALLOWED_MICROARRAY_PLATFORMS:
            raise CurationValidationError(
                f"Unrecognized microarray platform '{platform}'. Allowed platforms: {ALLOWED_MICROARRAY_PLATFORMS}"
            )

    def export(self, force: bool = False) -> Dict[str, Any]:
        """Exports data from SQLite back to tracked text files with collision verification."""
        conn = self.get_connection()
        if not force:
            self.check_collision(conn)

        cur = conn.cursor()

        # 1. Reconstruct kb_curation.json
        cur.execute("SELECT release, acmg_sf_version FROM curation_meta")
        meta_row = cur.fetchone()
        if not meta_row:
            raise CurationValidationError("Cannot export: curation_meta table is empty.")
        rel, acmg = meta_row

        kb_dict = {
            "release": rel,
            "acmg_sf_version": acmg,
            "genes": {},
            "loci": {},
        }

        # Genes in original row_order
        cur.execute(
            """
            SELECT symbol, topic, top_level_model, inheritance_model, mendelian_disease,
                   disease, omim, penetrance_json, acmg_sf, insights_json,
                   insights_provenance_json, diplotypes_json
            FROM genes ORDER BY row_order
            """
        )
        for g_row in cur.fetchall():
            sym, topic, top_model, inh_model, mendelian, disease, omim, penetrance_json, acmg_sf, ins, ins_prov, diplo = g_row
            gene_dict = {}
            if top_model is not None:
                gene_dict["model"] = top_model
            gene_dict["topic"] = topic
            gene_dict["inheritance"] = {
                "model": inh_model,
                "mendelian_disease": bool(mendelian),
                "disease": disease,
                "omim": omim,
                "penetrance": json.loads(penetrance_json) if penetrance_json is not None else None,
            }
            gene_dict["acmg_sf"] = bool(acmg_sf)
            gene_dict["insights"] = json.loads(ins) if ins else None
            if ins_prov is not None:
                gene_dict["insights_provenance"] = json.loads(ins_prov)
            if diplo is not None:
                gene_dict["diplotypes"] = json.loads(diplo)
            kb_dict["genes"][sym] = gene_dict

        # Loci in original row_order
        cur.execute(
            """
            SELECT rsid, gene, chrom, pos_grch37, pos_grch38, ref, alt, allele_codes_json,
                   role, limitation, limitation_ref, curated_tier, tier_rationale,
                   tier_citation, tier_position, limitation_position
            FROM loci ORDER BY row_order
            """
        )
        loci_rows = cur.fetchall()
        for l_row in loci_rows:
            rsid, gene, chrom, pos37, pos38, ref, alt, codes, role, lim, lim_ref, cur_tier, tier_rat, tier_cit, tier_pos, lim_pos = l_row
            loc_dict = {
                "gene": gene,
                "chrom": chrom,
                "pos_grch37": pos37,
                "pos_grch38": pos38,
                "ref": ref,
                "alt": alt,
                "allele_codes": json.loads(codes) if codes else None,
                "role": role,
            }

            if lim_pos == "before_interp":
                if lim_ref is not None:
                    loc_dict["limitation_ref"] = lim_ref
                else:
                    loc_dict["limitation"] = lim

            tier_dict = None
            if cur_tier is not None or tier_rat is not None or tier_cit is not None:
                tier_dict = {}
                if cur_tier is not None:
                    tier_dict["curated_tier"] = cur_tier
                if tier_rat is not None:
                    tier_dict["rationale"] = tier_rat
                if tier_cit is not None:
                    tier_dict["citation"] = tier_cit

            if tier_pos == "before_interp" and tier_dict is not None:
                loc_dict["tier"] = tier_dict

            # Interpretations
            loc_dict["interpretations"] = {}
            cur.execute(
                """
                SELECT alt_count, category, significance, magnitude_json, repute, phenotype, drug_response, caveats_json
                FROM interpretations WHERE locus_rsid = ? ORDER BY alt_count
                """,
                (rsid,),
            )
            for i_row in cur.fetchall():
                ac, cat, sig, mag_json, rep, pheno, dr, cav = i_row
                interp_obj = {
                    "category": cat,
                    "significance": sig,
                    "magnitude": json.loads(mag_json),
                    "repute": rep,
                    "phenotype": pheno,
                    "drug_response": dr,
                    "caveats": json.loads(cav),
                }
                loc_dict["interpretations"][ac] = interp_obj

            # Evidence
            cur.execute(
                "SELECT clinvar_json, gnomad_json, hpa_json, cpic_json FROM locus_evidence WHERE locus_rsid = ?",
                (rsid,),
            )
            ev_row = cur.fetchone()
            if ev_row:
                ev_dict = {}
                if ev_row[0]: ev_dict["clinvar"] = json.loads(ev_row[0])
                if ev_row[1]: ev_dict["gnomad"] = json.loads(ev_row[1])
                if ev_row[2]: ev_dict["hpa"] = json.loads(ev_row[2])
                if ev_row[3]: ev_dict["cpic"] = json.loads(ev_row[3])
                loc_dict["evidence"] = ev_dict

            if lim_pos == "after_evidence":
                if lim_ref is not None:
                    loc_dict["limitation_ref"] = lim_ref
                else:
                    loc_dict["limitation"] = lim

            if tier_pos != "before_interp" and tier_dict is not None:
                loc_dict["tier"] = tier_dict

            kb_dict["loci"][rsid] = loc_dict

        # 2. Reconstruct evidence_claims.json
        cur.execute(
            """
            SELECT claim_id, locus_rsid, gene, claim_type, statement, source_type,
                   citation_pmid, citation_label, review_status, confidence_score, limitations
            FROM evidence_claims ORDER BY row_order
            """
        )
        claims_list = []
        for c_row in cur.fetchall():
            cid, l_rsid, c_gene, c_type, stmt, src_type, pmid, cit_lbl, rev_stat, conf, lim_txt = c_row
            c_obj = {
                "claim_id": cid,
                "locus_rsid": l_rsid,
                "gene": c_gene,
                "claim_type": c_type,
                "statement": stmt,
                "source_type": src_type,
                "citation_pmid": pmid,
                "citation_label": cit_lbl,
                "review_status": rev_stat,
                "confidence_score": conf,
                "limitations": lim_txt,
            }
            claims_list.append(c_obj)
        claims_payload = {"version": "1.0", "claims": claims_list}

        # 3. Reconstruct platform_coverage.json
        cur.execute(
            """
            SELECT p.locus_rsid, l.gene, p.platform, p.is_covered, p.probe_id, p.strand_design, p.notes
            FROM platform_coverage p
            JOIN loci l ON p.locus_rsid = l.rsid
            ORDER BY l.row_order, p.platform
            """
        )
        coverage_payload = {
            "version": "1.0",
            "platforms": list(ALLOWED_MICROARRAY_PLATFORMS),
            "loci": {},
        }
        for cov_row in cur.fetchall():
            l_rsid, l_gene, plat, is_cov, probe, strand, notes = cov_row
            if l_rsid not in coverage_payload["loci"]:
                coverage_payload["loci"][l_rsid] = {
                    "gene": l_gene,
                    "coverage": {},
                }
            coverage_payload["loci"][l_rsid]["coverage"][plat] = {
                "is_covered": bool(is_cov),
                "probe_id": probe,
                "strand_design": strand,
                "notes": notes,
            }

        # Atomic writes
        kb_text = json.dumps(kb_dict, indent=2) + "\n"
        claims_text = json.dumps(claims_payload, indent=2) + "\n"
        cov_text = json.dumps(coverage_payload, indent=2) + "\n"

        atomic_write_text(self.kb_path, kb_text)
        atomic_write_text(self.claims_path, claims_text)
        atomic_write_text(self.coverage_path, cov_text)

        # Update session manifest with newly written file hashes
        self._update_manifest(conn)
        conn.close()

        return {
            "status": "exported",
            "kb_bytes": len(kb_text.encode("utf-8")),
            "genes": len(kb_dict["genes"]),
            "loci": len(kb_dict["loci"]),
            "claims": len(claims_list),
            "coverage_loci": len(coverage_payload["loci"]),
        }

    def verify(self) -> Dict[str, Any]:
        """Performs exhaustive verification of database integrity and round-trip byte-identity."""
        conn = self.get_connection()
        cur = conn.cursor()

        # Check FK integrity
        cur.execute("PRAGMA foreign_key_check")
        fk_errors = cur.fetchall()
        if fk_errors:
            raise CurationValidationError(f"Foreign key violations detected: {fk_errors}")

        # Check platform rules
        cur.execute("SELECT DISTINCT platform FROM platform_coverage")
        for (plat,) in cur.fetchall():
            self._validate_platform_name(plat)

        # Dry-run export in memory and compare kb_curation.json
        if not self.kb_path.exists():
            raise FileNotFoundError(f"Missing KB curation file: {self.kb_path}")

        with open(self.kb_path, "rb") as f:
            disk_kb_bytes = f.read()

        # Re-export in-memory
        cur.execute("SELECT release, acmg_sf_version FROM curation_meta")
        rel, acmg = cur.fetchone()
        kb_dict = {"release": rel, "acmg_sf_version": acmg, "genes": {}, "loci": {}}

        cur.execute("SELECT symbol, topic, top_level_model, inheritance_model, mendelian_disease, disease, omim, penetrance_json, acmg_sf, insights_json, insights_provenance_json, diplotypes_json FROM genes ORDER BY row_order")
        for g_row in cur.fetchall():
            sym, topic, top_model, inh_model, mendelian, disease, omim, penetrance_json, acmg_sf, ins, ins_prov, diplo = g_row
            gene_dict = {}
            if top_model is not None:
                gene_dict["model"] = top_model
            gene_dict["topic"] = topic
            gene_dict["inheritance"] = {
                "model": inh_model,
                "mendelian_disease": bool(mendelian),
                "disease": disease,
                "omim": omim,
                "penetrance": json.loads(penetrance_json) if penetrance_json is not None else None,
            }
            gene_dict["acmg_sf"] = bool(acmg_sf)
            gene_dict["insights"] = json.loads(ins) if ins else None
            if ins_prov is not None:
                gene_dict["insights_provenance"] = json.loads(ins_prov)
            if diplo is not None:
                gene_dict["diplotypes"] = json.loads(diplo)
            kb_dict["genes"][sym] = gene_dict

        cur.execute("SELECT rsid, gene, chrom, pos_grch37, pos_grch38, ref, alt, allele_codes_json, role, limitation, limitation_ref, curated_tier, tier_rationale, tier_citation, tier_position, limitation_position FROM loci ORDER BY row_order")
        for l_row in cur.fetchall():
            rsid, gene, chrom, pos37, pos38, ref, alt, codes, role, lim, lim_ref, cur_tier, tier_rat, tier_cit, tier_pos, lim_pos = l_row
            loc_dict = {
                "gene": gene,
                "chrom": chrom,
                "pos_grch37": pos37,
                "pos_grch38": pos38,
                "ref": ref,
                "alt": alt,
                "allele_codes": json.loads(codes) if codes else None,
                "role": role,
            }
            if lim_pos == "before_interp":
                if lim_ref is not None:
                    loc_dict["limitation_ref"] = lim_ref
                else:
                    loc_dict["limitation"] = lim

            tier_dict = None
            if cur_tier is not None or tier_rat is not None or tier_cit is not None:
                tier_dict = {}
                if cur_tier is not None:
                    tier_dict["curated_tier"] = cur_tier
                if tier_rat is not None:
                    tier_dict["rationale"] = tier_rat
                if tier_cit is not None:
                    tier_dict["citation"] = tier_cit

            if tier_pos == "before_interp" and tier_dict is not None:
                loc_dict["tier"] = tier_dict

            loc_dict["interpretations"] = {}
            cur.execute("SELECT alt_count, category, significance, magnitude_json, repute, phenotype, drug_response, caveats_json FROM interpretations WHERE locus_rsid = ? ORDER BY alt_count", (rsid,))
            for i_row in cur.fetchall():
                ac, cat, sig, mag_json, rep, pheno, dr, cav = i_row
                loc_dict["interpretations"][ac] = {
                    "category": cat,
                    "significance": sig,
                    "magnitude": json.loads(mag_json),
                    "repute": rep,
                    "phenotype": pheno,
                    "drug_response": dr,
                    "caveats": json.loads(cav),
                }

            cur.execute("SELECT clinvar_json, gnomad_json, hpa_json, cpic_json FROM locus_evidence WHERE locus_rsid = ?", (rsid,))
            ev_row = cur.fetchone()
            if ev_row:
                ev_dict = {}
                if ev_row[0]: ev_dict["clinvar"] = json.loads(ev_row[0])
                if ev_row[1]: ev_dict["gnomad"] = json.loads(ev_row[1])
                if ev_row[2]: ev_dict["hpa"] = json.loads(ev_row[2])
                if ev_row[3]: ev_dict["cpic"] = json.loads(ev_row[3])
                loc_dict["evidence"] = ev_dict

            if lim_pos == "after_evidence":
                if lim_ref is not None:
                    loc_dict["limitation_ref"] = lim_ref
                else:
                    loc_dict["limitation"] = lim

            if tier_pos != "before_interp" and tier_dict is not None:
                loc_dict["tier"] = tier_dict

            kb_dict["loci"][rsid] = loc_dict

        nl = detect_newline(self.kb_path)
        reconstructed_kb_text = json.dumps(kb_dict, indent=2) + "\n"
        if nl == "\r\n":
            reconstructed_kb_text = reconstructed_kb_text.replace("\n", "\r\n")
        reconstructed_kb_bytes = reconstructed_kb_text.encode("utf-8")
        byte_identical = (disk_kb_bytes == reconstructed_kb_bytes)

        # Check collision status
        collision_detected = False
        try:
            self.check_collision(conn)
        except CurationConflictError:
            collision_detected = True

        conn.close()

        if not byte_identical:
            raise CurationValidationError(
                f"Byte-identity verification failed on {self.kb_path}: reconstructed {len(reconstructed_kb_bytes)} "
                f"bytes vs disk {len(disk_kb_bytes)} bytes."
            )

        return {
            "byte_identical": True,
            "kb_bytes": len(reconstructed_kb_bytes),
            "genes": len(kb_dict["genes"]),
            "loci": len(kb_dict["loci"]),
            "collision_detected": collision_detected,
        }

    def status(self) -> Dict[str, Any]:
        """Returns comprehensive status of workbench database and session manifest."""
        conn = self.get_connection()
        cur = conn.cursor()

        self.init_schema(conn)

        cur.execute("SELECT COUNT(*) FROM genes")
        gene_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM loci")
        locus_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM interpretations")
        interp_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM evidence_claims")
        claim_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM platform_coverage")
        coverage_count = cur.fetchone()[0]

        # Manifest status
        cur.execute("SELECT file_name, file_path, sha256, updated_at FROM _session_manifest")
        manifest_rows = cur.fetchall()
        file_status: Dict[str, Dict[str, Any]] = {}
        for f_name, f_path_str, recorded_sha, updated_at in manifest_rows:
            p = Path(f_path_str)
            if not p.exists():
                st = "MISSING"
                cur_sha = None
            else:
                cur_sha = compute_file_sha256(p)
                st = "MATCH" if cur_sha == recorded_sha else "MODIFIED_ON_DISK"

            file_status[f_name] = {
                "status": st,
                "path": str(p),
                "recorded_sha256": recorded_sha,
                "current_sha256": cur_sha,
                "updated_at": updated_at,
            }

        conn.close()

        return {
            "db_path": str(self.db_path),
            "genes": gene_count,
            "loci": locus_count,
            "interpretations": interp_count,
            "claims": claim_count,
            "coverage_rows": coverage_count,
            "files": file_status,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lucidase Curation Workbench CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync tracked JSON files into SQLite database")
    sync_parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite database")

    # export
    export_parser = subparsers.add_parser("export", help="Export SQLite data to tracked JSON files with collision guard")
    export_parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite database")
    export_parser.add_argument("--force", action="store_true", help="Bypass collision guard and force overwrite")

    # verify
    verify_parser = subparsers.add_parser("verify", help="Verify database integrity and byte-identity")
    verify_parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite database")

    # status
    status_parser = subparsers.add_parser("status", help="Print workbench status and manifest check")
    status_parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite database")

    args = parser.parse_args()
    workbench = CurationWorkbench(db_path=Path(args.db))

    try:
        if args.command == "sync":
            res = workbench.sync()
            print(f"[OK] Sync successful: {res['genes']} genes, {res['loci']} loci, {res['claims']} claims, {res['coverage_loci']} coverage loci.")
        elif args.command == "export":
            res = workbench.export(force=args.force)
            print(f"[OK] Export successful: {res['genes']} genes, {res['loci']} loci ({res['kb_bytes']} bytes), {res['claims']} claims, {res['coverage_loci']} coverage loci.")
        elif args.command == "verify":
            res = workbench.verify()
            print(f"[OK] Verification successful: 100% byte-identical ({res['kb_bytes']} bytes), 0 FK errors, collision_detected={res['collision_detected']}.")
        elif args.command == "status":
            res = workbench.status()
            print(f"Database: {res['db_path']}")
            print(f"Counts:   {res['genes']} genes, {res['loci']} loci, {res['interpretations']} interpretations, {res['claims']} claims, {res['coverage_rows']} coverage rows")
            print("Tracked Files:")
            for fname, finfo in res["files"].items():
                print(f"  - {fname:22} [{finfo['status']}] (updated {finfo['updated_at']})")
        return 0
    except (CurationConflictError, CurationValidationError, FileNotFoundError) as err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
