import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { validateKb } from "../src/core/kb.js";
import { parseGenotypeFile } from "../src/core/parse.js";
import { classify } from "../src/core/classify.js";
import { assembleFindings } from "../src/core/apoe.js";
import { describeSegregation } from "../src/core/inheritance.js";
import {
  NOT_AVAILABLE,
  NO_CLINVAR_STATUS,
  apoeCardModel,
  csvReport,
  drawerTierText,
  escapeHtml,
  kbBadge,
  markdownReport,
  partnerModelNote,
  testedVariantCounts,
  toViewModel,
} from "../src/view-model.js";

const readText = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const KB_JSON = JSON.parse(readText("../src/knowledge-base.json"));
const DEMO = readText("../demo-data/sample-23andme.txt");

const PLACEHOLDERS = [
  "undefined", "null", "NaN", "MANE Select Transcript", "MANE Select Pending", "Score Available in API",
  "Constraint Available", "N/A (Non-missense)", "N/A (Not characterized)", "Domain boundaries computed from PAE matrix.",
  "Tested Normal", "Normal Baseline", "APOE-STATUS",
];

/** Classified view models for a genotype file, as the worker and app produce them. */
function analyse(text, mutateKb = (kb) => kb) {
  const kb = validateKb(mutateKb(structuredClone(KB_JSON)));
  const parsed = parseGenotypeFile(text, "x.txt");
  const { records, summary } = classify(parsed, kb);
  const { listed, apoe } = assembleFindings(records, kb, summary.outside_coverage_count);
  const counts = testedVariantCounts(listed);
  const vms = listed.map((r) => toViewModel(r, kb.genes, counts));
  return { kb, vms, apoe: apoe ? toViewModel(apoe, kb.genes, counts) : null, byRsid: Object.fromEntries(vms.map((v) => [v.id, v])) };
}

/** Every string anywhere in a display model (the raw record fields are excluded). */
const DISPLAY_KEYS = [
  "id", "exportId", "genotype", "positionText", "coordinates", "chromosomes", "positionExport", "stateBadge",
  "stateLabel", "tier", "category", "significance", "significanceValue", "phenotype", "statement", "magnitudeText",
  "starsText", "starsDetail", "clinvarUrl", "afText", "limitation", "limitationTooltip", "modelLabel",
];
const displayStrings = (vm) => [
  ...DISPLAY_KEYS.map((k) => vm[k]),
  ...Object.values(vm.biotools).flat(2),
  ...vm.caveats,
].filter((v) => typeof v === "string");

function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\r") { /* line end follows */ }
    else if (ch === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  row.push(cell); rows.push(row);
  const [header, ...body] = rows;
  return body.map((r) => Object.fromEntries(header.map((h, i) => [h, r[i]])));
}

const reportData = (a, extra = {}) => ({
  fileName: "x.txt",
  qc: { format_name: "23andme", build: "GRCh37", sex_signal: "x", total_snps: 1, call_rate: 1, heterozygosity_rate: 0.1 },
  manifest: { guardrail: "guardrail text" },
  coverage: {},
  apoe: a.apoe,
  compoundHeterozygotes: [],
  independentAssortment: [],
  // The worker's grouping: variant-present findings with an interpretation, then wild-type rows.
  records: a.vms.filter((v) => v.sample_observation === "variant_present" && v.interpretation !== null),
  negativeChecks: a.vms.filter((v) => v.sample_observation === "wild_type"),
  arrayGaps: a.vms.filter((v) => v.coverage_state === "not_tested_by_array"),
  insufficientEvidence: a.vms.filter((v) => v.coverage_state === "insufficient_evidence"),
  ...extra,
});

test("a record with null evidence fields shows Not available, never a fallback value", () => {
  const { vms, kb } = analyse(DEMO);
  const rec = structuredClone(vms.find((v) => v.id === "rs4244285"));
  rec.evidence = { clinvar: {}, gnomad: {} };
  rec.evidence_tier = null;
  const vm = toViewModel(rec, { ...kb.genes, CYP2C19: { ...kb.genes.CYP2C19, insights: null } });
  assert.equal(vm.tier, null);
  assert.equal(vm.stars, null);
  assert.equal(vm.starsText, NO_CLINVAR_STATUS);
  assert.equal(vm.afText, null);
  assert.equal(vm.clinvarUrl, null);
  assert.equal(vm.biotools.transcript, null);
  assert.equal(vm.biotools.alphamissense, null);
  assert.equal(vm.biotools.constraint, null);
  assert.equal(vm.biotools.uniprot, null);
  for (const field of ["evidence_tier", "clinvar_stars", "gnomad_af"]) assert.ok(vm.missing_fields.includes(field), field);
  for (const text of displayStrings(vm)) for (const bad of PLACEHOLDERS) assert.ok(!text.includes(bad), `${bad} in "${text}"`);
  assert.equal(drawerTierText(vm), `Evidence tier: ${NOT_AVAILABLE}`);

  const csv = parseCsv(csvReport([vm], kb.genes))[0];
  assert.equal(csv.Evidence_Tier, "");
  assert.equal(csv.ClinVar_Stars, "");
  assert.equal(csv.Gnomad_AF, "");
  assert.match(csv.Missing_Fields, /evidence_tier/);
});

test("a not-tested record has no undefined, null or NaN in any field, and shows its state label and reason", () => {
  const { vms, kb } = analyse(DEMO.replace(/^rs6025[^\n]*\r?\n/m, ""));
  const gap = vms.find((v) => v.id === "rs6025");
  assert.equal(gap.coverage_state, "not_tested_by_array");
  assert.equal(gap.significance, "Array Gap (State 3)");
  assert.equal(gap.phenotype, "locus not assayed on this array");
  assert.match(gap.positionText, /^chr1:169,519,049$/);
  assert.equal(gap.genotype, null);
  for (const text of displayStrings(gap)) for (const bad of PLACEHOLDERS) assert.ok(!text.includes(bad), `${bad} in "${text}"`);

  const csv = parseCsv(csvReport([gap], kb.genes))[0];
  assert.equal(csv.Magnitude, "");
  assert.equal(csv.Repute, "", "no 'Neutral' placeholder for a locus with no interpretation");
  assert.equal(csv.Category, "");
  assert.equal(csv.Position, "169519049");
  // A row with no segregation input also names its three empty inheritance cells.
  assert.deepEqual(csv.Missing_Fields.split(";"), [
    ...gap.missing_fields,
    "child_inherits_allele_wildtype_partner",
    "child_inherits_allele_unscreened_partner",
    "child_affected_unscreened_partner",
  ]);
  for (const name of ["genotype", "category", "magnitude", "repute"]) assert.ok(gap.missing_fields.includes(name), name);
});

/** The worker's segregation input for a view model (altCount and the KB's gnomAD af), so CSV inheritance cells can be built. */
function withSegregation(vm, kb, afOverride) {
  const e4 = vm.rsid === "APOE-STATUS";
  const locus = kb.loci[e4 ? "rs429358" : vm.rsid];
  const af = afOverride === undefined ? locus.evidence.gnomad.af : afOverride;
  const altCount = e4 ? vm.components[0].altCount : vm.altCount;
  return { ...vm, segregation: altCount === null ? null : describeSegregation(vm.gene, kb.genes[vm.gene], altCount, af, locus.alt) };
}

test("the demo file with CRLF line endings still drops the rs6025 row", () => {
  const a = analyse(DEMO.replace(/\r?\n/g, "\r\n").replace(/^rs6025[^\n]*\r?\n/m, ""));
  assert.equal(a.byRsid.rs6025.coverage_state, "not_tested_by_array");
});

test("inheritance cells: only the non-Mendelian affected cell is N/A, every other unavailable cell is empty and named in Missing_Fields", () => {
  const a = analyse(DEMO.replace(/^rs6025[^\n]*\r?\n/m, ""));
  const cells = ["Child_Inherits_Allele_Wildtype_Partner", "Child_Inherits_Allele_Unscreened_Partner", "Child_Affected_Unscreened_Partner"];
  const csvOf = (vm) => parseCsv(csvReport([vm], a.kb.genes))[0];
  const gap = csvOf(withSegregation(a.byRsid.rs6025, a.kb));
  for (const c of cells) assert.equal(gap[c], "", `${c} must be empty for a not-tested row`);
  for (const name of cells.map((c) => c.toLowerCase())) assert.ok(gap.Missing_Fields.split(";").includes(name), name);
  // A tested non-Mendelian row: transmission numbers, and "N/A" (not applicable) for the affected cell.
  const risk = csvOf(withSegregation(a.byRsid.rs1799963, a.kb));
  assert.match(risk.Child_Inherits_Allele_Wildtype_Partner, /^\d/);
  assert.equal(risk.Child_Affected_Unscreened_Partner, "N/A");
  assert.ok(!risk.Missing_Fields.includes("child_"));
  // No gnomAD af: the unscreened transmission cell is missing data, not "N/A".
  const noAf = csvOf(withSegregation(a.byRsid.rs1799963, a.kb, null));
  assert.equal(noAf.Child_Inherits_Allele_Unscreened_Partner, "");
  assert.ok(noAf.Missing_Fields.split(";").includes("child_inherits_allele_unscreened_partner"));
  assert.equal(noAf.Child_Affected_Unscreened_Partner, "N/A");
  // A Mendelian gene with no unscreened outcome has an empty affected cell, named as missing.
  const hfe = csvOf(withSegregation(a.byRsid.rs1800562, a.kb, null));
  assert.equal(hfe.Child_Affected_Unscreened_Partner, "");
  assert.ok(hfe.Missing_Fields.split(";").includes("child_affected_unscreened_partner"));
  // Over the whole demo, no cell holds "N/A" except the non-Mendelian affected cell.
  for (const vm of a.vms) {
    const row = csvOf(withSegregation(vm, a.kb));
    for (const c of cells.slice(0, 2)) assert.notEqual(row[c], "N/A", `${vm.id} ${c}`);
  }
});

test("the APOE row never presents one component's evidence as its own", () => {
  const a = analyse(DEMO);
  const apoe = a.apoe;
  const e4 = a.kb.loci.rs429358.evidence;
  const e2 = a.kb.loci.rs7412.evidence;
  assert.notEqual(e4.clinvar.stars, e2.clinvar.stars, "the two components have different review stars");
  assert.equal(apoe.stars, null);
  assert.equal(apoe.gnomad_af, null);
  assert.equal(apoe.clinvarUrl, null);
  assert.deepEqual(apoe.componentEvidence.map((c) => c.rsid), ["rs429358", "rs7412"]);
  assert.deepEqual(apoe.componentEvidence.map((c) => c.stars), [e4.clinvar.stars, e2.clinvar.stars]);
  assert.deepEqual(apoe.componentEvidence.map((c) => c.af), [e4.gnomad.af, e2.gnomad.af]);
  const url = (e) => `https://www.ncbi.nlm.nih.gov/clinvar/variation/${Number(e.clinvar.accession.replace(/\D/g, ""))}`;
  assert.deepEqual(apoe.clinvarLinks, [{ rsid: "rs429358", url: url(e4) }, { rsid: "rs7412", url: url(e2) }]);
  assert.equal(apoe.starsText, "rs429358: ★ · rs7412: ★★★");
  assert.match(apoe.afText, /^rs429358: \d+\.\d\d% · rs7412: \d+\.\d\d%$/);
  const round = (x) => Math.round(x * 1e6) / 1e6;
  const csv = parseCsv(csvReport([apoe], a.kb.genes))[0];
  assert.equal(csv.ClinVar_Stars, "1;3");
  assert.equal(csv.Gnomad_AF, `${round(e4.gnomad.af)};${round(e2.gnomad.af)}`);
  assert.equal(csv.Evidence_Tier, "Tier A;Tier A");
  const md = markdownReport(reportData(a));
  assert.ok(md.includes("★;★★★"), "Markdown ClinVar column joins the component values");
  // The tier is shown once when both components agree, and per component otherwise.
  assert.equal(apoe.tier, "Tier A");
  const split = structuredClone(apoe);
  split.components[1].evidence_tier = "Tier B";
  assert.equal(toViewModel(split, a.kb.genes).tier, "rs429358: Tier A · rs7412: Tier B");
  // A component whose accession is not machine imported has no link.
  const curated = structuredClone(apoe);
  curated.components[0].evidence.clinvar.provenance.curation_mode = "manually_curated";
  assert.deepEqual(toViewModel(curated, a.kb.genes).clinvarLinks.map((l) => l.rsid), ["rs7412"]);
  // A missing component figure is named in Missing_Fields.
  const noStars = structuredClone(apoe);
  noStars.components[1].evidence.clinvar.stars = null;
  const noStarsVm = toViewModel(noStars, a.kb.genes);
  assert.ok(noStarsVm.missing_fields.includes("clinvar_stars"));
  assert.equal(parseCsv(csvReport([noStarsVm], a.kb.genes))[0].ClinVar_Stars, "1;");
});

test("tier, stars and limitation are the same in the table model, drawer text, CSV and Markdown", () => {
  const a = analyse(DEMO);
  const csvRows = Object.fromEntries(parseCsv(csvReport(a.vms, a.kb.genes)).map((r) => [r.rsID, r]));
  const md = markdownReport(reportData(a, { records: a.vms, negativeChecks: [], arrayGaps: [], insufficientEvidence: [] }));
  const cyp = a.byRsid.rs4244285;
  assert.match(cyp.limitation, /star-allele/);
  assert.equal(csvRows.rs4244285.Evidence_Tier, cyp.tier);
  assert.equal(csvRows.rs4244285.ClinVar_Stars, String(cyp.stars));
  assert.equal(csvRows.rs4244285.Limitation, cyp.limitation);
  assert.ok(md.includes(cyp.tier) && md.includes(cyp.limitation), "Markdown carries the same tier and limitation");
  assert.equal(drawerTierText(cyp), `Evidence ${cyp.tier}`);
  for (const vm of a.vms.filter((v) => v.id !== a.apoe?.id)) {
    const row = csvRows[vm.exportId];
    assert.equal(row.Evidence_Tier, vm.tier ?? "", vm.id);
    assert.equal(row.Limitation, vm.limitation ?? "", vm.id);
    assert.equal(row.ClinVar_Stars, vm.stars === null ? "" : String(vm.stars), vm.id);
    assert.equal(row.Genotype, vm.genotype ?? "", vm.id);
  }
  // The same record always gives the same model.
  assert.deepEqual(toViewModel(a.byRsid.rs4244285, a.kb.genes), toViewModel(a.byRsid.rs4244285, a.kb.genes));
});

test("stars come exactly from the evidence, and ClinVar links only from a machine-imported accession", () => {
  const a = analyse(DEMO);
  const f5 = a.byRsid.rs6025;
  assert.equal(f5.starsText, "★".repeat(f5.stars));
  assert.match(f5.clinvarUrl, /^https:\/\/www\.ncbi\.nlm\.nih\.gov\/clinvar\/variation\/\d+$/);
  const curated = structuredClone(f5);
  curated.evidence.clinvar.provenance.curation_mode = "manually_curated";
  assert.equal(toViewModel(curated, a.kb.genes).clinvarUrl, null);
  const none = structuredClone(f5);
  none.evidence.clinvar.stars = 0;
  assert.equal(toViewModel(none, a.kb.genes).starsText, "0 stars");
});

test("not detected wording states the count, never 'Normal'", () => {
  const a = analyse(DEMO.replace(/^rs6025\t1\t169519049\tAG/m, "rs6025\t1\t169519049\tGG"));
  const f5 = a.byRsid.rs6025;
  assert.equal(f5.sample_observation, "wild_type");
  assert.equal(f5.statement, "rs6025 variant not detected (1 variant tested in F5)");
  const hfe = analyse(DEMO.replace(/^rs1800562\t6\t26093141\tAG/m, "rs1800562\t6\t26093141\tGG")).byRsid.rs1800562;
  assert.equal(hfe.statement, "rs1800562 variant not detected (2 variants tested in HFE)");
  // An array gap is not counted: with the other HFE locus not on the array, one variant was tested.
  const gapped = analyse(
    DEMO.replace(/^rs1800562\t6\t26093141\tAG/m, "rs1800562\t6\t26093141\tGG").replace(/^rs1799945[^\n]*\r?\n/m, "")
  );
  assert.equal(gapped.byRsid.rs1799945.coverage_state, "not_tested_by_array");
  assert.equal(gapped.byRsid.rs1800562.statement, "rs1800562 variant not detected (1 variant tested in HFE)");
  assert.ok(!/known/i.test(gapped.byRsid.rs1800562.statement));
  assert.ok(!/normal/i.test(f5.statement));
  const dpyd = analyse(DEMO.replace(/^rs3918290\t1\t97915614\tCT/m, "rs3918290\t1\t97915614\tCC")).byRsid.rs3918290;
  assert.match(dpyd.limitationTooltip, /Single-variant test/);
  const md = markdownReport(reportData(analyse(DEMO.replace(/^rs3918290\t1\t97915614\tCT/m, "rs3918290\t1\t97915614\tCC"))));
  assert.ok(md.includes(dpyd.statement) && md.includes(dpyd.limitation), "Markdown shows the not-detected result with its limitation");
});

test("the APOE row is one composite identity with both component positions, never APOE-STATUS", () => {
  const a = analyse(DEMO);
  const apoe = a.apoe;
  assert.equal(apoe.id, "APOE (rs429358 + rs7412)");
  assert.equal(apoe.exportId, "rs429358;rs7412");
  assert.deepEqual(apoe.positions.map((p) => p.pos), [45411941, 45412079]);
  assert.equal(apoe.positionText, "chr19:45,411,941 (rs429358) · chr19:45,412,079 (rs7412)");
  const csv = parseCsv(csvReport([apoe], a.kb.genes))[0];
  assert.equal(csv.rsID, "rs429358;rs7412");
  assert.equal(csv.Position, "45411941;45412079");
  const md = markdownReport(reportData(a));
  assert.ok(md.includes("rs429358;rs7412") && md.includes("chr19:45411941;chr19:45412079"));
  for (const text of [...displayStrings(apoe), csvReport([apoe], a.kb.genes), md]) assert.ok(!text.includes("APOE-STATUS"));
  // One formatter: the card uses core/apoe.js displayDiplotype.
  assert.equal(apoeCardModel(apoe).title, "APOE ε4/ε4");
});

test("CSV and Markdown serialisers write the same values for the same records", () => {
  const a = analyse(DEMO);
  const md = markdownReport(reportData(a));
  const csv = parseCsv(csvReport(a.vms, a.kb.genes));
  assert.equal(csv.length, a.vms.length);
  for (const row of csv) {
    const vm = a.vms.find((v) => v.exportId === row.rsID);
    for (const value of [row.Evidence_Tier, row.Genotype, vm.coordinates].filter(Boolean)) {
      assert.ok(md.includes(value), `${row.rsID}: "${value}" is in the CSV but not the Markdown`);
    }
  }
  for (const text of [md, csvReport(a.vms, a.kb.genes)]) for (const bad of PLACEHOLDERS) assert.ok(!text.includes(bad), bad);
});

test("escapeHtml makes markup payloads inert, and a record carrying one stays inert through the view model", () => {
  const payload = "<img src=x onerror=alert(1)>";
  assert.equal(escapeHtml(payload), "&lt;img src=x onerror=alert(1)&gt;");
  assert.equal(escapeHtml(`"'&`), "&quot;&#39;&amp;");
  assert.equal(escapeHtml(null), "");
  const a = analyse(DEMO);
  const rec = structuredClone(a.byRsid.rs6025);
  rec.gene = payload;
  rec.rsid = payload;
  rec.interpretation.caveats = [payload];
  const vm = toViewModel(rec, a.kb.genes);
  for (const text of [vm.id, vm.gene, ...vm.caveats, vm.limitationTooltip ?? ""]) {
    const html = `<li>${escapeHtml(text)}</li>`;
    assert.ok(!html.includes("<img"), html);
  }
  assert.ok(vm.caveats.includes(payload), "the model keeps the raw text; the view escapes it");
});

test("the KB badge text and title come from the manifest, with no source versions", () => {
  const badge = kbBadge({ release: "2026.10.02", sha256: "b79e6a67bb68c33f43e844dea9af2a3961f5fa3c448cccf98433933be74d2d83", locus_count: 14, gene_count: 12 });
  assert.equal(badge.text, "KB 2026.10.02 · Offline");
  assert.equal(badge.title, "Knowledge base release 2026.10.02 · sha256 b79e6a67bb68 · 14 loci in 12 genes");
  for (const bad of ["ClinVar", "dbSNP", "2024-06"]) assert.ok(!badge.text.includes(bad) && !badge.title.includes(bad), bad);
  assert.match(kbBadge({}).text, /Not available/);
});

test("the partner model is stated in words", () => {
  const unscreened = partnerModelNote("unscreened", 0.25);
  assert.match(unscreened, /gnomAD allele frequency \(25%\)/);
  assert.match(unscreened, /Hardy-Weinberg/);
  assert.match(partnerModelNote("unscreened", null), /No gnomAD allele frequency/);
  assert.match(partnerModelNote("heterozygous", 0.1), /heterozygous/);
  assert.throws(() => partnerModelNote("carrier", 0.1), /unknown partner model/);
});
