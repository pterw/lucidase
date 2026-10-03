# CLAUDE.md: Lucidase, formerly GenomePulse (this repository)

Read `AGENTS.md` first. It holds the engineering rules (SoC, SRP, KISS, fail fast, Anti-Corruption Layer),
the clinical honesty and privacy invariants, the testing rules and the gates. This file adds only what an agent
working here needs on top of that.

## Active work

The private repo is `pterw/lucidase` (renamed from `genomepulse` with the owner's OK; GitHub redirects the old URLs).
The controller pushes only commits that passed gate-runner, by explicit SHA, with `git push --atomic`. Implementers
never push. There is no CI: the five local gates are the check.

- **PR #1** (`fix/genomepulse-hardening`) was merged into `main` at `abeaaa3`, before its last 27 commits were
  pushed. Those commits (`abeaaa3..18a7821`: the review fix rounds, the rename, the fonts, the README) are on the
  branch but **not in `main`**. A follow-up PR from that branch into `main` waits on the owner.
  - Its workspace `.superpowers/sdd/2026-10-02-genomepulse-hardening/` is finished and kept for reference.
- **PR #2 (draft)**, branch `feat/karyogram`, based on `fix/genomepulse-hardening`, worked only in the worktree
  `C:/ssw/kary`. It adds the karyogram data-visualisation page (owner rulings 13 and 14) and carries the merge of PR
  #1's branch.
  - Its state of truth is the untracked workspace `.superpowers/sdd/2026-10-03-karyogram/`. Before acting, read the
    last `## RESUME HERE` block of `ledger.md`, then `constraints.md`, `contracts.md` (K-C1..K-C5, with the
    2026-10-03 amendments to K-C3) and `plan.md`.
  - The geometry comes from UCSC tables, fetched once and pinned under `tools/fixtures/upstream/real/ucsc/`.
  - The whole-PR review is done, and its findings have landed. The open owner decisions are listed in the PR body.

Two untracked items at the repo root belong to the owner, and both are excluded locally in `.git/info/exclude`:
- `workspace/`: the owner's separate Gemini agent's research database. Never edit, stage or plug it in. It has real
  captures but has mislabelled data before, so verify on disk before trusting anything from it.
- `.env`: holds an API key. Never read it, print it, or copy it anywhere.

## Owner rulings that bind every change

- Single source of genomic knowledge: `web/src/knowledge-base.json`. It is built by `tools/build_canonical_kb.py`
  from `tools/curation/kb_curation.json` plus the pinned real payloads in `tools/fixtures/upstream/real/`.
  Never hand-edit it, and never commit `canonical_variome.db`.
- The desktop Python stack is kept, and stays in parity with the web app through `tests/vectors/*.json`.
- Visual design and identity are NOT established. Make no design decisions (colours, fonts, themes, components).
  Reproduce the current look exactly. Styling lives in `web/tailwind.config.js`,
  `web/src/tailwind.input.css` (the `@tailwind` directives), `web/src/styles.css` (theme variables, badge classes,
  glass panels, typography overrides) and the vendored daisyUI. A design system will be authored later and will own
  all of them.
- Owner rulings 10, 11, 13 and 15 make exceptions to that:
  - the product is named **Lucidase** (ruling 11), and the UI shows the name text only;
  - the README opens with the controller-designed banner (a light/dark SVG in `docs/assets/`) and screenshots.
    Regenerate the screenshots with `python tools/capture_readme_screenshot.py`;
  - PR #2 adds a karyogram page built from existing classes and theme variables (ruling 13);
  - fonts (ruling 15): the owner's Adobe Fonts kit `gfe3vcu`, mapped as:
    - sans `akzidenz-grotesk-next-pro`;
    - serif `orpheuspro`;
    - mono `input-mono`;
    - display `swiss-721-bt-condensed`.

  Nothing else changes the look until the owner's design system.
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
