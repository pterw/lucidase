# Vendored styles

The page loads no third-party code. Both stylesheets are served from this directory.

| File | Version | Source | sha256 |
|---|---|---|---|
| `daisyui-4.12.10.min.css` | daisyUI 4.12.10 | https://cdn.jsdelivr.net/npm/daisyui@4.12.10/dist/full.min.css (downloaded once, unmodified) | `3c5948b1ebb3a6344521dd01ab3b3660eb95bbdd0b6dfe008cd6f803e99ac054` |
| `tailwind.css` | Tailwind CSS 3.4.17 (generated, minified) | compiled from `web/tailwind.config.js` and `web/src/tailwind.input.css` | changes whenever classes in `index.html`, `karyogram.html` or `src/**/*.js` change |

The Tailwind standalone CLI v3.4.17 is not committed. Put it at `bin/tailwindcss.exe` (or `bin/tailwindcss`);
its sha256 for the Windows build is `67f1c5e3f5a03406a7bf5badf5ada09b79f3ae78ec43450c15f7e983068da346`.
Download: https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17

## Link order in index.html (do not reorder)

`daisyui-4.12.10.min.css`, then `src/styles.css`, then `tailwind.css`. The Tailwind Play CDN used to append its
generated sheet after `styles.css`, so utilities beat the app's equal-specificity rules (dashed dropzone, accent
borders, `text-*` over `.font-serif`, `dark:` over `.glass-panel`). `tests/e2e/test_cascade.py` guards this.

## Regenerate tailwind.css

Run from the repo root after adding or removing any Tailwind class:

```
bin/tailwindcss.exe -c web/tailwind.config.js -i web/src/tailwind.input.css -o web/src/vendor/tailwind.css --minify
```

Check that the committed file is current (writes nothing in the repo):

```
python tools/check_vendored_css.py
```

The only remaining external host is Typekit (fonts), allowed by the CSP in `web/vercel.json` and `web/Dockerfile`.
