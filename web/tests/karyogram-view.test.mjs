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
  assert.match(svg, /class="kary-bin" [^>]*r="2\.4"/); // 1.6 + 1.6 * sqrt(1/4) = 2.4
});

test("a one-marker bin beside a busiest bin of 300 is visibly larger than an empty bin", () => {
  const calls = [call("2", 9_000_001)];
  for (let i = 0; i < 300; i++) calls.push(call("2", 5_000_001 + i));
  const svg = renderKaryogramSvg(sampleLayout(calls));
  const radii = [...svg.matchAll(/class="kary-bin" [^>]*r="([\d.]+)"/g)].map((m) => Number(m[1])).sort((a, b) => a - b);
  assert.equal(radii.length, 2);
  assert.ok(radii[0] >= 1.6, `one-marker bin r=${radii[0]}`);
  assert.equal(radii[1], 3.2);
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
  // The design system's plain result words (StateMark), never a "State N" code.
  assert.equal(labels.supported_and_observed, "Found");
  assert.equal(labels.supported_not_observed, "Not found");
  assert.equal(labels.not_tested_by_array, "Not on your chip");
  assert.equal(labels.insufficient_evidence, "Unclear");
  for (const text of Object.values(labels)) assert.ok(!/State \d|Observed|Array Gap|Wild-Type/.test(text), text);
  labels.reference = "changed";
  assert.notEqual(karyogramStateLabels().reference, "changed");
});

// Hand-made layout, no sample, default 2 Mb bins. Column 1: 3 bins, centromere in bin 1. Column 2: 5 bins, centromere in
// bin 2. So cenY = 24 + 2 * 7 = 38; column 1 bins sit at y 31, 38, 45 and column 2 bins at 24, 31, 38, 45, 52.
const handLayout = () => ({
  geometry: {
    build: "GRCh38",
    chromosomes: [
      { name: "1", length: 6_000_000, centromere: [2_000_001, 2_500_000] },
      { name: "2", length: 10_000_000, centromere: [4_000_001, 5_000_000] },
    ],
  },
  reference: {
    loci: [
      { rsid: "rsA", gene: "GA", chrom: "1", pos: 2_100_000 },
      { rsid: "rsB", gene: "GB", chrom: "2", pos: 100 },
    ],
  },
  sample: null,
});

test("centromeres align across columns and loci sit at the exact y of their bin", () => {
  const svg = renderKaryogramSvg(handLayout());
  assert.match(svg, /width="56\.0" height="76\.0" viewBox="0 0 56\.0 76\.0"/);
  const col = (n) => svg.match(new RegExp(`<g class="kary-col" data-chrom="${n}">[\\s\\S]*?</g>`))[0];
  // Both centromere ticks are on y=38 (aligned), at the columns' x of 14 and 42.
  assert.ok(col("1").includes('<line class="kary-cen" x1="11.0" y1="38.0" x2="17.0" y2="38.0"/>'));
  assert.ok(col("2").includes('<line class="kary-cen" x1="39.0" y1="38.0" x2="45.0" y2="38.0"/>'));
  const ys = (n) => [...col(n).matchAll(/<circle class="kary-bin[^"]*" cx="[\d.]+" cy="([\d.]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ys("1"), ["31.0", "45.0"]);
  assert.deepEqual(ys("2"), ["24.0", "31.0", "45.0", "52.0"]);
  assert.ok(col("1").includes('y="59.0"')); // label: last bin y 45 + 14
  assert.ok(col("2").includes('y="66.0"'));
  const locus = (rsid) => svg.match(new RegExp(`data-rsid="${rsid}"[\\s\\S]*?kary-core" cx="([\\d.]+)" cy="([\\d.]+)"`));
  assert.deepEqual(locus("rsA").slice(1), ["14.0", "38.0"]);
  assert.deepEqual(locus("rsB").slice(1), ["42.0", "24.0"]);
});

test("a locus on a chromosome that is not drawn throws instead of rendering NaN coordinates", () => {
  // Object.prototype members are not columns: a plain-object lookup found them and drew cx="NaN".
  for (const chrom of ["constructor", "__proto__", "toString", "hasOwnProperty", "chrUnknown"]) {
    const layout = handLayout();
    layout.reference.loci[0].chrom = chrom;
    assert.throws(
      () => renderKaryogramSvg(layout),
      (err) => err instanceof Error && err.message.includes(`undrawn chromosome ${chrom}`),
      chrom,
    );
  }
});

test("an unknown build says the GRCh38 geometry is a fallback and the file build is unknown", () => {
  const svg = renderKaryogramSvg(sampleLayout([call("2", 5_000_001)], "unknown"));
  const unescape = (t) => t.replaceAll("&#39;", "'").replaceAll("&#x27;", "'").replaceAll("&apos;", "'");
  const title = unescape(svg.match(/<title id="kary-title">([^<]*)<\/title>/)[1]);
  const desc = unescape(svg.match(/<desc id="kary-desc">([^<]*)<\/desc>/)[1]);
  const lead = "Karyogram: your file's genome version is unknown, so the chromosomes are drawn from the GRCh38 reference";
  assert.equal(title, lead);
  assert.ok(desc.startsWith(`${lead}. `), desc);
  assert.match(desc, /density unavailable/);
});

test("a known build keeps the plain title and desc", () => {
  const svg = renderKaryogramSvg(sampleLayout([call("2", 5_000_001)]));
  assert.match(svg, /<title id="kary-title">Karyogram \(GRCh37\)<\/title>/);
  assert.doesNotMatch(svg, /genome version is unknown/);
});
