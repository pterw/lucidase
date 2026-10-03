# Handoff Spec: Lucidase web app (provisional UI)

> **BANNER - READ FIRST.** This document records the **current, provisional UI as built** on branch `fix/genomepulse-hardening`, plus the behavioural, state and clinical-honesty requirements any future design system must satisfy.
> Owner ruling (verbatim): *"Webdev and identity haven't been established so when tailwind and daisy ui land properly and install design of this is within a system that is yet to be authored."*
> It proposes **no** new colours, fonts, spacing scales, themes or components. Every visual value below is a **de facto** value found in code, not a design decision. Citations are `file:line`.

Sources: `web/index.html` (I), `web/src/app.js` (A), `web/src/view-model.js` (V), `web/src/core/apoe.js` (C), `web/src/worker.js` (W), `web/src/styles.css` (S), `web/tailwind.config.js` (T), `web/src/vendor/README.md`, `AGENTS.md` sections 3-5, `task.md` (provisional), `tests/e2e/*.py`. The I, A, V, C and W line numbers were re-checked at the final commit of the hardening branch (T7, T8 and T9 have landed). The S and T cites were not re-measured.

---

## Overview

Single-page, client-only analysis of raw DNA files (23andMe, AncestryDNA, MyHeritage, VCF). Flow: **Upload -> Progress -> (Error | Results)**. Results = guardrail banner, QC summary, coverage-state cards, APOE card, multi-locus section, filter bar, findings table, slide-out variant drawer. Every table row, drawer field and export value is read from one view model per record (V:131-268; A:8-10). No routing; one page; one drawer.

| Item | Fact |
|---|---|
| Stack | Static HTML + ES modules (no bundler); Tailwind 3.4.17 compiled to `src/vendor/tailwind.css`; daisyUI 4.12.10 vendored; app CSS `src/styles.css` |
| **Load-bearing link order** | `daisyui` -> `src/styles.css` -> `vendor/tailwind.css` (I:12-17). Utilities must come last so they beat equal-specificity app rules. Do not reorder. Guarded by `tests/e2e/test_cascade.py` (dashed dropzone, accent borders, `text-[13px]` over `.font-serif`, `dark:` over `.glass-panel`). |
| External hosts | Only Typekit (fonts), I:9. CSP `script-src 'self'`, `connect-src 'self'` (`test_csp.py`). No third-party script. |
| task.md status | Its typography/brand sections (Adobe Fonts kit gfe3vcu: sans Akzidenz-Grotesk Next Pro, serif Orpheus Pro, mono Input Mono, display Swiss 721 BT Condensed; "High-Tech - Clinical - Crisp", sharp corners) are **PROVISIONAL**, not an established identity. |
| Test hook | `window.__lucidase` exposes `state`, `processText`, exports, `setTheme` (A:65-71). Tests read `state.records`, `negativeChecks`, `arrayGaps`, `insufficientEvidence`, `coverageSummary`. |

## Layout

| Region | Container (de facto) | Notes |
|---|---|---|
| Body | `dna-bg-grid min-h-screen flex flex-col justify-between` (I:19) | 28px grid background (S:214-226) |
| Header | `glass-header sticky top-0 z-40 px-6 py-4 flex justify-between border-b` (I:22) | Brand left; theme toggle + the Local-First pill right (I:41-50) |
| Main | `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-6` (I:54) | Sections stacked vertically |
| Order in `main` | hero/dropzone -> `#progress-section` -> `#analysis-error` -> `#results-section` | Results children: guardrail banner, QC panel (+5 KPI + 5 coverage cards), `#apoe-status-card`, `#assortment-section`, filter/search/export bar, table card |
| Drawer | `#variant-drawer` `fixed inset-y-0 right-0 z-50 w-full sm:w-[540px]`, scrolls internally (I:409) | Header, ACMG/CPIC/refusal/caveat boxes, metrics grid, phenotype, segregation + simulator, biotools, HPA, subcellular, footer |
| Footer | `glass-header px-6 py-4 mt-12` (I:686) | Static text (I:688-690): no release, source or tier claims |
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

### Typography (T:10-15; S:89-92) - Typekit kit `gfe3vcu`, provisional (kit and mapping chosen by the owner, 2026-10-03)

| Role | Family stack |
|---|---|
| sans (body) | akzidenz-grotesk-next-pro, system stack |
| mono (`.font-mono` is `!important`, S:114) | input-mono, ui-monospace, monospace |
| serif (`.font-serif` `!important` + 14.5px, S:119) | orpheuspro, Georgia, serif |
| display | swiss-721-bt-condensed, akzidenz-grotesk-next-pro, sans-serif (`.font-display` defined; no element uses it) |

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

Dark-mode mechanism: `data-theme` on `<html>` + Tailwind `darkMode: ['selector','[data-theme="dark"]']` (T:7) + the CSS variables above. Persisted in `localStorage["lucidase-theme"]` (A:56, 93). Default `light` (I:2 and A:56).

## Components

One entry per screen/region. State conventions: D default, H hover, F focus, A active, X disabled, L loading, E error, Em empty. "NI" = not implemented (no code for it).

### 1. Header / nav (I:22-51)

| Element | Notes | D | H | F | A | X | L | E | Em |
|---|---|---|---|---|---|---|---|---|---|
| Brand mark + wordmark + "Clinical Variome" chip + tagline | Static; mark is emoji in gradient square (`transition-all duration-300` with no changing property) | static | NI | n/a | n/a | n/a | n/a | n/a | n/a |
| `#btn-theme-toggle` | daisyUI `btn btn-sm btn-outline`; label "Dark HUD" (light) / "Light Mode" (dark) with emoji; label text `hidden sm:inline` (icon only < sm) | outline | `hover:border-sky-500` | daisyUI default only | daisyUI default | NI | NI | NI | n/a |
| "Local-First (Client-Side Only)" pill | Static; `hidden sm:flex`; green dot `animate-pulse` (I:46-48) | static | NI | n/a | n/a | n/a | n/a | n/a | n/a |
| *(removed)* `#redis-status-indicator` "Redis Edge Ready" | Deleted by T9: the header holds the toggle and the pill only (I:41-50). There is no Redis. `tests/e2e/test_ui_honesty.py:254` asserts the element is absent. | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### 2. Upload and dropzone (I:56-91; A:242-292)

| Element | D | H | F | A | X | L | E | Em |
|---|---|---|---|---|---|---|---|---|
| `#dropzone` (div; click opens file dialog; ignores clicks on button/a, A:274-277) | dashed 2px `slate-300` / dark `slate-700`, `bg-white` / dark `slate-900/40` | `hover:border-sky-500`; icon `group-hover:scale-105` | **NI** (div, no tabindex, not keyboard reachable) | NI | NI (not disabled while analysing) | NI | see Analysis error | n/a |
| Drag-over | adds `border-sky-500 bg-sky-500/10` on `dragover`, removed on `dragleave`/`drop` (A:243-256). Only first dropped file used (A:253-255) | | | | | | | |
| `#file-input` (hidden, `accept=".txt,.csv,.vcf,.tsv,.gz"`) | hidden | n/a | n/a | n/a | `disabled` while analysing (A:213-218) | n/a | n/a | n/a |
| `#btn-browse-files` (daisyUI `btn-primary`, `bg-sky-600 hover:bg-sky-700`) | filled | darker | daisyUI default | daisyUI default | **NI** (not disabled while analysing) | NI | NI | n/a |
| `#btn-load-demo` (`btn-outline`) | outline | `hover:border-sky-500`, text sky | daisyUI default | daisyUI default | `disabled` while analysing | NI (no spinner on button) | fetch failure shows the `#analysis-error` alert, no `alert()` (A:288-290) | n/a |
| Scope chips (I:82-88): `#hero-scope` reads "<ACMG SF version>: N loci in M genes tested" from the KB manifest (V:304-310; A:133-134), or "tested scope Not available" when the manifest cannot be read; "Human Protein Atlas" and "CPIC Pharmacogenomics" are static text (I:85, 87) | static, emoji | | | | | | | |

### 3. Progress (I:94-107; A:357-364)

| Element | Fact |
|---|---|
| Visibility | `#progress-section` `hidden` until `processText` removes it; hidden again on error/complete |
| Message `#parse-progress-msg` | daisyUI `loading loading-spinner loading-xs` + text; replaced by worker `status` strings. `textContent =` on the span **removes the spinner element** on the first update (A:362; the spinner is a child of that span, I:97-98) |
| Percent `#parse-progress-pct` | `${percent}%` |
| Bar `#parse-progress-bar` | `width: N%`, gradient sky-500 -> indigo-600, `transition-all duration-150`; track `h-2` |
| Watchdog | 30000 ms inactivity (A:37), re-armed on each progress message (A:194-200); failure -> Analysis error |
| States | D/L implemented; H/F/A/X n/a (non-interactive); E -> separate alert; Em n/a. **No cancel control (NI).** |

### 4. Analysis error alert (I:109-113; A:220-229)

| Fact | Detail |
|---|---|
| Element | `#analysis-error`, `role="alert"` (asserted in `test_web_smoke.py`), red surface, `border-l-4 border-red-500` |
| Copy (fixed) | "The analysis could not be completed. Nothing was uploaded, and no results are shown. Please try again, or try a different file." + `Technical detail: <span id="analysis-error-detail">` (raw message via `textContent`) |
| Triggers | worker `onerror` / `onmessageerror` / `type:"error"` message / watchdog timeout / unsupported format (text contains "unsupported") / KB load failure (the JSON module import through `web/src/kb-loader.js` fails) |
| Required behaviour (tests) | hidden until an analysis starts; on failure: alert visible, progress hidden, results hidden, inputs re-enabled; cleared at next run start; retry recovers; worker terminated per run |
| One error path | `showAnalysisError()` (A:220-229) is the only error path. FileReader failure (A:343-345), demo fetch failure (A:288-290), worker failures (A:158-169, 184-186) and an error inside `handleParseComplete` (A:179-183) all end there. `alert()` is not used (resolved by T9; e2e for FileReader failure in `tests/e2e/test_ui_honesty.py`) |
| States | D hidden; visible = E; no dismiss control (NI); no focus move on appearance (NI) |

### 5. QC summary (I:129-160; A:398-415)

| Element | Fact |
|---|---|
| `#qc-filename` | `textContent` of file name |
| Chips | Format (`FORMAT (build)`), Markers (`toLocaleString`), Call Rate (green text class), Heterozygosity, Sex-chromosome QC badge |
| Missing rate | `null` -> text "Not available" in the muted style, `title` = `qc.qc_note` (A:405-408). The Call Rate element keeps its green text class (I:147) around the muted span - verify |
| Sex badge | Shows `qc.sex_signal` verbatim, e.g. "Indeterminate (too few X markers)" (`test_formats.py`); `title` = X markers / X het / Y calls (A:410-414). **Must not claim sex or karyotype.** |
| Placeholders | "sample.txt", "—" are pre-render defaults only |
| States | Non-interactive; hover only for `title` tooltips (not keyboard reachable) |

### 6. Coverage-state cards (5-state taxonomy) (I:195-241; A:417-439)

| # | Card label (current) | Subtitle (current) | Count source | Tone classes |
|---|---|---|---|---|
| 1 | Observed | "Supported & observed" | `supported_and_observed_count` | sky |
| 2 | Tested WT | "Supported, not detected" (I:212) | `supported_not_observed_count` | emerald |
| 3 | Array Gaps | "Omitted from chip" | `not_tested_by_array_count` | amber |
| 4 | Outside Scope | "Markers uncurated" | `outside_coverage_count` | slate |
| 5 | Conflicting | "Disputed / insufficient" (I:239) | `insufficient_evidence_count` | rose |

- Static `State 1..5` pill on each card. Cards are **not** interactive (no click-to-filter); the filter tabs are the only way into states 2, 3, 5. State 4 has **no table view** (NI).
- `renderSummaryCards` shows the worker's own figures and recounts nothing; a figure that is not a number renders "Not available" (A:417-439; counts built in W:60-65, 94-103).
- Wording (AGENTS.md section 4.1): the card 2 subtitle is "Supported, not detected" (I:212); the label "Tested WT" (I:208; V:27) remains. No "normal" wording remains on the page: `tests/e2e/test_ui_honesty.py:25-37` bans "Tested Normal" and "Normal Baseline".
- `test_each_locus_is_counted_in_exactly_one_state`: states 1,2,3,5 sum to `total_loci`.

### 7. Category cards (I:163-193; A:428-432)

Five KPI cards: Pathogenic (rose), ACMG SF v3.2 (sky), Pharmacogenomics (purple), Carrier Status (amber), Elevated Risk (red). Counts from `state.summary.*` (`pathogenic_count`, `acmg_actionable_findings`, `pgx_count`, `carrier_count`, `risk_factor_count`), which the worker counts over observed findings only (W:84-103). The ACMG label comes from the manifest (`data-acmg-version`, I:171; A:135-137). Grid `grid-cols-2 sm:grid-cols-3 lg:grid-cols-5`. Non-interactive. Subtitle text static ("High clinical priority" I:167, "Recessive & APOE alleles" I:185).

### 8. APOE card (I:244-284; A:443-490)

| Aspect | Current behaviour |
|---|---|
| Visibility | `hidden` unless `state.apoe` truthy (A:447-450) |
| Fields | Every value comes from `apoeCardModel` (V:271-299) and the KB, set at A:464-470: title (`APOE ε3/ε4`, or `APOE: no diplotype` / `APOE: atypical` when none is asserted, V:286), state-and-significance pill (V:291), relative-risk badge, narrative, raw-loci string (`rs429358: CT · rs7412: CC`, V:287), lifetime-risk stat and HPA abundance summary. A missing value renders "Not available" (muted). Nothing is hard-coded in the HTML: the text in I:250-267 is a pre-render default that A:464-470 overwrites, and I:277, 281 are empty |
| Variants by diplotype | e4/e4: rose `border-l-4`, `badge-pathogenic`; any other e4: amber, `badge-carrier`; any e2: purple, `badge-pgx`; e3/e3: emerald, `badge-benign` (A:473-483). No diplotype asserted: neutral slate classes, never the green (A:484-488). Pill text is "<state> · <significance>" from the KB (V:291); state wording is V:33-38 |
| Button `#btn-inspect-apoe` | `btn-outline border-sky-500`; opens the drawer for the APOE row; no-op if none (A:325-331) |
| Missing component / atypical / indeterminate | Implemented by `resolveApoe` (C:46-139); the table below is the spec. A missing, no-call or unresolvable component asserts **no diplotype**: state `not_tested_by_array` or `insufficient_evidence` carrying the component's reason, never wild-type and never "presumed e3" (C:90-101) |
| Honesty | "Normal Baseline" is banned in page text and exports (`tests/e2e/test_ui_honesty.py:25-37`) |

Diplotype resolution (C:22-32, 103-139; e4 = alt count of rs429358, e2 = alt count of rs7412):

| e4 alt count | e2 alt count | Diplotype | State |
|---|---|---|---|
| 0 | 0 | e3/e3 | supported_not_observed (sample_observation wild_type) |
| 1 | 0 | e3/e4 | supported_and_observed |
| 2 | 0 | e4/e4 | supported_and_observed |
| 0 | 1 | e2/e3 | supported_and_observed |
| 0 | 2 | e2/e2 | supported_and_observed |
| 1 | 1 | e2/e4, caveat "phase unknown: e1/e3 is the rare alternative" (C:19) | supported_and_observed |
| 2/1, 1/2, 2/2 | | atypical: "requires an e1-type haplotype; cannot be resolved from genotype array data" (C:16-18) | insufficient_evidence, variant_present |

The row also moves to `insufficient_evidence` when a component locus's evidence is insufficient (C:120-130). The component SNP records attach as `components`; the APOE row is the only APOE row and the coverage cards count it once (C:141-152).

### 9. Multi-locus (assortment) section (I:286-316; A:492-586)

Hidden when 0 findings (A:502-505). Badge `N Multi-Locus Finding(s)` (A:509). Cards are built by `innerHTML` from worker data, every interpolated value through `escapeHtml` (A:513-576). The section heading and sub-heading are static text (I:297, 304, 309).

- **Possible compound heterozygote, phase unknown** (A:514-539): label "Possible Compound Heterozygote · Phase Unknown" (A:520), `badge-pathogenic` significance, title, summary and segregation note from the worker. The wording is "phase unknown (cis or trans cannot be determined from unphased genotypes)" and never "trans" (contracts C5; `tests/vectors/inheritance.json`).
- **Co-occurring variant alleles** (A:542-576): label "Co-occurring Variant Alleles" (A:548), "Loci on Different Chromosomes" (A:559), and "Child Inherits All Listed Alleles" with the percentage, whose `title` carries the stated assumption "assumes unlinked loci and a partner without these alleles" (A:563-564; `MULTI_LOCUS_ASSUMPTION`, `web/src/core/inheritance.js:14`).
- Scope: only genes whose KB inheritance model is `risk_factor` (F5 and F2 today), on different chromosomes, with alt count > 0 (`web/src/core/inheritance.js:123-134`; contracts C5, owner ruling 9).
- Each card has "Inspect <gene>" `btn-xs btn-outline` buttons that open the drawer when `state.records` holds a record for that gene (A:579-585).

### 10. Findings table with filters and search (I:319-404; A:294-312, 602-706)

| Element | Fact |
|---|---|
| Filter tabs (9) | `data-filter`: all "Observed Findings", negative "Tested Wild-Type (State 2)", gaps "Array Gaps (State 3)", insufficient "Conflicting Evidence (State 5)", carrier, pathogenic, acmg, pgx, risk. Plain `<button>`s in an `overflow-x-auto` strip |
| Tab states (A:300-312) | D: `text-slate-600 dark:text-slate-400`; H: `hover:text-slate-900` + `transition-colors`; Active: `tab-active bg-sky-600 text-white` (dark: `bg-sky-500/20 text-sky-300`, sky border) toggled by JS class swap; **no `aria-selected`/`aria-pressed`** (NI); F: browser/daisy default only; X/L/E/Em: NI |
| Dataset selection (A:606-621) | all/pathogenic/carrier/pgx/risk/acmg filter `state.records`; negative -> `negativeChecks`; gaps -> `arrayGaps`; insufficient -> `insufficientEvidence` |
| Search `#search-input` | daisyUI `input input-sm`, `focus:border-sky-500`, placeholder "Search rsID, gene, drug…", live on `input`; matches id, gene, phenotype, genotype, category, significance, drug_response and the APOE diplotype (A:624-629). No `<label>`, no clear button (NI) |
| Count `#showing-count` | "Showing N of M clinical findings" / state-specific strings (A:633-641); not `aria-live` |
| Columns (8, I:388-395; A:685-703) | rsID (APOE reads "APOE (rs429358 + rs7412)", V:178), Gene (+ACMG pill A:674-676, +limitation badge A:678-680), Genotype, Coverage State badge, Tier / Category, ClinVar (stars, or "No ClinVar review status", V:96), Magnitude (+repute; `text-rose` if >= 4), Clinical Guidance (`statement ?? phenotype ?? significance`, truncated `max-w-md`, `title` tooltip, A:682-683, 700-702) |
| Row states | D: `cursor-pointer`; H: `hover:bg-slate-50/80` / dark `slate-800/40`, plus global `tbody tr:hover` `--bg-surface-hover !important` (S:233); F/A/X: **NI** (rows not focusable; `onclick` only, no Enter/Space) |
| Empty | One row `colspan=8` "No variants match your search or filter." with emoji tile (A:643-653) |
| Loading | NI (table is not shown during progress) |
| Sorting | `state.sortBy="magnitude"` exists (A:54) but there is **no sort UI and no sort applied** in `renderVariantsTable` |
| Row badges | Coverage-state: Observed (sky) / Tested WT (emerald) / Array Gap (amber) / Conflicting (rose) (A:588-593; texts V:25-30; an unknown state throws, V:133); Tier A sky / B emerald / C amber / D slate (A:595-600); Category via `.badge-*` (A:660-665). A missing tier or category renders "Not available" in the muted style (A:667-672); there is no "Tier B" default. A **limitation badge** ("Limitation", or "Caveats" when only caveats exist) on the row carries the full text as its tooltip (A:678-680; V:225) |

### 11. Variant drawer (I:409-683; A:722-864, 1107-1110)

| Element | Fact |
|---|---|
| Open | Row click, "Inspect" buttons (APOE card, assortment cards): removes `translate-x-full` (A:863) |
| Close | `#btn-close-drawer` (daisyUI `btn-circle btn-ghost`, "✕"): adds `translate-x-full` (A:1107-1110). **No Escape key, no backdrop click, no focus trap, no focus return** (no `keydown`/`Escape`/`aria-*`/`inert` in A or I) |
| Closed state | Off-canvas via transform only; contents remain in tab order and accessibility tree (NI: `inert`/`aria-hidden`/`visibility`) |
| Header | rsID or, for APOE, "APOE (rs429358 + rs7412)" (sky, `text-2xl font-black`), gene, coordinates `chr<chrom>:<pos>` (APOE shows both component positions, V:182-184), Tier badge (or "Not available"), Coverage-state badge (A:727-752) |
| Coverage badge labels | "Supported & Observed", "Tested Wild-Type (State 2)", "Array Gap (State 3)", "Conflicting Evidence (State 5)" (V:25-30; A:749-752). An unknown state throws instead of printing a raw key (V:133) |
| Conditional boxes | ACMG (sky; "does not independently evaluate ACMG/AMP 2015" wording, I:435; A:779-785), CPIC drug alert (purple, with single-SNP caveat text, I:445; A:787-795), **Limitation of this Test** (purple; shown whenever the KB gives the record a `limitation`, for example the CYP2C19 star-allele refusal or a single-variant test, A:754-764), **Scientific caveats** list (slate, A:766-777); each toggled with `hidden` |
| Metrics grid | Genotype, ClinVar Stars (exact stars, or "No ClinVar review status"), Magnitude / Repute ("x / 10.0 (Repute)"), gnomAD AF; each shows "Not available" (muted) when the record lacks the value (A:729-738; V:96-97, 201) |
| Phenotype | "Clinical Significance & Phenotype" + serif paragraph |
| Segregation panel (A:866-957) | Mode badge (amber recessive / rose dominant / purple other; text from `MODEL_LABELS`, V:40-46). Mendelian genes show carrier prior, penetrance and risk vs unscreened / carrier partner (a genotype probability for a recessive gene, A:880-892). Every other model is relabelled for allele transmission ("Allele Transmission", "Allele Frequency (gnomAD)", "Child Inherits vs Unscreened Partner") and penetrance reads "Not applicable" (A:882-896, 934). With no `segregation` (not tested, no-call) every figure reads "Not available" (A:899-909) |
| Offspring simulator | 4 buttons (`partner-sim-btn`, `grid-cols-4`). Labels `Unscreened / Carrier / Affected / Wild-Type` for Mendelian genes and `Unscreened / Heterozygous / Homozygous / Wild-Type` for every other model (A:960-961, 895-897). D: white / bordered; H: `hover:border-sky-500`; selected: `bg-sky-600 text-white shadow-sm`, swapped by `className` rewrite (A:942-946); F: browser default; X/L/E: NI; no `aria-pressed`. Inputs are the patient's alt-allele count, a partner model (wildtype 0, heterozygous 0.5, homozygous 1, unscreened = the KB gnomAD allele frequency) and the gene's inheritance model (A:911, 960, 977-981; contracts C5). `#drawer-partner-model-note` states which partner model produced the figures (I:540; A:971-975; V:342-350); with no allele frequency the unscreened model reads "Not available" (V:344-345). Output: three probability bars and a fourth line, worded by model (A:985-1030): disease wording only for Mendelian genes; every other model reads "chance a child inherits the allele" and "Clinical Penetrance: Not applicable". Resets to "Unscreened" each time the drawer opens (A:954-956) |
| Biotools panel (A:1038-1104) | AlphaFold DB (UniProt chip, pLDDT chip toned by value: >=85 emerald, >=70 sky, else amber, null slate; status; domains; joints), Ensembl VEP (transcript chip, AlphaMissense, LOEUF with text band, V:114-118), ENCODE (TPM bars, floor of 100 TPM, A:1087). Every field absent from the KB insights reads "Not available" (muted). The old placeholder strings are gone and `tests/e2e/test_ui_honesty.py:25-37` bans them. The canonical transcript, AlphaMissense and LOEUF are imported by the KB build pipeline (`machine_imported`); the remaining biotools content (AlphaFold, ENCODE) is manually curated KB data |
| HPA | Tissue rows with level pill (High emerald / Medium amber / other sky, A:829-843); subcellular chips (A:849-857); each empty case reads "Not available" (A:845, 859). The tissue and subcellular values are manually curated |
| Footer | "Open ClinVar Record ↗" (`<a target=_blank rel="noopener noreferrer">`, I:678). A link appears only for a locus whose accession is `machine_imported` (V:91, 98) and is hidden when there is none; a composite APOE row gets one link per component, labelled with its rsID (A:797-818). `#drawer-footer-tier` shows "Evidence Tier X" or "Evidence tier: Not available" for the open record (I:681; A:747; V:331-333) |

### 12. Exports (I:365-373; A:1112-1152)

| Element | Fact |
|---|---|
| Control | daisyUI `dropdown dropdown-end`; trigger `div tabindex=0 role=button` "Export ▾"; `ul.menu` with `<a>` items **without `href`** (Markdown Report, CSV Dataset); opens via CSS focus (daisyUI) |
| States | D/H (`hover:bg-slate-100`)/F (daisyUI focus-within); X: **NI**, handlers silently return if there is no QC result (A:1120, 1139), not visually disabled; L/E/Em: NI; control exists only inside `#results-section` |
| Markdown (V:437-533) | Title, guardrail text from `state.manifest.guardrail` (V:442), sample/QC line, 5-state summary, APOE section (diplotype, state, caveat, limitation, underlying loci, V:453-468), possible compound heterozygotes (phase unknown), co-occurring alleles on unlinked loci, then tables for observed findings, tested wild-type, array gaps and insufficient evidence. Each table has a Limitation and a Missing fields column. A not-detected row reads "<allele> not detected (N variants tested in <gene>)" (V:76-83). File `Lucidase_Report_<ts>.md` |
| CSV (V:358-364, 391-420) | 22 columns incl. Coverage_State, Evidence_Tier, Inheritance_Mode, three offspring columns (child inherits the allele with a wild-type partner and with an unscreened partner; child affected with an unscreened partner), Result_Statement, Limitation, Caveats, Missing_Fields. Rows = every row once: records, negativeChecks, arrayGaps and insufficientEvidence (A:1113-1117). A missing value is an empty cell named in Missing_Fields; "N/A" appears only for the affected cell of a non-Mendelian gene (V:372-387). APOE exports as one row with both rsIDs joined by ";" (V:179). File `Lucidase_Variants_<ts>.csv` |
| Required (AGENTS.md 4.6) | Single-variant-test limitations appear in every export: the CSV Limitation and Caveats columns (V:413-414) and the Markdown Limitation columns (V:492-530) |

### 13. Dark mode ("Dark HUD")

| Fact | Detail |
|---|---|
| Trigger | `#btn-theme-toggle`; icon/label swap (🌙 "Dark HUD" <-> ☀️ "Light Mode") |
| Mechanism | `data-theme` on `<html>`; Tailwind `dark:` variants (selector strategy); CSS variable block `[data-theme="dark"]` |
| Persistence | `localStorage` key `lucidase-theme`; **no `prefers-color-scheme` handling**; read/write not wrapped in try/catch (A:56, 93) |
| Transition | `body` colour 0.2s ease; `#dropzone` `transition-all duration-200` (test waits 600 ms) |
| Test coverage | `test_theme_toggle_round_trip`; `test_dark_utilities_beat_glass_panel` (dropzone alpha 0.4, not `.glass-panel` 0.75) |

## States and Interactions

### Global flow (encoded by tests)

| State | UI | Entry | Exit |
|---|---|---|---|
| Idle | dropzone only; progress, error, results hidden | page load | file chosen / dropped / demo click |
| Reading | progress 5% "Reading <name> (x MB)..." | `handleFileSelected` (A:335-347) | FileReader load -> Analysing; FileReader error -> the error alert (A:343-345) |
| Analysing | progress shown; results hidden; error hidden; file input + demo button disabled | `processText` | `complete` -> Results; failure -> Error |
| Results | progress hidden; results shown; inputs re-enabled | `complete` | new run (results hidden at start) |
| Error | progress hidden; results hidden; alert visible; inputs re-enabled | any failure | next run clears it |

### Clinical-honesty states the design system MUST provide

Requirements only (what must be distinguishable), not visual treatments. Sources: AGENTS.md sections 3-5, coverage keys in `app.js`.

| # | Requirement | Current mapping |
|---|---|---|
| H1 | **Supported and observed** (`supported_and_observed`): alt allele present among variants tested | "Observed" / "Supported & Observed" |
| H2 | **Supported, not observed**: wording is *"not detected among the N variants tested"*; never "normal" or any statement of absent risk (4.1) | "Tested WT" / "Supported, not detected" (I:208, 212); row statement "<allele> not detected (N variants tested in <gene>)" (V:76-83) |
| H3 | **Not tested by array** (`not_tested_by_array`): locus absent from the file or a no-call; shows reason | "Array Gap" |
| H4 | **Outside coverage** (State 4): markers present but uncurated; counted only, no per-row view today | "Outside Scope" count |
| H5 | **Insufficient evidence** (`insufficient_evidence`): conflicting, Tier C/D, or unresolvable genotype; fail-closed results land here, never "wild-type" | "Conflicting" (label implies only conflict; the key also covers atypical/indeterminate) |
| H6 | **"Not available"** for missing data, muted, never a placeholder value or invented default (section 3) | Implemented: one muted italic treatment (A:109-124) in the table, drawer, QC chips, cards and APOE card; exports use an empty cell plus `Missing_Fields` (V:253-266) |
| H7 | **Limitation / caveat badge** on the row, in the drawer and in exports for single-variant tests of multi-variant genes (DPYD, CFTR, CYP2C19 star alleles, ACMG SF loci) (4.6) | Row badge with tooltip (A:678-680), drawer box and caveat list (A:754-777), CSV and Markdown columns (V:413-414, 492-530) |
| H8 | **Insufficient-evidence badge** distinct from category badges, shown beside a category when a variant is present | The "Conflicting" state badge sits in its own Coverage State column, separate from the category badge (A:666, 670-672, 691); there is no extra badge beside the category |
| H9 | **Phase-unknown wording** where unphased genotypes could be cis or trans (compound het, APOE e2/e4) | Implemented: "Possible Compound Heterozygote · Phase Unknown" (A:520); APOE e2/e4 carries "phase unknown: e1/e3 is the rare alternative" (C:19, 118) |
| H10 | **Global scope guardrail**: absence of a finding is not absence of risk, visible with results and in Markdown | `#coverage-guardrail-banner` (amber, static copy, I:119-127); Markdown uses `manifest.guardrail` (V:442) |
| H11 | **Fail visibly**: worker/KB/parse errors surface in the alert, never swallowed (section 3) | `#analysis-error` |
| H12 | **Offspring/recurrence figures** only for Mendelian disease loci, from the patient's genotype and a stated partner model; trait/PGx loci show allele-transmission wording only (4.4) | Implemented for the drawer and CSV: disease wording only for Mendelian genes, allele-transmission wording otherwise (A:880-938; V:377-388) |
| H13 | **Provenance never fabricated**: no invented versions or retrieval dates (4.5) | The KB badge and hero chip read the KB manifest (release, sha256 prefix, locus and gene counts; no source versions) (A:127-138; V:303-328); no page text names a ClinVar, dbSNP or other release |
| H14 | **Privacy affirmation** visible; no third-party script; data never leaves the browser (section 5) | Header pill (I:46-49) + footer text (I:688-690), static |

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
| XSS payload in rsID | Test asserts no execution. Table, cards and caveat list are built with `innerHTML`, and every record or KB value in those strings goes through `escapeHtml` (V:20-22; A:8-10, 517-576, 685-703, 772), with the CSP as a second layer |
| Wild-type loci | Not in `records`; reachable only via "Tested Wild-Type" tab (`test_classification.py`) |
| APOE components | Never separate rows; one APOE row + card |
| No matches for search/filter | Empty row message |
| Long phenotype text | `truncate max-w-md` with `title` |
| KB load failure (JSON module import) / worker failure / silent worker | Error alert; watchdog 30 s |
| Healthy slow progress | Watchdog re-armed per progress message; no false timeout |
| Placeholder-as-data | Removed by T9. None of the old placeholder strings renders (`tests/e2e/test_ui_honesty.py:25-37` bans them); a missing value reads "Not available" (A:109-124) |
| Gap / not-tested row fields | Genotype "Not available" (A:690); the phenotype is `record.reason` (V:161), the significance falls back to the state label (V:193), and the guidance cell is `statement ?? phenotype ?? significance` (A:682) |
| Multiple files dropped | First only, silently (A:253-255) |
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
| Contrast (to verify) | - | `text-[9px]`/`[10px]` labels in `text-slate-400`/`slate-500` on white/slate-50 (I:266, 276, 280, 532); `text-slate-400` "or" on white; `text-amber-500` stars on white; `text-white` on `bg-sky-600`; `text-emerald-600` on white; dark `text-slate-500` on `slate-900/60` (I:203 etc.); muted text on translucent glass over the grid |
| Touch targets | - | `btn-sm`/`btn-xs`, 11px tabs, `btn-circle btn-sm` close: likely below 44px, to verify |
| Motion | - | `animate-pulse` and spinner with no reduced-motion override |
| Emoji | Used as icons/labels | Read aloud by screen readers; not marked `aria-hidden` |
| Tooltips | `title` on QC rates, sex badge, KB badge (A:131), limitation badge (A:680), truncated phenotype | Not available to keyboard/touch |
| External link | `rel="noopener noreferrer"` | n/a |

## Pending changes

None. T7 (APOE card states), T8 (offspring simulator inputs, wording and multi-locus scope) and T9 (single view model, "Not available", limitation badges, one error path) landed on this branch. Their behaviour is described in the sections above, with `file:line` cites, and is no longer pending.

## Open questions for the design system

Decisions the design-system author must take; no values are recommended here.

1. **Identity**: is the brand (name treatment, emoji mark, "Clinical Variome" chip, tagline) established, and what stands in for the emoji icons and the 🧬 mark?
2. **Typography**: the owner chose Typekit kit `gfe3vcu` on 2026-10-03 (sans akzidenz-grotesk-next-pro, serif orpheuspro, mono input-mono, display swiss-721-bt-condensed; replaces the previous kit). Does it remain, given Typekit is the only external host in the CSP? Which roles (sans/mono/serif/display) exist, and should `.font-mono`/`.font-serif` keep `!important`? Should font variables live in `:root` rather than only `[data-theme="dark"]`?
3. **Dark mode**: is `data-theme` + Tailwind `selector` the final mechanism? Should it follow `prefers-color-scheme`? Is the name "Dark HUD" kept? How is persistence handled when storage is blocked?
4. **daisyUI role**: which daisyUI components (`btn`, `input`, `dropdown`, `menu`, `loading`, `btn-circle`) are in the system and which are overridden (forced 2px radius, utility colour overrides)? Which daisyUI theme applies (none is configured)?
5. **Badge semantics**: what do the colour families mean, given today's reuse (amber = carrier, warning, State 3, Tier C, guardrail, "Medium"; rose/red = pathogenic, risk, conflicting, error; emerald = benign, tested WT, Tier B, privacy; sky = observed, Tier A, primary action, selected)? Are category, coverage state, evidence tier, severity and UI chrome one vocabulary or several?
6. **Honesty states**: how are H1-H5 distinguished without relying on colour alone, and how is "not detected" kept distinct from "normal"? Where do H7/H8 (limitation badge, insufficient-evidence badge) sit relative to category and tier badges on a row?
7. **State 4 (outside coverage)**: a count only, or a navigable view?
8. **"Not available"** (an interim muted italic treatment now exists, A:109-124; the question stays open): one muted treatment for all contexts (table cell, drawer metric, QC chip, exports), and what is its reason/tooltip affordance?
9. **Interactive semantics**: are table rows buttons, links or selectable rows? Are filter tabs a tablist or a toggle group? Should the dropzone itself be a focusable control?
10. **Drawer**: modal dialog or non-modal panel? Escape/backdrop/focus-return expectations? Does it close on a new analysis? Small-screen behaviour?
11. **Error pattern**: single alert region only, or also inline errors? Dismissible? Does focus move to it?
12. **Counts vs states**: should coverage cards act as filters? How are "Observed" findings and category cards (subsets) explained so totals are not misread?
13. ~~**Static claims**~~ **Resolved by T9.** The "Redis Edge Ready" indicator was deleted (I:41-50; `tests/e2e/test_ui_honesty.py:254`). The KB badge and hero chip are data-driven from the KB manifest (A:127-138; V:303-328), and the footer tier is data-driven per record (A:747; V:331-333). Which of these the design system keeps is a design question and is not decided here.
14. **Responsive scope**: which viewports are supported (tests cover only 1440x900)? How should the 8-column table behave at narrow widths?
15. **Motion**: which transitions are intentional (several carry no changing property), and what is the reduced-motion policy?
16. **Density and sizes**: are 9-11px text and `btn-xs/sm` targets acceptable for this audience, and what are the minimum text and target sizes?
17. **Export parity**: should Markdown/CSV exports share the UI's badge vocabulary?
