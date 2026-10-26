// Made-up example data for the UI kit. Loci and genes are the 14 curated loci (12 genes) of the Lucidase KB;
// genotypes are invented for the demo. Counts on screen are computed from these rows, never typed in.
window.LDS_DEMO = {
  file: { name: "sample-23andme.txt", format: "23andMe", build: "GRCh37", markers: 28, callRate: "92.86%", het: "76.92%", sexQc: "X heterozygosity consistent with two X chromosomes", outside: 14 },
  records: [
    { id: "APOE", gene: "APOE", rsid: "rs429358 + rs7412", chrom: "19", gt: "ε4/ε4", raw: "rs429358 C/C · rs7412 C/C", state: "supported_and_observed", category: "Risk Factor", tier: "A", clinvar: "Reviewed by expert panel", af: null, inheritance: "risk_factor",
      statement: "Two copies of the ε4 allele were found. ε4 is associated with a higher risk of late-onset Alzheimer's disease. This is a risk factor, not a diagnosis.", limitation: null, caveat: "Diplotype built from two markers; phase is inferred from the two genotypes." },
    { id: "rs4244285", gene: "CYP2C19", rsid: "rs4244285", chrom: "10", gt: "G/A", state: "supported_and_observed", category: "Pharmacogenomics", tier: "A", clinvar: "Criteria provided, multiple submitters", af: 0.15, inheritance: "pgx",
      statement: "One copy of the *2 allele was found. CPIC links *2 to reduced activation of clopidogrel.", limitation: "This checks one variant of a gene with many star alleles. A full star-allele call is not possible from this file." },
    { id: "rs4149056", gene: "SLCO1B1", rsid: "rs4149056", chrom: "12", gt: "T/C", state: "supported_and_observed", category: "Pharmacogenomics", tier: "A", clinvar: "Criteria provided, single submitter", af: 0.16, inheritance: "pgx",
      statement: "One copy of the C allele (*5 / *15 haplotypes) was found. CPIC links it to higher simvastatin exposure.", limitation: null },
    { id: "rs9923231", gene: "VKORC1", rsid: "rs9923231", chrom: "16", gt: "C/T", state: "supported_and_observed", category: "Pharmacogenomics", tier: "A", clinvar: "Criteria provided, multiple submitters", af: 0.39, inheritance: "pgx",
      statement: "One copy of the T allele was found. CPIC uses it in warfarin dosing with other factors.", limitation: null },
    { id: "rs1800562", gene: "HFE", rsid: "rs1800562", chrom: "6", gt: "G/A", state: "supported_and_observed", category: "Carrier", tier: "A", clinvar: "Reviewed by expert panel", af: 0.03, inheritance: "recessive",
      statement: "One copy of C282Y was found. One copy alone is not expected to cause hereditary haemochromatosis.", limitation: null },
    { id: "rs1799945", gene: "HFE", rsid: "rs1799945", chrom: "6", gt: "C/G", state: "supported_and_observed", category: "Carrier", tier: "B", clinvar: "Criteria provided, conflicting classifications", af: 0.11, inheritance: "recessive",
      statement: "One copy of H63D was found.", limitation: null },
    { id: "rs1799963", gene: "F2", rsid: "rs1799963", chrom: "11", gt: "G/A", state: "supported_and_observed", category: "Risk Factor", tier: "A", clinvar: "Criteria provided, multiple submitters", af: 0.01, inheritance: "risk_factor",
      statement: "One copy of the prothrombin G20210A allele was found. It is associated with a higher risk of venous thrombosis.", limitation: null },
    { id: "rs6025", gene: "F5", rsid: "rs6025", chrom: "1", gt: "C/T", state: "supported_and_observed", category: "Risk Factor", tier: "A", clinvar: "Criteria provided, multiple submitters", af: 0.02, inheritance: "risk_factor",
      statement: "One copy of factor V Leiden was found. It is associated with a higher risk of venous thrombosis.", limitation: null },
    { id: "rs1801133", gene: "MTHFR", rsid: "rs1801133", chrom: "1", gt: "G/A", state: "supported_and_observed", category: "Trait", tier: "B", clinvar: "Criteria provided, single submitter", af: 0.31, inheritance: "trait",
      statement: "One copy of C677T was found. On its own it has no established clinical use.", limitation: null },
    { id: "rs4988235", gene: "MCM6", rsid: "rs4988235", chrom: "2", gt: "A/G", state: "supported_and_observed", category: "Trait", tier: "B", clinvar: null, af: 0.39, inheritance: "trait",
      statement: "One copy of the allele associated with lactase persistence was found.", limitation: null }
  ],
  negative: [
    { id: "rs671", gene: "ALDH2", rsid: "rs671", chrom: "12", gt: "G/G", state: "supported_not_observed", category: "Not detected", tier: "A", clinvar: null, af: 0.02, inheritance: "trait",
      statement: "ALDH2*2 not detected among the 1 variant tested in ALDH2.", limitation: null }
  ],
  gaps: [],
  insufficient: [
    { id: "rs3918290", gene: "DPYD", rsid: "rs3918290", chrom: "1", gt: "C/T", state: "insufficient_evidence", category: "Pharmacogenomics", tier: "C", clinvar: "Criteria provided, conflicting classifications", af: 0.005, inheritance: "pgx",
      statement: "A variant allele is present, but the evidence for this call is insufficient to report a result.", limitation: "This checks one variant of a gene with many known variants." },
    { id: "rs113993960", gene: "CFTR", rsid: "rs113993960", chrom: "7", gt: null, state: "insufficient_evidence", category: null, tier: null, clinvar: "Reviewed by expert panel", af: null, inheritance: "recessive",
      statement: "The genotype for this deletion cannot be resolved unambiguously from the array call, so no result is reported.", limitation: "A single-variant test of CFTR. Most CFTR variants are not on consumer arrays." }
  ]
};
