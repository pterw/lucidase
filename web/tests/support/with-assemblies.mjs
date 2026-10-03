// The shared mini knowledge bases (tests/vectors/*.json) predate the `assemblies` section (K-C1) and are
// also read by the Python tests. This adds a geometry stub, long enough for every mini locus, in memory.
const NAMES = [...Array.from({ length: 22 }, (_, i) => String(i + 1)), "X", "Y"];
const LENGTH = 300_000_000;

const stub = (ucsc) => ({
  ucsc,
  sources: ["chromInfo", "cytoBand"].map((table) => ({
    table,
    url: `https://example.test/${ucsc}/${table}`,
    retrieved: "2026-01-01",
    sha256: "0".repeat(64),
  })),
  chromosomes: Object.fromEntries(NAMES.map((n) => [n, { length: LENGTH, centromere: [1, 2] }])),
});

/** A copy of the raw mini KB with a stub `assemblies` section (an existing one is kept). */
export function withAssemblies(raw) {
  return { assemblies: { GRCh37: stub("hg19"), GRCh38: stub("hg38") }, ...raw };
}
