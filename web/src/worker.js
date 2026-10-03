/**
 * GenomePulse - High-Performance Genomic Web Worker
 * =================================================
 * Runs off the main UI thread to parse 1,000,000-line raw genotyping files
 * (23andMe, AncestryDNA, MyHeritage, VCF) without freezing the browser.
 *
 * The knowledge base is the pipeline's JSON (web/src/knowledge-base.json), validated once
 * per worker and cached. Classification is by alt-allele count (core/classify.js).
 */

import {
  computeSegregationReport,
  detectCompoundHeterozygosity,
  computeIndependentAssortment
} from "./knowledge-base.js";

import { parseGenotypeFile } from "./core/parse.js";
import { computeQc } from "./core/qc.js";
import { validateKb } from "./core/kb.js";
import { classify } from "./core/classify.js";
import { assembleFindings } from "./core/apoe.js";
import { COVERAGE_STATES, REASONS, SAMPLE_OBSERVATION } from "./core/coverage.js";

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

let kbPromise = null;

/**
 * Loads and validates the knowledge base once. It is imported as a JSON module rather than
 * fetched: tests/test_zero_knowledge_privacy.py requires that worker.js contains no fetch
 * call at all, and a JSON import is the same same-origin static load. A failed load is not
 * cached, so a retry can succeed.
 */
function loadKnowledgeBase() {
  if (!kbPromise) {
    kbPromise = import("./knowledge-base.json", { with: { type: "json" } })
      .then((mod) => validateKb(mod.default))
      .catch((err) => {
        kbPromise = null;
        throw new Error(`The knowledge base could not be loaded: ${(err && err.message) || err}`);
      });
  }
  return kbPromise;
}

/**
 * Transitional (until T8): the existing segregation functions take a genotype string. An alt
 * count of 0 passes an empty string, so a wild-type result is neither carrier nor affected.
 */
function segregationFor(rec) {
  if (rec.altCount === null) return null;
  const pseudoGenotype = ["", "RV", "VV"][rec.altCount];
  const seg = computeSegregationReport(rec.gene, pseudoGenotype, rec.interpretation.category, rec.interpretation.significance);
  return seg;
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

  for (const rec of records) rec.segregation = segregationFor(rec);

  // The two APOE component loci become one APOE finding (core/apoe.js), counted once in the coverage summary.
  const { listed, apoe: apoeFinding, summary: coverage } = assembleFindings(records, kb, rawCoverage.outside_coverage_count);

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

  // Transitional (until T8): the multi-locus functions read a "genotype" string and an rsid.
  const legacy = (r) => ({ rsid: r.rsid, genotype: r.genotype_display ? r.genotype_display.replace("/", "") : "" });
  const compoundHeterozygotes = detectCompoundHeterozygosity(observedFindings.map(legacy));
  const independentAssortment = computeIndependentAssortment(observedFindings.map(legacy));

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
