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

from bio_engine import _gc_content, find_orfs, safe_mw


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
    the ends of reads.  Returns the number of nodes removed."""
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


def extract_contigs(ag: nx.DiGraph, k: int) -> list[dict]:
    """Extract contigs (maximal non-branching paths) from the assembly graph.

    Each contig follows a maximal chain of nodes where every internal node has
    in-degree = out-degree = 1. Isolated cycles are also reported."""

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


def write_gfa(contigs: list[dict], path: str, k: int) -> None:
    """Write assembly in GFA 1.0 format (Bandage, gfatools, vg compatible)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("H\tVN:Z:1.0\n")
        for c in contigs:
            dp = int(round(c["mean_coverage"]))
            f.write(
                f"S\tctg{c['id']}\t{c['sequence']}\t"
                f"LN:i:{c['length']}\tRC:i:{c['edges']}\tDP:i:{dp}\n"
            )
        suffix_map: dict[str, list[int]] = {}
        for c in contigs:
            sfx = c["sequence"][-(k - 1) :]
            suffix_map.setdefault(sfx, []).append(c["id"])
        overlap = k - 1
        for c in contigs:
            pfx = c["sequence"][: k - 1]
            for src_id in suffix_map.get(pfx, []):
                if src_id != c["id"] or c.get("circular"):
                    f.write(f"L\tctg{src_id}\t+\tctg{c['id']}\t+\t{overlap}M\n")
