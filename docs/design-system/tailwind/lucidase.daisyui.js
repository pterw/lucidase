/**
 * daisyUI themes for Lucidase (daisyUI 4.x — the version the repo vendors, 4.12.10).
 * Theme names are "light" and "dark" on purpose: the product toggles <html data-theme="light|dark">,
 * so daisyUI components pick up the same switch as the CSS variables.
 * Usage:  daisyui: require("./tailwind/lucidase.daisyui.js")
 */
const shared = {
  "--rounded-box": "0",          // cards / panels: square
  "--rounded-btn": "2px",
  "--rounded-badge": "2px",
  "--tab-radius": "0",
  "--animation-btn": "0",        // no press bounce
  "--animation-input": "0",
  "--btn-focus-scale": "1",
  "--border-btn": "1px",
};
module.exports = {
  themes: [
    {
      light: {
        ...shared,
        "color-scheme": "light",
        primary: "#0893A6", "primary-content": "#FFFFFF",
        secondary: "#0E1A24", "secondary-content": "#FBFAF7",
        accent: "#0893A6", "accent-content": "#FFFFFF",
        neutral: "#0E1A24", "neutral-content": "#FBFAF7",
        "base-100": "#FFFFFF", "base-200": "#FBFAF7", "base-300": "#F4F1EA", "base-content": "#0E1A24",
        info: "#066E7D", success: "#2F7D57", warning: "#B07415", error: "#B53A55",
      },
    },
    {
      dark: {
        ...shared,
        "color-scheme": "dark",
        primary: "#62E4F1", "primary-content": "#0B1117",
        secondary: "#EDF2F5", "secondary-content": "#0B1117",
        accent: "#62E4F1", "accent-content": "#0B1117",
        neutral: "#EDF2F5", "neutral-content": "#0B1117",
        "base-100": "#0F171E", "base-200": "#0B1117", "base-300": "#080D12", "base-content": "#EDF2F5",
        info: "#62E4F1", success: "#5FCB92", warning: "#E9B65A", error: "#F2798F",
      },
    },
  ],
  darkTheme: "dark",
  logs: false,
};
