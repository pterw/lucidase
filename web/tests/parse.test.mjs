import { test } from "node:test";
import assert from "node:assert/strict";
import { parseGenotypeFile, UnsupportedFormatError } from "../src/core/parse.js";

const TAB = "\t";

test("parser is pure: it imports without any worker or DOM global", () => {
  assert.equal(typeof globalThis.self, "undefined");
  assert.equal(typeof globalThis.document, "undefined");
});

test("non-string input throws TypeError, not a format guess", () => {
  assert.throws(() => parseGenotypeFile(null, "x.txt"), TypeError);
});

test("UnsupportedFormatError is an Error with a stable name and readable message", () => {
  assert.throws(
    () => parseGenotypeFile("not a genotype file", "x.txt"),
    (e) => e instanceof UnsupportedFormatError && e.name === "UnsupportedFormatError" && /unsupported/i.test(e.message)
  );
});

test("content beats the file extension: a VCF named .txt is a VCF", () => {
  const vcf = `##fileformat=VCFv4.2\n#CHROM${TAB}POS${TAB}ID${TAB}REF${TAB}ALT${TAB}Q${TAB}F${TAB}I${TAB}FORMAT${TAB}S\n1${TAB}5${TAB}rs9${TAB}A${TAB}G${TAB}.${TAB}.${TAB}.${TAB}GT${TAB}0/1\n`;
  assert.equal(parseGenotypeFile(vcf, "genome_23andme.txt").format, "vcf");
});

test("a comma in a VCF line never routes it to the CSV parser", () => {
  const vcf = `##fileformat=VCFv4.2\n#CHROM${TAB}POS${TAB}ID${TAB}REF${TAB}ALT${TAB}Q${TAB}F${TAB}I${TAB}FORMAT${TAB}S\n1${TAB}5${TAB}rs9${TAB}A${TAB}G,T${TAB}.${TAB}.${TAB}AF=0.1,0.2${TAB}GT:AD${TAB}1/2:3,4,5\n`;
  const r = parseGenotypeFile(vcf, "a.vcf");
  assert.deepEqual(r.calls, [{ rsid: "rs9", chrom: "1", pos: 5, alleles: ["G", "T"] }]);
});

test("a malformed array row is skipped and counted, not turned into a call", () => {
  const txt = `# 23andMe\nrs1${TAB}1${TAB}100${TAB}AG\nrs2${TAB}1${TAB}notapos${TAB}AG\nrs3${TAB}1${TAB}300${TAB}XZ\n`;
  const r = parseGenotypeFile(txt, "a.txt");
  assert.equal(r.calls.length, 1);
  assert.equal(r.stats.skipped_malformed, 2);
});

test("a UTF-8 byte-order mark does not hide the header", () => {
  const txt = `\uFEFFrsid${TAB}chromosome${TAB}position${TAB}allele1${TAB}allele2\nrs1${TAB}1${TAB}5${TAB}A${TAB}G\n`;
  const r = parseGenotypeFile(txt, "a.txt");
  assert.equal(r.format, "ancestry");
  assert.equal(r.calls.length, 1);
});
