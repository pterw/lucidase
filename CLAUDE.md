# CLAUDE.md: Lucidase, formerly GenomePulse (this repository)

Read `AGENTS.md` first. It holds the engineering rules (SoC, SRP, KISS, fail fast, Anti-Corruption Layer),
the clinical honesty and privacy invariants, the testing rules and the gates. This file adds only what an agent
working here needs on top of that.

## Active work

All pull requests are merged (#1, #3, #2; `main` at `30602b2`). The current state, the open items and the design-system
notes are in `docs/HANDOFF.md`; read it after `AGENTS.md`. The controller pushes only commits that passed all five
gates, by explicit SHA, with `git push --atomic`. Implementers never push. There is no CI.

Two untracked items at the repo root belong to the owner, and both are excluded locally in `.git/info/exclude`:
- `workspace/`: the owner's separate Gemini agent's research database. Never edit, stage or plug it in. It has real
  captures but has mislabelled data before, so verify on disk before trusting anything from it.
- `.env`: holds an API key. Never read it, print it, or copy it anywhere.

## Owner rulings that bind every change

- Single source of genomic knowledge: `web/src/knowledge-base.json`. It is built by `tools/build_canonical_kb.py`
  from `tools/curation/kb_curation.json` plus the pinned real payloads in `tools/fixtures/upstream/real/`.
  Never hand-edit it, and never commit `canonical_variome.db`.
- The desktop Python stack is kept, and stays in parity with the web app through `tests/vectors/*.json`.
- Visual design and identity are owned by the **Lucidase design system** (owner ruling, 2026-10-03), authored by
  the owner in Claude Design. It supersedes the provisional look and ruling 15's font mapping. Follow it; do not
  invent colours, fonts, spacing or components outside it, and ask the owner when it does not cover a case.
  - Tokens are vendored unchanged in `web/src/ds/` (see its README); `web/src/styles.css` imports them and holds the
    daisyUI theme bridge and the design system's components as `lds-*` classes; `web/src/ds/lucidase.preset.cjs` is
    the Tailwind preset. Brand SVGs are in `web/src/brand/`, the vendored Lucide icons in `web/src/icons/`.
  - Fonts: the owner's Adobe Fonts kit `gfe3vcu`: serif `orpheuspro` (headings, prose), sans
    `akzidenz-grotesk-next-pro` (UI), condensed `akzidenz-grotesk-next-conden` (column heads, counts; Swiss 721 BT
    Condensed only as a fallback), mono `input-mono` and `input-mono-narrow` (rsIDs, genotypes, dense tables).
  - Copy: sentence case, no eyebrows above headings, no emoji, "Not available" for missing values, and the absence
    wording rules in `AGENTS.md`. The theme follows the device; the override is a footer link.
- Owner rulings 10, 11 and 13 still hold:
  - the product is named **Lucidase** (ruling 11);
  - the README opens with the controller-designed banner (a light/dark SVG in `docs/assets/`) and screenshots.
    Regenerate the screenshots with `python tools/capture_readme_screenshot.py`;
  - the karyogram page (ruling 13).
- The design system lands in two steps. PR 1 (this reskin) applies it on the existing DOM, flow and view-model
  wording. PR 2 brings its structure: the grouped report (Pharmacology, Health risk factors, Carrier status, Traits),
  the plain result words (Found, Not found, Not on your chip, Unclear, Not checked) in the view model and exports,
  the docked Inspector and the three-step StepNav.
- Product goal: "a real useful tool that does not charge for analyzing uploaded docs". Docs and UI describe only
  shipped behaviour, and the README stays faithful.
- Network access is allowed only when the owner approves it for a specific task. Tests are always offline.
- Owner decisions still pending:
  - homozygous calls at palindromic sites (review S1b-C-3);
  - whether to cite or remove the APOE card's risk figures;
  - the UI tagline;
  - the Vercel project `name`;
  - a trademark search.

  Do not decide them; keep the recorded defaults.

## Gates (all five, in order)

```
python -m pytest tests -q -p no:cacheprovider --ignore=tests/e2e
node --test --test-reporter=spec "web/tests/**/*.test.mjs"
python -m pytest tests/e2e -q -p no:cacheprovider
python tools/build_canonical_kb.py --verify-only
python tools/check_vendored_css.py
```

Run e2e with a long command timeout (600000 ms). It takes about 2 minutes, longer under load, and a 120 s shell timeout
kills it mid-run with no summary line. That looks like a failure but is not one.

## Repo-specific mechanics

- Tailwind CLI: `bin/tailwindcss.exe` (v3.4.17, git-ignored). Any class change in `web/*.html` or
  `web/src/**/*.js` means regenerating `web/src/vendor/tailwind.css` with the command in `web/src/vendor/README.md`.
  Worktrees have no `bin/`, so code phases set `TAILWIND_CLI` to the absolute path.
- CSS link order is fixed: daisyUI, then `src/styles.css`, then `src/vendor/tailwind.css` (guarded by
  `tests/e2e/test_cascade.py`).
- e2e tests serve `web/` on an ephemeral port with bundled Chromium. They stub only Typekit; the vendored CSS is real.
- Parallel code phases use detached worktrees at short paths under `C:/ssw/` (for MAX_PATH). Landings are serial,
  in the main tree for PR #1 and in `C:/ssw/kary` for PR #2. Remove a worktree only after checking that its leftover
  files match the landed commit.
- Line endings: `core.autocrlf=true`. Pinned upstream fixtures are `-text` (`.gitattributes`) so their sha256 holds.
  Tests must never assert on working-tree line endings.
- The worker and the page load the KB through one validating loader, `web/src/kb-loader.js`. It uses a JSON module
  import, not `fetch`. `tests/test_zero_knowledge_privacy.py` scans `worker.js`, the loader and every
  `web/src/core/*.js` for network primitives and telemetry hosts.
- Implementers have claimed fixes they did not make. Every task goes through review and gate-runner before push,
  never on its own report.
