/** @type {import('tailwindcss').Config} */
module.exports = {
  // The Lucidase design system preset: colours, fonts, sizes, radii and motion as CSS-variable references.
  presets: [require("./src/ds/lucidase.preset.cjs")],
  content: {
    relative: true,
    files: ["./index.html", "./karyogram.html", "./src/**/*.js"],
  },
};
