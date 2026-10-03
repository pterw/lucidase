"""
Graph Core: De Bruijn Directed Multigraphs, Eulerian Trails & Visualization
==========================================================================
Constructs directed multigraphs from k-mers, computes minimum Eulerian trail covers
via Hierholzer's algorithm with dummy edge matching, handles spatial graph layout,
and renders publication-quality matplotlib visualizations.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import os
import sys

# Ensure Matplotlib config directory is inside workspace to avoid permission errors
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".matplotlib_cache"))

import networkx as nx
import pandas as pd
from Bio.SeqRecord import SeqRecord
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch
from matplotlib.path import Path

from assembly import (
    assembly_metrics,
    build_assembly_graph,
    extract_contigs,
    simplify_graph,
)
from bio_engine import (
    contigs_to_seqrecords,
    evaluate_assembly_against_reference,
    parse_records,
    revcomp,
)
from ml_engine import (
    bin_contigs,
    coverage_summary,
    fit_kmer_error_model,
    kmer_spectrum,
)

# ---------------------------------------------------------------------------
# Palette (citrus) and limits
# ---------------------------------------------------------------------------
PITH = "#FFF8E1"  # background
LEMON = "#F9D923"  # ordinary node
RIND = "#E3B505"  # node outline
LIME = "#6BA32B"  # trail start
ORANGE = "#F28C28"  # trail end
EDGE = "#8C6D1F"  # edges (single trail)
INK = "#3B2F0B"  # text
FUTURE = "#D6CBA0"  # not-yet-traversed edges
FUTURE_TXT = "#B3A678"
PANEL = "#FFF1BF"
TRAIL_COLORS = ["#2F7D32", "#D9480F", "#C2255C", "#1C7ED6", "#9C36B5", "#8C6D1F"]

DEFAULT_K = 3  # the one default k for the GUI, the Python API and the CLI
MAX_KMERS = 500_000  # cap for total k-mers (raised for real assembly use)
MAX_DRAW_NODES = 400  # above this the graph is not drawn (tables still work)
MAX_TABLE_ROWS = 2000


def _require_dna(items: list[str]) -> None:
    for x in items:
        bad = set(x.upper()) - set("ACGTN")
        if bad:
            raise ValueError(
                f"Both strands only makes sense for DNA, but found: {sorted(bad)} in '{x}'"
            )


def _limit_error(n: int) -> ValueError:
    return ValueError(
        f"Input produced more than {MAX_KMERS:,} k-mers (counted {n:,} before stopping); "
        f"limit is {MAX_KMERS:,}. Use a smaller file or larger k."
    )


def _iter_read_kmers(records: list[str], k: int, both: bool):
    """Yield the k-mers of every record (and its reverse complement if `both`)
    lazily, so the caller can stop as soon as a limit is exceeded."""
    for rec in records:
        if len(rec) < k:
            continue
        for s in [rec] + ([revcomp(rec)] if both else []):
            for i in range(len(s) - k + 1):
                yield s[i : i + k]


def collect_kmers(text: str, mode: str, k: int, both: bool, unique: bool):
    """Turn raw input into a list of k-mers (a multiset unless `unique`).
    Returns (kmers, notes). Raises ValueError with a readable message.

    The MAX_KMERS limit is enforced while k-mers are generated, so an oversized
    input is rejected without first building the whole list."""
    notes: list[str] = []
    if mode == "kmers":
        # FASTA header lines are dropped whole, so header words never become k-mers.
        body = "\n".join(
            ln for ln in text.splitlines() if not ln.lstrip().startswith(">")
        )
        kmers = [t.upper() for t in re.split(r"[\s,;]+", body.strip()) if t]
        if not kmers:
            raise ValueError("Enter some k-mers (separated by spaces, commas or new lines).")
        if len({len(x) for x in kmers}) != 1:
            raise ValueError("All k-mers must have the same length.")
        if len(kmers) * (2 if both else 1) > MAX_KMERS:
            raise _limit_error(len(kmers) * (2 if both else 1))
        if both:
            _require_dna(kmers)
            kmers = kmers + [revcomp(x) for x in kmers]
    else:
        records = parse_records(text)
        if not records:
            raise ValueError("Enter a sequence or FASTA text.")
        if both:
            _require_dna(records)
        short_count = sum(1 for rec in records if len(rec) < k)
        kmers = []
        for km in _iter_read_kmers(records, k, both):
            kmers.append(km)
            if len(kmers) > MAX_KMERS:
                raise _limit_error(len(kmers))
        if not kmers:
            raise ValueError(f"No records are at least k={k} characters long.")
        if short_count:
            notes.append(f"Ignored {short_count} record(s) shorter than k={k}.")

    if unique:
        before = len(kmers)
        kmers = sorted(set(kmers))
        if before != len(kmers):
            notes.append(f"Deduplicated {before} k-mers down to {len(kmers)} unique.")
    return kmers, notes


def build_graph(kmers: list[str]) -> nx.MultiDiGraph:
    """Nodes = (k-1)-mers, edges = k-mers. Parallel edges for repeated k-mers."""
    if not kmers:
        raise ValueError("no k-mers")
    lengths = {len(x) for x in kmers}
    if len(lengths) != 1:
        raise ValueError("all k-mers must have the same length")
    if lengths.pop() < 2:
        raise ValueError("k must be at least 2")
    # Repeated k-mers become parallel edges. Copy counts live in the k-mer
    # multiset (see analyze), not on the edges.
    g = nx.MultiDiGraph()
    for km in kmers:
        g.add_edge(km[:-1], km[1:], kmer=km)
    return g


def _hierholzer(adj, start):
    """Iterative Hierholzer on adjacency lists of (v, key, is_dummy)."""
    stack = [(start, None)]
    out = []
    while stack:
        node, via = stack[-1]
        if adj[node]:
            v, key, dummy = adj[node].pop()
            stack.append((v, (node, v, key, dummy)))
        else:
            stack.pop()
            if via is not None:
                out.append(via)
    out.reverse()
    return out


def trail_cover(g: nx.MultiDiGraph) -> list[list[tuple[str, str, int]]]:
    """Minimum set of edge-disjoint trails covering every edge exactly once.
    One trail per component whenever an Eulerian path/circuit exists."""
    trails = []
    for comp in sorted(nx.weakly_connected_components(g), key=min):
        bal = {n: g.out_degree(n) - g.in_degree(n) for n in comp}
        sources = [n for n in sorted(comp) for _ in range(max(bal[n], 0))]
        sinks = [n for n in sorted(comp) for _ in range(max(-bal[n], 0))]
        adj = defaultdict(list)
        for u, v, key in g.out_edges(comp, keys=True):
            adj[u].append((v, key, False))
        for i, (sk, sc) in enumerate(zip(sinks, sources)):
            adj[sk].append((sc, f"__dummy_{i}__", True))

        if not sources:
            start = min(comp, key=lambda n: (g.out_degree(n) == 0, n))
            circuit = _hierholzer(adj, start)
            real = [(u, v, k) for u, v, k, d in circuit if not d]
            if real:
                trails.append(real)
            continue

        raw = _hierholzer(adj, sinks[0])
        dummy_idx = [i for i, step in enumerate(raw) if step[3]]
        if not dummy_idx:
            trails.append([(u, v, k) for u, v, k, d in raw if not d])
            continue
        first_d = dummy_idx[0]
        rotated = raw[first_d + 1 :] + raw[: first_d + 1]

        cur: list[tuple[str, str, int]] = []
        for u, v, key, dummy in rotated:
            if dummy:
                if cur:
                    trails.append(cur)
                    cur = []
            else:
                cur.append((u, v, key))
        if cur:
            trails.append(cur)
    return trails


def spell(trail: list[tuple[str, str, int]]) -> str:
    """Reconstruct sequence string spelled by an Eulerian trail."""
    if not trail:
        return ""
    return trail[0][0] + "".join(v[-1] for _, v, _ in trail)


def _rotate_horizontal(pos: dict[str, tuple[float, float]]):
    """Align the principal axis of the layout with the horizontal axis."""
    pts = list(pos.values())
    if len(pts) < 2:
        return pos
    mean_x = sum(x for x, y in pts) / len(pts)
    mean_y = sum(y for x, y in pts) / len(pts)
    sxx = sum((x - mean_x) ** 2 for x, y in pts)
    syy = sum((y - mean_y) ** 2 for x, y in pts)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in pts)
    angle = 0.5 * math.atan2(2 * sxy, sxx - syy)
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)
    return {
        k: (
            (x - mean_x) * cos_a - (y - mean_y) * sin_a,
            (x - mean_x) * sin_a + (y - mean_y) * cos_a,
        )
        for k, (x, y) in pos.items()
    }


def _component_layout(sub: nx.MultiDiGraph) -> dict[str, tuple[float, float]]:
    n = len(sub)
    if n == 1:
        return {next(iter(sub)): (0.0, 0.0)}
    if n == 2:
        nodes = list(sub)
        return {nodes[0]: (-1.0, 0.0), nodes[1]: (1.0, 0.0)}
    simple = nx.Graph(sub)
    seed = random.Random(2026).randint(0, 10000)
    pos = nx.spring_layout(
        simple,
        k=1.8 / math.sqrt(n),
        iterations=160,
        seed=seed,
        scale=2.0,
    )
    pos = _rotate_horizontal(pos)
    pts = list(pos.values())
    min_x, max_x = min(x for x, y in pts), max(x for x, y in pts)
    min_y, max_y = min(y for x, y in pts), max(y for x, y in pts)
    rx, ry = max(max_x - min_x, 1e-6), max(max_y - min_y, 1e-6)
    return {k: ((x - min_x) / rx, (y - min_y) / ry) for k, (x, y) in pos.items()}


def compute_layout(g: nx.MultiDiGraph):
    """Layout components in horizontal rows."""
    if len(g) > MAX_DRAW_NODES:
        return None
    comps = [
        g.subgraph(c).copy()
        for c in sorted(nx.weakly_connected_components(g), key=len, reverse=True)
    ]
    if not comps:
        return {}
    layouts = [_component_layout(c) for c in comps]

    row_w = 0.0
    gap = 0.4
    placements = []
    for lyt in layouts:
        pts = list(lyt.values())
        w = max(x for x, y in pts) - min(x for x, y in pts) if len(pts) > 1 else 0.5
        h = max(y for x, y in pts) - min(y for x, y in pts) if len(pts) > 1 else 0.5
        placements.append((row_w, 0.0, lyt))
        row_w += max(w, 0.5) + gap

    out = {}
    for ox, oy, lyt in placements:
        for k, (x, y) in lyt.items():
            out[k] = (ox + x, oy + y)

    xs, ys = [p[0] for p in out.values()], [p[1] for p in out.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    ext = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    f = 2.0 / ext
    return {k: ((px - cx) * f, (py - cy) * f) for k, (px, py) in out.items()}


layout = compute_layout


def _loop_geometry(x, y, r, i):
    tilt = 0.55 + 0.35 * i
    cx_loop = x + 2.2 * r * math.cos(tilt)
    cy_loop = y + 2.2 * r * math.sin(tilt)
    loop_r = 1.35 * r
    ang1 = tilt + math.pi - 0.7
    ang2 = tilt - math.pi + 0.7
    p_start = (cx_loop + loop_r * math.cos(ang1), cy_loop + loop_r * math.sin(ang1))
    p_end = (cx_loop + loop_r * math.cos(ang2), cy_loop + loop_r * math.sin(ang2))
    p_mid = (cx_loop + loop_r * math.cos(tilt), cy_loop + loop_r * math.sin(tilt))
    return p_start, p_end, p_mid, loop_r


@dataclass
class Model:
    g: nx.MultiDiGraph
    k: int
    kmers: list
    trails: list
    spelled: list
    step_of: dict
    total: int
    headline: str
    pos: dict | None
    starts: set
    ends: set
    edges_df: pd.DataFrame
    nodes_df: pd.DataFrame
    notes: list = field(default_factory=list)
    contigs: list = field(default_factory=list)
    contigs_df: pd.DataFrame | None = None
    metrics: dict = field(default_factory=dict)
    spectrum: dict = field(default_factory=dict)
    cov_stats: dict = field(default_factory=dict)
    assembly_graph: nx.DiGraph | None = None
    records: list[SeqRecord] = field(default_factory=list)
    binning_summary: dict = field(default_factory=dict)
    gmm_stats: dict = field(default_factory=dict)
    ref_eval: dict | None = None
    both: bool = False


def analyze(
    kmers: list[str],
    notes: list[str] | None = None,
    ref_seq: str | None = None,
    both: bool = False,
) -> Model:
    """Build the full model. ``both`` must be the flag the k-mers were collected with."""
    g = build_graph(kmers)
    k = len(kmers[0])
    trails = trail_cover(g)
    copies = Counter(kmers)

    step_of, rows, gs = {}, [], 0
    for ti, trail in enumerate(trails, 1):
        for si, (u, v, key) in enumerate(trail, 1):
            gs += 1
            kmer = g.edges[u, v, key]["kmer"]
            step_of[(u, v, key)] = (ti, si, gs)
            rows.append(
                dict(
                    trail=ti,
                    step=si,
                    global_step=gs,
                    kmer=kmer,
                    source=u,
                    target=v,
                    copies=copies[kmer],
                )
            )
    edges_df = pd.DataFrame(rows)

    starts = {t[0][0] for t in trails}
    ends = {t[-1][1] for t in trails}
    node_rows = []
    for n in sorted(g):
        role = (
            "start & end"
            if n in starts and n in ends
            else "trail start"
            if n in starts
            else "trail end"
            if n in ends
            else ""
        )
        node_rows.append(
            dict(
                node=n,
                in_degree=g.in_degree(n),
                out_degree=g.out_degree(n),
                balance=g.out_degree(n) - g.in_degree(n),
                role=role,
            )
        )
    nodes_df = pd.DataFrame(node_rows)

    E, N = g.number_of_edges(), len(g)
    if len(trails) == 1:
        circuit = trails[0][0][0] == trails[0][-1][1] and not (nodes_df["balance"] != 0).any()
        kind = "Eulerian circuit" if circuit else "Eulerian path"
        headline = f"{kind}  ·  {E} edges  ·  {N} nodes"
    else:
        headline = (
            f"No single Eulerian path  ·  minimum cover = {len(trails)} trails"
            f"  ·  {E} edges  ·  {N} nodes"
        )

    # ---- Assembly engine: coverage, GMM error model, contigs, metrics ----
    spectrum = kmer_spectrum(kmers)
    cov_stats = coverage_summary(kmers)
    ag = build_assembly_graph(kmers)
    err_thresh, gmm_stats = fit_kmer_error_model(spectrum)
    ag, simp_notes = simplify_graph(ag, k, min_cov=err_thresh)
    # Both strands on yields every contig twice (N included: revcomp(N) = N), so the
    # explicit flag, not the data, decides whether the twins are merged.
    contigs = extract_contigs(ag, k, canonical=both)
    if both:
        simp_notes.append(
            "Both strands: reported one contig per strand pair (the smaller strand "
            "in string order is kept, which may be the reverse complement of the input)."
        )
    metrics = assembly_metrics(contigs)

    # ---- Scikit-learn: Metagenomic Contig Binning, PCA, Anomaly Detection ----
    contigs, binning_summary = bin_contigs(contigs)

    # ---- Biopython: Convert to SeqRecord objects with annotated features ----
    records = contigs_to_seqrecords(contigs)

    # ---- Biopython: Pairwise reference alignment evaluation ----
    ref_eval = (
        evaluate_assembly_against_reference(contigs, ref_seq) if ref_seq else None
    )

    contig_rows = [
        dict(
            id=c["id"],
            length=c["length"],
            edges=c["edges"],
            mean_cov=c["mean_coverage"],
            min_cov=c["min_coverage"],
            gc=c["gc_content"],
            mw_da=c.get("molecular_weight", 0.0),
            orfs=len(c.get("orfs", [])),
            bin=c.get("bin_id", 1),
            outlier="yes" if c.get("is_outlier") else "",
            circular="yes" if c.get("circular") else "",
        )
        for c in contigs
    ]
    contigs_df = pd.DataFrame(contig_rows) if contig_rows else pd.DataFrame()

    all_notes = list(notes or []) + simp_notes
    if gmm_stats.get("method") == "scikit-learn GaussianMixture" and err_thresh > 1:
        all_notes.append(
            f"GMM error model: cutoff={err_thresh} (error \u03bc={gmm_stats.get('error_mean_cov')}, "
            f"genomic \u03bc={gmm_stats.get('genomic_mean_cov')})"
        )
    if binning_summary.get("n_bins", 0) > 1:
        all_notes.append(
            f"Scikit-learn binning: separated contigs into {binning_summary['n_bins']} cluster bins."
        )

    return Model(
        g=g,
        k=k,
        kmers=kmers,
        trails=trails,
        spelled=[spell(t) for t in trails],
        step_of=step_of,
        total=gs,
        headline=headline,
        pos=compute_layout(g),
        starts=starts,
        ends=ends,
        edges_df=edges_df,
        nodes_df=nodes_df,
        notes=all_notes,
        contigs=contigs,
        contigs_df=contigs_df,
        metrics=metrics,
        spectrum=spectrum,
        cov_stats=cov_stats,
        assembly_graph=ag,
        records=records,
        binning_summary=binning_summary,
        gmm_stats=gmm_stats,
        ref_eval=ref_eval,
        both=both,
    )


def render(fig: Figure, m: Model, upto: int | None = None) -> None:
    """Draw the de Bruijn graph with its Eulerian trail state on a matplotlib Figure."""
    fig.clear()
    ax = fig.add_subplot(111)
    ax.set_facecolor(PITH)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")

    pos = m.pos
    if pos is None:
        ax.text(
            0.5,
            0.5,
            f"{m.headline}\n\n(Graph has {len(m.g)} nodes; drawing is disabled above {MAX_DRAW_NODES}.\n"
            "Use the tables below to inspect the Eulerian trails and assembly contigs.)",
            ha="center",
            va="center",
            color=INK,
            fontsize=12,
            transform=ax.transAxes,
        )
        return

    n_nodes = max(len(pos), 1)
    base_r = max(0.06, min(0.24, 1.4 / math.sqrt(n_nodes)))
    font_s = max(6.0, min(11.0, base_r * 55))
    edge_fs = max(5.0, min(9.5, font_s - 1.5))
    multi_trail = len(m.trails) > 1
    upto_step = m.total if upto is None else upto

    cur_edge_key = None
    if upto_step > 0:
        for k_tuple, (_, _, g_step) in m.step_of.items():
            if g_step == upto_step:
                cur_edge_key = k_tuple
                break

    # Group parallel edges
    by_pair = defaultdict(list)
    for u, v, key in m.g.edges(keys=True):
        by_pair[(u, v)].append(key)

    rad_shifts = {}
    for (u, v), keys in by_pair.items():
        if u == v:
            continue
        has_rev = (v, u) in by_pair
        n_par = len(keys)
        base = 0.28 if has_rev else 0.0
        step = 0.24
        for i, k_id in enumerate(keys):
            rad_shifts[(u, v, k_id)] = (
                base + i * step if has_rev else -(n_par - 1) * step / 2 + i * step
            )

    # Draw edges
    for (u, v), keys in by_pair.items():
        if u == v:
            x, y = pos[u]
            for i, k_id in enumerate(keys):
                p_start, p_end, p_mid, loop_r = _loop_geometry(x, y, base_r, i)
                ti, _, g_step = m.step_of.get((u, v, k_id), (1, 1, 999999))
                past = g_step <= upto_step
                active = (u, v, k_id) == cur_edge_key
                color = (
                    (TRAIL_COLORS[(ti - 1) % len(TRAIL_COLORS)] if multi_trail else EDGE)
                    if past
                    else FUTURE
                )
                lw = 2.6 if active else 1.8 if past else 1.0
                patch = FancyArrowPatch(
                    p_start,
                    p_end,
                    connectionstyle=f"arc3,rad=-1.3",
                    arrowstyle="-|>",
                    mutation_scale=12 if past else 9,
                    color=color,
                    lw=lw,
                    zorder=3 if past else 1,
                )
                ax.add_patch(patch)
                kmer = m.g.edges[u, v, k_id]["kmer"]
                lbl = f"{kmer} (#{g_step})" if past else kmer
                ax.text(
                    p_mid[0],
                    p_mid[1] + 0.04,
                    lbl,
                    ha="center",
                    va="bottom",
                    fontsize=edge_fs,
                    color=INK if past else FUTURE_TXT,
                    weight="bold" if active else "normal",
                    zorder=5,
                    bbox=dict(boxstyle="round,pad=0.15", facecolor=PITH, edgecolor="none", alpha=0.8),
                )
            continue

        x1, y1 = pos[u]
        x2, y2 = pos[v]
        for k_id in keys:
            rad = rad_shifts.get((u, v, k_id), 0.0)
            ti, _, g_step = m.step_of.get((u, v, k_id), (1, 1, 999999))
            past = g_step <= upto_step
            active = (u, v, k_id) == cur_edge_key
            color = (
                (TRAIL_COLORS[(ti - 1) % len(TRAIL_COLORS)] if multi_trail else EDGE)
                if past
                else FUTURE
            )
            lw = 2.8 if active else 1.8 if past else 1.0
            patch = FancyArrowPatch(
                (x1, y1),
                (x2, y2),
                connectionstyle=f"arc3,rad={rad}",
                arrowstyle="-|>",
                mutation_scale=13 if past else 9,
                color=color,
                lw=lw,
                shrinkA=base_r * 60,
                shrinkB=base_r * 60,
                zorder=3 if past else 1,
            )
            ax.add_patch(patch)
            verts = patch.get_path().vertices
            mx, my = (
                verts[len(verts) // 2]
                if len(verts)
                else ((x1 + x2) / 2, (y1 + y2) / 2)
            )
            dx, dy = -(y2 - y1), x2 - x1
            dist = math.hypot(dx, dy) or 1.0
            off = 0.05 * (1 if rad >= 0 else -1)
            lx, ly = mx + dx / dist * off, my + dy / dist * off
            kmer = m.g.edges[u, v, k_id]["kmer"]
            lbl = f"{kmer} (#{g_step})" if past else kmer
            ax.text(
                lx,
                ly,
                lbl,
                ha="center",
                va="center",
                fontsize=edge_fs,
                color=INK if past else FUTURE_TXT,
                weight="bold" if active else "normal",
                zorder=5,
                bbox=dict(boxstyle="round,pad=0.15", facecolor=PITH, edgecolor="none", alpha=0.8),
            )

    # Draw nodes
    for node, (x, y) in pos.items():
        is_start = node in m.starts
        is_end = node in m.ends
        fill = (
            LIME
            if (is_start and not is_end)
            else ORANGE
            if (is_end and not is_start)
            else LEMON
        )
        circ = Circle(
            (x, y),
            base_r,
            facecolor=fill,
            edgecolor=RIND,
            linewidth=1.8,
            zorder=4,
        )
        ax.add_patch(circ)
        ax.text(
            x,
            y,
            node,
            ha="center",
            va="center",
            fontsize=font_s,
            weight="bold",
            color=INK,
            zorder=6,
        )

    # Legend / Title
    elements = []
    if multi_trail:
        for i, t in enumerate(m.trails, 1):
            c = TRAIL_COLORS[(i - 1) % len(TRAIL_COLORS)]
            elements.append(
                Line2D([0], [0], color=c, lw=2.2, label=f"trail {i} ({len(t)} edges)")
            )
    else:
        elements.append(Line2D([0], [0], color=EDGE, lw=2.0, label="Eulerian path/circuit"))
    if any(node in m.starts for node in pos):
        elements.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=LIME,
                markeredgecolor=RIND,
                markersize=9,
                label="start",
            )
        )
    if any(node in m.ends for node in pos):
        elements.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=ORANGE,
                markeredgecolor=RIND,
                markersize=9,
                label="end",
            )
        )
    elements.append(Line2D([0], [0], color=FUTURE, lw=1.2, label="future edge"))

    fig.legend(
        handles=elements,
        loc="upper left",
        bbox_to_anchor=(0.02, 0.98),
        frameon=True,
        facecolor=PITH,
        edgecolor=PANEL,
        fontsize=8.5,
    )
    fig.suptitle(m.headline, fontsize=12, fontweight="bold", color=INK, y=0.96)
    note = " · ".join(m.notes)
    if note:
        fig.text(
            0.5,
            0.058,
            note.strip(" |"),
            ha="center",
            va="bottom",
            fontsize=8,
            color=FUTURE_TXT,
        )
