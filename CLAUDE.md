# CLAUDE.md: GenomePulse (this repository)

Read `AGENTS.md` first. It holds the engineering rules (SoC, SRP, KISS, fail fast, Anti-Corruption Layer),
the clinical honesty and privacy invariants, the testing rules and the gates. This file adds only what an agent
working here needs on top of that.

## Active work

A subagent-driven hardening pass is in progress on branch `fix/genomepulse-hardening`. Its state of truth is the
untracked workspace `.superpowers/sdd/2026-10-02-genomepulse-hardening/`. Before acting, read the last
`## RESUME HERE` block of `ledger.md`, then `constraints.md` (owner rulings, Lessons, gates, Shared files),
`contracts.md` (C1-C6) and `plan.md`.

## Owner rulings that bind every change

- Single source of genomic knowledge: `web/src/knowledge-base.json`. It is built by `tools/build_canonical_kb.py`
  from `tools/curation/kb_curation.json` plus the pinned real payloads in `tools/fixtures/upstream/real/`.
  Never hand-edit it.
- The desktop Python stack is kept, and stays in parity with the web app through `tests/vectors/*.json`.
- Visual design and identity are NOT established. Make no design decisions (colours, fonts, themes, components).
  Reproduce the current look exactly. Styling config lives only in `web/tailwind.config.js` plus
  `web/src/tailwind.input.css`. A design system will be authored later.
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
- The worker loads the KB with a JSON module import, not `fetch`: `tests/test_zero_knowledge_privacy.py` forbids
  `fetch(` in the worker.
