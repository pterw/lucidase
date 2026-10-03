"""
Variant Annotator: pipeline knowledge base, same rules as the web app
=====================================================================
The desktop annotator reads the SAME knowledge base as the web app,
`web/src/knowledge-base.json` (schema v2, written only by tools/build_canonical_kb.py),
and applies the same rules. The shared vectors in tests/vectors/*.json are the spec
(tests/test_vectors.py runs them); this module matches the spec, not the web code line
by line:

- `load_knowledge_base` / `validate_kb`: schema_version 2 and the required fields, fail fast
  (`KbSchemaError`). Nothing clinical is defaulted.
- `resolve_alt_count` (contract C3): build-independent plus-strand alleles, strand
  complementing only for single-base non-palindromic sites, haploid only on X/Y/MT.
- `classify` (contract C4): one record per KB locus, always, with a per-sample coverage
  state computed at analysis time through `tools.coverage_taxonomy.derive_coverage_state`.
  Absence of a finding is never reported as absence of risk.
- `resolve_apoe`: the single APOE row built from rs429358 and rs7412 alt counts. Its
  `rsid` "APOE-STATUS" is an internal row id, not an rsid. Atypical combinations are
  `diplotype: "atypical"` with no interpretation, and an unresolved one is `None`.
- Inheritance (contract C5) lives in `segregation_engine.py`.

`VariantAnnotator.__init__` touches nothing on disk: the knowledge base is loaded on first
use, from the repo's `web/src/knowledge-base.json` unless a path (or a loaded KB) is passed.
The biotools orchestrator, which contacts external services, is only created when
`enrich_record_with_biotools` is called.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from genomic_parser import ParseResult
from segregation_engine import (
    PARTNER_MODELS,
    describe_segregation,
    detect_compound_heterozygosity,
    detect_multi_locus,
    gene_outcome,
    offspring_distribution,
)
from tools.coverage_taxonomy import (
    NO_CALL_REASON,
    NOT_ASSAYED_REASON,
    VCF_ABSENT_REASON,
    CoverageState,
    EvidenceSufficiency,
    derive_coverage_state,
)

DEFAULT_KB_PATH = Path(__file__).resolve().parent / "web" / "src" / "knowledge-base.json"

# ===========================================================================
# ACMG SF v3.2 Actionable Gene List (81 Genes)
# ===========================================================================
ACMG_SF_GENES = {
    "ACTA2", "ACTC1", "ACVRL1", "APC", "APOB", "ATP7B", "BAG3", "BMPR1A", "BRCA1",
    "BRCA2", "BTD", "CACNA1S", "CALM1", "CALM2", "CALM3", "CASQ2", "COL3A1",
    "DES", "DSC2", "DSG2", "DSP", "ENG", "FBN1", "FLNC", "GAA", "GLA", "HFE",
    "HNF1A", "KCNH2", "KCNJ2", "KCNQ1", "LDLR", "LMNA", "MAX", "MEN1", "MLH1",
    "MSH2", "MSH6", "MUTYH", "MYBPC3", "MYH11", "MYH7", "MYL2", "MYL3", "NF2",
    "OTC", "PALB2", "PCSK9", "PKP2", "PMS2", "PRKAG2", "PTEN", "RB1", "RBM20",
    "RET", "RPE65", "RYR1", "RYR2", "SCN5A", "SDHAF2", "SDHB", "SDHC", "SDHD",
    "SMAD3", "SMAD4", "STK11", "TGFBR1", "TGFBR2", "TMEM127", "TMEM43", "TNNC1",
    "TNNI3", "TNNT2", "TP53", "TPM1", "TRDN", "TSC1", "TSC2", "TTN", "VHL", "WT1",
}

# ===========================================================================
# Knowledge base loading and validation (contract C2, schema v2)
# ===========================================================================
class KbSchemaError(ValueError):
    """The knowledge base does not match schema v2. `problems` lists every problem found."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        plural = "" if len(problems) == 1 else "s"
        super().__init__(f"Invalid knowledge base ({len(problems)} problem{plural}):\n- " + "\n- ".join(problems))


_TIERS = ("Tier A", "Tier B", "Tier C", "Tier D")
_TIER_SOURCES = ("clinvar_review", "cpic_level", "curated")
_SUFFICIENCY = ("sufficient", "insufficient")
_ROLES = ("standard", "apoe_component")
_MODELS = ("autosomal_recessive", "autosomal_dominant", "risk_factor", "pharmacogenomic", "trait")
_DIPLOTYPES = ("e2/e2", "e2/e3", "e2/e4", "e3/e3", "e3/e4", "e4/e4")
_PER_SAMPLE_FIELDS = ("coverage_state", "sample_observation", "assay_coverage")
_BUILD_FIELDS = {"GRCh37": "pos_grch37", "GRCh38": "pos_grch38"}


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and len(v) > 0


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _check_interp(interp: Any, path: str, problems: list[str]) -> None:
    if not isinstance(interp, dict):
        problems.append(f"{path}: missing or not an object")
        return
    for k in ("category", "significance", "repute", "phenotype"):
        if not _is_str(interp.get(k)):
            problems.append(f"{path}.{k}: required non-empty string")
    if not _is_num(interp.get("magnitude")):
        problems.append(f"{path}.magnitude: required number")
    if "drug_response" not in interp or not (interp["drug_response"] is None or isinstance(interp["drug_response"], str)):
        problems.append(f"{path}.drug_response: required string or null")
    caveats = interp.get("caveats")
    if not isinstance(caveats, list) or not all(isinstance(c, str) for c in caveats):
        problems.append(f"{path}.caveats: required array of strings")


def _check_locus(key: str, locus: Any, genes: dict, problems: list[str]) -> None:
    p = f"loci.{key}"
    if not isinstance(locus, dict):
        problems.append(f"{p}: not an object")
        return
    if locus.get("rsid") != key:
        problems.append(f'{p}.rsid: "{locus.get("rsid")}" does not match its key')
    if not _is_str(locus.get("gene")):
        problems.append(f"{p}.gene: required")
    elif locus["gene"] not in genes:
        problems.append(f'{p}.gene: unknown gene "{locus["gene"]}"')
    if not _is_str(locus.get("chrom")):
        problems.append(f"{p}.chrom: required string")
    for f in _BUILD_FIELDS.values():
        v = locus.get(f)
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            problems.append(f"{p}.{f}: required positive integer")
    for f in ("ref", "alt"):
        v = locus.get(f)
        if not isinstance(v, str) or not re.fullmatch(r"[ACGT]+", v):
            problems.append(f"{p}.{f}: required ACGT sequence")
    if locus.get("ref") == locus.get("alt"):
        problems.append(f"{p}: ref and alt are identical")

    if "allele_codes" not in locus:
        problems.append(f"{p}.allele_codes: required (null or {{D, I}})")
    elif locus["allele_codes"] is not None:
        c = locus["allele_codes"]
        ok = isinstance(c, dict) and sorted(c) == ["D", "I"] and all(c[k] in ("ref", "alt") for k in ("D", "I"))
        if not ok:
            problems.append(f'{p}.allele_codes: must map D and I to "ref" or "alt"')

    interps = locus.get("interpretations")
    if not isinstance(interps, dict):
        problems.append(f"{p}.interpretations: required object")
    else:
        for k in ("0", "1", "2"):
            _check_interp(interps.get(k), f"{p}.interpretations.{k}", problems)
        extra = [k for k in interps if k not in ("0", "1", "2")]
        if extra:
            problems.append(f"{p}.interpretations: unexpected keys {', '.join(extra)}")

    if not isinstance(locus.get("evidence"), dict):
        problems.append(f"{p}.evidence: required object")
    if locus.get("evidence_tier") not in _TIERS:
        problems.append(f"{p}.evidence_tier: must be one of {', '.join(_TIERS)}")
    if locus.get("tier_source") not in _TIER_SOURCES:
        problems.append(f"{p}.tier_source: must be one of {', '.join(_TIER_SOURCES)}")
    if locus.get("tier_source") != "clinvar_review":
        if not _is_str(locus.get("tier_rationale")):
            problems.append(f"{p}.tier_rationale: required unless tier_source is clinvar_review")
        if not _is_str(locus.get("tier_citation")):
            problems.append(f"{p}.tier_citation: required unless tier_source is clinvar_review")
    if locus.get("evidence_sufficiency") not in _SUFFICIENCY:
        problems.append(f"{p}.evidence_sufficiency: must be one of {', '.join(_SUFFICIENCY)}")
    if "limitation" not in locus or not (locus["limitation"] is None or _is_str(locus["limitation"])):
        problems.append(f"{p}.limitation: required string or null")
    if locus.get("role") not in _ROLES:
        problems.append(f"{p}.role: must be one of {', '.join(_ROLES)}")


def _check_gene(symbol: str, gene: Any, problems: list[str]) -> None:
    p = f"genes.{symbol}"
    if not isinstance(gene, dict):
        problems.append(f"{p}: not an object")
        return
    inh = gene.get("inheritance")
    if not isinstance(inh, dict):
        problems.append(f"{p}.inheritance: required object")
    else:
        if inh.get("model") not in _MODELS:
            problems.append(f"{p}.inheritance.model: must be one of {', '.join(_MODELS)}")
        if not isinstance(inh.get("mendelian_disease"), bool):
            problems.append(f"{p}.inheritance.mendelian_disease: required boolean")
        for k in ("disease", "omim", "penetrance"):
            if k not in inh:
                problems.append(f"{p}.inheritance.{k}: required (null allowed)")
    if not isinstance(gene.get("acmg_sf"), bool):
        problems.append(f"{p}.acmg_sf: required boolean")
    if "insights" not in gene or not (gene["insights"] is None or isinstance(gene["insights"], dict)):
        problems.append(f"{p}.insights: required object or null")
    if "diplotypes" in gene:
        d = gene["diplotypes"]
        if not isinstance(d, dict) or sorted(d) != sorted(_DIPLOTYPES):
            problems.append(f"{p}.diplotypes: must hold exactly {', '.join(_DIPLOTYPES)}")
        else:
            for name in _DIPLOTYPES:
                _check_interp(d[name], f"{p}.diplotypes.{name}", problems)


def _scan_per_sample(node: Any, path: str, problems: list[str]) -> None:
    """The KB holds no per-sample field anywhere (C2)."""
    if isinstance(node, list):
        for i, v in enumerate(node):
            _scan_per_sample(v, f"{path}[{i}]", problems)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in _PER_SAMPLE_FIELDS:
                problems.append(f"{path}.{k}: per-sample field must not appear in the knowledge base")
            _scan_per_sample(v, f"{path}.{k}", problems)


@dataclass
class KnowledgeBase:
    """A validated, indexed copy of the pipeline knowledge base."""

    manifest: dict
    genes: dict[str, dict]
    loci: dict[str, dict]
    loci_list: list[dict]
    by_position: dict[str, dict[str, str]]


def validate_kb(data: Any) -> KnowledgeBase:
    """Validate a parsed KB (schema v2) and return an indexed deep copy. Raises KbSchemaError
    listing every problem. The input is not modified."""
    problems: list[str] = []
    if not isinstance(data, dict):
        raise KbSchemaError(["knowledge base is not an object"])

    if data.get("schema_version") != 2 or isinstance(data.get("schema_version"), bool):
        problems.append(f"schema_version: expected 2, got {json.dumps(data.get('schema_version'))}")
    manifest = data.get("manifest")
    if not isinstance(manifest, dict):
        problems.append("manifest: required object")
    elif not _is_str(manifest.get("guardrail")):
        problems.append("manifest.guardrail: required non-empty string")
    genes, loci = data.get("genes"), data.get("loci")
    if not isinstance(genes, dict):
        problems.append("genes: required object")
    if not isinstance(loci, dict):
        problems.append("loci: required object")

    if isinstance(genes, dict) and isinstance(loci, dict):
        for symbol, gene in genes.items():
            _check_gene(symbol, gene, problems)
        for key, locus in loci.items():
            _check_locus(key, locus, genes, problems)
        for build, field_name in _BUILD_FIELDS.items():
            seen: dict[str, str] = {}
            for key, locus in loci.items():
                if not isinstance(locus, dict) or not isinstance(locus.get(field_name), int):
                    continue
                pos = f"{locus.get('chrom')}:{locus[field_name]}"
                if pos in seen:
                    problems.append(f"duplicate position {pos} in {build}: {seen[pos]} and {key}")
                else:
                    seen[pos] = key
    _scan_per_sample(data, "kb", problems)
    if problems:
        raise KbSchemaError(problems)

    kb = copy.deepcopy(data)
    by_position: dict[str, dict[str, str]] = {build: {} for build in _BUILD_FIELDS}
    for locus in kb["loci"].values():
        for build, field_name in _BUILD_FIELDS.items():
            by_position[build][f"{locus['chrom']}:{locus[field_name]}"] = locus["rsid"]
    return KnowledgeBase(kb["manifest"], kb["genes"], kb["loci"], list(kb["loci"].values()), by_position)


def load_knowledge_base(path: str | Path | None = None) -> KnowledgeBase:
    """Read and validate the knowledge base (default: web/src/knowledge-base.json in the repo)."""
    target = Path(path) if path is not None else DEFAULT_KB_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise KbSchemaError([f"{target}: not valid JSON ({err})"]) from err
    return validate_kb(data)


# ===========================================================================
# Allele resolution (contract C3)
# ===========================================================================
_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}
_HAPLOID_CHROMS = {"X", "Y", "MT"}


def _is_base(s: Any) -> bool:
    return isinstance(s, str) and s in _COMPLEMENT


def is_palindromic(ref: str, alt: str) -> bool:
    """A site is palindromic when ref and alt are single bases that complement each other (A/T, C/G)."""
    return _is_base(ref) and _is_base(alt) and _COMPLEMENT[ref] == alt


def _count_alts(alleles: list[str], ref: str, alt: str) -> Optional[int]:
    n = 0
    for a in alleles:
        if a == alt:
            n += 1
        elif a != ref:
            return None
    return n


def resolve_alt_count(locus: dict, alleles: list[str] | None, assay: str) -> dict:
    """locus: {ref, alt, allele_codes, chrom}; alleles: list of tokens or None; assay: "array" | "vcf".
    VCF alleles are plus-strand by definition, so only a non-VCF assay may strand-complement.

    Returns {"ok": True, "altCount": 0|1|2, "strandFlipped": bool} or
    {"ok": False, "reason": "no_call" | "unresolvable"}. "palindromic_ambiguous" is in the
    contract's reason set but never produced: a palindromic site's complement is the same
    pair, so an unmatched call there is simply "unresolvable".
    """
    if not isinstance(alleles, list) or not alleles:
        return {"ok": False, "reason": "no_call"}
    ref, alt, codes, chrom = locus["ref"], locus["alt"], locus.get("allele_codes"), locus.get("chrom")

    called = []
    for a in alleles:
        if a in ("D", "I") and codes and codes.get(a) in ("ref", "alt"):
            called.append(ref if codes[a] == "ref" else alt)
        else:
            called.append(a)
    if len(called) == 1:  # haploid counts as two copies only where the chromosome is haploid
        if chrom not in _HAPLOID_CHROMS:
            return {"ok": False, "reason": "unresolvable"}
        called = [called[0], called[0]]
    if len(called) != 2:
        return {"ok": False, "reason": "unresolvable"}

    direct = _count_alts(called, ref, alt)
    if direct is not None:
        return {"ok": True, "altCount": direct, "strandFlipped": False}
    # Only an array may complement; a VCF's alleles are plus-strand, so a foreign alt stays unresolvable.
    can_complement = assay != "vcf" and _is_base(ref) and _is_base(alt) and not is_palindromic(ref, alt)
    if can_complement and all(_is_base(a) for a in called):
        flipped = _count_alts([_COMPLEMENT[a] for a in called], ref, alt)
        if flipped is not None:
            return {"ok": True, "altCount": flipped, "strandFlipped": True}
    return {"ok": False, "reason": "unresolvable"}


# ===========================================================================
# Classification and coverage (contract C4)
# ===========================================================================
OBSERVATION_VARIANT_PRESENT = "variant_present"
OBSERVATION_WILD_TYPE = "wild_type"
OBSERVATION_CALL_UNAVAILABLE = "call_unavailable"

_SUMMARY_STATES = (
    CoverageState.SUPPORTED_AND_OBSERVED,
    CoverageState.SUPPORTED_NOT_OBSERVED,
    CoverageState.NOT_TESTED_BY_ARRAY,
    CoverageState.INSUFFICIENT_EVIDENCE,
)


def _sample_observation(variant_present: Optional[bool]) -> str:
    if variant_present is None:
        return OBSERVATION_CALL_UNAVAILABLE
    return OBSERVATION_VARIANT_PRESENT if variant_present else OBSERVATION_WILD_TYPE


def _derive_state(assay: str, call, resolution: Optional[dict], sufficiency: str) -> dict:
    """{coverage_state, sample_observation, reason} through the shared C4 rule."""
    suff = EvidenceSufficiency(sufficiency)
    if call is None:
        ev = derive_coverage_state(suff, assayed=False, assay=assay)
        reason = VCF_ABSENT_REASON if assay == "vcf" else NOT_ASSAYED_REASON
    elif call.alleles is None or (resolution is not None and not resolution["ok"] and resolution["reason"] == "no_call"):
        ev = derive_coverage_state(suff, assayed=False, assay=assay)
        reason = NO_CALL_REASON
    elif resolution is None or not resolution["ok"]:
        ev = derive_coverage_state(suff, resolvable=False)
        reason = ev.reason
    else:
        ev = derive_coverage_state(suff, alt_count=resolution["altCount"])
        reason = ev.reason
    return {
        "coverage_state": ev.state.value,
        "sample_observation": _sample_observation(ev.variant_present),
        "reason": reason,
    }


def summarize_coverage(records: list[dict], outside_count: int = 0) -> dict:
    """Counts each record in exactly one state. `outside_count` is the number of file markers
    that match no KB locus (a per-file figure). An unknown state raises rather than being dropped."""
    counts = {s.value: 0 for s in _SUMMARY_STATES}
    for r in records:
        if r["coverage_state"] not in counts:
            raise ValueError(f"unknown coverage state {r['coverage_state']!r} on {r['rsid']}")
        counts[r["coverage_state"]] += 1
    return {
        "supported_and_observed_count": counts["supported_and_observed"],
        "supported_not_observed_count": counts["supported_not_observed"],
        "not_tested_by_array_count": counts["not_tested_by_array"],
        "insufficient_evidence_count": counts["insufficient_evidence"],
        "outside_coverage_count": outside_count,
        "total_loci": len(records),
    }


def _match_calls(parse: ParseResult, kb: KnowledgeBase) -> tuple[dict[str, list], int]:
    """Calls matched to KB loci. A call whose rsID is a KB key matches that locus and is never re-matched
    by position. Any other call (no rsID, or an rsID the KB lacks) matches by chrom:pos for the file's build."""
    by_rsid: dict[str, list] = {}
    matched = 0
    positions = kb.by_position.get(parse.build)
    for call in parse.calls:
        rsid = None
        if call.rsid is not None and call.rsid in kb.loci:
            rsid = call.rsid
        elif positions is not None and call.pos is not None:
            rsid = positions.get(f"{call.chrom}:{call.pos}")
        if rsid is None:
            continue
        matched += 1
        by_rsid.setdefault(rsid, []).append(call)
    return by_rsid, matched


def _same_alleles(a, b) -> bool:
    if a.alleles is None or b.alleles is None:
        return a.alleles is None and b.alleles is None
    return sorted(a.alleles) == sorted(b.alleles)


_POSITION_FIELD = {"GRCh37": "pos_grch37", "GRCh38": "pos_grch38"}


def classify(parse: ParseResult, kb: KnowledgeBase) -> dict:
    """One record per KB locus, always, so absence is never silent. Returns
    {"records": [...] in KB order, "summary": coverage counts}."""
    by_rsid, matched = _match_calls(parse, kb)
    pos_field = _POSITION_FIELD.get(parse.build)

    records = []
    for locus in kb.loci_list:
        calls = by_rsid.get(locus["rsid"], [])
        call = calls[0] if calls else None
        conflicting = call is not None and any(not _same_alleles(c, call) for c in calls)

        resolution = None
        if call is not None and call.alleles is not None:
            # Two calls for one locus that disagree are never guessed between.
            if conflicting:
                resolution = {"ok": False, "reason": "unresolvable"}
            else:
                resolution = resolve_alt_count(locus, call.alleles, parse.assay)
        state = _derive_state(parse.assay, call, resolution, locus["evidence_sufficiency"])

        resolved = resolution is not None and resolution["ok"]
        alt_count = resolution["altCount"] if resolved else None
        if pos_field:
            pos = locus[pos_field]
        else:
            pos = call.pos if call is not None and call.pos is not None else None
        records.append({
            "rsid": locus["rsid"],
            "gene": locus["gene"],
            "chrom": locus["chrom"],
            "pos": pos,
            "genotype_display": "/".join(call.alleles) if call is not None and call.alleles is not None else None,
            "altCount": alt_count,
            "strandFlipped": resolution["strandFlipped"] if resolved else None,
            **state,
            "interpretation_key": None if alt_count is None else str(alt_count),
            "interpretation": None if alt_count is None else locus["interpretations"][str(alt_count)],
            "evidence": locus["evidence"],
            "evidence_tier": locus["evidence_tier"],
            "tier_source": locus["tier_source"],
            "tier_rationale": locus["tier_rationale"],
            "tier_citation": locus["tier_citation"],
            "evidence_sufficiency": locus["evidence_sufficiency"],
            "limitation": locus["limitation"],
            "acmg_sf": kb.genes[locus["gene"]]["acmg_sf"],
            "role": locus["role"],
            # APOE components feed the combined APOE finding; views must not list them on their own.
            "standalone": locus["role"] != "apoe_component",
        })
    outside = max(0, len(parse.calls) - matched)
    return {"records": records, "summary": summarize_coverage(records, outside)}


# ===========================================================================
# APOE (single row from rs429358 + rs7412)
# ===========================================================================
APOE_E4_RSID = "rs429358"
APOE_E2_RSID = "rs7412"
APOE_ROW_ID = "APOE-STATUS"  # internal row id, not an rsid

ATYPICAL = "atypical"
ATYPICAL_REASON = "requires an e1-type haplotype; cannot be resolved from genotype array data"
PHASE_CAVEAT = "phase unknown: e1/e3 is the rare alternative"

# (rs429358 alt count = e4 copies, rs7412 alt count = e2 copies) -> diplotype
_DIPLOTYPE_BY_COUNTS = {
    (0, 0): "e3/e3",
    (1, 0): "e3/e4",
    (2, 0): "e4/e4",
    (0, 1): "e2/e3",
    (0, 2): "e2/e2",
    (1, 1): "e2/e4",
    (2, 1): ATYPICAL,
    (1, 2): ATYPICAL,
    (2, 2): ATYPICAL,
}


def display_diplotype(diplotype: str) -> str:
    """"e3/e4" gives "ε3/ε4"."""
    return diplotype.replace("e", "ε")


def _component_summary(components: list[dict]) -> str:
    return ", ".join(f"{c['rsid']}:{c['genotype_display'] if c.get('genotype_display') is not None else '--'}" for c in components)


def resolve_apoe(component_records: list[dict], kb: Any) -> dict:
    """Builds the single APOE finding from the two classified component records (any order).
    `kb` needs `.genes` and `.loci`. A diplotype is asserted only when both components resolve:
    a missing, no-call or unresolvable component gives `diplotype: None`, never wild-type and
    never "presumed e3". Interpretation text comes from the KB; nothing clinical is typed here."""
    e4 = next((r for r in component_records if r["rsid"] == APOE_E4_RSID), None)
    e2 = next((r for r in component_records if r["rsid"] == APOE_E2_RSID), None)
    if e4 is None or e2 is None:
        raise ValueError(f"APOE needs both component records ({APOE_E4_RSID}, {APOE_E2_RSID})")
    gene = kb.genes.get("APOE")
    base = kb.loci.get(APOE_E4_RSID)
    if not gene or "diplotypes" not in gene or not base:
        raise ValueError("The knowledge base has no APOE gene diplotypes or rs429358 locus, so APOE cannot be assembled.")
    components = [e4, e2]

    common = {
        "rsid": APOE_ROW_ID,
        "gene": "APOE",
        "chrom": base["chrom"],
        "pos": e4.get("pos"),
        "altCount": None,
        "strandFlipped": None,
        "evidence": base["evidence"],
        "evidence_tier": base["evidence_tier"],
        "tier_source": base["tier_source"],
        "tier_rationale": base["tier_rationale"],
        "tier_citation": base["tier_citation"],
        "evidence_sufficiency": base["evidence_sufficiency"],
        "limitation": base["limitation"],
        "acmg_sf": gene["acmg_sf"],
        "role": "standard",
        "standalone": True,
        "components": components,
    }

    def unresolved(state: str, reason: str, observation: str, diplotype: Optional[str]) -> dict:
        return {
            **common,
            "genotype_display": _component_summary(components),
            "coverage_state": state,
            "sample_observation": observation,
            "reason": reason,
            "interpretation_key": None,
            "interpretation": None,
            "diplotype": diplotype,
            "caveat": None,
        }

    # A component with no allele count means no diplotype. An unresolvable genotype outranks a missing one.
    missing = [c for c in components if c["altCount"] is None]
    if missing:
        insufficient = CoverageState.INSUFFICIENT_EVIDENCE.value
        state = insufficient if any(c["coverage_state"] == insufficient for c in missing) else CoverageState.NOT_TESTED_BY_ARRAY.value
        reason = "; ".join(f"{c['rsid']}: {c['reason']}" for c in missing if c["coverage_state"] == state)
        return unresolved(state, reason, OBSERVATION_CALL_UNAVAILABLE, None)

    key = (e4["altCount"], e2["altCount"])
    diplotype = _DIPLOTYPE_BY_COUNTS.get(key)
    if diplotype is None:
        raise ValueError(f"APOE: impossible allele counts {key}")
    if diplotype == ATYPICAL:
        return unresolved(
            CoverageState.INSUFFICIENT_EVIDENCE.value, ATYPICAL_REASON, OBSERVATION_VARIANT_PRESENT, ATYPICAL
        )

    kb_interp = gene["diplotypes"].get(diplotype)
    if not kb_interp:
        raise ValueError(f"The knowledge base has no APOE {diplotype} interpretation.")
    caveat = PHASE_CAVEAT if diplotype == "e2/e4" else None
    wild_type = diplotype == "e3/e3"
    sufficient = all(c["evidence_sufficiency"] == "sufficient" for c in components)
    if not sufficient:
        state = CoverageState.INSUFFICIENT_EVIDENCE.value
    elif wild_type:
        state = CoverageState.SUPPORTED_NOT_OBSERVED.value
    else:
        state = CoverageState.SUPPORTED_AND_OBSERVED.value
    return {
        **common,
        "genotype_display": f"{display_diplotype(diplotype)} ({_component_summary(components)})",
        "coverage_state": state,
        "sample_observation": OBSERVATION_WILD_TYPE if wild_type else OBSERVATION_VARIANT_PRESENT,
        "reason": None if sufficient else "locus evidence is insufficient",
        "interpretation_key": diplotype,
        "interpretation": {**kb_interp, "caveats": [*kb_interp["caveats"], *([caveat] if caveat else [])]},
        "diplotype": diplotype,
        "caveat": caveat,
    }


def assemble_findings(records: list[dict], kb: Any, outside_count: int = 0) -> dict:
    """Replaces the two APOE component records with the one APOE finding. Returns
    {"listed", "apoe", "summary"}: `listed` is every standalone record plus the APOE finding
    (or the unchanged standalone records when the KB has no APOE components), and `summary`
    counts each listed record once."""
    standalone = [r for r in records if r["standalone"]]
    components = [r for r in records if r["role"] == "apoe_component"]
    apoe = resolve_apoe(components, kb) if components else None
    listed = [*standalone, apoe] if apoe else standalone
    return {"listed": listed, "apoe": apoe, "summary": summarize_coverage(listed, outside_count)}


# ===========================================================================
# Desktop view of the findings
# ===========================================================================
_STATE_LABEL = {
    "not_tested_by_array": "Not tested by this file",
    "insufficient_evidence": "Insufficient evidence",
    "supported_not_observed": "Not detected",
    "supported_and_observed": "Detected",
}
_REPORTED_CATEGORIES = ("Pathogenic", "Carrier", "Pharmacogenomics", "Risk Factor", "Trait")


@dataclass
class AnnotationRecord:
    """One finding row for the desktop views, built from a classified record (never a guess).

    `genotype` is the alleles as read, e.g. "A/G"; for APOE it is the diplotype plus the two
    component genotypes. Values the KB does not hold are None, not 0.
    """

    rsid: str  # "APOE-STATUS" is an internal row id for the combined APOE finding
    gene: str
    genotype: str
    chrom: str
    pos: Optional[int]
    build: str
    coverage_state: str
    sample_observation: str
    reason: Optional[str]
    alt_count: Optional[int]
    category: str
    clinical_significance: str
    phenotype: str
    magnitude: Optional[float]
    repute: str
    drug_response: str
    caveats: list[str]
    evidence_tier: str
    review_stars: Optional[int]
    gnomad_af: Optional[float]
    gnomad_pli: Optional[float]
    hpa_tissues: dict[str, str]
    hpa_subcellular: list[str]
    limitation: Optional[str]
    acmg_actionable: bool
    segregation: Optional[dict]
    raw: dict
    # Biotools live insights (filled only by enrich_record_with_biotools)
    vep_consequence: str = ""
    vep_sift: str = ""
    vep_alphamissense_class: str = ""
    vep_alphamissense_score: Optional[float] = None
    vep_loeuf: Optional[float] = None
    alphafold_plddt: Optional[float] = None
    alphafold_domains: list[str] = field(default_factory=list)
    encode_tissues: dict[str, float] = field(default_factory=dict)
    alphagenome_status: str = "Ready / Key Needed"

    @property
    def variant_present(self) -> bool:
        return self.sample_observation == OBSERVATION_VARIANT_PRESENT


@dataclass
class AnnotationReport:
    """Everything the desktop shows for one parsed file."""

    build: str
    kb_release: str
    records: list[AnnotationRecord]
    coverage: dict
    compound_heterozygote_findings: list[dict]
    multi_locus_findings: list[dict]


def _segregation(rec: dict, kb: KnowledgeBase) -> Optional[dict]:
    """Inheritance inputs and outcomes per partner model. Genotype-aware: it uses the alt count."""
    gene_name = rec["gene"]
    gene = kb.genes[gene_name]
    gnomad = (rec["evidence"].get("gnomad") or {})
    af = gnomad.get("af")
    if rec["rsid"] == APOE_ROW_ID:
        # APOE transmits e4 by its e4 copy count (rs429358), so e4/e4 transmits e4 with probability 1.
        if rec.get("diplotype") in (None, ATYPICAL):
            return None
        e4_count = rec["components"][0]["altCount"]
        alt_count, allele = e4_count, "e4"
    else:
        if rec["altCount"] is None:
            return None
        alt_count = rec["altCount"]
        allele = kb.loci[rec["rsid"]]["alt"]
    out = describe_segregation(gene_name, gene, alt_count, af, allele)
    out["scenarios"] = {
        m: gene_outcome(gene, offspring_distribution(alt_count, m, af), allele) for m in PARTNER_MODELS
    }
    if rec["rsid"] == APOE_ROW_ID:
        out["e4_carrier"] = alt_count > 0
    return out


def _to_annotation(rec: dict, kb: KnowledgeBase, build: str) -> AnnotationRecord:
    interp = rec["interpretation"]
    evidence = rec["evidence"]
    clinvar = evidence.get("clinvar") or {}
    gnomad = evidence.get("gnomad") or {}
    hpa = evidence.get("hpa") or {}
    state = rec["coverage_state"]
    if interp is not None:
        category, significance, phenotype = interp["category"], interp["significance"], interp["phenotype"]
        magnitude, repute = interp["magnitude"], interp["repute"]
        drug, caveats = interp.get("drug_response") or "", list(interp["caveats"])
    else:
        category, significance = "Not available", _STATE_LABEL[state]
        phenotype = rec["reason"] or ""
        magnitude, repute, drug, caveats = None, "", "", []
    genotype = rec["genotype_display"] if rec["genotype_display"] is not None else "not tested"
    if rec["rsid"] == APOE_ROW_ID and rec.get("diplotype") == ATYPICAL:
        genotype = f"atypical ({_component_summary(rec['components'])})"
    return AnnotationRecord(
        rsid=rec["rsid"],
        gene=rec["gene"],
        genotype=genotype,
        chrom=rec["chrom"],
        pos=rec["pos"],
        build=build,
        coverage_state=state,
        sample_observation=rec["sample_observation"],
        reason=rec["reason"],
        alt_count=rec["altCount"],
        category=category,
        clinical_significance=significance,
        phenotype=phenotype,
        magnitude=magnitude,
        repute=repute,
        drug_response=drug,
        caveats=caveats,
        evidence_tier=rec["evidence_tier"],
        # Locus-level ClinVar stars are shown only next to an interpreted genotype, never beside "not tested".
        review_stars=clinvar.get("stars") if interp is not None else None,
        gnomad_af=gnomad.get("af"),
        gnomad_pli=gnomad.get("pli"),
        hpa_tissues=dict(hpa.get("tissues") or {}),
        hpa_subcellular=list(hpa.get("subcellular") or []),
        limitation=rec["limitation"],
        acmg_actionable=bool(rec["acmg_sf"]),
        segregation=_segregation(rec, kb),
        raw=rec,
    )


class VariantAnnotator:
    """Classifies a parsed file against the pipeline KB and builds the desktop findings.

    Construction does no I/O: the KB is loaded on first use (from `kb_path`, else the repo's
    web/src/knowledge-base.json) unless an already validated `kb` is passed.
    """

    def __init__(self, kb_path: str | Path | None = None, kb: KnowledgeBase | None = None):
        self._kb_path = kb_path
        self._kb = kb
        self._biotools = None

    @property
    def kb(self) -> KnowledgeBase:
        if self._kb is None:
            self._kb = load_knowledge_base(self._kb_path)
        return self._kb

    @property
    def biotools(self):
        """The biotools orchestrator, created on first use. It contacts external services."""
        if self._biotools is None:
            from biotools_orchestrator import BiotoolsOrchestrator

            self._biotools = BiotoolsOrchestrator()
        return self._biotools

    def annotate_genome(self, parse: ParseResult) -> AnnotationReport:
        """One finding per KB locus (APOE as one row), with coverage, inheritance and the
        compound / multi-locus findings. Findings with a variant present come first, by magnitude."""
        kb = self.kb
        classified = classify(parse, kb)
        assembled = assemble_findings(classified["records"], kb, classified["summary"]["outside_coverage_count"])
        listed = assembled["listed"]
        rows = [_to_annotation(r, kb, parse.build) for r in listed]
        rows.sort(key=lambda a: (not a.variant_present, -(a.magnitude or 0.0)))
        return AnnotationReport(
            build=parse.build,
            kb_release=str(kb.manifest.get("release", "unknown")),
            records=rows,
            coverage=assembled["summary"],
            compound_heterozygote_findings=detect_compound_heterozygosity(listed, kb.genes),
            multi_locus_findings=detect_multi_locus(listed, kb.genes),
        )

    def summarize_annotations(self, report: AnnotationReport) -> dict[str, Any]:
        """Counts of variants PRESENT by category, plus the coverage counts. A locus that was not
        tested, or whose genotype could not be read, is counted under coverage, never as clear."""
        categories: dict[str, list[AnnotationRecord]] = {c: [] for c in _REPORTED_CATEGORIES}
        for r in report.records:
            if r.variant_present and r.category in categories:
                categories[r.category].append(r)
        acmg = [
            r for r in report.records
            if r.variant_present and r.acmg_actionable and r.category in ("Pathogenic", "Risk Factor", "Carrier")
        ]
        carriers = [r for r in report.records if r.segregation and r.segregation.get("is_carrier")]
        return {
            "total_loci": len(report.records),
            "pathogenic_count": len(categories["Pathogenic"]),
            "carrier_count": len(categories["Carrier"]),
            "pgx_count": len(categories["Pharmacogenomics"]),
            "risk_factor_count": len(categories["Risk Factor"]),
            "acmg_actionable_findings": len(acmg),
            "categories": categories,
            "acmg_findings": acmg,
            "carrier_findings": carriers,
            "coverage": report.coverage,
            "compound_heterozygote_findings": report.compound_heterozygote_findings,
            "multi_locus_findings": report.multi_locus_findings,
        }

    def enrich_record_with_biotools(self, record: AnnotationRecord) -> AnnotationRecord:
        """Enrich a record with live data from ClinVar, Ensembl, AlphaFold and ENCODE.

        This SENDS the rsID (and gene symbol) to external services; the web app never does.
        """
        if record.rsid == APOE_ROW_ID:
            # Gene-level AlphaFold and ENCODE for APOE; "APOE-STATUS" is not an rsid, so it is never sent.
            af = self.biotools.analyze_alphafold_structure("APOE")
            if "uniprot_id" in af:
                record.alphafold_plddt = af.get("global_plddt")
                record.alphafold_domains = af.get("domains", [])
            enc = self.biotools.query_encode_expression("APOE")
            if "top_expressing_tissues" in enc:
                record.encode_tissues = enc["top_expressing_tissues"]
            return record

        enriched = self.biotools.enrich_variant(
            rsid=record.rsid,
            gene=record.gene,
            genotype=record.genotype,
            chrom=str(record.chrom),
            pos=record.pos,
        )
        if enriched.vep_consequence:
            record.vep_consequence = enriched.vep_consequence
        if enriched.vep_sift:
            record.vep_sift = enriched.vep_sift
        if enriched.vep_alphamissense_class:
            record.vep_alphamissense_class = enriched.vep_alphamissense_class
        if enriched.vep_alphamissense_score is not None:
            record.vep_alphamissense_score = enriched.vep_alphamissense_score
        if enriched.vep_loeuf is not None:
            record.vep_loeuf = enriched.vep_loeuf
        if enriched.alphafold_plddt is not None:
            record.alphafold_plddt = enriched.alphafold_plddt
        if enriched.alphafold_domains:
            record.alphafold_domains = enriched.alphafold_domains
        if enriched.encode_top_tissues:
            record.encode_tissues = enriched.encode_top_tissues
        record.alphagenome_status = enriched.alphagenome_status
        return record
