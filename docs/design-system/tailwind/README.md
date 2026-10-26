# Tailwind CSS + daisyUI

The product already uses Tailwind 3.4.17 (compiled) + daisyUI 4.12.10 (vendored) with `darkMode: ['selector','[data-theme="dark"]']`. These files keep that wiring and point it at Lucidase tokens.

| File | For |
|---|---|
| `lucidase.preset.js` | Tailwind v3 preset — colours, fonts, sizes, radii, shadows as CSS-variable references |
| `lucidase.daisyui.js` | daisyUI 4 `light` / `dark` themes (square boxes, 2px controls, no button animation) |
| `lucidase.v4.css` | Tailwind v4 `@theme inline` equivalent |

## Load order (unchanged from the repo, and still load-bearing)

```html
<link rel="stylesheet" href="https://use.typekit.net/gfe3vcu.css"> <!-- or via styles.css -->
<link rel="stylesheet" href="vendor/daisyui.min.css">              <!-- optional -->
<link rel="stylesheet" href="lucidase-ds/styles.css">
<link rel="stylesheet" href="vendor/tailwind.css">                 <!-- utilities LAST -->
```

## No Node.js?

Use the components' plain inline-style versions (`components/**`) or write HTML with the CSS variables directly — `styles.css` works with no build step. Tailwind is optional.

## Class cheatsheet

- Report section: `flex flex-wrap gap-x-10 pt-7 border-t border-line` (heading `basis-[200px] font-serif text-24`). No card wrappers.
- Primary button: `h-9 px-3.5 rounded-control bg-ink text-on-ink hover:bg-ink-muted font-sans font-bold text-14`
- Coverage badge: `inline-flex items-center gap-1.5 h-[22px] px-[7px] rounded-badge border bg-state-not-observed-wash border-state-not-observed-line text-state-not-observed-ink text-12 font-bold`
- Heading: `font-serif text-24 tracking-[-0.015em]` (no eyebrow above it)
- Data: `font-mono text-13`
