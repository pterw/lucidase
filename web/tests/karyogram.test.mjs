import test from "node:test";
import assert from "node:assert/strict";

import { loadKnowledgeBase } from "../src/kb-loader.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { CHROMOSOME_ORDER, layoutKaryogram, rollUpGeneResult } from "../src/core/karyogram.js";
import { COVERAGE_STATES } from "../src/core/coverage.js";
import { parseGenotypeFile } from "../src/core/parse.js";
import { classify } from "../src/core/classify.js";

const kb = await loadKnowledgeBase();
const observations = Object.fromEntries(kb.lociList.map((l) => [l.rsid, "supported_not_observed"]));
const call = (chrom, pos) => ({ rsid: "rsX", chrom, pos, alleles: ["A", "A"] });
const sumUnplaced = (t) => Object.values(t.unplaced).reduce((a, b) => a + b, 0);

test("reference-only layout is GRCh38, 24 chromosomes in order, loci at pos_grch38", () => {
  const layout = layoutKaryogram({ kb });
  assert.equal(layout.geometry.build, "GRCh38");
  assert.deepEqual(
    layout.geometry.chromosomes.map((c) => c.name),
    [...CHROMOSOME_ORDER],
  );
  assert.equal(layout.geometry.chromosomes[0].length, kb.assemblies.GRCh38.chromosomes["1"].length);
  assert.equal(layout.reference.loci.length, 48);
  for (const l of layout.reference.loci) assert.equal(l.pos, kb.loci[l.rsid].pos_grch38);

  assert.equal(layout.sample, null);
  for (const l of layout.reference.loci) assert.deepEqual(Object.keys(l), ["rsid", "gene", "chrom", "pos"]);
});

test("a GRCh37 sample uses the GRCh37 geometry and pos_grch37", () => {
  const layout = layoutKaryogram({ kb, sample: { build: "GRCh37", calls: [], observations } });
  assert.equal(layout.geometry.build, "GRCh37");
  assert.equal(layout.geometry.chromosomes[0].length, kb.assemblies.GRCh37.chromosomes["1"].length);
  for (const l of layout.reference.loci) assert.equal(l.pos, kb.loci[l.rsid].pos_grch37);
  assert.equal(layout.sample.density, "available");
});

test("hand-built calls land in exact bins and the rest is counted by reason", () => {
  const len = kb.assemblies.GRCh37.chromosomes["1"].length;
  const bs = 2_000_000;
  const calls = [
    call("1", 1),
    call("1", bs),
    call("1", bs + 1),
    call("1", len),
    call("MT", 100),
    call("XY", 5),
    call("0", 5),
    call("1", null),
    call("1", len + 1),
  ];
  const { sample } = layoutKaryogram({ kb, sample: { build: "GRCh37", calls, observations }, binSize: bs });
  const bins = sample.bins["1"];
  assert.equal(bins.length, Math.ceil(len / bs));
  assert.equal(bins[0], 2);
  assert.equal(bins[1], 1);
  assert.equal(bins[bins.length - 1], 1);
  assert.equal(bins.reduce((a, b) => a + b, 0), 4);
  assert.equal(sample.totals.placed, 4);
  assert.equal(sample.totals.mt, 1);
  assert.deepEqual(sample.totals.unplaced, { XY: 1, 0: 1 });
  assert.equal(sample.totals.outOfBounds, 2);
  assert.equal(sample.totals.notPlacedBuildUnknown, 0);
  assert.equal(sample.totals.rows, calls.length);
  const t = sample.totals;
  assert.equal(t.rows, t.placed + t.mt + sumUnplaced(t) + t.outOfBounds + t.notPlacedBuildUnknown);
});

test("an unknown build places nothing by position", () => {
  const calls = [call("1", 100), call("X", 200), call("MT", 1), call("XY", 1), call("1", null)];
  const { geometry, sample } = layoutKaryogram({ kb, sample: { build: "unknown", calls, observations } });
  assert.equal(geometry.build, "GRCh38");
  assert.equal(sample.density, "unavailable");
  assert.equal(sample.bins, null);
  const t = sample.totals;
  assert.equal(t.placed, 0);
  assert.equal(t.outOfBounds, 0);
  assert.equal(t.notPlacedBuildUnknown, 3);
  assert.equal(t.mt, 1);
  assert.deepEqual(t.unplaced, { XY: 1 });
  assert.equal(t.rows, t.placed + t.mt + sumUnplaced(t) + t.outOfBounds + t.notPlacedBuildUnknown);
});

test("bad input throws", () => {
  const sample = { build: "GRCh37", calls: [], observations };
  const missing = { ...observations };
  delete missing.rs429358;
  assert.throws(() => layoutKaryogram({ kb, sample: { ...sample, observations: missing } }), /rs429358/);
  assert.throws(() => layoutKaryogram({ kb, sample, binSize: 0 }), /binSize/);
  assert.throws(() => layoutKaryogram({ kb, sample, binSize: 1.5 }), /binSize/);
  const { assemblies, ...noAssemblies } = kb;
  assert.throws(() => layoutKaryogram({ kb: noAssemblies }), /assemblies/);
});

test("an observation that is not a known coverage state throws", () => {
  const sample = { build: "GRCh37", calls: [], observations };
  for (const bad of ["bogus", "", null, undefined, 3, "reference"]) {
    const obs = { ...observations, rs429358: bad };
    assert.throws(() => layoutKaryogram({ kb, sample: { ...sample, observations: obs } }), /rs429358.*coverage state/, String(bad));
  }
  for (const good of Object.values(COVERAGE_STATES)) {
    const obs = { ...observations, rs429358: good };
    assert.doesNotThrow(() => layoutKaryogram({ kb, sample: { ...sample, observations: obs } }), good);
  }
});

test("chromosome names that collide with Object.prototype are counted as unplaced, not mangled", () => {
  const calls = [call("constructor", 1), call("constructor", 2), call("__proto__", 3), call("toString", 4), call("1", 100)];
  const { sample } = layoutKaryogram({ kb, sample: { build: "GRCh37", calls, observations } });
  const t = sample.totals;
  assert.deepEqual(Object.keys(t.unplaced).sort(), ["__proto__", "constructor", "toString"]);
  assert.equal(t.unplaced.constructor, 2);
  assert.equal(t.unplaced.toString, 1);
  assert.equal(Object.getOwnPropertyDescriptor(t.unplaced, "__proto__").value, 1);
  assert.equal(Object.getPrototypeOf(t.unplaced), Object.prototype);
  assert.equal(t.placed, 1);
  assert.equal(t.rows, t.placed + t.mt + sumUnplaced(t) + t.outOfBounds + t.notPlacedBuildUnknown);
});

test("the remaining bad-input branches throw", () => {
  const sample = { build: "GRCh37", calls: [], observations };
  assert.throws(() => layoutKaryogram(), /assemblies/);
  assert.throws(() => layoutKaryogram({ kb: null }), /assemblies/);
  assert.throws(() => layoutKaryogram({ kb: { ...kb, assemblies: "x" } }), /assemblies/);
  assert.throws(() => layoutKaryogram({ kb: { ...kb, loci: undefined } }), /loci/);
  assert.throws(() => layoutKaryogram({ kb, binSize: -5 }), /binSize/);
  assert.throws(() => layoutKaryogram({ kb, binSize: "2000000" }), /binSize/);
  assert.throws(() => layoutKaryogram({ kb, sample: { build: "GRCh37", calls: [] } }), /no observation/);
  const noBuild = { ...kb, assemblies: { GRCh38: kb.assemblies.GRCh38 } };
  assert.throws(() => layoutKaryogram({ kb: noBuild, sample }), /no GRCh37 assembly/);
  assert.throws(() => layoutKaryogram({ kb: { ...kb, assemblies: { GRCh38: {} } } }), /no GRCh38 assembly/);
  const { Y, ...noY } = kb.assemblies.GRCh37.chromosomes;
  const noYKb = { ...kb, assemblies: { ...kb.assemblies, GRCh37: { ...kb.assemblies.GRCh37, chromosomes: noY } } };
  assert.throws(() => layoutKaryogram({ kb: noYKb, sample }), /GRCh37 has no chromosome Y/);
});

test("the real committed karyogram sample lays out and the totals invariant holds", () => {
  const text = readFileSync(fileURLToPath(new URL("../demo-data/sample-karyogram-23andme.txt", import.meta.url)), "utf8");
  const parsed = parseGenotypeFile(text, "sample-karyogram-23andme.txt");
  assert.equal(parsed.build, "GRCh37");
  const { records } = classify(parsed, kb);
  const obs = Object.fromEntries(records.map((r) => [r.rsid, r.coverage_state]));
  const { sample } = layoutKaryogram({ kb, sample: { build: parsed.build, calls: parsed.calls, observations: obs } });
  const t = sample.totals;
  assert.equal(sample.density, "available");
  assert.equal(t.rows, parsed.calls.length);
  assert.equal(t.rows, t.placed + t.mt + sumUnplaced(t) + t.outOfBounds + t.notPlacedBuildUnknown);
  assert.ok(t.placed > 15_000);
  const binned = Object.values(sample.bins).flat().reduce((a, b) => a + b, 0);
  assert.equal(binned, t.placed);
});


test("rollUpGeneResult validates input arguments and locus rsids", () => {
  assert.throws(() => rollUpGeneResult(), /loci must be a non-empty array/);
  assert.throws(() => rollUpGeneResult([]), /loci must be a non-empty array/);
  assert.throws(() => rollUpGeneResult(["not_an_rsid"]), /invalid locus rsid/);
  assert.throws(() => rollUpGeneResult([{ notRsid: "rs123" }]), /invalid locus rsid/);
});

test("rollUpGeneResult returns reference state and 'No file yet' when no sample observations exist", () => {
  const res = rollUpGeneResult(["rs1050828", "rs1050829", "rs5030868"], null);
  assert.deepEqual(res, {
    state: "reference",
    tested: 0,
    total: 3,
    isPartial: false,
  });
});

test("rollUpGeneResult throws on missing or invalid observation states (fail-fast)", () => {
  const loci = ["rs1", "rs2"];
  assert.throws(() => rollUpGeneResult(loci, { rs1: "supported_not_observed" }), /no observation for locus rs2/);
  assert.throws(
    () => rollUpGeneResult(loci, { rs1: "supported_not_observed", rs2: "invalid_state" }),
    /unknown or missing coverage state/
  );
});

test("rollUpGeneResult preserves partial coverage in negative multi-locus gene results (P1-097)", () => {
  const g6pdLoci = [{ rsid: "rs1050828" }, { rsid: "rs1050829" }, { rsid: "rs5030868" }];

  // 1 of 3 tested, negative
  const partial1 = rollUpGeneResult(g6pdLoci, {
    rs1050828: "not_tested_by_array",
    rs1050829: "supported_not_observed",
    rs5030868: "not_tested_by_array",
  });
  assert.deepEqual(partial1, {
    state: "supported_not_observed",
    tested: 1,
    total: 3,
    isPartial: true,
  });

  // 2 of 3 tested, negative
  const partial2 = rollUpGeneResult(g6pdLoci, {
    rs1050828: "supported_not_observed",
    rs1050829: "supported_not_observed",
    rs5030868: "not_tested_by_array",
  });
  assert.deepEqual(partial2, {
    state: "supported_not_observed",
    tested: 2,
    total: 3,
    isPartial: true,
  });

  // 3 of 3 tested, fully negative
  const full = rollUpGeneResult(g6pdLoci, {
    rs1050828: "supported_not_observed",
    rs1050829: "supported_not_observed",
    rs5030868: "supported_not_observed",
  });
  assert.deepEqual(full, {
    state: "supported_not_observed",
    tested: 3,
    total: 3,
    isPartial: false,
  });

  // 0 of 3 tested (all gaps)
  const gaps = rollUpGeneResult(g6pdLoci, {
    rs1050828: "not_tested_by_array",
    rs1050829: "not_tested_by_array",
    rs5030868: "not_tested_by_array",
  });
  assert.deepEqual(gaps, {
    state: "not_tested_by_array",
    tested: 0,
    total: 3,
    isPartial: false,
  });

  // 1 observed (variant present) takes precedence
  const observed = rollUpGeneResult(g6pdLoci, {
    rs1050828: "supported_and_observed",
    rs1050829: "supported_not_observed",
    rs5030868: "not_tested_by_array",
  });
  assert.deepEqual(observed, {
    state: "supported_and_observed",
    tested: 2,
    total: 3,
    isPartial: false,
  });

  // 1 unclear and none observed takes precedence over negative/gap
  const unclear = rollUpGeneResult(g6pdLoci, {
    rs1050828: "insufficient_evidence",
    rs1050829: "supported_not_observed",
    rs5030868: "not_tested_by_array",
  });
  assert.deepEqual(unclear, {
    state: "insufficient_evidence",
    tested: 2,
    total: 3,
    isPartial: false,
  });
});
