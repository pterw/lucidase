import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { validateKb } from "../src/core/kb.js";
import { classify } from "../src/core/classify.js";
import { assembleFindings, e4CountForDiplotype, resolveApoe } from "../src/core/apoe.js";

// The mini knowledge base is the one the shared classify vectors use (it has the rs429358 component only).
const classifyVectors = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../tests/vectors/classify.json", import.meta.url)), "utf8")
);
const apoeVectors = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../tests/vectors/apoe.json", import.meta.url)), "utf8")
);

/** classify's mini KB plus an rs7412 component and the APOE diplotype texts, built in memory. */
function kbWithApoe(mutate = (raw) => raw) {
  const raw = structuredClone(classifyVectors[0].input.kb);
  const e7412 = structuredClone(raw.loci.rs429358);
  Object.assign(e7412, { rsid: "rs7412", pos_grch37: 45412079, pos_grch38: 44908822, ref: "C", alt: "T" });
  raw.loci.rs7412 = e7412;
  raw.genes.APOE.diplotypes = structuredClone(apoeVectors[0].input.kb.genes.APOE.diplotypes);
  return validateKb(mutate(raw));
}

const parse = (calls) => ({
  format: "23andme",
  build: "GRCh37",
  assay: "array",
  calls,
  stats: { total_lines: calls.length, data_rows: calls.length, called: calls.length, no_calls: 0, skipped_malformed: 0 },
});
const call = (rsid, pos, alleles) => ({ rsid, chrom: "19", pos, alleles });

test("the coverage summary counts APOE once, with the components excluded", () => {
  const kb = kbWithApoe();
  const parsed = parse([
    call("rs429358", 45411941, ["T", "C"]),
    call("rs7412", 45412079, ["C", "C"]),
    call("rs1801133", 11856378, ["G", "G"]),
  ]);
  const { records, summary: before } = classify(parsed, kb);
  // classify alone counts the two component loci separately.
  assert.equal(before.total_loci, records.length);

  const { listed, apoe, summary } = assembleFindings(records, kb, before.outside_coverage_count);
  assert.equal(apoe.diplotype, "e3/e4");
  assert.equal(listed.filter((r) => r.gene === "APOE").length, 1, "one APOE row among the findings");
  assert.equal(listed.some((r) => r.role === "apoe_component"), false);
  assert.equal(summary.total_loci, listed.length);
  assert.equal(summary.total_loci, before.total_loci - 1, "two component loci become one APOE finding");
  const counted =
    summary.supported_and_observed_count +
    summary.supported_not_observed_count +
    summary.not_tested_by_array_count +
    summary.insufficient_evidence_count;
  assert.equal(counted, listed.length, "cards and table agree");
  // rs429358 (observed) and rs7412 (not observed) merge into one observed APOE finding.
  assert.equal(summary.supported_and_observed_count, before.supported_and_observed_count);
  assert.equal(summary.supported_not_observed_count, before.supported_not_observed_count - 1);
});

test("the APOE finding keeps its components and an indeterminate APOE is still one row", () => {
  const kb = kbWithApoe();
  const { records } = classify(parse([call("rs429358", 45411941, ["C", "C"])]), kb);
  const { listed, apoe, summary } = assembleFindings(records, kb);
  assert.equal(apoe.diplotype, null);
  assert.equal(apoe.coverage_state, "not_tested_by_array");
  assert.deepEqual(apoe.components.map((c) => c.rsid).sort(), ["rs429358", "rs7412"]);
  assert.equal(listed.filter((r) => r.gene === "APOE").length, 1);
  assert.equal(summary.not_tested_by_array_count, 4);
});

test("a half-built KB or missing component fails closed", () => {
  const kb = kbWithApoe();
  const { records } = classify(parse([]), kb);
  const comps = records.filter((r) => r.role === "apoe_component");
  assert.throws(() => resolveApoe([comps[0]], kb), /both component records/);
  const noTexts = kbWithApoe((raw) => {
    delete raw.genes.APOE.diplotypes;
    return raw;
  });
  assert.throws(() => resolveApoe(comps, noTexts), /diplotypes/);
});

test("resolveApoe does not mutate the knowledge base interpretation", () => {
  const kb = kbWithApoe();
  const { records } = classify(
    parse([call("rs429358", 45411941, ["T", "C"]), call("rs7412", 45412079, ["C", "T"])]),
    kb
  );
  const comps = records.filter((r) => r.role === "apoe_component");
  const before = JSON.stringify(kb.genes.APOE.diplotypes["e2/e4"]);
  const rec = resolveApoe(comps, kb);
  assert.equal(rec.diplotype, "e2/e4");
  assert.ok(rec.interpretation.caveats.some((c) => c.startsWith("phase unknown")));
  assert.equal(JSON.stringify(kb.genes.APOE.diplotypes["e2/e4"]), before);
});

test("the e4 count comes from a resolved diplotype, never from the rs429358 alt count", () => {
  const kb = kbWithApoe();
  const e4Count = (e4Alt, e2Alt) => {
    const parsed = parse([
      call("rs429358", 45411941, e4Alt === 2 ? ["C", "C"] : e4Alt === 1 ? ["T", "C"] : ["T", "T"]),
      call("rs7412", 45412079, e2Alt === 2 ? ["T", "T"] : e2Alt === 1 ? ["C", "T"] : ["C", "C"]),
    ]);
    const { apoe } = assembleFindings(classify(parsed, kb).records, kb);
    return e4CountForDiplotype(apoe.diplotype);
  };
  assert.equal(e4Count(2, 1), null, "e1/e4 (rs429358 alt count 2) is atypical: no e4 count");
  assert.equal(e4Count(1, 2), null);
  assert.equal(e4Count(1, 1), 1, "e2/e4");
  assert.equal(e4Count(1, 0), 1, "e3/e4");
  assert.equal(e4Count(2, 0), 2, "e4/e4");
  assert.equal(e4Count(0, 0), 0, "e3/e3");
  assert.equal(e4CountForDiplotype(null), null, "an unresolved diplotype has no e4 count");
  assert.equal(e4CountForDiplotype("atypical"), null);
  assert.equal(e4CountForDiplotype("e1/e4"), null);
});
