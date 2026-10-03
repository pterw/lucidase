/**
 * One display model per record (AGENTS.md sections 3 and 4). Pure: no DOM, no `self`, no `fetch`.
 *
 * `toViewModel(record, genes)` returns every field the table, the drawer, the Markdown export and the CSV export
 * show, so no view formats a clinical field itself. A value the record or knowledge base does not carry is `null`
 * and is listed in `missing_fields`: views render it as "Not available" (muted), exports write an empty cell.
 * Nothing here substitutes a default for a clinical field.
 *
 * `escapeHtml` is the one escape function for every record or KB value that reaches an `innerHTML` string.
 */
import { displayDiplotype } from "./core/apoe.js";
import { offspringDistribution, geneOutcome } from "./core/inheritance.js";

export const NOT_AVAILABLE = "Not available";
export const NO_CLINVAR_STATUS = "No ClinVar review status";

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escapes text for an HTML text node or a quoted attribute value. null and undefined give "". */
export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

/** Short badge text and long label per coverage state (contracts C4). Unknown states throw. */
const STATE_TEXT = {
  supported_and_observed: { badge: "Observed", label: "Supported & Observed" },
  supported_not_observed: { badge: "Tested WT", label: "Tested Wild-Type (State 2)" },
  not_tested_by_array: { badge: "Array Gap", label: "Array Gap (State 3)" },
  insufficient_evidence: { badge: "Conflicting", label: "Conflicting Evidence (State 5)" },
};

/** The APOE card's wording per state. */
const APOE_STATE_LABEL = {
  supported_and_observed: "Observed",
  supported_not_observed: "Not detected",
  not_tested_by_array: "Not tested by array",
  insufficient_evidence: "Insufficient evidence",
};

export const MODEL_LABELS = {
  autosomal_recessive: "Autosomal Recessive",
  autosomal_dominant: "Autosomal Dominant",
  risk_factor: "Risk Factor (allele transmission)",
  pharmacogenomic: "Pharmacogenomic (allele transmission)",
  trait: "Trait (allele transmission)",
};

const nonEmptyString = (v) => (typeof v === "string" && v !== "" ? v : null);
const numberOrNull = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const groupedNumber = (n) => n.toLocaleString("en-US");

/** A null rate (variants-only VCF) is "Not available". */
export function formatRate(rate) {
  return rate === null || rate === undefined ? NOT_AVAILABLE : `${(rate * 100).toFixed(2)}%`;
}

/** Percentage with at most one decimal: 0.25 gives "25%", 0.0066 gives "0.7%". */
export function fmtPct(fraction) {
  return `${Math.round(fraction * 1000) / 10}%`;
}

/**
 * Counts the variants tested per gene for this file: the distinct KB rsids among the listed records, leaving out
 * array gaps (a locus the array did not assay was not tested).
 */
export function testedVariantCounts(records) {
  const rsidsByGene = new Map();
  for (const r of records) {
    if (r.role === "apoe_component" || r.components || r.coverage_state === "not_tested_by_array") continue;
    if (!rsidsByGene.has(r.gene)) rsidsByGene.set(r.gene, new Set());
    rsidsByGene.get(r.gene).add(r.rsid);
  }
  return Object.fromEntries([...rsidsByGene].map(([gene, set]) => [gene, set.size]));
}

/** "<allele> not detected (N variant(s) tested in <gene>)" (AGENTS.md 4.1). Only for a wild-type genotype. */
function notDetectedStatement(record, testedCounts) {
  if (record.sample_observation !== "wild_type") return null;
  const label = record.components ? `${record.gene} ε2 and ε4 alleles` : `${record.rsid} variant`;
  const total = record.components ? record.components.length : testedCounts[record.gene];
  if (total === undefined) return `${label} not detected`;
  return `${label} not detected (${total} ${total === 1 ? "variant" : "variants"} tested in ${record.gene})`;
}

/** One locus's own evidence figures. A composite row carries one of these per component, never one as its own. */
function locusEvidence(rec) {
  const evidence = rec.evidence ?? {};
  const clinvar = evidence.clinvar ?? {};
  const stars = numberOrNull(clinvar.stars);
  const digits = nonEmptyString(clinvar.accession) ? clinvar.accession.replace(/\D/g, "") : "";
  const imported = clinvar.provenance && clinvar.provenance.curation_mode === "machine_imported";
  const af = numberOrNull(evidence.gnomad && evidence.gnomad.af);
  return {
    rsid: rec.rsid,
    stars,
    starsText: stars === null ? NO_CLINVAR_STATUS : stars > 0 ? "★".repeat(stars) : "0 stars",
    starsDetail: stars === null ? NO_CLINVAR_STATUS : stars > 0 ? `${"★".repeat(stars)} (${stars} / 4 stars)` : "0 / 4 stars",
    clinvarUrl: imported && digits ? `https://www.ncbi.nlm.nih.gov/clinvar/variation/${Number(digits)}` : null,
    af,
    afText: af === null ? null : `${(af * 100).toFixed(2)}%`,
    afExport: af === null ? null : Math.round(af * 1e6) / 1e6,
    tier: nonEmptyString(rec.evidence_tier),
  };
}

const joinLabelled = (parts, pick, naText = NOT_AVAILABLE) =>
  parts.map((p) => `${p.rsid}: ${pick(p) ?? naText}`).join(" · ");
/** Component values joined by ";" in component order (an absent one is an empty slot); null when none is present. */
const joinExport = (parts, pick) => {
  const values = parts.map(pick);
  return values.every((v) => v === null) ? null : values.map((v) => v ?? "").join(";");
};

function loeufText(value) {
  if (value === null) return null;
  const band = value < 0.35 ? "Extremely Constrained" : value < 0.75 ? "Constrained" : "Tolerant";
  return `LOEUF ${value.toFixed(2)} (${band})`;
}

/** Gene drawer content from the knowledge base; an empty insights object counts as none. */
function insightsOf(gene) {
  const insights = gene && gene.insights;
  return insights && Object.keys(insights).length > 0 ? insights : null;
}

/**
 * The display model for one classified record (core/classify.js, core/apoe.js). `genes` is the KB gene table and
 * `testedCounts` the per-gene variant counts from `testedVariantCounts`. The record's own fields are kept (the
 * views and tests read `coverage_state`, `components`, ...); the display fields below are added.
 */
export function toViewModel(record, genes, testedCounts = {}) {
  const state = STATE_TEXT[record.coverage_state];
  if (state === undefined) throw new Error(`unknown coverage state "${record.coverage_state}" on ${record.rsid}`);
  const gene = genes[record.gene];
  const interp = record.interpretation ?? null;
  const evidence = record.evidence ?? {};
  const gnomad = evidence.gnomad ?? {};
  const hpa = evidence.hpa ?? {};
  const vep = evidence.vep ?? {};

  const parts = record.components ?? [record];
  const positions = parts.map((c) => ({ rsid: c.rsid, chrom: c.chrom, pos: numberOrNull(c.pos) }));
  const allPositions = positions.every((p) => p.pos !== null);
  const isComposite = Boolean(record.components);

  // One evidence entry per locus. A composite (APOE) row carries both components' evidence, each labelled with its
  // rsid, and none of it is presented as the row's own (AGENTS.md 4.5, contracts C4).
  const evidenceParts = parts.map(locusEvidence);
  const single = isComposite ? null : evidenceParts[0];
  const stars = single && single.stars;
  const af = single && single.af;
  const tierParts = evidenceParts.map((p) => p.tier);
  const magnitude = numberOrNull(interp && interp.magnitude);
  const repute = nonEmptyString(interp && interp.repute);
  const limitation = nonEmptyString(record.limitation);
  const caveats = interp ? [...interp.caveats] : [];
  const insights = insightsOf(gene);
  const ensembl = (insights && insights.ensembl) ?? {};
  const alphafold = (insights && insights.alphafold) ?? {};
  const significanceValue = nonEmptyString(interp && interp.significance);
  const phenotype = interp ? nonEmptyString(interp.phenotype) : nonEmptyString(record.reason);
  const category = nonEmptyString(interp && interp.category);
  const genotype = nonEmptyString(record.genotype_display);
  const tier = isComposite
    ? tierParts.every((t) => t === null)
      ? null
      : tierParts.every((t) => t === tierParts[0])
        ? tierParts[0]
        : joinLabelled(evidenceParts, (p) => p.tier)
    : single.tier;

  const amScore = numberOrNull(ensembl.alphamissense_pathogenicity ?? vep.alphamissense_score);
  const amClass = nonEmptyString(ensembl.alphamissense_class ?? vep.alphamissense_class);
  const loeuf = numberOrNull(ensembl.loeuf ?? gnomad.loeuf);

  const vm = {
    ...record,
    id: isComposite ? `${record.gene} (${positions.map((p) => p.rsid).join(" + ")})` : record.rsid,
    exportId: positions.map((p) => p.rsid).join(";"),
    genotype,
    positions,
    positionText: allPositions
      ? positions.map((p) => `chr${p.chrom}:${groupedNumber(p.pos)}${isComposite ? ` (${p.rsid})` : ""}`).join(" · ")
      : null,
    coordinates: allPositions ? positions.map((p) => `chr${p.chrom}:${p.pos}`).join(";") : null,
    chromosomes: [...new Set(positions.map((p) => p.chrom))].join(";"),
    positionExport: allPositions ? positions.map((p) => p.pos).join(";") : null,
    stateBadge: state.badge,
    stateLabel: state.label,
    tier,
    category,
    isCarrier: category === "Carrier",
    significance: significanceValue ?? state.label,
    significanceValue,
    phenotype,
    statement: notDetectedStatement(record, testedCounts),
    magnitude,
    repute,
    magnitudeShort: magnitude === null ? null : magnitude.toFixed(1),
    diplotypeDisplay: record.diplotype && record.diplotype !== "atypical" ? displayDiplotype(record.diplotype) : null,
    magnitudeText: magnitude === null ? null : `${magnitude.toFixed(1)} / 10.0${repute ? ` (${repute})` : ""}`,
    componentEvidence: isComposite ? evidenceParts : null,
    stars,
    clinvar_stars: stars,
    starsMuted: isComposite ? evidenceParts.every((p) => p.stars === null) : stars === null,
    starsText: isComposite ? joinLabelled(evidenceParts, (p) => p.starsText) : single.starsText,
    starsDetail: isComposite ? joinLabelled(evidenceParts, (p) => p.starsDetail) : single.starsDetail,
    clinvarUrl: isComposite ? null : single.clinvarUrl,
    clinvarLinks: evidenceParts.filter((p) => p.clinvarUrl !== null).map((p) => ({ rsid: p.rsid, url: p.clinvarUrl })),
    gnomad_af: af,
    afText: isComposite
      ? evidenceParts.every((p) => p.af === null)
        ? null
        : joinLabelled(evidenceParts, (p) => p.afText)
      : single.afText,
    // Export columns: the single locus's value, or the component values joined by ";" in component order.
    starsExport: isComposite ? joinExport(evidenceParts, (p) => p.stars) : stars,
    starsExportText: isComposite
      ? evidenceParts.map((p) => p.starsText).join(";")
      : single.starsText,
    afExport: isComposite ? joinExport(evidenceParts, (p) => p.afExport) : single.afExport,
    tierExport: isComposite ? joinExport(evidenceParts, (p) => p.tier) : tier,
    limitation,
    caveats,
    limitationTooltip: [limitation, ...caveats].filter(Boolean).join(" ") || null,
    drug_response: nonEmptyString(interp && interp.drug_response),
    acmg_actionable: record.acmg_sf,
    modelLabel: gene && gene.inheritance ? (MODEL_LABELS[gene.inheritance.model] ?? gene.inheritance.model) : null,
    hpa_tissues: hpa.tissues ?? {},
    hpa_subcellular: hpa.subcellular ?? [],
    insights,
    biotools: {
      uniprot: insights && nonEmptyString(insights.uniprot_id) ? `UniProt ${insights.uniprot_id}` : null,
      plddt: numberOrNull(alphafold.global_plddt),
      status: nonEmptyString(alphafold.folding_status),
      domains: alphafold.domains ?? [],
      joints: nonEmptyString(alphafold.flexible_joints),
      transcript: nonEmptyString(ensembl.canonical_transcript ?? vep.mane_select_ensembl),
      alphamissense:
        amClass !== null && amScore !== null
          ? `${amClass} (${amScore.toFixed(2)})`
          : amClass !== null
            ? amClass
            : amScore !== null
              ? amScore.toFixed(2)
              : null,
      constraint: loeufText(loeuf),
      tissues: Object.entries((insights && insights.encode && insights.encode.top_tissues) ?? {}).filter(
        ([, tpm]) => numberOrNull(tpm) !== null
      ),
    },
  };
  vm.missing_fields = [
    ["genotype", genotype],
    ["position", vm.positionExport],
    ["evidence_tier", tierParts.some((t) => t === null) && isComposite ? null : tier],
    ["category", category],
    ["significance", significanceValue],
    ["magnitude", magnitude],
    ["repute", repute],
    ["clinvar_stars", evidenceParts.some((p) => p.stars === null) ? null : true],
    ["gnomad_af", evidenceParts.some((p) => p.af === null) ? null : true],
    ["phenotype", phenotype],
  ]
    .filter(([, value]) => value === null)
    .map(([name]) => name);
  return vm;
}

/** The APOE card's display strings, from the APOE view model (one formatter: core/apoe.js displayDiplotype). */
export function apoeCardModel(apoe) {
  const resolved = apoe.diplotype !== null && apoe.diplotype !== "atypical";
  const stateLabel = APOE_STATE_LABEL[apoe.coverage_state];
  const kbFigure = (prefix) => {
    const hit = apoe.caveats.find((c) => c.startsWith(prefix));
    return hit ? hit.slice(prefix.length) : null;
  };
  const diplotype = resolved ? displayDiplotype(apoe.diplotype) : null;
  const description = [resolved ? apoe.phenotype : apoe.reason, apoe.caveat ? `Caveat: ${apoe.caveat}.` : null]
    .filter((part) => part !== null)
    .join(" ");
  return {
    resolved,
    diplotype,
    stateLabel,
    title: resolved ? `APOE ${diplotype}` : `APOE: ${apoe.diplotype === null ? "no diplotype" : apoe.diplotype}`,
    rawLoci: apoe.components.map((c) => `${c.rsid}: ${c.genotype_display ?? NOT_AVAILABLE}`).join(" · "),
    description: description === "" ? null : description,
    riskBadge: resolved ? kbFigure("Relative risk: ") : stateLabel,
    lifetime: resolved ? kbFigure("Lifetime risk: ") : null,
    pill: resolved ? `${stateLabel} · ${apoe.significance}` : stateLabel,
    hpaSummary:
      Object.keys(apoe.hpa_tissues).length > 0
        ? Object.entries(apoe.hpa_tissues)
            .map(([tissue, level]) => `${tissue} (${level})`)
            .join(", ")
        : null,
  };
}

const ACMG_VERSION_FALLBACK = "ACMG SF";

/** Hero chip text: the ACMG SF version and tested scope, both from the KB manifest. */
export function heroScopeText(manifest) {
  const version = nonEmptyString(manifest && manifest.acmg_sf_version) ?? ACMG_VERSION_FALLBACK;
  const loci = numberOrNull(manifest && manifest.locus_count);
  const genes = numberOrNull(manifest && manifest.gene_count);
  if (loci === null || genes === null) return `🧬 ${version}: tested scope ${NOT_AVAILABLE}`;
  return `🧬 ${version}: ${loci} loci in ${genes} genes tested`;
}

/** The ACMG SF version label, from the manifest. */
export function acmgVersionLabel(manifest) {
  return nonEmptyString(manifest && manifest.acmg_sf_version) ?? ACMG_VERSION_FALLBACK;
}

/** KB badge text and title from the manifest: release, a sha256 prefix and the locus and gene counts. No source versions. */
export function kbBadge(manifest) {
  const release = nonEmptyString(manifest && manifest.release) ?? NOT_AVAILABLE;
  const sha = nonEmptyString(manifest && manifest.sha256) ? manifest.sha256.slice(0, 12) : NOT_AVAILABLE;
  const loci = numberOrNull(manifest && manifest.locus_count);
  const genes = numberOrNull(manifest && manifest.gene_count);
  const scope = loci === null || genes === null ? NOT_AVAILABLE : `${loci} loci in ${genes} genes`;
  return {
    text: `KB ${release} · Offline`,
    title: `Knowledge base release ${release} · sha256 ${sha} · ${scope}`,
  };
}

/** Footer text for the open record's tier. */
export function drawerTierText(vm) {
  return vm.tier === null ? `Evidence tier: ${NOT_AVAILABLE}` : `Evidence ${vm.tier}`;
}

const PARTNER_PHRASE = {
  wildtype: "wild-type: the partner transmits no variant allele",
  heterozygous: "heterozygous: the partner transmits the variant allele with probability 0.5",
  homozygous: "homozygous: the partner transmits the variant allele with probability 1",
};

/** States which partner model produced the offspring figures (AGENTS.md 4.4). */
export function partnerModelNote(partnerModel, af) {
  if (partnerModel === "unscreened") {
    return af === null || af === undefined
      ? `Partner model: unscreened. No gnomAD allele frequency is available for this variant, so the figures are ${NOT_AVAILABLE.toLowerCase()}.`
      : `Partner model: unscreened. The partner's allele probability is the gnomAD allele frequency (${fmtPct(af)}) under Hardy-Weinberg equilibrium.`;
  }
  if (!Object.hasOwn(PARTNER_PHRASE, partnerModel)) throw new Error(`unknown partner model ${JSON.stringify(partnerModel)}`);
  return `Partner model: ${PARTNER_PHRASE[partnerModel]}.`;
}

// ---------------------------------------------------------------------------------------------------------------
// Exports. Both serialisers read the same view models, so a value is the same in the table, drawer, CSV and Markdown.

const csvText = (value) => `"${String(value).replace(/"/g, '""')}"`;
const csvCell = (value) => (value === null || value === undefined ? '""' : typeof value === "number" ? String(value) : csvText(value));

const CSV_HEADERS = [
  "rsID", "Gene", "Genotype", "Chromosome", "Position", "Coverage_State", "Evidence_Tier",
  "Category", "Significance", "Magnitude", "Repute", "ClinVar_Stars",
  "Inheritance_Mode", "Gnomad_AF", "Child_Inherits_Allele_Wildtype_Partner", "Child_Inherits_Allele_Unscreened_Partner",
  "Child_Affected_Unscreened_Partner",
  "Condition_Phenotype", "Result_Statement", "Limitation", "Caveats", "Missing_Fields",
];

const INHERITANCE_FIELDS = [
  "child_inherits_allele_wildtype_partner",
  "child_inherits_allele_unscreened_partner",
  "child_affected_unscreened_partner",
];

/**
 * Wild-type-partner transmission, unscreened-partner transmission, unscreened-partner affected, as CSV values.
 * "N/A" means "not applicable" and is written only for the affected cell of a non-Mendelian gene (contracts C5).
 * Every other unavailable value is null (an empty cell) and its field name is in `missing`.
 */
function inheritanceCells(vm, genes) {
  const seg = vm.segregation;
  if (!seg) return { values: [null, null, null], missing: [...INHERITANCE_FIELDS] };
  const num = (v) => Math.round(v * 1e6) / 1e6;
  const gene = genes[seg.gene];
  const wildtypePartner = geneOutcome(gene, offspringDistribution(seg.altCount, "wildtype", seg.af), seg.allele);
  const unscreened = geneOutcome(gene, offspringDistribution(seg.altCount, "unscreened", seg.af), seg.allele);
  const transmits = (out) => (out.available ? num(out.p1 + out.p2) : null);
  const affected = !seg.mendelian_disease ? "N/A" : unscreened.available ? num(unscreened.affected) : null;
  const values = [transmits(wildtypePartner), transmits(unscreened), affected];
  return { values, missing: INHERITANCE_FIELDS.filter((_, i) => values[i] === null) };
}

/** CSV text for the given view models. Missing values are empty cells and are named in Missing_Fields. */
export function csvReport(viewModels, genes) {
  const rows = [CSV_HEADERS.join(",")];
  for (const vm of viewModels) {
    const inheritance = inheritanceCells(vm, genes);
    const cells = [
      csvCell(vm.exportId),
      csvCell(vm.gene),
      csvCell(vm.genotype),
      csvCell(vm.chromosomes),
      vm.positions.length === 1 && vm.positionExport !== null ? vm.positions[0].pos : csvCell(vm.positionExport),
      csvCell(vm.coverage_state),
      csvCell(vm.tierExport),
      csvCell(vm.category),
      csvCell(vm.significanceValue),
      csvCell(vm.magnitude),
      csvCell(vm.repute),
      csvCell(vm.starsExport),
      csvCell(vm.modelLabel),
      csvCell(vm.afExport),
      ...inheritance.values.map(csvCell),
      csvCell(vm.phenotype),
      csvCell(vm.statement),
      csvCell(vm.limitation),
      csvCell(vm.caveats.join("; ")),
      csvCell([...vm.missing_fields, ...inheritance.missing].join(";")),
    ];
    rows.push(cells.join(","));
  }
  return rows.join("\r\n");
}

/** One Markdown table cell: missing is empty, pipes and line breaks cannot break the table. */
const mdCell = (value) =>
  value === null || value === undefined ? "" : String(value).replace(/\|/g, "/").replace(/\s*\n\s*/g, " ");

const mdRow = (cells) => `| ${cells.map(mdCell).join(" | ")} |\n`;
const mdTable = (headers, rows) =>
  mdRow(headers) + mdRow(headers.map(() => ":---")) + rows.map(mdRow).join("");

const countText = (value) => (typeof value === "number" ? value.toLocaleString("en-US") : NOT_AVAILABLE);

/**
 * Markdown report. `data` holds the worker result: qc, manifest, coverage (the worker's summary), compoundHeterozygotes,
 * independentAssortment, fileName, and the view models in `apoe`, `records`, `negativeChecks`, `arrayGaps`,
 * `insufficientEvidence`.
 */
export function markdownReport(data) {
  const { qc, manifest, coverage: cov, apoe } = data;
  const listed = new Set();
  const unseen = (vms) => vms.filter((vm) => !listed.has(vm.id) && listed.add(vm.id));
  let md = `# Lucidase Variome Clinical Report\n\n`;
  md += `> **CARDINAL SCOPE GUARDRAIL**: ${manifest.guardrail}\n\n`;
  md += `**Sample**: ${data.fileName} | **Format**: ${qc.format_name.toUpperCase()} (${qc.build}) | **Sex-chromosome QC**: ${qc.sex_signal}\n`;
  md += `**Markers**: ${qc.total_snps.toLocaleString("en-US")} | **Call Rate**: ${formatRate(qc.call_rate)} | **Heterozygosity**: ${formatRate(qc.heterozygosity_rate)}\n\n`;

  md += `## Coverage Taxonomy (5-State Summary)\n\n`;
  md += `- **Supported & Observed (State 1)**: ${countText(cov.supported_and_observed_count)} findings\n`;
  md += `- **Tested Wild-Type / Supported Not Observed (State 2)**: ${countText(cov.supported_not_observed_count)} loci\n`;
  md += `- **Microarray Gaps / Not Tested by Chip (State 3)**: ${countText(cov.not_tested_by_array_count)} loci\n`;
  md += `- **Outside Coverage Scope (State 4)**: ${countText(cov.outside_coverage_count)} markers\n`;
  md += `- **Conflicting / Insufficient Evidence (State 5)**: ${countText(cov.insufficient_evidence_count)} loci\n\n`;

  if (apoe) {
    const card = apoeCardModel(apoe);
    md += `## APOE Neuro-Genomic Status\n`;
    md += `- **Locus**: ${apoe.exportId} (${apoe.coordinates ?? NOT_AVAILABLE})\n`;
    md += `- **Diplotype**: ${card.resolved ? card.title : "none asserted"}\n`;
    md += `- **State**: ${card.stateLabel}${apoe.reason ? ` (${apoe.reason})` : ""}\n`;
    if (card.resolved) {
      md += `- **Risk Ratio**: ${card.riskBadge ?? NOT_AVAILABLE}\n`;
      md += `- **Estimated Lifetime Risk**: ${card.lifetime ?? NOT_AVAILABLE}\n`;
    }
    if (apoe.caveat) md += `- **Caveat**: ${apoe.caveat}\n`;
    if (apoe.limitation) md += `- **Limitation**: ${apoe.limitation}\n`;
    md += `- **Underlying Loci**: ${card.rawLoci}\n`;
    if (card.resolved) md += `- **Clinical Guidance**: ${apoe.phenotype ?? NOT_AVAILABLE}\n`;
    md += `\n`;
  }

  if (data.compoundHeterozygotes.length > 0) {
    md += `## Possible Compound Heterozygotes (Phase Unknown)\n\n`;
    for (const ch of data.compoundHeterozygotes) {
      md += `### ${ch.title} (${ch.gene})\n`;
      md += `- **Significance**: ${ch.significance}\n`;
      md += `- **Clinical Summary**: ${ch.summary}\n`;
      md += `- **Segregation**: ${ch.segregation_notes}\n\n`;
    }
  }

  if (data.independentAssortment.length > 0) {
    md += `## Co-occurring Variant Alleles on Unlinked Loci\n\n`;
    for (const ia of data.independentAssortment) {
      md += `### ${ia.type} (${ia.genes.join(" + ")})\n`;
      md += `- **Loci**: ${ia.loci.join(" · ")}\n`;
      md += `- **Chance a child inherits all listed alleles**: ${(ia.joint_transmission_prob * 100).toFixed(0)}% (${ia.assumption})\n`;
      md += `- **Note**: ${ia.description}\n\n`;
    }
  }

  md += `## Observed Clinical Findings (State 1)\n\n`;
  md += mdTable(
    ["rsID", "Gene", "Genotype", "Position", "State", "Tier", "Category", "ClinVar", "Magnitude", "Limitation", "Phenotype / Guidance", "Missing fields"],
    unseen(data.records).map((r) => [
      r.exportId, r.gene, r.genotype, r.coordinates, r.coverage_state, r.tierExport, r.category,
      r.starsExportText, r.magnitude === null ? null : r.magnitude.toFixed(1),
      r.limitationTooltip, r.phenotype, r.missing_fields.join("; "),
    ])
  );

  const negatives = unseen(data.negativeChecks);
  if (negatives.length > 0) {
    md += `\n## Tested Wild-Type Loci (State 2: Supported but Not Observed)\n\n`;
    md += mdTable(
      ["rsID", "Gene", "Genotype", "Position", "State", "Tier", "Result", "Limitation", "Missing fields"],
      negatives.map((r) => [
        r.exportId, r.gene, r.genotype, r.coordinates, r.coverage_state, r.tierExport,
        r.statement ?? r.phenotype, r.limitationTooltip, r.missing_fields.join("; "),
      ])
    );
  }

  const gaps = unseen(data.arrayGaps);
  if (gaps.length > 0) {
    md += `\n## Microarray Gaps (State 3: Not Tested by Chip)\n\n`;
    md += mdTable(
      ["rsID", "Gene", "Build Coordinates", "State", "Reason", "Limitation", "Missing fields"],
      gaps.map((r) => [r.exportId, r.gene, r.coordinates, r.coverage_state, r.phenotype, r.limitationTooltip, r.missing_fields.join("; ")])
    );
  }

  const insufficient = unseen(data.insufficientEvidence);
  if (insufficient.length > 0) {
    md += `\n## Insufficient Evidence or Not Interpretable (State 5)\n\n`;
    md += mdTable(
      ["rsID", "Gene", "Genotype", "Position", "State", "Tier", "Reason", "Limitation", "Missing fields"],
      insufficient.map((r) => [
        r.exportId, r.gene, r.genotype, r.coordinates, r.coverage_state, r.tierExport, r.phenotype, r.limitationTooltip,
        r.missing_fields.join("; "),
      ])
    );
  }
  return md;
}
