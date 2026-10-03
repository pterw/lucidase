import test from "node:test";
import assert from "node:assert/strict";

import { loadKnowledgeBase } from "../src/kb-loader.js";
import { layoutKaryogram } from "../src/core/karyogram.js";
import { renderKaryogramSvg } from "../src/karyogram-view.js";

const kb = await loadKnowledgeBase();
const observations = Object.fromEntries(kb.lociList.map((l) => [l.rsid, "supported_and_observed"]));
const count = (s, re) => (s.match(re) ?? []).length;
const sampleLayout = (calls, build = "GRCh37") =>
  layoutKaryogram({ kb, sample: { build, calls, observations } });
const call = (chrom, pos) => ({ rsid: "rsX", chrom, pos, alleles: ["A", "A"] });

test("the same layout renders the same string", () => {
  const layout = layoutKaryogram({ kb });
  assert.equal(renderKaryogramSvg(layout), renderKaryogramSvg(layout));
});

test("24 columns and 14 reference loci with no sample", () => {
  const svg = renderKaryogramSvg(layoutKaryogram({ kb }));
  assert.equal(count(svg, /data-chrom="/g), 24);
  assert.equal(count(svg, /class="kary-locus /g), 14);
  assert.equal(count(svg, /data-state="reference"/g), 14);
  assert.match(svg, /role="img"/);
  assert.match(svg, /<title id="kary-title">Karyogram \(GRCh38\)<\/title>/);
  assert.doesNotMatch(svg, /fill=/);
});

test("the busiest bin has r=3.2 and empty bins r=0.9", () => {
  // chr2, well away from the centromere: 4 calls in one bin, 1 in another.
  const calls = [call("2", 5_000_001), call("2", 5_000_002), call("2", 5_000_003), call("2", 5_000_004), call("2", 9_000_001)];
  const svg = renderKaryogramSvg(sampleLayout(calls));
  assert.equal(count(svg, /class="kary-bin" [^>]*r="3\.2"/g), 1);
  assert.equal(count(svg, /class="kary-bin" /g), 2);
  assert.ok(count(svg, /kary-bin-empty" [^>]*r="0\.9"/g) > 100);
  assert.match(svg, /r="2\.0"/); // 0.9 + 2.3 * sqrt(1/4) = 2.05
});

test("density unavailable draws only empty dots", () => {
  const svg = renderKaryogramSvg(sampleLayout([call("2", 5_000_001)], "unknown"));
  assert.equal(count(svg, /class="kary-bin" /g), 0);
  assert.ok(count(svg, /kary-bin-empty/g) > 100);
  assert.match(svg, /density unavailable/);
});

test("a hostile gene name is escaped in the title and the desc", () => {
  const layout = layoutKaryogram({ kb });
  layout.reference.loci[0].gene = `<b>&"'`;
  const svg = renderKaryogramSvg(layout);
  assert.doesNotMatch(svg, /<b>/);
  assert.match(svg, /<title>&lt;b&gt;&amp;&quot;&#39; rs/);
  // desc carries state labels; a hostile state label must be escaped there too.
  const svg2 = renderKaryogramSvg(layoutKaryogram({ kb }), { stateLabels: { reference: `<b>&"'` } });
  assert.doesNotMatch(svg2, /<b>/);
  assert.match(svg2, /<desc id="kary-desc">[^<]*&lt;b&gt;&amp;&quot;&#39;: 14/);
});

test("co-located loci get distinct x positions", () => {
  const svg = renderKaryogramSvg(layoutKaryogram({ kb }));
  const xOf = (rsid) => {
    const m = svg.match(new RegExp(`data-rsid="${rsid}"[\\s\\S]*?kary-core" cx="([\\d.]+)"`));
    assert.ok(m, rsid);
    return m[1];
  };
  assert.notEqual(xOf("rs1799945"), xOf("rs1800562"));
  assert.notEqual(xOf("rs429358"), xOf("rs7412"));
});

const STATES = ["supported_and_observed", "supported_not_observed", "not_tested_by_array", "insufficient_evidence"];
const mixedObservations = Object.fromEntries(kb.lociList.map((l, i) => [l.rsid, STATES[i % STATES.length]]));
const mixedLayout = (calls = []) =>
  layoutKaryogram({ kb, sample: { build: "GRCh37", calls, observations: mixedObservations } });

test("with a sample, each locus group carries its observed state as data-state and class", () => {
  const svg = renderKaryogramSvg(mixedLayout());
  assert.equal(count(svg, /class="kary-locus /g), 14);
  assert.equal(count(svg, /data-state="reference"/g), 0);
  for (const [rsid, state] of Object.entries(mixedObservations)) {
    assert.match(
      svg,
      new RegExp(`<g class="kary-locus kary-state-${state}" data-rsid="${rsid}" data-state="${state}">`),
      rsid,
    );
  }
});

test("the desc counts loci per state from the sample", () => {
  const labels = {
    supported_and_observed: "L-obs",
    supported_not_observed: "L-wt",
    not_tested_by_array: "L-gap",
    insufficient_evidence: "L-ins",
  };
  const svg = renderKaryogramSvg(mixedLayout(), { stateLabels: labels });
  const per = Object.fromEntries(STATES.map((s) => [s, Object.values(mixedObservations).filter((o) => o === s).length]));
  assert.equal(Object.values(per).reduce((a, b) => a + b, 0), 14);
  for (const s of STATES) assert.ok(svg.includes(`${labels[s]}: ${per[s]}`), `${s}: ${per[s]}`);
});

test("markers inside a centromere band are drawn as dots, and the busiest such bin reaches r=3.2", () => {
  const [cenStart, cenEnd] = kb.assemblies.GRCh37.chromosomes["2"].centromere;
  const inBand = [cenStart, cenStart + 1, cenStart + 2, cenStart + 3].map((p) => call("2", p));
  const svg = renderKaryogramSvg(sampleLayout([...inBand, call("2", cenEnd + 5_000_000)]));
  const chr2 = svg.match(/<g class="kary-col" data-chrom="2">[\s\S]*?<\/g>/)[0];
  assert.equal(count(chr2, /class="kary-bin" [^>]*r="3\.2"/g), 1);
  assert.equal(count(chr2, /class="kary-bin" /g), 2);
});

test("a centromere bin with no markers, no sample, or unavailable density keeps the tick", () => {
  const ticks = (svg) => count(svg.match(/<g class="kary-col" data-chrom="2">[\s\S]*?<\/g>/)[0], /class="kary-cen"/g);
  // No sample and an unknown build both use the GRCh38 geometry; a GRCh37 sample uses GRCh37.
  const grch38 = ticks(renderKaryogramSvg(layoutKaryogram({ kb })));
  assert.ok(grch38 > 0);
  assert.equal(ticks(renderKaryogramSvg(sampleLayout([call("2", 5_000_001)], "unknown"))), grch38);
  const grch37 = ticks(renderKaryogramSvg(sampleLayout([])));
  assert.ok(grch37 > 0);
  const [cenStart] = kb.assemblies.GRCh37.chromosomes["2"].centromere;
  assert.equal(ticks(renderKaryogramSvg(sampleLayout([call("2", cenStart)]))), grch37 - 1);
});

test("the karyogram state labels reuse the analysis labels and add the reference label", async () => {
  const { karyogramStateLabels } = await import("../src/view-model.js");
  const labels = karyogramStateLabels();
  assert.deepEqual(Object.keys(labels).sort(), ["insufficient_evidence", "not_tested_by_array", "reference", "supported_and_observed", "supported_not_observed"]);
  assert.equal(labels.supported_and_observed, "Supported & Observed");
  assert.equal(labels.not_tested_by_array, "Array Gap (State 3)");
  labels.reference = "changed";
  assert.notEqual(karyogramStateLabels().reference, "changed");
});
