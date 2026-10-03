"""One-time capture of pinned upstream payloads for the 14 curated loci.

Owner-approved network use (hardening pass, ruling 5): public NCBI E-utilities
(ClinVar), NCBI Variation Services (dbSNP), Ensembl REST VEP and the gnomAD
GraphQL API, for the curated rsIDs only. Karyogram K1 adds one more approved capture: the UCSC
hg19/hg38 chromInfo and cytoBand tables (``--ucsc-only``, four GET requests). The captured bodies are committed as
fixtures under ``tools/fixtures/upstream/real/<source>/<key>.json`` and are
byte-verbatim; ``<key>.meta.json`` records how each body was obtained and its
sha256, so a tampered fixture is detectable offline.

Request construction (pure) is separate from I/O so tests never need a network.
Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

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
)
# Gene symbols behind the 14 loci ("MCM6 / LCT" is queried as both genes).
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


class TruncatedSearch(RuntimeError):
    """Raised when an esearch reports more hits (count) than it returned (idlist)."""


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
def perform(spec: dict, opener=urllib.request.urlopen, timeout: float = TIMEOUT_S) -> tuple[int, bytes]:
    """Execute one request. Returns (http_status, body_bytes); status 0 = transport failure."""
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


def perform_with_retry(spec, opener=urllib.request.urlopen, sleep=time.sleep, log=print):
    """At most one logged retry, only for transport failure, 429 or 5xx."""
    status, body = perform(spec, opener)
    if status == 0 or status == 429 or status >= 500:
        log(f"retrying once after status {status}: {spec['url']}")
        sleep(2.0)
        status, body = perform(spec, opener)
    return status, body


def write_capture(
    out_dir: Path, source: str, key: str, spec: dict, status: int, body: bytes, now=None, body_ext: str = ".json"
) -> dict:
    """Write verbatim body (if the request succeeded with a non-empty body) and its meta.

    The body file is ``<key><body_ext>``; the meta is always ``<key>.meta.json``.
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
        (target / f"{key}{body_ext}").write_bytes(body)
    (target / f"{key}.meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return meta


class Capturer:
    def __init__(self, out_dir: Path, opener=urllib.request.urlopen, sleep=time.sleep, log=print):
        self.out_dir, self.opener, self.sleep, self.log = Path(out_dir), opener, sleep, log
        self.total = 0
        self.rows: list[dict] = []

    def run(self, source: str, key: str, spec: dict, body_ext: str = ".json") -> tuple[int, bytes, dict]:
        self.sleep(MIN_INTERVAL_S)
        status, body = perform_with_retry(spec, self.opener, self.sleep, self.log)
        meta = write_capture(self.out_dir, source, key, spec, status, body, body_ext=body_ext)
        self.total += meta["bytes"]
        self.rows.append({"source": source, "key": key, "status": status, "bytes": meta["bytes"]})
        self.log(f"{source}/{key}: HTTP {status}, {meta['bytes']} bytes")
        if self.total > MAX_TOTAL_BYTES:
            raise CapBytesExceeded(f"captured {self.total} bytes, over the {MAX_TOTAL_BYTES} byte cap")
        return status, body, meta


def _uids(body: bytes) -> list[str]:
    """Uids from an esearch body; fails closed if the result list is truncated."""
    try:
        result = json.loads(body)["esearchresult"]
        uids = list(result["idlist"])
        count = int(result["count"])
    except (ValueError, KeyError, TypeError):
        return []
    if count != len(uids):
        raise TruncatedSearch(f"esearch count {count} != {len(uids)} uids returned; raise retmax")
    return uids


def capture_clinvar(cap: Capturer, rsid: str) -> None:
    status, body, _ = cap.run("clinvar", f"{rsid}.esearch", clinvar_esearch_request(rsid))
    uids = _uids(body) if status == 200 else []
    if not uids:
        cap.log(f"{rsid}: plain term returned 0 uids; trying tagged term")
        status, body, _ = cap.run("clinvar", f"{rsid}.esearch_tagged", clinvar_esearch_request(rsid, True))
        uids = _uids(body) if status == 200 else []
    if uids:
        cap.run("clinvar", rsid, clinvar_esummary_request(uids))


def grch38_variant_ids(dbsnp_body: bytes) -> list[str]:
    """gnomAD variant ids (chrom-pos-ref-alt, plus strand, GRCh38) from a dbSNP payload."""
    snap = json.loads(dbsnp_body)["primary_snapshot_data"]
    for placement in snap["placements_with_allele"]:
        seq = placement["seq_id"]
        if placement.get("is_ptlp") and seq.startswith("NC_0000"):
            chrom = {"23": "X", "24": "Y"}.get(str(int(seq[3:9])), str(int(seq[3:9])))
            ids = []
            for allele in placement["alleles"]:
                spdi = allele["allele"]["spdi"]
                if spdi["deleted_sequence"] != spdi["inserted_sequence"]:
                    ids.append(f"{chrom}-{spdi['position'] + 1}-{spdi['deleted_sequence']}-{spdi['inserted_sequence']}")
            return ids
    return []


def capture_gnomad_multiallelic(cap: Capturer, rsids=RSIDS) -> None:
    """For rsIDs whose gnomAD rsid query errored as multiallelic, query each alt by variant id."""
    for rsid in rsids:
        path = cap.out_dir / "gnomad" / f"{rsid}.json"
        if not path.exists() or b"Multiple variants found" not in path.read_bytes():
            continue
        dbsnp = (cap.out_dir / "dbsnp" / f"{rsid}.json").read_bytes()
        for vid in grch38_variant_ids(dbsnp):
            if (cap.out_dir / "gnomad" / f"{rsid}.{vid}.meta.json").exists():
                continue  # already captured; do not re-query
            cap.run("gnomad", f"{rsid}.{vid}", gnomad_variant_id_request(vid))


def capture_all(cap: Capturer, rsids=RSIDS, genes=GENES) -> None:
    for rsid in rsids:
        cap.run("dbsnp", rsid, dbsnp_request(rsid))

        capture_clinvar(cap, rsid)

        status, _, _ = cap.run("ensembl", rsid, vep_request(rsid))
        if status == 400:
            cap.log(f"{rsid}: VEP rejected request; error payload kept in meta, retrying without AlphaMissense")
            rejected = cap.out_dir / "ensembl"
            (rejected / f"{rsid}.meta.json").replace(rejected / f"{rsid}.alphamissense_rejected.meta.json")
            cap.run("ensembl", rsid, vep_request(rsid, alphamissense=False))

        cap.run("gnomad", rsid, gnomad_variant_request(rsid))
    for gene in genes:
        cap.run("gnomad", f"constraint_{gene}", gnomad_constraint_request(gene))
    capture_gnomad_multiallelic(cap, rsids)


def capture_ucsc(cap: Capturer) -> None:
    """Capture the four UCSC tables, byte-verbatim (gzip), under ``ucsc/<key>``."""
    for key, spec in ucsc_requests():
        status, _, _ = cap.run("ucsc", key, spec, body_ext="")
        if status != 200:
            raise UcscCaptureFailed(f"{spec['url']}: HTTP {status}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--gnomad-multiallelic-only",
        action="store_true",
        help="only query gnomAD by variant id for multiallelic rsIDs, reusing captured dbSNP/gnomAD files",
    )
    parser.add_argument(
        "--clinvar-only",
        nargs="+",
        metavar="RSID",
        help="re-capture only ClinVar esearch+esummary for these rsIDs (must be curated rsIDs)",
    )
    parser.add_argument(
        "--ucsc-only",
        action="store_true",
        help="capture only the four UCSC hg19/hg38 chromInfo and cytoBand tables",
    )
    args = parser.parse_args(argv)
    cap = Capturer(args.out)
    try:
        if args.ucsc_only:
            capture_ucsc(cap)
        elif args.clinvar_only:
            for rsid in args.clinvar_only:
                if rsid not in RSIDS:
                    raise SystemExit(f"{rsid} is not one of the approved rsIDs")
                capture_clinvar(cap, rsid)
        elif args.gnomad_multiallelic_only:
            capture_gnomad_multiallelic(cap)
        else:
            capture_all(cap)
    except (CapBytesExceeded, TruncatedSearch, UcscCaptureFailed) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"done: {len(cap.rows)} requests, {cap.total} body bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
