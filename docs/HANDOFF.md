# Handoff: Lucidase, state at 2026-10-04

For any coding or design agent (Claude, Codex, Qwen, Kimi, Gemini and others) picking up this repository. It is
self-contained. Read it top to bottom once. After that, use it as a reference.

```yaml
repo: pterw/lucidase              # private; formerly "genomepulse"; GitHub redirects old URLs
default_branch: main
state_of_main: 745b147            # merge of PR #5 (design-system reskin); PRs #1, #3, #2 and #5 are merged
open_prs: design-system PR 2 (draft, branch feat/design-system-structure)
next_work: owner review of PR 2 and its "Decisions to review"
gates: 5 commands, all must pass before any commit (section 5)
ci: none                          # the local gates are the check
platform_tested: Windows 11, Python 3.13.3, Node 24, Tailwind CLI 3.4.17, Playwright bundled Chromium
```

---

## 1. What Lucidase is

Lucidase is a free tool that analyses consumer raw DNA files: 23andMe, AncestryDNA, MyHeritage and VCF. The analysis
runs entirely in the browser, so **nothing from the user's file is uploaded**. The product goal, in the owner's
words: *"a real useful tool that does not charge for analyzing uploaded docs"*.

There are two pages:
- **`web/index.html`**, the analysis page. Upload, then progress, then results:
  - a three-step StepNav (choose your file, read your results, save a copy);
  - a guardrail notice, the file's QC, and a Summary: one sentence of counts, the karyogram with a mark per check,
    and a legend in the plain result words (Found, Not found, Not on your chip, Unclear, Not checked);
  - the grouped report (Pharmacology, Health risk factors, Carrier status, Traits), one row per check, APOE as one
    row with a Ligature figure;
  - a docked, non-modal Inspector beside the list (below it on narrow screens), multi-locus findings, the table one
    click away, and a "Save a copy" section with the Markdown and CSV exports;
  - an inline glossary (Term popovers) in the page's own copy.
- **`web/karyogram.html`**, the karyogram page. It draws the file's markers as dots on the 24 chromosomes, with the
  curated genes ringed by the user's result.

There is also a desktop Python stack (`gui.py`, `genomic_parser.py`, `variant_annotator.py` and others). It is kept,
and it must stay in parity with the web app through the shared vectors in `tests/vectors/*.json`.

## 2. Read these first, in this order

1. `AGENTS.md`: the engineering rules, clinical-honesty and privacy invariants, testing rules, gates and change
   hygiene. **It binds every change.**
2. `docs/design-handoff.md`: **a point-in-time record of the provisional UI** that the design system replaced. It
   covers every screen, state, component and copy string of that UI, with `file:line` cites, plus the behavioural and
   honesty requirements any design system must keep. It is not updated as the pages change, so its quotes and cites
   are stale; the code, the tests and `docs/design-system/` are the current spec.
3. `README.md` and `web/README.md`: what ships, and how to run it.
4. `AUDIT_LEDGER.md`: every finding (P0/P1/P2), its fix and its commit. Three items are still OPEN (section 8).
5. `CLAUDE.md`: notes for Claude Code sessions. Its owner rulings, gates and mechanics apply to every agent.

## 3. Repository map

| Path | What it is |
|---|---|
| `web/index.html`, `web/karyogram.html` | The two pages: static HTML, ES modules, no bundler |
| `web/src/app.js` | Analysis page controller (DOM, worker lifecycle, grouped report, Inspector, summary map, exports) |
| `web/src/karyogram-page.js` | Karyogram page controller |
| `web/src/worker.js` | Web worker: parse, classify, assemble findings, karyogram layout |
| `web/src/core/*.js` | Pure logic (no DOM, no `fetch`, no `self`): parsing, classification, APOE, coverage, KB validation, karyogram layout |
| `web/src/view-model.js` | One view model per record; every row, Inspector field and export reads from it (`RESULT_WORDS`, `REPORT_GROUPS`) |
| `web/src/term.js`, `web/src/glossary.js`, `web/src/pages-menu.js` | Glossary popovers and their definitions; the narrow header "Pages" disclosure |
| `web/src/karyogram-view.js` | Pure SVG renderer for the karyogram |
| `web/src/theme.js` | Light/dark theme, shared by both pages (storage key `lucidase-theme`, attribute `data-theme`) |
| `web/src/kb-loader.js` | The single validating loader for the knowledge base (a JSON module import) |
| `web/src/knowledge-base.json` | **Generated** knowledge base. Never hand-edit it |
| `web/src/styles.css` | Imports the design-system tokens (`web/src/ds/`); daisyUI theme bridge; the DS components as `lds-*` classes |
| `web/tailwind.config.js`, `web/src/tailwind.input.css` | Tailwind 3.4.17 config and input |
| `web/src/vendor/` | Vendored daisyUI 4.12.10 and the generated `tailwind.css` (see its README) |
| `web/demo-data/` | Two clearly synthetic sample files, one per page |
| `web/api/manifest.js` | The only server function (Vercel): a static KB manifest |
| `tools/build_canonical_kb.py` | Builds the KB from `tools/curation/kb_curation.json` plus pinned upstream payloads |
| `tools/source_adapters.py` | The only code that knows upstream payload shapes: ClinVar, dbSNP, VEP, gnomAD and UCSC (anti-corruption layer) |
| `tools/fetch_upstream.py` | One-off capture of upstream payloads into `tools/fixtures/upstream/real/` (needs owner approval to run) |
| `tools/capture_readme_screenshot.py` | Regenerates the README screenshots in `docs/assets/` |
| `tests/` | pytest, including `tests/e2e/` (Playwright) and the shared vectors; `web/tests/` holds the Node tests |
| `docs/assets/` | Banner (light and dark SVG) and README screenshots |
| `.agent/workflows/` | Generic UI-craft prompt files (polish, harden, animate and others). Not project rules |

## 4. Invariants: non-negotiable, and guarded by tests

These are summarised here; the full rules are in `AGENTS.md`.

- **Privacy.**
  - Raw genotype data and rsIDs from a user's file never leave the browser. The CSP keeps `connect-src 'self'`.
  - Allowed network calls:
    - same-origin static assets;
    - two same-origin GETs of the bundled demo files;
    - the owner's Adobe Fonts kit (`use.typekit.net` / `p.typekit.net`, admitted only by `style-src` and `font-src`).
  - No third-party script and no telemetry.
  - `tests/test_zero_knowledge_privacy.py` scans the code for network primitives and telemetry hosts, and
    `tests/e2e/test_csp.py` checks the CSP.
- **Clinical honesty.**
  - Absence of a finding is "not detected among the N variants tested", never "normal".
  - Fail closed on ambiguous genotypes: palindromic sites, alleles outside ref/alt, no-calls.
  - Never fabricate provenance.
  - Single-variant tests of multi-variant genes carry their limitation on the row, in the Inspector and in every export.
  - `tests/e2e/test_ui_honesty.py` pins user-visible wording.
- **Single source of genomic knowledge.** `web/src/knowledge-base.json` is built only by `tools/build_canonical_kb.py`,
  and `--verify-only` fails if it drifts. Never commit `canonical_variome.db`.
- **Web and desktop parity** through `tests/vectors/*.json`.
- **No new runtime dependency** without an owner decision.
- **Network** only when the owner approves it for a specific task. Tests are always offline.
- **Fail fast.** No silent defaults and no silent clipping. An unknown value raises.

## 5. Gates: run before every commit, from the repo root

```
python -m pytest tests -q -p no:cacheprovider --ignore=tests/e2e
node --test --test-reporter=spec "web/tests/**/*.test.mjs"
python -m pytest tests/e2e -q -p no:cacheprovider
python tools/build_canonical_kb.py --verify-only
python tools/check_vendored_css.py
```

Results on the design-system PR 2 branch (`feat/design-system-structure`), from the last full run:
- pytest: 946 passed, 35 subtests;
- node: 347 passed, fail 0;
- e2e: 170 passed;
- KB: up to date;
- vendored CSS: up to date.

Practical notes:
- **e2e takes about 3 minutes.** Give it a 10-minute timeout. A shell that kills it at 2 minutes shows no summary line,
  which looks like a failure but is not one.
- **Windows only:** under heavy parallel load, e2e can hit `net::ERR_NO_BUFFER_SPACE` on resource loads, as setup or
  teardown errors. Re-run once on a quiet machine before you treat it as a real failure. Never mask it in the
  conftest.
- **Line endings:** `core.autocrlf=true`. The pinned upstream fixtures are `-text` in `.gitattributes`, so their sha256
  holds. Tests must never assert on working-tree line endings.
- **The Tailwind CLI is not committed.** Put `tailwindcss` v3.4.17 at `bin/tailwindcss.exe` (or `bin/tailwindcss`).
  Version, sha256 and command are in `web/src/vendor/README.md`. Any class change in `web/*.html` or `web/src/**/*.js`
  means regenerating `web/src/vendor/tailwind.css`, or `check_vendored_css.py` fails.

## 6. Design-system work: what to know before changing the look

**Status (2026-10-04).** The owner's **Lucidase design system** now owns the look; it superseded the provisional
UI and ruling 15's font mapping. PR 1 (#5, merged) applied it on the existing DOM and view-model wording; PR 2
(branch `feat/design-system-structure`) brings its structure: grouped report, plain result words in the view model
and exports, Summary karyogram, docked Inspector, StepNav, glossary. See `web/src/ds/README.md` and the "Visual design" rules in `AGENTS.md` and `CLAUDE.md`.
The rest of this section describes the provisional stack it replaced, kept for reference.

**Already decided by the owner (keep these unless the owner changes them):**
- **Name:** **Lucidase**. The UI shows the name as text only.
- **Fonts:** Adobe Fonts kit **`gfe3vcu`**, loaded by both pages. The design system's families
  (`web/src/ds/typography.css`) are:
  - sans `akzidenz-grotesk-next-pro` (UI);
  - serif `orpheuspro` (headings, prose);
  - condensed `akzidenz-grotesk-next-conden` (column heads, counts);
  - mono `input-mono` and `input-mono-narrow` (rsIDs, genotypes, dense tables).
  - The earlier mapping, with `swiss-721-bt-condensed` as the display face, is retired. Swiss 721 BT Condensed
    remains only as a fallback inside the condensed stack.
- **README banner:** a light and dark SVG in `docs/assets/`, plus screenshots regenerated by
  `python tools/capture_readme_screenshot.py`. The banner's karyogram art is decorative.
- **Copy for people, not geneticists.** Karyogram examples: "genome version" rather than "build", "Genes this report
  checks" rather than "curated loci", "Try a made-up example file".

**Where styling lives today:**
- `web/src/styles.css` holds the theme variables.
  - Light and dark sets: `--bg-canvas`, `--bg-surface`, `--bg-surface-elevated`, `--bg-surface-hover`,
    `--text-main`, `--text-muted`, `--text-subtle`, `--border-subtle`, `--border-strong`, `--header-bg` and
    `--header-border`.
  - Accents: `--accent-cyan`, `--accent-emerald`, `--accent-amber`, `--accent-ruby` and `--accent-purple`.
  - Badges: `--badge-{benign,carrier,pathogenic,pgx,risk}-{bg,border,text}`.
  - Fonts: `--font-sans`, `--font-serif`, `--font-mono` and `--font-display`.
  - Karyogram: `--kary-fill`, plus `.kary-*` classes mapped to the accents.
  - It also holds `.glass-panel` and the badge classes.
- `web/tailwind.config.js` sets dark mode through the `[data-theme="dark"]` selector and the font families.
- daisyUI 4.12.10 is vendored unmodified.

**Constraints the tests enforce, so plan around them:**
- **Stylesheet order:** daisyUI, then `src/styles.css`, then `src/vendor/tailwind.css`. `tests/e2e/test_cascade.py`
  guards it; utilities must beat app rules of equal specificity. If the design system replaces this stack, replace
  the test with an equivalent guard too, and don't simply delete it.
- **Class-based assertions:** `tests/e2e/test_ui_classes.py` (badge and tier classes) and `tests/e2e/test_karyogram.py`
  (`.kary-*`, the column count, radii through the SVG) assert on classes and structure. Renaming classes means
  updating those tests in the same change.
- **Pure-view tests:** `web/tests/karyogram-view.test.mjs` pins exact SVG coordinates and radii:
  - an empty bin has r 0.9;
  - a bin with markers has r 1.6 + 1.6 * sqrt(count / busiest);
  - the busiest bin has r 3.2.
- **Honesty copy:** `tests/e2e/test_ui_honesty.py`, `tests/e2e/test_karyogram.py` and the Node tests pin user-visible
  strings. A wording change must keep the meaning that the test guards. For example, "not detected among the N
  variants tested" must never become "normal".
- **Every UI state** listed in `docs/design-handoff.md` (a point-in-time record, not kept current) must survive:
  - upload, progress, error and results;
  - the coverage states: observed, not tested by array, no-call, insufficient evidence and others;
  - the karyogram's no-file, known-version, unknown-version and error states;
  - the keyboard paths: rows, Details buttons and map marks open on Enter and Space, the export controls are
    buttons, and closing the Inspector (Esc or ×) returns focus to the element that opened it.
- **CSP:** no new third-party host. Fonts come only through the Typekit kit, and a new font source needs an owner
  decision plus CSP and test updates.
- **After a visual change:** regenerate `web/src/vendor/tailwind.css` and the README screenshots. Do not update
  `docs/design-handoff.md`: it records the provisional UI as it was and is left as it is.

**Known design debt, recorded and not fixed:**
- At a 390 px width, the upload button overflows on the analysis page.
- The karyogram's dot sizing is functional, not designed.
- The UI tagline is still an open owner decision.

### Decisions from the design-system gap work (branch `fix/ds-gaps`)

A review compared the app with the design project and this branch closed what it found. The product decisions it
recorded, so nobody reopens them by accident:

- **Header links** read "Your results" and "Chromosome map" on both pages. The karyogram page's H1 is "Chromosome map".
- **Karyogram genes table** (`web/karyogram.html`) shows Topic, Gene, Chromosome and "Your result". Marker and
  Position left it; the analysis table keeps its Marker column, and the Inspector keeps the exact coordinate (below).
- **Karyogram figure.** On a phone the genes table fits at 390 px with the fallback fonts, and scrolls inside its box
  if the real fonts need a few pixels more. It still overflows below 390 px (320 to 360). The figure itself keeps a
  672 px minimum width and scrolls inside a named, focusable region. With no file loaded the key reads
  "Genes this report checks" (`web/src/view-model.js`, `REFERENCE_STATE_LABEL`).
- **Inspector.** The exact coordinate sits in a "Position" row under Technical details, and the subtitle names the
  chromosome in words ("chromosome 19"; both markers' chromosomes for APOE). The gene and protein context (AlphaFold,
  Human Protein Atlas, subcellular) sits behind a disclosure, `#drawer-gene-context`: closed until a reader opens it,
  then it stays open while they browse other records.
- **Results table.** The category tabs are gone; the result-word tabs stay, with counts. It opens on every check, adds
  a Topic column, and marks the row whose details are open. A check whose gene has no KB topic shows "Not available"
  (unreachable today: the KB loader rejects a blank topic).
- **KB badge.** "KB · Offline" is now the plain text "KB <release>" (`kbBadge` in `web/src/view-model.js`).
- **Inheritance wording.** The Mendelian-only data labels "Risk if the other parent is unscreened / a carrier" stay as
  they are; the chances for the child are in plain words ("Child gets two copies", "one copy", "no copy").
- **Cosmetic.** Probability bars scale with `transform`; "Not available" text is set in the sans face; "more contrast"
  applies on a dark device that has no theme set.

Deviations from the design that PR #6 listed only in its body, still in force (each is the app's choice where the
design is silent or cannot be followed; ask the owner before changing one):
- Glossary: "variant" and "carrier" are the design's wording; genotype, allele, chip, marker and risk factor are drafts
  awaiting owner review (`web/src/glossary.js`).
- The Term popover is pinned to the bottom of the viewport below 560 px, because the design's 280 px popover runs off
  a phone (`web/src/styles.css`, `.lds-term-pop`).
- The Inspector stacks under the results list when the container is under 1032 px wide; the design gives no
  breakpoint (`web/src/styles.css`, `@container lds-results`).
- StepNav shows the vendored check and arrow-left icons where the design used the ✓ and ← glyphs, because the design
  system bans unicode as icons.
- An empty report group says "No checks in this group." (cannot happen with today's KB). The search placeholder stays
  "Find a marker, gene or drug", because search does not match topics. Caveats stay in the Inspector, and the row
  shows the limitation.
- The APOE figures sit under the Ligature as "Risk ratio" and "Estimated lifetime risk". Each APOE map mark shows its
  own marker's result word, so rs7412 "Not found" opens the APOE row, which can read "Found".
- The legend keeps a fifth row, "Not checked"; the design has four. The halo and focus-ring sizes of a selected map
  mark are not in the design.
- The Summary map reads the file a second time through the worker's existing karyogram action; a small worker change
  could avoid that.
- On a phone the Summary map keeps a 672 px minimum width and scrolls inside its box. Its mark halos are 20 px, short
  of the 24 px WCAG target, which is as close as the geometry allows. There is no scroll hint, because the design has
  none.
- Curated KB strings such as "High Risk Factor" and "Drug Response" are not recased in code. The desktop Markdown and
  CLI still print the raw `wild_type`, `variant_present` and `call_unavailable`. One "partner" is left in
  `MULTI_LOCUS_ASSUMPTION`, shared with the Python vectors.

Deliberately not adopted from the design (so a later review does not report them as gaps):
- **Dropzone `role="button"`:** it would hide the dropzone's two real buttons from assistive technology.
- **Plain progress stage labels:** they need a worker change, and the back end is off limits for design work.
- **HFE " — C282Y" / " — H63D" suffix on the topic:** the KB has no per-variant names, and the back end is off limits
  for design work.
- **Optional foundations items:** a fallback favicon, an `lds-btn-xs` size and hover transitions. The design marks them
  optional and the pages work without them.

## 7. How changes are made here

- **Commits:** subject `type(scope): summary` (`fix(web)`, `feat(pipeline)`, `docs(audit)`, `test(e2e)`).
  - The body is written for a developer reading `git log`: the problem (with a concrete case), the change, why this
    design, and the tests that pin it.
  - Never cite chat rulings, review ids or task ids that live outside the repo.
  - Wrap at 72 columns.
  - Stage files by name.
- **`AUDIT_LEDGER.md` (AGENTS.md section 8):** every remediated finding needs three things in the same commit:
  - a row in the Issue Register under the next free id (P0-011, P1-092 and P2-021 are next);
  - a line in a dated Remediation Log section;
  - a row in that section's `Commit | Scope | Description` table.
- **TDD with evidence:** write the failing test first, see it fail, then fix. A new test must fail if the hunk it
  guards is reverted.
- **PRs:** merge with a merge commit (not squash), so branches that build on each other keep their shared history.
  The owner merges.
- **Never** commit caches, ad-hoc screenshots, downloaded binaries (`bin/` is git-ignored) or `canonical_variome.db`.

## 8. Open items (from `AUDIT_LEDGER.md`)

None. P1-091, P2-018 and P2-019 were remediated on 2026-10-04 (see the ledger's remediation log), and the no-call
regression test for `_vcf_alleles` in `genomic_parser.py` is now `tests/test_vcf_alleles.py`.

## 9. Owner decisions still pending (keep the recorded defaults; do not decide them)

- Homozygous calls at palindromic sites. The default is fail-closed: not interpretable.
- Whether to cite or remove the APOE risk figures (in the APOE Inspector), and the HFE penetrance figures.
- The PR 2 "Decisions to review" list (glossary drafts, breakpoints, APOE map marks and others), in that PR's body.
- The UI tagline.
- The production domain in the Adobe Fonts kit `gfe3vcu`. A kit serves its fonts only to the domains listed in it, so
  the owner must add the production domain there; until then the live site shows the fallback fonts. The kit is the
  owner's, so nobody else adds it. Local and preview hosts may need the same.
- The Vercel project `name`, and a trademark search for "Lucidase".
- Whether AlphaGenome predictions belong in the KB. The only acceptable form is build time, on curated reference
  variants, labelled as model predictions, and never on user data.

## 10. Things in the working tree that are not in git

- **`workspace/`** is the owner's separate Gemini research cache. **Never edit, stage or import from it.**
  - An audit on 2026-10-03 found mislabelled variants: rs63750447 is described as MLH1 T117M Pathogenic, but its
    capture is V384D and benign.
  - AlphaGenome scores were computed at the wrong coordinates for 4 of the 6 variants (TP53 at chr17:7676154, against
    dbSNP's 7675088).
  - Its ClinVar ingest picks the first record of a response.
  - Anything from it must be re-fetched through `tools/fetch_upstream.py` and checked by `tools/source_adapters.py`
    before it can enter the KB.
- **`.env`** holds an API key. Never read it, print it or copy it.
- **`.superpowers/`** holds the local planning and review history from the agents that did the hardening and
  karyogram work (ledgers, briefs, reviews). It is useful context if it exists on your machine, but it is not
  required, and nothing in git depends on it.

## 11. History in one paragraph

GenomePulse was renamed **Lucidase**. The original code passed its Python tests while the browser worker had a
syntax error, and it reported fabricated clinical evidence. **PR #1** made it real:
- a test seam for the browser code;
- alt-allele counting against plus-strand ref/alt;
- one generated KB from pinned real upstream payloads;
- honest APOE and inheritance logic;
- web/desktop parity vectors;
- the privacy test;
- the rename, the fonts and the README.

#1 was merged before its last 27 commits were pushed, and **PR #3** carried those into `main`. **PR #2** added the
karyogram page: pinned UCSC hg19 and hg38 geometry in the KB, a deterministic synthetic sample, a pure layout and SVG
view, the page and worker action, a whole-PR review in four areas, and plain-language copy. All three are merged at
`30602b2`. **PR #5** applied the owner's Lucidase design system on the existing DOM (`745b147`). Design-system **PR 2**
(`feat/design-system-structure`) brings its structure and closed the last open audit items (P1-091, P2-018, P2-019).
