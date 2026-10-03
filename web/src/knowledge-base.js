/**
 * GenomePulse / HelixLens - Curated Clinical & Proteomic Knowledge Base
 * ====================================================================
 * Curated offline references for high-impact human genetic variants:
 * - ClinVar clinical significance and star ratings
 * - ACMG Secondary Findings v3.2 actionable gene flags (81 genes)
 * - Human Protein Atlas (HPA) tissue protein abundance & subcellular localization
 * - CPIC Pharmacogenomics (PGx) drug metabolism alerts
 * - gnomAD continental allele frequencies & pLI constraint scores
 */
export const KB_MANIFEST = {
  schema_version: "3.0.0",
  release_version: "2026.10.02",
  release_date: "2026-10-02",
  clinvar_release: "Release 2024-06",
  dbsnp_build: 156,
  acmg_sf_version: "v3.2 (81 genes)",
  variant_count: 14,
  sha256: "ad3c3cb5e04df46ff89b18effb0f2d0647ef41eccaaebbd6a65a2cf040838edd",
  local_analysis: true,
  genomic_uploads: false,
  variant_identifiers_transmitted: false,
  guardrail: "Absence of a finding must never imply absence of genetic risk. GenomePulse analyzes only specifically targeted loci on consumer arrays and does not sequence entire genes or detect structural variants."
};

export const COVERAGE_STATES = {
  SUPPORTED_AND_OBSERVED: "supported_and_observed",
  SUPPORTED_NOT_OBSERVED: "supported_not_observed",
  NOT_TESTED_BY_ARRAY: "not_tested_by_array",
  OUTSIDE_COVERAGE: "outside_coverage",
  INSUFFICIENT_EVIDENCE: "insufficient_evidence"
};

export const ASSAY_COVERAGE = {
  ASSAYED_CALLED: "assayed_called",
  NO_CALL: "no_call",
  UNPROBED: "unprobed"
};

export const CURATION_SCOPE = {
  IN_SCOPE: "in_scope",
  OUT_OF_SCOPE: "out_of_scope"
};

export const EVIDENCE_SUFFICIENCY = {
  SUFFICIENT: "sufficient",
  INSUFFICIENT: "insufficient",
  UNASSESSED: "unassessed"
};

export const SAMPLE_OBSERVATION = {
  VARIANT_PRESENT: "variant_present",
  WILD_TYPE: "wild_type",
  CALL_UNAVAILABLE: "call_unavailable"
};

export function deriveCoverageEvaluation(assay, scope, evidence, observation) {
  if (scope === CURATION_SCOPE.OUT_OF_SCOPE) {
    return {
      assay_coverage: assay,
      curation_scope: scope,
      evidence_sufficiency: evidence,
      sample_observation: observation,
      derived_state: COVERAGE_STATES.OUTSIDE_COVERAGE,
      user_label: "Outside Scope",
      explanation: "Marker was genotyped on the array but is outside GenomePulse's curated variome catalog."
    };
  }
  if (assay === ASSAY_COVERAGE.UNPROBED || assay === ASSAY_COVERAGE.NO_CALL) {
    return {
      assay_coverage: assay,
      curation_scope: scope,
      evidence_sufficiency: evidence,
      sample_observation: observation,
      derived_state: COVERAGE_STATES.NOT_TESTED_BY_ARRAY,
      user_label: assay === ASSAY_COVERAGE.UNPROBED ? "Array Gap" : "No-Call",
      explanation: assay === ASSAY_COVERAGE.UNPROBED 
        ? "Curated locus was omitted from this microarray design/manifest. Absence of a finding does NOT imply absence of risk."
        : "Curated locus was interrogated on the array but failed QC and produced an uncallable genotype ('--')."
    };
  }
  if (evidence === EVIDENCE_SUFFICIENCY.INSUFFICIENT) {
    return {
      assay_coverage: assay,
      curation_scope: scope,
      evidence_sufficiency: evidence,
      sample_observation: observation,
      derived_state: COVERAGE_STATES.INSUFFICIENT_EVIDENCE,
      user_label: "Conflicting Evidence",
      explanation: observation === SAMPLE_OBSERVATION.VARIANT_PRESENT
        ? "Locus exhibits conflicting clinical interpretations or disputed utility (e.g. MTHFR). Variant allele detected."
        : "Locus exhibits conflicting clinical interpretations; wild-type baseline observed."
    };
  }
  if (observation === SAMPLE_OBSERVATION.VARIANT_PRESENT) {
    return {
      assay_coverage: assay,
      curation_scope: scope,
      evidence_sufficiency: evidence,
      sample_observation: observation,
      derived_state: COVERAGE_STATES.SUPPORTED_AND_OBSERVED,
      user_label: "Supported & Observed",
      explanation: "Curated locus with sufficient clinical consensus; variant/risk/actionable allele detected in sample."
    };
  }
  return {
    assay_coverage: assay,
    curation_scope: scope,
    evidence_sufficiency: evidence,
    sample_observation: observation,
    derived_state: COVERAGE_STATES.SUPPORTED_NOT_OBSERVED,
    user_label: "Tested Wild-Type",
    explanation: "Curated locus with sufficient clinical consensus; homozygous reference/wild-type detected in sample."
  };
}

export const EVIDENCE_TIERS = {
  TIER_A: "Tier A",
  TIER_B: "Tier B",
  TIER_C: "Tier C",
  TIER_D: "Tier D"
};

export const ABSENCE_OF_FINDING_GUARDRAIL = (
  "ABSENCE OF A FINDING DOES NOT IMPLY ABSENCE OF GENETIC RISK. " +
  "GenomePulse analyzes only targeted single-nucleotide polymorphisms interrogated by consumer arrays. " +
  "It does not perform full gene sequencing, does not analyze unprobed exonic or intronic regions, " +
  "and cannot detect large copy-number variations (CNVs), balanced translocations, or structural repeats."
);

export const INCOMPLETE_STAR_ALLELE_REFUSAL = (
  "Incomplete star-allele coverage refusal: Interrogating an isolated SNP (e.g. *2) cannot rule out " +
  "other active, decreased, or gain-of-function alleles (e.g. *3, *4, *17) not present on this array. " +
  "A full metabolizer phenotype cannot and will not be inferred without complete haplotype sequencing."
);


export const ACMG_SF_GENES = new Set([
  "ACTA2", "ACTC1", "APC", "APOB", "ATP7B", "BAG3", "BMPR1A", "BRCA1", "BRCA2", "BTD",
  "CACNA1S", "CALM1", "CALM2", "CALM3", "CASQ2", "COL3A1", "DES", "DSC2", "DSG2", "DSP",
  "ENG", "FBN1", "FLNC", "GAA", "GLA", "HFE", "HNF1A", "KCNH2", "KCNQ1", "LDLR",
  "LMNA", "MAX", "MEN1", "MLH1", "MSH2", "MSH6", "MYBPC3", "MYH11", "MYH7", "MYL2",
  "MYL3", "NF2", "OTC", "PALB2", "PCSK9", "PKP2", "PMS2", "PRKAG2", "PTEN", "RB1",
  "RBM20", "RET", "RIT1", "RYR1", "RYR2", "SCN5A", "SDHAF2", "SDHB", "SDHC", "SDHD",
  "SMAD3", "SMAD4", "STK11", "TGFBR1", "TGFBR2", "TMEM127", "TMEM43", "TNNC1", "TNNI3", "TNNT2",
  "TP53", "TPM1", "TRDN", "TSC1", "TSC2", "TTN", "TTR", "VCL", "VHL", "WT1"
]);

export const CURATED_KB = {
  // APOE - Alzheimer's / Atherosclerosis
  "rs429358": {
    gene: "APOE",
    chrom: "19",
    pos_grch37: 45411941,
    pos_grch38: 44908684,
    ref: "T",
    alt: "C",
    clinvar_id: "VCV000017864",
    clinvar_stars: 3,
    gnomad_af: 0.145,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "cerebral cortex": "Medium", "plasma": "High", "adrenal gland": "Medium" },
    hpa_subcellular: ["Secreted", "Endoplasmic reticulum"],
    genotypes: {
      "CC": {
        category: "Risk Factor",
        isCarrier: true,
        significance: "High Risk Factor",
        magnitude: 5.0,
        repute: "Bad",
        phenotype: "APOE \u03b54/\u03b54 homozygote: ~12-15\u00d7 elevated lifetime risk of late-onset Alzheimer's disease.",
        drug_response: null
      },
      "GG": {
        category: "Risk Factor",
        isCarrier: true,
        significance: "High Risk Factor",
        magnitude: 5.0,
        repute: "Bad",
        phenotype: "APOE \u03b54/\u03b54 homozygote (minus strand): ~12-15\u00d7 elevated lifetime risk of late-onset Alzheimer's disease.",
        drug_response: null
      },
      "CT": {
        category: "Carrier",
        isCarrier: true,
        significance: "Carrier / Risk Factor",
        magnitude: 3.8,
        repute: "Bad",
        phenotype: "APOE \u03b54 carrier (heterozygote \u03b53/\u03b54 or \u03b52/\u03b54): ~3-4\u00d7 elevated risk of late-onset Alzheimer's disease.",
        drug_response: null
      },
      "AG": {
        category: "Carrier",
        isCarrier: true,
        significance: "Carrier / Risk Factor",
        magnitude: 3.8,
        repute: "Bad",
        phenotype: "APOE \u03b54 carrier (minus strand AG): ~3-4\u00d7 elevated risk of late-onset Alzheimer's disease.",
        drug_response: null
      },
      "TT": {
        category: "Carrier",
        isCarrier: true,
        significance: "Normal / Baseline",
        magnitude: 1.2,
        repute: "Good",
        phenotype: "APOE \u03b53/\u03b53 or \u03b52 baseline non-\u03b54 carrier: neutral population average Alzheimer's risk.",
        drug_response: null
      },
      "AA": {
        category: "Carrier",
        isCarrier: true,
        significance: "Normal / Baseline",
        magnitude: 1.2,
        repute: "Good",
        phenotype: "APOE \u03b53/\u03b53 or \u03b52 baseline (minus strand AA): neutral population average Alzheimer's risk.",
        drug_response: null
      }
    }
  },

  "rs7412": {
    gene: "APOE",
    chrom: "19",
    pos_grch37: 45412079,
    pos_grch38: 44908822,
    ref: "C",
    alt: "T",
    clinvar_id: "VCV000017865",
    clinvar_stars: 3,
    gnomad_af: 0.078,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "cerebral cortex": "Medium", "plasma": "High" },
    hpa_subcellular: ["Secreted"],
    genotypes: {
      "TT": {
        category: "Carrier",
        isCarrier: true,
        significance: "Protective AD / Lipid Risk",
        magnitude: 3.5,
        repute: "Bad",
        phenotype: "APOE \u03b52/\u03b52: Associated with Type III Hyperlipoproteinemia (dysbetalipoproteinemia), but protective against Alzheimer's.",
        drug_response: null
      },
      "AA": {
        category: "Carrier",
        isCarrier: true,
        significance: "Protective AD / Lipid Risk",
        magnitude: 3.5,
        repute: "Bad",
        phenotype: "APOE \u03b52/\u03b52 (minus strand AA): Associated with Type III Hyperlipoproteinemia, but protective against Alzheimer's.",
        drug_response: null
      },
      "CT": {
        category: "Carrier",
        isCarrier: true,
        significance: "Protective / Carrier",
        magnitude: 2.0,
        repute: "Good",
        phenotype: "APOE \u03b52 carrier: modestly lower LDL cholesterol and slightly reduced Alzheimer's risk.",
        drug_response: null
      },
      "AG": {
        category: "Carrier",
        isCarrier: true,
        significance: "Protective / Carrier",
        magnitude: 2.0,
        repute: "Good",
        phenotype: "APOE \u03b52 carrier (minus strand AG): modestly lower LDL cholesterol and slightly reduced Alzheimer's risk.",
        drug_response: null
      },
      "CC": {
        category: "Carrier",
        isCarrier: true,
        significance: "Common / Benign",
        magnitude: 1.0,
        repute: "Good",
        phenotype: "Common allele encoding normal Arg176 (\u03b53/\u03b54 baseline).",
        drug_response: null
      },
      "GG": {
        category: "Carrier",
        isCarrier: true,
        significance: "Common / Benign",
        magnitude: 1.0,
        repute: "Good",
        phenotype: "Common allele encoding normal Arg176 (minus strand GG).",
        drug_response: null
      }
    }
  },

  // HFE - Hereditary Hemochromatosis
  "rs1800562": {
    gene: "HFE",
    chrom: "6",
    pos_grch37: 26093141,
    pos_grch38: 26092520,
    ref: "G",
    alt: "A",
    clinvar_id: "VCV000009404",
    clinvar_stars: 4,
    gnomad_af: 0.052,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "duodenum": "High", "spleen": "Medium", "placenta": "Medium" },
    hpa_subcellular: ["Plasma membrane", "Endoplasmic reticulum membrane"],
    genotypes: {
      "AA": {
        category: "Pathogenic",
        significance: "Pathogenic",
        magnitude: 5.5,
        repute: "Bad",
        phenotype: "HFE C282Y homozygote: Primary genetic cause of Hereditary Hemochromatosis (iron overload). Regular ferritin monitoring recommended.",
        drug_response: null
      },
      "AG": {
        category: "Carrier",
        significance: "Pathogenic (Carrier)",
        magnitude: 2.0,
        repute: "Good",
        phenotype: "Carrier for Hereditary Hemochromatosis (C282Y heterozygote). Low individual risk unless compound heterozygous with H63D.",
        drug_response: null
      },
      "GG": {
        category: "Benign",
        significance: "Benign",
        magnitude: 0.0,
        repute: "Good",
        phenotype: "Normal wild-type HFE.",
        drug_response: null
      }
    }
  },

  "rs1799945": {
    gene: "HFE",
    chrom: "6",
    pos_grch37: 26092913,
    pos_grch38: 26092292,
    ref: "C",
    alt: "G",
    clinvar_id: "VCV000009405",
    clinvar_stars: 3,
    gnomad_af: 0.135,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "duodenum": "High" },
    hpa_subcellular: ["Plasma membrane"],
    genotypes: {
      "GG": {
        category: "Risk Factor",
        significance: "Risk Factor",
        magnitude: 2.5,
        repute: "Bad",
        phenotype: "HFE H63D homozygote: Slight predisposition to mildly elevated serum ferritin.",
        drug_response: null
      },
      "CG": {
        category: "Carrier",
        significance: "Risk Factor (Carrier)",
        magnitude: 1.0,
        repute: "Good",
        phenotype: "HFE H63D carrier: common variant with minimal clinical significance unless paired with C282Y.",
        drug_response: null
      }
    }
  },

  // F5 - Factor V Leiden (Thrombophilia)
  "rs6025": {
    gene: "F5",
    chrom: "1",
    pos_grch37: 169519049,
    pos_grch38: 169549811,
    ref: "G",
    alt: "A",
    clinvar_id: "VCV000009407",
    clinvar_stars: 4,
    gnomad_af: 0.021,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "plasma": "High" },
    hpa_subcellular: ["Secreted"],
    genotypes: {
      "AA": {
        category: "Pathogenic",
        significance: "Pathogenic",
        magnitude: 6.0,
        repute: "Bad",
        phenotype: "Factor V Leiden homozygote: 50-80\u00d7 markedly increased risk of venous thromboembolism (VTE/DVT/PE).",
        drug_response: null
      },
      "AG": {
        category: "Risk Factor",
        significance: "Pathogenic",
        magnitude: 4.0,
        repute: "Bad",
        phenotype: "Factor V Leiden heterozygote: 4-8\u00d7 increased risk of venous thromboembolism. Caution with oral contraceptives or prolonged immobility.",
        drug_response: null
      },
      "GG": {
        category: "Benign",
        significance: "Benign",
        magnitude: 0.0,
        repute: "Good",
        phenotype: "Normal Factor V genotype.",
        drug_response: null
      }
    }
  },

  // F2 - Prothrombin Thrombophilia
  "rs1799963": {
    gene: "F2",
    chrom: "11",
    pos_grch37: 46761055,
    pos_grch38: 46739493,
    ref: "G",
    alt: "A",
    clinvar_id: "VCV000009406",
    clinvar_stars: 4,
    gnomad_af: 0.012,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "plasma": "High" },
    hpa_subcellular: ["Secreted"],
    genotypes: {
      "AA": {
        category: "Pathogenic",
        significance: "Pathogenic",
        magnitude: 5.5,
        repute: "Bad",
        phenotype: "Prothrombin G20210A homozygote: ~10\u00d7 increased risk of thrombosis.",
        drug_response: null
      },
      "AG": {
        category: "Risk Factor",
        significance: "Pathogenic",
        magnitude: 3.5,
        repute: "Bad",
        phenotype: "Prothrombin G20210A heterozygote: 2-3\u00d7 increased risk of venous blood clots.",
        drug_response: null
      },
      "GG": {
        category: "Benign",
        significance: "Benign",
        magnitude: 0.0,
        repute: "Good",
        phenotype: "Normal wild-type Prothrombin.",
        drug_response: null
      }
    }
  },

  // CFTR - Cystic Fibrosis
  "rs113993960": {
    gene: "CFTR",
    chrom: "7",
    pos_grch37: 117199644,
    pos_grch38: 117559590,
    ref: "CTT",
    alt: "C",
    clinvar_id: "VCV000007105",
    clinvar_stars: 4,
    gnomad_af: 0.015,
    gnomad_pli: 0.0,
    hpa_tissues: { "pancreas": "High", "lung": "High", "duodenum": "High", "colon": "High", "gallbladder": "High" },
    hpa_subcellular: ["Plasma membrane"],
    genotypes: {
      "DD": {
        category: "Pathogenic",
        significance: "Pathogenic",
        magnitude: 7.0,
        repute: "Bad",
        phenotype: "Cystic Fibrosis (\u0394F508 homozygote): Classic severe cystic fibrosis affecting lungs and digestive system.",
        drug_response: null
      },
      "DI": {
        category: "Carrier",
        significance: "Pathogenic (Carrier)",
        magnitude: 2.5,
        repute: "Good",
        phenotype: "Cystic Fibrosis Carrier (\u0394F508 heterozygote). Asymptomatic carrier; 1 in 4 risk with carrier partner.",
        drug_response: null
      }
    }
  },

  // CYP2C19 - Clopidogrel (Plavix) Metabolism
  "rs4244285": {
    gene: "CYP2C19",
    chrom: "10",
    pos_grch37: 96541604,
    pos_grch38: 94775440,
    ref: "G",
    alt: "A",
    clinvar_id: "VCV000015049",
    clinvar_stars: 4,
    gnomad_af: 0.150,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "duodenum": "Medium" },
    hpa_subcellular: ["Endoplasmic reticulum membrane"],
    genotypes: {
      "AA": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 4.5,
        repute: "Bad",
        phenotype: "CYP2C19 Poor Metabolizer (*2/*2): Significantly impaired clopidogrel activation. Alternative antiplatelet (ticagrelor/prasugrel) strongly indicated by CPIC.",
        drug_response: "Clopidogrel: Poor Metabolizer (Alternative drug recommended)"
      },
      "AG": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 3.0,
        repute: "Bad",
        phenotype: "CYP2C19 Intermediate Metabolizer (*1/*2): Reduced clopidogrel activation; CPIC recommends alternative agent for acute coronary syndrome.",
        drug_response: "Clopidogrel: Intermediate Metabolizer (Reduced activation)"
      },
      "GG": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 0.0,
        repute: "Good",
        phenotype: "CYP2C19 Normal Metabolizer (*1/*1): Standard clopidogrel dosing.",
        drug_response: "Clopidogrel: Normal Metabolizer"
      }
    }
  },

  // VKORC1 - Warfarin Sensitivity
  "rs9923231": {
    gene: "VKORC1",
    chrom: "16",
    pos_grch37: 31107689,
    pos_grch38: 31096368,
    ref: "C",
    alt: "T",
    clinvar_id: "VCV000015052",
    clinvar_stars: 4,
    gnomad_af: 0.380,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "placenta": "Medium" },
    hpa_subcellular: ["Endoplasmic reticulum membrane"],
    genotypes: {
      "AA": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 4.0,
        repute: "Bad",
        phenotype: "High Warfarin sensitivity (-1639A/A): Significantly lower dose required to prevent bleeding complications.",
        drug_response: "Warfarin: High Sensitivity (50-60% lower initial dose)"
      },
      "AG": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 2.5,
        repute: "Bad",
        phenotype: "Intermediate Warfarin sensitivity: Moderate dose reduction typically required.",
        drug_response: "Warfarin: Intermediate Sensitivity (20-30% lower dose)"
      },
      "GG": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 0.0,
        repute: "Good",
        phenotype: "Normal Warfarin sensitivity: Standard clinical titration.",
        drug_response: "Warfarin: Normal Sensitivity"
      }
    }
  },

  // SLCO1B1 - Statin-Induced Myopathy
  "rs4149056": {
    gene: "SLCO1B1",
    chrom: "12",
    pos_grch37: 21331549,
    pos_grch38: 21178615,
    ref: "T",
    alt: "C",
    clinvar_id: "VCV000015050",
    clinvar_stars: 4,
    gnomad_af: 0.140,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High" },
    hpa_subcellular: ["Plasma membrane"],
    genotypes: {
      "CC": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 4.5,
        repute: "Bad",
        phenotype: "Poor SLCO1B1 transporter function (521C/C): ~17\u00d7 higher risk of simvastatin-induced myopathy/rhabdomyolysis.",
        drug_response: "Simvastatin: High Myopathy Risk (Prescribe rosuvastatin/pravastatin)"
      },
      "CT": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 3.0,
        repute: "Bad",
        phenotype: "Intermediate SLCO1B1 function: 4.5\u00d7 elevated risk of simvastatin-induced myopathy.",
        drug_response: "Simvastatin: Moderate Myopathy Risk (Limit dose to \u226420mg)"
      },
      "TT": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 0.0,
        repute: "Good",
        phenotype: "Normal SLCO1B1 function: Standard statin tolerance.",
        drug_response: "Simvastatin: Normal"
      }
    }
  },

  // DPYD - Fluorouracil (5-FU) / Capecitabine Toxicity
  "rs3918290": {
    gene: "DPYD",
    chrom: "1",
    pos_grch37: 97915614,
    pos_grch38: 97450058,
    ref: "C",
    alt: "T",
    clinvar_id: "VCV000015053",
    clinvar_stars: 4,
    gnomad_af: 0.006,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "kidney": "Medium", "colon": "Medium" },
    hpa_subcellular: ["Cytosol"],
    genotypes: {
      "TT": {
        category: "Pharmacogenomics",
        significance: "Drug Response (Critical)",
        magnitude: 6.5,
        repute: "Bad",
        phenotype: "DPYD Complete Deficiency (*2A/*2A): Fatal toxicity with standard 5-FU/capecitabine chemotherapy. Alternate therapy required.",
        drug_response: "5-Fluorouracil / Capecitabine: Complete Deficiency (Contraindicated)"
      },
      "CT": {
        category: "Pharmacogenomics",
        significance: "Drug Response",
        magnitude: 5.0,
        repute: "Bad",
        phenotype: "DPYD Partial Deficiency (*2A heterozygote): High risk of life-threatening neutropenia and mucositis. CPIC mandates \u226550% dose reduction.",
        drug_response: "5-Fluorouracil / Capecitabine: Intermediate (Reduce dose \u226550%)"
      }
    }
  },

  // MTHFR - Folate & Homocysteine
  "rs1801133": {
    gene: "MTHFR",
    chrom: "1",
    pos_grch37: 11856378,
    pos_grch38: 11796321,
    ref: "G",
    alt: "A",
    clinvar_id: "VCV000003521",
    clinvar_stars: 3,
    gnomad_af: 0.310,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "kidney": "Medium", "cerebral cortex": "Medium" },
    hpa_subcellular: ["Cytosol", "Nucleus"],
    genotypes: {
      "AA": {
        category: "Trait",
        significance: "Trait",
        magnitude: 2.0,
        repute: "Bad",
        phenotype: "MTHFR 677TT homozygote (~30% residual enzyme activity): Predisposition to elevated homocysteine if folate intake is deficient.",
        drug_response: null
      },
      "AG": {
        category: "Trait",
        significance: "Trait",
        magnitude: 1.0,
        repute: "Good",
        phenotype: "MTHFR 677CT heterozygote (~65% normal enzyme activity): Generally benign with normal dietary folate.",
        drug_response: null
      }
    }
  },

  // MCM6 / LCT - Lactase Persistence
  "rs4988235": {
    gene: "MCM6 / LCT",
    chrom: "2",
    pos_grch37: 136608646,
    pos_grch38: 135851076,
    ref: "G",
    alt: "A",
    clinvar_id: "VCV000015051",
    clinvar_stars: 3,
    gnomad_af: 0.480,
    gnomad_pli: 0.0,
    hpa_tissues: { "small intestine": "High", "duodenum": "High" },
    hpa_subcellular: ["Plasma membrane"],
    genotypes: {
      "AA": {
        category: "Trait",
        significance: "Trait",
        magnitude: 1.5,
        repute: "Good",
        phenotype: "Lactase persistent: Capable of digesting dairy lactose normally in adulthood.",
        drug_response: null
      },
      "AG": {
        category: "Trait",
        significance: "Trait",
        magnitude: 1.0,
        repute: "Good",
        phenotype: "Lactase persistent: Tolerates dairy lactose well.",
        drug_response: null
      },
      "GG": {
        category: "Trait",
        significance: "Trait",
        magnitude: 1.5,
        repute: "Bad",
        phenotype: "Lactose non-persistent (primary adult hypolactasia): Susceptible to lactose intolerance symptoms.",
        drug_response: null
      }
    }
  },

  // ALDH2 - Alcohol Metabolism / Flush
  "rs671": {
    gene: "ALDH2",
    chrom: "12",
    pos_grch37: 112241766,
    pos_grch38: 111803962,
    ref: "G",
    alt: "A",
    clinvar_id: "VCV000018390",
    clinvar_stars: 4,
    gnomad_af: 0.055,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "kidney": "High", "heart muscle": "Medium" },
    hpa_subcellular: ["Mitochondria"],
    genotypes: {
      "AA": {
        category: "Trait",
        significance: "Risk Factor",
        magnitude: 4.0,
        repute: "Bad",
        phenotype: "ALDH2*2 homozygote (near-zero acetaldehyde dehydrogenase activity): Severe alcohol flush reaction, nausea, and increased esophageal cancer risk with alcohol consumption.",
        drug_response: null
      },
      "AG": {
        category: "Trait",
        significance: "Risk Factor",
        magnitude: 2.5,
        repute: "Bad",
        phenotype: "ALDH2*2 heterozygote (~20-40% enzyme activity): Marked facial flushing, tachycardia, and acetaldehyde accumulation after alcohol consumption.",
        drug_response: null
      },
      "GG": {
        category: "Benign",
        significance: "Benign",
        magnitude: 0.0,
        repute: "Good",
        phenotype: "Normal ALDH2 wild-type activity.",
        drug_response: null
      }
    }
  }
};

// ===========================================================================
// Gene Inheritance & Mendelian Segregation Catalog
// ===========================================================================
export const GENE_INHERITANCE_CATALOG = {
  "CFTR": {
    mode: "Autosomal Recessive",
    disease: "Cystic Fibrosis",
    omim: "219700",
    carrier_freq_nfe: 0.04,
    carrier_freq_global: 0.02,
    penetrance: 1.0,
    description: "Impaired CFTR chloride channel, causing viscous mucus in respiratory and GI tracts."
  },
  "HFE": {
    mode: "Autosomal Recessive",
    disease: "Hereditary Hemochromatosis Type 1",
    omim: "235200",
    carrier_freq_nfe: 0.10,
    carrier_freq_global: 0.04,
    penetrance: 0.20,
    description: "Excess intestinal iron absorption with hepatic/cardiac storage.",
    compound_heterozygote_pairs: [["rs1800562", "rs1799945"]]
  },
  "F5": {
    mode: "Autosomal Dominant / Incomplete Dominant",
    disease: "Thrombophilia due to Factor V Leiden",
    omim: "188055",
    carrier_freq_nfe: 0.05,
    carrier_freq_global: 0.02,
    penetrance: 0.10,
    description: "Resistance to activated protein C leading to 4–8× increased venous thromboembolism risk."
  },
  "F2": {
    mode: "Autosomal Dominant / Incomplete Dominant",
    disease: "Thrombophilia due to Prothrombin G20210A",
    omim: "176930",
    carrier_freq_nfe: 0.025,
    carrier_freq_global: 0.015,
    penetrance: 0.08,
    description: "Elevated prothrombin expression and venous thrombosis predisposition."
  },
  "CYP2C19": {
    mode: "Codominant Pharmacogenomic",
    disease: "Clopidogrel / Antidepressant Metabolism",
    omim: "124020",
    carrier_freq_nfe: 0.28,
    carrier_freq_global: 0.35,
    penetrance: 1.0,
    description: "Altered bioactivation of clopidogrel prodrug into active platelet-inhibiting metabolite."
  },
  "SLCO1B1": {
    mode: "Codominant Pharmacogenomic",
    disease: "Statin-Induced Myopathy Sensitivity",
    omim: "604843",
    carrier_freq_nfe: 0.25,
    carrier_freq_global: 0.20,
    penetrance: 0.40,
    description: "Hepatic OATP1B1 transporter deficiency causes elevated plasma statin exposure."
  },
  "VKORC1": {
    mode: "Codominant Pharmacogenomic",
    disease: "Warfarin Sensitivity",
    omim: "608547",
    carrier_freq_nfe: 0.38,
    carrier_freq_global: 0.45,
    penetrance: 1.0,
    description: "Altered vitamin K epoxide reductase promoter sensitivity to warfarin inhibition."
  },
  "APOE": {
    mode: "Co-Dominant Complex Alleles (ε2/ε3/ε4)",
    disease: "Late-Onset Alzheimer's Disease & Dysbetalipoproteinemia",
    omim: "107741",
    carrier_freq_nfe: 0.25,
    carrier_freq_global: 0.22,
    penetrance: 0.60,
    description: "Apolipoprotein E lipid transport and amyloid-beta clearance kinetics."
  },
  "MTHFR": {
    mode: "Autosomal Recessive / Biomarker Modifier",
    disease: "Homocysteine & Folate Metabolism Variation",
    omim: "607093",
    carrier_freq_nfe: 0.45,
    carrier_freq_global: 0.35,
    penetrance: 0.05,
    description: "Thermolabile enzyme variant with modest reduction in 5-MTHF synthesis."
  },
  "ALDH2": {
    mode: "Autosomal Dominant / Incomplete Dominant",
    disease: "Alcohol Flush Reaction / Acetaldehyde Toxicity",
    omim: "100650",
    carrier_freq_nfe: 0.001,
    carrier_freq_global: 0.08,
    penetrance: 0.95,
    description: "Dominant negative Glu504Lys inactivation of mitochondrial aldehyde dehydrogenase."
  }
};

// ===========================================================================
// Deep Biotools Multi-Source Insights (ClinVar, Ensembl, AlphaFold, ENCODE)
// ===========================================================================
export const BIOTOOLS_GENE_INSIGHTS = {
  "APOE": {
    uniprot_id: "P02649",
    alphafold: {
      global_plddt: 75.5,
      folding_status: "Structured Core with Flexible Termini",
      domains: [
        "Domain 1 (Receptor-binding): residues 40–187 (Length: 148 AAs)",
        "Domain 2 (Lipid-binding): residues 219–305 (Length: 87 AAs)"
      ],
      flexible_joints: "Residues 188–218 form a hinge region mediating lipid vesicle interaction"
    },
    ensembl: {
      ensg: "ENSG00000130203",
      canonical_transcript: "ENST00000252486 (MANE Select)",
      sift_prediction: "tolerated (1.0)",
      alphamissense_class: "likely_benign",
      alphamissense_pathogenicity: 0.0365,
      loeuf: 1.26
    },
    encode: {
      top_tissues: { "liver": 4615.5, "adrenal gland": 3591.9, "heart": 2336.0, "brain": 1166.3, "kidney": 1321.3 }
    }
  },
  "HFE": {
    uniprot_id: "P55899",
    alphafold: {
      global_plddt: 86.4,
      folding_status: "Confidently Folded MHC-like α1/α2/α3 Domains",
      domains: [
        "Domain 1 (α1/α2 domains): residues 23–204 (Length: 182 AAs)",
        "Domain 2 (α3 domain): residues 205–297 (Length: 93 AAs)"
      ],
      flexible_joints: "Transmembrane anchor (residues 307–337)"
    },
    ensembl: {
      ensg: "ENSG00000010704",
      canonical_transcript: "ENST00000357618 (MANE Select)",
      sift_prediction: "deleterious (0.00)",
      alphamissense_class: "likely_pathogenic",
      alphamissense_pathogenicity: 0.842,
      loeuf: 0.82
    },
    encode: {
      top_tissues: { "liver": 1820.4, "duodenum": 1410.2, "spleen": 950.1, "bone marrow": 820.6 }
    }
  },
  "F5": {
    uniprot_id: "P12259",
    alphafold: {
      global_plddt: 82.1,
      folding_status: "Multi-domain Coagulation Factor",
      domains: [
        "A1 Domain: residues 29–335",
        "A2 Domain: residues 336–684",
        "A3-C1-C2 Domains: residues 1546–2224"
      ],
      flexible_joints: "B-domain (residues 685–1545) is heavily intrinsically disordered"
    },
    ensembl: {
      ensg: "ENSG00000198734",
      canonical_transcript: "ENST00000367520 (MANE Select)",
      sift_prediction: "tolerated (0.28)",
      alphamissense_class: "ambiguous / pathogenic (APC cleavage resistant)",
      alphamissense_pathogenicity: 0.612,
      loeuf: 0.74
    },
    encode: {
      top_tissues: { "liver": 5420.0, "plasma": 4890.2 }
    }
  },
  "F2": {
    uniprot_id: "P00734",
    alphafold: {
      global_plddt: 89.2,
      folding_status: "Serine Protease Proenzyme",
      domains: [
        "Gla Domain: residues 44–89",
        "Kringle Domains: residues 109–284",
        "Peptidase S1: residues 328–622"
      ],
      flexible_joints: "Inter-kringle linker segments"
    },
    ensembl: {
      ensg: "ENSG00000188404",
      canonical_transcript: "ENST00000344445 (MANE Select)",
      sift_prediction: "N/A (3' UTR regulatory variant)",
      alphamissense_class: "N/A (elevates mRNA cleavage/polyadenylation)",
      alphamissense_pathogenicity: null,
      loeuf: 0.68
    },
    encode: {
      top_tissues: { "liver": 8940.0 }
    }
  },
  "CFTR": {
    uniprot_id: "P13569",
    alphafold: {
      global_plddt: 84.8,
      folding_status: "12-Transmembrane ABC Transporter",
      domains: [
        "TMD1 & NBD1: residues 1–650 (NBD1 contains deltaF508 at position 508)",
        "Regulatory (R) Domain: residues 651–843 (intrinsically disordered)",
        "TMD2 & NBD2: residues 844–1480"
      ],
      flexible_joints: "R domain acts as dynamic phosphorylation-regulated switch"
    },
    ensembl: {
      ensg: "ENSG00000001626",
      canonical_transcript: "ENST00000003084 (MANE Select)",
      sift_prediction: "inframe deletion (deltaF508)",
      alphamissense_class: "pathogenic (misfolding & ERAD degradation)",
      alphamissense_pathogenicity: 0.985,
      loeuf: 0.44
    },
    encode: {
      top_tissues: { "lung": 450.2, "pancreas": 780.5, "colon": 610.1 }
    }
  },
  "DPYD": {
    uniprot_id: "Q12882",
    alphafold: {
      global_plddt: 88.7,
      folding_status: "5-Domain Heterotetramer-equivalent Catalytic Dimer",
      domains: [
        "Domain I (4Fe-4S Cluster): residues 1–172",
        "Domain II (FAD-binding): residues 173–286",
        "Domain III (NADPH-binding): residues 287–524",
        "Domain IV (Pyrimidine-binding core): residues 525–847",
        "Domain V (Second 4Fe-4S Cluster): residues 848–1025"
      ],
      flexible_joints: "Interdomain linkers coordinate electron transfer between flavin centers"
    },
    ensembl: {
      ensg: "ENSG00000188641",
      canonical_transcript: "ENST00000370192 (MANE Select)",
      sift_prediction: "deleterious (0.00)",
      alphamissense_class: "pathogenic (*2A splice disruption)",
      alphamissense_pathogenicity: 0.965,
      loeuf: 0.58
    },
    encode: {
      top_tissues: { "liver": 3210.5, "small intestine": 1140.2, "colon": 845.0 }
    }
  },
  "SLCO1B1": {
    uniprot_id: "Q9Y6L6",
    alphafold: {
      global_plddt: 85.3,
      folding_status: "12-Transmembrane MFS Superfamily Transporter",
      domains: [
        "TMD 1–6 (N-terminal bundle): residues 1–280",
        "Extracellular Loop 5 (Disulfide stabilized): residues 115–230",
        "TMD 7–12 (C-terminal bundle): residues 281–691"
      ],
      flexible_joints: "Central rocker-switch substrate translocation cavity"
    },
    ensembl: {
      ensg: "ENSG00000134538",
      canonical_transcript: "ENST00000256958 (MANE Select)",
      sift_prediction: "deleterious (0.02)",
      alphamissense_class: "likely_pathogenic (Val174Ala)",
      alphamissense_pathogenicity: 0.792,
      loeuf: 0.62
    },
    encode: {
      top_tissues: { "liver": 6420.0, "gallbladder": 310.2 }
    }
  },
  "CYP2C19": {
    uniprot_id: "P33261",
    alphafold: {
      global_plddt: 91.8,
      folding_status: "High-Confidence Cytochrome P450 Monooxygenase",
      domains: [
        "Transmembrane Anchor: residues 1–44",
        "Catalytic P450 Core: residues 45–490 (Heme-binding Cys435)"
      ],
      flexible_joints: "Substrate recognition loops B-C and F-G"
    },
    ensembl: {
      ensg: "ENSG00000165841",
      canonical_transcript: "ENST00000371401 (MANE Select)",
      sift_prediction: "deleterious (0.00)",
      alphamissense_class: "pathogenic (*2 splice defect / *3 stop)",
      alphamissense_pathogenicity: 0.941,
      loeuf: 0.72
    },
    encode: {
      top_tissues: { "liver": 3840.1, "small intestine": 410.5 }
    }
  },
  "VKORC1": {
    uniprot_id: "Q9BQB6",
    alphafold: {
      global_plddt: 88.5,
      folding_status: "4-Transmembrane Helical Bundle",
      domains: [
        "Helices 1–4: residues 10–160 (Active site Cys132-Cys135 redox triad)"
      ],
      flexible_joints: "ER luminal loop 1 (residues 31–78)"
    },
    ensembl: {
      ensg: "ENSG00000167397",
      canonical_transcript: "ENST00000394985 (MANE Select)",
      sift_prediction: "N/A (Promoter -1639G>A regulatory variant)",
      alphamissense_class: "N/A (Altered transcription factor binding)",
      alphamissense_pathogenicity: null,
      loeuf: 0.65
    },
    encode: {
      top_tissues: { "liver": 2950.4, "placenta": 620.1 }
    }
  },
  "MTHFR": {
    uniprot_id: "P42417",
    alphafold: {
      global_plddt: 87.2,
      folding_status: "Two-Domain Folate-Metabolizing Homodimer",
      domains: [
        "N-terminal Catalytic TIM Barrel: residues 1–356",
        "C-terminal Regulatory SAM-binding Domain: residues 357–656"
      ],
      flexible_joints: "Interdomain linker (residues 338–362; Ala222Val alters thermal stability)"
    },
    ensembl: {
      ensg: "ENSG00000185010",
      canonical_transcript: "ENST00000376585 (MANE Select)",
      sift_prediction: "tolerated (0.34)",
      alphamissense_class: "likely_benign (thermolabile modifier)",
      alphamissense_pathogenicity: 0.215,
      loeuf: 0.54
    },
    encode: {
      top_tissues: { "liver": 1650.0, "kidney": 1210.3, "brain": 720.4 }
    }
  },
  "ALDH2": {
    uniprot_id: "P05091",
    alphafold: {
      global_plddt: 93.4,
      folding_status: "High-Confidence Homotetrameric Mitochondrial Dehydrogenase",
      domains: [
        "NAD-binding Rossmann Fold: residues 1–135",
        "Catalytic Subunit: residues 136–470",
        "Oligomerization Interface: residues 471–517 (Glu504Lys disrupts tetramer)"
      ],
      flexible_joints: "Coenzyme-binding entrance loop"
    },
    ensembl: {
      ensg: "ENSG00000111275",
      canonical_transcript: "ENST00000261733 (MANE Select)",
      sift_prediction: "deleterious (0.00)",
      alphamissense_class: "pathogenic (Glu504Lys dominant negative)",
      alphamissense_pathogenicity: 0.912,
      loeuf: 0.61
    },
    encode: {
      top_tissues: { "liver": 5670.2, "heart": 1840.0, "kidney": 1420.5 }
    }
  },
  "BRCA1": {
    uniprot_id: "P38398",
    alphafold: {
      global_plddt: 62.5,
      folding_status: "Structured Termini with Large Disordered Central Scaffold",
      domains: [
        "RING Finger E3 Ubiquitin Ligase: residues 1–103",
        "BRCT Tandem Repeats: residues 1642–1855"
      ],
      flexible_joints: "Central disordered region (residues 104–1641) binds DNA damage response complexes"
    },
    ensembl: {
      ensg: "ENSG00000012048",
      canonical_transcript: "ENST00000357654 (MANE Select)",
      sift_prediction: "deleterious (0.00)",
      alphamissense_class: "pathogenic",
      alphamissense_pathogenicity: 0.942,
      loeuf: 0.12
    },
    encode: {
      top_tissues: { "testis": 215.3, "ovary": 142.1, "breast": 118.5 }
    }
  },
  "BRCA2": {
    uniprot_id: "P51587",
    alphafold: {
      global_plddt: 58.2,
      folding_status: "Helical DNA-Binding Domain with Flexible BRC Repeats",
      domains: [
        "BRC RAD51-Binding Repeats: residues 1002–2082",
        "Helical & OB-Fold DNA-Binding Domain: residues 2482–3184"
      ],
      flexible_joints: "N-terminal scaffold (residues 1–1000)"
    },
    ensembl: {
      ensg: "ENSG00000139618",
      canonical_transcript: "ENST00000380152 (MANE Select)",
      sift_prediction: "deleterious (0.00)",
      alphamissense_class: "pathogenic",
      alphamissense_pathogenicity: 0.924,
      loeuf: 0.18
    },
    encode: {
      top_tissues: { "testis": 185.0, "ovary": 110.2, "breast": 95.4 }
    }
  }
};

/**
 * Compute Mendelian Segregation and Transmission Risk for a variant.
 */
export function computeSegregationReport(gene, genotype, category, significance) {
  const catalog = GENE_INHERITANCE_CATALOG[gene] || {
    mode: "Unknown / Complex",
    disease: `Associated with ${gene}`,
    omim: "N/A",
    carrier_freq_nfe: 0.01,
    penetrance: 0.50
  };

  const mode = catalog.mode;
  const penetrance = catalog.penetrance || 1.0;
  const carrierPrior = catalog.carrier_freq_nfe || 0.02;

  let isCarrier = false;
  let isAffected = false;
  let riskUnscreened = 0.0;
  let riskCarrier = 0.0;

  const isHet = genotype.length === 2 && genotype[0] !== genotype[1];
  const isHom = genotype.length === 2 && genotype[0] === genotype[1];

  if (mode.includes("Recessive")) {
    if (isHet) {
      isCarrier = true;
      riskCarrier = 0.25; // 1 in 4
      riskUnscreened = Math.round(carrierPrior * 0.25 * 1000) / 1000;
    } else if (isHom && (significance.includes("Pathogenic") || category === "Pathogenic")) {
      isAffected = true;
      riskCarrier = 0.50;
      riskUnscreened = Math.round(carrierPrior * 0.50 * 1000) / 1000;
    }
  } else if (mode.includes("Dominant")) {
    if (isHet || isHom) {
      isAffected = true;
      riskCarrier = 0.50;
      riskUnscreened = 0.50;
    }
  }

  return {
    gene,
    disease: catalog.disease,
    mode,
    omim: catalog.omim,
    is_carrier: isCarrier,
    is_affected: isAffected,
    penetrance,
    partner_carrier_prior: carrierPrior,
    offspring_risk_unscreened: riskUnscreened,
    offspring_risk_carrier: riskCarrier,
    biotools: BIOTOOLS_GENE_INSIGHTS[gene] || null
  };
}

/**
 * Detect compound heterozygosity (e.g. HFE C282Y + H63D).
 */
export function detectCompoundHeterozygosity(findings) {
  const hits = [];
  const map = {};
  for (const f of findings) {
    if (f.rsid) map[f.rsid] = f;
  }

  // HFE C282Y (rs1800562) + H63D (rs1799945)
  const hfe1 = map["rs1800562"];
  const hfe2 = map["rs1799945"];
  if (hfe1 && hfe2) {
    const gt1 = (hfe1.genotype || "").toUpperCase();
    const gt2 = (hfe2.genotype || "").toUpperCase();
    const isHet1 = ["AG", "GA", "CT", "TC"].includes(gt1);
    const isHet2 = ["CG", "GC"].includes(gt2);

    if (isHet1 && isHet2) {
      hits.push({
        gene: "HFE",
        title: "Compound Heterozygote (C282Y / H63D)",
        significance: "Pathogenic / Moderate Hemochromatosis Risk",
        summary: "Carries one C282Y mutation and one H63D mutation on separate chromosomes (trans phase). Confers 1.5–3× increased risk of iron overload.",
        segregation_notes: "Trans Phase Segregation: 50% probability of passing C282Y and 50% probability of passing H63D to each child."
      });
    }
  }

  return hits;
}

/**
 * Calculate multi-locus independent assortment for unlinked chromosomes.
 */
export function computeIndependentAssortment(findings) {
  const assortmentList = [];
  const map = {};
  for (const f of findings) {
    if (f.rsid) map[f.rsid] = f;
  }

  // Factor V Leiden (rs6025 on chr 1) + Prothrombin G20210A (rs1799963 on chr 11)
  const f5 = map["rs6025"];
  const f2 = map["rs1799963"];
  if (f5 && f2) {
    const isF5Risk = ["AG", "GA", "AA"].includes(f5.genotype);
    const isF2Risk = ["AG", "GA", "AA"].includes(f2.genotype);

    if (isF5Risk && isF2Risk) {
      assortmentList.push({
        genes: ["F5", "F2"],
        loci: ["rs6025 (Chr 1)", "rs1799963 (Chr 11)"],
        type: "Synergistic Dual Thrombophilia",
        joint_transmission_prob: 0.25, // 0.5 * 0.5
        description: "Mendelian Independent Assortment: F5 (Chr 1) and F2 (Chr 11) segregate independently on separate chromosomes. Carrying both risk alleles synergistically multiplies venous thrombosis risk by 20–40×. Offspring have a 25% independent probability of inheriting both risk factors."
      });
    }
  }

  return assortmentList;
}

/**
 * Pedigree simulator for offspring genotypes given partner status.
 */
export function simulateOffspringPedigree(gene, partnerStatus = "unscreened") {
  const cat = GENE_INHERITANCE_CATALOG[gene] || {
    mode: "Autosomal Recessive",
    penetrance: 1.0,
    carrier_freq_nfe: 0.02
  };

  const mode = cat.mode;
  const carrierPrior = cat.carrier_freq_nfe || 0.02;
  const penetrance = cat.penetrance || 1.0;

  if (mode.includes("Recessive")) {
    let pAffected = 0.0;
    let pCarrier = 0.50;
    let pWildtype = 0.50;

    if (partnerStatus === "carrier") {
      pAffected = 0.25;
      pCarrier = 0.50;
      pWildtype = 0.25;
    } else if (partnerStatus === "affected") {
      pAffected = 0.50;
      pCarrier = 0.50;
      pWildtype = 0.00;
    } else if (partnerStatus === "wildtype") {
      pAffected = 0.00;
      pCarrier = 0.50;
      pWildtype = 0.50;
    } else {
      // unscreened
      pAffected = Math.round(carrierPrior * 0.25 * 1000) / 1000;
      pCarrier = 0.50;
      pWildtype = Math.max(0, 1.0 - pAffected - pCarrier);
    }

    return {
      mode: "Autosomal Recessive",
      partnerStatus,
      pAffected: Math.round(pAffected * 100),
      pCarrier: Math.round(pCarrier * 100),
      pWildtype: Math.round(pWildtype * 100),
      effectiveClinicalRisk: Math.round(pAffected * penetrance * 100)
    };
  } else if (mode.includes("Dominant")) {
    const pTransmits = 0.50;
    return {
      mode: "Autosomal Dominant",
      partnerStatus,
      pAffected: Math.round(pTransmits * 100),
      pCarrier: 0,
      pWildtype: 50,
      effectiveClinicalRisk: Math.round(pTransmits * penetrance * 100)
    };
  }

  return {
    mode: "Complex / Pharmacogenomic",
    partnerStatus,
    pAffected: 0,
    pCarrier: 50,
    pWildtype: 50,
    effectiveClinicalRisk: 0
  };
}
