/**
 * GenomePulse - High-Performance Genomic Web Worker
 * =================================================
 * Runs off the main UI thread to parse 1,000,000-line raw genotyping files
 * (23andMe, AncestryDNA, MyHeritage, VCF) without freezing the browser.
 */

import { 
  CURATED_KB, 
  ACMG_SF_GENES, 
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
        if (gt === "0/0" || gt === "0|0") genotype = ref + ref;
        else if (gt === "0/1" || gt === "0|1" || gt === "1|0") genotype = [ref, alt].sort().join("");
        else if (gt === "1/1" || gt === "1|1") genotype = alt + alt;
        else genotype = "--";
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

      // Check Clinical Knowledge Base
      if (CURATED_KB[rsid]) {
        const entry = CURATED_KB[rsid];
        // Sort alleles to match canonical format (e.g. AG vs GA)
        const sortedGt = genotype.length === 2 ? genotype.split("").sort().join("") : genotype;
        let match = entry.genotypes[genotype] || entry.genotypes[sortedGt];

        if (!match) {
          // Check inverted complement if strand flipped
          const compMap = { "A": "T", "T": "A", "C": "G", "G": "C" };
          const compGt = genotype.split("").map(b => compMap[b] || b).sort().join("");
          match = entry.genotypes[compGt];
        }

        if (match) {
          const isAcmg = ACMG_SF_GENES.has(entry.gene);
          const segregation = computeSegregationReport(entry.gene, genotype, match.category, match.significance);
          clinicalFindings.push({
            rsid,
            gene: entry.gene,
            genotype,
            chrom,
            pos,
            category: match.category,
            significance: match.significance,
            magnitude: match.magnitude,
            repute: match.repute,
            phenotype: match.phenotype,
            drug_response: match.drug_response,
            clinvar_stars: entry.clinvar_stars,
            clinvar_id: entry.clinvar_id,
            gnomad_af: entry.gnomad_af,
            gnomad_pli: entry.gnomad_pli,
            hpa_tissues: entry.hpa_tissues || {},
            hpa_subcellular: entry.hpa_subcellular || [],
            acmg_actionable: isAcmg,
            segregation
          });
        }
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

  // Infer biological sex
  let inferredSex = "Unknown (Insufficient X markers)";
  let xHetRate = 0;
  if (xCalled >= 10) {
    xHetRate = xHet / xCalled;
    if (xHetRate > 0.08) {
      inferredSex = "Female (XX)";
    } else if (xHetRate < 0.02 && yCalled >= 5) {
      inferredSex = "Male (XY)";
    } else if (xHetRate < 0.03) {
      inferredSex = "Male (XY, Hemizygous X)";
    } else {
      inferredSex = "Undetermined / Atypical";
    }
  }

  // Synthesize compound APOE Diplotype (rs429358 + rs7412)
  const apoeFinding = resolveApoeDiplotype(gt429, gt741);
  if (apoeFinding) {
    clinicalFindings.push(apoeFinding);
  }

  // Sort clinical findings by clinical priority (Magnitude descending, then stars)
  clinicalFindings.sort((a, b) => (b.magnitude - a.magnitude) || (b.clinvar_stars - a.clinvar_stars));

  // Detect Multi-Locus Segregation & Assortment
  const compoundHeterozygotes = detectCompoundHeterozygosity(clinicalFindings);
  const independentAssortment = computeIndependentAssortment(clinicalFindings);

  // Summary counts
  const summary = {
    total_annotated: clinicalFindings.length,
    pathogenic_count: clinicalFindings.filter(f => f.category === "Pathogenic").length,
    carrier_count: clinicalFindings.filter(f => f.category === "Carrier" || f.isCarrier).length,
    pgx_count: clinicalFindings.filter(f => f.category === "Pharmacogenomics").length,
    risk_factor_count: clinicalFindings.filter(f => f.category === "Risk Factor").length,
    acmg_actionable_findings: clinicalFindings.filter(f => f.acmg_actionable).length,
    compound_heterozygotes_count: compoundHeterozygotes.length,
    independent_assortment_count: independentAssortment.length
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
    records: clinicalFindings,
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
  } else if (n429 === "CT") {
    diplotype = "ε4 Carrier";
    label = "APOE ε4 Carrier (presumed ε3/ε4)";
    category = "Carrier";
    significance = "Risk Factor / Carrier";
    magnitude = 3.8;
    repute = "Bad";
    riskRatio = "~3× Increased Risk";
    lifetimeRisk = "~25–30% lifetime Alzheimer's risk";
    phenotype = "APOE ε4 Carrier: One ε4 copy detected at rs429358. Confers increased lifetime risk of late-onset Alzheimer's disease.";
  } else if (n429 === "TT") {
    diplotype = "Non-ε4";
    label = "APOE Non-ε4 (presumed ε3/ε3)";
    category = "Carrier";
    significance = "Normal / Baseline";
    magnitude = 1.2;
    repute = "Good";
    riskRatio = "1.0× (Baseline)";
    lifetimeRisk = "10–15% lifetime Alzheimer's risk";
    phenotype = "APOE non-ε4 genotype detected at rs429358 (presumed baseline ε3 or protective ε2).";
  } else if (n741 === "CT") {
    diplotype = "ε2 Carrier";
    label = "APOE ε2 Carrier (presumed ε2/ε3)";
    category = "Carrier";
    significance = "Protective / Carrier";
    magnitude = 2.0;
    repute = "Good";
    riskRatio = "0.6× (Protective)";
    lifetimeRisk = "5–8% lifetime Alzheimer's risk";
    phenotype = "APOE ε2 protective allele detected at rs7412.";
  } else {
    diplotype = "Indeterminate";
    label = `APOE (${n429 || '?'}/${n741 || '?'})`;
    category = "Carrier";
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
