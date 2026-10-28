/**
 * Lucidase — Tailwind CSS v3 preset (+ optional daisyUI themes).
 * Colours resolve to the CSS custom properties in styles.css, so `dark:` and the
 * daisyUI themes both follow [data-theme] exactly like the product (web/tailwind.config.js).
 *
 *   // tailwind.config.js
 *   module.exports = {
 *     presets: [require("./lucidase-ds/tailwind/lucidase.preset.js")],
 *     content: ["./index.html", "./src/** /*.js"],
 *     plugins: [require("daisyui")],                       // optional
 *     daisyui: require("./lucidase-ds/tailwind/lucidase.daisyui.js"),
 *   };
 *   // and link lucidase-ds/styles.css BEFORE the compiled Tailwind sheet.
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
        serif: ["mencken-std", "Georgia", "serif"],
        sans: ["akzidenz-grotesk-next-pro", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
        condensed: ["akzidenz-grotesk-next-conden", "swiss-721-bt-condensed", "Arial Narrow", "sans-serif"],
        mono: ["input-mono", "ui-monospace", "monospace"],
        "mono-narrow": ["input-mono-narrow", "input-mono", "ui-monospace", "monospace"],
        display: ["mencken-std", "Georgia", "serif"],
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
      spacing: { "header": v("header-h") },
      transitionDuration: { instant: "100ms", fast: "150ms", base: "200ms", slow: "300ms" },
      transitionTimingFunction: { standard: "cubic-bezier(.2,0,0,1)" },
      backgroundImage: { dotfield: v("pattern-dotfield") },
    },
  },
};
