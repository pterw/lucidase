/**
 * Classification of a ParseResult against a validated KB (contracts C2-C4). Pure: no DOM,
 * no `self`, no `fetch`. One record per KB locus, always, so absence is never silent.
 */
import { resolveAltCount } from "./alleles.js";
import { deriveCoverageState, summarizeCoverage } from "./coverage.js";

const POSITION_FIELD = { GRCh37: "pos_grch37", GRCh38: "pos_grch38" };

/**
 * Calls matched to KB loci. A call whose rsID is a KB key matches that locus and is never re-matched by
 * position. Any other call (no rsID, or an rsID the KB lacks) matches by chrom:pos for the file's build.
 */
function matchCalls(parseResult, kb) {
  const byRsid = new Map();
  let matched = 0;
  const positions = kb.byPosition[parseResult.build];
  for (const call of parseResult.calls) {
    let rsid = null;
    if (call.rsid !== null && Object.hasOwn(kb.loci, call.rsid)) {
      rsid = call.rsid;
    } else if (positions && call.pos !== null) {
      rsid = positions.get(`${call.chrom}:${call.pos}`) ?? null;
    }
    if (rsid === null) continue;
    matched += 1;
    if (!byRsid.has(rsid)) byRsid.set(rsid, []);
    byRsid.get(rsid).push(call);
  }
  return { byRsid, matched };
}

const sameAlleles = (a, b) =>
  a.alleles === null || b.alleles === null
    ? a.alleles === b.alleles
    : [...a.alleles].sort().join("/") === [...b.alleles].sort().join("/");

/** Returns { records, summary }. Records follow KB order. */
export function classify(parseResult, kb) {
  const { byRsid, matched } = matchCalls(parseResult, kb);
  const posField = POSITION_FIELD[parseResult.build];

  const records = kb.lociList.map((locus) => {
    const calls = byRsid.get(locus.rsid) || [];

    // If an array indel locus specifies allele_codes, prefer calls using those codes (D/I)
    // over coincident SNV bystander calls that happen to share genomic coordinates.
    let candidates = calls;
    if (parseResult.assay !== "vcf" && locus.allele_codes) {
      const codes = locus.allele_codes;
      const codeCalls = calls.filter((c) => c.alleles && c.alleles.every((a) => a in codes));
      if (codeCalls.length > 0) candidates = codeCalls;
    }

    const exact = candidates.filter((c) => c.rsid === locus.rsid);
    if (exact.length > 0) candidates = exact;

    const call = candidates[0];
    const conflicting = call !== undefined && candidates.some((c) => !sameAlleles(c, call));

    let resolution;
    if (call && call.alleles !== null) {
      // Two calls for one locus that disagree are never guessed between.
      resolution = conflicting ? { ok: false, reason: "unresolvable" } : resolveAltCount(locus, call.alleles, parseResult.assay);
    }
    const state = deriveCoverageState({
      assay: parseResult.assay,
      call,
      resolution,
      evidenceSufficiency: locus.evidence_sufficiency,
    });

    const altCount = resolution && resolution.ok ? resolution.altCount : null;
    return {
      rsid: locus.rsid,
      gene: locus.gene,
      chrom: locus.chrom,
      pos: posField ? locus[posField] : call && call.pos !== null ? call.pos : null,
      genotype_display: call && call.alleles !== null ? call.alleles.join("/") : null,
      altCount,
      strandFlipped: altCount === null ? null : resolution.strandFlipped,
      coverage_state: state.coverage_state,
      sample_observation: state.sample_observation,
      reason: state.reason,
      interpretation_key: altCount === null ? null : String(altCount),
      interpretation: altCount === null ? null : locus.interpretations[String(altCount)],
      evidence: locus.evidence,
      evidence_tier: locus.evidence_tier,
      tier_source: locus.tier_source,
      tier_rationale: locus.tier_rationale,
      tier_citation: locus.tier_citation,
      evidence_sufficiency: locus.evidence_sufficiency,
      limitation: locus.limitation,
      acmg_sf: kb.genes[locus.gene].acmg_sf,
      role: locus.role,
      // APOE components feed the combined APOE finding; the UI must not list them on their own.
      standalone: locus.role !== "apoe_component",
    };
  });

  const outside = Math.max(0, parseResult.calls.length - matched);
  return { records, summary: summarizeCoverage(records, outside) };
}
