/**
 * GenomePulse - High-Performance Genomic Web Worker
 * =================================================
 * Runs off the main UI thread to parse 1,000,000-line raw genotyping files
 * (23andMe, AncestryDNA, MyHeritage, VCF) without freezing the browser.
 */

import { 
  CURATED_KB, 
  ACMG_SF_GENES, 
  COVERAGE_STATES,
  ASSAY_COVERAGE,
  CURATION_SCOPE,
  EVIDENCE_SUFFICIENCY,
  SAMPLE_OBSERVATION,
  deriveCoverageEvaluation,
  EVIDENCE_TIERS,
  ABSENCE_OF_FINDING_GUARDRAIL,
  computeSegregationReport, 
  detectCompoundHeterozygosity, 
  computeIndependentAssortment 
} from "./knowledge-base.js";

self.onmessage = function (e) {
  const { action, text, fileName } = e.data;
  if (action === "parse") {
    try {
      parseGenomicText(text, fileName);
    } catch (err) {
      self.postMessage({ type: "error", error: err.message || String(err) });
    }
  }
};

function parseGenomicText(text, fileName = "") {
  self.postMessage({ type: "progress", percent: 5, status: "Detecting format and header..." });

  const lines = text.split(/\r?\n/);
  const totalLines = lines.length;

  let format = "unknown";
  let build = "GRCh37";
  let dataStartIndex = 0;
  let isAncestry = false;
  let isMyHeritage = false;
  let isVcf = false;
  let is23andMe = false;

  // Header inspect
  for (let i = 0; i < Math.min(200, totalLines); i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const lower = line.toLowerCase();
    if (lower.includes("23andme")) is23andMe = true;
    if (lower.includes("ancestrydna")) isAncestry = true;
    if (lower.includes("myheritage")) isMyHeritage = true;
    if (line.startsWith("##fileformat=vcf")) isVcf = true;

    if (lower.includes("build 38") || lower.includes("grch38") || lower.includes("hg38")) {
      build = "GRCh38";
    } else if (lower.includes("build 37") || lower.includes("grch37") || lower.includes("hg19")) {
      build = "GRCh37";
    } else if (lower.includes("ncbi36") || lower.includes("hg18")) {
      build = "NCBI36";
    }

    if (line.startsWith("#") || line.startsWith("##")) {
      dataStartIndex = i + 1;
      continue;
    }

    // CSV header for MyHeritage
    if (line.includes('"RSID"') || line.includes("RSID,CHROMOSOME")) {
      isMyHeritage = true;
      dataStartIndex = i + 1;
      break;
    }

    // If we reach a non-comment line
    if (!line.startsWith("#")) {
      dataStartIndex = i;
      break;
    }
  }

  // Fallback format heuristics
  if (isVcf) {
    format = "vcf";
  } else if (isAncestry) {
    format = "ancestry";
  } else if (isMyHeritage) {
    format = "myheritage";
  } else if (is23andMe) {
    format = "23andme";
  } else {
    // Check first data line
    const firstData = lines[dataStartIndex] || "";
    if (firstData.includes(",")) format = "myheritage";
    else if (firstData.split(/\t/).length >= 5) format = "ancestry";
    else format = "23andme";
  }

  self.postMessage({ type: "progress", percent: 15, status: `Parsing ${format.toUpperCase()} (${build})...` });

  let totalSnps = 0;
  let calledSnps = 0;
  let nocallSnps = 0;
  let homCount = 0;
  let hetCount = 0;

  let xCalled = 0;
  let xHet = 0;
  let yCalled = 0;
  const chromDist = {};

  let gt429 = null;
  let gt741 = null;

  const variants = {};
  const clinicalFindings = [];
  const assayedCurated = new Map();

  const updateInterval = Math.max(10000, Math.floor(totalLines / 20));

  for (let i = dataStartIndex; i < totalLines; i++) {
    const rawLine = lines[i];
    if (!rawLine || rawLine.startsWith("#")) continue;

    let rsid = "";
    let chrom = "";
    let pos = 0;
    let genotype = "";

    if (format === "myheritage" || rawLine.includes(",")) {
      const parts = rawLine.split(",").map(p => p.replace(/"/g, "").trim());
      if (parts.length < 4 || parts[0].toUpperCase() === "RSID") continue;
      rsid = parts[0];
      chrom = parts[1];
      pos = parseInt(parts[2], 10) || 0;
      genotype = parts[3];
    } else if (format === "vcf") {
      const cols = rawLine.split(/\t/);
      if (cols.length < 10) continue;
      chrom = cols[0].replace(/^chr/i, "");
      pos = parseInt(cols[1], 10) || 0;
      rsid = cols[2];
      const ref = cols[3];
      const alt = cols[4];
      const formatStr = cols[8];
      const sampleStr = cols[9];

      const gtIdx = formatStr.split(":").indexOf("GT");
      if (gtIdx >= 0) {
        const gt = sampleStr.split(":")[gtIdx];
        const altAlleles = alt.split(",");
        const alleleTable = [ref, ...altAlleles];
        const tokens = gt.split(/[/|]/);
        if (tokens.length === 1 && tokens[0] !== "." && tokens[0] !== "") {
          const idx = parseInt(tokens[0], 10);
          const a = alleleTable[idx] || "";
          genotype = a ? a + a : "--";
        } else if (tokens.length >= 2) {
          if (tokens[0] === "." || tokens[1] === ".") {
            genotype = "--";
          } else {
            const i0 = parseInt(tokens[0], 10);
            const i1 = parseInt(tokens[1], 10);
            const a0 = alleleTable[i0] || "";
            const a1 = alleleTable[i1] || "";
            genotype = (a0 && a1) ? [a0, a1].sort().join("") : "--";
          }
        } else {
          genotype = "--";
        }
      }
    } else {
      // 23andMe or Ancestry tab-delimited
      const cols = rawLine.split(/\t/);
      if (cols.length < 4) continue;
      rsid = cols[0].trim();
      chrom = cols[1].trim();
      pos = parseInt(cols[2], 10) || 0;

      if (cols.length >= 5) {
        // Ancestry format: allele1, allele2
        const a1 = cols[3].trim().toUpperCase();
        const a2 = cols[4].trim().toUpperCase();
        if (a1 === "0" || a2 === "0" || a1 === "-" || a2 === "-") {
          genotype = "--";
        } else {
          genotype = [a1, a2].sort().join("");
        }
      } else {
        genotype = cols[3].trim().toUpperCase();
      }
    }

    if (!rsid) continue;
    totalSnps++;
    chromDist[chrom] = (chromDist[chrom] || 0) + 1;

    // Check no-call
    const isNoCall = (
      genotype === "--" || genotype === "00" || genotype === "??" ||
      genotype === "NN" || genotype === "." || genotype === "" ||
      genotype.includes("-") || genotype.includes("0")
    );

    if (isNoCall) {
      nocallSnps++;
    } else {
      calledSnps++;
      const isHet = (genotype.length === 2 && genotype[0] !== genotype[1]);
      if (isHet) {
        hetCount++;
      } else {
        homCount++;
      }

      // Track APOE key SNPs
      if (rsid === "rs429358") gt429 = genotype;
      if (rsid === "rs7412") gt741 = genotype;

      // Sex chromosome metrics
      const cUpper = chrom.toUpperCase();
      if (cUpper === "X" || cUpper === "23") {
        xCalled++;
        if (isHet) xHet++;
      } else if (cUpper === "Y" || cUpper === "24") {
        yCalled++;
      }

      // Track all interrogated curated loci for 5-state coverage taxonomy evaluation
      if (CURATED_KB[rsid]) {
        assayedCurated.set(rsid, {
          chrom,
          pos,
          genotype,
          isNoCall: false
        });
      }
    } else {
      // If a curated locus had a no-call on the array, track it for gap reporting
      if (CURATED_KB[rsid]) {
        assayedCurated.set(rsid, {
          chrom,
          pos,
          genotype: "--",
          isNoCall: true
        });
      }
    }

    if (i % updateInterval === 0) {
      const p = Math.round(15 + (i / totalLines) * 75);
      self.postMessage({
        type: "progress",
        percent: p,
        status: `Parsed ${totalSnps.toLocaleString()} SNPs (${clinicalFindings.length} clinical findings)...`
      });
    }
  }

  // Compute QC metrics
  const callRate = totalSnps > 0 ? (calledSnps / totalSnps) : 0;
  const hetRate = calledSnps > 0 ? (hetCount / calledSnps) : 0;

  // Infer biological sex-chromosome karyotype signal
  let inferredSex = "Unknown (Insufficient X markers)";
  let xHetRate = 0;
  if (xCalled >= 10) {
    xHetRate = xHet / xCalled;
    if (xHetRate > 0.08 && yCalled >= 5) {
      inferredSex = "Atypical (High X Heterozygosity with Y Markers - e.g. 47,XXY or Mosaicism)";
    } else if (xHetRate > 0.08) {
      inferredSex = "Compatible with XX Karyotype (Heterozygous X)";
    } else if (xHetRate < 0.03 && yCalled >= 5) {
      inferredSex = "Compatible with XY Karyotype (Hemizygous X & Y Present)";
    } else if (xHetRate < 0.03 && yCalled === 0) {
      inferredSex = "Hemizygous X with No Y Markers Observed (Consistent with 45,X Turner or Sparse Y Coverage)";
    } else {
      inferredSex = "Indeterminate Sex-Chromosome Signal";
    }
  }

  // -------------------------------------------------------------------------
  // 5-STATE COVERAGE TAXONOMY EVALUATION
  // -------------------------------------------------------------------------
  const observedFindings = [];
  const negativeChecks = [];
  const arrayGaps = [];
  const insufficientEvidence = [];

  for (const [rsid, entry] of Object.entries(CURATED_KB)) {
    const isAcmg = ACMG_SF_GENES.has(entry.gene);
    const assayed = assayedCurated.get(rsid);

    if (!assayed) {
      // State 3: Not Tested By This Array (Omitted from chip)
      const isWeak = entry.evidence_tier === "Tier C" || entry.evidence_tier === "Tier D";
      const evalRes = deriveCoverageEvaluation(
        ASSAY_COVERAGE.UNPROBED,
        CURATION_SCOPE.IN_SCOPE,
        isWeak ? EVIDENCE_SUFFICIENCY.INSUFFICIENT : EVIDENCE_SUFFICIENCY.SUFFICIENT,
        SAMPLE_OBSERVATION.CALL_UNAVAILABLE
      );
      arrayGaps.push({
        rsid,
        gene: entry.gene,
        name: entry.name || rsid,
        coverage_state: evalRes.derived_state,
        assay_coverage: evalRes.assay_coverage,
        curation_scope: evalRes.curation_scope,
        evidence_sufficiency: evalRes.evidence_sufficiency,
        sample_observation: evalRes.sample_observation,
        user_label: evalRes.user_label,
        explanation: evalRes.explanation,
        reason: "Omitted from microarray chip manifest",
        chrom: entry.chrom,
        pos_grch37: entry.pos_grch37,
        pos_grch38: entry.pos_grch38,
        evidence_tier: entry.evidence_tier || "Tier D",
        acmg_actionable: isAcmg
      });
      continue;
    }

    if (assayed.isNoCall) {
      // State 3: Assayed on array but uncallable / no-call
      const isWeak = entry.evidence_tier === "Tier C" || entry.evidence_tier === "Tier D";
      const evalRes = deriveCoverageEvaluation(
        ASSAY_COVERAGE.NO_CALL,
        CURATION_SCOPE.IN_SCOPE,
        isWeak ? EVIDENCE_SUFFICIENCY.INSUFFICIENT : EVIDENCE_SUFFICIENCY.SUFFICIENT,
        SAMPLE_OBSERVATION.CALL_UNAVAILABLE
      );
      arrayGaps.push({
        rsid,
        gene: entry.gene,
        name: entry.name || rsid,
        coverage_state: evalRes.derived_state,
        assay_coverage: evalRes.assay_coverage,
        curation_scope: evalRes.curation_scope,
        evidence_sufficiency: evalRes.evidence_sufficiency,
        sample_observation: evalRes.sample_observation,
        user_label: evalRes.user_label,
        explanation: evalRes.explanation,
        reason: "No-call / uncallable on array (--)",
        chrom: entry.chrom,
        pos_grch37: entry.pos_grch37,
        pos_grch38: entry.pos_grch38,
        evidence_tier: entry.evidence_tier || "Tier D",
        acmg_actionable: isAcmg
      });
      continue;
    }

    // Match genotype against curated assertions
    const genotype = assayed.genotype;
    const sortedGt = genotype.length === 2 ? genotype.split("").sort().join("") : genotype;
    let match = entry.genotypes[genotype] || entry.genotypes[sortedGt];

    if (!match && !entry.is_palindromic) {
      // Check complement only if not palindromic
      const compMap = { "A": "T", "T": "A", "C": "G", "G": "C" };
      const compGt = genotype.split("").map(b => compMap[b] || b).sort().join("");
      match = entry.genotypes[compGt];
    }

    const segregation = computeSegregationReport(entry.gene, genotype, match ? match.category : "Trait", match ? match.significance : "Baseline");

    const record = {
      rsid,
      gene: entry.gene,
      genotype,
      chrom: assayed.chrom || entry.chrom,
      pos: assayed.pos || entry.pos_grch37,
      category: match ? match.category : "Trait",
      significance: match ? match.significance : "Negative / Wild-Type",
      magnitude: match ? match.magnitude : 1.0,
      repute: match ? match.repute : "Good",
      phenotype: match ? match.phenotype : "Normal / Baseline non-risk genotype confirmed.",
      drug_response: match ? match.drug_response : null,
      clinvar_stars: entry.clinvar_stars,
      clinvar_id: entry.clinvar_id,
      gnomad_af: entry.gnomad_af,
      gnomad_pli: entry.gnomad_pli,
      hpa_tissues: entry.hpa_tissues || {},
      hpa_subcellular: entry.hpa_subcellular || [],
      acmg_actionable: isAcmg,
      evidence_tier: entry.evidence_tier || (entry.clinvar_stars >= 3 ? "Tier A" : (entry.clinvar_stars === 2 ? "Tier B" : "Tier C")),
      tier_rationale: entry.tier_rationale || "",
      caveats: entry.caveats || [],
      refusal_notices: entry.refusal_notices || [],
      segregation
    };

    // Determine Coverage State & Orthogonal Dimensions
    const isRiskOrActionable = match && (
      match.category === "Pathogenic" ||
      match.category === "Carrier" ||
      match.category === "Pharmacogenomics" ||
      match.category === "Risk Factor" ||
      match.magnitude >= 2.0 ||
      match.isCarrier
    );

    const isConflictingOrWeak = record.evidence_tier === "Tier C" || record.evidence_tier === "Tier D" || (entry.clinvar_status && entry.clinvar_status.includes("conflicting"));
    const evSuff = isConflictingOrWeak ? EVIDENCE_SUFFICIENCY.INSUFFICIENT : EVIDENCE_SUFFICIENCY.SUFFICIENT;
    const sampleObs = isRiskOrActionable ? SAMPLE_OBSERVATION.VARIANT_PRESENT : SAMPLE_OBSERVATION.WILD_TYPE;

    const evalRes = deriveCoverageEvaluation(
      ASSAY_COVERAGE.ASSAYED_CALLED,
      CURATION_SCOPE.IN_SCOPE,
      evSuff,
      sampleObs
    );

    record.coverage_state = evalRes.derived_state;
    record.assay_coverage = evalRes.assay_coverage;
    record.curation_scope = evalRes.curation_scope;
    record.evidence_sufficiency = evalRes.evidence_sufficiency;
    record.sample_observation = evalRes.sample_observation;
    record.user_label = evalRes.user_label;
    record.explanation = evalRes.explanation;

    if (evalRes.derived_state === COVERAGE_STATES.INSUFFICIENT_EVIDENCE) {
      // State 5: Insufficient / Conflicting Evidence (e.g. MTHFR C677T)
      insufficientEvidence.push(record);
      if (sampleObs === SAMPLE_OBSERVATION.VARIANT_PRESENT) {
        observedFindings.push(record);
      } else {
        negativeChecks.push(record);
      }
    } else if (evalRes.derived_state === COVERAGE_STATES.SUPPORTED_AND_OBSERVED) {
      // State 1: Supported and Observed
      observedFindings.push(record);
    } else {
      // State 2: Supported but Not Observed (Negative check / Wild-Type)
      record.significance = "Negative / Wild-Type (Tested Normal)";
      record.repute = "Good";
      negativeChecks.push(record);
    }
  }

  // Synthesize compound APOE Diplotype (rs429358 + rs7412)
  const apoeFinding = resolveApoeDiplotype(gt429, gt741);
  if (apoeFinding) {
    const isApoeRisk = apoeFinding.apoeInfo.diplotype.includes("ε4") || apoeFinding.apoeInfo.diplotype.includes("ε2/ε2");
    const apoeObs = isApoeRisk ? SAMPLE_OBSERVATION.VARIANT_PRESENT : SAMPLE_OBSERVATION.WILD_TYPE;
    const apoeEval = deriveCoverageEvaluation(
      ASSAY_COVERAGE.ASSAYED_CALLED,
      CURATION_SCOPE.IN_SCOPE,
      EVIDENCE_SUFFICIENCY.SUFFICIENT,
      apoeObs
    );
    apoeFinding.coverage_state = apoeEval.derived_state;
    apoeFinding.assay_coverage = apoeEval.assay_coverage;
    apoeFinding.curation_scope = apoeEval.curation_scope;
    apoeFinding.evidence_sufficiency = apoeEval.evidence_sufficiency;
    apoeFinding.sample_observation = apoeEval.sample_observation;
    apoeFinding.user_label = apoeEval.user_label;
    apoeFinding.explanation = apoeEval.explanation;
    apoeFinding.evidence_tier = EVIDENCE_TIERS.TIER_A;
    if (isApoeRisk) {
      observedFindings.push(apoeFinding);
    } else {
      negativeChecks.push(apoeFinding);
    }
  }

  // Sort observed findings by clinical priority (Magnitude descending, then stars)
  observedFindings.sort((a, b) => (b.magnitude - a.magnitude) || (b.clinvar_stars - a.clinvar_stars));

  // Detect Multi-Locus Segregation & Assortment
  const compoundHeterozygotes = detectCompoundHeterozygosity(observedFindings);
  const independentAssortment = computeIndependentAssortment(observedFindings);

  const outsideCoverageCount = Math.max(0, totalSnps - assayedCurated.size);

  // Summary counts
  const summary = {
    total_annotated: observedFindings.length,
    pathogenic_count: observedFindings.filter(f => f.category === "Pathogenic").length,
    carrier_count: observedFindings.filter(f => f.category === "Carrier" || f.isCarrier).length,
    pgx_count: observedFindings.filter(f => f.category === "Pharmacogenomics").length,
    risk_factor_count: observedFindings.filter(f => f.category === "Risk Factor").length,
    acmg_actionable_findings: observedFindings.filter(f => f.acmg_actionable).length,
    compound_heterozygotes_count: compoundHeterozygotes.length,
    independent_assortment_count: independentAssortment.length,
    coverage_taxonomy: {
      cardinal_guardrail: ABSENCE_OF_FINDING_GUARDRAIL,
      supported_and_observed_count: observedFindings.filter(f => f.coverage_state === COVERAGE_STATES.SUPPORTED_AND_OBSERVED).length,
      supported_not_observed_count: negativeChecks.filter(f => f.coverage_state === COVERAGE_STATES.SUPPORTED_NOT_OBSERVED).length,
      not_tested_by_array_count: arrayGaps.length,
      outside_coverage_count: outsideCoverageCount,
      insufficient_evidence_count: insufficientEvidence.length
    }
  };

  const qc = {
    format_name: format,
    build,
    total_snps: totalSnps,
    called_snps: calledSnps,
    nocall_snps: nocallSnps,
    call_rate: callRate,
    heterozygosity_rate: hetRate,
    inferred_sex: inferredSex,
    x_markers_called: xCalled,
    x_het_rate: xHetRate,
    y_markers_called: yCalled,
    chrom_distribution: chromDist
  };

  self.postMessage({
    type: "complete",
    qc,
    records: observedFindings,
    negative_checks: negativeChecks,
    array_gaps: arrayGaps,
    insufficient_evidence: insufficientEvidence,
    coverage_taxonomy: {
      cardinal_guardrail: ABSENCE_OF_FINDING_GUARDRAIL,
      supported_and_observed_count: observedFindings.length,
      supported_not_observed_count: negativeChecks.length,
      not_tested_by_array_count: arrayGaps.length,
      outside_coverage_count: outsideCoverageCount,
      insufficient_evidence_count: insufficientEvidence.length
    },
    summary,
    apoe: apoeFinding ? apoeFinding.apoeInfo : null,
    compound_heterozygotes: compoundHeterozygotes,
    independent_assortment: independentAssortment
  });
}

function resolveApoeDiplotype(gt429, gt741) {
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

  return {
    rsid: "APOE-STATUS",
    gene: "APOE",
    genotype: `${diplotype} (${rawSummary})`,
    chrom: "19",
    pos: 45411941,
    category: category,
    isCarrier: true,
    significance: significance,
    magnitude: magnitude,
    repute: repute,
    phenotype: phenotype,
    drug_response: null,
    clinvar_stars: 4,
    clinvar_id: "VCV000017864",
    gnomad_af: 0.15,
    gnomad_pli: 0.0,
    hpa_tissues: { "liver": "High", "cerebral cortex": "Medium", "plasma": "High" },
    hpa_subcellular: ["Secreted", "Endoplasmic reticulum"],
    acmg_actionable: false,
    segregation: computeSegregationReport("APOE", diplotype, category, significance),
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
