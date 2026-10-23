# Avoiding AI-slop UI

"AI slop" is the generic look models fall back to when nothing constrains them. Public write-ups converge on the same tells; this file maps each one to a Lucidase rule. Read it before generating any Lucidase screen, and run the checklist at the end before calling work done.

Sources consulted (Oct 2026): mindstudio.ai "How to avoid AI slop…", github.com/LeoStehlik/no-slop-ui, aiuxplayground.com "Unslop my UI", docs.bswen.com "AI-generated UI anti-patterns", agent-design.com "Stop AI UI looking templated", design.sis.gov.uk AI patterns.

## The tells, and what Lucidase does instead

| Slop tell | Lucidase rule |
|---|---|
| Inter / Geist / Roboto / system-ui as the voice | Orpheus Pro (serif) + Akzidenz-Grotesk Next (sans) + Input Mono, from the product's Adobe kit. Never substitute Inter. |
| Blue/indigo/purple primary, purple-to-blue gradients, gradient text | One accent, teal `#0893A6` / `#62E4F1`, taken from the wordmark. No gradients anywhere — not on bars, tiles, text or backgrounds. Violet exists only as the pharmacogenomics category ink. |
| Gradient icon tile + emoji as the logo (the repo's current 🧬 square) | The wordmark SVG is the only mark. No icon tile. |
| Large rounded corners on every card and button | Panels 0px. Controls and badges 2px. Only data dots are round. |
| Glassmorphism, frosted panels, backdrop blur | Solid surfaces. The header is solid paper with a 1px rule. The repo's `.glass-panel` blur is retired. |
| Cards in cards; tinted mini-cards inside panels | One container (`Panel`). Inside it: rules, `CountStrip`, `DataList`, `DrawerSection`. Never a bordered box in a bordered box. |
| Fake metric grids, vanity stats, "99.9% accurate" | Only counts the analysis produced, each with a plain label. Missing values read "Not available". No testimonials, no user counts, no accuracy claims. |
| Eyebrow / kicker labels over headings ("COMPOUND HAPLOTYPE SYNTHESIS") | None, ever. Headings stand alone, sentence case. |
| Vague SaaS copy ("Engineered for…", "Zero-Knowledge Clinical & Proteomic…", "transform your workflow") | Say what it does and what it does not: "Your file is read in this browser and never uploaded." |
| Hero section where a product screen should be | The first screen is the dropzone — the tool itself. |
| Three-up identical feature cards | No feature grids. Explanations are prose. |
| Bounce, scale, spring hovers; pulsing dots | Colour/border transitions only, ≤300ms, zeroed under reduced motion. The privacy dot is still. |
| Soft drop shadows everywhere | 1px lines. Shadows only on the menu and the drawer. |
| 50px+ padding everywhere | Product density: 24px panels, 16px gutters at small sizes, 36px controls. |
| Cyan/neon accents on dark | The dark accent `#62E4F1` is the logo's own, so it stays — but only on loci dots, focus rings, the primary button and links. Never glows, large fills or body text. |
| Italic serif hero headlines | Italic is reserved for the wordmark and the banner tagline. Headings are upright Orpheus. |
| Cream "premium" parchment backgrounds | Paper `#FBFAF7` is the logo's ground and sits close to white; don't push it warmer. |
| Colour or icon as the only signal | Every state/category badge carries text; dots are supplementary. |
| Emoji as icons | Lucide line icons (CDN) beside text labels; no emoji. |

## Review checklist

1. Any gradient, blur, glow, or emoji? → remove.
2. Any radius above 2px on a box? → 0.
3. Any bordered/tinted box inside a Panel? → flatten to rules.
4. Any label above a heading? → delete it.
5. Any number not produced by the analysis (or by a stated model)? → delete it.
6. Any claim the product cannot back (diagnosis, "zero-knowledge", accuracy, "clinical-grade")? → rewrite factually.
7. Any state shown by colour alone? → add the text label.
8. Fonts other than the five kit families? → replace.

Two or more failures: revise before shipping.

## Added Oct 2026

| Slop tell | Lucidase rule |
|---|---|
| Logo artwork shrunk into the nav bar, recoloured to fit the chrome | Product name as text in the bar; the wordmark appears once as a Masthead with clear space, in approved artwork only |
| Sticky header by default | Static header; only the Inspector sticks, inside its own column |
| Theme switch as a header showpiece | Follow the device; a quiet override link lives in the footer |
