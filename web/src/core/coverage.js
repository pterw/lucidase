/**
 * Per-sample coverage state (contracts C4). Pure: no DOM, no `self`, no `fetch`.
 * Computed only at analysis time; none of it is ever stored in the knowledge base.
 */

export const COVERAGE_STATES = Object.freeze({
  SUPPORTED_AND_OBSERVED: "supported_and_observed",
  SUPPORTED_NOT_OBSERVED: "supported_not_observed",
  NOT_TESTED_BY_ARRAY: "not_tested_by_array",
  OUTSIDE_COVERAGE: "outside_coverage",
  INSUFFICIENT_EVIDENCE: "insufficient_evidence",
});

export const SAMPLE_OBSERVATION = Object.freeze({
  VARIANT_PRESENT: "variant_present",
  WILD_TYPE: "wild_type",
  CALL_UNAVAILABLE: "call_unavailable",
});

export const EVIDENCE_SUFFICIENCY = Object.freeze({
  SUFFICIENT: "sufficient",
  INSUFFICIENT: "insufficient",
});

export const REASONS = Object.freeze({
  NOT_ON_ARRAY: "locus not assayed on this array",
  ABSENT_FROM_VCF: "absent from VCF (variants-only VCFs omit reference calls)",
  NO_CALL: "no-call at this locus",
  NOT_INTERPRETABLE: "genotype not interpretable",
  INSUFFICIENT_EVIDENCE: "locus evidence is insufficient (see the evidence tier rationale)",
});

/**
 * Derives { coverage_state, sample_observation, reason } for one KB locus.
 *   assay: "array" | "vcf";  call: the matched Call, or undefined when the locus is absent from the file;
 *   resolution: resolveAltCount's result for that call (when it has alleles);
 *   evidenceSufficiency: the locus's evidence_sufficiency.
 */
export function deriveCoverageState({ assay, call, resolution, evidenceSufficiency }) {
  const unavailable = (coverage_state, reason) => ({
    coverage_state,
    sample_observation: SAMPLE_OBSERVATION.CALL_UNAVAILABLE,
    reason,
  });

  if (call === undefined) {
    return unavailable(
      COVERAGE_STATES.NOT_TESTED_BY_ARRAY,
      assay === "vcf" ? REASONS.ABSENT_FROM_VCF : REASONS.NOT_ON_ARRAY
    );
  }
  if (call.alleles === null || (resolution && !resolution.ok && resolution.reason === "no_call")) {
    return unavailable(COVERAGE_STATES.NOT_TESTED_BY_ARRAY, REASONS.NO_CALL);
  }
  if (!resolution || !resolution.ok) {
    return unavailable(COVERAGE_STATES.INSUFFICIENT_EVIDENCE, REASONS.NOT_INTERPRETABLE);
  }

  const sample_observation =
    resolution.altCount > 0 ? SAMPLE_OBSERVATION.VARIANT_PRESENT : SAMPLE_OBSERVATION.WILD_TYPE;
  if (evidenceSufficiency !== EVIDENCE_SUFFICIENCY.SUFFICIENT) {
    return {
      coverage_state: COVERAGE_STATES.INSUFFICIENT_EVIDENCE,
      sample_observation,
      reason: REASONS.INSUFFICIENT_EVIDENCE,
    };
  }
  return {
    coverage_state:
      resolution.altCount > 0 ? COVERAGE_STATES.SUPPORTED_AND_OBSERVED : COVERAGE_STATES.SUPPORTED_NOT_OBSERVED,
    sample_observation,
    reason: null,
  };
}

/**
 * Counts each record in exactly one state. `outsideCount` is the number of file markers that match no KB
 * locus (a per-file figure, not a per-locus state). An unknown state throws rather than being dropped.
 */
export function summarizeCoverage(records, outsideCount = 0) {
  const counts = {
    [COVERAGE_STATES.SUPPORTED_AND_OBSERVED]: 0,
    [COVERAGE_STATES.SUPPORTED_NOT_OBSERVED]: 0,
    [COVERAGE_STATES.NOT_TESTED_BY_ARRAY]: 0,
    [COVERAGE_STATES.INSUFFICIENT_EVIDENCE]: 0,
  };
  for (const r of records) {
    if (!Object.hasOwn(counts, r.coverage_state)) throw new Error(`unknown coverage state "${r.coverage_state}" on ${r.rsid}`);
    counts[r.coverage_state] += 1;
  }
  return {
    supported_and_observed_count: counts[COVERAGE_STATES.SUPPORTED_AND_OBSERVED],
    supported_not_observed_count: counts[COVERAGE_STATES.SUPPORTED_NOT_OBSERVED],
    not_tested_by_array_count: counts[COVERAGE_STATES.NOT_TESTED_BY_ARRAY],
    insufficient_evidence_count: counts[COVERAGE_STATES.INSUFFICIENT_EVIDENCE],
    outside_coverage_count: outsideCount,
    total_loci: records.length,
  };
}
