#!/usr/bin/env python3
"""
De Bruijn Explorer: Graph Algorithms, Biopython Integration & Machine Learning
=============================================================================
A computational biology tool for de Bruijn graph sequence analysis, assembly,
and metagenomics.

Quickstart:
    python debruijn_explorer.py              # Launch interactive desktop GUI
    python debruijn_explorer.py --selftest   # Run full 400-round + ML/Bio validation
    python debruijn_explorer.py --headless --seq ACGTGCAATG CAATGCCGTA -k 5 --metrics --binning

Architecture:
    bio_engine.py  : Biopython sequence utilities, ORF finding, GenBank/FASTA I/O, Bio.Align
    ml_engine.py   : Scikit-learn GMM error modeling, TNF profiles, KMeans binning, IsolationForest
    assembly.py    : Collapsed assembly graph, tip/bubble simplification, contig extraction, GFA 1.0
    graph_core.py  : Directed multigraphs, Hierholzer Eulerian trail covers, layout, matplotlib rendering
    gui.py         : Tkinter desktop interface with multi-tab inspection and animated walk
"""

from __future__ import annotations

import argparse
import importlib
import io
import os
import random
import sys
import unittest
from collections import Counter

# Configure UTF-8 stdout / stderr on Windows consoles to prevent cp1252 charmap errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure Matplotlib config directory is inside workspace to avoid permission errors
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".matplotlib_cache"))

# ---------------------------------------------------------------------------
# Dependency Verification
# ---------------------------------------------------------------------------
_REQUIRED = [
    ("networkx", "networkx"),
    ("matplotlib", "matplotlib"),
    ("pandas", "pandas"),
    ("Bio", "biopython"),
    ("sklearn", "scikit-learn"),
    ("numpy", "numpy"),
    ("scipy", "scipy"),
]


def _check_dependencies() -> None:
    missing = []
    for module, pip_name in _REQUIRED:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(pip_name)
    if missing:
        sys.exit(
            "De Bruijn Explorer needs a few packages that are not installed:\n"
            f"    {', '.join(missing)}\n\nInstall them with:\n"
            f"    {sys.executable} -m pip install {' '.join(missing)}\n"
        )


_check_dependencies()

# ---------------------------------------------------------------------------
# Re-exports from Modular Engines
# ---------------------------------------------------------------------------
from assembly import (  # noqa: E402
    assembly_metrics,
    build_assembly_graph,
    extract_contigs,
    simplify_graph,
    write_gfa,
)
from bio_engine import (  # noqa: E402
    _gc_content,
    contigs_to_seqrecords,
    evaluate_assembly_against_reference,
    find_orfs,
    load_sequences_as_fasta,
    parse_records,
    revcomp,
    safe_mw,
    write_contigs_fasta,
    write_contigs_genbank,
)
from graph_core import (  # noqa: E402
    EDGE,
    FUTURE,
    FUTURE_TXT,
    INK,
    LEMON,
    LIME,
    MAX_DRAW_NODES,
    MAX_KMERS,
    MAX_TABLE_ROWS,
    ORANGE,
    PANEL,
    PITH,
    RIND,
    TRAIL_COLORS,
    Model,
    analyze,
    build_graph,
    collect_kmers,
    layout,
    render,
    trail_cover,
)
from gui import (  # noqa: E402
    EXAMPLES,
    ExplorerApp,
    run_gui,
)
from genomic_parser import (  # noqa: E402
    GenomicParser,
    SampleQC,
    VariantCall,
)
from ml_engine import (  # noqa: E402
    bin_contigs,
    coverage_summary,
    estimate_error_threshold,
    extract_kmer_features,
    fit_kmer_error_model,
    kmer_spectrum,
)
from variant_annotator import (  # noqa: E402
    ACMG_SF_GENES,
    AnnotationRecord,
    VariantAnnotator,
)


# ===========================================================================
# High-Level Programmatic API
# ===========================================================================
def assemble(
    text: str,
    k: int = 31,
    mode: str = "seq",
    both_strands: bool = False,
    unique: bool = False,
    ref_seq: str | None = None,
    n_clusters: int | None = None,
) -> dict:
    """High-level computational biology assembly API for pipeline integration.

    Parameters
    ----------
    text : str
        Sequence data (raw sequence, FASTA, or space-separated k-mers).
    k : int
        K-mer length (default 31, typical for bacterial genomes).
    mode : str
        ``'seq'`` for sequences / FASTA, ``'kmers'`` for pre-computed k-mers.
    both_strands : bool
        Add reverse complements (standard for double-stranded DNA assembly).
    unique : bool
        Deduplicate k-mers (loses coverage information — not recommended).
    ref_seq : str | None
        Optional reference sequence to evaluate assembly against via Bio.Align.
    n_clusters : int | None
        Optional fixed cluster count for scikit-learn metagenomic binning.

    Returns
    -------
    dict
        ``contigs`` — list of contig dicts (sequence, coverage, gc, MW, ORFs, bin_id, PCA).
        ``records`` — list of Biopython SeqRecord objects with CDS feature annotations.
        ``metrics`` — assembly quality metrics (N50, L50, total length, etc.).
        ``binning`` — scikit-learn metagenomic binning summary (PCA, KMeans, outliers).
        ``gmm_error_model`` — scikit-learn Gaussian Mixture Model error parameters.
        ``spectrum`` — k-mer coverage histogram.
        ``coverage_stats`` — coverage distribution summary.
        ``reference_evaluation`` — Bio.Align comparison results (if ref_seq provided).
        ``model`` — full ``Model`` object for advanced use.

    Example
    -------
    >>> result = assemble(">r1\\nACGTGCAATG\\n>r2\\nCAATGCCGTA", k=5)
    >>> print(f"Contigs: {len(result['contigs'])}, N50: {result['metrics']['n50']}")
    """
    kmers, notes = collect_kmers(text, mode, k, both_strands, unique)
    m = analyze(kmers, notes, ref_seq=ref_seq)
    return {
        "contigs": m.contigs,
        "records": m.records,
        "metrics": m.metrics,
        "binning": m.binning_summary,
        "gmm_error_model": m.gmm_stats,
        "spectrum": m.spectrum,
        "coverage_stats": m.cov_stats,
        "reference_evaluation": m.ref_eval,
        "model": m,
    }


# ===========================================================================
# Headless CLI Execution
# ===========================================================================
def run_headless(args) -> int:
    """Execute command-line assembly, graph analysis, and artifact export."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    if getattr(args, "genome", None):
        try:
            variants, qc = GenomicParser.parse_file(args.genome)
            annotator = VariantAnnotator()
            records = annotator.annotate_genome(variants)
            summary = annotator.summarize_annotations(records)
        except Exception as err:
            print(f"Error parsing genomic file: {err}", file=sys.stderr)
            return 1

        print("=" * 60)
        print(f"GENOMIC SAMPLE QUALITY CONTROL ({qc.format_name.upper()})")
        print("=" * 60)
        print(f"  Genome Assembly:........ {qc.build}")
        print(f"  Total Markers:.......... {qc.total_snps:,} SNPs")
        print(f"  Call Rate:.............. {qc.call_rate*100:.2f}% ({qc.called_snps:,} called, {qc.nocall_snps:,} missing)")
        print(f"  Heterozygosity Rate:.... {qc.heterozygosity_rate*100:.2f}%")
        print(f"  Inferred Biological Sex: {qc.inferred_sex}")

        print("\n" + "=" * 60)
        print(f"CLINVAR & PROTEOMIC ANNOTATIONS ({len(records)} findings)")
        print("=" * 60)
        print(f"  Pathogenic Variants:.... {summary['pathogenic_count']}")
        print(f"  Carrier Conditions:..... {summary['carrier_count']}")
        print(f"  Pharmacogenomics:....... {summary['pgx_count']} drug response alerts")
        print(f"  Elevated Risk Factors:.. {summary['risk_factor_count']}")
        print(f"  ACMG SF v3.2 Actionable: {summary['acmg_actionable_findings']}\n")

        for r in records:
            stars_str = "*" * r.review_stars if r.review_stars else "-"
            print(f"- {r.rsid:<12s} [{r.gene:<8s}] Genotype: {r.genotype:<4s} | {r.category} ({stars_str})")
            print(f"  Significance: {r.clinical_significance}")
            print(f"  Condition:    {r.phenotype}")
            if r.drug_response:
                print(f"  CPIC Drug:    {r.drug_response}")
            if r.hpa_tissues:
                tissues_str = ", ".join(f"{t}: {l}" for t, l in list(r.hpa_tissues.items())[:3])
                print(f"  HPA Tissues:  {tissues_str}")
            print()

        if getattr(args, "clinical_report", None):
            if args.clinical_report.endswith(".csv"):
                import csv
                with open(args.clinical_report, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["rsid", "gene", "genotype", "category", "stars", "significance", "phenotype", "drug_response"])
                    for r in records:
                        writer.writerow([r.rsid, r.gene, r.genotype, r.category, r.review_stars, r.clinical_significance, r.phenotype, r.drug_response])
            else:
                with open(args.clinical_report, "w", encoding="utf-8") as f:
                    f.write(f"# Clinical Genomic Report: {os.path.basename(args.genome)}\n\n")
                    f.write(f"- Format: `{qc.format_name.upper()}` ({qc.build})\n")
                    f.write(f"- Call Rate: `{qc.call_rate*100:.2f}%`\n")
                    f.write(f"- Inferred Sex: `{qc.inferred_sex}`\n\n")
                    f.write(f"| rsID | Gene | Genotype | Category | Stars | Significance | Phenotype |\n")
                    f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
                    for r in records:
                        s_str = "★" * r.review_stars if r.review_stars else "—"
                        f.write(f"| {r.rsid} | {r.gene} | {r.genotype} | {r.category} | {s_str} | {r.clinical_significance} | {r.phenotype} |\n")
            print(f"Wrote clinical report to {args.clinical_report}")
        return 0

    try:
        if args.fasta:
            text, note = load_sequences_as_fasta(args.fasta)
            print(note)
            mode = "seq"
        elif args.kmers:
            text, mode = " ".join(args.kmers), "kmers"
        else:
            text, mode = "\n".join(args.seq or ["LEMONLEMONADE"]), "seq"

        ref_seq = None
        if args.ref:
            if os.path.exists(args.ref):
                r_text, _ = load_sequences_as_fasta(args.ref)
                ref_seq = "".join(parse_records(r_text))
            else:
                ref_seq = args.ref.strip().upper()

        kmers, notes = collect_kmers(text, mode, args.k, args.both_strands, args.unique)
        m = analyze(kmers, notes, ref_seq=ref_seq)
    except (ValueError, OSError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(m.headline.replace("  ·  ", " | "))
    for n in m.notes:
        print("Note:", n)
    for i, (t, s) in enumerate(zip(m.trails, m.spelled), 1):
        print(f"trail {i} ({len(t)} edges): {s}")
    if m.pos is None:
        print("Graph too large to draw; skipping figure.", file=sys.stderr)
    if args.save:
        fig = Figure(figsize=(11, 7.5))
        FigureCanvasAgg(fig)
        render(fig, m)
        fig.savefig(args.save, dpi=200, facecolor=fig.get_facecolor())
        print(f"Saved figure to {args.save}")
    if args.csv:
        m.edges_df.to_csv(f"{args.csv}_edges.csv", index=False)
        m.nodes_df.to_csv(f"{args.csv}_nodes.csv", index=False)
        if m.contigs_df is not None and not m.contigs_df.empty:
            m.contigs_df.to_csv(f"{args.csv}_contigs_ml.csv", index=False)
        print(f"Wrote {args.csv}_edges.csv, _nodes.csv, and _contigs_ml.csv")
    if args.export_bins:
        if m.contigs_df is not None and not m.contigs_df.empty:
            m.contigs_df.to_csv(args.export_bins, index=False)
            print(f"Wrote contig ML bins to {args.export_bins}")

    # ---- Assembly & ML outputs ----
    if args.metrics:
        print("\n--- Assembly Metrics ---")
        for key, val in m.metrics.items():
            print(f"  {key.replace('_', ' ').title():.<24s} {val}")
        print("\n--- K-mer Coverage ---")
        for key, val in m.cov_stats.items():
            print(f"  {key.replace('_', ' ').title():.<24s} {val}")
        print(f"\n--- Contigs ({len(m.contigs)}) ---")
        for c in m.contigs[:20]:
            tag = " [circular]" if c.get("circular") else ""
            outlier_tag = " [OUTLIER]" if c.get("is_outlier") else ""
            print(
                f"  ctg{c['id']}  len={c['length']}  cov={c['mean_coverage']}\u00d7  "
                f"gc={c['gc_content']:.3f}  bin={c.get('bin_id', 1)}{tag}{outlier_tag}"
            )
        if len(m.contigs) > 20:
            print(f"  ... ({len(m.contigs) - 20} more)")

    if args.binning:
        print("\n--- Scikit-Learn Contig Binning & PCA ---")
        bs = m.binning_summary
        print(f"  Clusters (KMeans Bins):... {bs.get('n_bins', 1)}")
        if bs.get("pca_variance_ratio"):
            vars_str = ", ".join(
                f"PC{i+1}: {v*100:.1f}%" for i, v in enumerate(bs["pca_variance_ratio"])
            )
            print(f"  PCA Explained Variance:... {vars_str}")
        print(f"  Potential Outliers:....... {bs.get('outlier_count', 0)}")
        for b_name, b_data in bs.get("clusters", {}).items():
            print(
                f"  {b_name}: {b_data.get('contigs')} contigs, {b_data.get('total_bp'):,} bp, "
                f"mean GC={b_data.get('mean_gc')}, mean cov={b_data.get('mean_cov')}\u00d7"
            )

        print("\n--- K-mer Error Model (Scikit-Learn GMM) ---")
        gs = m.gmm_stats
        print(f"  Method:................... {gs.get('method', 'None')}")
        print(f"  Bayes Decision Cutoff:.... {gs.get('cutoff', 1)}\u00d7")
        if "error_mean_cov" in gs:
            print(f"  Fitted Error Mean Cov:.... {gs.get('error_mean_cov')}\u00d7")
            print(f"  Fitted Genomic Mean Cov:.. {gs.get('genomic_mean_cov')}\u00d7")

    if m.ref_eval:
        print("\n--- Reference Alignment Fidelity (Bio.Align) ---")
        print(f"  Reference Length:......... {m.ref_eval.get('reference_length'):,} bp")
        print(
            f"  Genome Fraction Covered:.. {m.ref_eval.get('genome_fraction', 0)*100:.2f}%"
        )
        print(
            f"  Mean Alignment Identity:.. {m.ref_eval.get('mean_identity', 0)*100:.2f}%"
        )
        print(f"  Aligned Contigs:.......... {m.ref_eval.get('aligned_contigs')}")

    if args.gfa:
        write_gfa(m.contigs, args.gfa, m.k)
        print(f"Wrote GFA to {args.gfa} ({len(m.contigs)} contigs)")
    if args.contigs:
        write_contigs_fasta(m.contigs, args.contigs)
        print(f"Wrote {len(m.contigs)} contigs to {args.contigs}")
    if args.genbank:
        write_contigs_genbank(m.contigs, args.genbank)
        print(f"Wrote {len(m.contigs)} contigs with annotated ORFs to {args.genbank}")
    return 0


# ===========================================================================
# Correctness Self-Tests
# ===========================================================================
def selftest(rounds: int = 50) -> int:
    """Property checks on random inputs and advanced Biopython / Scikit-learn validation."""
    import networkx as nx
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    rng = random.Random(2026)

    def covered_once(m):
        seen = [e for t in m.trails for e in t]
        return len(seen) == len(set(seen)) == m.g.number_of_edges()

    def contiguous(m):
        return all(t[i][1] == t[i + 1][0] for t in m.trails for i in range(len(t) - 1))

    def expected_trails(g):
        total = 0
        for comp in nx.weakly_connected_components(g):
            surplus = sum(max(g.out_degree(n) - g.in_degree(n), 0) for n in comp)
            total += max(surplus, 1)
        return total

    checks = 0
    for _ in range(rounds):
        k = rng.randint(2, 6)
        seq = "".join(rng.choice("ACGT") for _ in range(rng.randint(k, 40)))
        # 1. Linear sequence has one Eulerian path spelling exactly its k-mers
        km, _ = collect_kmers(seq, "seq", k, False, False)
        m = analyze(km)
        assert len(m.trails) == 1 and covered_once(m) and contiguous(m), seq
        out = m.spelled[0]
        assert len(out) == len(seq) and Counter(
            out[i : i + k] for i in range(len(out) - k + 1)
        ) == Counter(km), seq

        # 2. Both strands / sets / multiple reads: trail count is the proven minimum
        for both, unique in ((True, False), (False, True), (True, True)):
            km2, _ = collect_kmers(seq, "seq", k, both, unique)
            m2 = analyze(km2)
            assert covered_once(m2) and contiguous(m2), (seq, both, unique)
            assert len(m2.trails) == expected_trails(m2.g), (seq, both, unique)
        reads = [seq, "".join(rng.choice("ACGT") for _ in range(rng.randint(k, 20)))]
        km3, _ = collect_kmers("\n".join(reads), "seq", k, False, False)
        m3 = analyze(km3)
        assert (
            covered_once(m3)
            and contiguous(m3)
            and len(m3.trails) == expected_trails(m3.g)
        )
        checks += 4

    # 3. Rendering never crashes, including self-loops, multi-trail and step states
    for ex in EXAMPLES.values():
        km, _ = collect_kmers(
            ex["text"], ex["mode"], ex["k"], ex["both"], ex["unique"]
        )
        m = analyze(km)
        fig = Figure()
        FigureCanvasAgg(fig)
        for step in (0, max(1, m.total // 2), m.total):
            render(fig, m, step)
        checks += 1

    # 4. Biopython and Scikit-learn unit checks
    test_dna = "ATGCGATCGATCGTAA"
    assert 0.0 < _gc_content(test_dna) < 1.0
    assert safe_mw(test_dna) > 1000.0

    # BioPython ORF finder
    gene = "ATGAAACCCGGGTTTTAA"
    orfs = find_orfs(gene, min_aa_len=3)
    assert len(orfs) >= 1
    assert orfs[0]["protein"] == "MKPGF"
    checks += 1

    # Scikit-learn GMM error modeling
    spec_with_errors = {
        1: 800,
        2: 60,
        3: 10,
        18: 40,
        19: 90,
        20: 150,
        21: 80,
        22: 30,
    }
    cutoff, gmm_stats = fit_kmer_error_model(spec_with_errors)
    assert cutoff >= 2
    assert gmm_stats.get("converged") is True
    checks += 1

    # Scikit-learn Contig Binning & PCA
    dummy_contigs = [
        {
            "id": 1,
            "sequence": "GCGCGCGCGCGCGCGCGCGC",
            "length": 20,
            "gc_content": 1.0,
            "mean_coverage": 25.0,
        },
        {
            "id": 2,
            "sequence": "GCGCGCGCGCGCCCGGGGGG",
            "length": 20,
            "gc_content": 1.0,
            "mean_coverage": 24.0,
        },
        {
            "id": 3,
            "sequence": "ATATATATATATATATATAT",
            "length": 20,
            "gc_content": 0.0,
            "mean_coverage": 10.0,
        },
        {
            "id": 4,
            "sequence": "ATATATATATATAAATTTTT",
            "length": 20,
            "gc_content": 0.0,
            "mean_coverage": 9.5,
        },
    ]
    binned, b_summary = bin_contigs(dummy_contigs)
    assert b_summary["n_bins"] == 2
    assert binned[0]["pca_x"] is not None
    checks += 1

    # BioPython SeqRecord and GenBank writer
    recs = contigs_to_seqrecords(binned)
    assert len(recs) == 4
    assert recs[0].id == "ctg1"
    checks += 1

    # Bio.Align reference evaluation
    ref_seq = "ACGTGCAATGCAATGCCGTACCGTAACGTG"
    eval_ctgs = [
        {"id": 1, "sequence": "ACGTGCAATGCAATG"},
        {"id": 2, "sequence": "CAATGCCGTACCGTAACGTG"},
    ]
    ref_res = evaluate_assembly_against_reference(eval_ctgs, ref_seq)
    assert ref_res["genome_fraction"] == 1.0
    assert ref_res["mean_identity"] == 1.0
    checks += 1

    # High-level assemble() API
    asm_res = assemble(
        ">r1\nACGTGCAATG\n>r2\nCAATGCCGTA", k=5, ref_seq="ACGTGCAATGCCGTA"
    )
    assert len(asm_res["contigs"]) >= 1
    assert len(asm_res["records"]) >= 1
    assert "binning" in asm_res
    checks += 1

    # 5. Genomic Parser, QC, ClinVar, HPA, and PGx unit checks
    from test_genomic_pipeline import TestGenomicPipeline

    suite = unittest.TestLoader().loadTestsFromTestCase(TestGenomicPipeline)
    runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0)
    result = runner.run(suite)
    assert result.wasSuccessful(), f"Genomic pipeline tests failed: {result.errors} {result.failures}"
    checks += result.testsRun

    print(
        f"selftest OK: {checks} checks over {rounds} random sequences + "
        f"{len(EXAMPLES)} examples + ML/Bio + Genomic Pipeline tests"
    )
    return 0


# ===========================================================================
# Argument Parser & CLI Entry Point
# ===========================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="De Bruijn graph + Eulerian trail explorer (GUI by default)."
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="no GUI: print results / save a figure",
    )
    p.add_argument(
        "--selftest", action="store_true", help="run correctness checks and exit"
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--seq", nargs="+", help="one or more sequences")
    src.add_argument("--kmers", nargs="+", help="explicit k-mers")
    src.add_argument(
        "--fasta",
        metavar="FILE",
        help="FASTA/FASTQ/GenBank/EMBL file (Biopython)",
    )
    src.add_argument(
        "--genome",
        metavar="FILE",
        help="23andMe, AncestryDNA, MyHeritage, or VCF raw genotyping file",
    )
    p.add_argument(
        "--clinical-report",
        metavar="FILE",
        help="write annotated clinical findings and QC metrics to Markdown or CSV",
    )
    p.add_argument("-k", type=int, default=3, help="k for --seq/--fasta (default 3)")
    p.add_argument(
        "--both-strands",
        action="store_true",
        help="also add reverse complements (DNA)",
    )
    p.add_argument(
        "--unique",
        action="store_true",
        help="treat input as a set (drop duplicate k-mers)",
    )
    p.add_argument("--save", metavar="FILE", help="save the figure (png/svg/pdf)")
    p.add_argument(
        "--csv",
        metavar="PREFIX",
        help="write PREFIX_edges.csv, _nodes.csv, and _contigs_ml.csv",
    )
    p.add_argument(
        "--gfa", metavar="FILE", help="write assembly graph in GFA 1.0 format"
    )
    p.add_argument(
        "--contigs",
        metavar="FILE",
        help="write assembled contigs as FASTA (Biopython)",
    )
    p.add_argument(
        "--genbank",
        metavar="FILE",
        help="write assembled contigs as GenBank with ORFs (Biopython)",
    )
    p.add_argument(
        "--metrics",
        action="store_true",
        help="print assembly quality metrics (N50 etc.)",
    )
    p.add_argument(
        "--binning",
        action="store_true",
        help="print scikit-learn contig binning, PCA, and GMM stats",
    )
    p.add_argument(
        "--ref",
        metavar="FILE",
        help="reference genome for assembly fidelity evaluation (Bio.Align)",
    )
    p.add_argument(
        "--export-bins",
        metavar="FILE",
        help="export contig ML features and bin assignments to CSV",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()
    if args.headless:
        return run_headless(args)
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
