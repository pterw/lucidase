import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { validateKb } from "../src/core/kb.js";
import { withAssemblies } from "./support/with-assemblies.mjs";
import { classify } from "../src/core/classify.js";
import { COVERAGE_STATES, deriveCoverageState, summarizeCoverage } from "../src/core/coverage.js";

// The mini knowledge base is the one the shared classify vectors use.
const vectors = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../tests/vectors/classify.json", import.meta.url)), "utf8")
);
const KB_JSON = vectors[0].input.kb;
const kb = () => validateKb(withAssemblies(structuredClone(KB_JSON)));

const parse = (calls, extra = {}) => ({
  format: "23andme",
  build: "GRCh37",
  assay: "array",
  calls,
  stats: { total_lines: calls.length, data_rows: calls.length, called: calls.length, no_calls: 0, skipped_malformed: 0 },
  ...extra,
});
const call = (rsid, chrom, pos, alleles) => ({ rsid, chrom, pos, alleles });

test("classify returns one record per KB locus, in KB order, whatever the file holds", () => {
  const out = classify(parse([]), kb());
  assert.deepEqual(out.records.map((r) => r.rsid), Object.keys(KB_JSON.loci));
  assert.ok(out.records.every((r) => r.coverage_state === COVERAGE_STATES.NOT_TESTED_BY_ARRAY));
});

test("every record carries the C2 fields the UI needs", () => {
  const out = classify(parse([call("rs4244285", "10", 96541616, ["G", "A"])]), kb());
  const rec = out.records.find((r) => r.rsid === "rs4244285");
  for (const key of [
    "rsid", "gene", "chrom", "pos", "genotype_display", "altCount", "strandFlipped", "coverage_state",
    "sample_observation", "reason", "interpretation", "evidence", "evidence_tier", "limitation", "acmg_sf", "role",
  ]) {
    assert.ok(key in rec, `record is missing ${key}`);
  }
  assert.equal(rec.gene, "CYP2C19");
  assert.equal(rec.chrom, "10");
});

test("each record is counted in exactly one coverage state", () => {
  const out = classify(
    parse([call("rs4244285", "10", 96541616, ["G", "A"]), call("rs1801133", "1", 11856378, ["G", "G"])]),
    kb()
  );
  const s = out.summary;
  const total =
    s.supported_and_observed_count +
    s.supported_not_observed_count +
    s.not_tested_by_array_count +
    s.insufficient_evidence_count;
  assert.equal(total, out.records.length);
  assert.equal(s.total_loci, out.records.length);
});

test("classify does not mutate the parse result", () => {
  const input = parse([call("rs4244285", "10", 96541616, ["G", "A"])]);
  const before = JSON.stringify(input);
  classify(input, kb());
  assert.equal(JSON.stringify(input), before);
});

test("an unknown build never matches by position", () => {
  const out = classify(parse([call(null, "10", 96541616, ["G", "A"])], { build: "unknown", assay: "vcf" }), kb());
  assert.equal(out.records.find((r) => r.rsid === "rs4244285").coverage_state, COVERAGE_STATES.NOT_TESTED_BY_ARRAY);
});

test("an rsID that is a KB key is never re-matched by position", () => {
  // rs1801133's rsID at rs4244285's chrom:pos: only rs1801133 may claim the call.
  const out = classify(parse([call("rs1801133", "10", 96541616, ["G", "G"])]), kb());
  const at = (rsid) => out.records.find((r) => r.rsid === rsid);
  assert.equal(at("rs1801133").genotype_display, "G/G");
  assert.equal(at("rs4244285").genotype_display, null);
  assert.equal(at("rs4244285").coverage_state, COVERAGE_STATES.NOT_TESTED_BY_ARRAY);
  assert.equal(out.summary.outside_coverage_count, 0);
});

test("an rsID the KB lacks falls back to the chrom:pos match", () => {
  const out = classify(parse([call("rs999999999", "10", 96541616, ["G", "A"])]), kb());
  const rec = out.records.find((r) => r.rsid === "rs4244285");
  assert.equal(rec.genotype_display, "G/A");
  assert.equal(rec.altCount, 1);
  assert.equal(out.summary.outside_coverage_count, 0);
});

test("a VCF call is never strand-complemented, an array call is", () => {
  const foreign = (assay) => classify(parse([call("rs4244285", "10", 96541616, ["C", "C"])], { assay }), kb());
  const vcf = foreign("vcf").records.find((r) => r.rsid === "rs4244285");
  assert.equal(vcf.altCount, null);
  assert.equal(vcf.coverage_state, COVERAGE_STATES.INSUFFICIENT_EVIDENCE);
  const array = foreign("array").records.find((r) => r.rsid === "rs4244285");
  assert.equal(array.altCount, 0);
  assert.equal(array.strandFlipped, true);
});

test("deriveCoverageState follows the C4 order", () => {
  const resolved = (n) => ({ ok: true, altCount: n, strandFlipped: false });
  const c = { alleles: ["A", "A"] };
  assert.equal(deriveCoverageState({ assay: "array", call: undefined }).coverage_state, "not_tested_by_array");
  assert.equal(deriveCoverageState({ assay: "array", call: { alleles: null } }).coverage_state, "not_tested_by_array");
  assert.equal(
    deriveCoverageState({ assay: "array", call: c, resolution: { ok: false, reason: "unresolvable" }, evidenceSufficiency: "sufficient" }).reason,
    "genotype not interpretable"
  );
  assert.equal(
    deriveCoverageState({ assay: "array", call: c, resolution: resolved(0), evidenceSufficiency: "insufficient" }).coverage_state,
    "insufficient_evidence"
  );
  assert.equal(
    deriveCoverageState({ assay: "array", call: c, resolution: resolved(2), evidenceSufficiency: "sufficient" }).sample_observation,
    "variant_present"
  );
});

test("summarizeCoverage rejects a record in an unknown state instead of dropping it", () => {
  assert.throws(() => summarizeCoverage([{ coverage_state: "bogus" }], 0), /bogus/);
});

test("coincident bystander probe does not conflict with compatible probe at same coordinate", () => {
  const rawKb = structuredClone(KB_JSON);
  rawKb.loci.rs113993960 = {
    rsid: "rs113993960",
    gene: "HFE",
    chrom: "7",
    pos_grch37: 117199644,
    pos_grch38: 117559590,
    ref: "ATCT",
    alt: "A",
    allele_codes: { D: "alt", I: "ref" },
    interpretations: {
      0: { category: "Not detected", significance: "Not detected", magnitude: 0, repute: "Neutral", phenotype: "None", drug_response: null, caveats: [] },
      1: { category: "Carrier", significance: "Carrier", magnitude: 1, repute: "Bad", phenotype: "Carrier", drug_response: null, caveats: [] },
      2: { category: "Pathogenic", significance: "Pathogenic", magnitude: 4, repute: "Bad", phenotype: "Affected", drug_response: null, caveats: [] }
    },
    evidence: { clinvar: { stars: 4, review_status: "practice guideline" } },
    evidence_tier: "Tier A",
    tier_source: "clinvar_review",
    tier_rationale: null,
    tier_citation: null,
    evidence_sufficiency: "sufficient",
    limitation: null,
    role: "standard",
  };
  const k = validateKb(withAssemblies(rawKb));

  const out = classify(
    parse([
      call("rs1801178", "7", 117199644, ["A", "A"]),
      call("i4000292", "7", 117199644, ["I", "I"]),
    ]),
    k
  );
  const rec = out.records.find((r) => r.rsid === "rs113993960");
  assert.equal(rec.coverage_state, COVERAGE_STATES.SUPPORTED_NOT_OBSERVED);
  assert.equal(rec.altCount, 0);
  assert.equal(rec.genotype_display, "I/I");
});

