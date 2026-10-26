# Lucidase design system (vendored)

The page styles are built on the Lucidase design system, authored by the owner in Claude Design (project
"Lucidase Design System", handoff of 2026-10-03). It supersedes the provisional look and owner ruling 15's font
mapping (see `CLAUDE.md`).

| File | Source in the design system | Changes |
|---|---|---|
| `colors.css`, `typography.css`, `spacing.css`, `shape.css`, `motion.css`, `base.css` | `tokens/*.css` | none (copied unchanged) |
| `lucidase.preset.cjs` | `tailwind/lucidase.preset.js` | the differences listed under "Recorded differences" below |
| `../brand/*.svg` | `assets/logo/` (favicon, lockup, wordmark; light and dark) | none |
| `../icons/*.svg` | Lucide `lucide-static@0.469.0` (ISC, `../icons/LICENSE`), the set the design system's `Icon` names | none; 17 icons (every one is used; `external-link` and `chevron-down` were removed as unused), served same-origin instead of from a CDN |

Recorded differences (`web/tests/ds-reference.test.mjs` asserts exactly these and nothing else):
- The six token CSS files: none, byte-for-byte equal after line endings.
- `lucidase.preset.cjs`, header comment: rewritten to say where the file comes from and why it is `.cjs`; the code after it is compared.
- `lucidase.preset.cjs`, `transitionDuration.slow`: `240ms` (the original said `300ms`), to match `motion.css`.
- `lucidase.preset.cjs`, `transitionTimingFunction.standard`: `cubic-bezier(.25,1,.5,1)` (ease-out-quart; the original said `cubic-bezier(.2,0,0,1)`).
- `lucidase.preset.cjs`, `spacing`: the key is written `header`, not `"header"` (formatting only).

Departures that live in the app's code rather than in these files:
- Theme storage key: `lucidase-theme-v` holds the value `2` once a visit has run under this version. Before the design
  system every first visit stored `light` without a choice, so a stored `light` with no marker is read as "no override"
  and removed; an unmarked `dark` was always a choice and is kept (`../theme-boot.js`, `../theme.js`; keep the two in step).
- Karyogram density dots: `.kary-bin` fills with `--ink-subtle` at 0.7 opacity, not the design's `--dot`, because the
  dots encode density and `--dot` is a decorative tone too faint to read as data (`../styles.css`).
- Masthead breakpoint: the design shows the lockup at 560 px wide and above; the app decides from the viewport
  (`@media (max-width: 559px)` switches to the wordmark alone), not from the masthead's own width
  (`../styles.css`, `.lds-masthead`).

Not copied:
- `tokens/fonts.css`: it `@import`s the Adobe Fonts kit `gfe3vcu`, which both pages already link once in `<head>`.
- `tailwind/lucidase.daisyui.js`: daisyUI is vendored as a prebuilt stylesheet, not a Tailwind plugin, so its theme
  values are set as variables at the top of `../styles.css` (the "daisyUI theme bridge").
- The React components: the pages are plain ES modules with no build step and a `script-src 'self'` CSP, so the
  components are ported as `lds-*` CSS classes in `../styles.css`, one block per component.

Lucide icons, sha256 of the npm tarball `lucide-static-0.469.0.tgz` they were taken from:
`c4d7d11a4c5ebd5e6dcb21c50f7fb65aeda9a48e97827d1eb4d7638fd1ec694b`.

Keep the `@media (prefers-color-scheme: dark)` block in `colors.css` in sync with its `[data-theme="dark"]` block: it is
the no-JS mirror that lets the page follow the device before `theme-boot.js` runs.
