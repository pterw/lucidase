"""
GUI Module: Interactive Tkinter / Matplotlib Interface for De Bruijn Explorer
=============================================================================
Provides the desktop graphical interface:
- Interactive text and file input (FASTA, FASTQ, GenBank, EMBL)
- Graph visualization with play/pause Eulerian trail step-through
- Contig inspection, ORF visualization, and Scikit-learn metagenomic binning display
- Multi-format exports: GFA 1.0, FASTA, GenBank, CSV, and PNG/SVG/PDF figures
"""

from __future__ import annotations

import csv
import gzip
import os
import sys

# Ensure Matplotlib config directory is inside workspace to avoid permission errors
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".matplotlib_cache"))

try:
    import tkinter as tk
    from tkinter import filedialog, ttk
except ImportError:  # pragma: no cover
    tk = ttk = filedialog = None

from matplotlib.figure import Figure

from assembly import write_gfa
from bio_engine import (
    alignment_basis_text,
    load_sequences_as_fasta,
    write_contigs_fasta,
    write_contigs_genbank,
)
from genomic_parser import (
    ParseResult,
    UnsupportedFormatError,
    compute_qc,
    parse_genotype_file,
    read_genotype_text,
)
from ml_engine import binning_caveat_lines
from variant_annotator import APOE_ROW_ID, RESULT_WORDS, AnnotationRecord, AnnotationReport, VariantAnnotator
from graph_core import (
    DEFAULT_K,
    EDGE,
    FUTURE,
    FUTURE_TXT,
    INK,
    LEMON,
    LIME,
    MAX_TABLE_ROWS,
    ORANGE,
    PANEL,
    PITH,
    RIND,
    TRAIL_COLORS,
    Model,
    analyze,
    collect_kmers,
    render,
)

# ===========================================================================
# EXAMPLES
# ===========================================================================
EXAMPLES = {
    "Lemon text, k=3 (single path)": dict(
        mode="seq", text="LEMONLEMONADE", k=3, both=False, unique=False
    ),
    "DNA with a repeat, k=4": dict(
        mode="seq", text="ACGTTGCAACGTTGCA", k=4, both=False, unique=False
    ),
    "Tandem repeat (self-loop), k=3": dict(
        mode="seq", text="AAAAAC", k=3, both=False, unique=False
    ),
    "Two unrelated reads (2 trails), k=4": dict(
        mode="seq",
        k=4,
        both=False,
        unique=False,
        text=">read1\nACGTACGGA\n>read2\nTTGCCATTA",
    ),
    "Both strands, k=5": dict(
        mode="seq", text="ATGGCGTACGTTAGC", k=5, both=True, unique=False
    ),
    "K-mer set -> circuit": dict(
        mode="kmers", text="ACG CGT GTA TAC", k=3, both=False, unique=False
    ),
    "Overlapping reads (assembly), k=5": dict(
        mode="seq",
        k=5,
        both=False,
        unique=False,
        text=">r1\nACGTGCAATG\n>r2\nCAATGCCGTA\n>r3\nCCGTAACGTG",
    ),
    "Reads + error (tip removal), k=4": dict(
        mode="seq",
        k=4,
        both=False,
        unique=False,
        text=">ok\nACGTGCGTACGT\n>err\nACGTTT",
    ),
    "Metagenomic mixture (binning & ORFs), k=5": dict(
        mode="seq",
        k=5,
        both=False,
        unique=False,
        text=">orgA_r1\nATGAAACCCGGGTTTTAACCGG\n>orgA_r2\nCCGGTTTTAACCCGGGTTTTAA\n>orgB_r1\nATATATATATATATATAAATTT\n>orgB_r2\nATATAAATTTTTTTTTATATAT",
    ),
    "23andMe Genotype Sample (ClinVar, PGx, tissue notes)": dict(
        mode="genome",
        k=3,
        both=False,
        unique=False,
        text="# 23andMe sample data\n# rsid\tchromosome\tposition\tgenotype\nrs429358\t19\t45411941\tCC\nrs7412\t19\t45412079\tCC\nrs1800562\t6\t26093141\tAG\nrs1799945\t6\t26092913\tCG\nrs6025\t1\t169519049\tGG\nrs1799963\t11\t46761055\tGG\nrs4244285\t10\t96541604\tAG\nrs9923231\t16\t31107689\tAG\nrs4149056\t12\t21331549\tCT\nrs1801133\t1\t11856378\tAG\nrs4988235\t2\t136608646\tAA\nrs671\t12\t112241766\tGG\nrs113993960\t7\t117199644\tDI",
    ),
}


def _rate_text(value, note, digits: int = 2) -> str:
    """A QC rate as a percentage, or "n/a" with the reason when it is not meaningful (VCF)."""
    return f"{value * 100:.{digits}f}%" if value is not None else f"n/a ({note})"


def _row_label(r: AnnotationRecord) -> str:
    """The identifier to show. APOE is one combined finding, so it never shows "APOE-STATUS"."""
    return "APOE (rs429358 + rs7412)" if r.rsid == APOE_ROW_ID else r.rsid


def _coordinate_text(r: AnnotationRecord) -> str:
    def one(rsid, chrom, pos):
        return f"{rsid} chr{chrom}:{pos:,}" if pos is not None else f"{rsid} chr{chrom} (position unavailable)"

    if r.rsid == APOE_ROW_ID:
        parts = "; ".join(one(c["rsid"], c["chrom"], c["pos"]) for c in r.raw["components"])
        return f"{parts} ({r.build})"
    return f"{one('', r.chrom, r.pos).strip()} ({r.build})"


# ---------------------------------------------------------------------------
# Pure helpers behind the genome table, the detail pane and both exports (testable without Tk)
# ---------------------------------------------------------------------------
GENOME_COLUMNS = (
    "rsid", "gene", "genotype", "category", "stars", "significance", "phenotype", "drug", "limitation",
)
PREVIEW_LIMIT = 500_000  # characters of a loaded file shown in the text box; analysis never uses this prefix
CSV_COLUMNS = (
    "source_file", "kb_release", "rsid", "gene", "genotype", "category", "review_stars", "significance",
    "magnitude", "repute", "phenotype", "limitation", "caveats", "drug_response", "acmg_actionable",
    "gnomad_af", "hpa_tissues", "hpa_subcellular", "hpa_provenance", "coverage_state", "sample_observation",
    "reason", "not_detected_statement", "evidence_tier",
)
REPORT_CAVEAT = "Absence of a finding does not imply absence of genetic risk."
NOT_AVAILABLE = "not available"


def _one_stars_text(stars) -> str:
    """ClinVar review stars in words, as the web says them: "3 of 4 review stars". Zero is a value
    ("0 of 4 review stars"); only None is "not available"."""
    return NOT_AVAILABLE if stars is None else f"{stars} of 4 review stars"


def coverage_count_lines(coverage: dict) -> list[str]:
    """The banner lines that count the untested and unclear loci, under the plain result words."""
    gaps, unclear = RESULT_WORDS["not_tested_by_array"], RESULT_WORDS["insufficient_evidence"]
    return [
        f"  {gaps + ':':.<24s} {coverage['not_tested_by_array_count']} of {coverage['total_loci']} loci",
        f"  {unclear + ':':.<24s} {coverage['insufficient_evidence_count']}",
    ]


def _labelled(r: AnnotationRecord, pick, fmt) -> str:
    """The APOE row's per-component values, each under its rsID (the row itself has none)."""
    return " · ".join(f"{c['rsid']}: {fmt(pick(c))}" for c in r.component_evidence)


def stars_text(r: AnnotationRecord) -> str:
    if r.component_evidence is not None:
        return _labelled(r, lambda c: c["review_stars"], _one_stars_text)
    return _one_stars_text(r.review_stars)


def _af_text(af) -> str:
    return f"{af * 100:.2f}%" if af is not None else NOT_AVAILABLE


def _pli_text(pli) -> str:
    return f"{pli:.2f}" if pli is not None else NOT_AVAILABLE


def _tier_text(tier) -> str:
    return tier if tier is not None else NOT_AVAILABLE


def _export_cell(r: AnnotationRecord, field: str):
    """The CSV value of stars, af or tier: the row's own, or the APOE components' values joined by ";" in
    component order (an absent one is an empty slot; all absent is an empty cell)."""
    if r.component_evidence is None:
        return getattr(r, field)
    values = [c[field] for c in r.component_evidence]
    return "" if all(v is None for v in values) else ";".join("" if v is None else str(v) for v in values)


def _hpa_provenance(r: AnnotationRecord) -> str:
    """The KB's own provenance text for the tissue entries (hand-entered, not verified against HPA)."""
    prov = ((r.raw.get("evidence") or {}).get("hpa") or {}).get("provenance") or {}
    return prov.get("source") or NOT_AVAILABLE


def _table_values(r: AnnotationRecord) -> tuple:
    return (
        _row_label(r),
        r.gene,
        r.genotype,
        r.category,
        stars_text(r),
        r.clinical_significance,
        r.phenotype,
        r.drug_response or "—",
        r.limitation or "—",
    )


def _md_cell(text) -> str:
    cell = str(text if text not in (None, "") else "—")
    return cell.replace("|", "\\|").replace("\n", " ")


def write_clinical_csv(path: str, records: list[AnnotationRecord], source: str, kb_release: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for r in records:
            writer.writerow([
                source, kb_release, _row_label(r), r.gene, r.genotype, r.category,
                _export_cell(r, "review_stars"),
                r.clinical_significance, r.magnitude, r.repute, r.phenotype, r.limitation or "",
                " | ".join(r.caveats), r.drug_response, r.acmg_actionable,
                _export_cell(r, "gnomad_af"),
                str(r.hpa_tissues), ";".join(r.hpa_subcellular), _hpa_provenance(r),
                r.coverage_state, r.sample_observation, r.reason or "", r.not_detected_statement or "",
                _export_cell(r, "evidence_tier"),
            ])


def write_clinical_markdown(
    path: str, records: list[AnnotationRecord], result: ParseResult, qc: dict, source: str, kb_release: str
) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Clinical & Proteomic Genomic Analysis Report\n\n")
        f.write(f"- **Source file**: `{source or 'pasted text'}`\n")
        f.write(f"- **Knowledge base release**: `{kb_release}`\n\n")
        f.write("### Sample Quality Control & Sequencing Metrics\n\n")
        f.write(f"- **File Format**: `{result.format.upper()}`\n")
        f.write(f"- **Genome Assembly**: `{result.build}`\n")
        f.write(f"- **Total Markers Evaluated**: `{len(result.calls):,}`\n")
        f.write(f"- **Call Rate**: `{_rate_text(qc['call_rate'], qc['qc_note'])}`\n")
        f.write(f"- **Sex-chromosome QC**: `{qc['sex_signal']}`\n\n")
        f.write(f"{REPORT_CAVEAT}\n\n")
        f.write("### High-Impact Clinical & Pharmacogenomic Findings\n\n")
        f.write(
            "| rsID | Gene | Genotype | Coverage | Observation | Category | Stars | Clinical Significance | "
            "Phenotype | Not detected | Limitation | Caveats |\n"
        )
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for r in records:
            f.write(
                f"| **{_md_cell(_row_label(r))}** | `{r.gene}` | `{r.genotype}` | "
                f"{_md_cell(RESULT_WORDS[r.coverage_state])} | "
                f"{_md_cell(r.sample_observation)} | {_md_cell(r.category)} | "
                f"{_md_cell(stars_text(r))} | {_md_cell(r.clinical_significance)} | {_md_cell(r.phenotype)} | "
                f"{_md_cell(r.not_detected_statement)} | "
                f"{_md_cell(r.limitation)} | {_md_cell(' | '.join(r.caveats))} |\n"
            )


def read_preview(path: str, limit: int = PREVIEW_LIMIT) -> str:
    """The first `limit` characters of a (possibly gzipped) file, with a final line saying so when cut.
    This is for display only: analysis always reads the whole file."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="ignore", newline="") as f:
        content = f.read(limit + 1)
    if len(content) <= limit:
        return content
    return (
        content[:limit]
        + f"\n\n# [preview: only the first {limit:,} characters are shown here; "
        "analysis uses the whole loaded file, not this text box]\n"
    )


# ===========================================================================
# GUI APPLICATION
# ===========================================================================
class ExplorerApp:
    def __init__(self, root: tk.Tk):
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg,
            NavigationToolbar2Tk,
        )

        self.root = root
        self.model: Model | None = None
        self.upto = 0
        self._playing = False
        self._busy = False

        root.title("De Bruijn Explorer")
        root.geometry("1340x860")
        root.minsize(980, 640)
        root.configure(bg=PITH)
        self._style()

        self.mode = tk.StringVar(value="seq")
        self.k = tk.IntVar(value=DEFAULT_K)
        self.both = tk.BooleanVar(value=False)
        self.unique = tk.BooleanVar(value=False)

        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        left = ttk.Frame(root, padding=12)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(root, padding=(0, 8, 8, 8))
        right.grid(row=0, column=1, sticky="nsew")

        # ---- left: input panel
        ttk.Label(left, text="De Bruijn Explorer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="graph  ·  Eulerian trail  ·  step-through",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(0, 10))
        ttk.Label(left, text="Input").pack(anchor="w")
        self.text = tk.Text(
            left,
            width=38,
            height=11,
            wrap="char",
            font=("Courier", 11),
            bg="white",
            fg=INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=RIND,
            highlightcolor=LIME,
            insertbackground=INK,
            undo=True,
        )
        self.text.pack(fill="x", pady=(2, 6))
        ttk.Radiobutton(
            left,
            text="Sequence(s) or FASTA",
            variable=self.mode,
            value="seq",
            command=self._mode_changed,
        ).pack(anchor="w")
        ttk.Radiobutton(
            left,
            text="K-mer list",
            variable=self.mode,
            value="kmers",
            command=self._mode_changed,
        ).pack(anchor="w")
        ttk.Radiobutton(
            left,
            text="23andMe / VCF Genome",
            variable=self.mode,
            value="genome",
            command=self._mode_changed,
        ).pack(anchor="w")
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=6)
        ttk.Label(row, text="k =").pack(side="left")
        self.k_spin = ttk.Spinbox(row, from_=2, to=31, width=4, textvariable=self.k)
        self.k_spin.pack(side="left", padx=6)
        ttk.Checkbutton(
            left,
            text="Both strands (adds reverse complements)",
            variable=self.both,
        ).pack(anchor="w")
        ttk.Checkbutton(
            left,
            text="Treat as a set (drop duplicate k-mers)",
            variable=self.unique,
        ).pack(anchor="w")
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(10, 4))
        ttk.Button(
            btns,
            text="Build graph",
            style="Accent.TButton",
            command=self.build,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(btns, text="Load file…", command=self.load_file).pack(
            side="left", padx=(6, 0)
        )
        ttk.Label(left, text="Examples").pack(anchor="w", pady=(10, 0))
        self.examples = ttk.Combobox(
            left, values=list(EXAMPLES), state="readonly", width=36
        )
        self.examples.pack(anchor="w", pady=2)
        self.examples.bind(
            "<<ComboboxSelected>>",
            lambda e: self.load_example(self.examples.get()),
        )
        self.status = ttk.Label(
            left, text="", wraplength=300, justify="left", style="Status.TLabel"
        )
        self.status.pack(anchor="w", pady=(14, 0))
        ttk.Label(
            left,
            text="Ctrl+Enter builds · click a table row to jump to that step",
            style="Sub.TLabel",
            wraplength=300,
        ).pack(side="bottom", anchor="w")

        # ---- right: figure, step controls, tables
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(3, weight=1)
        self.fig = Figure(figsize=(8.5, 5.6), facecolor=PITH)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        tb = ttk.Frame(right)
        tb.grid(row=1, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, tb, pack_toolbar=False)
        self.toolbar.pack(side="left")
        ttk.Button(tb, text="Zoom In (+)", width=11, command=self._zoom_in).pack(side="left", padx=(6, 2))
        ttk.Button(tb, text="Zoom Out (-)", width=12, command=self._zoom_out).pack(side="left", padx=2)
        ttk.Button(tb, text="Reset View", width=10, command=self._reset_view).pack(side="left", padx=2)
        ttk.Button(tb, text="Save figure…", command=self.save_figure).pack(
            side="right", padx=4
        )
        ttk.Button(tb, text="Export GFA…", command=self.export_gfa).pack(
            side="right", padx=4
        )
        ttk.Button(tb, text="Export FASTA…", command=self.export_contigs).pack(
            side="right", padx=4
        )
        ttk.Button(tb, text="Export GenBank…", command=self.export_genbank).pack(
            side="right", padx=4
        )
        self.export_clinical_btn = ttk.Button(tb, text="Export Clinical…", command=self.export_clinical_report)
        self.export_clinical_btn.pack(side="right", padx=4)
        self.export_clinical_btn.state(["disabled"])  # enabled by a successful genome analysis
        ttk.Button(tb, text="Export CSV…", command=self.export_csv).pack(side="right")

        ctl = ttk.Frame(right)
        ctl.grid(row=2, column=0, sticky="ew", pady=4)
        ctl.columnconfigure(2, weight=1)
        ttk.Button(
            ctl, text="◀", width=3, command=lambda: self.set_step(self.upto - 1)
        ).grid(row=0, column=0)
        self.play_btn = ttk.Button(
            ctl, text="▶ Play", width=8, command=self.toggle_play
        )
        self.play_btn.grid(row=0, column=1, padx=4)
        self.scale = tk.Scale(
            ctl,
            from_=0,
            to=1,
            orient="horizontal",
            showvalue=False,
            bg=PITH,
            troughcolor=LEMON,
            highlightthickness=0,
            command=self._on_scale,
        )
        self.scale.grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(
            ctl, text="▶", width=3, command=lambda: self.set_step(self.upto + 1)
        ).grid(row=0, column=3)
        ttk.Button(
            ctl,
            text="All",
            width=4,
            command=lambda: self.set_step(self.model.total if self.model else 0),
        ).grid(row=0, column=4, padx=(4, 0))
        self.step_lbl = ttk.Label(ctl, text="step 0 / 0", width=14, anchor="e")
        self.step_lbl.grid(row=0, column=5, padx=(8, 0))

        nb = ttk.Notebook(right)
        nb.grid(row=3, column=0, sticky="nsew", pady=(4, 0))
        self.edge_tree = self._tree(
            nb,
            "Edges",
            ("trail", "step", "global_step", "kmer", "source", "target", "copies"),
        )
        self.node_tree = self._tree(
            nb, "Nodes", ("node", "in_degree", "out_degree", "balance", "role")
        )
        tf = ttk.Frame(nb)
        nb.add(tf, text="Trails")
        self.trail_text = tk.Text(
            tf,
            wrap="word",
            font=("Courier", 10),
            bg="white",
            fg=INK,
            relief="flat",
            height=6,
        )
        self.trail_text.pack(fill="both", expand=True)
        self.contig_tree = self._tree(
            nb,
            "Contigs",
            (
                "id",
                "length",
                "edges",
                "mean_cov",
                "gc",
                "mw_da",
                "orfs",
                "bin",
                "outlier",
                "circular",
            ),
        )
        af = ttk.Frame(nb)
        nb.add(af, text="Assembly")
        self.assembly_text = tk.Text(
            af,
            wrap="word",
            font=("Courier", 10),
            bg="white",
            fg=INK,
            relief="flat",
            height=6,
        )
        self.assembly_text.pack(fill="both", expand=True)
        mf = ttk.Frame(nb)
        nb.add(mf, text="ML Binning & Features")
        self.ml_text = tk.Text(
            mf,
            wrap="word",
            font=("Courier", 10),
            bg="white",
            fg=INK,
            relief="flat",
            height=6,
        )
        self.ml_text.pack(fill="both", expand=True)
        self.edge_tree.bind("<<TreeviewSelect>>", self._row_selected)

        # ---- Genotypes / ClinVar / HPA tab
        self.genome_tree = self._tree(
            nb,
            "🧬 Genotypes",
            GENOME_COLUMNS,
        )
        for col, width in (("phenotype", 420), ("limitation", 420), ("significance", 160), ("drug", 140)):
            self.genome_tree.column(col, width=width, anchor="w", stretch=True)
        self.genome_tree.bind("<<TreeviewSelect>>", self._genome_row_selected)
        gf = ttk.Frame(nb)
        nb.add(gf, text="🧬 Proteomic & Clinical Detail")
        self.genome_detail_text = tk.Text(
            gf,
            wrap="word",
            font=("Courier", 10),
            bg="white",
            fg=INK,
            relief="flat",
            height=6,
        )
        self.genome_detail_text.pack(fill="both", expand=True)
        self.nb = nb
        self.genome_records: list[AnnotationRecord] = []
        self.sample_qc: dict | None = None  # compute_qc output for the loaded file
        self.sample_parse: ParseResult | None = None
        self.genome_source = ""  # file name the results belong to ("" for pasted text or an example)
        self.genome_kb_release = ""
        self.genome_path: str | None = None  # the loaded genotype file; analysis always reads this, not the text box
        self.genome_preview = ""  # what the text box held after the load, to tell an edit from the preview

        self._resize_job = None
        self.canvas.get_tk_widget().bind("<Configure>", self._on_resize, add="+")
        self.canvas.get_tk_widget().bind("<MouseWheel>", self._on_scroll, add="+")
        self.canvas.get_tk_widget().bind("<Button-4>", self._on_scroll, add="+")
        self.canvas.get_tk_widget().bind("<Button-5>", self._on_scroll, add="+")
        root.bind("<Control-Return>", lambda e: self.build())
        self.load_example(next(iter(EXAMPLES)))

    # ---- styling / widgets
    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=PITH, foreground=INK)
        s.configure("TFrame", background=PITH)
        s.configure("TLabel", background=PITH, foreground=INK)
        s.configure("Title.TLabel", font=("TkDefaultFont", 17, "bold"))
        s.configure("Sub.TLabel", foreground=EDGE, font=("TkDefaultFont", 9))
        s.configure("Status.TLabel", font=("TkDefaultFont", 10))
        s.configure("TCheckbutton", background=PITH)
        s.configure("TRadiobutton", background=PITH)
        s.configure("TButton", padding=5, background=PANEL)
        s.map("TButton", background=[("active", LEMON)])
        s.configure(
            "Accent.TButton",
            background=LIME,
            foreground="white",
            font=("TkDefaultFont", 10, "bold"),
        )
        s.map("Accent.TButton", background=[("active", "#588522")])
        s.configure(
            "Treeview", background="white", fieldbackground="white", rowheight=22
        )
        s.configure(
            "Treeview.Heading", background=PANEL, font=("TkDefaultFont", 9, "bold")
        )
        s.configure("TNotebook", background=PITH)

    def _tree(self, nb, title, cols):
        f = ttk.Frame(nb)
        nb.add(f, text=title)
        tree = ttk.Treeview(f, columns=cols, show="headings", height=6)
        for c in cols:
            tree.heading(c, text=c.replace("_", " "))
            tree.column(c, width=90, anchor="center")
        sb = ttk.Scrollbar(f, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return tree

    # ---- input handling
    def _mode_changed(self):
        is_seq = self.mode.get() == "seq"
        self.k_spin.state(["!disabled"] if is_seq else ["disabled"])

    def set_status(self, msg: str, error: bool = False):
        self.status.configure(text=msg, foreground="#B42318" if error else INK)

    def load_example(self, name: str):
        ex = EXAMPLES[name]
        self.examples.set(name)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", ex["text"])
        self.mode.set(ex["mode"])
        self.k.set(ex["k"])
        self.both.set(ex["both"])
        self.unique.set(ex["unique"])
        self.genome_path = None
        self.genome_preview = ""
        self._mode_changed()
        self.build()

    def load_file(self):
        path = filedialog.askopenfilename(
            title="Load sequences or genotype file",
            filetypes=[
                (
                    "Genomics & Sequence files",
                    "*.fa *.fasta *.fna *.fq *.fastq *.gb *.gbk *.embl *.txt *.csv *.vcf *.gz",
                ),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        # A recognised genotype file is analysed whole; the text box only previews it. A read error is shown,
        # never swallowed, and only "not a genotype format" falls through to the sequence readers.
        not_genotype = ""
        try:
            result, report = self._analyse_file(path)
        except UnsupportedFormatError as err:
            not_genotype = str(err)
        except Exception as err:
            self._clear_genome_results()
            self.set_status(f"Could not read {os.path.basename(path)}: {err}", error=True)
            return
        else:
            preview = read_preview(path)
            self.text.delete("1.0", "end")
            self.text.insert("1.0", preview)
            self.genome_path = path
            self.genome_preview = preview.strip()
            self.mode.set("genome")
            self._mode_changed()
            prefix = f"Loaded {os.path.basename(path)} ({result.format.upper()})"
            if "# [preview:" in preview:
                prefix += f"; the text box previews only the first {PREVIEW_LIMIT:,} characters"
            self._populate_genome_results(result, report, prefix, os.path.basename(path))
            return

        self.genome_path = None
        self.genome_preview = ""
        try:
            fasta, note = load_sequences_as_fasta(path)
        except Exception as err:
            self.set_status(f"Could not read file: {err} (not a genotype file either: {not_genotype})", error=True)
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", fasta)
        self.mode.set("seq")
        self._mode_changed()
        self.build(prefix=note)

    # ---- build / draw
    def build(self, prefix: str = ""):
        self._stop_play()
        raw_text = self.text.get("1.0", "end").strip()
        first_line = raw_text.splitlines()[0] if raw_text else ""

        is_genome = (
            self.mode.get() == "genome"
            or first_line.startswith("# rsid")
            or "23andme" in first_line.lower()
            or first_line.startswith("##fileformat=VCF")
            or first_line.startswith("#AncestryDNA")
            or '"RSID"' in first_line.upper()
        )

        if is_genome:
            if self.genome_path and raw_text == self.genome_preview:
                # Unedited preview of a loaded file: analyse the file itself, never the cut-off text.
                self._build_genome_file(self.genome_path, prefix)
            else:
                self.genome_path = None
                self._build_genome_text(raw_text, prefix)
            return

        try:
            k = int(self.k.get())
        except (tk.TclError, ValueError):
            self.set_status("k must be a whole number.", error=True)
            return
        try:
            kmers, notes = collect_kmers(
                self.text.get("1.0", "end"),
                self.mode.get(),
                k,
                self.both.get(),
                self.unique.get(),
            )
            self.model = analyze(kmers, notes, both=self.both.get())
        except ValueError as err:
            self.set_status(str(err), error=True)
            return
        m = self.model
        self.upto = m.total
        self._busy = True
        self.scale.configure(to=max(m.total, 1))
        self.scale.set(m.total)
        self._busy = False
        self._fill_tables()
        self._redraw(keep_view=False)
        lines = [prefix] if prefix else []
        lines.append(m.headline.replace("  ·  ", " · "))
        lines += m.notes
        if m.pos is None:
            lines.append("Too many nodes to draw; use the tables.")
        self.set_status("\n".join(lines))

    def _fill_tables(self):
        m = self.model
        for tree, df in ((self.edge_tree, m.edges_df), (self.node_tree, m.nodes_df)):
            tree.delete(*tree.get_children())
            for row in df.head(MAX_TABLE_ROWS).itertuples(index=False):
                tree.insert("", "end", values=tuple(row))
        self.trail_text.configure(state="normal")
        self.trail_text.delete("1.0", "end")
        for i, (t, s) in enumerate(zip(m.trails, m.spelled), 1):
            self.trail_text.insert("end", f"Trail {i}  ({len(t)} edges)\n{s}\n\n")
        self.trail_text.configure(state="disabled")

        # ---- Contigs tab
        self.contig_tree.delete(*self.contig_tree.get_children())
        if m.contigs_df is not None and not m.contigs_df.empty:
            for row in m.contigs_df.head(MAX_TABLE_ROWS).itertuples(index=False):
                self.contig_tree.insert("", "end", values=tuple(row))

        # ---- Assembly tab: metrics, k-mer spectrum, contig listing
        self.assembly_text.configure(state="normal")
        self.assembly_text.delete("1.0", "end")
        lines = ["\u2550" * 3 + " Assembly Metrics " + "\u2550" * 3 + "\n"]
        for key, val in m.metrics.items():
            lines.append(f"  {key.replace('_', ' ').title():.<24s} {val}\n")
        lines.append(f"\n" + "\u2550" * 3 + " K-mer Coverage " + "\u2550" * 3 + "\n")
        for key, val in m.cov_stats.items():
            lines.append(f"  {key.replace('_', ' ').title():.<24s} {val}\n")
        lines.append(
            f"\n"
            + "\u2550" * 3
            + " K-mer Spectrum (coverage \u2192 distinct k-mers) "
            + "\u2550" * 3
            + "\n"
        )
        for cov, cnt in list(m.spectrum.items())[:30]:
            bar = "\u2588" * min(cnt, 50)
            lines.append(f"  {cov:>4d}\u00d7  {cnt:>6d}  {bar}\n")
        if len(m.spectrum) > 30:
            lines.append(f"  ... ({len(m.spectrum) - 30} more levels)\n")
        lines.append(
            f"\n"
            + "\u2550" * 3
            + f" Contigs ({len(m.contigs)}) "
            + "\u2550" * 3
            + "\n"
        )
        for c in m.contigs[:50]:
            tag = " [circular]" if c.get("circular") else ""
            lines.append(
                f"  ctg{c['id']}  len={c['length']}  cov={c['mean_coverage']}  "
                f"gc={c['gc_content']}{tag}\n"
            )
            if c["length"] <= 200:
                lines.append(f"    {c['sequence']}\n")
            else:
                lines.append(f"    {c['sequence'][:80]}...{c['sequence'][-20:]}\n")
        if len(m.contigs) > 50:
            lines.append(f"  ... ({len(m.contigs) - 50} more contigs)\n")
        self.assembly_text.insert("end", "".join(lines))
        self.assembly_text.configure(state="disabled")

        # ---- ML Binning & Features tab
        self.ml_text.configure(state="normal")
        self.ml_text.delete("1.0", "end")
        m_lines = ["\u2550" * 3 + " Contig Binning & PCA (heuristic, exploratory) " + "\u2550" * 3 + "\n"]
        bs = m.binning_summary
        m_lines.extend(f"  {line}\n" for line in binning_caveat_lines(bs))
        m_lines.append(f"  Clusters (KMeans Bins):... {bs.get('n_bins', 1)}\n")
        if bs.get("pca_variance_ratio"):
            vars_str = ", ".join(
                f"PC{i+1}: {v*100:.1f}%" for i, v in enumerate(bs["pca_variance_ratio"])
            )
            m_lines.append(f"  PCA Explained Variance:... {vars_str}\n")
        m_lines.append(f"  Flagged by 10% rule:...... {bs.get('outlier_count', 0)}\n\n")
        for b_name, b_data in bs.get("clusters", {}).items():
            m_lines.append(f"  {b_name}:\n")
            m_lines.append(
                f"    Contigs: {b_data.get('contigs')}  ·  Total bp: {b_data.get('total_bp'):,}  ·  "
                f"Mean GC: {b_data.get('mean_gc')}  ·  Mean Cov: {b_data.get('mean_cov')}\u00d7\n"
            )
        m_lines.append(
            "\n" + "\u2550" * 3 + " K-mer Error Model (Scikit-Learn GMM) " + "\u2550" * 3 + "\n"
        )
        gs = m.gmm_stats
        m_lines.append(f"  Method:................... {gs.get('method', 'None')}\n")
        m_lines.append(f"  Bayes Decision Cutoff:.... {gs.get('cutoff', 1)}\u00d7\n")
        if "error_mean_cov" in gs:
            m_lines.append(f"  Fitted Error Mean Cov:.... {gs.get('error_mean_cov')}\u00d7\n")
            m_lines.append(f"  Fitted Genomic Mean Cov:.. {gs.get('genomic_mean_cov')}\u00d7\n")
            m_lines.append(f"  Component Weights:........ {gs.get('weights')}\n")
        m_lines.append(
            "\n" + "\u2550" * 3 + " Biopython ORF / Gene Predictions " + "\u2550" * 3 + "\n"
        )
        total_orfs = sum(len(c.get("orfs", [])) for c in m.contigs)
        m_lines.append(f"  Total ORFs Found:......... {total_orfs}\n")
        for c in m.contigs[:20]:
            orfs = c.get("orfs", [])
            m_lines.append(
                f"  ctg{c['id']} (MW: {c.get('molecular_weight', 0):,.1f} Da, Bin {c.get('bin_id', 1)}): {len(orfs)} ORF(s)\n"
            )
            for orf in orfs[:3]:
                strand_sym = "+" if orf["strand"] == 1 else "-"
                m_lines.append(
                    f"    [{strand_sym} frame {orf['frame']}] {orf['start']}..{orf['end']} ({orf['length_aa']} aa): {orf['protein'][:30]}...\n"
                )
            if len(orfs) > 3:
                m_lines.append(f"    ... ({len(orfs) - 3} more ORFs)\n")
        if m.ref_eval:
            m_lines.append(
                "\n" + "\u2550" * 3 + " Reference Alignment Fidelity (Bio.Align) " + "\u2550" * 3 + "\n"
            )
            m_lines.append(
                f"  Reference Length:......... {m.ref_eval.get('reference_length'):,} bp\n"
            )
            m_lines.append(
                f"  Genome Fraction Covered:.. {m.ref_eval.get('genome_fraction', 0)*100:.2f}%\n"
            )
            m_lines.append(
                f"  Mean Alignment Identity:.. {m.ref_eval.get('mean_identity', 0)*100:.2f}%\n"
            )
            m_lines.append(f"  ({alignment_basis_text()})\n")
            m_lines.append(
                f"  Aligned Contigs:.......... {m.ref_eval.get('aligned_contigs')}\n"
            )
        self.ml_text.insert("end", "".join(m_lines))
        self.ml_text.configure(state="disabled")

    def _redraw(self, keep_view: bool = True):
        if not self.model:
            return
        view = None
        if keep_view and self.fig.axes:
            ax = self.fig.axes[0]
            view = (ax.get_xlim(), ax.get_ylim())
        render(self.fig, self.model, self.upto)
        if view and self.fig.axes and self.model.pos is not None:
            self.fig.axes[0].set_xlim(*view[0])
            self.fig.axes[0].set_ylim(*view[1])
        if not keep_view:
            self.toolbar.update()
        self.canvas.draw_idle()
        self.step_lbl.configure(text=f"step {self.upto} / {self.model.total}")

    def _on_resize(self, _event):
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(180, self._redraw)

    def _zoom(self, factor: float):
        if not hasattr(self, "fig") or not self.fig.axes or not self.model or self.model.pos is None:
            return
        ax = self.fig.axes[0]
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        cx, cy = (xlim[0] + xlim[1]) / 2.0, (ylim[0] + ylim[1]) / 2.0
        w, h = (xlim[1] - xlim[0]) * factor, (ylim[1] - ylim[0]) * factor
        ax.set_xlim(cx - w / 2.0, cx + w / 2.0)
        ax.set_ylim(cy - h / 2.0, cy + h / 2.0)
        if hasattr(self, "canvas") and self.canvas is not None:
            self.canvas.draw_idle()

    def _zoom_in(self):
        self._zoom(0.75)

    def _zoom_out(self):
        self._zoom(1.33)

    def _reset_view(self):
        self._redraw(keep_view=False)

    def _on_scroll(self, event):
        if getattr(event, "delta", 0) > 0 or getattr(event, "num", None) == 4:
            self._zoom(0.85)
        elif getattr(event, "delta", 0) < 0 or getattr(event, "num", None) == 5:
            self._zoom(1.18)

    # ---- stepping
    def set_step(self, n: int):
        if not self.model:
            return
        self.upto = max(0, min(int(n), self.model.total))
        self._busy = True
        self.scale.set(self.upto)
        self._busy = False
        self._redraw()

    def _on_scale(self, value):
        if not self._busy and self.model:
            self.set_step(int(float(value)))

    def _row_selected(self, _event):
        sel = self.edge_tree.selection()
        if sel:
            self.set_step(int(self.edge_tree.item(sel[0], "values")[2]))

    def toggle_play(self):
        if self._playing:
            self._stop_play()
            return
        if not self.model:
            return
        if self.upto >= self.model.total:
            self.set_step(0)
        self._playing = True
        self.play_btn.configure(text="⏸ Pause")
        self._tick()

    def _tick(self):
        if not self._playing:
            return
        if self.upto >= self.model.total:
            self._stop_play()
            return
        self.set_step(self.upto + 1)
        self.root.after(550, self._tick)

    def _stop_play(self):
        self._playing = False
        self.play_btn.configure(text="▶ Play")

    # ---- export
    def save_figure(self):
        if not self.model:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg"), ("PDF", "*.pdf")],
        )
        if path and self._write_or_report(
            "the figure", lambda: self.fig.savefig(path, dpi=200, facecolor=self.fig.get_facecolor())
        ):
            self.set_status(f"Saved {os.path.basename(path)}")

    def export_csv(self):
        if not self.model:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile="debruijn.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if path:
            base = os.path.splitext(path)[0]

            def write():
                self.model.edges_df.to_csv(f"{base}_edges.csv", index=False)
                self.model.nodes_df.to_csv(f"{base}_nodes.csv", index=False)
                if self.model.contigs_df is not None and not self.model.contigs_df.empty:
                    self.model.contigs_df.to_csv(f"{base}_contigs_ml.csv", index=False)

            if not self._write_or_report("the CSV files", write):
                return
            self.set_status(
                f"Wrote {os.path.basename(base)}_edges.csv, _nodes.csv, and _contigs_ml.csv"
            )

    def export_gfa(self):
        if not self.model or not self.model.contigs:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".gfa",
            initialfile="assembly.gfa",
            filetypes=[("GFA", "*.gfa")],
        )
        if path:
            if not self._write_or_report("the GFA file", lambda: write_gfa(self.model.contigs, path, self.model.k, both=self.model.both)):
                return
            self.set_status(
                f"Saved {os.path.basename(path)} ({len(self.model.contigs)} contigs)"
            )

    def export_contigs(self):
        if not self.model or not self.model.contigs:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".fasta",
            initialfile="contigs.fasta",
            filetypes=[("FASTA", "*.fasta *.fa"), ("All", "*.*")],
        )
        if path:
            if not self._write_or_report("the FASTA file", lambda: write_contigs_fasta(self.model.contigs, path)):
                return
            self.set_status(
                f"Saved {os.path.basename(path)} ({len(self.model.contigs)} contigs)"
            )

    def export_genbank(self):
        if not self.model or not self.model.contigs:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".gbk",
            initialfile="contigs.gbk",
            filetypes=[("GenBank", "*.gb *.gbk *.genbank"), ("All", "*.*")],
        )
        if path:
            if not self._write_or_report("the GenBank file", lambda: write_contigs_genbank(self.model.contigs, path)):
                return
            self.set_status(
                f"Saved {os.path.basename(path)} ({len(self.model.contigs)} contigs with annotations)"
            )

    # ---- Genomic / ClinVar / HPA processing
    def _build_genome_text(self, raw_text: str, prefix: str = ""):
        try:
            result = parse_genotype_file(raw_text)
            report = VariantAnnotator().annotate_genome(result)
        except Exception as err:
            self._clear_genome_results()
            self.set_status(f"Error parsing genomic text: {err}. Previous results were cleared.", error=True)
            return
        self._populate_genome_results(result, report, prefix, "")

    def _analyse_file(self, path: str) -> tuple[ParseResult, AnnotationReport]:
        result = parse_genotype_file(read_genotype_text(path), os.path.basename(path))
        return result, VariantAnnotator().annotate_genome(result)

    def _build_genome_file(self, path: str, prefix: str = ""):
        try:
            result, report = self._analyse_file(path)
        except Exception as err:
            self._clear_genome_results()
            self.set_status(f"Error parsing genomic file: {err}. Previous results were cleared.", error=True)
            return
        self._populate_genome_results(result, report, prefix, os.path.basename(path))

    def _clear_genome_results(self):
        """A failed analysis leaves no earlier file's findings to view or export."""
        self.genome_records = []
        self.sample_qc = None
        self.sample_parse = None
        self.genome_source = ""
        self.genome_kb_release = ""
        self.genome_tree.delete(*self.genome_tree.get_children())
        self.genome_detail_text.configure(state="normal")
        self.genome_detail_text.delete("1.0", "end")
        self.genome_detail_text.configure(state="disabled")
        self.export_clinical_btn.state(["disabled"])

    def _write_or_report(self, what: str, write) -> bool:
        """Run a file write; a failure reaches the user in the status line instead of stderr only."""
        try:
            write()
        except (OSError, ValueError) as err:
            self.set_status(f"Could not save {what}: {err}", error=True)
            return False
        return True

    def _populate_genome_results(
        self, result: ParseResult, report: AnnotationReport, prefix: str = "", source: str = ""
    ):
        qc = compute_qc(result)
        records = report.records
        self.sample_qc = qc
        self.sample_parse = result
        self.genome_records = records
        self.genome_source = source
        self.genome_kb_release = report.kb_release
        self.export_clinical_btn.state(["!disabled"])
        summary = VariantAnnotator().summarize_annotations(report)
        coverage = summary["coverage"]

        # Populate tree
        self.genome_tree.delete(*self.genome_tree.get_children())
        for r in records:
            self.genome_tree.insert("", "end", values=_table_values(r))

        # Populate details text banner
        self.genome_detail_text.configure(state="normal")
        self.genome_detail_text.delete("1.0", "end")
        lines = [
            "═" * 3 + " Quality Control & Sequencing Metrics " + "═" * 3 + "\n",
            f"  Source:................. {source or 'pasted text'}\n",
            f"  Knowledge Base Release:. {report.kb_release}\n",
            f"  Format Detected:........ {result.format.upper()}\n",
            f"  Genome Assembly:........ {result.build}\n",
            f"  Total Markers:.......... {len(result.calls):,} SNPs\n",
            f"  Call Rate:.............. {_rate_text(qc['call_rate'], qc['qc_note'])}\n",
            f"  Heterozygosity Rate:.... {_rate_text(qc['heterozygosity_rate'], qc['qc_note'])}\n",
            f"  Sex-chromosome QC:...... {qc['sex_signal']}\n\n",
            "═" * 3 + f" Clinical & Proteomic Findings ({len(records)} loci) " + "═" * 3 + "\n",
            f"  Pathogenic Variants:.... {summary['pathogenic_count']}\n",
            f"  Carrier Conditions:..... {summary['carrier_count']}\n",
            f"  Pharmacogenomics:....... {summary['pgx_count']} drug response alerts\n",
            f"  Elevated Risk Factors:.. {summary['risk_factor_count']}\n",
            f"  ACMG SF v3.2 Actionable: {summary['acmg_actionable_findings']}\n",
            *(f"{line}\n" for line in coverage_count_lines(coverage)),
            "\n",
            "Absence of a finding does not imply absence of genetic risk.\n\n",
            "Select any variant row in the table above to inspect ClinVar review stars, the phenotype, the limitation and caveats, and the tissue notes (hand-entered; the provenance is shown with them).\n",
        ]
        self.genome_detail_text.insert("end", "".join(lines))
        self.genome_detail_text.configure(state="disabled")

        # Switch to Genotypes tab
        for tab_id in self.nb.tabs():
            if "Genotypes" in self.nb.tab(tab_id, "text"):
                self.nb.select(tab_id)
                break

        msg = (
            f"Parsed {len(result.calls):,} SNPs ({result.format.upper()}, {result.build}) · "
            f"Call rate: {_rate_text(qc['call_rate'], qc['qc_note'], 1)} · Sex-chromosome QC: {qc['sex_signal']} · "
            f"{len(records)} loci"
        )
        if prefix:
            msg = f"{prefix}\n{msg}"
        self.set_status(msg)

    def _genome_row_selected(self, _event):
        sel = self.genome_tree.selection()
        if not sel or not self.genome_records:
            return
        idx = self.genome_tree.index(sel[0])
        if idx >= len(self.genome_records):
            return
        r = self.genome_records[idx]

        self.genome_detail_text.configure(state="normal")
        self.genome_detail_text.delete("1.0", "end")
        lines = [
            f"═" * 3 + f" Clinical Variant Inspection: {_row_label(r)} ({r.gene}) " + "═" * 3 + "\n\n",
            f"  Genotype:............... {r.genotype}\n",
            f"  Coverage:............... {RESULT_WORDS[r.coverage_state]}"
            + (f" ({r.reason})" if r.reason else "")
            + "\n",
            f"  Chromosome Coordinate:.. {_coordinate_text(r)}\n",
            f"  Category:............... {r.category}\n",
            f"  Clinical Significance:.. {r.clinical_significance}\n",
            f"  ClinVar Review Stars:... {stars_text(r)}\n",
            "  Evidence Tier:.......... "
            + (
                _labelled(r, lambda c: c["evidence_tier"], _tier_text)
                if r.component_evidence is not None
                else _tier_text(r.evidence_tier)
            )
            + "\n",
            "  Magnitude:.............. "
            + (f"{r.magnitude:.1f} / 10.0 (Repute: {r.repute})" if r.magnitude is not None else "not available")
            + "\n",
        ]
        if r.not_detected_statement:
            lines.append(f"  Not detected:........... {r.not_detected_statement}\n")
        if r.limitation:
            lines.append(f"  Limitation:............. {r.limitation}\n")
        for caveat in r.caveats:
            lines.append(f"  Caveat:................. {caveat}\n")
        if r.acmg_actionable:
            lines.append("  ACMG Actionable:........ YES (Designated ACMG Secondary Findings v3.2 Gene)\n")
        if r.drug_response:
            lines.append(f"  Drug Response (CPIC):... {r.drug_response}\n")
        if r.component_evidence is not None:
            af_text = _labelled(r, lambda c: c["gnomad_af"], _af_text)
            pli_text = _labelled(r, lambda c: c["gnomad_pli"], _pli_text)
        else:
            af_text, pli_text = _af_text(r.gnomad_af), _pli_text(r.gnomad_pli)
        lines.append(f"  gnomAD Allele Frequency: {af_text}\n")
        lines.append(f"  gnomAD pLI (Constraint): {pli_text}\n\n")

        lines.append("═" * 3 + " Clinical Condition & Phenotype " + "═" * 3 + "\n")
        lines.append(f"  {r.phenotype}\n\n")

        lines.append("═" * 3 + " Tissue Abundance (hand-entered) " + "═" * 3 + "\n")
        lines.append(f"  Provenance:............. {_hpa_provenance(r)}\n")
        if r.hpa_tissues:
            for tissue, level in r.hpa_tissues.items():
                lines.append(f"  {tissue.title():.<26s} {level}\n")
        else:
            lines.append(f"  Tissues:................ {NOT_AVAILABLE}\n")
        if r.hpa_subcellular:
            lines.append(f"  Subcellular Location:... {', '.join(r.hpa_subcellular)}\n")

        self.genome_detail_text.insert("end", "".join(lines))
        self.genome_detail_text.configure(state="disabled")

    def export_clinical_report(self):
        if not self.genome_records or not self.sample_qc:
            self.set_status("No genomic records to export. Load a 23andMe or VCF file first.", error=True)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile="genomic_clinical_report.md",
            filetypes=[("Markdown Report", "*.md"), ("CSV Data", "*.csv"), ("All", "*.*")],
        )
        if not path:
            return

        qc, result = self.sample_qc, self.sample_parse
        if path.endswith(".csv"):
            write = lambda: write_clinical_csv(  # noqa: E731
                path, self.genome_records, self.genome_source, self.genome_kb_release
            )
        else:
            write = lambda: write_clinical_markdown(  # noqa: E731
                path, self.genome_records, result, qc, self.genome_source, self.genome_kb_release
            )
        if not self._write_or_report("the clinical report", write):
            return
        self.set_status(f"Saved clinical report to {os.path.basename(path)}")


def run_gui() -> int:
    if tk is None:
        sys.stderr.write(
            "tkinter is not available in this Python, so the GUI cannot start.\n"
            "  Debian/Ubuntu:  sudo apt install python3-tk\n"
            "  Fedora:         sudo dnf install python3-tkinter\n"
            "  macOS (brew):   brew install python-tk\n"
            "You can still run headless:  python debruijn_explorer.py --headless --seq ACGTACGT -k 3 --save out.png\n"
        )
        return 1
    root = tk.Tk()
    ExplorerApp(root)
    root.mainloop()
    return 0
