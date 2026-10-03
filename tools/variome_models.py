"""
Canonical Variome data models
=============================
Models shared by the KB build and the source adapters:

- `UPSTREAM_LICENSES` and `FieldProvenance`: the anti-corruption layer's provenance record
  (`tools/source_adapters.py`).
- `GenotypeInterpretation`: what one alt-allele count means at a locus (contract C2 `Interp`).
  It holds knowledge only. Nothing here depends on one person's sample: observed genotype,
  coverage state and sample observation are computed at analysis time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tools.coverage_taxonomy import CurationMode

class LicenseMeta(str):
    """String subclass supporting attribute and dict-like metadata access."""
    def __new__(cls, text: str, meta: Optional[dict[str, Any]] = None):
        obj = str.__new__(cls, text)
        obj._meta = meta or {}
        return obj

    def __getitem__(self, item: str) -> Any:
        if item == "license":
            return str(self)
        if item in self._meta:
            return self._meta[item]
        return str(self)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str) and item in self._meta:
            return True
        return super().__contains__(item)


def _make_license(name: str, redistribution: str, commercial: bool, citation: str) -> LicenseMeta:
    return LicenseMeta(name, {
        "license": name,
        "redistribution": redistribution,
        "commercial_use": commercial,
        "citation": citation
    })


# Standard upstream license definitions with full redistribution constraints
UPSTREAM_LICENSES: dict[str, LicenseMeta] = {
    "ncbi_clinvar": _make_license("Public Domain / Open Data (NCBI)", "Unrestricted open redistribution", True, "Landrum MJ, et al. ClinVar. Nucleic Acids Res. 2020"),
    "ncbi_dbsnp": _make_license("Public Domain (US Government / NLM)", "Unrestricted public domain", True, "Sherry ST, et al. dbSNP. Nucleic Acids Res. 2001"),
    "ensembl": _make_license("EMBL-EBI Open Terms of Use", "Freely available for academic and commercial use", True, "Martin FJ, et al. Ensembl 2023. Nucleic Acids Res. 2023"),
    "gnomad": _make_license("Open Access (Broad Institute, ODC-ODbL)", "Open Database License (ODbL) 1.0", True, "Chen S, et al. gnomAD v4. Nature 2024"),
    "cpic": _make_license("Creative Commons Attribution 4.0 International (CC-BY 4.0)", "Redistribution permitted with attribution", True, "Relling MV, et al. CPIC Guidelines. Clin Pharmacol Ther. 2020"),
    "hpa": _make_license("Creative Commons Attribution-ShareAlike 4.0 International (CC-BY-SA 4.0)", "ShareAlike redistribution permitted with attribution", True, "Uhlén M, et al. Human Protein Atlas. Science 2015"),
    "alphafold_db": _make_license("Creative Commons Attribution 4.0 International (CC-BY 4.0)", "Redistribution permitted with attribution to DeepMind / EMBL-EBI", True, "Jumper J, et al. AlphaFold. Nature 2021"),
    "encode": _make_license("ENCODE Consortium Open Access Policy", "Unrestricted open access post-moratorium", True, "ENCODE Project Consortium. Nature 2020"),
    "acmg": _make_license("ACMG Educational & Clinical Practice Terms", "Educational and non-commercial clinical guidance reference", False, "Miller DT, et al. ACMG SF v3.2. Genet Med. 2023"),
}

# Aliases for friendly querying
UPSTREAM_LICENSES["ClinVar"] = UPSTREAM_LICENSES["ncbi_clinvar"]
UPSTREAM_LICENSES["dbSNP"] = UPSTREAM_LICENSES["ncbi_dbsnp"]
UPSTREAM_LICENSES["Ensembl"] = UPSTREAM_LICENSES["ensembl"]
UPSTREAM_LICENSES["gnomAD"] = UPSTREAM_LICENSES["gnomad"]
UPSTREAM_LICENSES["CPIC"] = UPSTREAM_LICENSES["cpic"]
UPSTREAM_LICENSES["Human Protein Atlas"] = UPSTREAM_LICENSES["hpa"]
UPSTREAM_LICENSES["AlphaFold DB"] = UPSTREAM_LICENSES["alphafold_db"]
UPSTREAM_LICENSES["ENCODE"] = UPSTREAM_LICENSES["encode"]
UPSTREAM_LICENSES["ACMG"] = UPSTREAM_LICENSES["acmg"]


@dataclass
class FieldProvenance:
    """Provenance audit record for an individual data field."""
    source: str
    source_release: str
    accession_id: str
    retrieval_timestamp: str
    transformation: str
    review_status: str
    curation_mode: CurationMode
    license: str


@dataclass
class GenotypeInterpretation:
    """Interpretation of one alt-allele count (0, 1 or 2) at a locus (contract C2 `Interp`)."""
    category: str                   # e.g. Pathogenic, Carrier, Pharmacogenomics, Risk Factor, Trait, Not detected
    significance: str               # Short assertion label
    magnitude: float                # Clinical priority scale (0.0 to 10.0)
    repute: str                     # Good, Bad, Neutral
    phenotype: str                  # Scientific phenotype description
    drug_response: Optional[str] = None
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "significance": self.significance,
            "magnitude": self.magnitude,
            "repute": self.repute,
            "phenotype": self.phenotype,
            "drug_response": self.drug_response,
            "caveats": list(self.caveats),
        }
