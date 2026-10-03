# Lucidase — Engineering & Design Specification

## Design Context

> **Provisional (owner ruling, 2026-10-02).** Visual design and brand identity have not been established, and the
> design system that will own them has not been authored yet. The Brand Personality, Aesthetic Direction,
> Typography Specification and Design Principles sections below describe the current look and are provisional, not
> authoritative. Styling lives in `web/tailwind.config.js`, `web/src/tailwind.input.css` (the `@tailwind`
> directives), `web/src/styles.css` (theme CSS variables, badge classes, glass panels, typography overrides) and the
> vendored daisyUI. The future design system will own all of them.

### Users
- **Target Audience**: Proactive health explorers, biohackers, individuals analyzing their own 23andMe / AncestryDNA / VCF raw files, clinicians, and genetics enthusiasts.
- **Context & Motivation**: Users who "want more from their analysis" than basic consumer summaries, seeking Promethease-level depth without sacrificing privacy, clarity, or interface elegance.
- **Job to Be Done**: Rapidly evaluate genetic risk factors, carrier conditions, pharmacogenomics (drug metabolism), and actionable medical findings with complete local privacy.
- **Emotional Goals**: Confidence, clinical clarity, empowering comprehension, and peace of mind.

### Brand Personality (provisional)
- **Voice & Tone**: High-tech, clinical, authoritative, crisp, and user-centric.
- **3-Word Personality**: **High-Tech · Clinical · Crisp**.
- **User Focus**: Prioritize clear, actionable UX for people who want rigorous, deep insights into their biological blueprints.

### Aesthetic Direction (provisional)
- **Visual Direction**: High-tech clinical with **sharp corners** (clean geometric cards, refined structural borders, high-density professional tables).
- **Theme**: **Light Mode** foundation with a bespoke design system, plus a toggleable **Dark HUD** biotech mode.
- **Anti-References**:
  - **Promethease**: Explicitly avoid clunky, outdated web 1.0 styling, overwhelming walls of unformatted text, and confusing layouts.
  - **Toy / Gamified Apps**: Avoid overly cartoonish, bubbly, rounded consumer tropes that compromise clinical credibility.

### Typography Specification (Adobe Typekit `gfe3vcu`, chosen by the owner 2026-10-03) (provisional)
- **Kit Source**: `<link rel="stylesheet" href="https://use.typekit.net/gfe3vcu.css">`
- **Sans (body & interface)**: **`akzidenz-grotesk-next-pro`** (400, 400 Italic, 700, 700 Italic)
  - *Fallbacks*: `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `Roboto`, `sans-serif` (Strictly **NO Inter**).
- **Mono (genomic & data)**: **`input-mono`** (400, 400 Italic, 700, 700 Italic)
  - *Use*: rsIDs (`rs429358`), genotypes (`CT`, `0/1`), genomic coordinates (`chr19:45411941`), and latency benchmarks (`3 ms`).
  - *Fallbacks*: `ui-monospace`, `monospace` (Strictly **NO JetBrains Mono**).
- **Serif (editorial areas)**: **`orpheuspro`** (400, 400 Italic, 700)
  - *Use*: clinical phenotype narratives and medical interpretations (Replaces any Instrument Serif).
  - *Fallbacks*: `Georgia`, `serif`.
- **Display (condensed metric callouts)**: **`swiss-721-bt-condensed`** (400, 400 Italic, 700, 700 Italic)
  - *Use*: high-density statistical callouts (e.g. `12–15×`, `99.8%`, `ACMG SF v3.2`).
  - *Fallbacks*: `akzidenz-grotesk-next-pro`, `sans-serif`.

### Interactive Font Studio & Extension Companion
- **Font Kit Studio (`tools/font-kit-studio/`)**: Standalone designer tooling and laboratory suite exposing the four families of Typekit kit `gfe3vcu` (Akzidenz-Grotesk Next Pro, Orpheus Pro, Input Mono, Swiss 721 BT Condensed; ruling 15) (extracted out of the production clinical application).
  - Dynamically binds to `--font-sans`, `--font-serif`, `--font-mono`, `--font-display`, `--editorial-size`, `--mono-spacing`.
  - 4 1-click curated presets: *🧬 Impeccable Clinical*, *📰 Editorial Heavyweight*, *🔬 Swiss Bio Precision*, *⚡ Biotech Cyber HUD*.
  - Live fine-tuning sliders for narrative text size (12px–20px) and monospace letter spacing (-0.05em to +0.1em).
- **Chrome Extension Companion (`chrome-extension/`)**:
  - Manifest V3 extension with custom popup, active-tab scripting, and live injection.
  - Allows swapping typography in real time directly from the Chrome toolbar.

### Design Principles (principles 1, 2, 3 and 6 are provisional design direction)
1. **Sharp Clinical Precision**: Use crisp geometric architecture, sharp corners (`rounded-none` / `rounded-sm`), and precise structural dividers. Data must look scientific, authoritative, and expertly curated.
2. **Actionable Synthesis Over Text Walls**: Replace Promethease-style walls of text with structured, glanceable cards, high-density sortable datagrids, and deep on-demand flyout drawers.
3. **Compound Haplotype Intelligence**: Multi-SNP loci (specifically **APOE ε2/ε3/ε4 diplotypes**) must be synthesized into one dedicated clinical record, never fragmented or lost as isolated neutral SNPs. CYP450 star alleles are not called: single-SNP array data cannot support a star-allele diplotype, so the app shows the single interrogated SNP with a limitation notice and refuses a metabolizer assignment (provisional, like the rest of this section).
4. **Uncompromising Zero-Knowledge Privacy**: Raw genomic data never leaves the browser. The interface must transparently affirm local-first processing at all times.
5. **One Curated Knowledge Base, Honest Provenance**: All annotations come from one build-time knowledge base (`web/src/knowledge-base.json`, built from pinned upstream payloads plus labelled manual curation). There is no edge cache, no Redis and no live literature lookup: nothing about a user's variants is sent to any server, and every value shows where it came from or is shown as "not available".
6. **Editorial Typography Hierarchy**: Use Akzidenz-Grotesk Next Pro for authoritative human communication and Input Mono for raw biological blueprints.


