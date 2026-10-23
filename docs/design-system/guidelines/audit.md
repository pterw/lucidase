# Audit of v1 (Oct 2026) and the v2 direction

Audit run against the Impeccable anti-pattern catalog (impeccable.style/slop: 61 detector rules + 6 review patterns), the repo's own `.agent/skills/frontend-design.md` and `.agent/workflows/audit.md` / `critique.md`, and data-density principles (Tufte's data-ink; vertical + layered density; progressive disclosure).

## Verdict on v1: FAIL — reads as a tidy SaaS dashboard

| Finding (Impeccable rule) | Where in v1 | Severity |
|---|---|---|
| Wrap everything in cards / monotonous spacing | Every section a bordered Panel, same 24px pad, same 24px gap | High |
| Hero metric layout / identical card grid | CountStrip: 5 equal cells, big number, small label, note | High |
| Centered hero template | Dropzone: centered icon + headline + copy + 2 buttons | High |
| Decorative grid-line background | `.lds-dotfield` on the page body | Medium |
| Hairline border with wide shadow ("ghost card") | Drawer and Menu: 1px line + broad blur shadow | Medium |
| Modal abuse | Record drawer is a modal with scrim; hides the table being inspected | Medium |
| Pulsing/status-dot pattern | Header "Read in this browser" green dot | Low |
| Chip soup (colour without hierarchy) | 2–3 tinted badges per table row | High |
| Low-contrast text | `--ink-subtle` #7A8690 on paper ≈3.6:1 used for text; white on accent #0893A6 ≈3.6:1 on the primary button | Critical (WCAG AA) |
| Tiny interface text | 11–12px labels and badges | Medium |
| Animation that changes layout | Progress / ProbabilityBar animate `width` | Low |
| Cream/beige palette by reflex | Kept deliberately: paper #FBFAF7 is the logo's ground. Neutrals must not drift warmer | Note |

## v2 direction: "the specimen report"

The product is a report about one file. v2 designs it like a laboratory report / journal figure page, not a dashboard:

1. **Ledger grid, not cards.** Each report section is a row of a two-column grid: a fixed margin column holding the section heading (serif), and the content column. Sections are separated by hairline rules and generous space; contents are tight. No bordered boxes except the drop field and the inspector pane.
2. **The karyogram is Figure 1.** Results open with the karyogram figure showing where the 14 loci sit and their state. The counts are its legend, written as a line of text — the figure replaces the hero-metric strip and is the logo motif doing real work.
3. **State marks by shape + colour + word.** ● observed · ○ not detected · dashed ring not on array · small dot outside coverage · half-filled insufficient evidence. Colourblind-safe, echoes the karyogram dots. No tinted chips.
4. **Limitations as numbered footnotes.** A superscript marker on the row links to a numbered note in the report's notes section and in the inspector — the scientific convention, and the honesty rule made visible.
5. **The ligature as a connector.** Composite results (APOE from rs429358 + rs7412) draw the two markers joined by the wordmark's arch into one result. Used only where two things genuinely join.
6. **Ink is primary; teal is the dot.** Primary buttons are ink on paper (≥15:1). Teal appears only as the logo uses it: one point of colour — focus, selection, links, the observed mark.
7. **Docked inspector.** Record details open in a non-modal pane beside the table on wide screens; a full sheet on narrow screens.
8. **Rhythm.** 4/8/12 inside groups, 56–72 between report sections. Body 15px sans, prose 17px serif, 12px floor. Prose max 68ch.
9. **Motion** only transform/opacity, ease-out-quart, ≤240ms; nothing loops.
