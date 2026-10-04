import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { validateKb } from "../src/core/kb.js";
import { parseGenotypeFile } from "../src/core/parse.js";
import { classify } from "../src/core/classify.js";
import { assembleFindings } from "../src/core/apoe.js";
import { describeSegregation, detectCompoundHeterozygosity, detectMultiLocus } from "../src/core/inheritance.js";
import {
  NOT_AVAILABLE,
  APOE_FIGURES_NOTE,
  MODEL_LABELS,
  NO_CLINVAR_STATUS,
  REPORT_GROUPS,
  RESULT_WORDS,
  apoeCardModel,
  csvReport,
  drawerTierText,
  escapeHtml,
  foundCategoryCounts,
  groupIdForModel,
  groupedReport,
  karyogramStateLabels,
  kbBadge,
  markdownReport,
  partnerModelNote,
  rowsByState,
  summaryProse,
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
  "id", "exportId", "genotype", "positionText", "coordinates", "chromosomes", "positionExport", "stateLabel",
  "stateHelp", "tier", "category", "significance", "significanceValue", "phenotype", "statement", "magnitudeText",
  "starsText", "clinvarUrl", "afText", "limitation", "limitationTooltip", "modelLabel",
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

test("the drawer shows the imported AlphaMissense, LOEUF and transcript; no curated value can win", () => {
  const { vms, kb } = analyse(DEMO);
  const rec = structuredClone(vms.find((v) => v.id === "rs1801133"));
  rec.evidence.vep = { ...rec.evidence.vep, alphamissense_class: "likely_pathogenic", alphamissense_score: 0.6324,
    mane_select_ensembl: "ENST00000376590" };
  rec.evidence.gnomad = { ...rec.evidence.gnomad, loeuf: 1.19 };
  const curated = { alphamissense_class: "likely_benign", alphamissense_pathogenicity: 0.215, loeuf: 0.44,
    canonical_transcript: "ENST00000376585 (MANE Select)" };
  const genes = { ...kb.genes, MTHFR: { ...kb.genes.MTHFR, insights: { ...kb.genes.MTHFR.insights, ensembl: curated } } };
  const vm = toViewModel(rec, genes);
  assert.equal(vm.biotools.alphamissense, "likely_pathogenic (0.63)");
  assert.equal(vm.biotools.transcript, "ENST00000376590");
  assert.equal(vm.biotools.constraint, "gnomAD LOEUF 1.19");

  const bare = structuredClone(rec);
  bare.evidence.vep = null;
  bare.evidence.gnomad = { af: 0.3 };
  const none = toViewModel(bare, genes);
  assert.equal(none.biotools.alphamissense, null);
  assert.equal(none.biotools.transcript, null);
  assert.equal(none.biotools.constraint, null);
});

test("a not-tested record has no undefined, null or NaN in any field, and shows its state label and reason", () => {
  const { vms, kb } = analyse(DEMO.replace(/^rs6025[^\n]*\r?\n/m, ""));
  const gap = vms.find((v) => v.id === "rs6025");
  assert.equal(gap.coverage_state, "not_tested_by_array");
  assert.equal(gap.significance, "Not on your chip");
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
  assert.equal(apoe.starsText, "rs429358: 1 of 4 review stars · rs7412: 3 of 4 review stars");
  assert.match(apoe.afText, /^rs429358: \d+\.\d\d% · rs7412: \d+\.\d\d%$/);
  const round = (x) => Math.round(x * 1e6) / 1e6;
  const csv = parseCsv(csvReport([apoe], a.kb.genes))[0];
  assert.equal(csv.ClinVar_Stars, "1;3");
  assert.equal(csv.Gnomad_AF, `${round(e4.gnomad.af)};${round(e2.gnomad.af)}`);
  assert.equal(csv.Evidence_Tier, "Tier A;Tier A");
  const md = markdownReport(reportData(a));
  assert.equal(md.split("\n")[0], "# Lucidase variome clinical report");
  assert.ok(md.includes("1 of 4 review stars;3 of 4 review stars"), "Markdown ClinVar column joins the component values");
  // The tier is shown once when both components agree, and per component otherwise.
  assert.equal(apoe.tier, "Tier A");
  const split = structuredClone(apoe);
  split.components[1].evidence_tier = "Tier B";
  assert.equal(toViewModel(split, a.kb.genes).tier, "rs429358: Tier A · rs7412: Tier B");
  // The Inspector footer says the same in sentence case: once when the components agree, per marker otherwise.
  assert.equal(drawerTierText(apoe), "Evidence tier A");
  assert.equal(drawerTierText(toViewModel(split, a.kb.genes)), "Evidence tier: rs429358 A · rs7412 B");
  const halfTier = structuredClone(apoe);
  halfTier.components[1].evidence_tier = null;
  assert.equal(drawerTierText(toViewModel(halfTier, a.kb.genes)), `Evidence tier: rs429358 A · rs7412 ${NOT_AVAILABLE}`);
  // The Inspector names the markers once, without the gene the subtitle already starts with.
  assert.equal(apoe.markerText, "rs429358 + rs7412");
  assert.equal(a.byRsid.rs4244285.markerText, "rs4244285");
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
  // The footer is a sentence-case phrase around the KB tier's letter ("Tier A" reads "Evidence tier A").
  assert.equal(cyp.tier, "Tier A");
  assert.equal(drawerTierText(cyp), "Evidence tier A");
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
  assert.equal(f5.starsText, `${f5.stars} of 4 review stars`);
  assert.match(f5.clinvarUrl, /^https:\/\/www\.ncbi\.nlm\.nih\.gov\/clinvar\/variation\/\d+$/);
  const curated = structuredClone(f5);
  curated.evidence.clinvar.provenance.curation_mode = "manually_curated";
  assert.equal(toViewModel(curated, a.kb.genes).clinvarUrl, null);
  const none = structuredClone(f5);
  none.evidence.clinvar.stars = 0;
  assert.equal(toViewModel(none, a.kb.genes).starsText, "0 of 4 review stars");
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

test("the other parent's model is stated in words, calling them the other parent", () => {
  assert.equal(
    partnerModelNote("unscreened", 0.25),
    "Other parent: unscreened. The chance they pass on the variant allele is taken as the gnomAD allele frequency (25%), under Hardy-Weinberg equilibrium."
  );
  assert.equal(
    partnerModelNote("unscreened", null),
    `Other parent: unscreened. No gnomAD allele frequency is available for this variant, so the figures are ${NOT_AVAILABLE.toLowerCase()}.`
  );
  assert.equal(partnerModelNote("heterozygous", 0.1), "Other parent: one copy (heterozygous). They pass on the variant allele with probability 0.5.");
  assert.equal(partnerModelNote("homozygous", 0.1), "Other parent: two copies (homozygous). They pass on the variant allele with probability 1.");
  assert.equal(partnerModelNote("wildtype", 0.1), "Other parent: no variant (wild-type). They pass on no variant allele.");
  assert.throws(() => partnerModelNote("carrier", 0.1), /unknown partner model/);
});

/** The Markdown table under a "## <heading>" line as rows keyed by rsID, with `\|` read as a literal pipe. */
function markdownRows(md, heading) {
  const lines = md.split("\n");
  const start = lines.findIndex((l) => l === `## ${heading}`);
  assert.ok(start >= 0, `no section "${heading}"`);
  const cells = (line) =>
    line.replace(/^\| /, "").replace(/ \|$/, "").split(/ \| /).map((c) => c.replace(/\\\|/g, "|"));
  const table = [];
  let i = start + 1;
  while (i < lines.length && !lines[i].startsWith("|") && !lines[i].startsWith("## ")) i++;
  for (; i < lines.length && lines[i].startsWith("|"); i++) table.push(lines[i]);
  const [header, , ...body] = table.map(cells);
  return Object.fromEntries(body.map((r) => [r[0], Object.fromEntries(header.map((h, i) => [h, r[i]]))]));
}

test("a hostile genotype is neutralised in the CSV and the Markdown", () => {
  const a = analyse(DEMO);
  for (const hostile of ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx", "  =1+1"]) {
    const rec = structuredClone(a.byRsid.rs6025);
    rec.genotype_display = hostile;
    const vm = toViewModel(rec, a.kb.genes);
    const cell = parseCsv(csvReport([vm], a.kb.genes))[0].Genotype;
    assert.equal(cell, `'${hostile}`, JSON.stringify(hostile));
  }
  const plain = toViewModel(a.byRsid.rs6025, a.kb.genes);
  assert.equal(parseCsv(csvReport([plain], a.kb.genes))[0].Genotype, plain.genotype, "a normal genotype is untouched");

  const rec = structuredClone(a.byRsid.rs6025);
  rec.genotype_display = "<DEL>/a|b&c";
  const md = markdownReport(reportData(a, { records: [toViewModel(rec, a.kb.genes)], negativeChecks: [], arrayGaps: [], insufficientEvidence: [] }));
  const row = md.split("\n").find((l) => l.startsWith("| rs6025 "));
  assert.ok(row.includes("&lt;DEL&gt;/a\\|b&amp;c"), row);
  assert.ok(!row.includes("<DEL>"), row);
  assert.equal(markdownRows(md, "Found").rs6025.Genotype, "&lt;DEL&gt;/a|b&amp;c", "the pipe did not move any cell");
});

test("a backslash before a pipe is escaped too, so it cannot cancel the pipe's escape (S2-F1 Minor)", () => {
  const a = analyse(DEMO);
  const rec = structuredClone(a.byRsid.rs6025);
  rec.genotype_display = "a\\|b";
  const md = markdownReport(reportData(a, { records: [toViewModel(rec, a.kb.genes)], negativeChecks: [], arrayGaps: [], insufficientEvidence: [] }));
  const row = md.split("\n").find((l) => l.startsWith("| rs6025 "));
  assert.ok(row.includes("a\\\\\\|b"), row);
});

test("the tested-variant count leaves out a sibling locus whose genotype is not interpretable", () => {
  // rs1799945 TT is neither ref/alt nor a strand flip of them: insufficient evidence, no altCount.
  const a = analyse(
    DEMO.replace(/^rs1800562\t6\t26093141\tAG/m, "rs1800562\t6\t26093141\tGG").replace(/^rs1799945\t6\t26092913\tCG/m, "rs1799945\t6\t26092913\tTT")
  );
  assert.equal(a.byRsid.rs1799945.coverage_state, "insufficient_evidence");
  assert.equal(a.byRsid.rs1800562.statement, "rs1800562 variant not detected (1 variant tested in HFE)");
});

test("the constraint line is the numeric gnomAD LOEUF value with no curated band", () => {
  const a = analyse(DEMO);
  const shown = [...a.vms, a.apoe].map((v) => v.biotools.constraint).filter((c) => c !== null);
  assert.ok(shown.length > 0, "the demo shows at least one LOEUF value");
  for (const text of shown) {
    assert.match(text, /^gnomAD LOEUF \d+\.\d\d$/);
    for (const band of ["Constrained", "Tolerant"]) assert.ok(!text.includes(band), text);
  }
});

test("Markdown rows match the CSV rows per record: tier, stars, limitation, genotype", () => {
  const a = analyse(DEMO);
  const all = a.vms.some((v) => v.id === a.apoe.id) ? a.vms : [...a.vms, a.apoe];
  const md = markdownReport(reportData(a, { records: all, negativeChecks: [], arrayGaps: [], insufficientEvidence: [] }));
  const csv = parseCsv(csvReport(all, a.kb.genes));
  const starsText = (n) => (n === "" ? NO_CLINVAR_STATUS : `${Number(n)} of 4 review stars`);
  // Each record is in the section of its own result word; the demo has Found, Not found and Unclear records.
  const compare = (mdText) => {
    const rows = Object.assign({}, ...["Found", "Not found", "Unclear"].map((word) => markdownRows(mdText, word)));
    assert.equal(Object.keys(rows).length, csv.length);
    for (const c of csv) {
      const r = rows[c.rsID];
      assert.ok(r, `${c.rsID} is missing from the Markdown: ${Object.keys(rows)}`);
      assert.equal(r.Tier, c.Evidence_Tier, `${c.rsID} tier`);
      // The Not found table has no ClinVar column.
      if (c.Result !== "Not found") assert.equal(r.ClinVar, c.ClinVar_Stars.split(";").map(starsText).join(";"), `${c.rsID} stars`);
      assert.ok(r.Limitation.startsWith(c.Limitation), `${c.rsID} limitation`);
      assert.equal(r.Genotype, c.Genotype, `${c.rsID} genotype`);
    }
  };
  compare(md);
  // Dropping one record's tier from the Markdown must be caught.
  const dropped = md
    .split("\n")
    .map((l) => (l.startsWith("| rs6025 ") ? l.replace(/ \| Tier [A-D] \| /, " |  | ") : l))
    .join("\n");
  assert.notEqual(dropped, md);
  assert.throws(() => compare(dropped), /rs6025 tier/);
});

test("the APOE figures are labelled as curated and unverified on the card and in both exports", () => {
  const a = analyse(DEMO);
  const card = apoeCardModel(a.apoe);
  assert.equal(card.resolved, true);
  assert.equal(APOE_FIGURES_NOTE, "manually curated; source citation pending verification");
  for (const text of [card.riskBadge, card.lifetime, card.description]) assert.ok(text.includes(APOE_FIGURES_NOTE), text);
  const md = markdownReport(reportData(a));
  for (const label of ["Risk ratio", "Estimated lifetime risk", "Clinical guidance"]) {
    const line = md.split("\n").find((l) => l.startsWith(`- **${label}**`));
    assert.ok(line.includes(APOE_FIGURES_NOTE), line);
  }
  const csv = parseCsv(csvReport([a.apoe], a.kb.genes))[0];
  assert.ok(csv.Condition_Phenotype.includes(APOE_FIGURES_NOTE));
  assert.ok(csv.Caveats.includes(APOE_FIGURES_NOTE));
});

test("the APOE phenotype wording states 12-15x as a relative figure, not a lifetime risk", () => {
  // The curation source; the landing rebuilds the KB from it, and kb-verify pins the two together.
  const e44 = JSON.parse(readText("../../tools/curation/kb_curation.json")).genes.APOE.diplotypes["e4/e4"];
  assert.match(e44.phenotype, /relative risk/i);
  assert.match(e44.phenotype, /ε3\/ε3/);
  assert.ok(!/increased lifetime risk/.test(e44.phenotype));
  assert.ok(e44.phenotype.includes("12–15×"), "the numbers are unchanged");
});

/** The APOE row as the view model sees it for a given diplotype (the raw record's diplotype and KB interpretation replaced). */
function apoeWith(diplotype) {
  const kb = validateKb(structuredClone(KB_JSON));
  const { records, summary } = classify(parseGenotypeFile(DEMO, "x.txt"), kb);
  const { apoe } = assembleFindings(records, kb, summary.outside_coverage_count);
  const kbInterp = kb.genes.APOE.diplotypes[diplotype];
  const interpretation = kbInterp ? { ...kbInterp, caveats: [] } : null;
  return toViewModel({ ...apoe, diplotype, interpretation }, kb.genes, {});
}

test("the Risk filter flag is Risk Factor OR an e3/e4 or e4/e4 APOE diplotype", () => {
  for (const [diplotype, want] of [["e3/e4", true], ["e4/e4", true], ["e3/e3", false], ["e2/e3", false], ["atypical", false], [null, false]]) {
    assert.equal(apoeWith(diplotype).riskFilter, want, `APOE ${diplotype}`);
  }
  // The diplotype rule stands on its own: it does not rely on the KB category being "Risk Factor".
  const e4e4 = apoeWith("e4/e4");
  const uncategorised = toViewModel({ ...e4e4, components: e4e4.components, interpretation: { ...e4e4.interpretation, category: "Carrier" } }, {}, {});
  assert.equal(uncategorised.riskFilter, true);
  const a = analyse(DEMO);
  const riskFactor = a.vms.filter((v) => v.category === "Risk Factor");
  assert.ok(riskFactor.length > 0, "the demo has Risk Factor rows");
  assert.ok(riskFactor.every((v) => v.riskFilter === true));
  const others = a.vms.filter((v) => v.category !== "Risk Factor");
  assert.ok(others.length > 0 && others.every((v) => v.riskFilter === false));
});

test("PENDING OWNER DECISION: an e2/e4 APOE row is not under Risk Factors today", () => {
  // Whether e2/e4 belongs in the Risk filter is an owner decision still open; this pins the current answer.
  assert.equal(apoeWith("e2/e4").riskFilter, false);
  assert.equal(apoeWith("e2/e4").apoeE4Accent, true, "the card still carries the e4 accent");
});

test("the APOE e4 accent flag and the card's accent key follow the diplotype", () => {
  const cases = [["e4/e4", "e4e4", true], ["e3/e4", "e4", true], ["e2/e4", "e4", true], ["e2/e3", "e2", false], ["e3/e3", "e3e3", false]];
  for (const [diplotype, accent, e4] of cases) {
    const vm = apoeWith(diplotype);
    assert.equal(apoeCardModel(vm).accent, accent, `card accent ${diplotype}`);
    assert.equal(vm.apoeE4Accent, e4, `e4 flag ${diplotype}`);
  }
  for (const diplotype of ["atypical", null]) {
    assert.equal(apoeCardModel(apoeWith(diplotype)).accent, null, `no accent for ${diplotype}`);
    assert.equal(apoeWith(diplotype).apoeE4Accent, false);
  }
});

// The design system's plain result words and their one-line help (components/core/hooks.js stateMeta and stateHelp),
// copied verbatim. The data keys never change; only the words a person reads do.
const DS_RESULT_WORDS = {
  supported_and_observed: ["Found", "Your file has the variant this check looks for."],
  supported_not_observed: [
    "Not found",
    "Your file was checked here and the variant was not found among the variants tested. This is not the same as 'normal'.",
  ],
  not_tested_by_array: ["Not on your chip", "Your DNA chip did not read this position, or the reading failed. No result."],
  outside_coverage: ["Not checked", "Markers in your file that Lucidase does not interpret. Counted only."],
  insufficient_evidence: [
    "Unclear",
    "A reading exists, but the evidence or the genotype is not clear enough to report a result.",
  ],
};
const OLD_STATE_WORDS = [
  /State \d/, /Supported/, /Observed/, /Tested WT/, /Wild-Type/, /Array Gap/, /Microarray/, /Conflicting Evidence/,
  /Taxonomy/, /★/, /☆/,
];

/** A file that gives every per-locus state: the demo with rs6025 dropped (gap) and rs1799945 unreadable (unclear). */
const ALL_STATES_FILE = DEMO.replace(/^rs6025[^\n]*\r?\n/m, "")
  .replace(/^rs1800562\t6\t26093141\tAG/m, "rs1800562\t6\t26093141\tGG")
  .replace(/^rs1799945\t6\t26092913\tCG/m, "rs1799945\t6\t26092913\tTT");

test("each coverage state reads as the design system's plain word with its one-line help", () => {
  for (const [state, [label, help]] of Object.entries(DS_RESULT_WORDS)) {
    assert.deepEqual(RESULT_WORDS[state], { label, help }, state);
  }
  assert.deepEqual(Object.keys(RESULT_WORDS), Object.keys(DS_RESULT_WORDS), "the design system's state order");
  const a = analyse(ALL_STATES_FILE);
  const seen = new Set();
  for (const vm of [...a.vms, a.apoe]) {
    const [label, help] = DS_RESULT_WORDS[vm.coverage_state];
    assert.equal(vm.stateLabel, label, vm.id);
    assert.equal(vm.stateHelp, help, vm.id);
    assert.equal(vm.stateBadge, undefined, "one word per state: the badge and the label are the same field");
    for (const text of displayStrings(vm)) for (const old of OLD_STATE_WORDS) assert.ok(!old.test(text), `${old} in "${text}"`);
    seen.add(vm.coverage_state);
  }
  assert.deepEqual([...seen].sort(), ["insufficient_evidence", "not_tested_by_array", "supported_and_observed", "supported_not_observed"]);
  assert.throws(() => toViewModel({ ...a.byRsid.rs6025, coverage_state: "outside_coverage" }, a.kb.genes), /coverage state/);
  // The karyogram reuses the same words; its reference marker keeps its own label.
  const labels = karyogramStateLabels();
  for (const state of ["supported_and_observed", "supported_not_observed", "not_tested_by_array", "insufficient_evidence"]) {
    assert.equal(labels[state], DS_RESULT_WORDS[state][0], state);
  }
});

test("the APOE card states its result in the same plain words", () => {
  const a = analyse(DEMO);
  assert.equal(apoeCardModel(a.apoe).stateLabel, "Found");
  const sparse = analyse(DEMO.replace(/^rs7412[^\n]*\r?\n/m, ""));
  const card = apoeCardModel(sparse.apoe);
  assert.equal(sparse.apoe.coverage_state, "not_tested_by_array");
  assert.equal(card.stateLabel, "Not on your chip");
  assert.equal(card.pill, "Not on your chip");
});

test("the Markdown report uses the plain words, keeps the help and the absence statement, and has no state codes", () => {
  const a = analyse(ALL_STATES_FILE);
  const coverage = {
    supported_and_observed_count: 7, supported_not_observed_count: 3, not_tested_by_array_count: 2,
    outside_coverage_count: 600000, insufficient_evidence_count: 1,
  };
  const md = markdownReport(reportData(a, { coverage }));
  for (const old of OLD_STATE_WORDS) assert.ok(!old.test(md), `${old} is still in the Markdown`);
  // Every heading is sentence case: no capital after the first word, other than gene symbols and APOE.
  for (const heading of md.split("\n").filter((l) => l.startsWith("#"))) {
    const words = heading.replace(/^#+ /, "").split(" ").slice(1);
    for (const w of words) assert.ok(!/^[A-Z][a-z]/.test(w), `"${w}" in "${heading}" is not sentence case`);
  }
  const summary = md.split("\n## Results of the checks\n")[1].split("\n## ")[0];
  const counts = [7, 3, 2, 600000, 1];
  Object.values(DS_RESULT_WORDS).forEach(([label, help], i) => {
    assert.ok(summary.includes(`- **${label}**: ${counts[i].toLocaleString("en-US")}. ${help}`), `${label} summary line`);
  });
  for (const [state, [label, help]] of Object.entries(DS_RESULT_WORDS)) {
    if (state === "outside_coverage") continue;
    const section = md.split(`\n## ${label}\n`)[1];
    assert.ok(section, `no "## ${label}" section`);
    assert.ok(section.trimStart().startsWith(help), `${label} section opens with its help`);
    const rows = Object.values(markdownRows(md, label));
    assert.ok(rows.some((row) => row.Result === label), label);
    // A section named by a result word holds only checks with that word, though the worker lists an unclear check
    // with the variant-present or wild-type ones too.
    for (const row of rows) assert.equal(row.Result, label, `${label} row: ${row.Result}`);
  }
  assert.ok(md.includes("This is not the same as 'normal'."), "absence of a finding is not absence of risk");
  assert.ok(md.includes("guardrail text"), "the scope guardrail still opens the report");
});

test("the CSV keeps the machine state key and adds the plain result word", () => {
  const a = analyse(ALL_STATES_FILE);
  const rows = parseCsv(csvReport([...a.vms, a.apoe], a.kb.genes));
  const header = csvReport([], a.kb.genes).split("\r\n")[0].split(",");
  assert.equal(header[header.indexOf("Coverage_State") + 1], "Result", "Result sits next to Coverage_State");
  for (const row of rows) {
    assert.ok(Object.hasOwn(DS_RESULT_WORDS, row.Coverage_State), row.Coverage_State);
    assert.equal(row.Result, DS_RESULT_WORDS[row.Coverage_State][0], row.rsID);
  }
  const text = csvReport([...a.vms, a.apoe], a.kb.genes);
  for (const old of OLD_STATE_WORDS) assert.ok(!old.test(text), `${old} is still in the CSV`);
});

test("ClinVar review stars are words, never star glyphs, everywhere", () => {
  const a = analyse(DEMO);
  for (const vm of [...a.vms, a.apoe]) {
    for (const p of vm.componentEvidence ?? [vm]) {
      if (p.stars === null) continue;
      const text = `${p.stars} of 4 review stars`;
      assert.ok((vm.componentEvidence ? vm.starsText.includes(`${p.rsid}: ${text}`) : vm.starsText === text), vm.id);
    }
    assert.equal(vm.starsDetail, undefined, "the drawer shows the same words as the table");
  }
  const one = structuredClone(a.byRsid.rs6025);
  one.evidence.clinvar.stars = 1;
  assert.equal(toViewModel(one, a.kb.genes).starsText, "1 of 4 review stars");
  const none = structuredClone(a.byRsid.rs6025);
  none.evidence.clinvar.stars = null;
  assert.equal(toViewModel(none, a.kb.genes).starsText, NO_CLINVAR_STATUS);
  const md = markdownReport(reportData(a));
  const csv = csvReport(a.vms, a.kb.genes);
  for (const text of [md, csv, ...a.vms.flatMap(displayStrings)]) assert.ok(!/[★☆]/.test(text), text.slice(0, 80));
});

test("inheritance model labels are sentence case", () => {
  assert.deepEqual(MODEL_LABELS, {
    autosomal_recessive: "Autosomal recessive",
    autosomal_dominant: "Autosomal dominant",
    risk_factor: "Risk factor (allele transmission)",
    pharmacogenomic: "Pharmacogenomic (allele transmission)",
    trait: "Trait (allele transmission)",
  });
  const a = analyse(DEMO);
  const csv = parseCsv(csvReport(a.vms, a.kb.genes));
  assert.ok(csv.some((r) => r.Inheritance_Mode === "Autosomal recessive"));
});

test("the report groups are the design system's, in its order, and every KB gene belongs to one", () => {
  // ui_kits/web/meta.js LDS_GROUPS, verbatim.
  assert.deepEqual(REPORT_GROUPS, [
    { id: "medicines", title: "Pharmacology", aside: "How your genes may affect the way some drugs work in your body. Talk to a doctor or pharmacist before changing any medicine." },
    { id: "risk", title: "Health risk factors", aside: "Variants linked to a higher chance of a condition. A risk factor is not a diagnosis." },
    { id: "carrier", title: "Carrier status", aside: "Variants that usually cause no symptoms with one copy, but can be passed on to children." },
    { id: "traits", title: "Traits", aside: "Everyday traits. These have little or no medical use." },
  ]);
  assert.equal(groupIdForModel("pharmacogenomic"), "medicines");
  assert.equal(groupIdForModel("risk_factor"), "risk");
  assert.equal(groupIdForModel("autosomal_recessive"), "carrier");
  assert.equal(groupIdForModel("trait"), "traits");
  for (const other of ["autosomal_dominant", "unknown", "toString", "", null, undefined]) assert.equal(groupIdForModel(other), null, String(other));
  // Fail fast: a model added to the KB without a group breaks this test.
  const ids = new Set(REPORT_GROUPS.map((g) => g.id));
  for (const [gene, entry] of Object.entries(KB_JSON.genes)) {
    assert.ok(ids.has(groupIdForModel(entry.inheritance.model)), `${gene} (${entry.inheritance.model}) has no report group`);
  }
  assert.throws(() => { REPORT_GROUPS.push({}); }, TypeError);
  assert.throws(() => { REPORT_GROUPS[0].title = "x"; }, TypeError);
});

test("the page's summary legend takes the view model's words and help (no second copy can drift)", () => {
  // The legend is rendered by app.js from RESULT_WORDS (tests/e2e/test_summary_map.py reads it on the page), so the
  // page carries an empty list and no copy of the help. Positive control: the same strings are in view-model.js.
  const html = readText("../index.html");
  const source = readText("../src/view-model.js");
  assert.match(html, /<ul id="summary-legend"[^>]*><\/ul>/);
  for (const [state, { help }] of Object.entries(RESULT_WORDS)) {
    assert.ok(source.includes(help), `${state}: the help is not in view-model.js`);
    assert.ok(!html.includes(help), `${state}: index.html carries a second copy of the help`);
  }
  assert.match(readText("../src/app.js"), /RESULT_WORDS\[s\]\.help/);
});

// ---------------------------------------------------------------------------------------------------------------
// The grouped report (design system ui_kits/web/AnalysisScreen.jsx): one ReportSection per REPORT_GROUPS group,
// holding one FindingRow per interpreted check.

/** Every interpreted check, in the overlapping lists the worker sends (an unclear record is in two lists). */
const workerLists = (a) => [
  ...a.vms.filter((vm) => vm.coverage_state === "supported_and_observed" || vm.sample_observation === "variant_present"),
  ...a.vms.filter((vm) => vm.sample_observation === "wild_type"),
  ...a.vms.filter((vm) => vm.coverage_state === "not_tested_by_array"),
  ...a.vms.filter((vm) => vm.coverage_state === "insufficient_evidence"),
];
const reportRows = (report) => report.flatMap((group) => group.rows.map((row) => ({ group: group.id, ...row })));

test("the grouped report has the four design-system groups in order, with their titles and asides", () => {
  const a = analyse(DEMO);
  const report = groupedReport(workerLists(a), a.kb.genes);
  assert.deepEqual(
    report.map(({ id, title, aside }) => ({ id, title, aside })),
    REPORT_GROUPS.map(({ id, title, aside }) => ({ id, title, aside }))
  );
});

test("every interpreted check is in the grouped report exactly once, in all four per-locus states", () => {
  const a = analyse(ALL_STATES_FILE);
  const lists = workerLists(a);
  assert.ok(lists.length > a.vms.length, "the worker's lists overlap, so the report must not repeat a check");
  const rows = reportRows(groupedReport(lists, a.kb.genes));
  assert.deepEqual(rows.map((r) => r.id).sort(), a.vms.map((vm) => vm.id).sort());
  assert.equal(new Set(rows.map((r) => r.id)).size, rows.length);
  assert.deepEqual(
    [...new Set(rows.map((r) => r.state))].sort(),
    ["insufficient_evidence", "not_tested_by_array", "supported_and_observed", "supported_not_observed"]
  );
});

test("APOE is one composite row in the grouped report, never its two component loci", () => {
  const a = analyse(DEMO);
  const components = a.apoe.components.map((c) => toViewModel(c, a.kb.genes));
  const rows = reportRows(groupedReport([...workerLists(a), ...components], a.kb.genes));
  const apoe = rows.filter((r) => r.gene === "APOE");
  assert.equal(apoe.length, 1);
  assert.equal(apoe[0].id, a.apoe.id);
  assert.equal(apoe[0].record.components.length, 2);
  assert.equal(apoe[0].technical, "rs429358 · C/C + rs7412 · C/C");
  assert.equal(apoe[0].markers, "rs429358 and rs7412");
  for (const rsid of ["rs429358", "rs7412"]) assert.ok(!rows.some((r) => r.id === rsid), rsid);
});

test("markers outside coverage are never in the grouped report", () => {
  const a = analyse(DEMO);
  const outside = { ...a.byRsid.rs6025, id: "rs1234567", rsid: "rs1234567", coverage_state: "outside_coverage" };
  const rows = reportRows(groupedReport([...workerLists(a), outside], a.kb.genes));
  assert.ok(!rows.some((r) => r.id === "rs1234567" || r.state === "outside_coverage"));
  assert.equal(rows.length, a.vms.length);
});

test("a check's group follows its gene's KB inheritance model; a model with no group fails loudly", () => {
  const a = analyse(DEMO);
  for (const row of reportRows(groupedReport(workerLists(a), a.kb.genes))) {
    assert.equal(row.group, groupIdForModel(a.kb.genes[row.gene].inheritance.model), row.id);
  }
  // Move MTHFR to the pharmacogenomic model in the KB: its row moves to Pharmacology.
  const moved = analyse(DEMO, (kb) => {
    kb.genes.MTHFR.inheritance.model = "pharmacogenomic";
    return kb;
  });
  const movedRows = reportRows(groupedReport(workerLists(moved), moved.kb.genes));
  assert.equal(movedRows.find((r) => r.gene === "MTHFR").group, "medicines");
  const genes = structuredClone(a.kb.genes);
  genes.MTHFR.inheritance.model = "autosomal_dominant";
  assert.throws(() => groupedReport(workerLists(a), genes), /MTHFR/);
});

test("a group with no check in this KB is still listed, with no rows", () => {
  const a = analyse(DEMO, (kb) => {
    for (const gene of Object.values(kb.genes)) if (gene.inheritance.model === "trait") gene.inheritance.model = "risk_factor";
    return kb;
  });
  const report = groupedReport(workerLists(a), a.kb.genes);
  assert.deepEqual(report.map((g) => g.id), REPORT_GROUPS.map((g) => g.id));
  assert.deepEqual(report.find((g) => g.id === "traits").rows, []);
});

test("each finding row carries the topic, the plain word, the statement, the limitation and the technical line", () => {
  const a = analyse(ALL_STATES_FILE);
  const rows = reportRows(groupedReport(workerLists(a), a.kb.genes));
  for (const row of rows) {
    const vm = a.vms.find((v) => v.id === row.id);
    assert.equal(row.record, vm, row.id);
    assert.equal(row.topic, a.kb.genes[row.gene].topic, row.id);
    assert.equal(row.gene, vm.gene);
    assert.equal(row.state, vm.coverage_state);
    assert.equal(row.stateLabel, RESULT_WORDS[vm.coverage_state].label);
    assert.equal(row.statement, vm.statement ?? vm.phenotype ?? vm.significance);
    assert.equal(row.limitation, vm.limitation);
    assert.deepEqual(row.caveats, vm.caveats);
    assert.match(row.key, /^[A-Za-z0-9-]+$/, "the key is safe in an element id");
  }
  assert.equal(new Set(rows.map((r) => r.key)).size, rows.length);
  const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
  assert.equal(byId.rs4244285.technical, `rs4244285 · ${a.byRsid.rs4244285.genotype}`);
  assert.ok(byId.rs4244285.limitation.length > 0, "the CYP2C19 star-allele limitation travels with its row");
  // A gap has no genotype: the technical line says so in words.
  assert.equal(byId.rs6025.state, "not_tested_by_array");
  assert.equal(byId.rs6025.technical, "rs6025 · No reading");
  assert.equal(byId.rs6025.stateLabel, "Not on your chip");
  assert.equal(byId.rs1799945.stateLabel, "Unclear");
  // The wild-type statement keeps its count, never "normal".
  assert.match(byId.rs671.statement, /not detected \(1 variant tested in ALDH2\)/);
  // HFE: two loci share one topic; the KB carries no per-locus variant name, so the technical lines tell them apart.
  const hfe = rows.filter((r) => r.gene === "HFE");
  assert.equal(hfe.length, 2);
  assert.equal(hfe[0].topic, hfe[1].topic);
  assert.notEqual(hfe[0].technical, hfe[1].technical);
  for (const text of rows.flatMap((r) => [r.topic, r.statement, r.technical, r.stateLabel])) {
    for (const bad of PLACEHOLDERS) assert.ok(!text.includes(bad), `${bad} in "${text}"`);
  }
});

test("rows that share a topic still have distinct markers, so their Details buttons can be told apart", () => {
  const a = analyse(ALL_STATES_FILE);
  const rows = reportRows(groupedReport(workerLists(a), a.kb.genes));
  const hfe = rows.filter((r) => r.gene === "HFE");
  assert.ok(hfe.length >= 2, "the fixture needs both HFE loci for this check to mean anything");
  assert.equal(new Set(hfe.map((r) => r.topic)).size, 1);
  const names = rows.map((r) => `${r.topic}, ${r.markers}`);
  assert.equal(new Set(names).size, names.length);
});

// ---------------------------------------------------------------------------------------------------------------
// Lists and sections named by a result word hold exactly the checks in that word's state. The worker's lists are
// split by sample observation and overlap: an unclear check sits in its observation list and in the unclear list.

/**
 * The demo with rs6025 dropped (Not on your chip) and HFE H63D made wild type: H63D is then Unclear with no variant
 * (the worker also lists it with the wild-type checks), and MTHFR rs1801133 stays Unclear with the variant present
 * (the worker also lists it with the variant-present findings). Both carry a KB interpretation.
 */
const MIXED_UNCLEAR_FILE = DEMO.replace(/^rs6025[^\n]*\r?\n/m, "").replace(
  /^rs1799945\t6\t26092913\tCG/m,
  "rs1799945\t6\t26092913\tCC"
);
const PER_LOCUS_STATES = ["supported_and_observed", "supported_not_observed", "not_tested_by_array", "insufficient_evidence"];

/** The first cell of every body row of the Markdown table under "## <heading>", duplicates kept. */
function markdownIds(md, heading) {
  const lines = md.split("\n");
  const start = lines.findIndex((l) => l === `## ${heading}`);
  assert.ok(start >= 0, `no section "${heading}"`);
  let i = start + 1;
  while (i < lines.length && !lines[i].startsWith("|") && !lines[i].startsWith("## ")) i++;
  const ids = [];
  for (i += 2; i < lines.length && lines[i].startsWith("|"); i++) ids.push(lines[i].replace(/^\| /, "").split(" | ")[0]);
  return ids;
}

test("each Markdown result section holds exactly the checks in that state, and each check is in one section once", () => {
  const a = analyse(MIXED_UNCLEAR_FILE);
  const data = reportData(a);
  // The fixture exercises both overlaps, or this test proves nothing.
  assert.ok(data.records.some((vm) => vm.id === "rs1801133" && vm.coverage_state === "insufficient_evidence"));
  assert.ok(data.negativeChecks.some((vm) => vm.id === "rs1799945" && vm.coverage_state === "insufficient_evidence"));
  const md = markdownReport(data);
  const placed = [];
  for (const state of PER_LOCUS_STATES) {
    const label = RESULT_WORDS[state].label;
    const expected = a.vms.filter((vm) => vm.coverage_state === state).map((vm) => vm.exportId);
    assert.ok(expected.length > 0, `the fixture has a check in ${label}`);
    const ids = markdownIds(md, label);
    assert.deepEqual([...ids].sort(), [...expected].sort(), `## ${label}`);
    for (const row of Object.values(markdownRows(md, label))) assert.equal(row.Result, label, `## ${label}: ${row.rsID}`);
    placed.push(...ids);
  }
  assert.deepEqual(placed.sort(), a.vms.map((vm) => vm.exportId).sort(), "every check once, in one section");
});

test("an unclear check keeps its interpretation, reason and statement in the Unclear section of the Markdown", () => {
  const a = analyse(MIXED_UNCLEAR_FILE);
  const rows = markdownRows(markdownReport(reportData(a)), "Unclear");
  const mthfr = a.byRsid.rs1801133; // variant present
  const h63d = a.byRsid.rs1799945; // wild type
  for (const vm of [mthfr, h63d]) {
    assert.equal(vm.coverage_state, "insufficient_evidence", vm.id);
    assert.ok(vm.interpretation && typeof vm.phenotype === "string" && vm.phenotype.length > 0, `${vm.id} is interpreted`);
    const row = rows[vm.exportId];
    assert.ok(row, `${vm.id} is in the Unclear section`);
    assert.equal(row["Phenotype / guidance"], vm.phenotype, vm.id);
    assert.equal(row.Category, vm.category, vm.id);
    assert.equal(row.Magnitude, vm.magnitude === null ? "" : vm.magnitude.toFixed(1), vm.id);
    assert.equal(row.ClinVar, vm.starsExportText, vm.id);
    assert.equal(row.Reason, vm.reason, vm.id);
  }
  assert.match(h63d.statement, /^rs1799945 variant not detected \(\d variants tested in HFE\)$/);
  assert.equal(rows.rs1799945.Statement, h63d.statement);
});

test("rows by state: each check once, under its own state, from the worker's overlapping lists", () => {
  const a = analyse(MIXED_UNCLEAR_FILE);
  const lists = workerLists(a);
  assert.ok(lists.length > a.vms.length, "the lists overlap, or this test proves nothing");
  const byState = rowsByState(lists);
  assert.deepEqual(Object.keys(byState), PER_LOCUS_STATES);
  for (const state of PER_LOCUS_STATES) {
    const expected = a.vms.filter((vm) => vm.coverage_state === state).map((vm) => vm.id);
    assert.ok(expected.length > 0, `the fixture has a check in ${state}`);
    assert.deepEqual(byState[state].map((vm) => vm.id).sort(), expected.sort(), state);
  }
  // A component locus on its own and a marker outside coverage are never a row.
  const component = { ...a.byRsid.rs1801133, id: "rs429358", role: "apoe_component" };
  assert.deepEqual(rowsByState([component]).supported_and_observed, []);
  assert.deepEqual(rowsByState([component]).insufficient_evidence, []);
  assert.throws(() => rowsByState([{ ...a.byRsid.rs671, coverage_state: "outside_coverage" }]), /coverage state/);
});

test("the counts by category count Found checks only, once each, and an ACMG SF gene once", () => {
  const a = analyse(DEMO);
  // HFE H63D is a heterozygous Carrier reading with unclear evidence (Tier D): it is not found, so it is not counted.
  assert.equal(a.byRsid.rs1799945.coverage_state, "insufficient_evidence");
  assert.equal(a.byRsid.rs1799945.sample_observation, "variant_present");
  assert.equal(a.byRsid.rs1799945.category, "Carrier");
  assert.deepEqual(foundCategoryCounts(workerLists(a)), { pathogenic: 0, carrier: 2, pgx: 4, risk: 3, acmg: 1 });
  // The same rule, computed independently from the Found checks.
  const found = a.vms.filter((vm) => vm.coverage_state === "supported_and_observed");
  const n = (category) => found.filter((vm) => vm.category === category).length;
  assert.deepEqual(foundCategoryCounts(workerLists(a)), {
    pathogenic: n("Pathogenic"), carrier: n("Carrier"), pgx: n("Pharmacogenomics"), risk: n("Risk Factor"),
    acmg: new Set(found.filter((vm) => vm.acmg_sf).map((vm) => vm.gene)).size,
  });
  // With H63D's evidence sufficient, both HFE variants are Found: two Carrier checks, still one ACMG SF gene.
  const both = analyse(DEMO, (kb) => {
    kb.loci.rs1799945.evidence_sufficiency = "sufficient";
    return kb;
  });
  assert.equal(both.vms.filter((vm) => vm.gene === "HFE" && vm.coverage_state === "supported_and_observed").length, 2);
  assert.deepEqual(foundCategoryCounts(workerLists(both)), { pathogenic: 0, carrier: 3, pgx: 4, risk: 3, acmg: 1 });
});

// Owner ruling 2026-10-04: a multi-locus finding may rest on an Unclear reading, but it must say so. Each component
// carries its own result word; a caution line is added only when a component is not Found.
const MULTI_LOCUS_CAUTION = "This pairing relies on a reading Lucidase marks as unclear, so treat it with extra caution.";

/** The demo's report data with the worker's multi-locus findings, detected from its observed findings. */
function demoMultiLocusData(mutate = (records) => records) {
  const base = reportData(analyse(DEMO));
  const records = mutate(base.records);
  return {
    ...base,
    records,
    compoundHeterozygotes: detectCompoundHeterozygosity(records, KB_JSON.genes),
    independentAssortment: detectMultiLocus(records, KB_JSON.genes),
  };
}

/** The body of one "## " section of a Markdown report (up to the next "## " heading). */
function mdSection(md, heading) {
  const start = md.indexOf(`## ${heading}\n`);
  assert.ok(start >= 0, `no "## ${heading}" section`);
  const next = md.indexOf("\n## ", start + 3);
  return md.slice(start, next < 0 ? md.length : next);
}

test("a multi-locus finding with an Unclear component shows each marker's word and the caution line", () => {
  const data = demoMultiLocusData();
  // The demo's HFE pairing: C282Y is Found, H63D's evidence is insufficient (its own word is Unclear).
  assert.equal(data.compoundHeterozygotes.length, 1);
  assert.equal(data.records.find((r) => r.rsid === "rs1799945").coverage_state, "insufficient_evidence");
  const compound = mdSection(markdownReport(data), "Possible compound heterozygotes (phase unknown)");
  assert.match(compound, /rs1800562: Found/);
  assert.match(compound, /rs1799945: Unclear/);
  assert.ok(compound.includes(MULTI_LOCUS_CAUTION), compound);
});

test("a multi-locus finding whose components are all Found shows the words and no caution line", () => {
  const data = demoMultiLocusData();
  const pairing = mdSection(markdownReport(data), "Co-occurring variant alleles on unlinked loci");
  assert.match(pairing, /rs6025: Found/);
  assert.match(pairing, /rs1799963: Found/);
  assert.ok(!pairing.includes(MULTI_LOCUS_CAUTION), pairing);
  // Positive control for the same string: the same pairing with F2 read as Unclear carries the caution.
  const unclear = demoMultiLocusData((records) =>
    records.map((r) => (r.rsid === "rs1799963" ? { ...r, coverage_state: "insufficient_evidence" } : r)));
  assert.equal(unclear.independentAssortment.length, 1);
  const flagged = mdSection(markdownReport(unclear), "Co-occurring variant alleles on unlinked loci");
  assert.match(flagged, /rs1799963: Unclear/);
  assert.ok(flagged.includes(MULTI_LOCUS_CAUTION), flagged);
});

test("a multi-locus finding whose marker is not among the findings fails fast instead of guessing a word", () => {
  const data = demoMultiLocusData();
  const records = data.records.filter((r) => r.rsid !== "rs1799945");
  assert.throws(() => markdownReport({ ...data, records }), /rs1799945/);
});

test("the Summary sentence says each count in the result words, singular and plural, and Not on your chip only when there is one", () => {
  const counts = (found, notFound, gaps, unclear, outside) => ({
    supported_and_observed: found,
    supported_not_observed: notFound,
    not_tested_by_array: gaps,
    insufficient_evidence: unclear,
    outside_coverage: outside,
  });
  assert.equal(
    summaryProse(counts(10, 1, 0, 2, 612)),
    "Lucidase ran 13 checks on your file. A variant was found in 10, not found in 1, and 2 were unclear. " +
      "612 other markers in your file were counted but not interpreted."
  );
  assert.equal(
    summaryProse(counts(0, 9, 2, 1, 1)),
    "Lucidase ran 12 checks on your file. A variant was found in 0, not found in 9, 2 were not on your chip, " +
      "and 1 was unclear. 1 other marker in your file was counted but not interpreted."
  );
  assert.equal(
    summaryProse(counts(1, 0, 1, 0, 1234567)),
    "Lucidase ran 2 checks on your file. A variant was found in 1, not found in 0, 1 was not on your chip, " +
      "and 0 were unclear. 1,234,567 other markers in your file were counted but not interpreted."
  );
  assert.match(summaryProse(counts(1, 0, 0, 0, 0)), /^Lucidase ran 1 check on your file\. /);
  // The words are the result words.
  const text = summaryProse(counts(1, 1, 1, 1, 1));
  for (const state of ["supported_and_observed", "supported_not_observed", "not_tested_by_array", "insufficient_evidence"]) {
    assert.ok(text.includes(RESULT_WORDS[state].label.toLowerCase()), state);
  }
  // A count that is not a non-negative integer is a bug upstream, never a sentence with NaN in it.
  for (const bad of [undefined, null, -1, 1.5, NaN, "3"]) {
    assert.throws(() => summaryProse({ ...counts(1, 1, 1, 1, 1), insufficient_evidence: bad }), /insufficient_evidence/);
  }
  assert.throws(() => summaryProse(null), /count/);
});
