# Source of this folder

This folder is the reference copy of the Lucidase design system. The product owner authored it in Claude Design
(project "Lucidase Design System", id 2410068c-80ef-4a71-8ca3-04f37e6c6c1b) and it was pulled on 2026-10-22. The
files are byte-for-byte copies, and `.gitattributes` marks them `-text` so line endings are never rewritten.

## Not copied

- `_ds_bundle.js`, `_ds_manifest.json`, `ui_kits/web/kit.compiled.js` and `ui_kits/web/index.html` are generated
  output, and the bundle and the HTML load React from a CDN.
- Every `*.card.html` is a preview card that loads React from a CDN. `thumbnail.html` is a preview page.
- `_adherence.oxlintrc.json` is a lint config for the design project itself.
- `uploads/` is scratch space from the design session.

## Renamed

`PROJECT-NOTES.md` is the design project's own `CLAUDE.md`. It is renamed so that Claude Code does not load it
automatically as an instruction file for this folder.

## Icons

`icons/lucide-0.469.0/` holds the 16 Lucide 0.469.0 SVGs the design uses. They were fetched once from
`lucide-static@0.469.0`. The ISC `LICENSE` and a `SHA256SUMS` file are included.

## How the app relates to this folder

The app's working copies (tokens and Tailwind preset) are in `web/src/ds/`. They differ from this folder only where
`web/src/ds/README.md` records it, and `web/tests/ds-reference.test.mjs` checks that they match. This folder is the
reference: edit it only when re-syncing from the design project.
