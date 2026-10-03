/**
 * APOE diplotype from the two component loci's alt-allele counts (contracts C2 `genes.APOE.diplotypes`, C3, C4).
 * Pure: no DOM, no `self`, no `fetch`.
 *
 *   e4 = alt count of rs429358 (alt C), e2 = alt count of rs7412 (alt T).
 *
 * A diplotype is asserted only when both components resolve. A missing, no-call or unresolvable component gives
 * no diplotype, never wild-type and never "presumed e3". Interpretation text, stars, allele frequency and
 * magnitude come from the knowledge base; nothing clinical is typed here.
 */
import { COVERAGE_STATES, EVIDENCE_SUFFICIENCY, SAMPLE_OBSERVATION, summarizeCoverage } from "./coverage.js";

export const APOE_E4_RSID = "rs429358";
export const APOE_E2_RSID = "rs7412";

export const ATYPICAL = "atypical";
export const ATYPICAL_REASON =
  "requires an e1-type haplotype; cannot be resolved from genotype array data";
export const PHASE_CAVEAT = "phase unknown: e1/e3 is the rare alternative";

/** Diplotype for (e4 count, e2 count), or ATYPICAL for the combinations the genotype cannot resolve. */
const DIPLOTYPE_BY_COUNTS = {
  "0,0": "e3/e3",
  "1,0": "e3/e4",
  "2,0": "e4/e4",
  "0,1": "e2/e3",
  "0,2": "e2/e2",
  "1,1": "e2/e4",
  "2,1": ATYPICAL,
  "1,2": ATYPICAL,
  "2,2": ATYPICAL,
};

/** Display form of a diplotype key, e.g. "e3/e4" gives "ε3/ε4". */
export const displayDiplotype = (diplotype) => diplotype.replace(/e/g, "ε");

function componentSummary(components) {
  return components.map((c) => `${c.rsid}:${c.genotype_display ?? "--"}`).join(", ");
}

/**
 * Builds the single APOE finding from the classified component records. `componentRecords` holds the two
 * records (any order); `kb` is a validated knowledge base. Returns a record shaped like classify's records plus
 * `diplotype` (null when none is asserted), `components` and `caveat`.
 */
export function resolveApoe(componentRecords, kb) {
  const e4Rec = componentRecords.find((r) => r.rsid === APOE_E4_RSID);
  const e2Rec = componentRecords.find((r) => r.rsid === APOE_E2_RSID);
  if (!e4Rec || !e2Rec) {
    throw new Error(`APOE needs both component records (${APOE_E4_RSID}, ${APOE_E2_RSID})`);
  }
  const gene = kb.genes.APOE;
  const base = kb.loci[APOE_E4_RSID];
  if (!gene || !gene.diplotypes || !base) {
    throw new Error("The knowledge base has no APOE gene diplotypes or rs429358 locus, so APOE cannot be assembled.");
  }
  const components = [e4Rec, e2Rec];

  const common = {
    rsid: "APOE-STATUS",
    gene: "APOE",
    chrom: base.chrom,
    pos: e4Rec.pos,
    altCount: null,
    strandFlipped: null,
    evidence: base.evidence,
    evidence_tier: base.evidence_tier,
    tier_source: base.tier_source,
    tier_rationale: base.tier_rationale,
    tier_citation: base.tier_citation,
    evidence_sufficiency: base.evidence_sufficiency,
    limitation: base.limitation,
    acmg_sf: gene.acmg_sf,
    role: "standard",
    standalone: true,
    components,
  };
  const unresolved = (coverage_state, reason, sample_observation, diplotype) => ({
    ...common,
    genotype_display: componentSummary(components),
    coverage_state,
    sample_observation,
    reason,
    interpretation_key: null,
    interpretation: null,
    diplotype,
    caveat: null,
  });

  // A component with no allele count means no diplotype. An unresolvable genotype outranks a missing one.
  const missing = components.filter((c) => c.altCount === null);
  if (missing.length > 0) {
    const state = missing.some((c) => c.coverage_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE)
      ? COVERAGE_STATES.INSUFFICIENT_EVIDENCE
      : COVERAGE_STATES.NOT_TESTED_BY_ARRAY;
    const reason = missing
      .filter((c) => c.coverage_state === state)
      .map((c) => `${c.rsid}: ${c.reason}`)
      .join("; ");
    return unresolved(state, reason, SAMPLE_OBSERVATION.CALL_UNAVAILABLE, null);
  }

  const key = `${e4Rec.altCount},${e2Rec.altCount}`;
  const diplotype = DIPLOTYPE_BY_COUNTS[key];
  if (diplotype === undefined) throw new Error(`APOE: impossible allele counts ${key}`);

  if (diplotype === ATYPICAL) {
    return unresolved(
      COVERAGE_STATES.INSUFFICIENT_EVIDENCE,
      ATYPICAL_REASON,
      SAMPLE_OBSERVATION.VARIANT_PRESENT,
      ATYPICAL
    );
  }

  const kbInterp = gene.diplotypes[diplotype];
  if (!kbInterp) throw new Error(`The knowledge base has no APOE ${diplotype} interpretation.`);
  const caveat = diplotype === "e2/e4" ? PHASE_CAVEAT : null;
  const wildType = diplotype === "e3/e3";
  const sufficient = components.every((c) => c.evidence_sufficiency === EVIDENCE_SUFFICIENCY.SUFFICIENT);
  const observation = wildType ? SAMPLE_OBSERVATION.WILD_TYPE : SAMPLE_OBSERVATION.VARIANT_PRESENT;
  const coverage_state = !sufficient
    ? COVERAGE_STATES.INSUFFICIENT_EVIDENCE
    : wildType
      ? COVERAGE_STATES.SUPPORTED_NOT_OBSERVED
      : COVERAGE_STATES.SUPPORTED_AND_OBSERVED;

  return {
    ...common,
    genotype_display: `${displayDiplotype(diplotype)} (${componentSummary(components)})`,
    coverage_state,
    sample_observation: observation,
    reason: sufficient ? null : "locus evidence is insufficient (see the evidence tier rationale)",
    interpretation_key: diplotype,
    interpretation: { ...kbInterp, caveats: caveat ? [...kbInterp.caveats, caveat] : [...kbInterp.caveats] },
    diplotype,
    caveat,
  };
}

/**
 * Replaces the two component records with the one APOE finding. Returns
 *   { listed, apoe, summary }: `listed` is every standalone record plus the APOE finding (or the unchanged
 * standalone records when the KB has no APOE components); `summary` counts each listed record once, so the
 * coverage cards agree with the table.
 */
export function assembleFindings(records, kb, outsideCount = 0) {
  const standalone = records.filter((r) => r.standalone);
  const components = records.filter((r) => r.role === "apoe_component");
  const apoe = components.length > 0 ? resolveApoe(components, kb) : null;
  const listed = apoe ? [...standalone, apoe] : standalone;
  return { listed, apoe, summary: summarizeCoverage(listed, outsideCount) };
}
