/**
 * GenomePulse - High-Performance Genomic Web Worker
 * =================================================
 * Runs off the main UI thread to parse 1,000,000-line raw genotyping files
 * (23andMe, AncestryDNA, MyHeritage, VCF) without freezing the browser.
 *
 * The knowledge base is the pipeline's JSON (web/src/knowledge-base.json), validated once
 * per worker and cached by kb-loader.js. Classification is by alt-allele count (core/classify.js).
 */

import { parseGenotypeFile } from "./core/parse.js";
import { computeQc } from "./core/qc.js";
import { loadKnowledgeBase } from "./kb-loader.js";
import { classify } from "./core/classify.js";
import { assembleFindings } from "./core/apoe.js";
import { COVERAGE_STATES, SAMPLE_OBSERVATION } from "./core/coverage.js";
import { describeSegregation, detectMultiLocus, detectCompoundHeterozygosity } from "./core/inheritance.js";

self.onmessage = async function (e) {
  try {
    const { action, text, fileName } = e.data;
    if (action === "parse") {
      await analyzeGenotypeFile(text, fileName);
    }
  } catch (err) {
    self.postMessage({ type: "error", message: String((err && err.message) || err) });
  }
};

/**
 * Inheritance inputs for one locus, from its alt-allele count and the KB (gene inheritance model,
 * gnomAD allele frequency). `afRsid` names the locus whose allele frequency applies when it
 * differs from the record's own (the APOE e4 allele is the rs429358 alt allele).
 */
function segregationFor(rec, kb, altCount = rec.altCount, afRsid = rec.rsid) {
  if (altCount === null || altCount === undefined) return null;
  const locus = kb.loci[afRsid];
  const gnomad = locus.evidence && locus.evidence.gnomad;
  const af = gnomad && typeof gnomad.af === "number" ? gnomad.af : null;
  const allele = afRsid === "rs429358" ? "e4" : locus.alt;
  return describeSegregation(rec.gene, kb.genes[rec.gene], altCount, af, allele);
}

async function analyzeGenotypeFile(text, fileName = "") {
  self.postMessage({ type: "progress", percent: 5, status: "Detecting format and header..." });

  // Throws UnsupportedFormatError for unrecognised content; the catch above reports it.
  const parsed = parseGenotypeFile(text, fileName);
  const { format, build } = parsed;

  self.postMessage({ type: "progress", percent: 15, status: `Parsed ${format.toUpperCase()} (${build})...` });

  const chromDist = {};
  for (const call of parsed.calls) chromDist[call.chrom] = (chromDist[call.chrom] || 0) + 1;

  self.postMessage({ type: "progress", percent: 90, status: `Parsed ${parsed.calls.length.toLocaleString()} SNPs...` });

  const kb = await loadKnowledgeBase();
  const qcMetrics = computeQc(parsed);
  const { records, summary: rawCoverage } = classify(parsed, kb);

  for (const rec of records) rec.segregation = segregationFor(rec, kb);

  // The two APOE component loci become one APOE finding (core/apoe.js), counted once in the coverage summary.
  const { listed, apoe: apoeFinding, summary: coverage } = assembleFindings(records, kb, rawCoverage.outside_coverage_count);
  // The e4 allele is the rs429358 alt allele, so its count and frequency drive the APOE offspring figures.
  if (apoeFinding) {
    const e4 = records.find((r) => r.rsid === "rs429358");
    apoeFinding.segregation = segregationFor(apoeFinding, kb, e4.altCount, "rs429358");
  }

  // Group by the UI's lists. Component loci are not listed on their own (no double counting).
  const isObserved = (r) =>
    r.sample_observation === SAMPLE_OBSERVATION.VARIANT_PRESENT &&
    (r.coverage_state === COVERAGE_STATES.SUPPORTED_AND_OBSERVED || r.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE);
  // An atypical APOE is variant-present but has no interpretation: it is listed as insufficient evidence only.
  const observedFindings = listed.filter((r) => isObserved(r) && r.interpretation !== null);
  const negativeChecks = listed.filter(
    (r) =>
      r.coverage_state === COVERAGE_STATES.SUPPORTED_NOT_OBSERVED ||
      (r.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE && r.sample_observation === SAMPLE_OBSERVATION.WILD_TYPE)
  );
  const arrayGaps = listed.filter((r) => r.coverage_state === COVERAGE_STATES.NOT_TESTED_BY_ARRAY);
  const insufficientEvidence = listed.filter((r) => r.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE);

  // Sort observed findings by clinical priority (magnitude descending)
  observedFindings.sort((a, b) => (b.interpretation.magnitude - a.interpretation.magnitude));

  // Multi-locus findings come from alt counts and KB inheritance models, never genotype strings.
  const compoundHeterozygotes = detectCompoundHeterozygosity(observedFindings, kb.genes);
  const independentAssortment = detectMultiLocus(observedFindings, kb.genes);

  const category = (c) => observedFindings.filter((f) => f.interpretation.category === c).length;
  const summary = {
    total_annotated: observedFindings.length,
    pathogenic_count: category("Pathogenic"),
    carrier_count: category("Carrier"),
    pgx_count: category("Pharmacogenomics"),
    risk_factor_count: category("Risk Factor"),
    acmg_actionable_findings: observedFindings.filter((f) => f.acmg_sf).length,
    compound_heterozygotes_count: compoundHeterozygotes.length,
    independent_assortment_count: independentAssortment.length
  };

  const qc = {
    format_name: format,
    build,
    total_snps: parsed.calls.length,
    called_snps: parsed.stats.called,
    nocall_snps: parsed.stats.no_calls,
    ...qcMetrics,
    chrom_distribution: chromDist
  };

  self.postMessage({
    type: "complete",
    qc,
    records: observedFindings,
    negative_checks: negativeChecks,
    array_gaps: arrayGaps,
    insufficient_evidence: insufficientEvidence,
    coverage_taxonomy: coverage,
    summary,
    apoe: apoeFinding,
    compound_heterozygotes: compoundHeterozygotes,
    independent_assortment: independentAssortment,
    manifest: kb.manifest,
    genes: kb.genes
  });
}
