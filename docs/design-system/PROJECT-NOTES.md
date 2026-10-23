# Project instructions

- Fonts: keep the Adobe Fonts kit gfe3vcu (use.typekit.net). Ignore check_design_system warnings about missing project font files for orpheuspro, akzidenz-grotesk-next-pro, akzidenz-grotesk-next-conden, input-mono, input-mono-narrow. Do not self-host or substitute.
- Ignore the check_design_system warning about ~64 custom properties under `:root:not([data-theme="light"])` in tokens/colors.css. It is the intentional prefers-color-scheme mirror of the `[data-theme="dark"]` block; keep the two in sync and do not move it.
- Section naming: use "Pharmacology" (not "Medicines") for drug-response results.
