// Sets the theme before first paint, so a stored dark override never flashes light. The rule is theme.js's: the
// stored override, else the device setting. A classic script file, not inline, because the CSP is script-src 'self'.
(function () {
  var theme = null;
  try {
    var stored = localStorage.getItem("lucidase-theme");
    if (stored === "dark" || stored === "light") theme = stored;
  } catch (e) {
    // Storage is unavailable: follow the device.
  }
  if (theme === null && typeof window.matchMedia === "function") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (theme !== null) document.documentElement.setAttribute("data-theme", theme);
})();
