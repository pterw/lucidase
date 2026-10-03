# Handoff Spec: GenomePulse web app (provisional UI)

> **BANNER - READ FIRST.** This document records the **current, provisional UI as built** on branch `fix/genomepulse-hardening`, plus the behavioural, state and clinical-honesty requirements any future design system must satisfy.
> Owner ruling (verbatim): *"Webdev and identity haven't been established so when tailwind and daisy ui land properly and install design of this is within a system that is yet to be authored."*
> It proposes **no** new colours, fonts, spacing scales, themes or components. Every visual value below is a **de facto** value found in code, not a design decision. Citations are `file:line`.

Sources: `web/index.html` (I), `web/src/app.js` (A), `web/src/styles.css` (S), `web/tailwind.config.js` (T), `web/src/vendor/README.md`, `AGENTS.md` sections 3-5, `task.md` (provisional), `tests/e2e/*.py`, briefs T7/T8/T9.

---

## Overview

Single-page, client-only analysis of raw DNA files (23andMe, AncestryDNA, MyHeritage, VCF). Flow: **Upload -> Progress -> (Error | Results)**. Results = guardrail banner, QC summary, coverage-state cards, APOE card, multi-locus section, filter bar, findings table, slide-out variant drawer. No routing; one page; one drawer.

| Item | Fact |
|---|---|
| Stack | Static HTML + ES modules (no bundler); Tailwind 3.4.17 compiled to `src/vendor/tailwind.css`; daisyUI 4.12.10 vendored; app CSS `src/styles.css` |
| **Load-bearing link order** | `daisyui` -> `src/styles.css` -> `vendor/tailwind.css` (I:12-17). Utilities must come last so they beat equal-specificity app rules. Do not reorder. Guarded by `tests/e2e/test_cascade.py` (dashed dropzone, accent borders, `text-[13px]` over `.font-serif`, `dark:` over `.glass-panel`). |
| External hosts | Only Typekit (fonts), I:9. CSP `script-src 'self'`, `connect-src 'self'` (`test_csp.py`). No third-party script. |
| task.md status | Its typography/brand sections (Gotham / Attribute Mono / Orpheus Pro / Neuzeit, "High-Tech - Clinical - Crisp", sharp corners) are **PROVISIONAL**, not an established identity. |
| Test hook | `window.__genomePulse` exposes `state`, `processText`, exports, `setTheme` (A:42-48). Tests read `state.records`, `negativeChecks`, `arrayGaps`, `insufficientEvidence`, `coverageSummary`. |

## Layout

| Region | Container (de facto) | Notes |
|---|---|---|
| Body | `dna-bg-grid min-h-screen flex flex-col justify-between` (I:19) | 28px grid background (S:214-226) |
| Header | `glass-header sticky top-0 z-40 px-6 py-4 flex justify-between border-b` (I:22) | Brand left; theme toggle + 2 badges right |
| Main | `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-6` (I:59) | Sections stacked vertically |
| Order in `main` | hero/dropzone -> `#progress-section` -> `#analysis-error` -> `#results-section` | Results children: guardrail banner, QC panel (+5 KPI + 5 coverage cards), `#apoe-status-card`, `#assortment-section`, filter/search/export bar, table card |
| Drawer | `#variant-drawer` `fixed inset-y-0 right-0 z-50 w-full sm:w-[540px]`, scrolls internally (I:420) | Header, ACMG/CPIC/refusal/caveat boxes, metrics grid, phenotype, segregation + simulator, biotools, HPA, subcellular, footer |
| Footer | `glass-header px-6 py-4 mt-12` (I:698) | Static text |
| Z-order | header 40, dropdown 30, drawer 50 | No overlay/backdrop behind drawer |

## Design Tokens Used (provisional, de facto, **not a design system**)

> **Provisional - de facto, not a design system.** Values below are what the code uses today. None is endorsed.

### CSS custom properties (`src/styles.css`)

| Group | Tokens (light `:root` S:4-45 / `[data-theme="dark"]` S:47-95) |
|---|---|
| Surfaces | `--bg-canvas` #f8fafc / #070b14; `--bg-surface` #fff / rgba(15,23,42,.75); `--bg-surface-elevated` #fff / #0f172a; `--bg-surface-hover` #f1f5f9 / rgba(30,41,59,.85); `--header-bg`, `--header-border` |
| Text | `--text-main` #0f172a / #f1f5f9; `--text-muted` #475569 / #cbd5e1; `--text-subtle` #64748b / #94a3b8 |
| Borders | `--border-subtle` #cbd5e1 / rgba(255,255,255,.12); `--border-strong` #94a3b8 / rgba(255,255,255,.25) |
| Accents | `--accent-cyan` #0284c7 / #38bdf8; `--accent-emerald` #059669 / #10b981; `--accent-purple` #7c3aed / #a855f7; `--accent-ruby` #e11d48 / #f43f5e; `--accent-amber` #d97706 / #f59e0b |
| Badge classes | `--badge-{pathogenic,carrier,pgx,risk,benign}-{bg,text,border}` -> classes `.badge-pathogenic/-carrier/-pgx/-risk/-benign` (S:164-192) |
| Font vars | `--font-sans/-mono/-serif/-display`, `--editorial-size:14.5px`, `--mono-spacing:0em` - **defined only inside `[data-theme="dark"]`** (S:88-94) but consumed globally (S:106,115,120). Verify they resolve in light mode (`:root` does not define them). |

### Typography (T:10-15; S:89-92) - Typekit kit `cqu4tvx`, provisional

| Role | Family stack |
|---|---|
| sans (body) | gotham, nimbus-sans, system stack |
| mono (`.font-mono` is `!important`, S:114) | attribute-mono, ballinger-mono, azo-mono, monospace |
| serif (`.font-serif` `!important` + 14.5px, S:119) | orpheuspro, archer-pro, Georgia, serif |
| display | neuzeit-grotesk-condensed, gotham, sans-serif (`.font-display` defined; no element uses it) |

Sizes in use: `text-[9px]`, `[10px]`, `[11px]`, `[13px]`, `text-xs`, `text-sm`, `text-lg`, `text-xl`, `text-2xl`. `body letter-spacing:-0.01em` (S:110).

### Utility palette in use (Tailwind classes)

| Role (de facto) | Classes |
|---|---|
| Neutrals | `slate-50..950` |
| Primary/interactive | `sky-500/600/700` |
| Pathogenic / error | `rose-*`, `red-*` |
| Carrier / warning / guardrail | `amber-*` |
| Pharmacogenomics | `purple-*` |
| Benign / tested-WT / privacy | `emerald-*` |
| Multi-locus section | `indigo-*` |
| Header brand mark | `from-sky-600 via-indigo-600 to-purple-600` gradient |

### Shape, elevation, spacing

| Aspect | De facto |
|---|---|
| Radius | `rounded-sm` everywhere; forced `border-radius:2px !important` on `.rounded-none/.rounded-sm/.btn/.input/.badge/.tab/table/th/td/.dropdown-content` (S:150-161); `.glass-panel` 2px (S:133) |
| Panel | `.glass-panel`: surface var, `backdrop-filter: blur(16px)`, 1px border, shadow `0 1px 3px rgba(0,0,0,.05)`, hover `--border-strong` (S:129-141) |
| Accent edge | `border-l-4` on guardrail, error, APOE card, assortment, refusal box |
| Shadows | `shadow-sm`, `shadow-md`, `shadow-xl` (dropdown), `shadow-2xl` (drawer) |
| Spacing | Tailwind default scale in use: `gap-2/3/4/6`, `p-2.5/3/3.5/4/6/8/12`, `space-x-1.5/2/3/4` |
| Scrollbar | 6px, 2px radius thumb `--border-strong`, hover `--accent-cyan` (S:195-211) |
| Table viewport | `max-h-[600px] overflow-y-auto`, sticky `thead` |
| Icons | Emoji characters only (no icon system) |

Dark-mode mechanism: `data-theme` on `<html>` + Tailwind `darkMode: ['selector','[data-theme="dark"]']` (T:7) + the CSS variables above. Persisted in `localStorage["genomepulse-theme"]` (A:34,70). Default `light` (I:2 and A:34).

## Components

One entry per screen/region. State conventions: D default, H hover, F focus, A active, X disabled, L loading, E error, Em empty. "NI" = not implemented (no code for it).

### 1. Header / nav (I:22-56)

| Element | Notes | D | H | F | A | X | L | E | Em |
|---|---|---|---|---|---|---|---|---|---|
| Brand mark + wordmark + "Clinical Variome" chip + tagline | Static; mark is emoji in gradient square (`transition-all duration-300` with no changing property) | static | NI | n/a | n/a | n/a | n/a | n/a | n/a |
| `#btn-theme-toggle` | daisyUI `btn btn-sm btn-outline`; label "Dark HUD" (light) / "Light Mode" (dark) with emoji; label text `hidden sm:inline` (icon only < sm) | outline | `hover:border-sky-500` | daisyUI default only | daisyUI default | NI | NI | NI | n/a |
| "Local-First (Client-Side Only)" pill | Static; `hidden sm:flex`; green dot `animate-pulse` (I:46-47) | static | NI | n/a | n/a | n/a | n/a | n/a | n/a |
| `#redis-status-indicator` "Redis Edge Ready" | **Static text; no code updates it** (no reference in A). Not tied to any real state. | static | NI | n/a | n/a | n/a | n/a | n/a | n/a |

### 2. Upload and dropzone (I:62-98; A:170-220)

| Element | D | H | F | A | X | L | E | Em |
|---|---|---|---|---|---|---|---|---|
| `#dropzone` (div; click opens file dialog; ignores clicks on button/a, A:202) | dashed 2px `slate-300` / dark `slate-700`, `bg-white` / dark `slate-900/40` | `hover:border-sky-500`; icon `group-hover:scale-105` | **NI** (div, no tabindex, not keyboard reachable) | NI | NI (not disabled while analysing) | NI | see Analysis error | n/a |
| Drag-over | adds `border-sky-500 bg-sky-500/10` on `dragover`, removed on `dragleave`/`drop` (A:171-184). Only first dropped file used | | | | | | | |
| `#file-input` (hidden, `accept=".txt,.csv,.vcf,.tsv,.gz"`) | hidden | n/a | n/a | n/a | `disabled` while analysing (A:143-148) | n/a | n/a | n/a |
| `#btn-browse-files` (daisyUI `btn-primary`, `bg-sky-600 hover:bg-sky-700`) | filled | darker | daisyUI default | daisyUI default | **NI** (not disabled while analysing) | NI | NI | n/a |
| `#btn-load-demo` (`btn-outline`) | outline | `hover:border-sky-500`, text sky | daisyUI default | daisyUI default | `disabled` while analysing | NI (no spinner on button) | blocking `alert()` on fetch failure (A:216-218, 1212) - in flight to change (T9) | n/a |
| Source/dataset chips (ClinVar 2026.1, ACMG SF v3.2 (81 Genes), HPA, CPIC) | static text, emoji | | | | | | | |

### 3. Progress (I:101-114; A:285-292)

| Element | Fact |
|---|---|
| Visibility | `#progress-section` `hidden` until `processText` removes it; hidden again on error/complete |
| Message `#parse-progress-msg` | daisyUI `loading loading-spinner loading-xs` + text; replaced by worker `status` strings. `textContent =` on the span **removes the spinner element** on the first update (A:290; the spinner is a child of that span, I:104) |
| Percent `#parse-progress-pct` | `${percent}%` |
| Bar `#parse-progress-bar` | `width: N%`, gradient sky-500 -> indigo-600, `transition-all duration-150`; track `h-2` |
| Watchdog | 30000 ms inactivity (A:15), re-armed on each progress message; failure -> Analysis error |
| States | D/L implemented; H/F/A/X n/a (non-interactive); E -> separate alert; Em n/a. **No cancel control (NI).** |

### 4. Analysis error alert (I:117-120; A:150-157)

| Fact | Detail |
|---|---|
| Element | `#analysis-error`, `role="alert"` (asserted in `test_web_smoke.py`), red surface, `border-l-4 border-red-500` |
| Copy (fixed) | "The analysis could not be completed. Nothing was uploaded, and no results are shown. Please try again, or try a different file." + `Technical detail: <span id="analysis-error-detail">` (raw message via `textContent`) |
| Triggers | worker `onerror` / `onmessageerror` / `type:"error"` message / watchdog timeout / unsupported format (text contains "unsupported") / KB fetch 500 |
| Required behaviour (tests) | hidden until an analysis starts; on failure: alert visible, progress hidden, results hidden, inputs re-enabled; cleared at next run start; retry recovers; worker terminated per run |
| Second error path (to be retired) | `showError()` -> blocking `alert("GenomePulse Processing Notice: ...")` for FileReader failure and demo fetch failure (A:216-218, 271-273, 1212-1214). See Pending |
| States | D hidden; visible = E; no dismiss control (NI); no focus move on appearance (NI) |

### 5. QC summary (I:137-167; A:363-379)

| Element | Fact |
|---|---|
| `#qc-filename` | `textContent` of file name |
| Chips | Format (`FORMAT (build)`), Markers (`toLocaleString`), Call Rate (green text class), Heterozygosity, Sex-chromosome QC badge |
| Missing rate | `null` -> text "Not available", `title` = `qc.qc_note` (A:359-372). Call Rate keeps its green text class even when "Not available" - verify |
| Sex badge | Shows `qc.sex_signal` verbatim, e.g. "Indeterminate (too few X markers)" (`test_formats.py`); `title` = X markers / X het / Y calls. **Must not claim sex or karyotype.** |
| Placeholders | "sample.txt", "—" are pre-render defaults only |
| States | Non-interactive; hover only for `title` tooltips (not keyboard reachable) |

### 6. Coverage-state cards (5-state taxonomy) (I:203-248; A:381-406)

| # | Card label (current) | Subtitle (current) | Count source | Tone classes |
|---|---|---|---|---|
| 1 | Observed | "Supported & observed" | `supported_and_observed_count` | sky |
| 2 | Tested WT | "Supported, normal" | `supported_not_observed_count` | emerald |
| 3 | Array Gaps | "Omitted from chip" | `not_tested_by_array_count` | amber |
| 4 | Outside Scope | "Markers uncurated" | `outside_coverage_count` | slate |
| 5 | Conflicting | "Disputed / Tier C" | `insufficient_evidence_count` | rose |

- Static `State 1..5` pill on each card. Cards are **not** interactive (no click-to-filter); the filter tabs are the only way into states 2, 3, 5. State 4 has **no table view** (NI).
- `renderSummaryCards` uses fallbacks like `?? state.records.length` (A:393-405): silent defaults, flagged by AGENTS.md section 3; T9 moves counts to the worker `summary`.
- Wording conflict with AGENTS.md section 4.1: card 2 subtitle "Supported, normal" and label "Tested WT" use "normal" for a not-detected result. See Pending T9 wording rule.
- `test_each_locus_is_counted_in_exactly_one_state`: states 1,2,3,5 sum to `total_loci`.

### 7. Category cards (I:170-200; A:381-389)

Five KPI cards: Pathogenic (rose), ACMG SF v3.2 (sky), Pharmacogenomics (purple), Carrier Status (amber), Elevated Risk (red). Counts from `state.summary.*` (`pathogenic_count`, `acmg_actionable_findings`, `pgx_count`, `carrier_count`, `risk_factor_count`). Grid `grid-cols-2 sm:grid-cols-3 lg:grid-cols-5`. Non-interactive. Subtitle text static ("High clinical priority", "Recessive & APOE alleles").

### 8. APOE card (I:252-295; A:408-456)

| Aspect | Current behaviour |
|---|---|
| Visibility | `hidden` unless `state.apoe` truthy |
| Fields | Title `APOE <diplotype> (<label>)`; risk-ratio badge; narrative; raw-loci string; lifetime-risk stat; static "Actionable Modulation" and "HPA Proteomic Abundance" text (**hard-coded in HTML, identical for every genotype**, I:288,292) |
| Variants by diplotype | e4/e4: rose `border-l-4`, `badge-pathogenic`, pill "High Risk Locus"; any other e4: amber, `badge-carrier`, "Carrier Status"; any e2: purple, `badge-pgx`, "Neuroprotective / Carrier"; else emerald, `badge-benign`, **"Normal Baseline"** (A:434-455) |
| Button `#btn-inspect-apoe` | `btn-outline border-sky-500`; opens drawer for the APOE record; no-op if none found |
| Missing component / atypical / indeterminate | **Not implemented**: card hidden if no `state.apoe`; no indeterminate state exists today (see Pending T7) |
| Honesty gap | "Normal Baseline" contradicts AGENTS.md section 4.1 (T9 test bans it) |

### 9. Multi-locus (assortment) section (I:298-327; A:458-552)

Hidden when 0 findings. Badge `N Multi-Locus Finding(s)`. Cards built by `innerHTML` from worker data: **Compound heterozygote** ("Trans Phase Compound Heterozygote" label, `badge-pathogenic` significance) and **Independent assortment** (genes, loci, "Offspring Joint Probability" shown as `Math.round(p*100)% (0.50 × 0.50)`). Each card has "Inspect <gene>" `btn-xs btn-outline` buttons that open the drawer if a record exists. **"Trans phase" asserts phase on unphased data** (flagged in `test_segregation_biotools.py` docstring and T8). Pending T8.

### 10. Findings table with filters and search (I:331-414; A:228-240, 554-680)

| Element | Fact |
|---|---|
| Filter tabs (9) | `data-filter`: all "Observed Findings", negative "Tested Wild-Type (State 2)", gaps "Array Gaps (State 3)", insufficient "Conflicting Evidence (State 5)", carrier, pathogenic, acmg, pgx, risk. Plain `<button>`s in an `overflow-x-auto` strip |
| Tab states | D: `text-slate-600 dark:text-slate-400`; H: `hover:text-slate-900` + `transition-colors`; Active: `tab-active bg-sky-600 text-white` (dark: `bg-sky-500/20 text-sky-300`, sky border) toggled by JS class swap; **no `aria-selected`/`aria-pressed`** (NI); F: browser/daisy default only; X/L/E/Em: NI |
| Dataset selection | all/pathogenic/carrier/pgx/risk/acmg filter `state.records`; negative -> `negativeChecks`; gaps -> `arrayGaps`; insufficient -> `insufficientEvidence` |
| Search `#search-input` | daisyUI `input input-sm`, `focus:border-sky-500`, placeholder "Search rsID, gene, drug…", live on `input`; matches rsid, gene, phenotype, genotype, category, significance, drug_response, APOE info. No `<label>`, no clear button (NI) |
| Count `#showing-count` | "Showing N of M clinical findings" / state-specific strings (A:593-601); not `aria-live` |
| Columns (8) | rsID, Gene (+ACMG pill), Genotype, Coverage State badge, Tier / Category, ClinVar (stars), Magnitude (+repute; `text-rose` if >= 4), Clinical Guidance (truncated `max-w-md`, `title` tooltip) |
| Row states | D: `cursor-pointer`; H: `hover:bg-slate-50/80` / dark `slate-800/40`, plus global `tbody tr:hover` `--bg-surface-hover !important` (S:233); F/A/X: **NI** (rows not focusable; `onclick` only, no Enter/Space) |
| Empty | One row `colspan=8` "No variants match your search or filter." with emoji tile |
| Loading | NI (table is not shown during progress) |
| Sorting | `state.sortBy="magnitude"` exists (A:32) but there is **no sort UI and no sort applied** in `renderVariantsTable` |
| Row badges | Coverage-state: Observed (sky) / Tested WT (emerald) / Array Gap (amber) / Conflicting (rose); Tier A sky / B emerald / C amber / D slate; Category via `.badge-*`; unknown tier defaults to "Tier B" (A:638, silent default, T9 removes) |

### 11. Variant drawer (I:420-695; A:682-843, 1069-1072)

| Element | Fact |
|---|---|
| Open | Row click, "Inspect" buttons (APOE card, assortment cards): removes `translate-x-full` |
| Close | `#btn-close-drawer` (daisyUI `btn-circle btn-ghost`, "✕"): adds `translate-x-full`. **No Escape key, no backdrop click, no focus trap, no focus return** (no `keydown`/`Escape`/`aria-*`/`inert` in A or I) |
| Closed state | Off-canvas via transform only; contents remain in tab order and accessibility tree (NI: `inert`/`aria-hidden`/`visibility`) |
| Header | rsID (sky, `text-2xl font-black`), gene, coordinates `chr<chrom>:<pos>`, Tier badge, Coverage-state badge |
| Coverage badge labels | "Supported & Observed", "Tested Wild-Type (State 2)", "Array Gap (State 3)", "Conflicting Evidence (State 5)"; any other value prints the raw key (A:737) |
| Conditional boxes | ACMG (sky; "does not independently evaluate ACMG/AMP 2015" wording), CPIC drug alert (purple, with single-SNP caveat text), **Star-allele refusal** (purple, shown if `record.limitation` or category = Pharmacogenomics, A:742-754), **Scientific caveats** list (slate); each toggled with `hidden` |
| Metrics grid | Genotype, ClinVar Stars ("— (0 / 4 stars)" when none), Magnitude / Repute ("x / 10.0 (Neutral)" default), gnomAD AF ("N/A (Not characterized)" when null) |
| Phenotype | "Clinical Significance & Phenotype" + serif paragraph |
| Segregation panel | Mode badge (amber recessive / rose dominant / purple other / sky default); Carrier prior, Penetrance, Risk vs Unscreened, Risk vs Carrier; if no `segregation`: "Complex", "N/A", "Variable" (A:854-862) |
| Offspring simulator | 4 buttons `Unscreened / Carrier / Affected / Wild-Type` (`partner-sim-btn`, `grid-cols-4`). D: white / bordered; H: `hover:border-sky-500`; selected: `bg-sky-600 text-white shadow-sm`, swapped by `className` rewrite; F: browser default; X/L/E: NI; no `aria-pressed`. Output: three probability bars + "Effective Penetrance Adjusted". Resets to "Unscreened" each time the drawer opens. Inputs today = partner status + gene only (`simulateOffspringPedigree(gene, partner)`, A:913); the patient's genotype is **not** an input (changes in T8) |
| Biotools panel | AlphaFold DB (UniProt chip, pLDDT chip toned by value: >=85 emerald, >=70 sky, else amber, N/A slate; status; domains; joints), Ensembl VEP (transcript chip, AlphaMissense, LOEUF with text band), ENCODE (TPM bars). With no insights: placeholder strings "UniProt Search", "MANE Select Pending", "Score Available in API", "Constraint Available" (A:953-963) presented as if data; flagged by AGENTS.md section 3 (T9) |
| HPA | Tissue rows with level pill (High emerald / Medium amber / other sky); empty copy "Normal protein abundance widely expressed across human tissues."; subcellular chips, empty copy "Cytosol / Nucleus" (invented default, A:838) |
| Footer | "Open ClinVar Record ↗" (`<a target=_blank rel="noopener noreferrer">`, hidden if no accession; hard-coded APOE fallback link variation/17864, A:793); static text "Evidence Tier 1" (I:693) regardless of record, **not data-driven** |

### 12. Exports (I:376-384; A:1074-1210)

| Element | Fact |
|---|---|
| Control | daisyUI `dropdown dropdown-end`; trigger `div tabindex=0 role=button` "Export ▾"; `ul.menu` with `<a>` items **without `href`** (Markdown Report, CSV Dataset); opens via CSS focus (daisyUI) |
| States | D/H (`hover:bg-slate-100`)/F (daisyUI focus-within); X: **NI**, handlers silently return if no records (A:1075), not visually disabled; L/E/Em: NI; control exists only inside `#results-section` |
| Markdown | Title, guardrail text from `state.manifest.guardrail`, sample/QC line, 5-state summary, APOE, multi-locus, three tables (observed, tested WT, array gaps). File `GenomePulse_Report_<ts>.md` |
| CSV | 19 columns incl. Coverage_State, Evidence_Tier, Refusal_Notices, Caveats. Rows = records + negativeChecks + arrayGaps (not insufficientEvidence). Silent fallbacks (`'Tier B'`, magnitude `0`, `'Neutral'`, stars `0`; Markdown `"★".repeat(stars || 1)`) are placeholders-as-data (T9). File `GenomePulse_Variants_<ts>.csv` |
| Required (AGENTS.md 4.6) | Single-variant-test limitations appear in every export; today caveats/refusals appear in CSV only |

### 13. Dark mode ("Dark HUD")

| Fact | Detail |
|---|---|
| Trigger | `#btn-theme-toggle`; icon/label swap (🌙 "Dark HUD" <-> ☀️ "Light Mode") |
| Mechanism | `data-theme` on `<html>`; Tailwind `dark:` variants (selector strategy); CSS variable block `[data-theme="dark"]` |
| Persistence | `localStorage` key `genomepulse-theme`; **no `prefers-color-scheme` handling**; read/write not wrapped in try/catch (A:34,70) |
| Transition | `body` colour 0.2s ease; `#dropzone` `transition-all duration-200` (test waits 600 ms) |
| Test coverage | `test_theme_toggle_round_trip`; `test_dark_utilities_beat_glass_panel` (dropzone alpha 0.4, not `.glass-panel` 0.75) |

## States and Interactions

### Global flow (encoded by tests)

| State | UI | Entry | Exit |
|---|---|---|---|
| Idle | dropzone only; progress, error, results hidden | page load | file chosen / dropped / demo click |
| Reading | progress 5% "Reading <name> (x MB)..." | `handleFileSelected` | FileReader load -> Analysing; FileReader error -> `alert()` (see Pending) |
| Analysing | progress shown; results hidden; error hidden; file input + demo button disabled | `processText` | `complete` -> Results; failure -> Error |
| Results | progress hidden; results shown; inputs re-enabled | `complete` | new run (results hidden at start) |
| Error | progress hidden; results hidden; alert visible; inputs re-enabled | any failure | next run clears it |

### Clinical-honesty states the design system MUST provide

Requirements only (what must be distinguishable), not visual treatments. Sources: AGENTS.md sections 3-5, coverage keys in `app.js`.

| # | Requirement | Current mapping |
|---|---|---|
| H1 | **Supported and observed** (`supported_and_observed`): alt allele present among variants tested | "Observed" / "Supported & Observed" |
| H2 | **Supported, not observed**: wording is *"not detected among the N variants tested"*; never "normal" or any statement of absent risk (4.1) | "Tested WT" / "Supported, normal" - **wording currently conflicts** |
| H3 | **Not tested by array** (`not_tested_by_array`): locus absent from the file or a no-call; shows reason | "Array Gap" |
| H4 | **Outside coverage** (State 4): markers present but uncurated; counted only, no per-row view today | "Outside Scope" count |
| H5 | **Insufficient evidence** (`insufficient_evidence`): conflicting, Tier C/D, or unresolvable genotype; fail-closed results land here, never "wild-type" | "Conflicting" (label implies only conflict; the key also covers atypical/indeterminate) |
| H6 | **"Not available"** for missing data, muted, never a placeholder value or invented default (section 3) | Only for QC rates today; elsewhere placeholders (see Edge cases) |
| H7 | **Limitation / caveat badge** on the row, in the drawer and in exports for single-variant tests of multi-variant genes (DPYD, CFTR, CYP2C19 star alleles, ACMG SF loci) (4.6) | Drawer refusal box + caveat list only; **no row badge** |
| H8 | **Insufficient-evidence badge** distinct from category badges, shown beside a category when a variant is present | Not implemented as a separate badge |
| H9 | **Phase-unknown wording** where unphased genotypes could be cis or trans (compound het, APOE e2/e4) | Not implemented; current UI asserts "Trans Phase" |
| H10 | **Global scope guardrail**: absence of a finding is not absence of risk, visible with results and in Markdown | `#coverage-guardrail-banner` (amber, static copy) |
| H11 | **Fail visibly**: worker/KB/parse errors surface in the alert, never swallowed (section 3) | `#analysis-error` |
| H12 | **Offspring/recurrence figures** only for Mendelian disease loci, from the patient's genotype and a stated partner model; trait/PGx loci show allele-transmission wording only (4.4) | Not yet (T8) |
| H13 | **Provenance never fabricated**: no invented versions or retrieval dates (4.5) | Static strings "ClinVar 2024-06 / dbSNP 156" (KB badge, footer) vs hero "ClinVar 2026.1" disagree; **to verify against KB** |
| H14 | **Privacy affirmation** visible; no third-party script; data never leaves the browser (section 5) | Header pill + footer text (static) |

## Responsive Behavior

Breakpoints actually used (Tailwind defaults: sm 640, md 768, lg 1024):

| Breakpoint | Behaviour (source) |
|---|---|
| < sm | Header toggle label hidden (I:43); "Local-First" pill hidden (I:46); drawer `w-full`; category cards 2 cols; coverage cards 2 cols; hero `p-8`; footer stacked |
| sm (640) | Toggle label + privacy pill shown; drawer `w-[540px]`; category cards 3 cols; coverage cards 5 cols; hero `p-12`; main `px-6`; APOE button row `flex-row`; assortment header `flex-row` |
| md (768) | QC header `flex-row`; filter/search bar `flex-row`; APOE detail 3 cols; assortment cards 2 cols |
| lg (1024) | Category cards 5 cols; APOE header `flex-row`; main `px-8` |
| Overflow | Filter strip `overflow-x-auto`; table `overflow-x-auto` (8 columns, no column hiding); `body overflow-x:hidden` (S:109) |
| Not implemented | No `xl:`/`2xl:` classes; header never wraps (no mobile menu); search `sm:w-64` only; simulator stays 4 columns at all widths (tight < 400px, to verify); e2e tests run only at 1440x900 (`conftest.py:68`) |

## Edge Cases

| Case | Current behaviour |
|---|---|
| Variants-only VCF (no call rate) | "Not available" + `title` note |
| Unsupported / garbage / empty file | Error alert containing "unsupported"; no NaN/Infinity on empty file (`test_web_adversarial.py`) |
| Header row in Ancestry file | Not counted as SNP (`test_formats.py`) |
| XSS payload in rsID | Test asserts no execution; table, cards and caveat list are built with `innerHTML` from data (A:605-677, 483, 511, 763), relying on CSP and sanitised data; **to verify** |
| Wild-type loci | Not in `records`; reachable only via "Tested Wild-Type" tab (`test_classification.py`) |
| APOE components | Never separate rows; one APOE row + card |
| No matches for search/filter | Empty row message |
| Long phenotype text | `truncate max-w-md` with `title` |
| KB fetch failure / worker failure / silent worker | Error alert; watchdog 30 s |
| Healthy slow progress | Watchdog re-armed per progress message; no false timeout |
| Placeholder-as-data (rendered today) | "MANE Select Transcript", "MANE Select Pending", "Score Available in API", "Constraint Available", "N/A (Non-missense)", "N/A (Not characterized)", "Domain boundaries computed from PAE matrix.", "Cytosol / Nucleus", "Tier B"/"Tier D" defaults, "Neutral", "★" minimum 1 in Markdown, "Evidence Tier 1" footer |
| Gap / not-tested row fields | Genotype "—"; phenotype/significance fall back to `rec.reason` (A:308-311) |
| Multiple files dropped | First only, silently |
| Drawer open + new analysis | Drawer not closed on a new run (NI) |

## Animation / Motion

| Where | Class / rule | Duration / easing |
|---|---|---|
| Drawer slide | `translate-x-full` toggled; `transition-transform duration-300 ease-in-out` (I:420) | 300 ms ease-in-out |
| Progress bar width | `transition-all duration-150` (I:111) | 150 ms (Tailwind default easing) |
| Simulator bars | `transition-all duration-300` (I:562 etc.); JS clamps width to min 1% (A:919) | 300 ms |
| Simulator buttons | `transition-all` | Tailwind default 150 ms |
| Dropzone | `transition-all duration-200`; hero icon `group-hover:scale-105 transition-transform duration-200` | 200 ms |
| Hero section / brand mark | `transition-all duration-300` | 300 ms (no changing property) |
| Filter tabs | `transition-colors` | default 150 ms |
| Table rows | `transition-colors` + `tbody tr {transition: background-color .1s ease}` (S:229) | 100 ms |
| `.glass-panel` | `transition: border-color .15s ease, box-shadow .15s ease` (S:136) | 150 ms |
| APOE card | `transition-all duration-200` | 200 ms |
| Body theme | `transition: background-color .2s ease, color .2s ease` (S:111) | 200 ms |
| Privacy pill dot | `animate-pulse` (infinite) | continuous (Tailwind default 2 s) |
| Spinner | daisyUI `loading loading-spinner` | continuous |
| Reduced motion | **No `prefers-reduced-motion` handling anywhere (NI)** | |

## Accessibility Notes

Factual audit from code; "to verify" = cannot be proven without rendering.

| Area | Present | Missing / risk |
|---|---|---|
| Language/title | `<html lang="en">`, descriptive `<title>` | n/a |
| Landmarks | `<header>`, `<main id="main-content-flow">`, `<aside id="variant-drawer">`, `<footer>` | No skip link; `<aside>` has no label |
| Live regions | `#analysis-error` has `role="alert"` (the only `role`/`aria-*` the app adds, besides dropdown `role=button`) | `#showing-count`, progress percent/message, results arrival: no `aria-live`/`role=status`; no `aria-busy` |
| Headings | `h1` brand, `h2` hero, `h3` panels/drawer, `h4` in cards | Hero `h2` persists after results; drawer uses `h3` for rsID; outline per state: verify |
| Dropzone | Contains real buttons (browse, demo), so the action is keyboard-operable | The dropzone div itself is mouse-only; hidden `file-input` has no label |
| Filter tabs | Native `<button>`s (Tab/Enter/Space work) | No `role=tablist/tab`, no `aria-selected`/`aria-pressed`; active state conveyed by colour/class only |
| Search | Native input, placeholder | No `<label>` or `aria-label`; emoji icon not hidden from AT |
| Table | Real `<table>`, `<thead>`, `<th>` | No `scope`, no caption; rows clickable via `tr.onclick` only: **not keyboard operable**, no `role`/`tabindex`; sticky header |
| Drawer | Close is a native `<button>` | "✕" button has no accessible name; no `role=dialog`/`aria-modal`/`aria-labelledby`; **no Escape, no focus move on open, no focus trap, no focus return**; closed drawer still focusable (off-canvas by transform); no backdrop |
| Simulator buttons | Native buttons | No `aria-pressed`; selection by colour only; results not announced |
| Export dropdown | daisyUI focus-based menu; trigger has `role=button tabindex=0` | `<a>` items without `href` are not focusable by default; keyboard operability: verify |
| Theme toggle | Native button with text label (>= sm) | Icon-only below sm: no `aria-label` |
| Colour-only meaning | Badges carry text labels | Bars (simulator, ENCODE) rely on colour + adjacent number |
| Focus ring | daisyUI/browser defaults only; no custom `:focus-visible` in `styles.css` | Visibility on all backgrounds, in dark mode: to verify |
| Contrast (to verify) | - | `text-[9px]`/`[10px]` labels in `text-slate-400`/`slate-500` on white/slate-50 (I:283,288,291,524, "Select Partner Status"); `text-slate-400` "or" on white; `text-amber-500` stars on white; `text-white` on `bg-sky-600`; `text-emerald-600` on white; dark `text-slate-500` on `slate-900/60` (I:210 etc.); muted text on translucent glass over the grid |
| Touch targets | - | `btn-sm`/`btn-xs`, 11px tabs, `btn-circle btn-sm` close: likely below 44px, to verify |
| Motion | - | `animate-pulse` and spinner with no reduced-motion override |
| Emoji | Used as icons/labels | Read aloud by screen readers; not marked `aria-hidden` |
| Tooltips | `title` on QC rates, sex badge, KB badge, truncated phenotype | Not available to keyboard/touch |
| External link | `rel="noopener noreferrer"` | n/a |

## Pending changes (in flight, not yet on this branch)

> Sourced from briefs `T7.md`, `T8.md`, `T9.md` in `.superpowers/sdd/2026-10-02-genomepulse-hardening/briefs/`. None of this is current behaviour; briefs may change.

### T7 - APOE card states (`core/apoe.js`; card renders KB values)

| e4 alt count | e2 alt count | Diplotype | State |
|---|---|---|---|
| 0 | 0 | e3/e3 | supported_not_observed, wild_type |
| 1 | 0 | e3/e4 | supported_and_observed |
| 2 | 0 | e4/e4 | supported_and_observed |
| 0 | 1 | e2/e3 | supported_and_observed |
| 0 | 2 | e2/e2 | supported_and_observed |
| 1 | 1 | e2/e4 with caveat "phase unknown: e1/e3 is the rare alternative" | supported_and_observed |
| 2/1, 1/2, 2/2 | | atypical: "requires an e1-type haplotype; cannot be resolved from genotype array data" | insufficient_evidence, variant_present |

- A missing, no-call or unresolvable component asserts **no diplotype**: state `not_tested_by_array` or `insufficient_evidence` carrying the component's reason; never wild-type, never "presumed e3".
- Card renders diplotype, state, caveat and KB-sourced numbers; no hard-coded APOE values (stars, af, magnitude, ClinVar link). Component SNP records attach as `components`; the APOE finding is the only APOE row; coverage cards count it once.
- e2e: CC/CT fixture shows indeterminate wording not "Tested Normal"; rs429358-only shows "not tested"; demo still shows e4/e4.

### T8 - Offspring simulator inputs and wording (`core/inheritance.js`)

- Simulator inputs become **patient alt-allele count + partner model** (wildtype 0, heterozygous 0.5, homozygous 1, unscreened = population af from KB). Old partner-only API removed. If af is null, the "unscreened" model is **unavailable and says so**, no default.
- Output is a distribution of alt alleles in the child; wording depends on the KB inheritance model:
  - Mendelian recessive: affected / carrier probabilities.
  - Mendelian dominant: affected = (het + hom) x penetrance; null penetrance -> unavailable.
  - Any other model (trait, risk, PGx): allele-transmission only, worded "chance a child inherits the <allele> allele"; **never** "affected", "recurrence" or "disease risk".
- Patient status `is_affected`/`is_carrier` exist only for Mendelian loci; wild-type is never affected.
- Multi-locus findings: only loci with alt count > 0 on different chromosomes; labelled "assumes unlinked loci and a partner without these alleles"; "combined thrombophilia" text only from KB.
- Compound heterozygosity: "possible compound heterozygote: phase unknown (cis or trans cannot be determined from unphased genotypes)"; never "trans".
- e2e: APOE e4/e4 drawer shows 100% chance a child inherits e4 and no "affected" wording; wild-type F5 shows no affected status and no 50%; CSV has no `0.5` risk for wild-type loci.

### T9 - Single view-model and honest rendering (`web/src/view-model.js`)

- One `toViewModel(record, genes)` feeds table, drawer, Markdown and CSV; no view formats a clinical field itself.
- **"Not available"** rendered as text in a **muted style** for any missing value; exports write an empty cell plus a `missing_fields` column. All `||` clinical fallbacks deleted (placeholder strings in Edge cases, tier defaults, `"★".repeat(stars || 1)`).
- Stars rendered exactly from evidence, or "No ClinVar review status". ClinVar links only when accession provenance is `machine_imported`. Tier identical across views.
- Gap / not-tested rows show state label and reason; "undefined" never appears.
- **Limitation badges**: row badge with tooltip, drawer, and both exports; CYP2C19 star-allele refusal on the row; DPYD/CFTR "only one variant tested" wherever a not-detected result is shown.
- Not-detected wording: "<allele> not detected (1 of N known variants in <gene> tested)"; never "Normal" or "Tested Normal"; "Normal Baseline" banned in page text and exports.
- Coverage cards use the worker `summary` only; category cards count only `sample_observation == variant_present`; insufficient-evidence records with a variant present show the insufficient-evidence badge.
- **One error path**: `showError()`/`alert()` deleted; every error (including FileReader failure) goes through `showAnalysisError()` into `#analysis-error`; e2e for FileReader failure.
- e2e `test_ui_honesty.py`: page text, Markdown and CSV downloads contain none of `undefined`, `null`, `NaN`, the placeholder strings, "Tested Normal", "Normal Baseline".

## Open questions for the design system

Decisions the design-system author must take; no values are recommended here.

1. **Identity**: is the brand (name treatment, emoji mark, "Clinical Variome" chip, tagline) established, and what stands in for the emoji icons and the 🧬 mark?
2. **Typography**: does Typekit kit `cqu4tvx` (gotham, attribute-mono, orpheuspro, neuzeit) remain, given Typekit is the only external host in the CSP? Which roles (sans/mono/serif/display) exist, and should `.font-mono`/`.font-serif` keep `!important`? Should font variables live in `:root` rather than only `[data-theme="dark"]`?
3. **Dark mode**: is `data-theme` + Tailwind `selector` the final mechanism? Should it follow `prefers-color-scheme`? Is the name "Dark HUD" kept? How is persistence handled when storage is blocked?
4. **daisyUI role**: which daisyUI components (`btn`, `input`, `dropdown`, `menu`, `loading`, `btn-circle`) are in the system and which are overridden (forced 2px radius, utility colour overrides)? Which daisyUI theme applies (none is configured)?
5. **Badge semantics**: what do the colour families mean, given today's reuse (amber = carrier, warning, State 3, Tier C, guardrail, "Medium"; rose/red = pathogenic, risk, conflicting, error; emerald = benign, tested WT, Tier B, privacy; sky = observed, Tier A, primary action, selected)? Are category, coverage state, evidence tier, severity and UI chrome one vocabulary or several?
6. **Honesty states**: how are H1-H5 distinguished without relying on colour alone, and how is "not detected" kept distinct from "normal"? Where do H7/H8 (limitation badge, insufficient-evidence badge) sit relative to category and tier badges on a row?
7. **State 4 (outside coverage)**: a count only, or a navigable view?
8. **"Not available"**: one muted treatment for all contexts (table cell, drawer metric, QC chip, exports), and what is its reason/tooltip affordance?
9. **Interactive semantics**: are table rows buttons, links or selectable rows? Are filter tabs a tablist or a toggle group? Should the dropzone itself be a focusable control?
10. **Drawer**: modal dialog or non-modal panel? Escape/backdrop/focus-return expectations? Does it close on a new analysis? Small-screen behaviour?
11. **Error pattern**: single alert region only, or also inline errors? Dismissible? Does focus move to it?
12. **Counts vs states**: should coverage cards act as filters? How are "Observed" findings and category cards (subsets) explained so totals are not misread?
13. **Static claims**: header "Redis Edge Ready", KB badge "ClinVar 2024-06", hero "ClinVar 2026.1" and footer "Evidence Tier 1" are static text. Which should be data-driven from the KB manifest, and which dropped?
14. **Responsive scope**: which viewports are supported (tests cover only 1440x900)? How should the 8-column table behave at narrow widths?
15. **Motion**: which transitions are intentional (several carry no changing property), and what is the reduced-motion policy?
16. **Density and sizes**: are 9-11px text and `btn-xs/sm` targets acceptable for this audience, and what are the minimum text and target sizes?
17. **Export parity**: should Markdown/CSV exports share the UI's badge vocabulary?
