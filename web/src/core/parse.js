/**
 * Pure genotype-file parser (contracts C1). No DOM, no `self`, no `fetch`, and no
 * knowledge of the knowledge base: it only turns text into a ParseResult.
 *
 *   ParseResult = { format, build, assay, calls, stats }
 *   Call        = { rsid: string|null, chrom, pos: number|null, alleles: string[]|null }
 *
 * `alleles: null` is a no-call; length 1 is a haploid call. Phase is dropped.
 * `stats`: total_lines (all lines), data_rows (data lines, excluding blanks,
 * comments and the column-header row), skipped_malformed (data lines that could
 * not be parsed), called / no_calls (counted per Call, so a VCF line with two
 * `;`-joined IDs adds two), filtered (VCF calls whose FILTER is neither PASS nor `.`;
 * they are no-calls, so they are also in no_calls; always 0 for array formats).
 * A VCF row whose REF, or a GT-selected ALT, is not A/C/G/T sequence or I/D is a no-call too (in no_calls, not filtered).
 */

export class UnsupportedFormatError extends Error {
  constructor(message) {
    super(message);
    this.name = "UnsupportedFormatError";
  }
}

const HEADER_SCAN_LINES = 200;
const CHROM_ALIASES = { "23": "X", "24": "Y", "25": "XY", "26": "MT", "M": "MT" };
const ARRAY_CODES = /^[ACGTDI]{1,2}$/;
const ARRAY_NOCALLS = new Set(["--", "-", "0", "00", "??", "NN", "."]);

/** Normalise a chromosome label: strip "chr", uppercase, map 23/24/25/26 to X/Y/XY/MT. */
function normalizeChrom(raw) {
  const c = String(raw).trim().replace(/^chr/i, "").toUpperCase();
  return CHROM_ALIASES[c] || c;
}

function parsePos(raw) {
  const s = String(raw).trim();
  return /^\d+$/.test(s) ? Number(s) : null;
}

function isColumnHeader(firstField) {
  return firstField.replace(/"/g, "").trim().toLowerCase() === "rsid";
}

// ---------------------------------------------------------------------------
// Detection (content first; the file extension is only a tie-break)
// ---------------------------------------------------------------------------

function detectFormat(lines, fileName) {
  const head = lines.slice(0, HEADER_SCAN_LINES).map((l) => l.trim()).filter(Boolean);
  const lower = head.map((l) => l.toLowerCase());

  if (lower.some((l) => l.startsWith("##fileformat=vcf") || l.startsWith("#chrom\t") || l.startsWith("#chrom "))) {
    return "vcf";
  }

  const candidates = [];
  const comments = lower.filter((l) => l.startsWith("#"));
  if (comments.some((l) => l.includes("ancestrydna"))) candidates.push("ancestry");
  if (comments.some((l) => l.includes("myheritage"))) candidates.push("myheritage");
  if (comments.some((l) => l.includes("23andme"))) candidates.push("23andme");

  const firstData = head.find((l) => !l.startsWith("#"));
  if (firstData !== undefined) {
    const tabs = firstData.split("\t");
    if (isColumnHeader(tabs[0]) && tabs.length >= 5) candidates.push("ancestry");
    else if (isExact23andMeHeader(tabs)) candidates.push("23andme");
    else if (isMyHeritageHeader(splitCsv(firstData))) candidates.push("myheritage");
    else if (candidates.length === 0) {
      // No header signal at all: accept only a well-formed first data row.
      if (tabs.length >= 5 && parsePos(tabs[2]) !== null) candidates.push("ancestry");
      else if (tabs.length === 4 && parsePos(tabs[2]) !== null) candidates.push("23andme");
      else if (isMyHeritageRow(splitCsv(firstData))) candidates.push("myheritage");
    }
  } else if (candidates.length > 0 && head.every((l) => l.startsWith("#"))) {
    // Comments only, no rows: nothing to parse.
    return candidates[0];
  }

  if (candidates.length === 0) return null;
  if (candidates.length === 1) return candidates[0];
  const name = String(fileName || "").toLowerCase();
  const byExt = candidates.find((c) => name.includes(c === "23andme" ? "23andme" : c));
  return byExt || candidates[0];
}

/** The exact MyHeritage column header `RSID,CHROMOSOME,POSITION,RESULT` (CSV, any case, quotes allowed). */
function isMyHeritageHeader(cols) {
  return cols.length === 4 && cols.map((c) => c.toLowerCase()).join(",") === "rsid,chromosome,position,result";
}

/** A headerless MyHeritage row: "rs<digits>", a chromosome, a digits position and a valid genotype code. */
function isMyHeritageRow(cols) {
  return (
    cols.length >= 4 &&
    /^rs\d+$/i.test(cols[0]) &&
    cols[1] !== "" &&
    /^\d+$/.test(cols[2]) &&
    arrayAlleles(cols[3]) !== undefined
  );
}

/** The exact column header `rsid chromosome position genotype` (tab-separated). */
function isExact23andMeHeader(cols) {
  return (
    cols.length === 4 &&
    cols.map((c) => c.trim().toLowerCase()).join("\t") === "rsid\tchromosome\tposition\tgenotype"
  );
}

const BUILD_PATTERNS = [
  // GRCh38: GRCh38[.pN], hg38, hs38[DH], GATK "assembly38", accession GCA_000001405.15.
  ["GRCh38", /(?:^|[^a-z0-9])(?:grch38|hg38|hs38(?:dh)?|assembly38|build 38|gca_000001405\.15)(?:[^a-z0-9]|$)/],
  // GRCh37: GRCh37[.pN], hg19, b37, hs37d5, human_g1k_v37.
  ["GRCh37", /(?:^|[^a-z0-9])(?:grch37|hg19|b37|hs37d5|build 37)(?:[^a-z0-9]|$)|g1k_v37/],
];

function matchBuild(lowerLine) {
  for (const [build, re] of BUILD_PATTERNS) if (re.test(lowerLine)) return build;
  return null;
}

/** Array build comes from header comments only. */
function detectArrayBuild(lines) {
  for (const line of lines.slice(0, HEADER_SCAN_LINES)) {
    if (!line.startsWith("#")) continue;
    const b = matchBuild(line.toLowerCase());
    if (b) return b;
  }
  return "unknown";
}

/** VCF build comes from ##reference and ##contig assembly tokens. */
function detectVcfBuild(lines) {
  for (const line of lines) {
    if (!line.startsWith("##")) {
      if (line.startsWith("#CHROM") || line.startsWith("#chrom")) break;
      continue;
    }
    const l = line.toLowerCase();
    if (!l.startsWith("##reference") && !l.startsWith("##contig") && !l.startsWith("##assembly")) continue;
    const b = matchBuild(l);
    if (b) return b;
  }
  return "unknown";
}

// ---------------------------------------------------------------------------
// Per-format line parsers. Each returns Call[] or null when the line is malformed.
// ---------------------------------------------------------------------------

/** "AG", "A", "DI", "--" ... to alleles; undefined when the code is malformed. */
function arrayAlleles(code) {
  const g = code.trim().toUpperCase();
  if (ARRAY_NOCALLS.has(g)) return null;
  return ARRAY_CODES.test(g) ? g.split("") : undefined;
}

function arrayCall(rsid, chrom, posRaw, alleles) {
  const pos = parsePos(posRaw);
  if (!rsid || !chrom || pos === null || alleles === undefined) return null;
  return [{ rsid, chrom: normalizeChrom(chrom), pos, alleles }];
}

function parse23andMeLine(line) {
  let cols = line.split("\t");
  if (cols.length < 4) cols = line.trim().split(/\s+/);
  if (cols.length < 4) return null;
  return arrayCall(cols[0].trim(), cols[1], cols[2], arrayAlleles(cols[3]));
}

function parseAncestryLine(line) {
  const cols = line.split("\t");
  if (cols.length < 5) return null;
  const a = arrayAlleles(cols[3]);
  const b = arrayAlleles(cols[4]);
  // One single-letter allele per column; a missing allele makes the call a no-call.
  if (a === undefined || b === undefined || (a && a.length !== 1) || (b && b.length !== 1)) return null;
  return arrayCall(cols[0].trim(), cols[1], cols[2], a === null || b === null ? null : [a[0], b[0]]);
}

/** Split one CSV line, honouring double quotes (MyHeritage only). */
function splitCsv(line) {
  const out = [];
  let cur = "";
  let quoted = false;
  for (const ch of line) {
    if (ch === '"') quoted = !quoted;
    else if (ch === "," && !quoted) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

function parseMyHeritageLine(line) {
  const cols = splitCsv(line);
  if (cols.length < 4) return null;
  return arrayCall(cols[0], cols[1], cols[2], arrayAlleles(cols[3]));
}

/**
 * A VCF allele we will carry: A/C/G/T sequences (SNPs and indel sequences) or the single codes I/D.
 * Anything else (symbolic `<DEL>`, `=1+1`, markup) is untrusted file content and is never kept.
 */
const VCF_ALLELE = /^(?:[ACGT]+|[ID])$/i;

/** GT string and allele table to alleles: null = no-call, undefined = malformed. */
function vcfAlleles(gt, table) {
  const tokens = gt.split(/[/|]/);
  const out = [];
  // REF is checked for every row; an ALT only when the GT selects it.
  let missing = table[0] !== "*" && !VCF_ALLELE.test(table[0]);
  for (const t of tokens) {
    if (t === ".") {
      missing = true;
      continue;
    }
    if (!/^\d+$/.test(t)) return undefined;
    const idx = Number(t);
    if (idx >= table.length) return undefined;
    // "*" is a spanning deletion, not a base: the position has no usable call.
    if (table[idx] === "*") {
      missing = true;
      continue;
    }
    if (!VCF_ALLELE.test(table[idx])) {
      missing = true;
      continue;
    }
    out.push(table[idx].toUpperCase());
  }
  return missing ? null : out;
}

/** A VCF record is usable only when FILTER is PASS or `.`; anything else failed the caller's filters. */
function failedFilter(filterField) {
  const f = filterField.trim();
  return f !== "PASS" && f !== ".";
}

function parseVcfLine(line, ctx) {
  const cols = line.split("\t");
  const sampleIdx = ctx.sampleIdx;
  if (cols.length <= sampleIdx || cols.length < 5) return null;
  const pos = parsePos(cols[1]);
  if (pos === null || !cols[0].trim()) return null;

  const keys = cols[ctx.formatIdx].split(":");
  const gtIdx = keys.indexOf("GT");
  if (gtIdx < 0) return null;
  const gt = cols[sampleIdx].split(":")[gtIdx];
  if (gt === undefined || gt === "") return null;

  const alt = cols[4].trim();
  const table = [cols[3].trim(), ...(alt === "." || alt === "" ? [] : alt.split(","))].map((a) => a.trim());
  if (!table[0]) return null;
  const parsedAlleles = vcfAlleles(gt.trim(), table);
  if (parsedAlleles === undefined) return null;
  const filtered = failedFilter(cols[6]);
  const alleles = filtered ? null : parsedAlleles;

  const ids = cols[2].trim() === "." || cols[2].trim() === "" ? [null] : cols[2].split(";").map((s) => s.trim()).filter((s) => s && s !== ".");
  if (ids.length === 0) ids.push(null);
  const chrom = normalizeChrom(cols[0]);
  if (filtered) ctx.filtered += ids.length;
  return ids.map((rsid) => ({ rsid, chrom, pos, alleles: alleles === null ? null : [...alleles] }));
}

const LINE_PARSERS = {
  "23andme": parse23andMeLine,
  ancestry: parseAncestryLine,
  myheritage: parseMyHeritageLine,
};

/** True when the #CHROM line (or, lacking one, the first data row) has a sample column after FORMAT. */
function hasSampleColumn(lines) {
  for (const line of lines) {
    if (line.startsWith("#CHROM") || line.startsWith("#chrom")) return line.split("\t").length >= 10;
    if (!line.startsWith("#") && line.trim()) return line.split("\t").length >= 10;
  }
  return false;
}

// ---------------------------------------------------------------------------

/**
 * Parse a raw genotype file. Throws UnsupportedFormatError when the content is not
 * a recognised format (never guesses); throws TypeError when `text` is not a string.
 */
export function parseGenotypeFile(text, fileName = "") {
  if (typeof text !== "string") throw new TypeError("parseGenotypeFile: text must be a string");
  const lines = text.replace(/^﻿+/, "").split(/\r?\n/);
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();

  const format = detectFormat(lines, fileName);
  if (format === null) {
    throw new UnsupportedFormatError(
      "Unsupported file format: expected a 23andMe, AncestryDNA or MyHeritage raw-data file, or a VCF."
    );
  }

  const assay = format === "vcf" ? "vcf" : "array";
  const build = format === "vcf" ? detectVcfBuild(lines) : detectArrayBuild(lines);
  if (format === "vcf" && !hasSampleColumn(lines)) {
    throw new UnsupportedFormatError("Unsupported file: VCF contains no sample genotypes (no FORMAT or sample column).");
  }
  const calls = [];
  const stats = { total_lines: lines.length, data_rows: 0, called: 0, no_calls: 0, skipped_malformed: 0, filtered: 0 };

  // VCF columns are fixed: FORMAT is column 8 and the FIRST sample is column 9.
  const vcfCtx = { sampleIdx: 9, formatIdx: 8, filtered: 0 };
  const parseLine = format === "vcf" ? (l) => parseVcfLine(l, vcfCtx) : LINE_PARSERS[format];

  for (const line of lines) {
    if (!line.trim()) continue;
    if (line.startsWith("#")) continue;
    if (format !== "vcf" && isColumnHeader(line.split(/[\t,]/)[0])) continue;
    stats.data_rows++;
    const parsed = parseLine(line);
    if (parsed === null) {
      stats.skipped_malformed++;
      continue;
    }
    for (const call of parsed) {
      calls.push(call);
      if (call.alleles === null) stats.no_calls++;
      else stats.called++;
    }
  }

  stats.filtered = vcfCtx.filtered;
  return { format, build, assay, calls, stats };
}
