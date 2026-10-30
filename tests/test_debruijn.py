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

import debruijn.graph_core as gc  # noqa: E402
from debruijn.assembly import (  # noqa: E402
    assembly_metrics,
    build_assembly_graph,
    extract_contigs,
    simplify_graph,
    write_gfa,
)
from debruijn.bio_engine import evaluate_assembly_against_reference, revcomp  # noqa: E402


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
    import debruijn.debruijn_explorer as d  # imports cleanly

    with pytest.raises(SystemExit) as exc:
        d.parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--headless" in out
    assert "--selftest" not in out


def test_explorer_has_no_selftest_entry_point():
    import debruijn.debruijn_explorer as d

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
    m = gc.analyze(kmers, both=True)
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


def test_read_plus_revcomp_is_deduplicated_when_both_strands_is_on():
    s = "CTTCGCCTGATACG"
    kmers, _ = gc.collect_kmers(s, "seq", 5, True, False)
    result = gc.analyze(kmers, both=True)
    assert len(result.contigs) == 1
    assert result.metrics["total_length"] == len(s)
    assert any("one contig per strand pair" in n for n in result.notes)


def test_strand_closed_forward_input_keeps_both_contigs():
    # C-7: strand symmetry is no longer inferred. A read plus its reverse complement,
    # given as two forward reads, is two contigs and no note claims otherwise.
    s = "CTTCGCCTGATACG"
    kmers, _ = gc.collect_kmers(f"{s}\n{revcomp(s)}", "seq", 5, False, False)
    result = gc.analyze(kmers)
    assert sorted(c["sequence"] for c in result.contigs) == sorted([s, revcomp(s)])
    assert result.metrics["total_length"] == 2 * len(s)
    assert not any("strand pair" in n for n in result.notes)


def test_both_strands_with_n_reports_each_contig_once():
    # C-3: N is valid DNA in the reads and revcomp(N) = N, so N must not defeat the dedup.
    seq = "ACGTNACGTTGCAGGATCCATTGACN"
    kmers, _ = gc.collect_kmers(seq, "seq", 5, True, False)
    result = gc.analyze(kmers, both=True)
    assert "N" in "".join(kmers)
    seqs = [c["sequence"] for c in result.contigs]
    assert all(revcomp(x) not in seqs or revcomp(x) == x for x in seqs)
    assert any("N" in x for x in seqs)
    undeduplicated = gc.analyze(kmers, both=False)
    assert len(result.contigs) < len(undeduplicated.contigs)


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
    import debruijn.debruijn_explorer as d

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
    contigs = gc.analyze(kmers, both=True).contigs
    assert len(contigs) == 1
    assert contigs[0]["circular"] is True
    assert contigs[0]["edges"] == len(genome)


# ---------------------------------------------------------------------------
# S4c-C-1: the reference evaluation scores either strand of a canonical contig
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [5, 6, 7, 8])
def test_reference_evaluation_is_strand_independent(seed):
    genome = _random_genome(400, seed)
    kmers, _ = gc.collect_kmers(genome, "seq", 15, True, False)
    fwd = gc.analyze(kmers, ref_seq=genome, both=True).ref_eval
    rev = gc.analyze(kmers, ref_seq=revcomp(genome), both=True).ref_eval
    assert fwd["genome_fraction"] > 0.95
    assert rev["genome_fraction"] == fwd["genome_fraction"]
    assert rev["mean_identity"] == fwd["mean_identity"]


def test_reference_evaluation_aligns_a_reverse_strand_contig():
    genome = _random_genome(200, 21)
    contig = {"id": 1, "sequence": revcomp(genome), "length": len(genome)}
    ev = evaluate_assembly_against_reference([contig], genome)
    assert ev["genome_fraction"] == 1.0
    assert ev["mean_identity"] == 1.0


# ---------------------------------------------------------------------------
# S4c-C-2: GFA links follow the canonical sequences and use - where the rc was kept
# ---------------------------------------------------------------------------
def _gfa(tmp_path, text, k, both):
    kmers, _ = gc.collect_kmers(text, "seq", k, both, False)
    m = gc.analyze(kmers, both=both)
    path = tmp_path / "out.gfa"
    write_gfa(m.contigs, str(path), k, both=both)
    segs, links = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        f = line.split("	")
        if f[0] == "S":
            segs[f[1]] = f[2]
        elif f[0] == "L":
            links.append(f[1:])
    return m, segs, links


def _oriented(segs, name, orient):
    return segs[name] if orient == "+" else revcomp(segs[name])


@pytest.mark.parametrize("seed", range(8))
def test_gfa_links_branching_both_strands(tmp_path, seed):
    stem, tail1, tail2 = (_random_genome(40, seed * 3 + i) for i in range(3))
    head = _random_genome(40, seed * 3 + 100)
    text = f"{head + stem + tail1}\n{head + stem + tail2}"
    k = 11
    m, segs, links = _gfa(tmp_path, text, k, True)
    assert len(m.contigs) == 3  # the shared head+stem and the two tails, once each
    assert len(links) == 2, links
    for a, ao, b, bo, cigar in links:
        assert cigar == f"{k - 1}M"
        assert _oriented(segs, a, ao)[-(k - 1):] == _oriented(segs, b, bo)[: k - 1]


def test_gfa_uses_minus_orientation_for_some_branching_input(tmp_path):
    orients = set()
    for seed in range(8):
        stem, tail1, tail2 = (_random_genome(40, seed * 3 + i) for i in range(3))
        head = _random_genome(40, seed * 3 + 100)
        text = f"{head + stem + tail1}\n{head + stem + tail2}"
        _, _, links = _gfa(tmp_path, text, 11, True)
        orients |= {l[1] for l in links} | {l[3] for l in links}
    assert "-" in orients


def test_gfa_forward_only_input_keeps_plus_links(tmp_path):
    stem, tail1, tail2 = (_random_genome(40, 60 + i) for i in range(3))
    text = f"{stem + tail1}\n{stem + tail2}"
    _, segs, links = _gfa(tmp_path, text, 11, False)
    assert links
    assert all(l[1] == "+" and l[3] == "+" for l in links)


# ---------------------------------------------------------------------------
# S4-F3 follow-up: the CLI prints the GUI's labels, rules and thresholds
# ---------------------------------------------------------------------------
def test_cli_prints_the_same_binning_and_identity_labels_as_the_gui(capsys):
    import debruijn.debruijn_explorer as d
    from debruijn.bio_engine import alignment_basis_text
    from debruijn.ml_engine import binning_caveat_lines

    genome = _random_genome(300, 4)
    args = d.parse_args(
        ["--headless", "--seq", genome, "-k", "15", "--both-strands", "--binning", "--ref", genome]
    )
    assert d.run_headless(args) == 0
    out = capsys.readouterr().out
    assert "Potential Outliers" not in out
    assert "Flagged by 10% rule" in out
    assert "heuristic, exploratory" in out.lower()
    assert "left unbinned" in out
    assert alignment_basis_text() in out
    for line in binning_caveat_lines({}):
        assert line.split(";")[0] in out


def test_gui_and_cli_share_one_default_k():
    import debruijn.debruijn_explorer as d

    assert d.DEFAULT_K == gc.DEFAULT_K == 3
    assert "IntVar(value=DEFAULT_K)" in open(os.path.join(ROOT, "gui.py"), encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Audited fixes: viewport autoscale, smaller nodes, label centering, gzip, k<2
# ---------------------------------------------------------------------------
def test_render_autoscales_viewport_and_generates_smaller_nodes():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    kmers, notes = gc.collect_kmers("LEMONLEMONADE", "seq", 3, False, False)
    m = gc.analyze(kmers, notes)
    fig = Figure(figsize=(8.5, 5.6), dpi=100)
    FigureCanvasAgg(fig)
    gc.render(fig, m)
    fig.canvas.draw()
    ax = fig.axes[0]

    # Pre-fix bug: render never autoscaled view limits, so y was stuck at (0.0, 1.0)
    # and all nodes with y < 0 (half the graph) were clipped off the canvas.
    ymin, ymax = ax.get_ylim()
    assert ymin < -0.9, f"ymin {ymin} should encompass nodes extending to -1.0"
    assert ymax > 0.9, f"ymax {ymax} should encompass nodes extending to +1.0"

    # Node size: nodes should be smaller and not giant balloons taking 24% of canvas.
    # Radius of nodes should be <= 0.12 in data units.
    circles = [p for p in ax.patches if isinstance(p, gc.Circle)]
    assert circles, "Graph should contain Circle patches for nodes"
    assert all(c.radius <= 0.12 for c in circles), f"Node radius {[c.radius for c in circles]} is too large"


def test_render_edge_label_positions_centered_between_nodes():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    kmers, notes = gc.collect_kmers("AAAAAC", "seq", 3, False, False)
    m = gc.analyze(kmers, notes)
    fig = Figure(figsize=(8.5, 5.6), dpi=100)
    FigureCanvasAgg(fig)
    gc.render(fig, m)
    fig.canvas.draw()
    ax = fig.axes[0]

    # Node AA is at (-1, 0) and AC is at (1, 0).
    # The label for edge AA -> AC ("AAC (#4)") must be placed near the mathematical
    # midpoint (x approx 0), not offset near x=0.5 or 1.0 from untransformed unit arrow vertices.
    texts = [t for t in ax.texts if "AAC" in t.get_text()]
    assert len(texts) == 1
    t_pos = texts[0].get_position()
    assert abs(t_pos[0]) < 0.15, f"Edge label x-position {t_pos[0]} is not centered near x=0.0"


def test_collect_kmers_k_less_than_two_fails_fast():
    for bad_k in [1, 0, -2]:
        with pytest.raises(ValueError, match="k must be at least 2"):
            gc.collect_kmers("ACGTACGT", "seq", bad_k, False, False)
        with pytest.raises(ValueError, match="k must be at least 2"):
            gc.collect_kmers("AC GT", "kmers", bad_k, False, False)


def test_load_sequences_as_fasta_supports_gzip(tmp_path):
    import gzip
    from debruijn.bio_engine import load_sequences_as_fasta

    fa_gz = tmp_path / "reads.fasta.gz"
    with gzip.open(fa_gz, "wt", encoding="utf-8") as f:
        f.write(">r1\nACGTACGT\n>r2\nCGTACGTA\n")

    text, note = load_sequences_as_fasta(str(fa_gz))
    assert ">r1" in text and ">r2" in text
    assert "Loaded 2 record(s)" in note

    fq_gz = tmp_path / "sample.fq.gz"
    with gzip.open(fq_gz, "wt", encoding="utf-8") as f:
        f.write("@read1\nACGT\n+\nIIII\n")

    fq_text, fq_note = load_sequences_as_fasta(str(fq_gz))
    assert ">read1" in fq_text
    assert "fastq" in fq_note.lower()


def test_extract_kmer_features_arbitrary_k():
    from debruijn.ml_engine import extract_kmer_features

    vec2 = extract_kmer_features("ACGTACGT", k=2)
    assert len(vec2) == 16
    assert abs(vec2.sum() - 1.0) < 1e-6

    vec3 = extract_kmer_features("ACGTACGT", k=3)
    assert len(vec3) == 64
    assert abs(vec3.sum() - 1.0) < 1e-6


def test_render_dense_graph_declutters_redundant_edge_labels_and_adapts_radius():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    # 67 bp sequence with k=5 gives 62 nodes and 62 edges (> 25 edges)
    seq = "AAACAAGAATACACGACTAGAGGAGTATATGATTCCCGCCTCGCGTCTGCTCTTGGGTGTGTTTAA"
    kmers, notes = gc.collect_kmers(seq, "seq", 5, False, False)
    m = gc.analyze(kmers, notes)
    fig = Figure(figsize=(8.5, 5.6), dpi=100)
    FigureCanvasAgg(fig)
    gc.render(fig, m)
    fig.canvas.draw()
    ax = fig.axes[0]

    # In dense graphs with >25 edges, edge labels should not overwhelm the canvas
    # Instead of drawing 62 overlapping text boxes over nodes, only parallel, self-loop
    # and active edges have labels.
    edge_label_texts = [
        t.get_text() for t in ax.texts
        if any(char in t.get_text() for char in ["#", "AAAC", "TGTT"])
    ]
    assert len(edge_label_texts) < 62, f"Dense graphs should declutter non-branching edge labels, got {len(edge_label_texts)}"

    # Node circles must adapt dynamically and not exceed spacing bounds
    circles = [p for p in ax.patches if isinstance(p, gc.Circle)]
    assert circles
    assert all(c.radius <= 0.09 for c in circles)

    # In graphs with >40 nodes, intermediate non-branching node labels are decluttered
    node_texts = [t.get_text() for t in ax.texts if t.get_text() not in edge_label_texts]
    assert len(node_texts) < 62, f"Dense graphs should declutter intermediate node labels, got {len(node_texts)}"


def test_render_large_multi_copy_graph_landmarks():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    # 4 copies of a 105 bp sequence with k=13 gives 94 nodes and 372 edges
    seq = "ATGAACTTTATTATCAATAAAGATATTTACAATGAAATCATTAATGATAAGTTTATAAACGAATACATCAACAATAAATTTATCGATGATAGCTTCATTAACTAA\n" * 4
    kmers, notes = gc.collect_kmers(seq, "seq", 13, False, False)
    m = gc.analyze(kmers, notes)
    fig = Figure(figsize=(10, 6), dpi=100)
    FigureCanvasAgg(fig)
    gc.render(fig, m)
    fig.canvas.draw()
    ax = fig.axes[0]

    # Circles must be scaled and not collide
    circles = [p for p in ax.patches if isinstance(p, gc.Circle)]
    assert len(circles) == 94
    assert all(c.radius <= 0.09 for c in circles)

    # Parallel coverage edges (>25 edges) must not create 372 edge text labels
    edge_labels = [t for t in ax.texts if "ATG" in t.get_text() and "#" in t.get_text()]
    assert len(edge_labels) <= 2


