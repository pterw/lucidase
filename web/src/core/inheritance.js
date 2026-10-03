/**
 * Genotype-aware inheritance engine (contracts C5). Pure: no DOM, no `self`, no `fetch`.
 *
 * Offspring distribution = the patient's gametes (P(alt) = altCount / 2) convolved with the
 * partner's gametes, giving P(0), P(1), P(2) alt alleles in the child. Disease or recurrence
 * wording exists only for Mendelian-disease genes; every other model reports allele
 * transmission only. Nothing is defaulted: a missing allele frequency or penetrance makes the
 * figure unavailable, and it says so.
 */

export const PARTNER_MODELS = ["wildtype", "heterozygous", "homozygous", "unscreened"];

const PHASE_UNKNOWN = "phase unknown (cis or trans cannot be determined from unphased genotypes)";
export const MULTI_LOCUS_ASSUMPTION = "assumes unlinked loci and a partner without these alleles";

function checkAltCount(altCount) {
  if (altCount !== 0 && altCount !== 1 && altCount !== 2) {
    throw new Error(`alt-allele count must be 0, 1 or 2, got ${JSON.stringify(altCount)}`);
  }
}

/**
 * Alt-allele distribution in a child. Returns {available: true, p0, p1, p2}, or
 * {available: false, reason} when the unscreened model has no allele frequency.
 */
export function offspringDistribution(patientAltCount, partnerModel, af) {
  checkAltCount(patientAltCount);
  let partnerAlt;
  if (partnerModel === "wildtype") partnerAlt = 0;
  else if (partnerModel === "heterozygous") partnerAlt = 0.5;
  else if (partnerModel === "homozygous") partnerAlt = 1;
  else if (partnerModel === "unscreened") {
    if (typeof af !== "number" || !Number.isFinite(af) || af < 0 || af > 1) {
      return { available: false, reason: "Not available: no gnomAD allele frequency for this variant, so an unscreened partner cannot be modelled." };
    }
    partnerAlt = af;
  } else {
    throw new Error(`unknown partner model ${JSON.stringify(partnerModel)}`);
  }
  const a = patientAltCount / 2;
  const b = partnerAlt;
  return { available: true, p0: (1 - a) * (1 - b), p1: a * (1 - b) + (1 - a) * b, p2: a * b };
}

function inheritanceOf(gene) {
  const inh = gene && gene.inheritance;
  if (!inh || typeof inh.mendelian_disease !== "boolean" || typeof inh.model !== "string") {
    throw new Error("gene has no valid inheritance block (model, mendelian_disease)");
  }
  return inh;
}

/**
 * Outcome for a gene given an offspring distribution. Mendelian-disease genes report affected
 * (and carrier) probabilities; every other model reports allele transmission only.
 */
export function geneOutcome(gene, dist, allele = "variant") {
  const inh = inheritanceOf(gene);
  if (!dist.available) return { available: false, kind: inh.mendelian_disease ? "mendelian" : "transmission", reason: dist.reason };
  const { p0, p1, p2 } = dist;
  if (inh.mendelian_disease) {
    if (inh.model === "autosomal_recessive") {
      return {
        available: true, kind: "mendelian", model: inh.model, p0, p1, p2,
        affected: p2, carrier: p1, label: "Chance a child is affected (two copies)",
      };
    }
    if (inh.model === "autosomal_dominant") {
      if (typeof inh.penetrance !== "number") {
        return {
          available: false, kind: "mendelian", model: inh.model, p0, p1, p2,
          reason: "Not available: the knowledge base has no penetrance for this dominant condition.",
        };
      }
      return {
        available: true, kind: "mendelian", model: inh.model, p0, p1, p2,
        affected: (p1 + p2) * inh.penetrance, label: "Chance a child is affected (at least one copy x penetrance)",
      };
    }
    throw new Error(`Mendelian gene with unsupported model ${inh.model}`);
  }
  return {
    available: true, kind: "transmission", model: inh.model, p0, p1, p2,
    inherits_allele: p1 + p2, one_copy: p1, two_copies: p2, none: p0,
    label: `Chance a child inherits the ${allele} allele`,
  };
}

/** is_affected / is_carrier exist only for Mendelian-disease genes, derived from the alt count. */
export function patientStatus(gene, altCount) {
  const inh = inheritanceOf(gene);
  checkAltCount(altCount);
  if (!inh.mendelian_disease) return {};
  if (inh.model === "autosomal_recessive") return { is_affected: altCount === 2, is_carrier: altCount === 1 };
  if (inh.model === "autosomal_dominant") return { is_affected: altCount >= 1 };
  throw new Error(`Mendelian gene with unsupported model ${inh.model}`);
}

/**
 * Per-record inheritance summary for the UI. The UI reruns offspringDistribution / geneOutcome
 * for the chosen partner model from `altCount` and `af`, so the worker sends inputs, not results.
 */
export function describeSegregation(geneName, gene, altCount, af, allele) {
  const inh = inheritanceOf(gene);
  checkAltCount(altCount);
  return {
    gene: geneName,
    model: inh.model,
    mendelian_disease: inh.mendelian_disease,
    disease: inh.disease,
    omim: inh.omim,
    penetrance: inh.penetrance,
    altCount,
    af,
    allele,
    ...patientStatus(gene, altCount),
  };
}

const isCandidate = (r) => r && r.standalone !== false && r.role !== "apoe_component" && (r.altCount === 1 || r.altCount === 2);

/**
 * Multi-locus findings: pairs of loci with altCount > 0 on different chromosomes, in genes whose
 * model is a risk factor. Recognition is by gene and altCount, never by genotype strings. The
 * joint chance is the product of altCount / 2, under the stated assumption.
 */
export function detectMultiLocus(records, genes) {
  const findings = [];
  const eligible = records.filter((r) => isCandidate(r) && genes[r.gene] && inheritanceOf(genes[r.gene]).model === "risk_factor");
  for (let i = 0; i < eligible.length; i++) {
    for (let j = i + 1; j < eligible.length; j++) {
      const a = eligible[i];
      const b = eligible[j];
      if (a.chrom === b.chrom) continue;
      const joint = (a.altCount / 2) * (b.altCount / 2);
      findings.push({
        genes: [a.gene, b.gene],
        loci: [`${a.rsid} (Chr ${a.chrom})`, `${b.rsid} (Chr ${b.chrom})`],
        type: "Co-occurring variant alleles",
        joint_transmission_prob: joint,
        assumption: MULTI_LOCUS_ASSUMPTION,
        description:
          `This sample carries variant alleles in ${a.gene} (${a.rsid}) and ${b.gene} (${b.rsid}), on different chromosomes. ` +
          `Chance a child inherits both alleles: ${(joint * 100).toFixed(0)}% (${a.altCount}/2 x ${b.altCount}/2); ${MULTI_LOCUS_ASSUMPTION}.`,
      });
    }
  }
  return findings;
}

/**
 * Possible compound heterozygosity: two or more loci of one recessive Mendelian gene that are each
 * heterozygous. Unphased genotypes cannot place the alleles in cis or trans, so phase is never asserted.
 */
export function detectCompoundHeterozygosity(records, genes) {
  const byGene = new Map();
  for (const r of records) {
    if (!r || r.altCount !== 1 || r.role === "apoe_component") continue;
    if (!byGene.has(r.gene)) byGene.set(r.gene, []);
    byGene.get(r.gene).push(r);
  }
  const findings = [];
  for (const [gene, hets] of byGene) {
    const g = genes[gene];
    if (!g || hets.length < 2) continue;
    const inh = inheritanceOf(g);
    if (!inh.mendelian_disease || inh.model !== "autosomal_recessive") continue;
    const rsids = hets.map((r) => r.rsid);
    findings.push({
      gene,
      loci: rsids,
      phase: "unknown",
      title: `Possible compound heterozygote (${rsids.join(" / ")})`,
      significance: "Phase unknown",
      summary: `Possible compound heterozygote in ${gene}: heterozygous at ${rsids.join(" and ")}; ${PHASE_UNKNOWN}.`,
      segregation_notes:
        `Each heterozygous locus is transmitted with probability 1/2 per child; whether a child could inherit both alleles together depends on phase, which is unknown.`,
    });
  }
  return findings;
}
