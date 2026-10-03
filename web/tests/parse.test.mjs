import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { parseGenotypeFile, UnsupportedFormatError } from "../src/core/parse.js";

const TAB = "\t";

test("every core module is pure: no worker/DOM/network tokens, only relative imports", () => {
  const dir = fileURLToPath(new URL("../src/core/", import.meta.url));
  const files = readdirSync(dir).filter((f) => f.endsWith(".js"));
  assert.ok(files.length >= 2);
  for (const f of files) {
    // Strip comments so documentation may mention the forbidden names.
    const src = readFileSync(join(dir, f), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1");
    for (const tok of ["self", "window", "document", "fetch", "importScripts", "XMLHttpRequest"]) {
      assert.doesNotMatch(src, new RegExp(`\\b${tok}\\b`), `${f} uses ${tok}`);
    }
    for (const m of src.matchAll(/\bimport\s*(?:[^'"]*?from\s*)?["']([^"']+)["']/g)) {
      assert.match(m[1], /^\.\//, `${f} imports non-relative module ${m[1]}`);
    }
    assert.doesNotMatch(src, /\bimport\s*\(/, `${f} uses dynamic import`);
  }
});

test("a sites-only VCF is rejected with a clear message", () => {
  const vcf = `##fileformat=VCFv4.2\n#CHROM${TAB}POS${TAB}ID${TAB}REF${TAB}ALT${TAB}Q${TAB}F${TAB}I\n1${TAB}5${TAB}rs9${TAB}A${TAB}G${TAB}.${TAB}.${TAB}.\n`;
  assert.throws(
    () => parseGenotypeFile(vcf, "a.vcf"),
    (e) => e instanceof UnsupportedFormatError && /VCF contains no sample genotypes/.test(e.message)
  );
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
