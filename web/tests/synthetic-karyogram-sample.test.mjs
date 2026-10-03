import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseGenotypeFile } from "../src/core/parse.js";
import { validateKb } from "../src/core/kb.js";
import { classify } from "../src/core/classify.js";
import { computeQc, SEX_SIGNAL } from "../src/core/qc.js";

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const kb = validateKb(JSON.parse(read("../src/knowledge-base.json")));
const original = parseGenotypeFile(read("../demo-data/sample-23andme.txt"), "sample-23andme.txt");
const synthetic = parseGenotypeFile(
  read("../demo-data/sample-karyogram-23andme.txt"),
  "sample-karyogram-23andme.txt"
);

test("the synthetic sample parses as a 23andMe GRCh37 array with every row called", () => {
  assert.equal(synthetic.format, "23andme");
  assert.equal(synthetic.build, "GRCh37");
  assert.equal(synthetic.assay, "array");
  assert.equal(synthetic.stats.skipped_malformed, 0);
  assert.equal(synthetic.calls.length, original.calls.length + 15_000);
  assert.equal(synthetic.stats.called, original.stats.called + 15_000);
});

test("every KB locus has the same coverage state and alt count as in the original demo", () => {
  const pick = (r) => r.records.map((x) => [x.rsid, x.coverage_state, x.altCount]);
  const a = pick(classify(original, kb));
  const b = pick(classify(synthetic, kb));
  assert.ok(a.length > 0);
  assert.deepEqual(b, a);
});

test("the sex signal is unchanged: two X chromosomes", () => {
  const a = computeQc(original);
  const b = computeQc(synthetic);
  assert.equal(a.sex_signal, SEX_SIGNAL.TWO_X);
  assert.equal(b.sex_signal, a.sex_signal);
  assert.equal(b.y_calls, a.y_calls);
});
