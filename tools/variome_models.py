"""
Canonical Variome data models
=============================
Models shared by the KB build and the source adapters:

- `UPSTREAM_LICENSES`: redistribution terms of the upstream sources.
- The adapter output models (`ClinVarRecord`, `DbsnpRecord`, `VepRecord`, `GnomadVariant`,
  `GnomadConstraint`, `ImportProvenance`): the only shapes downstream code sees from an upstream
  payload (anti-corruption layer, `tools/source_adapters.py`). A value the payload lacks is `None`
  and the model's `reasons` says why. Nothing is ever synthesised.
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


def normalize_edit(pos: int, ref: str, alt: str) -> tuple[int, str, str]:
    """Reduce a (1-based pos, ref, alt) change to its minimal left-aligned edit (start, deleted, inserted).

    Trailing bases shared by ref and alt are trimmed first, then leading ones (each leading base moves
    `start` right). Trimming the suffix first keeps an edit at the left edge of a repeat, which is how
    gnomAD and ClinVar write it. dbSNP SPDI deletions (`TCTT` > `T`) and VCF anchored deletions
    (`ATCT` > `A`) both reduce to the same edit (start, `TCT`, ``). Without the reference sequence this
    cannot shift an edit left past the allele's own bases, so it is exact only for SPDI or VCF input
    that already starts at the left edge of its repeat.
    """
    while ref and alt and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    while ref and alt and ref[0] == alt[0]:
        ref, alt, pos = ref[1:], alt[1:], pos + 1
    return pos, ref, alt


@dataclass(frozen=True)
class ImportProvenance:
    """Where a machine-imported value came from. Every field comes from the pinned payload or its meta."""
    source: str
    release: Optional[str]
    accession: Optional[str]
    url: str
    retrieved_at: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Contract C2 provenance (the sha256 is checked by QC and is not part of the KB)."""
        return {
            "source": self.source,
            "release": self.release,
            "accession": self.accession,
            "url": self.url,
            "curation_mode": CurationMode.MACHINE_IMPORTED.value,
            "retrieved_at": self.retrieved_at,
        }


@dataclass(frozen=True)
class ChromosomeGeometry:
    """One primary chromosome of an assembly. Coordinates are 1-based inclusive."""
    name: str                           # "1".."22", "X", "Y"
    length: int
    centromere_start: int
    centromere_end: int


@dataclass(frozen=True)
class AssemblyGeometry:
    """Reference geometry of one build. `sources` are the two UCSC tables (accession = table name)."""
    build: str                          # GRCh37 | GRCh38
    ucsc: str                           # hg19 | hg38
    chromosomes: dict[str, ChromosomeGeometry]
    sources: tuple[ImportProvenance, ...]


@dataclass(frozen=True)
class ClinVarRecord:
    """The ClinVar record selected for one locus. `accession` is None when the payload carries none."""
    accession: Optional[str]            # VCV000007105 (no version)
    accession_version: Optional[str]    # VCV000007105.212
    title: str
    obj_type: str
    review_status: str                  # exact ClinVar vocabulary
    stars: int
    conflicting: bool
    significance: Optional[str]
    selected_by: str
    reasons: dict[str, str] = field(default_factory=dict)
    provenance: Optional[ImportProvenance] = None


@dataclass(frozen=True)
class DbsnpPlacement:
    """One chromosome placement (one assembly) of a refsnp. `alleles` are SPDI (0-based pos, deleted, inserted)."""
    seq_id: str
    build: str                          # GRCh37 | GRCh38
    alleles: tuple[tuple[int, str, str], ...]

    @property
    def allele_set(self) -> frozenset[str]:
        """Every allele dbSNP lists at this placement, including the assembly reference."""
        return frozenset(seq for _, deleted, inserted in self.alleles for seq in (deleted, inserted))

    def locate(self, ref: str, alt: str) -> Optional[int]:
        """The 1-based VCF-style position of {ref, alt} at this placement, or None when dbSNP lacks the alleles.

        A single-base ref and alt must both be among dbSNP's alleles (ref/alt are build-independent
        variant and non-variant alleles, not assembly bases). An indel must equal one dbSNP edit after
        both are reduced with `normalize_edit`; its position is that of the VCF anchor base.
        """
        if len(ref) == 1 and len(alt) == 1:
            if {ref, alt} <= self.allele_set:
                return next((pos + 1 for pos, deleted, _ in self.alleles if len(deleted) == 1), None)
            return None
        _, deleted, inserted = normalize_edit(0, ref, alt)
        for pos, spdi_deleted, spdi_inserted in self.alleles:
            if spdi_deleted == spdi_inserted:
                continue
            start, d, i = normalize_edit(pos + 1, spdi_deleted, spdi_inserted)
            if (d, i) == (deleted, inserted):
                return start - 1
        return None


@dataclass(frozen=True)
class DbsnpRecord:
    rsid: str
    release: Optional[str]
    placements: dict[str, DbsnpPlacement]   # keyed by build
    reasons: dict[str, str] = field(default_factory=dict)
    provenance: Optional[ImportProvenance] = None

    def check_locus(self, build: str, pos: int, ref: str, alt: str) -> Optional[str]:
        """None when the curated position and alleles agree with dbSNP for `build`, else the reason."""
        placement = self.placements.get(build)
        if placement is None:
            return f"dbSNP has no {build} placement"
        found = placement.locate(ref, alt)
        if found is None:
            return f"{build} alleles {ref}/{alt} are not in dbSNP's allele set {sorted(placement.allele_set)}"
        if found != pos:
            return f"{build} position {pos} differs from dbSNP's {found}"
        return None


@dataclass(frozen=True)
class VepRecord:
    """MANE Select transcript and AlphaMissense for the locus allele. Absent values are None with a reason."""
    rsid: str
    mane_select_ensembl: Optional[str]
    mane_select_refseq: Optional[str]
    alphamissense_class: Optional[str]
    alphamissense_score: Optional[float]
    reasons: dict[str, str] = field(default_factory=dict)
    provenance: Optional[ImportProvenance] = None


@dataclass(frozen=True)
class GnomadVariant:
    variant_id: Optional[str]
    af: Optional[float]                 # pooled ac/an over the exome and genome records that have an > 0
    reasons: dict[str, str] = field(default_factory=dict)
    provenance: Optional[ImportProvenance] = None
    refusal: Optional[str] = None       # a named reason (source_adapters.GNOMAD_REFUSAL_*) when gnomAD refused the query


@dataclass(frozen=True)
class GnomadConstraint:
    symbol: Optional[str]
    pli: Optional[float]
    loeuf: Optional[float]              # the upper bound of the observed/expected LoF ratio
    reasons: dict[str, str] = field(default_factory=dict)
    provenance: Optional[ImportProvenance] = None


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
