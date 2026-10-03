import test from "node:test";
import assert from "node:assert/strict";

import { loadKnowledgeBase } from "../src/kb-loader.js";
import { CHROMOSOME_ORDER, layoutKaryogram } from "../src/core/karyogram.js";

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
  assert.equal(layout.reference.loci.length, 14);
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
