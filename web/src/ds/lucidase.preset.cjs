/**
 * Lucidase design system: Tailwind CSS v3 preset (from the design system's tailwind/lucidase.preset.js).
 * Colours resolve to the CSS custom properties in ds/colors.css, so `dark:` and the daisyUI theme bridge in
 * styles.css follow [data-theme] exactly like the page. Motion values are the ones in ds/motion.css
 * (100/150/200/240 ms, ease-out-quart); the design system's preset file said 300 ms and a different curve,
 * which contradicted its own tokens and README.
 * Kept as .cjs so the Tailwind content glob (./src/** /*.js) does not scan it for class names.
 */
const v = (name) => `var(--${name})`;
const tone = (p) => ({ DEFAULT: v(p), ink: v(`${p}-ink`), wash: v(`${p}-wash`), line: v(`${p}-line`) });
const cat = (p) => ({ ink: v(`cat-${p}-ink`), wash: v(`cat-${p}-wash`), line: v(`cat-${p}-line`) });

module.exports = {
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        paper: { DEFAULT: v("paper"), sunk: v("paper-sunk"), raised: v("paper-raised") },
        ink: { DEFAULT: v("ink"), muted: v("ink-muted"), subtle: v("ink-subtle") },
        line: { DEFAULT: v("line"), strong: v("line-strong") },
        dot: v("dot"),
        "on-ink": v("on-ink"),
        accent: { DEFAULT: v("accent"), ink: v("accent-ink"), hover: v("accent-hover"), wash: v("accent-wash"), line: v("accent-line"), on: v("on-accent") },
        state: {
          observed: tone("state-observed"), "not-observed": tone("state-not-observed"), "array-gap": tone("state-array-gap"),
          outside: tone("state-outside"), insufficient: tone("state-insufficient"),
        },
        cat: { pathogenic: cat("pathogenic"), risk: cat("risk"), carrier: cat("carrier"), pgx: cat("pgx"), trait: cat("trait"), "not-detected": cat("not-detected") },
        danger: { ink: v("danger-ink"), wash: v("danger-wash"), line: v("danger-line") },
        notice: { ink: v("notice-ink"), wash: v("notice-wash"), line: v("notice-line") },
        ok: v("ok"),
      },
      fontFamily: {
        serif: ["orpheuspro", "Georgia", "serif"],
        sans: ["akzidenz-grotesk-next-pro", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
        condensed: ["akzidenz-grotesk-next-conden", "swiss-721-bt-condensed", "Arial Narrow", "sans-serif"],
        mono: ["input-mono", "ui-monospace", "monospace"],
        "mono-narrow": ["input-mono-narrow", "input-mono", "ui-monospace", "monospace"],
        display: ["orpheuspro", "Georgia", "serif"],
      },
      fontSize: {
        "11": ["11px", "1.45"], "12": ["12px", "1.45"], "13": ["13px", "1.45"], "14": ["14px", "1.45"], "15": ["15px", "1.55"],
        "16": ["16px", "1.6"], "18": ["18px", "1.3"], "20": ["20px", "1.3"], "24": ["24px", "1.2"], "30": ["30px", "1.15"],
        "38": ["38px", "1.1"], "48": ["48px", "1.1"], "64": ["64px", "1.05"],
      },
      borderRadius: { none: "0", panel: "0", control: "2px", badge: "2px", DEFAULT: "2px", sm: "2px", md: "2px", lg: "2px", xl: "2px", full: "9999px" },
      boxShadow: { menu: v("shadow-menu"), none: "none" },
      maxWidth: { layout: v("layout-max") },
      width: { inspector: v("inspector-w"), margin: v("margin-col") },
      spacing: { header: v("header-h") },
      transitionDuration: { instant: "100ms", fast: "150ms", base: "200ms", slow: "240ms" },
      transitionTimingFunction: { standard: "cubic-bezier(.25,1,.5,1)" },
      backgroundImage: { dotfield: v("pattern-dotfield") },
    },
  },
};
