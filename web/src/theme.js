/**
 * Light/dark theme, shared by index.html and karyogram.html (one stored preference, `lucidase-theme`).
 *
 * Storage is a preference, not data: when it is unavailable (blocked cookies, private mode) every read answers
 * "light" and every write is skipped, and the page keeps working.
 */

export const THEME_KEY = "lucidase-theme";

let current = "light";

/** The stored theme, "light" when nothing valid is stored or storage throws. */
export function readStoredTheme() {
  try {
    return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function getTheme() {
  return current;
}

/** Applies a theme to the page, updates the toggle's icon and text, and stores it when storage allows. */
export function setTheme(theme) {
  current = theme === "dark" ? "dark" : "light";
  try {
    localStorage.setItem(THEME_KEY, current);
  } catch {
    // Storage is unavailable: the theme still applies for this page view.
  }
  document.documentElement.setAttribute("data-theme", current);

  const icon = document.getElementById("theme-toggle-icon");
  const text = document.getElementById("theme-toggle-text");
  if (icon && text) {
    if (current === "dark") {
      icon.textContent = "☀️";
      text.textContent = "Light Mode";
    } else {
      icon.textContent = "🌙";
      text.textContent = "Dark HUD";
    }
  }
}

/** Applies the stored theme and wires the #btn-theme-toggle button. */
export function initTheme() {
  setTheme(readStoredTheme());
  const btnToggle = document.getElementById("btn-theme-toggle");
  if (btnToggle) {
    btnToggle.addEventListener("click", () => setTheme(current === "light" ? "dark" : "light"));
  }
}
