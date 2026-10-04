/**
 * The inline glossary (design system components/core/Term): the one place the page's plain definitions live, and the
 * pure split of a sentence Lucidase writes into text and glossary words. Pure: no DOM. src/term.js renders the parts.
 *
 * Use a Term only in copy Lucidase writes, on the first occurrence of a word in a section; never in knowledge-base
 * text (statements, limitations, phenotypes, drug text), headings, buttons or table cells.
 */

export const GLOSSARY = Object.freeze({
  // Design system, verbatim (ui_kits/web/AnalysisScreen.jsx, the Summary sentence).
  variant: "A change in the DNA letters at one position, compared with the most common version.",
  // Design system, verbatim (components/core/Term.prompt.md).
  carrier: "You have one copy. Carriers usually have no symptoms but can pass it on.",
  // Drafts (owner ruling 2026-10-04: shipped, pending owner review).
  genotype: "The DNA letters your file has at one position, usually two: one from each parent.",
  allele: "One version of the DNA at a position. Most positions have two, one from each parent.",
  chip: "The DNA test your company used. It reads a fixed list of positions, not whole genes.",
  marker: "One position in the DNA that the chip reads, named by an ID such as rs429358.",
  "risk factor": "Something linked to a higher chance of a condition. It is not a diagnosis.",
});

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Splits `text` into parts, `{ text }` or `{ text, term }`, wrapping the first occurrence of each glossary word in
 * `terms` (whole word, any case, singular or plural). The parts' texts joined are `text`. A word that is not in the
 * glossary, or that the text does not contain, throws (fail fast): a placement never disappears silently.
 */
export function termParts(text, terms) {
  const hits = terms.map((term) => {
    if (!Object.hasOwn(GLOSSARY, term)) throw new Error(`"${term}" is not a glossary word`);
    const match = new RegExp(`\\b${escapeRegExp(term)}s?\\b`, "i").exec(text);
    if (match === null) throw new Error(`the glossary word "${term}" is not in "${text}"`);
    return { term, start: match.index, end: match.index + match[0].length };
  }).sort((a, b) => a.start - b.start);
  const parts = [];
  let at = 0;
  for (const hit of hits) {
    if (hit.start < at) throw new Error(`the glossary word "${hit.term}" overlaps another in "${text}"`);
    if (hit.start > at) parts.push({ text: text.slice(at, hit.start) });
    parts.push({ text: text.slice(hit.start, hit.end), term: hit.term });
    at = hit.end;
  }
  if (at < text.length || parts.length === 0) parts.push({ text: text.slice(at) });
  return parts;
}
