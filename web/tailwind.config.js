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
        sans: ['akzidenz-grotesk-next-pro', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['input-mono', 'ui-monospace', 'monospace'],
        serif: ['orpheuspro', 'Georgia', 'serif'],
        display: ['swiss-721-bt-condensed', 'akzidenz-grotesk-next-pro', 'sans-serif'],
      },
    },
  },
};
