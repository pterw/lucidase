"""
Assembly Engine: De Bruijn Graph Assembly Algorithms
===================================================
Constructs collapsed assembly graphs, performs graph simplification (tip removal,
low-coverage pruning), extracts maximal non-branching contigs, and computes standard
assembly quality metrics (N50, L50, GC content, etc.). Outputs GFA 1.0 format.
"""

from __future__ import annotations

import statistics
from collections import Counter

import networkx as nx

from bio_engine import _gc_content, find_orfs, revcomp, safe_mw


def build_assembly_graph(kmers: list[str]) -> nx.DiGraph:
    """Build a collapsed de Bruijn graph: one edge per unique k-mer with coverage.

    Unlike ``build_graph`` (which creates parallel edges for repeated k-mers to
    support Eulerian trail enumeration), this builds a simple DiGraph suited to
    assembly: each unique k-mer is a single edge whose ``coverage`` attribute
    records how many times it appeared in the input."""
    counts = Counter(kmers)
    ag = nx.DiGraph()
    for km, cov in counts.items():
        ag.add_edge(km[:-1], km[1:], kmer=km, coverage=cov)
    return ag


def _remove_tips(ag: nx.DiGraph, k: int) -> int:
    """Remove short dead-end paths (tips) caused by sequencing errors.

    A tip is a non-branching path shorter than ``2 * k`` edges ending at a
    dead-end node.  Such paths typically arise from base-call errors near
    the ends of reads.  Returns the number of nodes removed.

    Known limitation (teaching tool): the test is on path length only and is
    coverage-blind, so a genuine read end next to a branch or repeat can be
    clipped.  Each pass rescans all nodes, which is quadratic in the worst case."""
    max_tip_len = 2 * k
    removed = 0
    changed = True
    while changed:
        changed = False
        for node in list(ag.nodes()):
            if node not in ag:
                continue
            # Forward tip: dead end (out_degree == 0)
            if ag.out_degree(node) == 0 and ag.in_degree(node) >= 1:
                path = [node]
                cur = node
                is_tip = False
                for _ in range(max_tip_len):
                    preds = list(ag.predecessors(cur))
                    if len(preds) != 1:
                        break
                    pred = preds[0]
                    if ag.out_degree(pred) > 1:
                        is_tip = True
                        break
                    path.append(pred)
                    cur = pred
                if is_tip and len(path) < max_tip_len:
                    for n in path:
                        ag.remove_node(n)
                    removed += len(path)
                    changed = True
                    continue
            # Backward tip: source (in_degree == 0)
            if node not in ag:
                continue
            if ag.in_degree(node) == 0 and ag.out_degree(node) >= 1:
                path = [node]
                cur = node
                is_tip = False
                for _ in range(max_tip_len):
                    succs = list(ag.successors(cur))
                    if len(succs) != 1:
                        break
                    succ = succs[0]
                    if ag.in_degree(succ) > 1:
                        is_tip = True
                        break
                    path.append(succ)
                    cur = succ
                if is_tip and len(path) < max_tip_len:
                    for n in path:
                        ag.remove_node(n)
                    removed += len(path)
                    changed = True
    return removed


def _remove_low_coverage(ag: nx.DiGraph, min_cov: int) -> int:
    """Remove edges whose coverage is below *min_cov*.  Isolated nodes left
    behind are also pruned.  Returns the number of edges removed."""
    to_remove = [(u, v) for u, v, d in ag.edges(data=True) if d.get("coverage", 1) < min_cov]
    ag.remove_edges_from(to_remove)
    ag.remove_nodes_from(list(nx.isolates(ag)))
    return len(to_remove)


def simplify_graph(ag: nx.DiGraph, k: int, min_cov: int = 0) -> tuple[nx.DiGraph, list[str]]:
    """Apply graph simplification: low-coverage pruning then tip removal.

    Returns ``(simplified_graph_copy, notes)``."""
    ag = ag.copy()
    notes: list[str] = []
    if min_cov > 1:
        n = _remove_low_coverage(ag, min_cov)
        if n:
            notes.append(f"Removed {n} low-coverage edge(s) (coverage < {min_cov}).")
    n = _remove_tips(ag, k)
    if n:
        notes.append(f"Clipped {n} tip node(s) (dead-end paths < {2 * k} edges).")
    return ag, notes


def _least_rotation(s: str) -> str:
    """Lexicographically least rotation of *s* (Booth's algorithm, O(n))."""
    n = len(s)
    if n < 2:
        return s
    ss = s + s
    f = [-1] * (2 * n)
    least = 0
    for j in range(1, 2 * n):
        sj = ss[j]
        i = f[j - least - 1]
        while i != -1 and sj != ss[least + i + 1]:
            if sj < ss[least + i + 1]:
                least = j - i - 1
            i = f[i]
        if sj != ss[least + i + 1]:
            if sj < ss[least]:
                least = j
            f[j - least] = -1
        else:
            f[j - least] = i + 1
    return ss[least : least + n]


def _strand_key(contig: dict) -> str:
    """Strand-independent identity of a contig: the smaller of its sequence and
    reverse complement. Circular contigs are compared up to rotation."""
    seq = contig["sequence"]
    if contig.get("circular"):
        core = seq[: contig["edges"]]  # the cycle without its repeated k-1 tail
        return min(_least_rotation(core), _least_rotation(revcomp(core)))
    return min(seq, revcomp(seq))


def _drop_reverse_complement_twins(contigs: list[dict]) -> list[dict]:
    """Keep one contig per strand pair: the lexicographically smaller strand.
    A contig whose twin is absent (for example clipped) is kept as it is."""
    best: dict[str, dict] = {}
    for c in contigs:
        key = (c.get("circular", False), _strand_key(c))
        if key not in best or c["sequence"] < best[key]["sequence"]:
            best[key] = c
    kept = {id(c) for c in best.values()}
    return [c for c in contigs if id(c) in kept]


def extract_contigs(ag: nx.DiGraph, k: int, canonical: bool = False) -> list[dict]:
    """Extract contigs (maximal non-branching paths) from the assembly graph.

    Each contig follows a maximal chain of nodes where every internal node has
    in-degree = out-degree = 1. Isolated cycles are also reported.

    With ``canonical=True`` (use it when the graph holds both strands, DNA only)
    each contig and its reverse complement count once: the lexicographically
    smaller strand is kept, so lengths and metrics are not doubled.

    Known limitation (teaching tool): the graph is collapsed, so repeats longer
    than k merge into one path and linear reads through them are lost; a pure
    repeat such as ``AAAAAAAAAA`` is reported as a short circular contig."""

    def is_internal(n: str) -> bool:
        return ag.in_degree(n) == 1 and ag.out_degree(n) == 1

    used_edges: set[tuple[str, str]] = set()
    contigs: list[dict] = []

    # Start from branching / boundary nodes
    starts = sorted(n for n in ag if not is_internal(n) and ag.out_degree(n) > 0)
    for start in starts:
        for _, target in ag.out_edges(start):
            if (start, target) in used_edges:
                continue
            path = [(start, target)]
            used_edges.add((start, target))
            cur = target
            while is_internal(cur):
                succs = list(ag.successors(cur))
                if not succs or (cur, succs[0]) in used_edges:
                    break
                nxt = succs[0]
                path.append((cur, nxt))
                used_edges.add((cur, nxt))
                cur = nxt
            seq = path[0][0] + "".join(tgt[-1] for _, tgt in path)
            coverages = [ag.edges[u, v].get("coverage", 1) for u, v in path]
            mean_cov = statistics.mean(coverages) if coverages else 0
            contigs.append({
                "id": 0,
                "sequence": seq,
                "length": len(seq),
                "edges": len(path),
                "mean_coverage": round(mean_cov, 1),
                "min_coverage": min(coverages) if coverages else 0,
                "gc_content": round(_gc_content(seq), 4),
                "molecular_weight": safe_mw(seq),
                "orfs": find_orfs(seq, min_aa_len=10),
                "circular": False,
            })

    # Remaining edges belong to isolated cycles (every node is internal)
    remaining = set(ag.edges()) - used_edges
    if remaining:
        temp = nx.DiGraph()
        for u, v in remaining:
            temp.add_edge(u, v, **ag.edges[u, v])
        for comp in nx.weakly_connected_components(temp):
            sub = temp.subgraph(comp)
            start_node = min(comp)
            cur, visited, cycle = start_node, set(), []
            while True:
                nxt_list = [w for w in sub.successors(cur) if (cur, w) not in visited]
                if not nxt_list:
                    break
                nxt = nxt_list[0]
                cycle.append((cur, nxt))
                visited.add((cur, nxt))
                cur = nxt
                if cur == start_node:
                    break
            if cycle:
                seq = cycle[0][0] + "".join(tgt[-1] for _, tgt in cycle)
                coverages = [sub.edges[u, v].get("coverage", 1) for u, v in cycle]
                mean_cov = statistics.mean(coverages) if coverages else 0
                contigs.append({
                    "id": 0,
                    "sequence": seq,
                    "length": len(seq),
                    "edges": len(cycle),
                    "mean_coverage": round(mean_cov, 1),
                    "min_coverage": min(coverages) if coverages else 0,
                    "gc_content": round(_gc_content(seq), 4),
                    "molecular_weight": safe_mw(seq),
                    "orfs": find_orfs(seq, min_aa_len=10),
                    "circular": True,
                })

    if canonical:
        contigs = _drop_reverse_complement_twins(contigs)
    contigs.sort(key=lambda c: -c["length"])
    for i, c in enumerate(contigs, 1):
        c["id"] = i
    return contigs


def assembly_metrics(contigs: list[dict]) -> dict:
    """Compute standard assembly quality metrics (N50, L50, GC%, etc.)."""
    if not contigs:
        return {"num_contigs": 0, "total_length": 0}
    lengths = sorted((c["length"] for c in contigs), reverse=True)
    total = sum(lengths)
    cumsum, n50, l50 = 0, 0, 0
    for i, ln in enumerate(lengths, 1):
        cumsum += ln
        if cumsum >= total / 2 and n50 == 0:
            n50, l50 = ln, i
    cumsum, n90 = 0, 0
    for ln in lengths:
        cumsum += ln
        if cumsum >= total * 0.9 and n90 == 0:
            n90 = ln
    gc_total = sum(c["gc_content"] * c["length"] for c in contigs)
    coverages = [c["mean_coverage"] for c in contigs if c["mean_coverage"] > 0]
    return {
        "num_contigs": len(contigs),
        "total_length": total,
        "longest": lengths[0],
        "shortest": lengths[-1],
        "mean_length": round(total / len(contigs), 1),
        "n50": n50,
        "l50": l50,
        "n90": n90,
        "gc_content": round(gc_total / total if total else 0, 4),
        "mean_coverage": round(statistics.mean(coverages), 1) if coverages else 0,
    }


def _flip(orient: str) -> str:
    return "-" if orient == "+" else "+"


def gfa_links(contigs: list[dict], k: int, both: bool = False) -> list[tuple[int, str, int, str]]:
    """Overlap links ``(from_id, from_orient, to_id, to_orient)`` between contigs.

    A link joins two oriented contigs when the last k-1 bases of the first equal the
    first k-1 of the second. With ``both`` (both strands were assembled, so each kept
    contig stands for its reverse complement too) either strand of every contig can
    take part, and ``-`` marks the reverse complement. A link and its mirror image
    (``b- -> a-`` for ``a+ -> b+``) are the same GFA edge, so only one is written."""
    orients = ("+", "-") if both else ("+",)
    seqs = {(c["id"], o): c["sequence"] if o == "+" else revcomp(c["sequence"])
            for c in contigs for o in orients}
    circular = {c["id"]: bool(c.get("circular")) for c in contigs}
    n = k - 1
    by_prefix: dict[str, list[tuple[int, str]]] = {}
    for key, seq in seqs.items():
        by_prefix.setdefault(seq[:n], []).append(key)
    links: list[tuple[int, str, int, str]] = []
    seen: set[tuple[int, str, int, str]] = set()
    for (a, ao), seq in seqs.items():
        for b, bo in by_prefix.get(seq[-n:], []):
            if (a, ao) == (b, bo) and not circular[a]:
                continue
            mirror = (b, _flip(bo), a, _flip(ao))
            if mirror in seen:
                continue
            link = (a, ao, b, bo)
            seen.add(link)
            links.append(link)
    return links


def write_gfa(contigs: list[dict], path: str, k: int, both: bool = False) -> None:
    """Write assembly in GFA 1.0 format (Bandage, gfatools, vg compatible).

    Pass ``both=True`` when the contigs are canonical (one per strand pair) so the
    links may use either strand of a contig."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("H\tVN:Z:1.0\n")
        for c in contigs:
            dp = int(round(c["mean_coverage"]))
            f.write(
                f"S\tctg{c['id']}\t{c['sequence']}\t"
                f"LN:i:{c['length']}\tRC:i:{c['edges']}\tDP:i:{dp}\n"
            )
        overlap = k - 1
        for a, ao, b, bo in gfa_links(contigs, k, both):
            f.write(f"L\tctg{a}\t{ao}\tctg{b}\t{bo}\t{overlap}M\n")
