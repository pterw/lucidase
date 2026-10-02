# GenomePulse — Engineering & Design Specification

## Design Context

### Users
- **Target Audience**: Proactive health explorers, biohackers, individuals analyzing their own 23andMe / AncestryDNA / VCF raw files, clinicians, and genetics enthusiasts.
- **Context & Motivation**: Users who "want more from their analysis" than basic consumer summaries, seeking Promethease-level depth without sacrificing privacy, clarity, or interface elegance.
- **Job to Be Done**: Rapidly evaluate genetic risk factors, carrier conditions, pharmacogenomics (drug metabolism), and actionable medical findings with complete local privacy.
- **Emotional Goals**: Confidence, clinical clarity, empowering comprehension, and peace of mind.

### Brand Personality
- **Voice & Tone**: High-tech, clinical, authoritative, crisp, and user-centric.
- **3-Word Personality**: **High-Tech · Clinical · Crisp**.
- **User Focus**: Prioritize clear, actionable UX for people who want rigorous, deep insights into their biological blueprints.

### Aesthetic Direction
- **Visual Direction**: High-tech clinical with **sharp corners** (clean geometric cards, refined structural borders, high-density professional tables).
- **Theme**: **Light Mode** foundation with a bespoke design system, plus a toggleable **Dark HUD** biotech mode.
- **Anti-References**:
  - **Promethease**: Explicitly avoid clunky, outdated web 1.0 styling, overwhelming walls of unformatted text, and confusing layouts.
  - **Toy / Gamified Apps**: Avoid overly cartoonish, bubbly, rounded consumer tropes that compromise clinical credibility.

### Impeccable Typography Specification (Adobe Typekit `cqu4tvx`)
- **Kit Source**: `<link rel="stylesheet" href="https://use.typekit.net/cqu4tvx.css">`
- **Primary Body & Interface**: **`gotham`** (400 Normal, 500 Medium, 200 Light)
  - *Rationale*: Architectural rigor, geometric purity, and clinical confidence.
  - *Fallbacks*: `'nimbus-sans'`, `-apple-system`, `BlinkMacSystemFont`, `sans-serif` (Strictly **NO Inter**).
- **Genomic & Data Monospace**: **`attribute-mono`** (300 Light, 400 Regular)
  - *Rationale*: Surgical clarity for rsIDs (`rs429358`), genotypes (`CT`, `0/1`), genomic coordinates (`chr19:45411941`), and latency benchmarks (`3 ms`).
  - *Fallbacks*: `'ballinger-mono'`, `'azo-mono'`, `monospace` (Strictly **NO JetBrains Mono**).
- **Humanist Editorial Serif**: **`orpheuspro`** (400 Normal, 400 Italic, 500 Normal)
  - *Rationale*: Elegantly expresses clinical phenotype narratives, medical interpretations, and high-impact biological insights with humanistic editorial authority (Replaces any Instrument Serif).
  - *Fallbacks*: `'archer-pro'`, `Georgia`, `serif`.
- **Condensed Metric Display**: **`neuzeit-grotesk-condensed`** (900 Heavy)
  - *Rationale*: High-density statistical callouts (e.g. `12–15×`, `99.8%`, `ACMG SF v3.2`).

### Interactive Font Studio & Extension Companion
- **Live In-App Font Studio**: Floating typography engine (`web/src/font-studio.js`) exposing all 27 foundry fonts from Typekit kit `cqu4tvx`.
  - Dynamically binds to `--font-sans`, `--font-serif`, `--font-mono`, `--font-display`, `--editorial-size`, `--mono-spacing`.
  - 4 1-click curated presets: *🧬 Impeccable Clinical*, *📰 Editorial Heavyweight*, *🔬 Swiss Bio Precision*, *⚡ Biotech Cyber HUD*.
  - Live fine-tuning sliders for narrative text size (12px–20px) and monospace letter spacing (-0.05em to +0.1em).
- **Chrome Extension Companion (`chrome-extension/`)**:
  - Manifest V3 extension with custom popup, active-tab scripting, and live injection.
  - Allows swapping typography in real time directly from the Chrome toolbar.

### Design Principles
1. **Sharp Clinical Precision**: Use crisp geometric architecture, sharp corners (`rounded-none` / `rounded-sm`), and precise structural dividers. Data must look scientific, authoritative, and expertly curated.
2. **Actionable Synthesis Over Text Walls**: Replace Promethease-style walls of text with structured, glanceable cards, high-density sortable datagrids, and deep on-demand flyout drawers.
3. **Compound Haplotype Intelligence**: Multi-SNP loci (specifically **APOE ε2/ε3/ε4 diplotypes** and CYP450 pharmacogenomic star alleles) must be synthesized into dedicated, definitive clinical calls, never fragmented or lost as isolated neutral SNPs.
4. **Uncompromising Zero-Knowledge Privacy**: Raw genomic data never leaves the browser. The interface must transparently affirm local-first processing at all times.
5. **Ultra-Responsive Edge Enrichment**: Leverage Upstash Redis edge caching to provide lightning-fast (<10ms) literature lookups and proteomic insights for users seeking deeper exploration.
6. **Editorial Typography Hierarchy**: Use Gotham for authoritative human communication and Attribute Mono for raw biological blueprints.


