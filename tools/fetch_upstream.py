"""One-time capture of pinned upstream payloads for the 14 curated loci.

Owner-approved network use (hardening pass, ruling 5): public NCBI E-utilities
(ClinVar), NCBI Variation Services (dbSNP), Ensembl REST VEP and the gnomAD
GraphQL API, for the curated rsIDs only. Karyogram K1 adds one more approved capture: the UCSC
hg19/hg38 chromInfo and cytoBand tables (``--ucsc-only``, four GET requests). The captured bodies are committed as
fixtures under ``tools/fixtures/upstream/real/<source>/<key>.json`` and are
byte-verbatim; ``<key>.meta.json`` records how each body was obtained and its
sha256, so a tampered fixture is detectable offline.

Request construction (pure) is separate from I/O so tests never need a network.
This script names no field of any payload: reading a response is `tools/source_adapters.py`'s job
(AGENTS.md section 2). A failed request fails the run (exit 1, failed keys listed) and writes nothing: a response
is checked (status 200, a non-empty body, readable JSON for a `.json` capture, plus the source's own validator)
before its body and meta replace a pinned capture, so a failed or garbage recapture leaves the pinned files as
they were. Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:  # run as `python tools/fetch_upstream.py`, as build_canonical_kb.py does
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.source_adapters import (  # noqa: E402
    AdapterError,
    TruncatedSearch,
    decode_json_body,
    esearch_uids,
    gnomad_variant_ids_from_dbsnp,
    is_multiple_variants_refusal,
)

__all__ = ["TruncatedSearch"]  # re-exported: the completeness rule lives in the adapters

USER_AGENT = "Lucidase-KB-builder/1.0 (fixture capture)"
TIMEOUT_S = 30
MIN_INTERVAL_S = 0.5  # >= 0.4 s between NCBI requests; applied to every host
MAX_TOTAL_BYTES = 20 * 1024 * 1024  # owner-approved cap

RSIDS = (
    "rs429358",
    "rs7412",
    "rs1800562",
    "rs1799945",
    "rs6025",
    "rs1799963",
    "rs4244285",
    "rs9923231",
    "rs4149056",
    "rs3918290",
    "rs1801133",
    "rs4988235",
    "rs671",
    "rs113993960",
    "rs4986893",
    "rs12248560",
    "rs1799853",
    "rs1057910",
    "rs55886062",
    "rs67376798",
    "rs56038477",
    "rs2108622",
    "rs2231142",
    "rs1801131",
    "rs4680",
    "rs1800462",
    "rs1142345",
    "rs1800460",
    "rs116855232",
    "rs2395029",
    "rs1061235",
    "rs9263726",
)
# Gene symbols behind the loci ("MCM6 / LCT" is queried as both genes).
GENES = (
    "APOE",
    "HFE",
    "F5",
    "F2",
    "CFTR",
    "CYP2C19",
    "VKORC1",
    "SLCO1B1",
    "DPYD",
    "MTHFR",
    "MCM6",
    "LCT",
    "ALDH2",
    "CYP2C9",
    "CYP4F2",
    "ABCG2",
    "COMT",
    "TPMT",
    "NUDT15",
    "HLA-B",
    "HLA-A",
    "PSORS1C1",
)

DEFAULT_OUT = Path(__file__).resolve().parent / "fixtures" / "upstream" / "real"

GNOMAD_URL = "https://gnomad.broadinstitute.org/api"
GNOMAD_VARIANT_QUERY = (
    "query($rsid: String!) { variant(rsid: $rsid, dataset: gnomad_r4) {"
    " variant_id rsid exome { ac an } genome { ac an } } }"
)
GNOMAD_VARIANT_ID_QUERY = (
    "query($variantId: String!) { variant(variantId: $variantId, dataset: gnomad_r4) {"
    " variant_id rsid exome { ac an } genome { ac an } } }"
)
GNOMAD_CONSTRAINT_QUERY = (
    "query($symbol: String!) { gene(gene_symbol: $symbol, reference_genome: GRCh38) {"
    " symbol gnomad_constraint { pli oe_lof oe_lof_upper } } }"
)


class CapBytesExceeded(RuntimeError):
    """Raised when the running body total passes the owner-approved cap."""


class UcscCaptureFailed(RuntimeError):
    """Raised when one of the four approved UCSC requests does not return HTTP 200."""


class CaptureFailed(RuntimeError):
    """A request ended in a final non-200 status (or an empty body). Nothing was written, so a pinned capture under
    that key is unchanged; `error_payload` keeps the start of the response for the log. The run must fail."""

    def __init__(self, source: str, key: str, status: int, error_payload: str = ""):
        super().__init__(f"{source}/{key}: HTTP {status}")
        self.source, self.key, self.status, self.error_payload = source, key, status, error_payload


ESEARCH_RETMAX = 500


# ---------------------------------------------------------------------------
# Pure request builders. A request spec is {url, method, body (str|None), headers}.
# ---------------------------------------------------------------------------
def _spec(url: str, method: str = "GET", body: str | None = None, headers: dict | None = None) -> dict:
    return {"url": url, "method": method, "body": body, "headers": dict(headers or {})}


def numeric_id(rsid: str) -> str:
    if not rsid.startswith("rs") or not rsid[2:].isdigit():
        raise ValueError(f"not an rsid: {rsid!r}")
    return rsid[2:]


def dbsnp_request(rsid: str) -> dict:
    return _spec(f"https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/{numeric_id(rsid)}")


def clinvar_term(rsid: str, tagged: bool = False) -> str:
    numeric_id(rsid)
    return f"{rsid}[Variant ID]" if tagged else rsid


def clinvar_esearch_request(rsid: str, tagged: bool = False) -> dict:
    query = urllib.parse.urlencode({"db": "clinvar", "term": clinvar_term(rsid, tagged), "retmode": "json", "retmax": ESEARCH_RETMAX})
    return _spec(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{query}")


def clinvar_esummary_request(uids: list[str]) -> dict:
    if not uids:
        raise ValueError("no uids for esummary")
    query = urllib.parse.urlencode({"db": "clinvar", "id": ",".join(uids), "retmode": "json"})
    return _spec(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{query}")


def vep_request(rsid: str, alphamissense: bool = True) -> dict:
    numeric_id(rsid)
    url = (
        f"https://rest.ensembl.org/vep/human/id/{rsid}"
        "?content-type=application/json&mane=1&canonical=1&hgvs=1"
    )
    if alphamissense:
        url += "&AlphaMissense=1"
    return _spec(url)


def _graphql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}, separators=(",", ":"))
    return _spec(GNOMAD_URL, "POST", body, {"Content-Type": "application/json"})


def gnomad_variant_request(rsid: str) -> dict:
    numeric_id(rsid)
    return _graphql(GNOMAD_VARIANT_QUERY, {"rsid": rsid})


def gnomad_variant_id_request(variant_id: str) -> dict:
    """Used when an rsID is multiallelic and gnomAD refuses to pick one variant."""
    chrom, pos, ref, alt = variant_id.split("-")
    if not (pos.isdigit() and ref.isalpha() and alt.isalpha() and chrom.isalnum()):
        raise ValueError(f"not a gnomAD variant id: {variant_id!r}")
    return _graphql(GNOMAD_VARIANT_ID_QUERY, {"variantId": variant_id})


def gnomad_constraint_request(gene: str) -> dict:
    if not gene or not gene.replace("-", "").isalnum():
        raise ValueError(f"not a gene symbol: {gene!r}")
    return _graphql(GNOMAD_CONSTRAINT_QUERY, {"symbol": gene})


# UCSC Genome Browser assembly geometry (karyogram K1): the four owner-approved gzip tables, GET only.
UCSC_BASE = "https://hgdownload.soe.ucsc.edu/goldenPath"
UCSC_ASSEMBLIES = ("hg19", "hg38")  # GRCh37, GRCh38
UCSC_TABLES = ("chromInfo", "cytoBand")


def ucsc_requests() -> list[tuple[str, dict]]:
    """(key, request spec) for exactly the four approved UCSC tables. Keys double as the body file names."""
    return [
        (
            f"{assembly}.{table}.txt.gz",
            _spec(f"{UCSC_BASE}/{assembly}/database/{table}.txt.gz", headers={"Accept": "*/*"}),
        )
        for assembly in UCSC_ASSEMBLIES
        for table in UCSC_TABLES
    ]


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def perform(spec: dict, opener=None, timeout: float = TIMEOUT_S) -> tuple[int, bytes]:
    """Execute one request. Returns (http_status, body_bytes); status 0 = transport failure.

    `opener` defaults to `urllib.request.urlopen`, looked up at call time (so a test guard can replace it).
    It is called with the timeout only: urllib's default certificate verification stays on.
    """
    opener = opener or urllib.request.urlopen
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **spec["headers"]}
    data = spec["body"].encode("utf-8") if spec["body"] is not None else None
    req = urllib.request.Request(spec["url"], data=data, headers=headers, method=spec["method"])
    try:
        with opener(req, timeout=timeout) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, str(exc).encode("utf-8")


def perform_with_retry(spec, opener=None, sleep=time.sleep, log=print):
    """At most one logged retry, only for transport failure, 429 or 5xx."""
    status, body = perform(spec, opener)
    if status == 0 or status == 429 or status >= 500:
        log(f"retrying once after status {status}: {spec['url']}")
        sleep(2.0)
        status, body = perform(spec, opener)
    return status, body


def _replace_atomically(path: Path, data: bytes) -> None:
    """Write `data` to a temp file in the same directory, then rename it over `path` (atomic on one filesystem),
    so an interrupted write never leaves a half-written capture in place of a good one."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_capture(
    out_dir: Path, source: str, key: str, spec: dict, status: int, body: bytes, now=None, body_ext: str = ".json"
) -> dict:
    """Write verbatim body (if the request succeeded with a non-empty body) and its meta, each atomically.

    The body file is ``<key><body_ext>``; the meta is always ``<key>.meta.json``. A failure writes a meta with no
    body; `Capturer.run` never calls this for a failure, only `_capture_locus` does, for the VEP 400 evidence under
    its own key.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    ok = 200 <= status < 300 and len(body) > 0
    meta = {
        "url": spec["url"],
        "method": spec["method"],
        "request_body": spec["body"],
        "retrieved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "http_status": status,
        "sha256_of_body": hashlib.sha256(body).hexdigest() if ok else None,
        "bytes": len(body) if ok else 0,
    }
    if not ok:  # no body file; keep the error payload so the failure is explained
        meta["error_payload"] = body[:2000].decode("utf-8", "replace")
    target = Path(out_dir) / source
    target.mkdir(parents=True, exist_ok=True)
    if ok:
        _replace_atomically(target / f"{key}{body_ext}", body)
    _replace_atomically(target / f"{key}.meta.json", (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return meta


class Capturer:
    def __init__(self, out_dir: Path, opener=None, sleep=time.sleep, log=print):
        self.out_dir, self.opener, self.sleep, self.log = Path(out_dir), opener, sleep, log
        self.total = 0
        self.rows: list[dict] = []
        self.failures: list[CaptureFailed] = []

    def run(
        self,
        source: str,
        key: str,
        spec: dict,
        allow_status: tuple[int, ...] = (),
        body_ext: str = ".json",
        validate: Callable[[bytes], None] | None = None,
    ) -> tuple[int, bytes, dict | None]:
        """One request; only a good response is written to disk. Returns (status, body, the written meta).

        Every check runs BEFORE anything is written, so a failed or garbage response can neither overwrite a pinned
        body nor its meta:
        - a status other than 200, or an empty body, writes nothing and raises `CaptureFailed`, unless the status is
          in `allow_status` (the caller handles that status itself: only VEP's 400 for the AlphaMissense flag); then
          it writes nothing and returns meta None;
        - a `.json` capture must be readable JSON (`decode_json_body`, the rule `load_pinned` applies);
        - `validate`, the source's own check, runs last.
        Whatever a check raises propagates."""
        self.sleep(MIN_INTERVAL_S)
        status, body = perform_with_retry(spec, self.opener, self.sleep, self.log)
        if status != 200 or not body:
            self.rows.append({"source": source, "key": key, "status": status, "bytes": 0})
            payload = body[:2000].decode("utf-8", "replace")
            self.log(f"{source}/{key}: HTTP {status}, nothing written; response: {payload[:200]!r}")
            if status in allow_status:
                return status, body, None
            raise CaptureFailed(source, key, status, payload)
        if body_ext == ".json":
            decode_json_body(body, f"{source}/{key} ({spec['url']})")
        if validate is not None:
            validate(body)
        meta = write_capture(self.out_dir, source, key, spec, status, body, body_ext=body_ext)
        self.total += meta["bytes"]
        self.rows.append({"source": source, "key": key, "status": status, "bytes": meta["bytes"]})
        self.log(f"{source}/{key}: HTTP {status}, {meta['bytes']} bytes")
        if self.total > MAX_TOTAL_BYTES:
            raise CapBytesExceeded(f"captured {self.total} bytes, over the {MAX_TOTAL_BYTES} byte cap")
        return status, body, meta

    def attempt(self, unit, *args, **kwargs) -> None:
        """Run one unit of work (one rsID, one gene). A `CaptureFailed` is recorded and the run goes on, so one
        outage lists every failed key instead of hiding the second behind the first. Nothing else is caught."""
        try:
            unit(self, *args, **kwargs)
        except CaptureFailed as exc:
            self.failures.append(exc)
            self.log(f"FAILED {exc}")


def capture_clinvar(cap: Capturer, rsid: str) -> None:
    """An esearch is validated by `esearch_uids` (readable, not truncated) before it is written."""
    _, body, _ = cap.run("clinvar", f"{rsid}.esearch", clinvar_esearch_request(rsid), validate=esearch_uids)
    uids = esearch_uids(body)
    if not uids:
        cap.log(f"{rsid}: plain term returned 0 uids; trying tagged term")
        _, body, _ = cap.run(
            "clinvar", f"{rsid}.esearch_tagged", clinvar_esearch_request(rsid, True), validate=esearch_uids
        )
        uids = esearch_uids(body)
    if uids:
        cap.run("clinvar", rsid, clinvar_esummary_request(uids))


def capture_gnomad_multiallelic(cap: Capturer, rsids=RSIDS) -> None:
    """For rsIDs whose gnomAD rsid query errored as multiallelic, query each alt by variant id."""
    for rsid in rsids:
        path = cap.out_dir / "gnomad" / f"{rsid}.json"
        if not path.exists() or not is_multiple_variants_refusal(path.read_bytes()):
            continue
        dbsnp = json.loads((cap.out_dir / "dbsnp" / f"{rsid}.json").read_bytes())
        for vid in gnomad_variant_ids_from_dbsnp(dbsnp):
            if (cap.out_dir / "gnomad" / f"{rsid}.{vid}.meta.json").exists():
                continue  # already captured; do not re-query
            cap.attempt(_capture_gnomad_variant_id, rsid, vid)


def _capture_gnomad_variant_id(cap: Capturer, rsid: str, vid: str) -> None:
    cap.run("gnomad", f"{rsid}.{vid}", gnomad_variant_id_request(vid))


def _capture_locus(cap: Capturer, rsid: str) -> None:
    cap.run("dbsnp", rsid, dbsnp_request(rsid))

    capture_clinvar(cap, rsid)

    # The one status handled in place: VEP answers 400 when the AlphaMissense flag is not supported. The 400 is kept
    # as evidence under its own key (a meta with no body), never over the pinned `<rsid>.meta.json`, and the request
    # is repeated once without the flag; that repeat must be 200.
    spec = vep_request(rsid)
    status, body, _ = cap.run("ensembl", rsid, spec, allow_status=(400, 500))
    if status in (400, 500):
        cap.log(f"{rsid}: VEP rejected request (status {status}); error payload kept in meta, retrying without AlphaMissense")
        write_capture(cap.out_dir, "ensembl", f"{rsid}.alphamissense_rejected", spec, status, body)
        cap.run("ensembl", rsid, vep_request(rsid, alphamissense=False))

    cap.run("gnomad", rsid, gnomad_variant_request(rsid))


def _capture_constraint(cap: Capturer, gene: str) -> None:
    cap.run("gnomad", f"constraint_{gene}", gnomad_constraint_request(gene))


def capture_all(cap: Capturer, rsids=RSIDS, genes=GENES) -> None:
    """Every request. A failed request ends its rsID (or gene) and the run goes on; `cap.failures` lists them."""
    for rsid in rsids:
        cap.attempt(_capture_locus, rsid)
    for gene in genes:
        cap.attempt(_capture_constraint, gene)
    capture_gnomad_multiallelic(cap, rsids)


GZIP_MAGIC = bytes([0x1F, 0x8B])


def capture_ucsc(cap: Capturer) -> None:
    """Capture the four UCSC tables, byte-verbatim (gzip), under ``ucsc/<key>``."""
    for key, spec in ucsc_requests():
        def require_gzip(body: bytes, url: str = spec["url"]) -> None:
            if body[:2] != GZIP_MAGIC:
                raise UcscCaptureFailed(f"{url}: response body is not gzip (it does not start with the 1f 8b magic)")

        try:
            cap.run("ucsc", key, spec, body_ext="", validate=require_gzip)
        except CaptureFailed as exc:
            reason = "empty response body" if exc.status == 200 else f"HTTP {exc.status}"
            raise UcscCaptureFailed(f"{spec['url']}: {reason}") from exc


def main(argv=None, opener=None, sleep=time.sleep) -> int:
    """Exit 0 when every request succeeded, 1 when any failed (failed keys listed on stderr), 2 on a cap or
    payload error (an unreadable response is systematic, so the run stops at once)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--gnomad-multiallelic-only",
        action="store_true",
        help="only query gnomAD by variant id for multiallelic rsIDs, reusing captured dbSNP/gnomAD files",
    )
    modes.add_argument(
        "--clinvar-only",
        nargs="+",
        metavar="RSID",
        help="re-capture only ClinVar esearch+esummary for these rsIDs (must be curated rsIDs)",
    )
    modes.add_argument(
        "--locus-only",
        nargs="+",
        metavar="RSID",
        help="capture upstream payloads (dbSNP, ClinVar, VEP, gnomAD) for these rsIDs (must be approved rsIDs)",
    )
    modes.add_argument(
        "--gene-only",
        nargs="+",
        metavar="GENE",
        help="capture gnomAD constraint for these genes",
    )
    modes.add_argument(
        "--ucsc-only",
        action="store_true",
        help="capture only the four UCSC hg19/hg38 chromInfo and cytoBand tables",
    )
    args = parser.parse_args(argv)
    cap = Capturer(args.out, opener=opener, sleep=sleep)
    try:
        if args.ucsc_only:
            capture_ucsc(cap)
        elif args.clinvar_only:
            for rsid in args.clinvar_only:
                if rsid not in RSIDS:
                    raise SystemExit(f"{rsid} is not one of the approved rsIDs")
                cap.attempt(capture_clinvar, rsid)
        elif args.locus_only:
            for rsid in args.locus_only:
                if rsid not in RSIDS:
                    raise SystemExit(f"{rsid} is not one of the approved rsIDs")
                cap.attempt(_capture_locus, rsid)
            capture_gnomad_multiallelic(cap, args.locus_only)
        elif args.gene_only:
            for gene in args.gene_only:
                if gene not in GENES:
                    raise SystemExit(f"{gene} is not one of the approved genes")
                cap.attempt(_capture_constraint, gene)
        elif args.gnomad_multiallelic_only:
            capture_gnomad_multiallelic(cap)
        else:
            capture_all(cap)
    except (CapBytesExceeded, AdapterError, UcscCaptureFailed) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if cap.failures:
        print(f"FAILED {len(cap.failures)} request(s) of {len(cap.rows)}:", file=sys.stderr)
        for failure in cap.failures:
            print(f"  {failure.source}/{failure.key}: HTTP {failure.status}", file=sys.stderr)
        return 1
    print(f"done: {len(cap.rows)} requests, {cap.total} body bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
