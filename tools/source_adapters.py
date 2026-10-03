"""
Upstream source adapters: the anti-corruption layer (AGENTS.md section 2)
=========================================================================
The only module that names a field of an upstream payload. It reads the pinned captures under
`tools/fixtures/upstream/real/` (ClinVar esummary, dbSNP refsnp, Ensembl VEP, gnomAD GraphQL) and
returns our models from `tools/variome_models.py`. Downstream code never sees a raw dict.

Rules every adapter follows:
- Fail closed. A value the payload lacks is `None` and the model's `reasons` names why. Nothing is
  synthesised: no default accession, no fallback transcript, no 0.0 placeholder.
- Fail fast on a vocabulary it does not know (an unknown ClinVar review status raises).
- Provenance (`retrieved_at`, `url`, `sha256`) comes from the capture's `.meta.json`, `release`
  from the payload or the request recorded in the meta, never from a constant.

Only sources with real pinned payloads have an adapter. AlphaFold, CPIC, HPA and ENCODE data stay
manually curated in the curation file.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional

from tools.variome_models import (
    ClinVarRecord,
    DbsnpPlacement,
    DbsnpRecord,
    GnomadConstraint,
    GnomadVariant,
    ImportProvenance,
    VepRecord,
    normalize_edit,
)

CLINVAR_CONFLICTING = "criteria provided, conflicting classifications"
# The exact ClinVar review-status vocabulary -> gold stars. Lookup is exact, never by substring.
REVIEW_STATUS_STARS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, single submitter": 1,
    CLINVAR_CONFLICTING: 1,
    "no assertion criteria provided": 0,
    "no classification provided": 0,
    # ClinVar's wording for a reference-allele record; it occurs in the pinned rs429358 capture.
    "no classification for the single variant": 0,
}
STAR_ALLELE_TITLE = re.compile(r"[A-Za-z0-9]+\*\d+[A-Za-z]?")
BUILDS = ("GRCh37", "GRCh38")


class AdapterError(ValueError):
    """The payload cannot be read safely (unknown vocabulary, ambiguity, wrong record)."""


class PayloadIntegrityError(AdapterError):
    """A pinned payload does not match its meta."""


# =============================================================================
# Pinned payloads
# =============================================================================
@dataclass(frozen=True)
class PinnedPayload:
    path: Path
    data: Any
    meta: dict[str, Any]

    def provenance(self, source: str, release: Optional[str], accession: Optional[str]) -> ImportProvenance:
        return ImportProvenance(
            source=source,
            release=release,
            accession=accession,
            url=self.meta["url"],
            retrieved_at=self.meta["retrieved_at"],
            sha256=self.meta["sha256_of_body"],
        )


def _meta_path(body_path: Path) -> Path:
    return body_path.with_name(body_path.name[: -len(".json")] + ".meta.json")


def load_pinned(body_path: Path | str) -> PinnedPayload:
    """Load a capture after checking its bytes against the sha256 in its meta."""
    body_path = Path(body_path)
    meta_path = _meta_path(body_path)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body = body_path.read_bytes()
    except OSError as exc:
        raise PayloadIntegrityError(f"{body_path}: cannot read capture or meta ({exc})") from exc
    if meta.get("http_status") != 200 or not meta.get("sha256_of_body"):
        raise PayloadIntegrityError(f"{body_path}: capture was not a successful response")
    if hashlib.sha256(body).hexdigest() != meta["sha256_of_body"]:
        raise PayloadIntegrityError(f"{body_path}: sha256 does not match {meta_path.name}")
    return PinnedPayload(body_path, json.loads(body.decode("utf-8")), meta)


def verify_pinned_payloads(root: Path | str) -> list[str]:
    """One error per pinned payload whose sha256 or size disagrees with its meta (empty when all match)."""
    root = Path(root)
    if not root.is_dir():
        return [f"upstream payload directory not found: {root}"]
    errors = []
    metas = sorted(root.rglob("*.meta.json"))
    if not metas:
        errors.append(f"no pinned payloads under {root}")
    for meta_path in metas:
        body_path = meta_path.with_name(meta_path.name[: -len(".meta.json")] + ".json")
        rel = body_path.relative_to(root).as_posix()
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("http_status") != 200:
                continue  # a recorded failure has no body to check
            body = body_path.read_bytes()
        except (OSError, ValueError) as exc:
            errors.append(f"pinned payload {rel}: unreadable ({exc})")
            continue
        if hashlib.sha256(body).hexdigest() != meta.get("sha256_of_body"):
            errors.append(f"pinned payload {rel}: sha256 does not match its meta")
        elif len(body) != meta.get("bytes"):
            errors.append(f"pinned payload {rel}: size {len(body)} differs from meta bytes {meta.get('bytes')}")
    return errors


# =============================================================================
# ClinVar (esummary)
# =============================================================================
def _spdi_edit(spdi: Any) -> Optional[tuple[int, str, str]]:
    """Parse `NC_000007.14:117559590:TCTT:T` (0-based) into a normalised 1-based edit, or None."""
    if not isinstance(spdi, str) or spdi.count(":") != 3:
        return None
    _, pos, deleted, inserted = spdi.split(":")
    if not pos.isdigit():
        return None
    return normalize_edit(int(pos) + 1, deleted, inserted)


def _dbsnp_numbers(variation: dict[str, Any]) -> set[str]:
    return {x.get("db_id") for x in variation.get("variation_xrefs", []) if x.get("db_source") == "dbSNP"}


class TruncatedSearch(AdapterError):
    """An esearch reports more hits (count) than it returned (idlist)."""


def esearch_uids(esearch: bytes | dict[str, Any]) -> list[str]:
    """Uids of an esearch (raw body or parsed). The one completeness rule: count must equal len(idlist).

    An esearch with no hits is a valid answer (count 0, empty idlist). A body that is not an esearch
    result raises `AdapterError`; a truncated one raises `TruncatedSearch`. Never an empty list by default.
    """
    try:
        raw = json.loads(esearch) if isinstance(esearch, (bytes, str)) else esearch
        result = raw["esearchresult"]
        ids = [str(uid) for uid in result["idlist"]]
        count = int(result["count"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AdapterError(f"ClinVar esearch body is not a readable esearch result ({exc!r})") from exc
    if count != len(ids):
        raise TruncatedSearch(f"ClinVar esearch is truncated: count {count} but {len(ids)} ids; raise retmax")
    return ids


def check_clinvar_search_complete(esearch: dict[str, Any], esummary: dict[str, Any]) -> None:
    """Raise unless the esearch was complete (count == len(idlist)) and esummary covers exactly its ids (L2)."""
    ids = esearch_uids(esearch)
    if set(ids) != set(esummary.get("result", {}).get("uids", [])):
        raise AdapterError("ClinVar esummary does not cover exactly the esearch ids")


def _clinvar_record(raw: dict[str, Any], selected_by: str, provenance: Optional[ImportProvenance]) -> ClinVarRecord:
    germline = raw.get("germline_classification")
    if not isinstance(germline, dict):
        raise AdapterError(f"ClinVar record {raw.get('uid')!r} has no germline_classification")
    status = germline.get("review_status")
    if status not in REVIEW_STATUS_STARS:
        raise AdapterError(f"unknown ClinVar review status {status!r}")
    reasons: dict[str, str] = {}
    accession = raw.get("accession") or None
    if accession is None:
        reasons["accession"] = "the payload record carries no accession"
    significance = germline.get("description") or None
    if significance is None:
        reasons["significance"] = "the payload record carries no germline classification description"
    return ClinVarRecord(
        accession=accession,
        accession_version=raw.get("accession_version") or None,
        title=raw.get("title", ""),
        obj_type=raw.get("obj_type", ""),
        review_status=status,
        stars=REVIEW_STATUS_STARS[status],
        conflicting=status == CLINVAR_CONFLICTING,
        significance=significance,
        selected_by=selected_by,
        reasons=reasons,
        provenance=provenance,
    )


def select_clinvar_record(
    esummary: dict[str, Any],
    rsid: str,
    pos: int,
    ref: str,
    alt: str,
    provenance: Optional[ImportProvenance] = None,
) -> Optional[ClinVarRecord]:
    """Pick the ClinVar record that describes this locus allele, or None when none does.

    ClinVar's search by rsid is noisy (rs6025 also returns a LRRK2 record) and returns haplotypes and
    diplotypes that merely contain the variant. Selection, in order:
    1. keep records with a variation whose dbSNP xref is `rsid` (constraints L3) and whose canonical
       SPDI, normalised with `normalize_edit`, equals the locus change `pos` `ref` > `alt` on GRCh38
       (so a reference-allele record such as `T:T`, or the C>G record at a C>T locus, never matches);
    2. if a star-allele haplotype record (`GENE*N`) remains, take it: it is the allele-defining record
       (the single-variant record for CYP2C19 c.681G>A reads "Likely benign" for a loss-of-function allele);
    3. otherwise take the one remaining single-variant record. More than one raises, none gives None.
    """
    number = rsid[2:]
    want = normalize_edit(pos, ref, alt)
    records = esummary.get("result", {})
    matches = []
    for uid in records.get("uids", []):
        raw = records[uid]
        for variation in raw.get("variation_set", []):
            if number in _dbsnp_numbers(variation) and _spdi_edit(variation.get("canonical_spdi")) == want:
                matches.append(raw)
                break
    stars = [r for r in matches if r.get("obj_type") == "Haplotype" and STAR_ALLELE_TITLE.fullmatch(r.get("title", ""))]
    if stars:
        if len(stars) > 1:
            raise AdapterError(f"{rsid}: several star-allele haplotype records match: {[r['accession'] for r in stars]}")
        return _clinvar_record(stars[0], "star-allele haplotype record containing the locus variant", provenance)
    singles = [r for r in matches if len(r.get("variation_set", [])) == 1]
    if len(singles) > 1:
        raise AdapterError(f"{rsid}: several single-variant ClinVar records match: {[r.get('accession') for r in singles]}")
    if not singles:
        return None
    return _clinvar_record(singles[0], "single-variant record whose dbSNP xref and SPDI match the locus", provenance)


# =============================================================================
# dbSNP (refsnp)
# =============================================================================
def parse_dbsnp(raw: dict[str, Any], provenance: Optional[ImportProvenance] = None) -> DbsnpRecord:
    """Read the GRCh37 and GRCh38 chromosome placements and their SPDI alleles (0-based) from a refsnp."""
    placements: dict[str, DbsnpPlacement] = {}
    for placement in raw.get("primary_snapshot_data", {}).get("placements_with_allele", []):
        annot = placement.get("placement_annot", {})
        if annot.get("seq_type") != "refseq_chromosome":
            continue
        for trait in annot.get("seq_id_traits_by_assembly", []):
            name = trait.get("assembly_name", "")
            build = next((b for b in BUILDS if name.startswith(b)), None)
            if build is None or not trait.get("is_chromosome") or trait.get("is_alt") or trait.get("is_patch"):
                continue
            if build in placements:
                raise AdapterError(f"rs{raw.get('refsnp_id')}: several {build} chromosome placements")
            spdis = [a["allele"]["spdi"] for a in placement.get("alleles", [])]
            placements[build] = DbsnpPlacement(
                seq_id=placement["seq_id"],
                build=build,
                alleles=tuple((s["position"], s["deleted_sequence"], s["inserted_sequence"]) for s in spdis),
            )
    reasons = {f"placement_{b}": "the payload has no chromosome placement for this build" for b in BUILDS if b not in placements}
    build_id = raw.get("last_update_build_id")
    return DbsnpRecord(
        rsid=f"rs{raw.get('refsnp_id')}",
        release=f"dbSNP build {build_id}" if build_id else None,
        placements=placements,
        reasons=reasons,
        provenance=provenance,
    )


_CHROMOSOME_ACCESSION = re.compile(r"NC_0000(\d\d)\.\d+")


def gnomad_variant_ids_from_dbsnp(raw: dict[str, Any]) -> list[str]:
    """gnomAD variant ids (`chrom-pos-ref-alt`, plus strand, GRCh38, 1-based) of a refsnp's variant alleles.

    Reads the placements through `parse_dbsnp`. An allele whose deleted and inserted sequences are equal is
    the reference allele and gives no id. A payload without a GRCh38 chromosome placement raises.
    """
    placement = parse_dbsnp(raw).placements.get("GRCh38")
    if placement is None:
        raise AdapterError(f"rs{raw.get('refsnp_id')}: the dbSNP payload has no GRCh38 chromosome placement")
    found = _CHROMOSOME_ACCESSION.fullmatch(placement.seq_id)
    if found is None:
        raise AdapterError(f"unexpected GRCh38 sequence accession {placement.seq_id!r}")
    number = int(found.group(1))
    chrom = {23: "X", 24: "Y"}.get(number, str(number))
    return [f"{chrom}-{pos + 1}-{deleted}-{inserted}" for pos, deleted, inserted in placement.alleles if deleted != inserted]


# =============================================================================
# Ensembl VEP
# =============================================================================
def parse_vep(
    raw: Any,
    rsid: str,
    gene: str,
    ref: str,
    alt: str,
    provenance: Optional[ImportProvenance] = None,
) -> VepRecord:
    """MANE Select transcript and AlphaMissense for gene `gene` and the locus allele `ref` > `alt`.

    The MANE Select transcript is the one whose `mane` list holds `MANE_Select` (`mane_select` is its
    RefSeq accession). Ensembl canonical is not MANE and there is no fallback: with no MANE Select row
    the transcript is None. VEP lists one row per transcript and variant allele (plus strand), so the
    row is chosen by gene symbol and by the allele, compared with `normalize_edit`. AlphaMissense is
    read from the row's `alphamissense.am_class` and `am_pathogenicity`; a row without that block gives None.
    """
    record = raw[0] if isinstance(raw, list) and raw else raw
    if not isinstance(record, dict) or record.get("id") != rsid:
        raise AdapterError(f"VEP payload is not for {rsid}")
    vep_ref = str(record.get("allele_string", "")).split("/")[0]
    want = normalize_edit(0, ref, alt)[1:]
    rows = [
        tc for tc in record.get("transcript_consequences", [])
        if "MANE_Select" in (tc.get("mane") or [])
        and tc.get("gene_symbol") == gene
        and normalize_edit(0, vep_ref, tc.get("variant_allele", ""))[1:] == want
    ]
    transcripts = {(tc.get("transcript_id"), tc.get("mane_select")) for tc in rows}
    if len(transcripts) > 1:
        raise AdapterError(f"{rsid}: several MANE Select transcripts for {gene}: {sorted(transcripts, key=str)}")
    reasons: dict[str, str] = {}
    if not rows:
        reason = f"the payload has no MANE Select transcript row for {gene} and allele {alt}"
        return VepRecord(rsid, None, None, None, None, {"mane_select": reason, "alphamissense": reason}, provenance)
    row = rows[0]
    am = row.get("alphamissense")
    am_class: Optional[str] = None
    am_score: Optional[float] = None
    if isinstance(am, dict):
        am_class = am.get("am_class")
        am_score = float(am["am_pathogenicity"]) if am.get("am_pathogenicity") is not None else None
    if am_class is None:
        reasons["alphamissense_class"] = "the payload row has no alphamissense am_class"
    if am_score is None:
        reasons["alphamissense_score"] = "the payload row has no alphamissense am_pathogenicity"
    return VepRecord(
        rsid=rsid,
        mane_select_ensembl=row.get("transcript_id"),
        mane_select_refseq=row.get("mane_select"),
        alphamissense_class=am_class,
        alphamissense_score=am_score,
        reasons=reasons,
        provenance=provenance,
    )


# =============================================================================
# gnomAD (GraphQL)
# =============================================================================
GNOMAD_REFUSAL_MULTIPLE_VARIANTS = "multiple_variants"
_GNOMAD_MULTIPLE_VARIANTS_MESSAGE = "Multiple variants found"


def parse_gnomad_variant(raw: dict[str, Any], provenance: Optional[ImportProvenance] = None) -> GnomadVariant:
    """Allele frequency as ac/an pooled over the exome and genome records that have an > 0, else None."""
    variant = (raw.get("data") or {}).get("variant")
    if not isinstance(variant, dict):
        errors = "; ".join(str(e.get("message")) for e in raw.get("errors", []) if isinstance(e, dict))
        refusal = GNOMAD_REFUSAL_MULTIPLE_VARIANTS if _GNOMAD_MULTIPLE_VARIANTS_MESSAGE in errors else None
        reason = {"af": f"gnomAD returned no variant ({errors or 'null variant'})"}
        return GnomadVariant(None, None, reason, provenance, refusal)
    ac_total = an_total = 0
    for key in ("exome", "genome"):
        record = variant.get(key)
        if isinstance(record, dict) and record.get("ac") is not None and (record.get("an") or 0) > 0:
            ac_total += record["ac"]
            an_total += record["an"]
    reasons = {}
    af = None
    if an_total > 0:
        af = ac_total / an_total
    else:
        reasons["af"] = "no exome or genome record with an > 0"
    return GnomadVariant(variant.get("variant_id"), af, reasons, provenance)


def is_multiple_variants_refusal(body: bytes | dict[str, Any]) -> bool:
    """True when a gnomAD rsid response is the "Multiple variants found" refusal (a multiallelic rsID)."""
    try:
        raw = json.loads(body) if isinstance(body, (bytes, str)) else body
    except ValueError as exc:
        raise AdapterError(f"gnomAD body is not JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise AdapterError("gnomAD body is not a JSON object")
    return parse_gnomad_variant(raw).refusal == GNOMAD_REFUSAL_MULTIPLE_VARIANTS


def parse_gnomad_constraint(raw: dict[str, Any], provenance: Optional[ImportProvenance] = None) -> GnomadConstraint:
    """pLI and LOEUF (oe_lof_upper) of a gene. Both are None when the payload has no constraint."""
    gene = (raw.get("data") or {}).get("gene")
    if not isinstance(gene, dict):
        reason = "gnomAD returned no gene"
        return GnomadConstraint(None, None, None, {"pli": reason, "loeuf": reason}, provenance)
    constraint = gene.get("gnomad_constraint")
    if not isinstance(constraint, dict):
        reason = "gnomAD has no constraint for this gene"
        return GnomadConstraint(gene.get("symbol"), None, None, {"pli": reason, "loeuf": reason}, provenance)
    pli = constraint.get("pli")
    loeuf = constraint.get("oe_lof_upper")
    reasons = {}
    if pli is None:
        reasons["pli"] = "the constraint record has no pli"
    if loeuf is None:
        reasons["loeuf"] = "the constraint record has no oe_lof_upper"
    return GnomadConstraint(
        gene.get("symbol"),
        None if pli is None else float(pli),
        None if loeuf is None else float(loeuf),
        reasons,
        provenance,
    )


# =============================================================================
# One locus at a time, from the pinned directory
# =============================================================================
class UpstreamSnapshot:
    """Reads the pinned payloads of `tools/fixtures/upstream/real/`. A source with no capture gives None."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def verify_integrity(self) -> list[str]:
        return verify_pinned_payloads(self.root)

    def _load(self, source: str, key: str) -> Optional[PinnedPayload]:
        path = self.root / source / f"{key}.json"
        return load_pinned(path) if path.is_file() else None

    def clinvar(self, rsid: str, pos_grch38: int, ref: str, alt: str) -> Optional[ClinVarRecord]:
        summary = self._load("clinvar", rsid)
        if summary is None:
            return None
        search = self._load("clinvar", f"{rsid}.esearch")
        if search is None:
            raise AdapterError(f"{rsid}: ClinVar esummary has no esearch capture to prove it is complete")
        check_clinvar_search_complete(search.data, summary.data)
        record = select_clinvar_record(summary.data, rsid, pos_grch38, ref, alt)
        if record is None:
            return None
        provenance = summary.provenance("NCBI ClinVar", None, record.accession_version)
        return replace(record, provenance=provenance)

    def dbsnp(self, rsid: str) -> Optional[DbsnpRecord]:
        payload = self._load("dbsnp", rsid)
        if payload is None:
            return None
        record = parse_dbsnp(payload.data)
        if record.rsid != rsid:
            raise AdapterError(f"{rsid}: dbSNP payload is for {record.rsid}")
        return replace(record, provenance=payload.provenance("NCBI dbSNP", record.release, rsid))

    def vep(self, rsid: str, gene: str, ref: str, alt: str) -> Optional[VepRecord]:
        payload = self._load("ensembl", rsid)
        if payload is None:
            return None
        provenance = payload.provenance("Ensembl VEP", None, rsid)
        return parse_vep(payload.data, rsid, gene, ref, alt, provenance)

    def gnomad_variant(self, rsid: str, variant_id: str) -> Optional[GnomadVariant]:
        """The capture for `variant_id`: a per-variant file where gnomAD refuses the rsid query (L6), else the rsid file.

        When the rsid file is gnomAD's "Multiple variants found" refusal and the per-variant file is absent, the
        model carries `refusal` and a reason naming the expected file.
        """
        payload = self._load("gnomad", f"{rsid}.{variant_id}")
        if payload is None:
            payload = self._load("gnomad", rsid)
            if payload is None:
                return None
            if parse_gnomad_variant(payload.data).refusal == GNOMAD_REFUSAL_MULTIPLE_VARIANTS:
                # No fall-back to the rsid file and no curated af: the caller must fail the build.
                expected = f"gnomad/{rsid}.{variant_id}.json"
                reason = f"gnomAD refused the rsid query (multiple variants) and the per-variant capture {expected} is missing"
                return GnomadVariant(None, None, {"af": reason}, None, GNOMAD_REFUSAL_MULTIPLE_VARIANTS)
        meta_query = (payload.meta.get("request_body") or "")
        dataset = re.search(r"dataset:\s*(\w+)", meta_query)
        provenance = payload.provenance("gnomAD", dataset.group(1) if dataset else None, variant_id)
        return parse_gnomad_variant(payload.data, provenance)

    def constraint(self, gene: str) -> Optional[GnomadConstraint]:
        payload = self._load("gnomad", f"constraint_{gene}")
        if payload is None:
            return None
        return parse_gnomad_constraint(payload.data, payload.provenance("gnomAD", None, gene))
