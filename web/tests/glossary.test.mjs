// The inline glossary (design system Term, ledger DS2-10): one table of plain definitions, and the pure split of a
// sentence Lucidase writes into text and glossary words. The DOM side (src/term.js) is covered by tests/e2e/test_glossary.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { GLOSSARY, termParts } from "../src/glossary.js";
import { summaryProse, summaryProseParts } from "../src/view-model.js";

// Verbatim from the controller's glossary table (owner ruling 2026-10-04): variant and carrier are the design
// system's own words; the other five are drafts pending owner review.
const EXPECTED = {
  variant: "A change in the DNA letters at one position, compared with the most common version.",
  carrier: "You have one copy. Carriers usually have no symptoms but can pass it on.",
  genotype: "The DNA letters your file has at one position, usually two: one from each parent.",
  allele: "One version of the DNA at a position. Most positions have two, one from each parent.",
  chip: "The DNA test your company used. It reads a fixed list of positions, not whole genes.",
  marker: "One position in the DNA that the chip reads, named by an ID such as rs429358.",
  "risk factor": "Something linked to a higher chance of a condition. It is not a diagnosis.",
};

test("the glossary holds exactly the seven words, with the agreed definitions, and cannot be changed", () => {
  assert.deepEqual({ ...GLOSSARY }, EXPECTED);
  assert.deepEqual(Object.keys(GLOSSARY).sort(), Object.keys(EXPECTED).sort());
  assert.ok(Object.isFrozen(GLOSSARY));
  assert.throws(() => { GLOSSARY.variant = "x"; }, TypeError);
  assert.throws(() => { GLOSSARY.gene = "x"; }, TypeError);
});

test("termParts wraps only the first occurrence of each word, keeps the text's own spelling, and loses no text", () => {
  const text = "Variants linked to a higher chance of a condition. A risk factor is not a diagnosis, nor are variants.";
  const parts = termParts(text, ["variant", "risk factor"]);
  assert.equal(parts.map((p) => p.text).join(""), text);
  assert.deepEqual(parts.filter((p) => p.term), [
    { text: "Variants", term: "variant" },
    { text: "risk factor", term: "risk factor" },
  ]);
  // A word inside a longer word is not the glossary word.
  assert.deepEqual(termParts("Invariant chips", ["chip"]).filter((p) => p.term), [{ text: "chips", term: "chip" }]);
  assert.throws(() => termParts("Invariants only", ["variant"]), /variant/);
  // Unknown words and words the text does not contain are bugs in the page copy, never silently skipped.
  assert.throws(() => termParts("A gene", ["gene"]), /gene/);
  assert.throws(() => termParts("No such word here", ["allele"]), /allele/);
  // No words: the text comes back whole.
  assert.deepEqual(termParts("Plain text", []), [{ text: "Plain text" }]);
});

test("the Summary sentence exposes 'variant' as its one glossary word, and reads the same as summaryProse", () => {
  const counts = {
    supported_and_observed: 10,
    supported_not_observed: 1,
    not_tested_by_array: 2,
    insufficient_evidence: 2,
    outside_coverage: 612,
  };
  const parts = summaryProseParts(counts);
  assert.equal(parts.map((p) => p.text).join(""), summaryProse(counts));
  assert.deepEqual(parts.filter((p) => p.term), [{ text: "variant", term: "variant" }]);
  assert.match(parts[0].text, /^Lucidase ran 15 checks on your file\. A $/);
  assert.throws(() => summaryProseParts(null), /count/);
});
