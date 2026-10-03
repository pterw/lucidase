"""Tests for the deterministic synthetic karyogram sample (contract K-C5)."""

import json
import re

from tools import make_synthetic_karyogram_sample as gen

KB = json.loads(gen.KB_PATH.read_text(encoding="utf-8"))
CHROMS = KB["assemblies"]["GRCh37"]["chromosomes"]


def _rows(text):
    return [l.split("\t") for l in text.split("\n") if l and not l.startswith("#")]


def _committed():
    return gen.OUTPUT_PATH.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _original_rows():
    text = gen.ORIGINAL_PATH.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return [l for l in text.split("\n") if l and not l.startswith("#")]


def _background():
    return [r for r in _rows(_committed()) if r[0].startswith("i9")]


def test_regenerating_in_memory_equals_the_committed_file():
    same = gen.build_sample_text() == _committed()  # a bool: pytest would diff 370 KB for minutes
    assert same, "committed sample is stale: run tools/make_synthetic_karyogram_sample.py"


def test_rows_are_the_original_rows_plus_exactly_15000_background_rows():
    lines = [l for l in _committed().split("\n") if l and not l.startswith("#")]
    kept = [l for l in lines if not l.startswith("i9")]
    assert sorted(kept) == sorted(_original_rows())  # verbatim; the file is position-sorted
    assert len(lines) - len(kept) == 15_000
    assert [r[0] for r in _background()] == [f"i9{n:07d}" for n in range(1, 15_001)]
    assert "\r" not in gen.OUTPUT_PATH.read_bytes().decode("utf-8")


def test_background_positions_obey_the_allowed_position_rules():
    original = {(r.split("\t")[1], int(r.split("\t")[2])) for r in _original_rows()}
    loci = {}
    for locus in KB["loci"].values():
        loci.setdefault(locus["chrom"], []).append(locus["pos_grch37"])
    seen = set()
    for _id, chrom, pos, geno in _background():
        pos = int(pos)
        info = CHROMS[chrom]  # Y and MT would KeyError or fail below
        assert chrom != "Y"
        assert 1 <= pos <= info["length"]
        assert not info["centromere"][0] <= pos <= info["centromere"][1]
        if chrom in ("13", "14", "15", "21", "22"):
            assert pos > info["centromere"][1]
        assert all(abs(pos - p) > 1_000 for p in loci.get(chrom, []))
        assert (chrom, pos) not in original
        assert (chrom, pos) not in seen
        seen.add((chrom, pos))
        assert re.fullmatch(r"[ACGT]{2}", geno)


def test_per_chromosome_counts_match_largest_remainder_allocation():
    counts = gen.allocate(CHROMS)
    assert sum(counts.values()) == 15_000
    assert "Y" not in counts
    total = sum(CHROMS[c]["length"] for c in counts)
    for c, n in counts.items():
        assert abs(n - 15_000 * CHROMS[c]["length"] / total) < 1  # floor or ceil of the quota
    actual = {}
    for _id, chrom, _pos, _g in _background():
        actual[chrom] = actual.get(chrom, 0) + 1
    assert actual == counts


def test_rows_are_sorted_by_chromosome_order_then_position():
    order = gen.CHROM_ORDER
    keys = [(order.index(r[1]), int(r[2])) for r in _rows(_committed())]
    assert keys == sorted(keys)
