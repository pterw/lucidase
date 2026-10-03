/**
 * Allele resolution (contracts C3). Pure: no DOM, no `self`, no `fetch`.
 *
 * The KB's ref/alt are build-independent plus-strand alleles; indel loci hold the
 * VCF-normalised form (left-aligned, with the anchor base). A call's alleles are
 * compared to that form verbatim, and strand complementing is only ever tried for a
 * single-base, non-palindromic site.
 */

const COMPLEMENT = Object.freeze({ A: "T", T: "A", C: "G", G: "C" });

/** Chromosomes where a single reported allele is a real haploid call. */
const HAPLOID_CHROMS = new Set(["X", "Y", "MT"]);

const isBase = (s) => typeof s === "string" && s.length === 1 && s in COMPLEMENT;

/** A site is palindromic when ref and alt are single bases that complement each other (A/T, C/G). */
export function isPalindromic(ref, alt) {
  return isBase(ref) && isBase(alt) && COMPLEMENT[ref] === alt;
}

const fail = (reason) => ({ ok: false, reason });

function countAlts(alleles, ref, alt) {
  let n = 0;
  for (const a of alleles) {
    if (a === alt) n += 1;
    else if (a !== ref) return null;
  }
  return n;
}

/**
 * locus: { ref, alt, allele_codes, chrom }; alleles: string[] | null.
 * Returns { ok: true, altCount: 0|1|2, strandFlipped } or { ok: false, reason: "no_call" | "unresolvable" }.
 * "palindromic_ambiguous" is part of the contract's reason set but is never produced: a palindromic
 * site's complement is the same pair, so an unmatched call there is simply "unresolvable".
 */
export function resolveAltCount(locus, alleles) {
  if (!Array.isArray(alleles) || alleles.length === 0) return fail("no_call");

  const { ref, alt, allele_codes: codes, chrom } = locus;

  // 1. Array indel codes map through allele_codes (D/I -> ref or alt sequence).
  let called = alleles.map((a) => {
    if ((a === "D" || a === "I") && codes && (codes[a] === "ref" || codes[a] === "alt")) {
      return codes[a] === "ref" ? ref : alt;
    }
    return a;
  });

  // Haploid counts as two copies only where the chromosome really is haploid.
  if (called.length === 1) {
    if (!HAPLOID_CHROMS.has(chrom)) return fail("unresolvable");
    called = [called[0], called[0]];
  }
  if (called.length !== 2) return fail("unresolvable");

  // 2. Every allele in {ref, alt}: count the alts.
  const direct = countAlts(called, ref, alt);
  if (direct !== null) return { ok: true, altCount: direct, strandFlipped: false };

  // 3. Complement only a single-base, non-palindromic site, and only the whole genotype.
  if (isBase(ref) && isBase(alt) && !isPalindromic(ref, alt) && called.every(isBase)) {
    const flipped = countAlts(called.map((a) => COMPLEMENT[a]), ref, alt);
    if (flipped !== null) return { ok: true, altCount: flipped, strandFlipped: true };
  }

  // 4. Otherwise it cannot be interpreted.
  return fail("unresolvable");
}
