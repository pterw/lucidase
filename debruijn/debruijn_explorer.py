#!/usr/bin/env python3
"""
De Bruijn Explorer: Graph Algorithms, Biopython Integration & Machine Learning
=============================================================================
A computational biology tool for de Bruijn graph sequence analysis, assembly,
and metagenomics.

Quickstart:
    python debruijn_explorer.py              # Launch interactive desktop GUI
    python -m pytest tests/test_debruijn.py  # Run the tool's tests
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
import os
import sys

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
try:
    from .assembly import (  # noqa: E402
        assembly_metrics,
        build_assembly_graph,
        extract_contigs,
        simplify_graph,
        write_gfa,
    )
    from .bio_engine import (  # noqa: E402
        _gc_content,
        alignment_basis_text,
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
    from .graph_core import (  # noqa: E402
        EDGE,
        FUTURE,
        FUTURE_TXT,
        DEFAULT_K,
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
    from .ml_engine import (  # noqa: E402
        OUTLIER_FRACTION,
        bin_contigs,
        binning_caveat_lines,
        coverage_summary,
        estimate_error_threshold,
        extract_kmer_features,
        fit_kmer_error_model,
        kmer_spectrum,
    )
except ImportError:
    from assembly import (  # noqa: E402
        assembly_metrics,
        build_assembly_graph,
        extract_contigs,
        simplify_graph,
        write_gfa,
    )
    from bio_engine import (  # noqa: E402
        _gc_content,
        alignment_basis_text,
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
        DEFAULT_K,
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
    from ml_engine import (  # noqa: E402
        OUTLIER_FRACTION,
        bin_contigs,
        binning_caveat_lines,
        coverage_summary,
        estimate_error_threshold,
        extract_kmer_features,
        fit_kmer_error_model,
        kmer_spectrum,
    )

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

def __getattr__(name: str):
    if name in {
        "EXAMPLES",
        "ExplorerApp",
        "coverage_count_lines",
        "stars_text",
        "run_gui",
        "write_clinical_csv",
        "write_clinical_markdown",
    }:
        import gui
        return getattr(gui, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from genomic_parser import (  # noqa: E402
    compute_qc,
    parse_genotype_file,
    read_genotype_text,
)
from variant_annotator import (  # noqa: E402
    APOE_ROW_ID,
    RESULT_WORDS,
    AnnotationRecord,
    VariantAnnotator,
)


# DEFAULT_K lives in graph_core, so the GUI, the Python API and the CLI share one value.


# ===========================================================================
# High-Level Programmatic API
# ===========================================================================
def assemble(
    text: str,
    k: int = DEFAULT_K,
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
        K-mer length (default ``DEFAULT_K``, shared with the CLI ``-k`` option;
        use a larger k such as 31 for real reads).
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
    m = analyze(kmers, notes, ref_seq=ref_seq, both=both_strands)
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
def _rate_text(value, note) -> str:
    """A QC rate as a percentage, or "n/a" with the reason when it is not meaningful (VCF)."""
    return f"{value * 100:.2f}%" if value is not None else f"n/a ({note})"


def run_headless(args) -> int:
    """Execute command-line assembly, graph analysis, and artifact export."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from gui import coverage_count_lines, stars_text, write_clinical_csv, write_clinical_markdown
    if getattr(args, "genome", None):
        try:
            result = parse_genotype_file(read_genotype_text(args.genome), os.path.basename(args.genome))
            qc = compute_qc(result)
            annotator = VariantAnnotator()
            report = annotator.annotate_genome(result)
            records = report.records
            summary = annotator.summarize_annotations(report)
        except Exception as err:
            print(f"Error parsing genomic file: {err}", file=sys.stderr)
            return 1

        print("=" * 60)
        print(f"GENOMIC SAMPLE QUALITY CONTROL ({result.format.upper()})")
        print("=" * 60)
        print(f"  Genome Assembly:........ {result.build}")
        print(f"  Total Markers:.......... {len(result.calls):,} SNPs")
        print(
            f"  Call Rate:.............. {_rate_text(qc['call_rate'], qc['qc_note'])} "
            f"({result.stats.called:,} called, {result.stats.no_calls:,} missing)"
        )
        print(f"  Heterozygosity Rate:.... {_rate_text(qc['heterozygosity_rate'], qc['qc_note'])}")
        print(f"  Sex-chromosome QC:...... {qc['sex_signal']}")

        print("\n" + "=" * 60)
        print(f"CLINVAR & PROTEOMIC ANNOTATIONS ({len(records)} loci)")
        print("=" * 60)
        print(f"  Pathogenic Variants:.... {summary['pathogenic_count']}")
        print(f"  Carrier Conditions:..... {summary['carrier_count']}")
        print(f"  Pharmacogenomics:....... {summary['pgx_count']} drug response alerts")
        print(f"  Elevated Risk Factors:.. {summary['risk_factor_count']}")
        print(f"  ACMG SF v3.2 Actionable: {summary['acmg_actionable_findings']}")
        coverage = summary["coverage"]
        for line in coverage_count_lines(coverage):
            print(line)
        print("  Absence of a finding does not imply absence of genetic risk.\n")

        for r in records:
            label = "APOE" if r.rsid == APOE_ROW_ID else r.rsid  # APOE_ROW_ID is an internal row id
            print(
                f"- {label:<12s} [{r.gene:<8s}] Genotype: {r.genotype:<4s} | {r.category} "
                f"({stars_text(r)}) | {RESULT_WORDS[r.coverage_state]} | {r.sample_observation}"
            )
            print(f"  Significance: {r.clinical_significance}")
            print(f"  Condition:    {r.phenotype}")
            if r.not_detected_statement:
                print(f"  Not detected: {r.not_detected_statement}")
            if r.limitation:
                print(f"  Limitation:   {r.limitation}")
            if r.drug_response:
                print(f"  CPIC Drug:    {r.drug_response}")
            if r.hpa_tissues:
                tissues_str = ", ".join(f"{t}: {l}" for t, l in list(r.hpa_tissues.items())[:3])
                print(f"  HPA Tissues:  {tissues_str}")
            print()

        if getattr(args, "clinical_report", None):
            # The same serialisers as the GUI export, so the two cannot drift (S4c-C-4).
            source = os.path.basename(args.genome)
            try:
                if args.clinical_report.endswith(".csv"):
                    write_clinical_csv(args.clinical_report, records, source, report.kb_release)
                else:
                    write_clinical_markdown(args.clinical_report, records, result, qc, source, report.kb_release)
            except OSError as err:
                print(f"Error writing the clinical report: {err}", file=sys.stderr)
                return 1
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
        m = analyze(kmers, notes, ref_seq=ref_seq, both=args.both_strands)
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
        print("\n--- Contig Binning & PCA (heuristic, exploratory) ---")
        bs = m.binning_summary
        for line in binning_caveat_lines(bs):
            print(f"  {line}")
        print(f"  Clusters (KMeans Bins):... {bs.get('n_bins', 1)}")
        if bs.get("pca_variance_ratio"):
            vars_str = ", ".join(
                f"PC{i+1}: {v*100:.1f}%" for i, v in enumerate(bs["pca_variance_ratio"])
            )
            print(f"  PCA Explained Variance:... {vars_str}")
        print(f"  Flagged by {OUTLIER_FRACTION:.0%} rule:...... {bs.get('outlier_count', 0)}")
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
        print(f"  ({alignment_basis_text()})")
        print(f"  Aligned Contigs:.......... {m.ref_eval.get('aligned_contigs')}")

    if args.gfa:
        write_gfa(m.contigs, args.gfa, m.k, both=m.both)
        print(f"Wrote GFA to {args.gfa} ({len(m.contigs)} contigs)")
    if args.contigs:
        write_contigs_fasta(m.contigs, args.contigs)
        print(f"Wrote {len(m.contigs)} contigs to {args.contigs}")
    if args.genbank:
        write_contigs_genbank(m.contigs, args.genbank)
        print(f"Wrote {len(m.contigs)} contigs with annotated ORFs to {args.genbank}")
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
    p.add_argument(
        "-k",
        type=int,
        default=DEFAULT_K,
        help=f"k for --seq/--fasta (default {DEFAULT_K})",
    )
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
    if args.headless:
        return run_headless(args)
    from gui import run_gui
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
