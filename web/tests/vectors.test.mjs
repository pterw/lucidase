// Generic runner for the shared vectors (contracts C6). Every tests/vectors/*.json
// file must have a handler below, keyed by file name; a file without one fails
// loudly so a new vector area cannot be silently ignored.
//
// Vector: { id, description, input, expected }. `expected` holds genetics or format
// facts, compared as a SUBSET of the real output:
//   - plain keys (format, build, assay, stats, ...): the actual value must contain them
//     (objects recursively, scalars and arrays by deep equality);
//   - `calls`: the exact call list;  `calls_include`: calls that must be present;
//   - `error`: the parser must throw an error whose name equals it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const VECTOR_DIR = fileURLToPath(new URL("../../tests/vectors/", import.meta.url));

function assertSubset(actual, expected, path) {
  if (expected !== null && typeof expected === "object" && !Array.isArray(expected)) {
    assert.ok(actual !== null && typeof actual === "object", `${path}: expected an object`);
    for (const [k, v] of Object.entries(expected)) assertSubset(actual[k], v, `${path}.${k}`);
  } else {
    assert.deepEqual(actual, expected, path);
  }
}

// Subset comparison where numbers match within 1e-12 and arrays match element by element.
function assertClose(actual, expected, path) {
  if (typeof expected === "number") {
    assert.equal(typeof actual, "number", `${path}: expected a number, got ${JSON.stringify(actual)}`);
    assert.ok(Math.abs(actual - expected) <= 1e-12, `${path}: ${actual} != ${expected}`);
  } else if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${path}: expected an array`);
    assert.equal(actual.length, expected.length, `${path}: length`);
    expected.forEach((e, i) => assertClose(actual[i], e, `${path}[${i}]`));
  } else if (expected !== null && typeof expected === "object") {
    assert.ok(actual !== null && typeof actual === "object", `${path}: expected an object`);
    for (const [k, v] of Object.entries(expected)) assertClose(actual[k], v, `${path}.${k}`);
  } else {
    assert.deepEqual(actual, expected, path);
  }
}

const HANDLERS = {
  "parse.json": async (vector) => {
    const { parseGenotypeFile } = await import("../src/core/parse.js");
    const { text, fileName } = vector.input;
    const exp = vector.expected;
    if (exp.error) {
      assert.throws(
        () => parseGenotypeFile(text, fileName),
        (err) => err.name === exp.error,
        `${vector.id}: expected ${exp.error}`
      );
      return;
    }
    const result = parseGenotypeFile(text, fileName);
    for (const [key, want] of Object.entries(exp)) {
      if (key === "calls_include") {
        for (const call of want) {
          assert.ok(
            result.calls.some((c) => JSON.stringify(c) === JSON.stringify(call)),
            `${vector.id}: missing call ${JSON.stringify(call)}`
          );
        }
      } else {
        assertSubset(result[key], want, `${vector.id}.${key}`);
      }
    }
  },

  // input: { locus: {ref, alt, allele_codes, chrom}, alleles }; expected is a subset of the result.
  "alleles.json": async (vector) => {
    const { resolveAltCount } = await import("../src/core/alleles.js");
    const result = resolveAltCount(vector.input.locus, vector.input.alleles, vector.input.assay);
    assertSubset(result, vector.expected, vector.id);
  },

  // input: { kb, parse }; expected: { records: {rsid: subset}, summary: subset }.
  "classify.json": async (vector) => {
    const { validateKb } = await import("../src/core/kb.js");
    const { classify } = await import("../src/core/classify.js");
    const kb = validateKb(vector.input.kb);
    const out = classify(vector.input.parse, kb);
    for (const [rsid, want] of Object.entries(vector.expected.records || {})) {
      const rec = out.records.find((r) => r.rsid === rsid);
      assert.ok(rec, `${vector.id}: no record for ${rsid}`);
      assertSubset(rec, want, `${vector.id}.${rsid}`);
    }
    if (vector.expected.summary) assertSubset(out.summary, vector.expected.summary, `${vector.id}.summary`);
  },

  // input: { kb: {genes.APOE, loci.rs429358}, components: [classified component records] }; expected is a subset of
  // the APOE record, plus `caveats_include`: strings the record's caveats must contain.
  "apoe.json": async (vector) => {
    const { resolveApoe } = await import("../src/core/apoe.js");
    const rec = resolveApoe(structuredClone(vector.input.components), vector.input.kb);
    const { caveats_include: caveats, ...subset } = vector.expected;
    assertSubset(rec, subset, vector.id);
    for (const want of caveats || []) {
      assert.ok(rec.interpretation.caveats.includes(want), `${vector.id}: missing caveat "${want}"`);
    }
  },

  // input: { fn: "scenario" | "status" | "multi_locus" | "compound" | "apoe_e4", ... }. Numbers compare within
  // 1e-12; `absent` lists dotted paths that must not exist; `text_includes` / `text_excludes` check the
  // lower-cased JSON of the result (scenario, multi_locus, compound).
  "inheritance.json": async (vector) => {
    const inh = await import("../src/core/inheritance.js");
    const { fn, gene, altCount, partner, af, allele, genes, records } = vector.input;
    let result;
    if (fn === "scenario") {
      const dist = inh.offspringDistribution(altCount, partner, af);
      result = { dist, outcome: inh.geneOutcome(gene, dist, allele) };
    } else if (fn === "status") {
      result = { status: inh.patientStatus(gene, altCount) };
    } else if (fn === "multi_locus") {
      result = { findings: inh.detectMultiLocus(records, genes) };
    } else if (fn === "compound") {
      result = { findings: inh.detectCompoundHeterozygosity(records, genes) };
    } else if (fn === "apoe_e4") {
      // The APOE row's offspring figures: the e4 count comes from the diplotype; no count, no figures.
      const { e4CountForDiplotype } = await import("../src/core/apoe.js");
      const e4Count = e4CountForDiplotype(vector.input.diplotype);
      result = { e4_count: e4Count };
      if (e4Count !== null) {
        const dist = inh.offspringDistribution(e4Count, partner, af);
        result = { ...result, dist, outcome: inh.geneOutcome(gene, dist, allele) };
      }
    } else {
      assert.fail(`${vector.id}: unknown fn ${fn}`);
    }
    const { absent = [], text_includes = [], text_excludes = [], ...facts } = vector.expected;
    assertClose(result, facts, vector.id);
    for (const path of absent) {
      const value = path.split(".").reduce((o, k) => (o === undefined || o === null ? undefined : o[k]), result);
      assert.equal(value, undefined, `${vector.id}: ${path} must be absent`);
    }
    const text = JSON.stringify(result).toLowerCase();
    for (const t of text_includes) assert.ok(text.includes(t.toLowerCase()), `${vector.id}: missing "${t}"`);
    for (const t of text_excludes) assert.ok(!text.includes(t.toLowerCase()), `${vector.id}: must not contain "${t}"`);
  },
};

const files = readdirSync(VECTOR_DIR).filter((f) => f.endsWith(".json")).sort();

test("tests/vectors holds at least one vector file", () => {
  assert.ok(files.length > 0);
});

for (const file of files) {
  const handler = HANDLERS[file];
  if (!handler) {
    test(`vectors/${file} has a handler`, () => {
      assert.fail(`no handler for tests/vectors/${file}; add one to web/tests/vectors.test.mjs`);
    });
    continue;
  }
  const vectors = JSON.parse(readFileSync(join(VECTOR_DIR, file), "utf8"));
  for (const vector of vectors) {
    test(`${file}: ${vector.id}`, () => handler(vector));
  }
}
