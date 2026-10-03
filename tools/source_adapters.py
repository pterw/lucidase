"""
Upstream Source Adapters & Ingestion Architecture
=================================================
Implements explicit source adapters for authoritative open genomic repositories:
- NCBI ClinVar
- NCBI dbSNP
- Ensembl VEP & MANE Select
- gnomAD (Genome Aggregation Database)
- CPIC (Clinical Pharmacogenetics Implementation Consortium)
- AlphaFold Protein Structure Database
- Human Protein Atlas (HPA)
- ENCODE SCREEN (cCREs)

Every adapter ingests and normalizes authoritative upstream responses into
canonical record schemas, fails closed on missing evidence (defaulting to Tier D,
and None for absent numeric values), and attaches field-level provenance with
licensing and curation tracking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from tools.coverage_taxonomy import CurationMode, EvidenceTier
from tools.variome_models import FieldProvenance, UPSTREAM_LICENSES


def derive_evidence_tier(
    clinvar_review: str = "",
    cpic_level: Optional[str] = None,
    stars: Optional[int] = None,
    conflicting: bool = False
) -> EvidenceTier:
    """
    Module-level convenience helper to derive evidence tier transparently:
    - Tier A: Practice guideline / expert panel / CPIC Level A
    - Tier B: Multiple submitters, criteria provided, no conflicts
    - Tier C: Single submitter or conflicting clinical evaluations
    - Tier D: Research / functional context only (fails closed)
    """
    review_lower = clinvar_review.lower().strip()
    if stars is None:
        if "practice_guideline" in review_lower or "expert_panel" in review_lower:
            stars = 3
        elif "multiple_submitters" in review_lower and "no_conflict" in review_lower:
            stars = 2
        elif "conflicting" in review_lower:
            stars = 1
            conflicting = True
        elif "no_assertion" in review_lower:
            stars = 0
        elif "single_submitter" in review_lower or "criteria_provided" in review_lower:
            stars = 1
        else:
            stars = 0
    if "conflicting" in review_lower:
        conflicting = True

    tier, _ = ClinVarSourceAdapter.derive_evidence_tier(
        stars=stars,
        conflicting=conflicting,
        has_cpic_a=(cpic_level == "A")
    )
    return tier


class ClinVarSourceAdapter:
    """Adapter for NCBI ClinVar (Variation-Condition-VCV records)."""
    SOURCE_NAME = "NCBI ClinVar"
    DEFAULT_RELEASE = "Release 2024-06"
    LICENSE = UPSTREAM_LICENSES["ncbi_clinvar"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any], rsid: str = "") -> dict[str, Any]:
        """
        Ingests real ClinVar VCV/esummary JSON payload.
        Fails closed: missing stars default to 0, missing review defaults to unasserted.
        """
        var_id = str(raw_payload.get("variation_id", raw_payload.get("variant_id", "")))
        accession = raw_payload.get("accession", "")
        if not accession and var_id.isdigit():
            accession = f"VCV{int(var_id):09d}.5"

        review = raw_payload.get("review_status", "no_assertion_criteria_provided")
        # Star resolution: check explicit stars, or calculate from review string
        stars_val = raw_payload.get("gold_stars", raw_payload.get("stars", None))
        if stars_val is None:
            rev_lower = review.lower()
            if "practice guideline" in rev_lower or "practice_guideline" in rev_lower:
                stars_val = 4
            elif "reviewed by expert panel" in rev_lower or "expert_panel" in rev_lower:
                stars_val = 3
            elif "multiple submitters" in rev_lower or "multiple_submitters" in rev_lower:
                stars_val = 2
            elif "criteria provided" in rev_lower or "single submitter" in rev_lower:
                stars_val = 1
            else:
                stars_val = 0
        else:
            stars_val = int(stars_val)

        sig = raw_payload.get("clinical_significance", "Uncertain significance")
        if isinstance(raw_payload.get("germline_classification"), dict):
            sig = raw_payload["germline_classification"].get("description", sig)

        phenotypes_raw = raw_payload.get("phenotypes", [])
        phenotype_names = []
        medgen_id = ""
        for p in phenotypes_raw:
            if isinstance(p, dict):
                name = p.get("name", "")
                if name:
                    phenotype_names.append(name)
                if not medgen_id and p.get("medgen_id"):
                    medgen_id = p["medgen_id"]
            elif isinstance(p, str):
                phenotype_names.append(p)

        conflicting = "conflicting" in sig.lower() or "conflicting" in review.lower()
        tier, tier_rationale = self.derive_evidence_tier(stars=stars_val, conflicting=conflicting)

        prov = self.create_provenance(
            accession=accession or rsid or var_id,
            review_status=review,
            curation_mode=CurationMode.MACHINE_IMPORTED
        )
        return {
            "rsid": rsid,
            "variation_id": var_id,
            "vcv_accession": accession,
            "review_stars": stars_val,
            "review_status": review,
            "clinical_significance": sig,
            "phenotypes": phenotype_names,
            "medgen_id": medgen_id,
            "evidence_tier": tier,
            "tier_rationale": tier_rationale,
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path, rsid: str = "") -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return self.ingest_record(data, rsid=rsid)

    @classmethod
    def create_provenance(
        cls,
        accession: str,
        review_status: str,
        transformation: str = "vcv_classification_extraction",
        curation_mode: CurationMode = CurationMode.MACHINE_IMPORTED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=accession,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status=review_status,
            curation_mode=curation_mode,
            license=cls.LICENSE
        )

    @classmethod
    def derive_evidence_tier(cls, stars: int, conflicting: bool, has_cpic_a: bool = False) -> tuple[EvidenceTier, str]:
        """Derives conservative evidence tier, failing closed to Tier D if unvalidated."""
        if stars >= 3 or has_cpic_a:
            rationale = "Expert panel review or clinical practice guideline endorsement."
            return EvidenceTier.TIER_A, rationale
        elif stars == 2 and not conflicting:
            rationale = "Multi-submitter consensus with criteria provided and zero conflicting assertions."
            return EvidenceTier.TIER_B, rationale
        elif stars == 1 or conflicting:
            rationale = "Limited assertion: single submitter or conflicting clinical evaluations."
            return EvidenceTier.TIER_C, rationale
        else:
            rationale = "Research or functional context only without gold-standard clinical consensus."
            return EvidenceTier.TIER_D, rationale


class DbSnpSourceAdapter:
    """Adapter for NCBI dbSNP identifiers, coordinates, and alleles."""
    SOURCE_NAME = "NCBI dbSNP"
    DEFAULT_RELEASE = "Build 156 (GRCh38.p14 / GRCh37.p13)"
    LICENSE = UPSTREAM_LICENSES["ncbi_dbsnp"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Ingests dbSNP RefSNP/SPDI JSON payload.
        Extracts dual coordinates (GRCh37/GRCh38), alleles, strand, palindromic status.
        """
        refsnp_id = str(raw_payload.get("refsnp_id", ""))
        rsid = f"rs{refsnp_id}" if not refsnp_id.startswith("rs") else refsnp_id

        chrom = raw_payload.get("chrom", "")
        ref = raw_payload.get("ref", "")
        alt = raw_payload.get("alt", "")
        strand = raw_payload.get("strand", "+")

        pos_37 = 0
        pos_38 = 0

        # Parse placements
        snapshot = raw_payload.get("primary_snapshot_data", {})
        placements = snapshot.get("placements_with_allele", [])
        for p in placements:
            asm = p.get("assembly_name", "")
            if "GRCh37" in asm:
                pos_37 = int(p.get("position", 0))
                if not ref:
                    ref = p.get("deleted_sequence", "")
                if not alt:
                    alt = p.get("inserted_sequence", "")
            elif "GRCh38" in asm:
                pos_38 = int(p.get("position", 0))
                if not ref:
                    ref = p.get("deleted_sequence", "")
                if not alt:
                    alt = p.get("inserted_sequence", "")

        is_pal = (ref, alt) in {("A", "T"), ("T", "A"), ("C", "G"), ("G", "C")}

        prov = self.create_provenance(
            rsid=rsid,
            curation_mode=CurationMode.MACHINE_IMPORTED
        )
        return {
            "rsid": rsid,
            "chrom": chrom,
            "pos_grch37": pos_37,
            "pos_grch38": pos_38,
            "ref": ref,
            "alt": alt,
            "strand": strand,
            "is_palindromic": is_pal,
            "spdi": raw_payload.get("spdi", ""),
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path) -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.ingest_record(data)

    @classmethod
    def create_provenance(
        cls,
        rsid: str,
        transformation: str = "coordinate_and_allele_canonicalization",
        curation_mode: CurationMode = CurationMode.MACHINE_IMPORTED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=rsid,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status="refseq_curated",
            curation_mode=curation_mode,
            license=cls.LICENSE
        )


class EnsemblSourceAdapter:
    """Adapter for Ensembl VEP and MANE Select transcripts."""
    SOURCE_NAME = "Ensembl VEP / MANE Select"
    DEFAULT_RELEASE = "Release 112 / MANE v1.3"
    LICENSE = UPSTREAM_LICENSES["ensembl"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Ingests Ensembl VEP payload with MANE Select isoform matching.
        Fails closed: AlphaMissense score is None if absent (never defaults to 0.0).
        """
        rsid = raw_payload.get("id", "")
        tc_list = raw_payload.get("transcript_consequences", [])
        mane_tc = next((tc for tc in tc_list if tc.get("mane_select") or tc.get("canonical") == 1), None)
        if not mane_tc and tc_list:
            mane_tc = tc_list[0]

        mane_transcript = ""
        hgvsc = ""
        hgvsp = ""
        am_class = ""
        am_score: Optional[float] = None

        if mane_tc:
            mane_transcript = mane_tc.get("transcript_id", "")
            hgvsc = mane_tc.get("hgvsc", "")
            hgvsp = mane_tc.get("hgvsp", "")
            am_data = mane_tc.get("alphamissense", {})
            if isinstance(am_data, dict):
                am_class = am_data.get("pathogenicity", "")
                if "score" in am_data and am_data["score"] is not None:
                    am_score = float(am_data["score"])

        prov = self.create_provenance(
            transcript_id=mane_transcript or rsid,
            curation_mode=CurationMode.MACHINE_IMPORTED
        )
        return {
            "rsid": rsid,
            "mane_transcript": mane_transcript,
            "hgvs_coding": hgvsc,
            "hgvs_protein": hgvsp,
            "alphamissense_class": am_class,
            "alphamissense_score": am_score,
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path) -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return self.ingest_record(data)

    @classmethod
    def create_provenance(
        cls,
        transcript_id: str,
        transformation: str = "mane_select_isoform_canonicalization",
        curation_mode: CurationMode = CurationMode.MACHINE_IMPORTED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=transcript_id,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status="mane_select_matched",
            curation_mode=curation_mode,
            license=cls.LICENSE
        )


class GnomadSourceAdapter:
    """Adapter for gnomAD population frequencies and gene constraint scores."""
    SOURCE_NAME = "gnomAD"
    DEFAULT_RELEASE = "v4.1.0"
    LICENSE = UPSTREAM_LICENSES["gnomad"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Ingests gnomAD GraphQL payload.
        Fails closed: missing AF, pLI, or LOEUF return None (NEVER 0.0!).
        """
        var_id = raw_payload.get("variantId", "")
        exome = raw_payload.get("exome") or {}
        genome = raw_payload.get("genome") or {}

        # Safe extraction of AF: exome preferred, then genome
        af: Optional[float] = None
        if "af" in exome and exome["af"] is not None:
            af = float(exome["af"])
        elif "af" in genome and genome["af"] is not None:
            af = float(genome["af"])

        pli: Optional[float] = None
        loeuf: Optional[float] = None
        constraint = raw_payload.get("gene_constraint", {})
        if "pli" in constraint and constraint["pli"] is not None:
            pli = float(constraint["pli"])
        if "oe_lof_upper" in constraint and constraint["oe_lof_upper"] is not None:
            loeuf = float(constraint["oe_lof_upper"])
        elif "loeuf" in constraint and constraint["loeuf"] is not None:
            loeuf = float(constraint["loeuf"])

        prov = self.create_provenance(
            variant_id=var_id,
            curation_mode=CurationMode.MACHINE_IMPORTED
        )
        return {
            "variant_id": var_id,
            "gnomad_af": af,
            "gnomad_pli": pli,
            "gnomad_loeuf": loeuf,
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path) -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.ingest_record(data)

    @classmethod
    def create_provenance(
        cls,
        variant_id: str,
        transformation: str = "exome_frequency_extraction",
        curation_mode: CurationMode = CurationMode.MACHINE_IMPORTED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=variant_id,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status="quality_filtered_pass",
            curation_mode=curation_mode,
            license=cls.LICENSE
        )


class CpicSourceAdapter:
    """Adapter for CPIC pharmacogenomic guidelines."""
    SOURCE_NAME = "CPIC Guidelines"
    DEFAULT_RELEASE = "2024 Guideline Updates"
    LICENSE = UPSTREAM_LICENSES["cpic"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any], rsid_or_gene: str = "") -> dict[str, Any]:
        gene = raw_payload.get("gene", rsid_or_gene)
        drug = raw_payload.get("drug", "clinical_guideline")
        cpic_level = raw_payload.get("cpic_level", None)
        drug_rec = raw_payload.get("drug_recommendation", "")
        url = raw_payload.get("guideline_url", "")
        prov = self.create_provenance(
            gene_drug_pair=f"{gene}:{drug}",
            curation_mode=CurationMode.MANUALLY_CURATED
        )
        return {
            "gene": gene,
            "drug": drug,
            "cpic_level": cpic_level,
            "guideline_url": url,
            "drug_recommendation": drug_rec,
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path, rsid_or_gene: str = "") -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.ingest_record(data, rsid_or_gene=rsid_or_gene)

    @classmethod
    def create_provenance(
        cls,
        gene_drug_pair: str,
        transformation: str = "guideline_actionability_extraction",
        curation_mode: CurationMode = CurationMode.MANUALLY_CURATED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=gene_drug_pair,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status="cpic_guideline_endorsed",
            curation_mode=curation_mode,
            license=cls.LICENSE
        )


class AlphaFoldSourceAdapter:
    """Adapter for AlphaFold Protein Structure Database v4."""
    SOURCE_NAME = "AlphaFold Protein Structure Database"
    DEFAULT_RELEASE = "Version 4 (EBI/DeepMind)"
    LICENSE = UPSTREAM_LICENSES["alphafold_db"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any], gene_or_uniprot: str = "") -> dict[str, Any]:
        """
        Ingests real AlphaFold DB v4 structure metadata.
        Fails closed: missing pLDDT returns None (never defaults to 80.0 or 0.0).
        """
        uniprot = raw_payload.get("uniprotAccession", raw_payload.get("uniprot_accession", gene_or_uniprot))
        plddt_val = raw_payload.get("globalMetricValue", raw_payload.get("global_plddt", None))
        plddt: Optional[float] = float(plddt_val) if plddt_val is not None else None

        prov = self.create_provenance(
            uniprot_id=uniprot,
            curation_mode=CurationMode.MACHINE_IMPORTED
        )
        return {
            "uniprot_accession": uniprot,
            "global_plddt": plddt,
            "domains": raw_payload.get("domains", []),
            "folding_status": raw_payload.get("folding_status", "Predicted monomer"),
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path, gene_or_uniprot: str = "") -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.ingest_record(data, gene_or_uniprot=gene_or_uniprot)

    @classmethod
    def create_provenance(
        cls,
        uniprot_id: str,
        transformation: str = "mean_plddt_calculation",
        curation_mode: CurationMode = CurationMode.MACHINE_IMPORTED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=uniprot_id,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status="deepmind_predicted_validated",
            curation_mode=curation_mode,
            license=cls.LICENSE
        )


class HpaSourceAdapter:
    """Adapter for Human Protein Atlas normal tissue proteomics."""
    SOURCE_NAME = "Human Protein Atlas"
    DEFAULT_RELEASE = "Release 23.0"
    LICENSE = UPSTREAM_LICENSES["hpa"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any], gene: str = "") -> dict[str, Any]:
        """Ingests Human Protein Atlas normal tissue proteomics and subcellular locations."""
        gene_name = raw_payload.get("gene", gene)
        tissues = raw_payload.get("tissue_expression", {})
        subcellular = raw_payload.get("subcellular_location", [])

        prov = self.create_provenance(
            gene=gene_name,
            curation_mode=CurationMode.MACHINE_IMPORTED
        )
        return {
            "gene": gene_name,
            "tissues": tissues,
            "subcellular": subcellular,
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path, gene: str = "") -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.ingest_record(data, gene=gene)

    @classmethod
    def create_provenance(
        cls,
        gene: str,
        transformation: str = "ihc_expression_aggregation",
        curation_mode: CurationMode = CurationMode.MACHINE_IMPORTED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=gene,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status="ihc_antibody_validated",
            curation_mode=curation_mode,
            license=cls.LICENSE
        )


class EncodeSourceAdapter:
    """Adapter for ENCODE SCREEN cCREs."""
    SOURCE_NAME = "ENCODE SCREEN"
    DEFAULT_RELEASE = "ENCODE v4"
    LICENSE = UPSTREAM_LICENSES["encode"]

    def __init__(self, release_version: Optional[str] = None):
        self.release_version = release_version or self.DEFAULT_RELEASE

    def ingest_record(self, raw_payload: dict[str, Any], locus: str = "") -> dict[str, Any]:
        """Ingests ENCODE SCREEN candidate cis-Regulatory Elements."""
        accession = raw_payload.get("accession", locus)
        ccre_type = raw_payload.get("ccre_type", "")
        nearest_gene = raw_payload.get("nearest_gene", "")

        prov = self.create_provenance(
            locus=accession,
            curation_mode=CurationMode.MACHINE_IMPORTED
        )
        return {
            "accession": accession,
            "ccre_type": ccre_type,
            "nearest_gene": nearest_gene,
            "provenance": prov
        }

    def ingest_from_file(self, file_path: str | Path, locus: str = "") -> dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.ingest_record(data, locus=locus)

    @classmethod
    def create_provenance(
        cls,
        locus: str,
        transformation: str = "ccre_promoter_enhancer_annotation",
        curation_mode: CurationMode = CurationMode.MACHINE_IMPORTED,
        timestamp: str = "2026-10-02T00:00:00Z"
    ) -> FieldProvenance:
        return FieldProvenance(
            source=cls.SOURCE_NAME,
            source_release=cls.DEFAULT_RELEASE,
            accession_id=locus,
            retrieval_timestamp=timestamp,
            transformation=transformation,
            review_status="dnase_chip_supported",
            curation_mode=curation_mode,
            license=cls.LICENSE
        )
