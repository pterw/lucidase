"""
Segregation Engine: genotype-aware Mendelian inheritance (contract C5)
======================================================================
Port of web/src/core/inheritance.js. It matches the shared spec in
tests/vectors/inheritance.json, not the web code line by line. Pure functions:
no I/O, no knowledge-base lookup. The caller passes the gene's inheritance block.

- Offspring distribution = the patient's gametes (P(alt) = alt_count / 2) convolved
  with the partner's gametes. Partner models: `wildtype` (P(alt) = 0),
  `heterozygous` (0.5), `homozygous` (1) and `unscreened` (P(alt) = the gnomAD allele
  frequency, i.e. Hardy-Weinberg). The result is P(0), P(1), P(2) alt alleles in the
  child, and they sum to 1. An unscreened partner without a frequency is unavailable
  and says so; nothing is defaulted.
- Disease or recurrence wording exists only for genes whose
  `inheritance.mendelian_disease` is true: autosomal recessive affected = P(2),
  autosomal dominant affected = P(>=1) x penetrance. Every other model (risk factor,
  pharmacogenomic, trait) reports allele-transmission probabilities only.
- Compound heterozygosity says "phase unknown" and never asserts trans.
- Multi-locus findings cover loci on different chromosomes in `risk_factor` genes
  (owner ruling 9). They are labelled "assumes unlinked loci and a partner
  without these alleles". The gene filter matches the KB `model` value exactly.
"""

from __future__ import annotations

import math
from typing import Any

PARTNER_MODELS = ("wildtype", "heterozygous", "homozygous", "unscreened")

PHASE_UNKNOWN = "phase unknown (cis or trans cannot be determined from unphased genotypes)"
MULTI_LOCUS_ASSUMPTION = "assumes unlinked loci and a partner without these alleles"


def _check_alt_count(alt_count: Any) -> None:
    if isinstance(alt_count, bool) or alt_count not in (0, 1, 2):
        raise ValueError(f"alt-allele count must be 0, 1 or 2, got {alt_count!r}")


def _inheritance(gene: dict | None) -> dict:
    inh = gene.get("inheritance") if isinstance(gene, dict) else None
    if (
        not isinstance(inh, dict)
        or not isinstance(inh.get("mendelian_disease"), bool)
        or not isinstance(inh.get("model"), str)
    ):
        raise ValueError("gene has no valid inheritance block (model, mendelian_disease)")
    return inh


def offspring_distribution(patient_alt_count: int, partner_model: str, af: float | None = None) -> dict:
    """Alt-allele distribution in a child: {available: True, p0, p1, p2}, or
    {available: False, reason} when the unscreened model has no allele frequency."""
    _check_alt_count(patient_alt_count)
    if partner_model == "wildtype":
        partner_alt = 0.0
    elif partner_model == "heterozygous":
        partner_alt = 0.5
    elif partner_model == "homozygous":
        partner_alt = 1.0
    elif partner_model == "unscreened":
        if (
            isinstance(af, bool)
            or not isinstance(af, (int, float))
            or not math.isfinite(af)
            or af < 0
            or af > 1
        ):
            return {
                "available": False,
                "reason": (
                    "Not available: no gnomAD allele frequency for this variant, so an "
                    "unscreened partner cannot be modelled."
                ),
            }
        partner_alt = float(af)
    else:
        raise ValueError(f"unknown partner model {partner_model!r}")
    a = patient_alt_count / 2
    b = partner_alt
    return {
        "available": True,
        "p0": (1 - a) * (1 - b),
        "p1": a * (1 - b) + (1 - a) * b,
        "p2": a * b,
    }


def gene_outcome(gene: dict, dist: dict, allele: str = "variant") -> dict:
    """Outcome for a gene given an offspring distribution. Mendelian-disease genes report
    affected (and carrier) probabilities; every other model reports transmission only."""
    inh = _inheritance(gene)
    if not dist["available"]:
        return {
            "available": False,
            "kind": "mendelian" if inh["mendelian_disease"] else "transmission",
            "reason": dist["reason"],
        }
    p0, p1, p2 = dist["p0"], dist["p1"], dist["p2"]
    if inh["mendelian_disease"]:
        if inh["model"] == "autosomal_recessive":
            return {
                "available": True, "kind": "mendelian", "model": inh["model"],
                "p0": p0, "p1": p1, "p2": p2, "affected": p2, "carrier": p1,
                "label": "Chance a child is affected (two copies)",
            }
        if inh["model"] == "autosomal_dominant":
            penetrance = inh.get("penetrance")
            if isinstance(penetrance, bool) or not isinstance(penetrance, (int, float)):
                return {
                    "available": False, "kind": "mendelian", "model": inh["model"],
                    "p0": p0, "p1": p1, "p2": p2,
                    "reason": "Not available: the knowledge base has no penetrance for this dominant condition.",
                }
            return {
                "available": True, "kind": "mendelian", "model": inh["model"],
                "p0": p0, "p1": p1, "p2": p2, "affected": (p1 + p2) * penetrance,
                "label": "Chance a child is affected (at least one copy x penetrance)",
            }
        raise ValueError(f"Mendelian gene with unsupported model {inh['model']}")
    return {
        "available": True, "kind": "transmission", "model": inh["model"],
        "p0": p0, "p1": p1, "p2": p2,
        "inherits_allele": p1 + p2, "one_copy": p1, "two_copies": p2, "none": p0,
        "label": f"Chance a child inherits the {allele} allele",
    }


def patient_status(gene: dict, alt_count: int) -> dict:
    """is_affected / is_carrier exist only for Mendelian-disease genes, derived from the
    alt count. Only KB alt alleles are counted, so an unannotated allele is never a carrier."""
    inh = _inheritance(gene)
    _check_alt_count(alt_count)
    if not inh["mendelian_disease"]:
        return {}
    if inh["model"] == "autosomal_recessive":
        return {"is_affected": alt_count == 2, "is_carrier": alt_count == 1}
    if inh["model"] == "autosomal_dominant":
        return {"is_affected": alt_count >= 1}
    raise ValueError(f"Mendelian gene with unsupported model {inh['model']}")


def describe_segregation(gene_name: str, gene: dict, alt_count: int, af: float | None, allele: str) -> dict:
    """Per-record inheritance summary: the inputs a view needs to rerun the scenarios."""
    inh = _inheritance(gene)
    _check_alt_count(alt_count)
    return {
        "gene": gene_name,
        "model": inh["model"],
        "mendelian_disease": inh["mendelian_disease"],
        "disease": inh.get("disease"),
        "omim": inh.get("omim"),
        "penetrance": inh.get("penetrance"),
        "altCount": alt_count,
        "af": af,
        "allele": allele,
        **patient_status(gene, alt_count),
    }


def _is_candidate(rec: dict) -> bool:
    return (
        isinstance(rec, dict)
        and rec.get("standalone") is not False
        and rec.get("role") != "apoe_component"
        and rec.get("altCount") in (1, 2)
    )


def detect_multi_locus(records: list[dict], genes: dict[str, dict]) -> list[dict]:
    """Pairs of loci with alt_count > 0 on different chromosomes, in risk-factor genes.
    Recognition is by gene and alt count, never by genotype strings. The joint chance is the
    product of alt_count / 2, under the stated assumption."""
    eligible = [
        r for r in records
        if _is_candidate(r)
        and r.get("gene") in genes
        and _inheritance(genes[r["gene"]])["model"] == "risk_factor"
    ]
    findings = []
    for i, a in enumerate(eligible):
        for b in eligible[i + 1:]:
            if a["chrom"] == b["chrom"]:
                continue
            joint = (a["altCount"] / 2) * (b["altCount"] / 2)
            findings.append({
                "genes": [a["gene"], b["gene"]],
                "loci": [f"{a['rsid']} (Chr {a['chrom']})", f"{b['rsid']} (Chr {b['chrom']})"],
                "type": "Co-occurring variant alleles",
                "joint_transmission_prob": joint,
                "assumption": MULTI_LOCUS_ASSUMPTION,
                "description": (
                    f"This sample carries variant alleles in {a['gene']} ({a['rsid']}) and "
                    f"{b['gene']} ({b['rsid']}), on different chromosomes. "
                    f"Chance a child inherits both alleles: {joint * 100:.0f}% "
                    f"({a['altCount']}/2 x {b['altCount']}/2); {MULTI_LOCUS_ASSUMPTION}."
                ),
            })
    return findings


def detect_compound_heterozygosity(records: list[dict], genes: dict[str, dict]) -> list[dict]:
    """Possible compound heterozygosity: two or more loci of one recessive Mendelian gene that
    are each heterozygous. Unphased genotypes cannot place the alleles in cis or trans, so
    phase is never asserted."""
    by_gene: dict[str, list[dict]] = {}
    for r in records:
        if not r or r.get("altCount") != 1 or r.get("role") == "apoe_component":
            continue
        by_gene.setdefault(r["gene"], []).append(r)
    findings = []
    for gene, hets in by_gene.items():
        g = genes.get(gene)
        if not g or len(hets) < 2:
            continue
        inh = _inheritance(g)
        if not inh["mendelian_disease"] or inh["model"] != "autosomal_recessive":
            continue
        rsids = [r["rsid"] for r in hets]
        findings.append({
            "gene": gene,
            "loci": rsids,
            "phase": "unknown",
            "title": f"Possible compound heterozygote ({' / '.join(rsids)})",
            "significance": "Phase unknown",
            "summary": (
                f"Possible compound heterozygote in {gene}: heterozygous at "
                f"{' and '.join(rsids)}; {PHASE_UNKNOWN}."
            ),
            "segregation_notes": (
                "Each heterozygous locus is transmitted with probability 1/2 per child; whether a "
                "child could inherit both alleles together depends on phase, which is unknown."
            ),
        })
    return findings
