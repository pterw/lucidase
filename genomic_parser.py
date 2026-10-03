"""
Genomic Parser: DTC Raw Data Ingestion & Quality Control Engine
==============================================================
Pure parser for direct-to-consumer (DTC) genotyping and VCF files, implementing
contract C1 (see web/src/core/parse.js, which it mirrors, and tests/vectors/parse.json,
which both implementations must pass):

- 23andMe, AncestryDNA, MyHeritage / FamilyTreeDNA (CSV), and VCF
- `parse_genotype_file(text, file_name)` returns a `ParseResult`; unrecognised input
  raises `UnsupportedFormatError` (never guesses)
- build is read from the header only: "GRCh37", "GRCh38" or "unknown" (never assumed)
- VCF alleles stay full sequences, haploid stays haploid, phase is dropped, and one
  Call is produced per VCF ID (ID "." gives rsid None)
- `compute_qc(result)` mirrors web/src/core/qc.js, including the sex-signal wording
  and thresholds. The signal describes X heterozygosity only, never a karyotype.

The parser knows nothing about the knowledge base. `read_genotype_text(path)` reads a
file (plain or gzip) for `parse_genotype_file`.
"""

from __future__ import annotations

import gzip
import os
import re
from dataclasses import dataclass, field


class UnsupportedFormatError(ValueError):
    """The input is not a recognised 23andMe / AncestryDNA / MyHeritage / VCF file."""


@dataclass
class Call:
    """One genotype call. `alleles` is None for a no-call; length 1 means haploid."""

    rsid: str | None
    chrom: str
    pos: int | None
    alleles: list[str] | None


@dataclass
class ParseStats:
    total_lines: int = 0
    data_rows: int = 0
    called: int = 0
    no_calls: int = 0
    skipped_malformed: int = 0
    filtered: int = 0  # VCF calls whose FILTER is not PASS or '.'; they are also in no_calls


@dataclass
class ParseResult:
    format: str
    build: str
    assay: str
    calls: list[Call] = field(default_factory=list)
    stats: ParseStats = field(default_factory=ParseStats)


# ---------------------------------------------------------------------------
# Pure parser (contract C1)
# ---------------------------------------------------------------------------

HEADER_SCAN_LINES = 200
_CHROM_ALIASES = {"23": "X", "24": "Y", "25": "XY", "26": "MT", "M": "MT"}
_ARRAY_CODES = re.compile(r"[ACGTDI]{1,2}")
_ARRAY_NOCALLS = {"--", "-", "0", "00", "??", "NN", "."}
_DIGITS = re.compile(r"[0-9]+")
_MALFORMED = object()  # sentinel: a field that cannot be parsed (None means no-call)

# JavaScript `String.prototype.trim` / `\s` whitespace. Python's `str.strip()` differs
# (it strips U+001C-U+001F and U+0085, and keeps U+FEFF), so it is never used here.
_JS_WS = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007""\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_WS_RUN = re.compile("[" + _JS_WS + "]+")


def _trim(value: str) -> str:
    return value.strip(_JS_WS)


def _normalize_chrom(raw: str) -> str:
    c = re.sub(r"^chr", "", _trim(str(raw)), flags=re.IGNORECASE).upper()
    return _CHROM_ALIASES.get(c, c)


def _parse_pos(raw: str) -> int | None:
    s = _trim(str(raw))
    return int(s) if _DIGITS.fullmatch(s) else None


def _is_column_header(first_field: str) -> bool:
    return _trim(first_field.replace('"', "")).lower() == "rsid"


def _detect_format(lines: list[str], file_name: str) -> str | None:
    head = [s for s in (_trim(l) for l in lines[:HEADER_SCAN_LINES]) if s]
    lower = [l.lower() for l in head]

    if any(
        l.startswith("##fileformat=vcf") or l.startswith("#chrom\t") or l.startswith("#chrom ")
        for l in lower
    ):
        return "vcf"

    candidates: list[str] = []
    comments = [l for l in lower if l.startswith("#")]
    if any("ancestrydna" in l for l in comments):
        candidates.append("ancestry")
    if any("myheritage" in l for l in comments):
        candidates.append("myheritage")
    if any("23andme" in l for l in comments):
        candidates.append("23andme")

    first_data = next((l for l in head if not l.startswith("#")), None)
    if first_data is not None:
        tabs = first_data.split("\t")
        if _is_column_header(tabs[0]) and len(tabs) >= 5:
            candidates.append("ancestry")
        elif _is_exact_23andme_header(tabs):
            candidates.append("23andme")
        elif _is_myheritage_header(_split_csv(first_data)):
            candidates.append("myheritage")
        elif not candidates:
            # No header signal at all: accept only a well-formed first data row.
            if len(tabs) >= 5 and _parse_pos(tabs[2]) is not None:
                candidates.append("ancestry")
            elif len(tabs) == 4 and _parse_pos(tabs[2]) is not None:
                candidates.append("23andme")
            elif _is_myheritage_row(_split_csv(first_data)):
                candidates.append("myheritage")
    elif candidates and all(l.startswith("#") for l in head):
        return candidates[0]  # comments only, no rows: nothing to parse

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    name = str(file_name or "").lower()
    return next((c for c in candidates if c in name), candidates[0])


def _is_exact_23andme_header(cols: list[str]) -> bool:
    """The exact tab-separated column header rsid chromosome position genotype."""
    return len(cols) == 4 and "\t".join(_trim(c).lower() for c in cols) == "rsid\tchromosome\tposition\tgenotype"


def _is_myheritage_header(cols: list[str]) -> bool:
    """The exact MyHeritage header RSID,CHROMOSOME,POSITION,RESULT (any case, quotes allowed)."""
    return len(cols) == 4 and ",".join(c.lower() for c in cols) == "rsid,chromosome,position,result"


def _is_myheritage_row(cols: list[str]) -> bool:
    """A headerless MyHeritage row: rs<digits>, a chromosome, a digits position, a valid genotype."""
    return (
        len(cols) >= 4
        and re.fullmatch(r"rs[0-9]+", cols[0], flags=re.IGNORECASE) is not None
        and cols[1] != ""
        and _DIGITS.fullmatch(cols[2]) is not None
        and _array_alleles(cols[3]) is not _MALFORMED
    )


_BUILD_PATTERNS = [
    # GRCh38: GRCh38[.pN], hg38, hs38[DH], GATK "assembly38", accession GCA_000001405.15.
    (
        "GRCh38",
        re.compile(
            r"(?:^|[^a-z0-9])(?:grch38|hg38|hs38(?:dh)?|assembly38|build 38|gca_000001405\.15)(?:[^a-z0-9]|$)"
        ),
    ),
    # GRCh37: GRCh37[.pN], hg19, b37, hs37d5, human_g1k_v37.
    (
        "GRCh37",
        re.compile(r"(?:^|[^a-z0-9])(?:grch37|hg19|b37|hs37d5|build 37)(?:[^a-z0-9]|$)|g1k_v37"),
    ),
]


def _match_build(lower_line: str) -> str | None:
    for build, pattern in _BUILD_PATTERNS:
        if pattern.search(lower_line):
            return build
    return None


def _detect_array_build(lines: list[str]) -> str:
    """Array build comes from header comments only."""
    for line in lines[:HEADER_SCAN_LINES]:
        if line.startswith("#"):
            b = _match_build(line.lower())
            if b:
                return b
    return "unknown"


def _detect_vcf_build(lines: list[str]) -> str:
    """VCF build comes from ##reference, ##contig and ##assembly tokens."""
    for line in lines:
        if not line.startswith("##"):
            if line.startswith("#CHROM") or line.startswith("#chrom"):
                break
            continue
        l = line.lower()
        if not (l.startswith("##reference") or l.startswith("##contig") or l.startswith("##assembly")):
            continue
        b = _match_build(l)
        if b:
            return b
    return "unknown"


def _array_alleles(code: str):
    """Alleles for "AG", "A", "DI", "--"...; None = no-call, _MALFORMED = bad code."""
    g = _trim(code).upper()
    if g in _ARRAY_NOCALLS:
        return None
    return list(g) if _ARRAY_CODES.fullmatch(g) else _MALFORMED


def _array_call(rsid: str, chrom: str, pos_raw: str, alleles):
    pos = _parse_pos(pos_raw)
    if not rsid or not chrom or pos is None or alleles is _MALFORMED:
        return None
    return [Call(rsid, _normalize_chrom(chrom), pos, alleles)]


def _parse_23andme_line(line: str):
    cols = line.split("\t")
    if len(cols) < 4:
        cols = _WS_RUN.split(_trim(line))
    if len(cols) < 4:
        return None
    return _array_call(_trim(cols[0]), cols[1], cols[2], _array_alleles(cols[3]))


def _parse_ancestry_line(line: str):
    cols = line.split("\t")
    if len(cols) < 5:
        return None
    a, b = _array_alleles(cols[3]), _array_alleles(cols[4])
    # One single-letter allele per column; a missing allele makes the call a no-call.
    if a is _MALFORMED or b is _MALFORMED or (a and len(a) != 1) or (b and len(b) != 1):
        return None
    return _array_call(
        _trim(cols[0]), cols[1], cols[2], None if a is None or b is None else [a[0], b[0]]
    )


def _split_csv(line: str) -> list[str]:
    """Split one CSV line, honouring double quotes (MyHeritage only)."""
    out, cur, quoted = [], "", False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [_trim(s) for s in out]


def _parse_myheritage_line(line: str):
    cols = _split_csv(line)
    if len(cols) < 4:
        return None
    return _array_call(cols[0], cols[1], cols[2], _array_alleles(cols[3]))


# A VCF allele we carry: A/C/G/T sequences (SNPs and indels) or the single codes I/D. Symbolic
# `<DEL>`, `=1+1` and markup are untrusted file content and are never kept.
_VCF_ALLELE = re.compile(r"(?:[ACGT]+|[ID])", re.IGNORECASE | re.ASCII)


def _vcf_alleles(gt: str, table: list[str]):
    """GT string and allele table to alleles: None = no-call, _MALFORMED = bad GT."""
    out: list[str] = []
    # REF is checked for every row; an ALT only when the GT selects it.
    missing = table[0] != "*" and not _VCF_ALLELE.fullmatch(table[0])
    for t in re.split(r"[/|]", gt):
        if t == ".":
            missing = True
            continue
        if not _DIGITS.fullmatch(t):
            return _MALFORMED
        idx = int(t)
        if idx >= len(table):
            return _MALFORMED
        # "*" is a spanning deletion, not a base: the position has no usable call.
        if table[idx] == "*":
            missing = True
            continue
        if not _VCF_ALLELE.fullmatch(table[idx]):
            missing = True
            continue
        out.append(table[idx].upper())
    return None if missing else out


def _failed_filter(filter_field: str) -> bool:
    """A VCF record is usable only when FILTER is PASS or '.'."""
    return _trim(filter_field) not in ("PASS", ".")


def _parse_vcf_line(line: str, stats: ParseStats):
    sample_idx, format_idx = 9, 8  # FORMAT is column 8, the FIRST sample is column 9
    cols = line.split("\t")
    if len(cols) <= sample_idx or len(cols) < 5:
        return None
    pos = _parse_pos(cols[1])
    if pos is None or not _trim(cols[0]):
        return None

    keys = cols[format_idx].split(":")
    if "GT" not in keys:
        return None
    gt_idx = keys.index("GT")
    parts = cols[sample_idx].split(":")
    gt = parts[gt_idx] if gt_idx < len(parts) else None
    if gt is None or gt == "":
        return None

    alt = _trim(cols[4])
    table = [_trim(cols[3])] + ([] if alt in (".", "") else alt.split(","))
    table = [_trim(a) for a in table]
    if not table[0]:
        return None
    alleles = _vcf_alleles(_trim(gt), table)
    if alleles is _MALFORMED:
        return None
    filtered = _failed_filter(cols[6])
    if filtered:
        alleles = None

    if _trim(cols[2]) in (".", ""):
        ids: list[str | None] = [None]
    else:
        ids = [s for s in (_trim(p) for p in cols[2].split(";")) if s and s != "."]
        if not ids:
            ids = [None]
    chrom = _normalize_chrom(cols[0])
    if filtered:
        stats.filtered += len(ids)
    return [Call(rsid, chrom, pos, None if alleles is None else list(alleles)) for rsid in ids]


def _has_sample_column(lines: list[str]) -> bool:
    """True when the #CHROM line (or, lacking one, the first data row) has a sample column."""
    for line in lines:
        if line.startswith("#CHROM") or line.startswith("#chrom"):
            return len(line.split("\t")) >= 10
        if not line.startswith("#") and _trim(line):
            return len(line.split("\t")) >= 10
    return False


_LINE_PARSERS = {
    "23andme": _parse_23andme_line,
    "ancestry": _parse_ancestry_line,
    "myheritage": _parse_myheritage_line,
}


def parse_genotype_file(text: str, file_name: str = "") -> ParseResult:
    """Parse a raw genotype file.

    Raises UnsupportedFormatError when the content is not a recognised format (never
    guesses) and TypeError when `text` is not a str.
    """
    if not isinstance(text, str):
        raise TypeError("parse_genotype_file: text must be a str")
    text = text.lstrip("\ufeff")
    lines = re.split(r"\r?\n", text)
    if lines and lines[-1] == "":
        lines.pop()

    fmt = _detect_format(lines, file_name)
    if fmt is None:
        raise UnsupportedFormatError(
            "Unsupported file format: expected a 23andMe, AncestryDNA or MyHeritage "
            "raw-data file, or a VCF."
        )

    assay = "vcf" if fmt == "vcf" else "array"
    build = _detect_vcf_build(lines) if fmt == "vcf" else _detect_array_build(lines)
    if fmt == "vcf" and not _has_sample_column(lines):
        raise UnsupportedFormatError(
            "Unsupported file: VCF contains no sample genotypes (no FORMAT or sample column)."
        )
    result = ParseResult(fmt, build, assay, [], ParseStats(total_lines=len(lines)))
    if fmt == "vcf":
        parse_line = lambda l: _parse_vcf_line(l, result.stats)  # noqa: E731
    else:
        parse_line = _LINE_PARSERS[fmt]

    for line in lines:
        if not _trim(line) or line.startswith("#"):
            continue
        if fmt != "vcf" and _is_column_header(re.split(r"[\t,]", line)[0]):
            continue
        result.stats.data_rows += 1
        parsed = parse_line(line)
        if parsed is None:
            result.stats.skipped_malformed += 1
            continue
        for call in parsed:
            result.calls.append(call)
            if call.alleles is None:
                result.stats.no_calls += 1
            else:
                result.stats.called += 1
    return result


# ---------------------------------------------------------------------------
# QC (mirrors web/src/core/qc.js)
# ---------------------------------------------------------------------------

MIN_X_MARKERS = 10
X_HET_CUTOFF = 0.05  # strictly greater means "two X"

VCF_RATE_NOTE = "not meaningful for variants-only VCF"

SEX_SIGNAL_TWO_X = "X heterozygosity consistent with two X chromosomes"
SEX_SIGNAL_ONE_X = "X heterozygosity consistent with one X chromosome"
SEX_SIGNAL_INDETERMINATE = "Indeterminate (too few X markers)"


def _is_het(alleles: list[str]) -> bool:
    return len(alleles) == 2 and alleles[0] != alleles[1]


def compute_qc(result: ParseResult) -> dict:
    """call_rate and heterozygosity_rate (both None for a VCF, with qc_note), x_markers,
    x_het_rate, y_calls, sex_signal."""
    called = no_calls = diploid = het = x_markers = x_het = y_calls = 0
    for call in result.calls:
        if call.alleles is None:
            no_calls += 1
            continue
        called += 1
        if len(call.alleles) == 2:
            diploid += 1
            if _is_het(call.alleles):
                het += 1
        if call.chrom == "X":
            x_markers += 1
            if _is_het(call.alleles):
                x_het += 1
        elif call.chrom == "Y":
            y_calls += 1

    total = called + no_calls
    # A VCF lists variant sites, so rates over it are ~100% called / mostly het by construction.
    variants_only = result.assay == "vcf"
    x_het_rate = x_het / x_markers if x_markers > 0 else 0
    sex_signal = SEX_SIGNAL_INDETERMINATE
    if x_markers >= MIN_X_MARKERS:
        sex_signal = SEX_SIGNAL_TWO_X if x_het_rate > X_HET_CUTOFF else SEX_SIGNAL_ONE_X
    return {
        "call_rate": None if variants_only else (called / total if total > 0 else 0),
        "heterozygosity_rate": None if variants_only else (het / diploid if diploid > 0 else 0),
        "qc_note": VCF_RATE_NOTE if variants_only else None,
        "x_markers": x_markers,
        "x_het_rate": x_het_rate,
        "y_calls": y_calls,
        "sex_signal": sex_signal,
    }


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------


def read_genotype_text(path: str) -> str:
    """Read a .txt, .csv, .vcf or .gz genotype file as text. Opened with newline="" so a lone
    CR is not a line break (as in the web app). Raises FileNotFoundError."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="ignore", newline="") as f:
        return f.read()
