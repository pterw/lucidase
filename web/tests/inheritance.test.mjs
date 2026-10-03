import { test } from "node:test";
import assert from "node:assert/strict";
import {
  PARTNER_MODELS,
  offspringDistribution,
  geneOutcome,
  patientStatus,
  describeSegregation,
  detectMultiLocus,
  detectCompoundHeterozygosity,
} from "../src/core/inheritance.js";

const gene = (model, mendelian_disease, penetrance = null) => ({
  inheritance: { model, mendelian_disease, penetrance, disease: "d", omim: null },
});
const AR = gene("autosomal_recessive", true, 1);
const RF = gene("risk_factor", false);

test("the distribution sums to 1 for every patient count and partner model", () => {
  for (const alt of [0, 1, 2]) {
    for (const partner of PARTNER_MODELS) {
      const d = offspringDistribution(alt, partner, 0.137);
      assert.ok(Math.abs(d.p0 + d.p1 + d.p2 - 1) < 1e-12, `${alt} x ${partner}`);
    }
  }
});

test("an alt count outside 0..2 and an unknown partner model fail loudly", () => {
  assert.throws(() => offspringDistribution(3, "wildtype", 0.1), /alt-allele count/);
  assert.throws(() => offspringDistribution(null, "wildtype", 0.1), /alt-allele count/);
  assert.throws(() => offspringDistribution(1, "carrier", 0.1), /unknown partner model/);
});

test("unscreened without a usable allele frequency is unavailable, never defaulted", () => {
  for (const af of [null, undefined, NaN, -0.1, 1.5]) {
    const d = offspringDistribution(1, "unscreened", af);
    assert.equal(d.available, false);
    assert.match(d.reason, /Not available/);
    assert.equal(geneOutcome(AR, d).available, false);
  }
});

test("a Mendelian outcome names affected and carrier; a transmission outcome names neither", () => {
  const dist = offspringDistribution(1, "heterozygous", 0.1);
  const mendelian = geneOutcome(AR, dist, "F508del");
  assert.equal(mendelian.affected, 0.25);
  assert.equal(mendelian.carrier, 0.5);
  const transmission = geneOutcome(RF, dist, "Leiden");
  assert.equal("affected" in transmission, false);
  assert.equal("carrier" in transmission, false);
  assert.equal(transmission.label, "Chance a child inherits the Leiden allele");
});

test("a Mendelian gene with an unsupported model throws instead of guessing", () => {
  const bad = gene("trait", true);
  assert.throws(() => geneOutcome(bad, offspringDistribution(1, "wildtype", 0.1)), /unsupported model/);
  assert.throws(() => patientStatus(bad, 1), /unsupported model/);
});

test("a gene without an inheritance block fails closed", () => {
  assert.throws(() => geneOutcome({}, offspringDistribution(1, "wildtype", 0.1)), /inheritance block/);
});

test("describeSegregation carries the inputs the simulator reruns, and status only for Mendelian genes", () => {
  const seg = describeSegregation("CFTR", AR, 1, 0.011931, "ATCT>A");
  assert.deepEqual(
    { gene: seg.gene, altCount: seg.altCount, af: seg.af, allele: seg.allele, is_carrier: seg.is_carrier, is_affected: seg.is_affected },
    { gene: "CFTR", altCount: 1, af: 0.011931, allele: "ATCT>A", is_carrier: true, is_affected: false }
  );
  const rf = describeSegregation("F5", RF, 0, 0.021432, "T");
  assert.equal("is_affected" in rf, false);
  assert.equal("is_carrier" in rf, false);
});

test("multi-locus ignores component loci and records with no call", () => {
  const genes = { F5: RF, F2: RF };
  const r = (rsid, g, chrom, altCount, extra = {}) => ({ rsid, gene: g, chrom, altCount, standalone: true, role: "standard", ...extra });
  assert.equal(detectMultiLocus([r("a", "F5", "1", 1), r("b", "F2", "11", null)], genes).length, 0);
  assert.equal(detectMultiLocus([r("a", "F5", "1", 1), r("b", "F2", "11", 1, { role: "apoe_component" })], genes).length, 0);
  assert.equal(detectMultiLocus([r("a", "F5", "1", 1), r("b", "F2", "11", 1)], genes).length, 1);
});

test("compound heterozygosity never asserts trans phase", () => {
  const genes = { CFTR: AR };
  const recs = ["rs1", "rs2"].map((rsid) => ({ rsid, gene: "CFTR", chrom: "7", altCount: 1, role: "standard" }));
  const [f] = detectCompoundHeterozygosity(recs, genes);
  assert.equal(f.phase, "unknown");
  assert.doesNotMatch(JSON.stringify(f).toLowerCase(), /trans phase|opposite|separate chromosomes/);
});
