# Handoff: Lucidase, state at 2026-10-03

For any coding or design agent (Claude, Codex, Qwen, Kimi, Gemini and others) picking up this repository. It is
self-contained. Read it top to bottom once. After that, use it as a reference.

```yaml
repo: pterw/lucidase              # private; formerly "genomepulse"; GitHub redirects old URLs
default_branch: main
state_of_main: 30602b2            # merge of PR #2; PRs #1, #3 and #2 are all merged
open_prs: none
next_work: a design system for the web UI (owner-led, with Claude Design), then a review PR
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
  - a guardrail banner, a QC summary and coverage-state cards;
  - an APOE card, a multi-locus section and a filter bar;
  - a findings table with a slide-out variant drawer;
  - Markdown and CSV exports.
- **`web/karyogram.html`**, the karyogram page. It draws the file's markers as dots on the 24 chromosomes, with the
  curated genes ringed by the user's result.

There is also a desktop Python stack (`gui.py`, `genomic_parser.py`, `variant_annotator.py` and others). It is kept,
and it must stay in parity with the web app through the shared vectors in `tests/vectors/*.json`.

## 2. Read these first, in this order

1. `AGENTS.md`: the engineering rules, clinical-honesty and privacy invariants, testing rules, gates and change
   hygiene. **It binds every change.**
2. `docs/design-handoff.md`: **the spec of the current UI.** It covers every screen, state, component and copy
   string, with `file:line` cites, plus the behavioural and honesty requirements any design system must keep. This
   is the input for the design-system work.
3. `README.md` and `web/README.md`: what ships, and how to run it.
4. `AUDIT_LEDGER.md`: every finding (P0/P1/P2), its fix and its commit. Three items are still OPEN (section 8).
5. `CLAUDE.md`: notes for Claude Code sessions. Its owner rulings, gates and mechanics apply to every agent.

## 3. Repository map

| Path | What it is |
|---|---|
| `web/index.html`, `web/karyogram.html` | The two pages: static HTML, ES modules, no bundler |
| `web/src/app.js` | Analysis page controller (DOM, worker lifecycle, drawer, exports) |
| `web/src/karyogram-page.js` | Karyogram page controller |
| `web/src/worker.js` | Web worker: parse, classify, assemble findings, karyogram layout |
| `web/src/core/*.js` | Pure logic (no DOM, no `fetch`, no `self`): parsing, classification, APOE, coverage, KB validation, karyogram layout |
| `web/src/view-model.js` | One view model per record; every row, drawer field and export reads from it |
| `web/src/karyogram-view.js` | Pure SVG renderer for the karyogram |
| `web/src/theme.js` | Light/dark theme, shared by both pages (storage key `lucidase-theme`, attribute `data-theme`) |
| `web/src/kb-loader.js` | The single validating loader for the knowledge base (a JSON module import) |
| `web/src/knowledge-base.json` | **Generated** knowledge base. Never hand-edit it |
| `web/src/styles.css` | Theme variables, badge classes, glass panels, typography overrides |
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
  - Single-variant tests of multi-variant genes carry their limitation on the row, in the drawer and in every export.
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

Results at `30602b2`, from the last full run on the merged tree:
- pytest: 873 passed, 29 subtests;
- node: fail 0;
- e2e: 104 passed;
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

**Status (2026-10-03).** The owner's **Lucidase design system** now owns the look; it superseded the provisional
UI and ruling 15's font mapping. PR 1 (branch `feat/design-system-reskin`) applies it on the existing DOM and
view-model wording; PR 2 brings its structure (grouped report, plain result words in the view model and exports,
docked Inspector, StepNav). See `web/src/ds/README.md` and the "Visual design" rules in `AGENTS.md` and `CLAUDE.md`.
The rest of this section describes the provisional stack it replaced, kept for reference.

**Already decided by the owner (keep these unless the owner changes them):**
- **Name:** **Lucidase**. The UI shows the name as text only.
- **Fonts:** Adobe Fonts kit **`gfe3vcu`**, loaded by both pages. The Tailwind and CSS families are:
  - sans `akzidenz-grotesk-next-pro`;
  - serif `orpheuspro`;
  - mono `input-mono`;
  - display `swiss-721-bt-condensed`.
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
- **Every UI state** listed in `docs/design-handoff.md` must survive:
  - upload, progress, error and results;
  - the coverage states: observed, not tested by array, no-call, insufficient evidence and others;
  - the karyogram's no-file, known-version, unknown-version and error states;
  - the keyboard paths: rows open on Enter and Space, the Export items are buttons, and closing the drawer returns
    focus to the element that opened it.
- **CSP:** no new third-party host. Fonts come only through the Typekit kit, and a new font source needs an owner
  decision plus CSP and test updates.
- **After a visual change:** regenerate `web/src/vendor/tailwind.css` and the README screenshots, and update
  `docs/design-handoff.md` (both its quotes and its `file:line` cites).

**Known design debt, recorded and not fixed:**
- At a 390 px width, the upload button overflows on the analysis page.
- The karyogram's dot sizing is functional, not designed.
- The UI tagline is still an open owner decision.

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

| Id | Where | What | Suggested fix |
|---|---|---|---|
| P1-091 | `tools/fetch_upstream.py` `Capturer.run` | It writes the body and its meta before it checks the status, so a failed recapture overwrites a good pinned fixture. Only `git diff` reveals it. | Write into a staging directory, and promote a capture into `fixtures/upstream/real/` only on success |
| P2-018 | `web/src/karyogram-page.js` `loadSample` | `loadSample` waits on `fetch` before `startWorker` arms the 30 s watchdog, so a demo fetch that never resolves leaves the page loading forever | Arm a timeout around the fetch and send it to the existing error path |
| P2-019 | `tools/build_canonical_kb.py`, `web/src/karyogram-view.js` | `build_kb(..., upstream_root=None)` omits `assemblies` without saying so, and `colByName` is a plain-object lookup. Neither is reachable from the shipped build | Refuse or document the first; make the second a `Map` or use `Object.hasOwn` |

There is also one cheap test to add: `_vcf_alleles` in `genomic_parser.py` should get a regression test for
no-call inputs (`'.'` and `'./.'` with a string allele table must return `None`). An automated reviewer flagged it
with a harness artifact (integer inputs). The real behaviour is correct, but no test pins it.

## 9. Owner decisions still pending (keep the recorded defaults; do not decide them)

- Homozygous calls at palindromic sites. The default is fail-closed: not interpretable.
- Whether to cite or remove the APOE card's risk figures, and the HFE penetrance figures.
- The UI tagline.
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
`30602b2`.
