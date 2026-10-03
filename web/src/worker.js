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

/** Plus-strand allele string for an alt count, e.g. ref T / alt C with count 1 gives "TC". */
function genotypeFromAltCount(locus, altCount) {
  return locus.ref.repeat(2 - altCount) + locus.alt.repeat(altCount);
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
  const { records, summary: coverage } = classify(parsed, kb);

  for (const rec of records) rec.segregation = segregationFor(rec);

  // Transitional (until T7): the combined APOE finding is built from the two component loci.
  const byRsid = Object.fromEntries(records.map((r) => [r.rsid, r]));
  const gt = (rsid) => {
    const rec = byRsid[rsid];
    return rec && rec.altCount !== null ? genotypeFromAltCount(kb.loci[rsid], rec.altCount) : null;
  };
  const apoeFinding = resolveApoeDiplotype(gt("rs429358"), gt("rs7412"), kb);

  // Group by the UI's lists. Component loci are not listed on their own (no double counting).
  const listed = records.filter((r) => r.standalone);
  const isObserved = (r) =>
    r.sample_observation === SAMPLE_OBSERVATION.VARIANT_PRESENT &&
    (r.coverage_state === COVERAGE_STATES.SUPPORTED_AND_OBSERVED || r.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE);
  const observedFindings = listed.filter(isObserved);
  const negativeChecks = listed.filter(
    (r) =>
      r.coverage_state === COVERAGE_STATES.SUPPORTED_NOT_OBSERVED ||
      (r.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE && r.sample_observation === SAMPLE_OBSERVATION.WILD_TYPE)
  );
  const arrayGaps = listed.filter((r) => r.coverage_state === COVERAGE_STATES.NOT_TESTED_BY_ARRAY);
  const insufficientEvidence = listed.filter((r) => r.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE);

  if (apoeFinding) {
    if (apoeFinding.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE) insufficientEvidence.push(apoeFinding);
    else if (apoeFinding.sample_observation === SAMPLE_OBSERVATION.VARIANT_PRESENT) observedFindings.push(apoeFinding);
    else negativeChecks.push(apoeFinding);
  }

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
    apoe: apoeFinding ? apoeFinding.apoeInfo : null,
    compound_heterozygotes: compoundHeterozygotes,
    independent_assortment: independentAssortment,
    manifest: kb.manifest,
    genes: kb.genes
  });
}

function resolveApoeDiplotype(gt429, gt741, kb) {
  if (!gt429 && !gt741) return null;

  function norm429(gt) {
    if (!gt) return null;
    const s = gt.toUpperCase();
    if (s === "TT" || s === "AA") return "TT";
    if (s === "CT" || s === "TC" || s === "AG" || s === "GA") return "CT";
    if (s === "CC" || s === "GG") return "CC";
    return s;
  }

  function norm741(gt) {
    if (!gt) return null;
    const s = gt.toUpperCase();
    if (s === "CC" || s === "GG") return "CC";
    if (s === "CT" || s === "TC" || s === "AG" || s === "GA") return "CT";
    if (s === "TT" || s === "AA") return "TT";
    return s;
  }

  const n429 = norm429(gt429);
  const n741 = norm741(gt741);
  if (!n429 && !n741) return null;

  let diplotype = "";
  let label = "";
  let phenotype = "";
  let category = "Carrier";
  let significance = "";
  let magnitude = 1.0;
  let repute = "Neutral";
  let riskRatio = "";
  let lifetimeRisk = "";

  if (n429 === "TT" && n741 === "CC") {
    diplotype = "ε3/ε3";
    label = "APOE ε3/ε3 (Normal Baseline)";
    category = "Carrier";
    significance = "Normal / Baseline";
    magnitude = 1.5;
    repute = "Good";
    riskRatio = "1.0× (Average Population Baseline)";
    lifetimeRisk = "10–15% lifetime Alzheimer's risk";
    phenotype = "APOE ε3/ε3: The most common human genotype (~60–65% population frequency). Normal baseline lifetime risk for late-onset Alzheimer's disease and standard lipid metabolism.";
  } else if (n429 === "CT" && n741 === "CC") {
    diplotype = "ε3/ε4";
    label = "APOE ε3/ε4 Carrier";
    category = "Carrier";
    significance = "Risk Factor / Carrier";
    magnitude = 4.2;
    repute = "Bad";
    riskRatio = "3–4× Increased Risk";
    lifetimeRisk = "25–35% lifetime Alzheimer's risk";
    phenotype = "APOE ε3/ε4 Heterozygous Carrier: One ε4 copy conferring ~3–4× elevated risk for late-onset Alzheimer's disease (~20–25% population prevalence; ~25–35% lifetime risk). Cardiovascular health, regular aerobic exercise, ApoB management, and quality sleep are effective protective lifestyle modulators.";
  } else if (n429 === "CC" && n741 === "CC") {
    diplotype = "ε4/ε4";
    label = "APOE ε4/ε4 Homozygote";
    category = "Risk Factor";
    significance = "High Risk Factor";
    magnitude = 6.0;
    repute = "Bad";
    riskRatio = "12–15× Markedly Elevated Risk";
    lifetimeRisk = "50–65% lifetime Alzheimer's risk";
    phenotype = "APOE ε4/ε4 Homozygote: Two copies of the ε4 allele (~2% population prevalence). Confers ~12–15× increased lifetime risk of late-onset Alzheimer's disease and increased LDL/atherosclerosis susceptibility.";
  } else if (n429 === "TT" && n741 === "CT") {
    diplotype = "ε2/ε3";
    label = "APOE ε2/ε3 Carrier";
    category = "Carrier";
    significance = "Protective / Carrier";
    magnitude = 2.2;
    repute = "Good";
    riskRatio = "0.6× (Protective Effect)";
    lifetimeRisk = "5–8% lifetime Alzheimer's risk";
    phenotype = "APOE ε2/ε3 Heterozygous Carrier: One protective ε2 allele and one neutral ε3 allele (~10–15% population prevalence). Associated with ~40–50% lower lifetime risk of Alzheimer's disease and lower circulating LDL-cholesterol.";
  } else if (n429 === "TT" && n741 === "TT") {
    diplotype = "ε2/ε2";
    label = "APOE ε2/ε2 Homozygote";
    category = "Carrier";
    significance = "Protective AD / Lipid Risk";
    magnitude = 3.5;
    repute = "Bad";
    riskRatio = "Protective AD / Type III HLP Risk";
    lifetimeRisk = "<5% AD risk; Monitor blood lipid panels";
    phenotype = "APOE ε2/ε2 Homozygote: Protective against Alzheimer's disease, but strongly associated with genetic predisposition to Type III Hyperlipoproteinemia (familial dysbetalipoproteinemia; requires secondary metabolic triggers).";
  } else if (n429 === "CT" && n741 === "CT") {
    diplotype = "ε2/ε4";
    label = "APOE ε2/ε4 Double Heterozygote";
    category = "Carrier";
    significance = "Risk Factor / Carrier";
    magnitude = 3.2;
    repute = "Bad";
    riskRatio = "1.5–2× Intermediate Risk";
    lifetimeRisk = "15–20% lifetime Alzheimer's risk";
    phenotype = "APOE ε2/ε4 Double Heterozygote: Carries one protective ε2 allele and one risk-elevating ε4 allele (~2% population prevalence). Overall Alzheimer's risk is intermediate between ε3/ε3 and ε3/ε4.";
  } else if (!n429 || !n741) {
    diplotype = "Indeterminate";
    label = "APOE Indeterminate (Missing rs429358 or rs7412)";
    category = "Trait";
    significance = "Incomplete Loci";
    magnitude = 1.0;
    repute = "Neutral";
    riskRatio = "Unknown";
    lifetimeRisk = "Cannot determine without both loci";
    phenotype = "Both rs429358 (codon 112) and rs7412 (codon 158) must be genotyped to determine an APOE diplotype. A single locus cannot distinguish ε3 from ε2 or ε4 without unsupported assumptions.";
  } else {
    diplotype = "Atypical";
    label = `APOE (${n429 || '?'}/${n741 || '?'})`;
    category = "Trait";
    significance = "Uncertain";
    magnitude = 1.0;
    repute = "Neutral";
    riskRatio = "Uncertain";
    lifetimeRisk = "Average population risk";
    phenotype = `Atypical APOE combination: rs429358=${n429}, rs7412=${n741}.`;
  }

  const rawSummary = `rs429358:${gt429 || '--'}, rs7412:${gt741 || '--'}`;

  const determinate = /^ε[234]\/ε[234]$/.test(diplotype);
  const isRisk = diplotype.includes("ε4") || diplotype.includes("ε2/ε2");
  const sampleObservation = !determinate
    ? SAMPLE_OBSERVATION.CALL_UNAVAILABLE
    : isRisk ? SAMPLE_OBSERVATION.VARIANT_PRESENT : SAMPLE_OBSERVATION.WILD_TYPE;
  // Evidence, tier and limitation come from the KB's APOE locus, not from hand-typed values.
  const base = kb.loci.rs429358;
  if (!base) throw new Error("The knowledge base has no rs429358 locus, so APOE cannot be assembled.");

  return {
    rsid: "APOE-STATUS",
    gene: "APOE",
    chrom: base.chrom,
    pos: base.pos_grch37,
    genotype_display: `${diplotype} (${rawSummary})`,
    altCount: null,
    strandFlipped: null,
    coverage_state: !determinate
      ? COVERAGE_STATES.INSUFFICIENT_EVIDENCE
      : isRisk ? COVERAGE_STATES.SUPPORTED_AND_OBSERVED : COVERAGE_STATES.SUPPORTED_NOT_OBSERVED,
    sample_observation: sampleObservation,
    reason: determinate ? null : REASONS.NOT_INTERPRETABLE,
    interpretation_key: null,
    interpretation: { category, significance, magnitude, repute, phenotype, drug_response: null, caveats: [] },
    evidence: base.evidence,
    evidence_tier: base.evidence_tier,
    tier_source: base.tier_source,
    tier_rationale: base.tier_rationale,
    tier_citation: base.tier_citation,
    evidence_sufficiency: base.evidence_sufficiency,
    limitation: base.limitation,
    acmg_sf: kb.genes.APOE.acmg_sf,
    role: "standard",
    standalone: true,
    segregation: computeSegregationReport("APOE", isRisk ? "RV" : "", category, significance),
    apoeInfo: {
      diplotype,
      label,
      riskRatio,
      lifetimeRisk,
      phenotype,
      repute,
      rawSummary,
      rs429358: gt429,
      rs7412: gt741
    }
  };
}
