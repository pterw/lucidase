<p align="center"><img src="docs/assets/lucidase-banner.svg" alt="Lucidase: free, private analysis of your raw DNA file"></p>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/lucidase-screenshot-dark.png">
  <img src="docs/assets/lucidase-screenshot-light.png" alt="Lucidase results for the bundled demo sample: the Summary sentence, sticky toolbar with 1-line Coverage Ledger bar and view switcher, multi-locus gene brackets, and docked inspector drawer">
</picture>

*The bundled synthetic demo sample, analysed in the browser.*

Lucidase is a privacy-first, client-side genetic analysis workbench and plain-language alternative to Promethease. It reads a raw genotype file in your browser and interprets the 55 curated loci (34 genes) in its canonical knowledge base. It states plainly what it could not test. It supports 23andMe, AncestryDNA, MyHeritage array files and standard VCF files (GRCh37/GRCh38), rejecting any unknown or corrupted format with a clear, visible error. Formerly GenomePulse.

## Karyogram view

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/lucidase-karyogram-dark.png">
  <img src="docs/assets/lucidase-karyogram-light.png" alt="The Lucidase karyogram of the bundled example file: 24 chromosome columns of marker-density dots with the 34 genes this report checks marked by result">
</picture>

`web/karyogram.html` provides a dedicated chromosome distribution explorer that maps your genotype file onto all 24 human chromosomes. Each dot represents a genomic bin (~4 Mb) sized by how many markers from your file fall there, with all 34 curated genes annotated by their coverage state. If a file lacks explicit reference build metadata, the page notes the limitation while retaining gene-level checks. The map is rendered purely in SVG from UCSC chromosome geometry and centromere coordinates, with instant gene search and high-resolution JPEG export.

## What it does

- **Zero-knowledge client-side analysis**: Parses and classifies genotypes in a background Web Worker in the browser—no accounts, no trackers, and DNA data never leaves your device.
- **Fail-closed genetic classification**: Compares alleles by alt-allele count against plus-strand ref/alt. Ambiguous palindromic sites (A/T, C/G), multi-allelic collisions, and no-calls fail closed to unresolvable rather than guessing wild-type.
- **Strict coverage taxonomy**: Assigns every curated locus exactly one coverage state per sample: `supported_and_observed`, `supported_not_observed`, `not_tested_by_array`, `outside_coverage`, or `insufficient_evidence`.
- **Calm editorial results ledger**: Groups findings into Pharmacology, Health risk factors, Carrier status, and Traits, presented with unambiguous result words (*Found*, *Not found*, *Not on your chip*, *Unclear*) and prominent negative-finding guardrails ("Absence of a finding is not absence of risk").
- **Multi-locus gene brackets**: Groups multiple variants within the same gene (e.g. BRCA1, HFE, DPYD) under a shared structural bracket with upfront unphased microarray caveats.
- **Composite diplotypes**: Unifies complex multi-variant loci like APOE (rs429358 + rs7412) into a single composite finding with phenotype risk projections.
- **Sticky control strip & 1-line Coverage Ledger**: A full-width sticky navigation bar provides a compact proportional Coverage Ledger bar, high-contrast Cards / Table segmented toggle, live status filter pills, instant text search, and category jumps.
- **Docked non-modal Inspector drawer**: Explores deep findings alongside the results ledger with sequential keyboard navigation (`< X of Y >`), 4-pip geometric ClinVar review status (`■■■□`), CPIC/ACMG clinical alerts, Offspring Allele Simulator, and 1px-bordered technical detail accordions.
- **Rigorous inheritance modeling**: Distinguishes Mendelian disease risk from non-disease allele transmission figures; risk percentages reflect actual patient genotype and partner models.
- **Clean data exports**: Exports full-scope Markdown (.md) and technical CSV (.csv) reports directly from browser memory.
- **Dual archival themes**: Crafted with Lucidase design tokens in warm archival paper light mode and deep slate-obsidian dark mode.

## What it does not do

- It is not a diagnostic test and not medical advice. Absence of a finding does not imply absence of genetic risk.
- It does not sequence whole genes. It cannot detect copy-number variations, balanced translocations or structural repeats.
- A single-variant test of a multi-variant gene carries its limitation on the row, in the details pane and in every export.
- Only the curated loci are interpreted. Other markers in your file are counted, not interpreted.

See "Known limitations" in [`web/README.md`](web/README.md).

## Privacy

Your file is read and analysed in the browser and is never uploaded. The Content-Security-Policy sets `connect-src 'self'`. There are no accounts and no payments. The page currently loads its web fonts from Adobe Fonts (use.typekit.net); no genotype data is sent there.

## Run it

See [Deployment Options](web/README.md#deployment-options) and its Local Development section in [`web/README.md`](web/README.md).

## Repository map

| Area | Path | Role |
|---|---|---|
| Web app | `web/` | Parses and classifies raw DNA files in the browser. |
| Knowledge-base build | `tools/` | Builds the one curated knowledge base, `web/src/knowledge-base.json`. |
| Desktop genomics | `genomic_parser.py`, `variant_annotator.py`, `segregation_engine.py`, `biotools_orchestrator.py`, `gui.py` | Local reference implementation of the same rules. |
| de Bruijn explorer | `debruijn/` (`graph_core.py`, `assembly.py`, `bio_engine.py`, `ml_engine.py`, `debruijn_explorer.py`) | Standalone assembly and graph teaching tool. |

## Development

Rules and gates are in [`AGENTS.md`](AGENTS.md). Working notes are in [`CLAUDE.md`](CLAUDE.md). The audit and its remediation history are in [`AUDIT_LEDGER.md`](AUDIT_LEDGER.md).

The `Gates` workflow (`.github/workflows/gates.yml`) runs the five gates on every pull request and every push to `main`, and pull request bodies follow [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md). Run `python -m pip install pre-commit` and then `pre-commit install` once per clone.

`python run.py` serves `web/` on localhost and opens the app (`--port N`, `--no-browser`).

## About the name

Lucidase is *lucid* plus *-ase*, the enzyme suffix, as in Promethease. The arch from the c to the dot of the i in the wordmark is a ligature, and "ligature" and "ligase", the enzyme that joins DNA strands, share a root. The dot field in the banner is a stylised karyogram.
