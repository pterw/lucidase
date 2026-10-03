import { test } from "node:test";
import assert from "node:assert/strict";
import { isPalindromic, resolveAltCount } from "../src/core/alleles.js";

const snp = (ref, alt, chrom = "1") => ({ ref, alt, allele_codes: null, chrom });

test("palindromic is derived from single-base complementary ref/alt", () => {
  assert.equal(isPalindromic("C", "G"), true);
  assert.equal(isPalindromic("G", "C"), true);
  assert.equal(isPalindromic("A", "T"), true);
  assert.equal(isPalindromic("T", "A"), true);
  assert.equal(isPalindromic("C", "T"), false);
  assert.equal(isPalindromic("G", "A"), false);
  // an indel is never palindromic, and never complemented
  assert.equal(isPalindromic("ATCT", "A"), false);
});

test("a palindromic site gives CC=0 CG=1 GG=2 and never reports a strand flip (P0-006)", () => {
  const locus = snp("C", "G");
  assert.deepEqual(resolveAltCount(locus, ["C", "C"]), { ok: true, altCount: 0, strandFlipped: false });
  assert.deepEqual(resolveAltCount(locus, ["G", "C"]), { ok: true, altCount: 1, strandFlipped: false });
  assert.deepEqual(resolveAltCount(locus, ["G", "G"]), { ok: true, altCount: 2, strandFlipped: false });
});

test("a non-palindromic site is complemented as a whole, once", () => {
  const locus = snp("C", "T");
  assert.deepEqual(resolveAltCount(locus, ["A", "G"], "array"), { ok: true, altCount: 1, strandFlipped: true });
  // half forward, half complemented is never a valid call
  assert.deepEqual(resolveAltCount(locus, ["C", "A"]), { ok: false, reason: "unresolvable" });
});

test("a VCF call is never strand-complemented: a foreign alt is unresolvable (P0-009)", () => {
  const locus = snp("G", "A", "10");
  assert.deepEqual(resolveAltCount(locus, ["C", "C"], "vcf"), { ok: false, reason: "unresolvable" });
  assert.deepEqual(resolveAltCount(locus, ["T", "T"], "vcf"), { ok: false, reason: "unresolvable" });
  assert.deepEqual(resolveAltCount(locus, ["G", "A"], "vcf"), { ok: true, altCount: 1, strandFlipped: false });
  assert.deepEqual(resolveAltCount(locus, ["C", "C"], "array"), { ok: true, altCount: 0, strandFlipped: true });
});

test("a result never uses the reason palindromic_ambiguous for an unmatched palindromic call", () => {
  assert.deepEqual(resolveAltCount(snp("A", "T"), ["C", "G"]), { ok: false, reason: "unresolvable" });
});

test("null and empty allele lists are a no-call", () => {
  assert.deepEqual(resolveAltCount(snp("G", "A"), null), { ok: false, reason: "no_call" });
  assert.deepEqual(resolveAltCount(snp("G", "A"), []), { ok: false, reason: "no_call" });
});

test("haploid counts as two copies only on X, Y and MT", () => {
  for (const chrom of ["X", "Y", "MT"]) {
    assert.deepEqual(resolveAltCount(snp("G", "A", chrom), ["A"]), { ok: true, altCount: 2, strandFlipped: false });
  }
  assert.deepEqual(resolveAltCount(snp("G", "A", "7"), ["A"]), { ok: false, reason: "unresolvable" });
});

test("array D/I codes map through allele_codes and stay on the VCF-normalised form (L8)", () => {
  const cftr = { ref: "ATCT", alt: "A", allele_codes: { D: "alt", I: "ref" }, chrom: "7" };
  assert.equal(resolveAltCount(cftr, ["D", "I"]).altCount, 1);
  assert.equal(resolveAltCount(cftr, ["ATCT", "A"]).altCount, 1);
  assert.equal(resolveAltCount(cftr, ["ATCT", "AT"]).ok, false);
});

test("the locus and the allele list are not mutated", () => {
  const locus = Object.freeze({ ref: "C", alt: "T", allele_codes: null, chrom: "1" });
  const alleles = Object.freeze(["A", "G"]);
  assert.equal(resolveAltCount(locus, alleles).altCount, 1);
});
