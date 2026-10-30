/**
 * Karyogram layout (contracts K-C2). Pure and deterministic: no DOM, no `self`, no `fetch`.
 *
 * Three separate tracks (the reference track never carries a sample field and the sample track never carries a KB
 * fact):
 *   geometry:  the assembly's chromosomes, from the KB `assemblies`;
 *   reference: the KB loci at their reference position;
 *   sample:    null, or the file's own marker density, coverage states and totals.
 *
 * Nothing from a file is placed by position when its build is unknown (fail closed): density is "unavailable" and
 * every row on a drawable chromosome is counted in `totals.notPlacedBuildUnknown`.
 */
import { COVERAGE_STATES } from "./coverage.js";

export const CHROMOSOME_ORDER = Object.freeze([
  ...Array.from({ length: 22 }, (_, i) => String(i + 1)),
  "X",
  "Y",
]);

export const DEFAULT_BIN_SIZE = 2_000_000;

const KNOWN_BUILDS = ["GRCh37", "GRCh38"];
const DRAWABLE = new Set(CHROMOSOME_ORDER);
const VALID_STATES = new Set(Object.values(COVERAGE_STATES));

/** Bin index of a 1-based position. */
export function binIndex(pos, binSize) {
  return Math.floor((pos - 1) / binSize);
}

/**
 * Rolls up individual locus observation states for a gene to a single clinical result.
 * Pure and deterministic (contracts K-C2).
 *
 * Clinical honesty rules (contracts AGENTS.md 4.1 & 4.6):
 * - If any locus has supported_and_observed: "supported_and_observed" (Found).
 * - Else if any locus has insufficient_evidence: "insufficient_evidence" (Unclear).
 * - Else if all loci are not_tested_by_array (0 tested): "not_tested_by_array" (Not on your chip).
 * - Else if tested < total (partial coverage): "supported_not_observed", isPartial: true,
 *   label: `Not found (${tested} of ${total} tested)`.
 * - Else: "supported_not_observed", isPartial: false, label: "Not found".
 *
 * @param {Array<{ rsid: string }|string>} loci The gene's loci (objects with rsid or string rsIDs).
 * @param {Record<string, string>|null} observations Locus observations map, or null for reference.
 * @returns {{ state: string, label: string, tested: number, total: number, isPartial: boolean }}
 */
export function rollUpGeneResult(loci, observations) {
  if (!Array.isArray(loci) || loci.length === 0) {
    throw new Error("rollUpGeneResult: loci must be a non-empty array");
  }
  const rsids = loci.map((l) => (typeof l === "string" ? l : (l && l.rsid)));
  for (const rsid of rsids) {
    if (typeof rsid !== "string" || !rsid.startsWith("rs")) {
      throw new Error(`rollUpGeneResult: invalid locus rsid "${rsid}"`);
    }
  }
  const total = rsids.length;
  if (!observations) {
    return {
      state: "reference",
      label: "No file yet",
      tested: 0,
      total,
      isPartial: false,
    };
  }

  const states = rsids.map((rsid) => {
    if (!Object.hasOwn(observations, rsid)) {
      throw new Error(`rollUpGeneResult: no observation for locus ${rsid}`);
    }
    const s = observations[rsid];
    if (!VALID_STATES.has(s)) {
      throw new Error(`rollUpGeneResult: unknown or missing coverage state "${s}" for ${rsid}`);
    }
    return s;
  });

  const observed = states.filter((s) => s === COVERAGE_STATES.SUPPORTED_AND_OBSERVED).length;
  const unclear = states.filter((s) => s === COVERAGE_STATES.INSUFFICIENT_EVIDENCE).length;
  const gaps = states.filter((s) => s === COVERAGE_STATES.NOT_TESTED_BY_ARRAY).length;
  const tested = total - gaps;

  if (observed > 0) {
    return {
      state: COVERAGE_STATES.SUPPORTED_AND_OBSERVED,
      label: "Found",
      tested,
      total,
      isPartial: false,
    };
  }
  if (unclear > 0) {
    return {
      state: COVERAGE_STATES.INSUFFICIENT_EVIDENCE,
      label: "Unclear",
      tested,
      total,
      isPartial: false,
    };
  }
  if (tested === 0) {
    return {
      state: COVERAGE_STATES.NOT_TESTED_BY_ARRAY,
      label: "Not on your chip",
      tested: 0,
      total,
      isPartial: false,
    };
  }
  if (tested < total) {
    return {
      state: COVERAGE_STATES.SUPPORTED_NOT_OBSERVED,
      label: `Not found (${tested} of ${total} tested)`,
      tested,
      total,
      isPartial: true,
    };
  }
  return {
    state: COVERAGE_STATES.SUPPORTED_NOT_OBSERVED,
    label: "Not found",
    tested,
    total,
    isPartial: false,
  };
}


function assertLayoutInputs(kb, binSize) {
  if (!kb || typeof kb !== "object" || !kb.assemblies || typeof kb.assemblies !== "object") {
    throw new Error("layoutKaryogram: the knowledge base carries no assemblies");
  }
  if (!kb.loci || typeof kb.loci !== "object") {
    throw new Error("layoutKaryogram: the knowledge base carries no loci");
  }
  if (!Number.isInteger(binSize) || binSize <= 0) {
    throw new Error(`layoutKaryogram: binSize must be a positive integer, got ${binSize}`);
  }
}

export function layoutKaryogram({ kb, sample = null, binSize = DEFAULT_BIN_SIZE } = {}) {
  assertLayoutInputs(kb, binSize);

  const loci = Object.values(kb.loci);
  if (sample) {
    for (const locus of loci) {
      const observations = sample.observations ?? {};
      if (!Object.hasOwn(observations, locus.rsid)) {
        throw new Error(`layoutKaryogram: no observation for KB locus ${locus.rsid}`);
      }
      if (!VALID_STATES.has(observations[locus.rsid])) {
        throw new Error(
          `layoutKaryogram: observation for KB locus ${locus.rsid} is not a coverage state: ${String(observations[locus.rsid])}`,
        );
      }
    }
  }

  const known = sample ? KNOWN_BUILDS.includes(sample.build) : false;
  const geometryBuild = known ? sample.build : "GRCh38";
  const assembly = kb.assemblies[geometryBuild];
  if (!assembly || !assembly.chromosomes) {
    throw new Error(`layoutKaryogram: the knowledge base has no ${geometryBuild} assembly`);
  }

  const chromosomes = CHROMOSOME_ORDER.map((name) => {
    const c = assembly.chromosomes[name];
    if (!c) throw new Error(`layoutKaryogram: ${geometryBuild} has no chromosome ${name}`);
    return { name, length: c.length, centromere: [...c.centromere] };
  });

  const posField = geometryBuild === "GRCh37" ? "pos_grch37" : "pos_grch38";
  const reference = {
    loci: loci.map((l) => ({ rsid: l.rsid, gene: l.gene, chrom: l.chrom, pos: l[posField] })),
  };

  if (!sample) {
    return { geometry: { build: geometryBuild, chromosomes }, reference, sample: null, binSize };
  }

  const lengthOf = Object.fromEntries(chromosomes.map((c) => [c.name, c.length]));
  const bins = known
    ? Object.fromEntries(chromosomes.map((c) => [c.name, new Array(Math.ceil(c.length / binSize)).fill(0)]))
    : null;
  const totals = { rows: 0, placed: 0, mt: 0, unplaced: {}, outOfBounds: 0, notPlacedBuildUnknown: 0 };

  for (const call of sample.calls) {
    totals.rows += 1;
    const chrom = call.chrom;
    if (chrom === "MT") {
      totals.mt += 1;
    } else if (!DRAWABLE.has(chrom)) {
      // defineProperty, not assignment: a name such as "__proto__" or "constructor" must stay a plain own key.
      const seen = Object.hasOwn(totals.unplaced, chrom) ? totals.unplaced[chrom] : 0;
      Object.defineProperty(totals.unplaced, chrom, { value: seen + 1, enumerable: true, writable: true, configurable: true });
    } else if (!known) {
      totals.notPlacedBuildUnknown += 1;
    } else if (!Number.isInteger(call.pos) || call.pos < 1 || call.pos > lengthOf[chrom]) {
      totals.outOfBounds += 1;
    } else {
      bins[chrom][binIndex(call.pos, binSize)] += 1;
      totals.placed += 1;
    }
  }

  const unplacedSum = Object.values(totals.unplaced).reduce((a, b) => a + b, 0);
  const accounted = totals.placed + totals.mt + unplacedSum + totals.outOfBounds + totals.notPlacedBuildUnknown;
  if (totals.rows !== sample.calls.length || totals.rows !== accounted) {
    throw new Error(
      `layoutKaryogram: totals invariant broken (rows ${totals.rows}, calls ${sample.calls.length}, accounted ${accounted})`,
    );
  }

  return {
    geometry: { build: geometryBuild, chromosomes },
    reference,
    sample: {
      build: sample.build,
      density: known ? "available" : "unavailable",
      binSize,
      bins,
      observations: { ...sample.observations },
      totals,
    },
  };
}
