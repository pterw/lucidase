# Lucidase Design System

Lucidase reads a raw genotype file **in the browser** and interprets the 55 curated loci (34 genes) in its knowledge base. It says plainly what it could not test. It reads 23andMe, AncestryDNA, MyHeritage and VCF files and rejects anything else with a visible error. No accounts, no payments, no upload. Formerly GenomePulse.

The name is *lucid* + *-ase* (the enzyme suffix). The arch from the **c** to the dot of the **i** in the wordmark is a ligature — "ligature" and "ligase", the enzyme that joins DNA strands, share a root. The dot field in the banner is a stylised karyogram. **That logo is the idea this system is built from.**

## Sources

- GitHub: **https://github.com/pterw/lucidase** (branch `main`) — read `README.md`, `web/index.html`, `web/karyogram.html`, `web/src/styles.css`, `web/src/theme.js`, `web/tailwind.config.js`, `docs/design-handoff.md`, `docs/assets/*`, `web/src/knowledge-base.json` (loci list). Explore it further — especially `docs/design-handoff.md` (states H1–H14, a11y audit, open questions) and `AGENTS.md` (honesty rules) — before designing new surfaces.
- Upload: `uploads/lucidase-banner.svg` (the user's banner).
- Fonts: Adobe Fonts kit `gfe3vcu` (`https://use.typekit.net/gfe3vcu.css`), as linked by the repo.

The repo's own handoff says the current UI is **provisional, not a design system**. This project is the proposal for one: it keeps the product's structure, states and honesty rules, and replaces the provisional visuals (emoji, gradient tile, slate/sky Tailwind defaults, glass panels, nested tinted boxes, ALL-CAPS kickers) with an identity drawn from the wordmark.

## Products

One product, two static pages — both recreated in `ui_kits/web/`:
- **Analysis** (`web/index.html`): dropzone → progress → error | results (scope notice, sample QC, coverage-state counts, APOE composite, filters/search/export, findings table, record drawer with inheritance calculator).
- **Karyogram** (`web/karyogram.html`): where the file's markers sit on 24 chromosomes; reference-only, loading, result, density-unavailable, error states.

---

## Content fundamentals

The product's best copy is already factual and humble; the system makes that the only register.

- **Say what it does and what it does not.** "Your file is read in this browser and never uploaded." "It does not sequence whole genes." Every limitation travels with the result (row, drawer, export).
- **Never overpromise.** Not a diagnostic test, not medical advice. No "clinical-grade", "zero-knowledge", "proteomic explorer", "engineered for". No accuracy figures, no user counts, **no testimonials, no fake stats**. Every number on screen is produced by the analysis or by a stated model.
- **Absence ≠ normal.** Use "Not detected among the N variants tested", never "normal", "wild-type baseline" or "no risk".
- **Missing is "Not available"** (muted italic) — never a placeholder value or a default.
- **Plain words over codes.** Result words are Found / Not found / Not on your chip / Unclear / Not checked (keys stay `supported_and_observed` … in data and exports).
- **Address the reader as "you" / "your file"**; the product speaks in the third person ("Lucidase checks…"), never "we".
- **Sentence case** everywhere — headings, buttons, badges, tabs. No ALL-CAPS, no tracking-wide labels.
- **No eyebrow/kicker above any heading.** A heading stands alone; context goes in a description line below it.
- **No emoji.** Not in buttons, headings, badges or the logo.
- Wording rules from the product: disease/recurrence figures only for Mendelian loci ("Child affected"); otherwise "Child inherits the allele". Unphased pairs say "phase unknown".

Examples (repo → system):
- "⚡ Load 23andMe Demo Sample" → "Try a made-up example file"
- "SCIENTIFIC SCOPE & GUARDRAIL: ABSENCE OF A FINDING ≠ ABSENCE OF RISK" → title "Absence of a finding is not absence of risk." + plain explanation
- "Dark HUD" / "Light Mode" → "Dark" / "Light"
- "Local-First (Client-Side Only)" (pulsing) → "Read in this browser" (still dot)
- "Tested WT (State 2) · Supported, not detected" → "Not detected · Among the variants tested"

## Visual foundations

- **Palette** — lifted from the wordmark/banner SVGs: paper `#FBFAF7`, line `#E6E1D7`, ink `#0E1A24`, muted `#56636E`, dot `#D6CFC2`, accent teal `#0893A6`; dark twins `#0B1117 / #1D2731 / #EDF2F5 / #97A6B2 / #253441 / #62E4F1`. One accent. Teal also = "Observed" state, exactly as the banner marks its 14 loci.
- **Semantic colour** — two separate vocabularies, each an ink/wash/line triple: *coverage states* (observed teal, not detected green, not on array amber, outside coverage grey, insufficient evidence rose) and *categories* (pathogenic, risk factor, carrier, pharmacogenomics, trait, not detected). They never share a column. Colour is never the only signal.
- **Type** — a family built from the product's Adobe kit: **Orpheus Pro** (headings, plain-language prose; the wordmark's voice), **Akzidenz-Grotesk Next Pro** (UI/body), **Akzidenz-Grotesk Next Condensed** (column heads, large counts; Swiss 721 BT Condensed as fallback), **Input Mono** (rsIDs, genotypes, coordinates, file names) and **Input Mono Narrow** (dense tables). Italic is reserved for the wordmark/tagline. 11px floor.
- **Corners** — panels and cards **square (0)**; controls and badges 2px (the repo's value); only data dots are round.
- **Containers** — no cards. Report sections sit on a ledger grid (heading in a 200px margin column, hairline rule above). Only the drop field and the docked Inspector have a border.
- **Borders & shadow** — hairlines carry structure. The only shadow is a small one under the menu. Primary buttons are ink, not teal (contrast).
- **Backgrounds** — paper, flat. The dot field appears only inside figures (karyogram, banner), never as page texture. No gradients, imagery, blur or glass.
- **Data viz** — dots with soft halos (banner/karyogram motif); bars are solid, square, 4–6px, always labelled with the number.
- **Motion** — transform/opacity only, 100–240ms, ease-out-quart `cubic-bezier(.25,1,.5,1)`. Nothing loops or pulses. `prefers-reduced-motion` zeroes durations.
- **Hover** — panel row/background shifts to `--bg-hover`; primary deepens to `--accent-hover`; outlines darken to `--ink-muted`. **Press** — no shrink. **Focus** — 2px accent outline, 2px offset.
- **Layout** — 1280px max; 64px between report sections, 4–16px inside them; sticky solid header; Inspector 440px docked beside the list.
- **Transparency** — only washes in dark mode (state/category backgrounds at ~9–10% alpha) and the drawer scrim.
- **Themes** — `data-theme="light|dark"` on `<html>`, stored in `localStorage["lucidase-theme"]` (same as the product).

See `guidelines/anti-slop.md` for the full list of generic-AI patterns this system forbids.

## Iconography

- The product today uses **emoji only** (🧬 📂 ⚡ 🔬 💊 ⚠️ 🛡️ ✕). That is retired.
- **Substitution (flagged):** Lucide line icons via CDN (`lucide-static@0.469.0`), rendered by the `Icon` component as a `currentColor` mask so they follow theme and tone. 1.5–2px stroke matches Akzidenz' weight. Sizes 14/16/20. Used sparingly and always beside a text label.
- No icon font, no sprite, no PNG icons in the repo. No unicode-as-icon except `·` as a separator and `ε` in APOE names.
- The logo is never reduced to an icon tile.

## Brand assets (`assets/`)

- **The logo is the wordmark.** The **karyogram mark** (`logo/lucidase-karyogram-{light,dark}.svg`) is the logo element beside it in the banner: computed from GRCh38 chromosome lengths in 4 Mb bins, with the 14 curated loci in accent. Extracted unchanged from the banner.
- **Favicon / app icon:** `logo/favicon-{light,dark}.svg` (`favicon.svg` = light) is the wordmark's **c→i ligature with the teal dot**, cut from the wordmark outlines and stroked slightly heavier so it reads at 16px. It carries the name's idea (ligature ≈ ligase, a join). Unstroked versions for large sizes: `logo/lucidase-monogram-{light,dark}.svg`. Link both with `media="(prefers-color-scheme: …)"`.

- `logo/lucidase-wordmark-{light,dark}.svg` (+ `-mono` single-colour black), `logo/lucidase-banner-{light,dark}.svg`. The repo's SVGs carry CSS-variable styles (prefers-color-scheme); those were baked into fixed light/dark files here because `<style>` in SVG is stripped on save.
- `screenshots/` — the repo's README captures of the provisional UI (reference only, not the new look).

---

## Index

- `styles.css` — entry; imports `tokens/fonts.css, colors.css, typography.css, spacing.css, shape.css, motion.css, base.css`.
- `guidelines/` — foundation cards (`*.card.html`) and `anti-slop.md`.
- `components/` — React primitives (below), one card per folder.
- `ui_kits/web/` — Analysis + Karyogram click-through (`index.html`).
- `tailwind/` — Tailwind v3 preset, daisyUI 4 themes, Tailwind v4 `@theme`; see `tailwind/README.md`. Node is optional — `styles.css` + components work without a build.
- `SKILL.md` — agent-skill entry point. `github.md` — source sync record.

## Components

- **core/** — Button, IconButton, Icon, StateMark, Term, StatusDot, Wordmark, Masthead
- **forms/** — Dropzone, SearchInput, SegmentedControl, ThemeToggle
- **feedback/** — Alert, Progress, NotAvailable
- **report/** — ReportSection, FindingRow, Karyogram, KaryogramLegend, Ligature, DataList, DataTable, ProbabilityBar
- **navigation/** — AppHeader, NavLink, StepNav, LocalNote, FilterTabs, Menu, Inspector (+ InspectorSection), AppFooter

Mapping to the repo's inventory (`docs/design-handoff.md`): header → AppHeader, NavLink, ThemeToggle, LocalNote; dropzone → Dropzone; progress → Progress; analysis error / guardrail / density notice → Alert; coverage + category cards → Karyogram + KaryogramLegend (the summary) and ReportSection groups; APOE card → FindingRow + Ligature; filter tabs/search/table → DataTable + SearchInput (behind "All results as a table"); export dropdown → Menu / "Save a copy" step; variant drawer → Inspector; offspring simulator → SegmentedControl + ProbabilityBar; footer → AppFooter; "Not available" → NotAvailable.

### Intentional additions
- **Icon** — Lucide wrapper replacing emoji.
- **Wordmark** — the logo as a component.
- **StateMark** — shape-coded result mark (filled / ring / dashed ring / half / small dot) from the karyogram's dot language.
- **Term** — inline glossary for newcomers.
- **StepNav** — three-step orientation (choose → read → save).
- **ReportSection, FindingRow** — the plain-language report layout that replaces cards.
- **Ligature** — the wordmark's arch as a figure for two-marker composites (APOE).
- **Inspector** — non-modal docked details (replaces the modal drawer).

## Responsive & accessibility rules

- **Theme:** follows the device (`prefers-color-scheme`) by default, live. Most people never change it, so the override is not in the header: the footer has one muted link offering the opposite theme ("Dark theme" / "Light theme"), and "Use device setting" appears only after an override. Stored in `localStorage["lucidase-theme"]`. Add the no-flash snippet from `ThemeToggle.prompt.md` to `<head>`.
- **Header:** static (scrolls away; NN/g: sticky bars cost content space and hide focus). Slim 56px bar with the product name as plain text, page links, local-only note and a "Theme" menu. Below 680px (its own width) links fold into a "Pages" disclosure. Skip link first.
- **Logo placement:** the wordmark is never shrunk into app chrome or recoloured to fit it. It appears once, as the lockup (`logo/lucidase-lockup-{light,dark}.svg`: the banner without its frame, wordmark + karyogram at their banner proportion) in a Masthead at ≥560px wide; smaller than that, use the wordmark alone at the top of the start page (and on report covers), at ≥48px with ¼-height clear space, using the source SVG's approved light/dark artwork.
- **Steps:** below 560px StepNav becomes "Step 2 of 3", a thin bar and a back link.
- **Targets:** at least 24×24px everywhere (WCAG 2.2 AA 2.5.8); nav links, header buttons and the large button are 40–48px.
- **Focus:** 2px accent outline with offset; nothing sticky covers focused content (WCAG 2.2 2.4.11). `prefers-contrast: more` strengthens lines and muted text.

## Contrast (WCAG 2.2 AA), measured

Text needs 4.5:1 (1.4.3); control edges, focus rings and meaningful marks need 3:1 (1.4.11).

| Pair | Light | Dark |
|---|---|---|
| ink on paper (body) | 16.9 | 16.8 |
| ink-muted on paper (secondary text) | 5.9 | 7.6 |
| ink-subtle on paper (least text; floor) | 4.8 | 5.6 |
| accent-ink on paper (links) | 5.7 | 12.6 |
| on-ink on ink (primary button) | 16.9 | 16.8 |
| state ink on its wash (5 states) | 5.2–6.7 | 6.9–11.3 |
| notice / danger ink on wash | 5.5 / 6.7 | 10.3 / 8.1 |
| control-border on paper (inputs, outlined buttons) | 3.6 | 3.7 |
| accent on paper (focus ring, observed mark) | 3.5 | 12.6 |
| state-outside mark on paper | 3.6 | 4.5 |

Rules: `--accent` (light #0893A6, 3.5:1) is never used for text. Text in teal uses `--accent-ink`. `--line` / `--line-strong` are decorative hairlines only. Anything that marks a control's edge uses `--border-control`.

## UX principles (for a newcomer)

Lucidase is a lightweight, private Promethease. Assume the reader has never seen a genotype file.
1. **Three steps, always visible.** Choose your file → Read your results → Save a copy (StepNav).
2. **Meaning before jargon.** Each result leads with its topic ("Clopidogrel (Plavix) response"), then a plain sentence, then the gene, then the marker and genotype. Technical tables are one click away, not the default.
3. **Grouped by what it means to you:** Pharmacology, Health risk factors, Carrier status, Traits.
4. **Five result words, everywhere the same:** Found, Not found, Not on your chip, Unclear, Not checked — each with a shape and a one-line explanation (`stateHelp`).
5. **Limits travel with the result** as "What this can't tell you", in the row itself.
6. **The map is the overview.** The karyogram opens the results; selecting a mark opens that result.
7. **Inspect without losing your place.** Details dock beside the list; Esc closes.
8. **Define words in place** with Term rather than a separate glossary page.

Audit and rationale: `guidelines/audit.md` and `guidelines/anti-slop.md`.

## Fonts — caveat

All five families load from Adobe Fonts kit `gfe3vcu`; no font files are in the repo or here. Kits are domain-locked — add your production domain to the kit, or supply licensed self-host files. No Google substitutes are used.
