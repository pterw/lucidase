import { test } from "node:test";
import assert from "node:assert/strict";
import { computeQc, MIN_X_MARKERS, X_HET_CUTOFF, SEX_SIGNAL } from "../src/core/qc.js";

const call = (chrom, alleles) => ({ rsid: "rs1", chrom, pos: 1, alleles });
const xCalls = (n, nHet) =>
  Array.from({ length: n }, (_, i) => call("X", i < nHet ? ["A", "G"] : ["A", "A"]));
const qc = (calls) => computeQc({ calls });

test("call rate and heterozygosity rate use called diploid calls", () => {
  const r = qc([call("1", ["A", "G"]), call("1", ["A", "A"]), call("1", null), call("X", ["G"])]);
  assert.equal(r.call_rate, 0.75);
  assert.equal(r.heterozygosity_rate, 0.5); // 1 het of 2 diploid calls; haploid excluded
});

test("an empty call list yields zero rates and an indeterminate signal", () => {
  const r = qc([]);
  assert.equal(r.call_rate, 0);
  assert.equal(r.heterozygosity_rate, 0);
  assert.equal(r.sex_signal, SEX_SIGNAL.INDETERMINATE);
});

test("fewer than the minimum X markers is indeterminate", () => {
  const r = qc(xCalls(MIN_X_MARKERS - 1, MIN_X_MARKERS - 1));
  assert.equal(r.x_markers, MIN_X_MARKERS - 1);
  assert.equal(r.sex_signal, SEX_SIGNAL.INDETERMINATE);
});

test("X heterozygosity above the cut-off reads as two X chromosomes", () => {
  const r = qc(xCalls(100, 25));
  assert.equal(r.x_het_rate, 0.25);
  assert.equal(r.sex_signal, SEX_SIGNAL.TWO_X);
});

test("single-letter and homozygous X calls read as one X chromosome", () => {
  const calls = Array.from({ length: MIN_X_MARKERS }, () => call("X", ["G"]));
  assert.equal(qc(calls).sex_signal, SEX_SIGNAL.ONE_X);
});

test("the X het cut-off is exclusive: exactly at the cut-off is one X", () => {
  const n = 100;
  const atCutoff = qc(xCalls(n, n * X_HET_CUTOFF));
  const above = qc(xCalls(n, n * X_HET_CUTOFF + 1));
  assert.equal(atCutoff.sex_signal, SEX_SIGNAL.ONE_X);
  assert.equal(above.sex_signal, SEX_SIGNAL.TWO_X);
});

test("Y calls are counted but never change the signal or name a karyotype", () => {
  const calls = [...xCalls(100, 25), ...Array.from({ length: 8 }, () => call("Y", ["A"]))];
  const r = qc(calls);
  assert.equal(r.y_calls, 8);
  assert.equal(r.sex_signal, SEX_SIGNAL.TWO_X);
  for (const s of Object.values(SEX_SIGNAL)) {
    assert.doesNotMatch(s, /47|45|XXY|Turner|Klinefelter|mosaic|atypical/i);
  }
});

test("X no-calls and the PAR (XY) are not X markers", () => {
  const r = qc([call("X", null), call("XY", ["A", "G"])]);
  assert.equal(r.x_markers, 0);
});

test("variants-only VCF: call rate and het rate are null with an explanatory note", () => {
  const r = computeQc({ assay: "vcf", calls: [call("1", ["A", "G"]), call("1", ["A", "A"]), call("1", null)] });
  assert.equal(r.call_rate, null);
  assert.equal(r.heterozygosity_rate, null);
  assert.equal(r.qc_note, "not meaningful for variants-only VCF");
});

test("array QC keeps numeric rates and has no note", () => {
  const r = computeQc({ assay: "array", calls: [call("1", ["A", "G"]), call("1", null)] });
  assert.equal(r.call_rate, 0.5);
  assert.equal(r.qc_note, null);
});

test("VCF still reports the X signal fields", () => {
  const r = computeQc({ assay: "vcf", calls: xCalls(100, 25) });
  assert.equal(r.sex_signal, SEX_SIGNAL.TWO_X);
});
