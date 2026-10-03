/** @type {import('tailwindcss').Config} */
module.exports = {
  content: {
    relative: true,
    files: ["./index.html", "./src/**/*.js"],
  },
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['gotham', 'nimbus-sans', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['attribute-mono', 'ballinger-mono', 'azo-mono', 'monospace'],
        serif: ['orpheuspro', 'archer-pro', 'Georgia', 'serif'],
        display: ['neuzeit-grotesk-condensed', 'gotham', 'sans-serif'],
      },
    },
  },
};
