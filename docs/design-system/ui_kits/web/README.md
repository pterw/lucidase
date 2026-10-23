# Lucidase web app — UI kit

Click-through recreation of the two static pages in `pterw/lucidase/web`: `index.html` (analysis) and `karyogram.html`, rebuilt on this design system.

- **Analysis** — idle dropzone → progress → results: scope notice, sample panel (QC chips + coverage-state count strip, which also filters), APOE composite panel, filter tabs + search + export, findings table, docked record inspector.
- **Karyogram** — reference-only state on load; "Try a made-up example file" switches to the result state.

Structure follows the repo (regions, flow, states H1–H14 from `docs/design-handoff.md`). Visual treatment is the new system: no emoji, no gradient tile, no nested tinted boxes, no eyebrow labels, no "State N" codes.

Data in `data.js` is a made-up example; every count on screen is computed from those rows. The karyogram density dots for the example file are seeded noise (the real page computes them from the file); the "Markers in your file" totals are left as "Not available" rather than invented.

Sources are the `.jsx` files plus `app.jsx`; `index.html` loads the precompiled `kit.compiled.js` (no in-browser Babel, so it renders instantly). Re-compile after editing a `.jsx` source.

Files: `index.html`, `kit.compiled.js`, `app.jsx`, `Shell.jsx`, `AnalysisScreen.jsx`, `RecordInspector.jsx`, `meta.js`, `KaryogramScreen.jsx`, `data.js`.
