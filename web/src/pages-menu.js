/**
 * The header's "Pages" disclosure, shared by both pages (design system AppHeader, narrow form).
 *
 * Below 680px the CSS hides the page links in the header and shows the toggle; the panel #lds-pages holds the same
 * links. State lives in the toggle's aria-expanded and the panel's hidden attribute, nowhere else. Escape closes the
 * panel and returns focus to the toggle; a click outside the header, or on a link in the panel, closes it.
 * The 680px breakpoint is the design system's (AppHeader) and must match the media query in styles.css.
 */

export function initPagesMenu() {
  const toggle = document.querySelector(".lds-pages-toggle");
  const panel = toggle && document.getElementById(toggle.getAttribute("aria-controls"));
  if (!toggle || !panel) return;
  const icon = toggle.querySelector(".lds-icon");
  const header = toggle.closest("header");

  const setOpen = (open) => {
    toggle.setAttribute("aria-expanded", String(open));
    panel.hidden = !open;
    if (icon) {
      icon.classList.toggle("lds-i-menu", !open);
      icon.classList.toggle("lds-i-x", open);
    }
  };
  const isOpen = () => toggle.getAttribute("aria-expanded") === "true";

  setOpen(false);
  toggle.addEventListener("click", () => setOpen(!isOpen()));
  panel.addEventListener("click", (e) => {
    if (e.target.closest("a")) setOpen(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !isOpen()) return;
    setOpen(false);
    toggle.focus();
  });
  document.addEventListener("pointerdown", (e) => {
    if (isOpen() && !header.contains(e.target)) setOpen(false);
  });
  // At 680px and wider the CSS hides the toggle and the panel, so the disclosure resets to closed.
  window.matchMedia("(min-width: 680px)").addEventListener("change", (e) => {
    if (e.matches) setOpen(false);
  });
}
