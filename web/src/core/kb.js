/**
 * Knowledge-base validation and indexing (contracts C2, schema v2). Pure: no DOM, no
 * `self`, no `fetch`; the caller loads the JSON. Nothing is defaulted: a missing clinical
 * field is a KbSchemaError at load time, never a fallback string at display time.
 */

export class KbSchemaError extends Error {
  constructor(problems) {
    super(`Invalid knowledge base (${problems.length} problem${problems.length === 1 ? "" : "s"}):\n- ${problems.join("\n- ")}`);
    this.name = "KbSchemaError";
    this.problems = problems;
  }
}

const TIERS = ["Tier A", "Tier B", "Tier C", "Tier D"];
const TIER_SOURCES = ["clinvar_review", "cpic_level", "curated"];
const SUFFICIENCY = ["sufficient", "insufficient"];
const ROLES = ["standard", "apoe_component"];
const MODELS = ["autosomal_recessive", "autosomal_dominant", "risk_factor", "pharmacogenomic", "trait"];
const DIPLOTYPES = ["e2/e2", "e2/e3", "e2/e4", "e3/e3", "e3/e4", "e4/e4"];
const PER_SAMPLE_FIELDS = ["coverage_state", "sample_observation", "assay_coverage"];
const BUILD_FIELDS = { GRCh37: "pos_grch37", GRCh38: "pos_grch38" };

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const isStr = (v) => typeof v === "string" && v.length > 0;
const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

function checkInterp(interp, path, problems) {
  if (!isObj(interp)) {
    problems.push(`${path}: missing or not an object`);
    return;
  }
  for (const k of ["category", "significance", "repute", "phenotype"]) {
    if (!isStr(interp[k])) problems.push(`${path}.${k}: required non-empty string`);
  }
  if (typeof interp.magnitude !== "number" || !Number.isFinite(interp.magnitude)) {
    problems.push(`${path}.magnitude: required number`);
  }
  if (!hasOwn(interp, "drug_response") || (interp.drug_response !== null && typeof interp.drug_response !== "string")) {
    problems.push(`${path}.drug_response: required string or null`);
  }
  if (!Array.isArray(interp.caveats) || !interp.caveats.every((c) => typeof c === "string")) {
    problems.push(`${path}.caveats: required array of strings`);
  }
}

function checkLocus(key, locus, genes, problems) {
  const p = `loci.${key}`;
  if (!isObj(locus)) {
    problems.push(`${p}: not an object`);
    return;
  }
  if (locus.rsid !== key) problems.push(`${p}.rsid: "${locus.rsid}" does not match its key`);
  if (!isStr(locus.gene)) problems.push(`${p}.gene: required`);
  else if (!hasOwn(genes, locus.gene)) problems.push(`${p}.gene: unknown gene "${locus.gene}"`);
  if (!isStr(locus.chrom)) problems.push(`${p}.chrom: required string`);
  for (const f of Object.values(BUILD_FIELDS)) {
    if (!Number.isInteger(locus[f]) || locus[f] <= 0) problems.push(`${p}.${f}: required positive integer`);
  }
  for (const f of ["ref", "alt"]) {
    if (typeof locus[f] !== "string" || !/^[ACGT]+$/.test(locus[f])) problems.push(`${p}.${f}: required ACGT sequence`);
  }
  if (locus.ref === locus.alt) problems.push(`${p}: ref and alt are identical`);

  if (!hasOwn(locus, "allele_codes")) {
    problems.push(`${p}.allele_codes: required (null or {D, I})`);
  } else if (locus.allele_codes !== null) {
    const c = locus.allele_codes;
    const ok = isObj(c) && Object.keys(c).sort().join() === "D,I" && ["D", "I"].every((k) => c[k] === "ref" || c[k] === "alt");
    if (!ok) problems.push(`${p}.allele_codes: must map D and I to "ref" or "alt"`);
  }

  if (!isObj(locus.interpretations)) {
    problems.push(`${p}.interpretations: required object`);
  } else {
    for (const k of ["0", "1", "2"]) checkInterp(locus.interpretations[k], `${p}.interpretations.${k}`, problems);
    const extra = Object.keys(locus.interpretations).filter((k) => !["0", "1", "2"].includes(k));
    if (extra.length) problems.push(`${p}.interpretations: unexpected keys ${extra.join(", ")}`);
  }

  if (!isObj(locus.evidence)) problems.push(`${p}.evidence: required object`);
  if (!TIERS.includes(locus.evidence_tier)) problems.push(`${p}.evidence_tier: must be one of ${TIERS.join(", ")}`);
  if (!TIER_SOURCES.includes(locus.tier_source)) problems.push(`${p}.tier_source: must be one of ${TIER_SOURCES.join(", ")}`);
  if (locus.tier_source !== "clinvar_review") {
    if (!isStr(locus.tier_rationale)) problems.push(`${p}.tier_rationale: required unless tier_source is clinvar_review`);
    if (!isStr(locus.tier_citation)) problems.push(`${p}.tier_citation: required unless tier_source is clinvar_review`);
  }
  if (!SUFFICIENCY.includes(locus.evidence_sufficiency)) {
    problems.push(`${p}.evidence_sufficiency: must be one of ${SUFFICIENCY.join(", ")}`);
  }
  if (!hasOwn(locus, "limitation") || (locus.limitation !== null && !isStr(locus.limitation))) {
    problems.push(`${p}.limitation: required string or null`);
  }
  if (!ROLES.includes(locus.role)) problems.push(`${p}.role: must be one of ${ROLES.join(", ")}`);
}

function checkGene(symbol, gene, problems) {
  const p = `genes.${symbol}`;
  if (!isObj(gene)) {
    problems.push(`${p}: not an object`);
    return;
  }
  const inh = gene.inheritance;
  if (!isObj(inh)) {
    problems.push(`${p}.inheritance: required object`);
  } else {
    if (!MODELS.includes(inh.model)) problems.push(`${p}.inheritance.model: must be one of ${MODELS.join(", ")}`);
    if (typeof inh.mendelian_disease !== "boolean") problems.push(`${p}.inheritance.mendelian_disease: required boolean`);
    for (const k of ["disease", "omim", "penetrance"]) {
      if (!hasOwn(inh, k)) problems.push(`${p}.inheritance.${k}: required (null allowed)`);
    }
  }
  if (typeof gene.acmg_sf !== "boolean") problems.push(`${p}.acmg_sf: required boolean`);
  if (!hasOwn(gene, "insights") || (gene.insights !== null && !isObj(gene.insights))) {
    problems.push(`${p}.insights: required object or null`);
  }
  if (hasOwn(gene, "diplotypes")) {
    if (!isObj(gene.diplotypes) || Object.keys(gene.diplotypes).sort().join() !== DIPLOTYPES.join()) {
      problems.push(`${p}.diplotypes: must hold exactly ${DIPLOTYPES.join(", ")}`);
    } else {
      for (const d of DIPLOTYPES) checkInterp(gene.diplotypes[d], `${p}.diplotypes.${d}`, problems);
    }
  }
}

/** The KB holds no per-sample field anywhere (C2). */
function scanPerSample(node, path, problems) {
  if (Array.isArray(node)) {
    node.forEach((v, i) => scanPerSample(v, `${path}[${i}]`, problems));
  } else if (isObj(node)) {
    for (const [k, v] of Object.entries(node)) {
      if (PER_SAMPLE_FIELDS.includes(k)) problems.push(`${path}.${k}: per-sample field must not appear in the knowledge base`);
      scanPerSample(v, `${path}.${k}`, problems);
    }
  }
}

function deepFreeze(value) {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const v of Object.values(value)) deepFreeze(v);
  }
  return value;
}

/**
 * Validates a parsed KB (schema v2) and returns a frozen, indexed copy:
 *   { manifest, genes, loci (by rsid), lociList (KB order), byPosition: { GRCh37: Map("chrom:pos" -> rsid), GRCh38: Map } }.
 * Throws KbSchemaError listing every problem. The input is not modified.
 */
export function validateKb(json) {
  const problems = [];
  if (!isObj(json)) throw new KbSchemaError(["knowledge base is not an object"]);

  if (json.schema_version !== 2) problems.push(`schema_version: expected 2, got ${JSON.stringify(json.schema_version)}`);
  if (!isObj(json.manifest)) problems.push("manifest: required object");
  else if (!isStr(json.manifest.guardrail)) problems.push("manifest.guardrail: required non-empty string");
  if (!isObj(json.genes)) problems.push("genes: required object");
  if (!isObj(json.loci)) problems.push("loci: required object");

  if (isObj(json.genes) && isObj(json.loci)) {
    for (const [symbol, gene] of Object.entries(json.genes)) checkGene(symbol, gene, problems);
    for (const [key, locus] of Object.entries(json.loci)) checkLocus(key, locus, json.genes, problems);

    for (const [build, field] of Object.entries(BUILD_FIELDS)) {
      const seen = new Map();
      for (const [key, locus] of Object.entries(json.loci)) {
        if (!isObj(locus) || !Number.isInteger(locus[field])) continue;
        const pos = `${locus.chrom}:${locus[field]}`;
        if (seen.has(pos)) problems.push(`duplicate position ${pos} in ${build}: ${seen.get(pos)} and ${key}`);
        else seen.set(pos, key);
      }
    }
  }
  scanPerSample(json, "kb", problems);
  if (problems.length) throw new KbSchemaError(problems);

  const kb = structuredClone(json);
  const byPosition = { GRCh37: new Map(), GRCh38: new Map() };
  for (const locus of Object.values(kb.loci)) {
    for (const [build, field] of Object.entries(BUILD_FIELDS)) byPosition[build].set(`${locus.chrom}:${locus[field]}`, locus.rsid);
  }
  return deepFreeze({
    manifest: kb.manifest,
    genes: kb.genes,
    loci: kb.loci,
    lociList: Object.values(kb.loci),
    byPosition,
  });
}
