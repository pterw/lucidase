# CLAUDE.md: Lucidase, formerly GenomePulse (this repository)

Read `AGENTS.md` first. It holds the engineering rules (SoC, SRP, KISS, fail fast, Anti-Corruption Layer),
the clinical honesty and privacy invariants, the testing rules and the gates. This file adds only what an agent
working here needs on top of that.

## Active work

Two pull requests are open on the private repo `pterw/genomepulse`. The repo keeps its old name; renaming it is the
owner's call. The controller pushes only commits that passed gate-runner, by explicit SHA, with
`git push --atomic`. Implementers never push.

- **PR #1 (draft)**, branch `fix/genomepulse-hardening`, in the main tree: the hardening pass, the rename to
  Lucidase and the root README.
  - Its state of truth is the untracked workspace `.superpowers/sdd/2026-10-02-genomepulse-hardening/`. Before acting,
    read the last `## RESUME HERE` block of `ledger.md`, then `constraints.md` (owner rulings, Lessons, gates, Shared
    files), `contracts.md` (C1-C6) and `plan.md`.
  - What remains, in order:
    1. a whole-branch review, one section at a time;
    2. a Chrome inspection;
    3. the final report, after which PR #1 leaves draft.
- **PR #2**, stacked on PR #1: branch `feat/karyogram`, worked only in the worktree `C:/ssw/kary`. It adds a karyogram
  data-visualisation page (owner rulings 13 and 14). Its state of truth is
  `.superpowers/sdd/2026-10-03-karyogram/`.

An untracked `workspace/` folder at the repo root belongs to the owner's separate Gemini agent. It is excluded
locally in `.git/info/exclude`. Never edit, stage or plug it in: its output is unverified, and part of it is
hardcoded data presented as real.

## Owner rulings that bind every change

- Single source of genomic knowledge: `web/src/knowledge-base.json`. It is built by `tools/build_canonical_kb.py`
  from `tools/curation/kb_curation.json` plus the pinned real payloads in `tools/fixtures/upstream/real/`.
  Never hand-edit it.
- The desktop Python stack is kept, and stays in parity with the web app through `tests/vectors/*.json`.
- Visual design and identity are NOT established. Make no design decisions (colours, fonts, themes, components).
  Reproduce the current look exactly. Styling lives in `web/tailwind.config.js`,
  `web/src/tailwind.input.css` (the `@tailwind` directives), `web/src/styles.css` (theme variables, badge classes,
  glass panels, typography overrides) and the vendored daisyUI. A design system will be authored later and will own
  all of them.
- Owner rulings 10, 11 and 13 make exceptions to that:
  - the product is named **Lucidase** (ruling 11), and the UI shows the name text only;
  - the README opens with the controller-designed banner (a light/dark SVG in `docs/assets/`) and screenshots.
    Regenerate the screenshots with `python tools/capture_readme_screenshot.py`;
  - PR #2 adds a karyogram page built from existing classes and theme variables (ruling 13).

  Nothing else changes the look until the owner's design system.
- Product goal: "a real useful tool that does not charge for analyzing uploaded docs". Docs and UI describe only
  shipped behaviour, and the README stays faithful.
- Network access is allowed only when the owner approves it for a specific task. Tests are always offline.

## Gates (all five, in order)

```
python -m pytest tests -q -p no:cacheprovider --ignore=tests/e2e
node --test --test-reporter=spec "web/tests/**/*.test.mjs"
python -m pytest tests/e2e -q -p no:cacheprovider
python tools/build_canonical_kb.py --verify-only
python tools/check_vendored_css.py
```

## Repo-specific mechanics

- Tailwind CLI: `bin/tailwindcss.exe` (v3.4.17, git-ignored). Any class change in `web/index.html` or
  `web/src/**/*.js` means regenerating `web/src/vendor/tailwind.css` with the command in `web/src/vendor/README.md`.
- CSS link order is fixed: daisyUI, then `src/styles.css`, then `src/vendor/tailwind.css` (guarded by
  `tests/e2e/test_cascade.py`).
- e2e tests serve `web/` on an ephemeral port with bundled Chromium. They stub only Typekit; the vendored CSS is real.
- Parallel code phases use detached worktrees at `C:/ssw/t<N>` (short paths for MAX_PATH). Landings are serial in
  the main worktree.
- Line endings: `core.autocrlf=true`. Pinned upstream fixtures are `-text` (`.gitattributes`) so their sha256 holds.
- The worker and the page load the KB through one validating loader, `web/src/kb-loader.js`. It uses a JSON module
  import, not `fetch`. `tests/test_zero_knowledge_privacy.py` forbids `fetch(` in `worker.js`, and scans the loader
  and every `web/src/core/*.js` for telemetry hosts.
