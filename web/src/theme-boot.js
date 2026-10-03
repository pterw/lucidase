// Sets the theme before first paint, so a stored dark override never flashes light. The rule is theme.js's: the
// stored override, else the device setting. A classic script file, not inline, because the CSP is script-src 'self'.
//
// Migration (keep in step with theme.js): before the design system every first visit stored "light" without a
// choice, so a "lucidase-theme" written without the "lucidase-theme-v" marker is not an override when it is "light".
// An unmarked "dark" was always a choice and is kept. After this runs once, the marker is set.
(function () {
  var theme = null;
  try {
    var stored = localStorage.getItem("lucidase-theme");
    if (localStorage.getItem("lucidase-theme-v") !== "2") {
      if (stored === "light") {
        localStorage.removeItem("lucidase-theme");
        stored = null;
      }
      localStorage.setItem("lucidase-theme-v", "2");
    }
    if (stored === "dark" || stored === "light") theme = stored;
  } catch (e) {
    // Storage is unavailable: follow the device.
  }
  if (theme === null && typeof window.matchMedia === "function") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (theme !== null) document.documentElement.setAttribute("data-theme", theme);
})();
