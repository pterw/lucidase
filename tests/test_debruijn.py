"""Tests for the de Bruijn tool (graph_core, assembly, debruijn_explorer).

Property tests use fixed seeds and capped case counts so the file stays fast.
"""

from __future__ import annotations

import inspect
import os
import random
import sys
import tracemalloc
from collections import Counter

import networkx as nx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import graph_core as gc  # noqa: E402
from assembly import (  # noqa: E402
    assembly_metrics,
    build_assembly_graph,
    extract_contigs,
    simplify_graph,
)
from bio_engine import revcomp  # noqa: E402


# ---------------------------------------------------------------------------
# Property tests: trail_cover is an exact, minimal edge cover
# ---------------------------------------------------------------------------
def _trail_errors(kmers: list[str]) -> list[str]:
    g = gc.build_graph(kmers)
    k = len(kmers[0])
    trails = gc.trail_cover(g)
    errs = []

    used = Counter(e for t in trails for e in t)
    if set(used) != set(g.edges(keys=True)) or any(c != 1 for c in used.values()):
        errs.append("every edge must be used exactly once")

    for t in trails:
        for a, b in zip(t, t[1:]):
            if a[1] != b[0]:
                errs.append("trail is not a valid walk")

    expected = 0
    for comp in nx.weakly_connected_components(g):
        expected += max(
            1, sum(max(g.out_degree(n) - g.in_degree(n), 0) for n in comp)
        )
    if len(trails) != expected:
        errs.append(f"trail count {len(trails)} != {expected}")

    spelled = Counter()
    for t in trails:
        s = gc.spell(t)
        for i in range(len(s) - k + 1):
            spelled[s[i : i + k]] += 1
    if spelled != Counter(kmers):
        errs.append("spelled k-mer multiset differs from input")
    return errs


def _random_case(rng: random.Random):
    k = rng.randint(2, 6)
    alpha = rng.choice(["AC", "ACG", "ACGT"])
    mode = rng.choice(["seq", "kmers"])
    both = rng.random() < 0.3
    unique = rng.random() < 0.4
    if mode == "seq":
        longest = rng.randint(k, k + 12)
        text = "\n".join(
            "".join(rng.choice(alpha) for _ in range(rng.randint(1, longest)))
            for _ in range(rng.randint(1, 4))
        )
    else:
        text = " ".join(
            "".join(rng.choice(alpha) for _ in range(k))
            for _ in range(rng.randint(1, 10))
        )
    return text, mode, k, both, unique


@pytest.mark.parametrize("seed", [1234, 7, 2026])
def test_trail_cover_properties_hold_on_random_inputs(seed):
    rng = random.Random(seed)
    checked = 0
    for _ in range(300):
        text, mode, k, both, unique = _random_case(rng)
        try:
            kmers, _ = gc.collect_kmers(text, mode, k, both, unique)
        except ValueError:
            continue
        checked += 1
        assert _trail_errors(kmers) == [], (text, mode, k, both, unique)
    assert checked > 100  # guard against a generator that rejects everything


def test_trail_cover_self_loop_and_parallel_edges():
    # Self-loop on AA with a parallel pair, then AA -> AC.
    assert _trail_errors(["AAA", "AAA", "AAC"]) == []
    # Two components, one needing two trails.
    assert _trail_errors(["ACG", "CGT", "CGA", "TTT"]) == []


# ---------------------------------------------------------------------------
# G-F1: the dead --selftest flag is gone
# ---------------------------------------------------------------------------
def test_cli_help_does_not_list_selftest_and_module_imports(capsys):
    import debruijn_explorer as d  # imports cleanly

    with pytest.raises(SystemExit) as exc:
        d.parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--headless" in out
    assert "--selftest" not in out


def test_explorer_has_no_selftest_entry_point():
    import debruijn_explorer as d

    assert not hasattr(d, "selftest")
    with pytest.raises(SystemExit):
        d.parse_args(["--selftest"])


# ---------------------------------------------------------------------------
# G-F2: reverse-complement twins are reported once
# ---------------------------------------------------------------------------
def _random_genome(n: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(n))


def test_both_strands_reports_each_contig_once():
    genome = _random_genome(3000, 11)
    kmers, _ = gc.collect_kmers(genome, "seq", 21, True, False)
    m = gc.analyze(kmers)
    total = m.metrics["total_length"]
    assert len(genome) - 5 <= total <= len(genome) + 5, (
        f"total_length {total} for a {len(genome)} bp genome"
    )
    seqs = [c["sequence"] for c in m.contigs]
    for s in seqs:
        assert revcomp(s) not in seqs or revcomp(s) == s


def test_both_strands_keeps_lexicographically_smaller_strand():
    genome = _random_genome(400, 5)
    kmers, _ = gc.collect_kmers(genome, "seq", 15, True, False)
    contigs = extract_contigs(build_assembly_graph(kmers), 15, canonical=True)
    assert len(contigs) == 1
    seq = contigs[0]["sequence"]
    assert seq == min(seq, revcomp(seq))
    assert seq in (genome, revcomp(genome))


def test_read_plus_revcomp_is_deduplicated():
    # A read plus its reverse complement is strand-symmetric, so the two
    # strands collapse to one contig of the true length.
    s = "CTTCGCCTGATACG"
    kmers, _ = gc.collect_kmers(f"{s}\n{revcomp(s)}", "seq", 5, False, False)
    result = gc.analyze(kmers)
    assert len(result.contigs) == 1
    assert result.metrics["total_length"] == len(s)


def test_forward_only_input_drops_no_contig():
    # Two unrelated forward reads: the k-mer set is not closed under reverse
    # complement, so nothing is deduplicated and both contigs are reported.
    s, t = "AAACCCGGGTTTAC", "ACACAGTGTCGA"
    kmers, _ = gc.collect_kmers(f"{s}\n{t}", "seq", 5, False, False)
    kset = set(kmers)
    assert {revcomp(x) for x in kset} != kset
    result = gc.analyze(kmers)
    assert sorted(c["sequence"] for c in result.contigs) == sorted([s, t])
    assert result.metrics["total_length"] == len(s) + len(t)


# ---------------------------------------------------------------------------
# G-F3: FASTA headers in k-mer mode
# ---------------------------------------------------------------------------
def test_kmers_mode_ignores_whole_fasta_header_lines():
    kmers, _ = gc.collect_kmers(">seq1 human gene\nACGTAC", "kmers", 6, False, False)
    assert kmers == ["ACGTAC"]


def test_kmers_mode_header_words_never_become_kmers():
    # "gene" has length 4 == k, so it would silently become a k-mer.
    text = ">r1 gene\nACGT CGTA\n>r2 more\nGTAC"
    kmers, _ = gc.collect_kmers(text, "kmers", 4, False, False)
    assert kmers == ["ACGT", "CGTA", "GTAC"]


# ---------------------------------------------------------------------------
# G-F4: MAX_KMERS is enforced while generating
# ---------------------------------------------------------------------------
def test_max_kmers_raises_before_materialising_the_list(monkeypatch):
    monkeypatch.setattr(gc, "MAX_KMERS", 100)
    text = "ACGT" * 250_000  # 1 Mbp, about 1M k-mers if fully built
    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match="limit is 100"):
            gc.collect_kmers(text, "seq", 5, False, False)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # A fully materialised list would be tens of MB.
    assert peak < 8_000_000, f"peak {peak} bytes: the k-mer list was built first"


def test_max_kmers_boundary_is_inclusive(monkeypatch):
    monkeypatch.setattr(gc, "MAX_KMERS", 10)
    kmers, _ = gc.collect_kmers("ACGTACGTACGT", "seq", 3, False, False)  # 10 k-mers
    assert len(kmers) == 10
    with pytest.raises(ValueError, match="limit is 10"):
        gc.collect_kmers("ACGTACGTACGTA", "seq", 3, False, False)  # 11 k-mers


def test_max_kmers_counts_both_strands(monkeypatch):
    monkeypatch.setattr(gc, "MAX_KMERS", 10)
    with pytest.raises(ValueError, match="limit is 10"):
        gc.collect_kmers("ACGTACGTACG", "seq", 3, True, False)  # 9 x 2 = 18


# ---------------------------------------------------------------------------
# G-F5: no dead, overcounted `coverage` attribute on the Eulerian multigraph
# ---------------------------------------------------------------------------
def test_eulerian_multigraph_has_no_coverage_attribute():
    g = gc.build_graph(["AAA", "AAA", "AAA", "AAC"])
    for _, _, data in g.edges(data=True):
        assert "coverage" not in data
    assert g.number_of_edges() == 4


def test_assembly_graph_coverage_is_per_distinct_kmer():
    ag = build_assembly_graph(["AAA", "AAA", "AAA", "AAC"])
    assert ag.edges["AA", "AA"]["coverage"] == 3
    assert ag.edges["AA", "AC"]["coverage"] == 1


# ---------------------------------------------------------------------------
# G-F7: one default k
# ---------------------------------------------------------------------------
def test_default_k_is_shared_by_assemble_and_cli():
    import debruijn_explorer as d

    assert isinstance(d.DEFAULT_K, int)
    assert inspect.signature(d.assemble).parameters["k"].default == d.DEFAULT_K
    assert d.parse_args([]).k == d.DEFAULT_K


# ---------------------------------------------------------------------------
# Assembly sanity (locks in the teaching-tool behaviour)
# ---------------------------------------------------------------------------
def test_linear_genome_assembles_to_one_contig():
    genome = _random_genome(500, 3)
    kmers, _ = gc.collect_kmers(genome, "seq", 21, False, False)
    ag, _ = simplify_graph(build_assembly_graph(kmers), 21)
    contigs = extract_contigs(ag, 21)
    assert [c["sequence"] for c in contigs] == [genome]
    assert assembly_metrics(contigs)["total_length"] == len(genome)


def test_both_strands_circular_genome_reported_once():
    genome = _random_genome(300, 9)
    k = 15
    circ = genome + genome[: k - 1]  # wrap-around k-mers make the graph a cycle
    kmers, _ = gc.collect_kmers(circ, "seq", k, True, False)
    contigs = gc.analyze(kmers).contigs
    assert len(contigs) == 1
    assert contigs[0]["circular"] is True
    assert contigs[0]["edges"] == len(genome)
