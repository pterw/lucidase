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
    load_sequences_as_fasta,
    write_contigs_fasta,
    write_contigs_genbank,
)
from genomic_parser import GenomicParser, SampleQC, VariantCall
from variant_annotator import AnnotationRecord, VariantAnnotator
from graph_core import (
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
    "23andMe Genotype Sample (ClinVar, HPA, PGx)": dict(
        mode="genome",
        k=3,
        both=False,
        unique=False,
        text="# 23andMe sample data\n# rsid\tchromosome\tposition\tgenotype\nrs429358\t19\t45411941\tCC\nrs7412\t19\t45412079\tCC\nrs1800562\t6\t26093141\tAG\nrs1799945\t6\t26092913\tCG\nrs6025\t1\t169519049\tGG\nrs1799963\t11\t46761055\tGG\nrs4244285\t10\t96541604\tAG\nrs9923231\t16\t31107689\tAG\nrs4149056\t12\t21331549\tCT\nrs1801133\t1\t11856378\tAG\nrs4988235\t2\t136608646\tAA\nrs671\t12\t112241766\tGG\nrs113993960\t7\t117199644\tDI",
    ),
}


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
        self.k = tk.IntVar(value=3)
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
        ttk.Button(tb, text="Export Clinical…", command=self.export_clinical_report).pack(
            side="right", padx=4
        )
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
            ("rsid", "gene", "genotype", "category", "stars", "significance", "phenotype", "drug"),
        )
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
        self.sample_qc: SampleQC | None = None

        self._resize_job = None
        self.canvas.get_tk_widget().bind("<Configure>", self._on_resize, add="+")
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
        # Auto-detect DTC genome / VCF
        try:
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8", errors="ignore") as f:
                head_lines = [f.readline() for _ in range(30)]
            fmt, _ = GenomicParser.detect_format(head_lines)
            if fmt != "unknown":
                with opener(path, "rt", encoding="utf-8", errors="ignore") as f:
                    content = f.read(500_000)
                self.text.delete("1.0", "end")
                self.text.insert("1.0", content)
                self.mode.set("genome")
                self._mode_changed()
                self._build_genome_file(path, prefix=f"Loaded {os.path.basename(path)} ({fmt.upper()})")
                return
        except Exception:
            pass

        try:
            fasta, note = load_sequences_as_fasta(path)
        except Exception as err:
            self.set_status(f"Could not read file: {err}", error=True)
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
            self.model = analyze(kmers, notes)
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
        m_lines = ["\u2550" * 3 + " Scikit-Learn Contig Binning & PCA " + "\u2550" * 3 + "\n"]
        bs = m.binning_summary
        m_lines.append(f"  Clusters (KMeans Bins):... {bs.get('n_bins', 1)}\n")
        if bs.get("pca_variance_ratio"):
            vars_str = ", ".join(
                f"PC{i+1}: {v*100:.1f}%" for i, v in enumerate(bs["pca_variance_ratio"])
            )
            m_lines.append(f"  PCA Explained Variance:... {vars_str}\n")
        m_lines.append(f"  Potential Outliers:....... {bs.get('outlier_count', 0)}\n\n")
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
        if path:
            self.fig.savefig(path, dpi=200, facecolor=self.fig.get_facecolor())
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
            self.model.edges_df.to_csv(f"{base}_edges.csv", index=False)
            self.model.nodes_df.to_csv(f"{base}_nodes.csv", index=False)
            if self.model.contigs_df is not None and not self.model.contigs_df.empty:
                self.model.contigs_df.to_csv(f"{base}_contigs_ml.csv", index=False)
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
            write_gfa(self.model.contigs, path, self.model.k)
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
            write_contigs_fasta(self.model.contigs, path)
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
            write_contigs_genbank(self.model.contigs, path)
            self.set_status(
                f"Saved {os.path.basename(path)} ({len(self.model.contigs)} contigs with annotations)"
            )

    # ---- Genomic / ClinVar / HPA processing
    def _build_genome_text(self, raw_text: str, prefix: str = ""):
        try:
            variants, qc = GenomicParser.parse_text(raw_text)
            annotator = VariantAnnotator()
            records = annotator.annotate_genome(variants)
            self._populate_genome_results(qc, records, prefix)
        except Exception as err:
            self.set_status(f"Error parsing genomic text: {err}", error=True)

    def _build_genome_file(self, path: str, prefix: str = ""):
        try:
            variants, qc = GenomicParser.parse_file(path)
            annotator = VariantAnnotator()
            records = annotator.annotate_genome(variants)
            self._populate_genome_results(qc, records, prefix)
        except Exception as err:
            self.set_status(f"Error parsing genomic file: {err}", error=True)

    def _populate_genome_results(
        self, qc: SampleQC, records: list[AnnotationRecord], prefix: str = ""
    ):
        self.sample_qc = qc
        self.genome_records = records
        annotator = VariantAnnotator()
        summary = annotator.summarize_annotations(records)

        # Populate tree
        self.genome_tree.delete(*self.genome_tree.get_children())
        for r in records:
            stars_str = "★" * r.review_stars if r.review_stars else "—"
            short_pheno = r.phenotype[:40] + ("…" if len(r.phenotype) > 40 else "")
            self.genome_tree.insert(
                "",
                "end",
                values=(
                    r.rsid,
                    r.gene,
                    r.genotype,
                    r.category,
                    stars_str,
                    r.clinical_significance,
                    short_pheno,
                    r.drug_response or "—",
                ),
            )

        # Populate details text banner
        self.genome_detail_text.configure(state="normal")
        self.genome_detail_text.delete("1.0", "end")
        lines = [
            "═" * 3 + " Quality Control & Sequencing Metrics " + "═" * 3 + "\n",
            f"  Format Detected:........ {qc.format_name.upper()}\n",
            f"  Genome Assembly:........ {qc.build}\n",
            f"  Total Markers:.......... {qc.total_snps:,} SNPs\n",
            f"  Call Rate:.............. {qc.call_rate*100:.2f}%\n",
            f"  Heterozygosity Rate:.... {qc.heterozygosity_rate*100:.2f}%\n",
            f"  Inferred Biological Sex: {qc.inferred_sex}\n\n",
            "═" * 3 + f" Clinical & Proteomic Findings ({len(records)}) " + "═" * 3 + "\n",
            f"  Pathogenic Variants:.... {summary['pathogenic_count']}\n",
            f"  Carrier Conditions:..... {summary['carrier_count']}\n",
            f"  Pharmacogenomics:....... {summary['pgx_count']} drug response alerts\n",
            f"  Elevated Risk Factors:.. {summary['risk_factor_count']}\n",
            f"  ACMG SF v3.2 Actionable: {summary['acmg_actionable_findings']}\n\n",
            "Select any variant row in the table above to inspect ClinVar review criteria, OMIM/MedGen phenotypes, and Human Protein Atlas (HPA) tissue protein abundance.\n",
        ]
        self.genome_detail_text.insert("end", "".join(lines))
        self.genome_detail_text.configure(state="disabled")

        # Switch to Genotypes tab
        for tab_id in self.nb.tabs():
            if "Genotypes" in self.nb.tab(tab_id, "text"):
                self.nb.select(tab_id)
                break

        msg = (
            f"Parsed {qc.total_snps:,} SNPs ({qc.format_name.upper()}, {qc.build}) · "
            f"Call rate: {qc.call_rate*100:.1f}% · Inferred: {qc.inferred_sex} · "
            f"{len(records)} clinical findings"
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
            f"═" * 3 + f" Clinical Variant Inspection: {r.rsid} ({r.gene}) " + "═" * 3 + "\n\n",
            f"  Genotype:............... {r.genotype} ({r.call.zygosity.upper()})\n",
            f"  Chromosome Coordinate:.. chr{r.call.chrom}:{r.call.pos:,} ({r.call.build})\n",
            f"  Category:............... {r.category}\n",
            f"  Clinical Significance:.. {r.clinical_significance}\n",
            f"  ClinVar Review Stars:... {'★' * r.review_stars} ({r.review_stars} / 4 stars)\n",
            f"  Promethease Magnitude:.. {r.magnitude:.1f} / 10.0 (Repute: {r.repute})\n",
        ]
        if r.acmg_actionable:
            lines.append("  ACMG Actionable:........ YES (Designated ACMG Secondary Findings v3.2 Gene)\n")
        if r.drug_response:
            lines.append(f"  Drug Response (CPIC):... {r.drug_response}\n")
        lines.append(f"  gnomAD Allele Frequency: {r.gnomad_af*100:.2f}%\n")
        lines.append(f"  gnomAD pLI (Constraint): {r.gnomad_pli:.2f}\n\n")

        lines.append("═" * 3 + " Clinical Condition & Phenotype " + "═" * 3 + "\n")
        lines.append(f"  {r.phenotype}\n\n")

        lines.append("═" * 3 + " Human Protein Atlas (HPA) Tissue Abundance " + "═" * 3 + "\n")
        if r.hpa_tissues:
            for tissue, level in r.hpa_tissues.items():
                lines.append(f"  {tissue.title():.<26s} {level}\n")
        else:
            lines.append("  Wild-type protein expression widely distributed.\n")
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

        qc = self.sample_qc
        if path.endswith(".csv"):
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "rsid", "gene", "genotype", "category", "review_stars", "significance",
                    "magnitude", "repute", "phenotype", "drug_response", "acmg_actionable",
                    "gnomad_af", "hpa_tissues", "hpa_subcellular"
                ])
                for r in self.genome_records:
                    writer.writerow([
                        r.rsid, r.gene, r.genotype, r.category, r.review_stars,
                        r.clinical_significance, r.magnitude, r.repute, r.phenotype,
                        r.drug_response, r.acmg_actionable, r.gnomad_af,
                        str(r.hpa_tissues), ";".join(r.hpa_subcellular)
                    ])
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Clinical & Proteomic Genomic Analysis Report\n\n")
                f.write(f"### Sample Quality Control & Sequencing Metrics\n\n")
                f.write(f"- **File Format**: `{qc.format_name.upper()}`\n")
                f.write(f"- **Genome Assembly**: `{qc.build}`\n")
                f.write(f"- **Total Markers Evaluated**: `{qc.total_snps:,}`\n")
                f.write(f"- **Call Rate**: `{qc.call_rate*100:.2f}%`\n")
                f.write(f"- **Inferred Biological Sex**: `{qc.inferred_sex}`\n\n")
                f.write(f"### High-Impact Clinical & Pharmacogenomic Findings\n\n")
                f.write(f"| rsID | Gene | Genotype | Category | Stars | Clinical Significance | Phenotype |\n")
                f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
                for r in self.genome_records:
                    stars_str = "★" * r.review_stars if r.review_stars else "—"
                    f.write(f"| **{r.rsid}** | `{r.gene}` | `{r.genotype}` | {r.category} | {stars_str} | {r.clinical_significance} | {r.phenotype} |\n")
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
