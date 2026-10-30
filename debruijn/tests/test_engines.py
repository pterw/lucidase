"""The alignment and clustering engines report what they compute (S4b-C-17, S4b-C-18)."""

from __future__ import annotations

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
DEBRUIJN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DEBRUIJN_DIR not in sys.path:
    sys.path.insert(0, DEBRUIJN_DIR)

import debruijn.bio_engine as bio_engine  # noqa: E402
import debruijn.ml_engine as ml_engine  # noqa: E402


def _dna(n: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(n))


def _contig(i: int, seq: str, cov: float = 10.0) -> dict:
    gc = (seq.count("G") + seq.count("C")) / len(seq)
    return {
        "id": i,
        "sequence": seq,
        "length": len(seq),
        "gc_content": gc,
        "mean_coverage": cov,
    }


def _mutate(seq: str, positions: list[int]) -> str:
    out = list(seq)
    for p in positions:
        out[p] = {"A": "C", "C": "G", "G": "T", "T": "A"}[out[p]]
    return "".join(out)


def test_identity_is_matches_over_aligned_columns_not_score_per_base():
    ref = _dna(300, 1)
    contig = _mutate(ref[100:200], [30, 50, 70, 80, 90])  # 95 matches of 100 columns
    ev = bio_engine.evaluate_assembly_against_reference([_contig(1, contig)], ref)
    assert ev["aligned_contigs"] == 1
    assert ev["alignments"][0]["identity"] == 0.95
    assert ev["mean_identity"] == 0.95


def test_chance_local_hits_are_not_counted_and_the_limits_are_reported():
    ref = _dna(2000, 2)
    ev = bio_engine.evaluate_assembly_against_reference([_contig(1, _dna(30, 99))], ref)
    assert ev["aligned_contigs"] == 0
    assert ev["genome_fraction"] == 0.0
    assert ev["min_aligned_columns"] == bio_engine.MIN_ALIGNED_COLUMNS
    assert ev["min_identity"] == bio_engine.MIN_ALIGNMENT_IDENTITY
    assert "matches / aligned columns" in bio_engine.alignment_basis_text()


def test_low_identity_hit_is_dropped():
    ref = _dna(300, 3)
    contig = _mutate(ref[100:200], list(range(5, 95, 4)))  # 23 substitutions
    ev = bio_engine.evaluate_assembly_against_reference([_contig(1, contig)], ref)
    assert ev["aligned_contigs"] == 0


def test_one_organism_gets_one_bin():
    base = _dna(400, 5)
    contigs = [_contig(i, _mutate(base, [i, i + 50]), 10.0 + i * 0.1) for i in range(8)]
    _, summary = ml_engine.bin_contigs(contigs)
    assert summary["n_bins"] == 1
    assert {c["bin_id"] for c in contigs} == {1}


def test_two_clear_compositions_still_split():
    rng = random.Random(7)
    at = ["".join(rng.choice("AAAT" + "C") for _ in range(300)) for _ in range(5)]
    gcs = ["".join(rng.choice("GGGC" + "A") for _ in range(300)) for _ in range(5)]
    contigs = [_contig(i, s, 10.0) for i, s in enumerate(at + gcs)]
    _, summary = ml_engine.bin_contigs(contigs)
    assert summary["n_bins"] == 2
    assert len({c["bin_id"] for c in contigs[:5]}) == 1
    assert contigs[0]["bin_id"] != contigs[5]["bin_id"]


def test_short_contigs_are_left_unbinned_and_counted():
    short = [_contig(i, _dna(30, i)) for i in range(4)]
    long_ = [_contig(10 + i, _dna(300, 50 + i)) for i in range(4)]
    _, summary = ml_engine.bin_contigs(short + long_)
    assert all(c["bin_id"] == ml_engine.UNBINNED and not c["is_outlier"] for c in short)
    assert all(c["bin_id"] >= 1 for c in long_)
    assert summary["n_unbinned"] == 4
    assert summary["min_contig_len"] == ml_engine.MIN_BIN_CONTIG_LEN


def test_only_short_contigs_report_no_bins_and_no_outliers():
    contigs = [_contig(i, _dna(30, i)) for i in range(6)]
    _, summary = ml_engine.bin_contigs(contigs)
    assert summary["n_bins"] == 0
    assert summary["outlier_count"] == 0


def test_caveat_states_heuristic_and_the_fixed_ten_percent_rule():
    text = "\n".join(ml_engine.binning_caveat_lines({"n_unbinned": 3, "min_contig_len": 100}))
    assert "Heuristic, exploratory" in text
    assert "fixed 10%" in text
    assert "100 bp" in text and "3 here" in text
    assert "silhouette" in text


def test_gui_tab_prints_the_caveat_and_the_alignment_basis():
    gui_candidates = [os.path.join(os.path.dirname(__file__), "..", "gui.py"), os.path.join(os.path.dirname(__file__), "..", "..", "gui.py")]
    gui_path = next(p for p in gui_candidates if os.path.exists(p))
    src = open(gui_path, encoding="utf-8").read()
    assert "binning_caveat_lines(bs)" in src
    assert "alignment_basis_text()" in src
    assert "(heuristic, exploratory)" in src
    assert "Potential Outliers" not in src
