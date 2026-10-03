/**
 * Pure QC metrics over a ParseResult (contracts C1). No DOM, no `self`, no `fetch`.
 *
 * The sex-chromosome output is a QC signal about X heterozygosity, never a
 * karyotype or condition claim: array Y calls are noisy and X het rates overlap
 * across conditions, so the wording only describes what was measured.
 */

/** Fewer called X markers than this cannot support a signal (a typical array has thousands). */
export const MIN_X_MARKERS = 10;

/**
 * Cut-off between the two X-het regimes. Two X chromosomes give roughly 0.25-0.30
 * heterozygosity at array X SNPs; one X gives near 0 (genotyping error only).
 * 0.05 sits well inside the gap. Strictly greater means "two X".
 */
export const X_HET_CUTOFF = 0.05;

export const VCF_RATE_NOTE = "not meaningful for variants-only VCF";

export const SEX_SIGNAL = Object.freeze({
  TWO_X: "X heterozygosity consistent with two X chromosomes",
  ONE_X: "X heterozygosity consistent with one X chromosome",
  INDETERMINATE: "Indeterminate (too few X markers)",
});

function isHet(alleles) {
  return alleles.length === 2 && alleles[0] !== alleles[1];
}

/** Returns { call_rate, heterozygosity_rate (both null for a VCF, with qc_note), x_markers, x_het_rate, y_calls, sex_signal }. */
export function computeQc(parseResult) {
  let called = 0;
  let noCalls = 0;
  let diploid = 0;
  let het = 0;
  let xMarkers = 0;
  let xHet = 0;
  let yCalls = 0;

  for (const call of parseResult.calls) {
    if (call.alleles === null) {
      noCalls++;
      continue;
    }
    called++;
    if (call.alleles.length === 2) {
      diploid++;
      if (isHet(call.alleles)) het++;
    }
    if (call.chrom === "X") {
      xMarkers++;
      if (isHet(call.alleles)) xHet++;
    } else if (call.chrom === "Y") {
      yCalls++;
    }
  }

  const total = called + noCalls;
  // A VCF lists variant sites, so rates over it are ~100% called / mostly het by construction.
  const variantsOnly = parseResult.assay === "vcf";
  const xHetRate = xMarkers > 0 ? xHet / xMarkers : 0;
  let sexSignal = SEX_SIGNAL.INDETERMINATE;
  if (xMarkers >= MIN_X_MARKERS) {
    sexSignal = xHetRate > X_HET_CUTOFF ? SEX_SIGNAL.TWO_X : SEX_SIGNAL.ONE_X;
  }

  return {
    call_rate: variantsOnly ? null : total > 0 ? called / total : 0,
    heterozygosity_rate: variantsOnly ? null : diploid > 0 ? het / diploid : 0,
    qc_note: variantsOnly ? VCF_RATE_NOTE : null,
    x_markers: xMarkers,
    x_het_rate: xHetRate,
    y_calls: yCalls,
    sex_signal: sexSignal,
  };
}
