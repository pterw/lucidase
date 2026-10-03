/**
 * Light/dark theme, shared by index.html and karyogram.html (one stored preference, `lucidase-theme`).
 *
 * The page follows the device setting (prefers-color-scheme), live, until the person overrides it from the footer.
 * Only an override is stored; "Use device setting" clears it. src/theme-boot.js applies the same rule before first
 * paint. Storage is a preference, not data: when it is unavailable (blocked cookies, private mode) every read answers
 * "no override" and every write is skipped, and the page keeps working.
 */

export const THEME_KEY = "lucidase-theme";
// Marks a stored value as written by this version. theme-boot.js migrates unmarked values (see there): an unmarked
// "light" was the old page's automatic default, not a choice.
const THEME_VERSION_KEY = "lucidase-theme-v";
const THEME_VERSION = "2";

const DARK_QUERY = "(prefers-color-scheme: dark)";

let override = null; // "light" | "dark" | null (follow the device)
let current = "light";

/** The stored override, or null when nothing valid is stored, an unmarked legacy "light" is stored, or storage throws. */
export function readStoredTheme() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    if (value === "light" && localStorage.getItem(THEME_VERSION_KEY) !== THEME_VERSION) return null;
    return value === "dark" || value === "light" ? value : null;
  } catch {
    return null;
  }
}

function writeStoredTheme(value) {
  try {
    localStorage.setItem(THEME_VERSION_KEY, THEME_VERSION);
    if (value === null) localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, value);
  } catch {
    // Storage is unavailable: the theme still applies for this page view.
  }
}

function deviceTheme() {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function getTheme() {
  return current;
}

/** Shows the opposite theme on the footer link, and "Use device setting" only after an override. */
function renderControls() {
  const next = current === "dark" ? "light" : "dark";
  const icon = document.getElementById("theme-toggle-icon");
  const text = document.getElementById("theme-toggle-text");
  if (icon) icon.className = `lds-icon lds-icon-14 ${next === "dark" ? "lds-i-moon" : "lds-i-sun"}`;
  if (text) text.textContent = next === "dark" ? "Dark theme" : "Light theme";
  const system = document.getElementById("btn-theme-system");
  if (system) system.classList.toggle("hidden", override === null);
}

function apply() {
  current = override ?? deviceTheme();
  document.documentElement.setAttribute("data-theme", current);
  renderControls();
}

/** Overrides the device setting with a theme, and stores it when storage allows. */
export function setTheme(theme) {
  override = theme === "dark" ? "dark" : "light";
  writeStoredTheme(override);
  apply();
}

/** Drops the override: the page follows the device setting again. */
export function useDeviceTheme() {
  override = null;
  writeStoredTheme(null);
  apply();
}

/** Applies the stored override (or the device setting) and wires the footer's theme links. */
export function initTheme() {
  override = readStoredTheme();
  apply();
  if (typeof window.matchMedia === "function") {
    const query = window.matchMedia(DARK_QUERY);
    const onChange = () => {
      if (override === null) apply();
    };
    if (query.addEventListener) query.addEventListener("change", onChange);
    else if (query.addListener) query.addListener(onChange);
  }
  const toggle = document.getElementById("btn-theme-toggle");
  if (toggle) toggle.addEventListener("click", () => setTheme(current === "light" ? "dark" : "light"));
  const system = document.getElementById("btn-theme-system");
  if (system) system.addEventListener("click", useDeviceTheme);
}
