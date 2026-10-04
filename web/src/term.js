/**
 * Term (design system components/core/Term): an inline glossary word, dotted beneath, whose plain definition
 * (glossary.js GLOSSARY) opens on hover, on focus and on tap or click.
 *
 * Markup (styles.css reads only the button's aria-expanded; the popover must follow the button directly):
 *   <span class="lds-termwrap">
 *     <button type="button" class="lds-term" aria-expanded="false" aria-describedby="term-…">carrier</button>
 *     <span id="term-…" role="tooltip" class="lds-term-pop">…definition…</span>
 *   </span>
 *
 * Behaviour (design system contract): open on mouse enter and on focus, close on mouse leave and when focus leaves,
 * toggle on click; Escape closes it and keeps focus on the word; a press outside closes it; one is open at a time.
 * Enter and leave are heard on the wrapper, so the pointer can move onto the definition. A touch never counts as enter
 * or leave, and a click toggles from the state before the press, so the tap that focuses the word does not also shut
 * it.
 *
 * Static copy in the HTML marks a word as `<button type="button" class="lds-term" data-term="<word>">…</button>`;
 * `upgradeTerms` adds the wrapper and the definition, so the definitions are written in one place only. Every text
 * node is set with textContent: nothing here parses HTML.
 */
import { GLOSSARY, termParts } from "./glossary.js";

let openTerm = null;
let serial = 0;
let listening = false;
// The open state each word had when the current press began (see the click handler).
const stateAtPress = new WeakMap();

const isOpen = (button) => button.getAttribute("aria-expanded") === "true";

function setOpen(button, open) {
  if (open && openTerm !== null && openTerm !== button) setOpen(openTerm, false);
  button.setAttribute("aria-expanded", String(open));
  const pop = button.nextElementSibling;
  pop.style.removeProperty("left");
  if (open) {
    openTerm = button;
    keepInViewport(pop);
  } else if (openTerm === button) {
    openTerm = null;
  }
}

/**
 * At 560px and wider the definition hangs from the word (280px wide). A word near the right edge would push it
 * past the viewport, so it moves left until it fits inside the 16px gutter. Below 560px the CSS pins it to the foot of
 * the viewport and this does nothing.
 */
function keepInViewport(pop) {
  if (getComputedStyle(pop).position === "fixed") return;
  const gutter = 16;
  const box = pop.getBoundingClientRect();
  const limit = document.documentElement.clientWidth - gutter;
  if (box.right > limit) pop.style.left = `${Math.min(0, limit - box.right)}px`;
}

function listenOnce() {
  if (listening) return;
  listening = true;
  document.addEventListener("pointerdown", (e) => {
    if (openTerm !== null && !openTerm.parentElement.contains(e.target)) setOpen(openTerm, false);
  });
  // Escape closes the open definition, whether hover or focus opened it; focus stays where it is (on the word when
  // it has it). Heard in the capture phase and stopped there, so the same key does not also close the Inspector.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || openTerm === null) return;
    e.stopPropagation();
    setOpen(openTerm, false);
  }, true);
}

/** Wraps an existing `button.lds-term[data-term]` with its definition and its behaviour. */
function attach(button, term) {
  if (!Object.hasOwn(GLOSSARY, term)) throw new Error(`"${term}" is not a glossary word`);
  listenOnce();
  const wrap = document.createElement("span");
  wrap.className = "lds-termwrap";
  const pop = document.createElement("span");
  pop.id = `term-${term.replace(/\s+/g, "-")}-${++serial}`;
  pop.setAttribute("role", "tooltip");
  pop.className = "lds-term-pop";
  pop.textContent = GLOSSARY[term];
  button.replaceWith(wrap);
  wrap.append(button, pop);
  button.type = "button";
  button.classList.add("lds-term");
  button.dataset.term = term;
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-describedby", pop.id);

  wrap.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") setOpen(button, true); });
  wrap.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") setOpen(button, false); });
  button.addEventListener("focusin", () => setOpen(button, true));
  button.addEventListener("focusout", () => setOpen(button, false));
  button.addEventListener("pointerdown", () => stateAtPress.set(button, isOpen(button)));
  button.addEventListener("click", () => {
    const before = stateAtPress.has(button) ? stateAtPress.get(button) : isOpen(button);
    stateAtPress.delete(button);
    setOpen(button, !before);
  });
  return wrap;
}

/** A new Term for glossary word `term`, showing `text` (the page's own spelling, such as "Variants"). */
export function createTerm(term, text) {
  const button = document.createElement("button");
  button.textContent = text;
  // attach() moves the button into its wrapper, so it needs a parent first.
  const holder = document.createElement("span");
  holder.append(button);
  return attach(button, term);
}

/** Replaces `el`'s content with `parts` (glossary.js termParts): plain text, and a Term for each glossary word. */
export function renderTermParts(el, parts) {
  el.replaceChildren(...parts.map((part) => (part.term ? createTerm(part.term, part.text) : document.createTextNode(part.text))));
}

/** Replaces `el`'s content with `text`, with a Term on the first occurrence of each word in `terms`. */
export function renderTextWithTerms(el, text, terms) {
  renderTermParts(el, termParts(text, terms));
}

/** Upgrades every glossary word marked in the static HTML under `root`. */
export function upgradeTerms(root = document) {
  for (const button of root.querySelectorAll("button.lds-term[data-term]")) {
    if (!button.parentElement.classList.contains("lds-termwrap")) attach(button, button.dataset.term);
  }
}
