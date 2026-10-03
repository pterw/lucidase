/**
 * GenomePulse - inheritance catalog and segregation helpers (transitional)
 * =======================================================================
 * The curated variant records, ACMG gene flags, gene insights and coverage constants now
 * live in the pipeline knowledge base (web/src/knowledge-base.json, validated by
 * core/kb.js) and in core/coverage.js. What remains here is the legacy inheritance catalog
 * and the segregation functions, which T8 replaces with core/inheritance.js.
 */

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
    offspring_risk_carrier: riskCarrier
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
