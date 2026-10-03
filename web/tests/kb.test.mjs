import { test } from "node:test";
import assert from "node:assert/strict";
import { KbSchemaError, validateKb } from "../src/core/kb.js";

const interp = (category, magnitude) => ({
  category,
  significance: category,
  magnitude,
  repute: "Neutral",
  phenotype: `${category} phenotype`,
  drug_response: null,
  caveats: [],
});

function goodKb() {
  return {
    schema_version: 2,
    manifest: { release: "test", guardrail: "Absence of a finding is not absence of risk." },
    genes: {
      HFE: {
        inheritance: { model: "autosomal_recessive", mendelian_disease: true, disease: "HH", omim: "1", penetrance: null },
        acmg_sf: true,
        insights: null,
      },
    },
    loci: {
      rs1: {
        rsid: "rs1",
        gene: "HFE",
        chrom: "6",
        pos_grch37: 100,
        pos_grch38: 200,
        ref: "G",
        alt: "A",
        allele_codes: null,
        interpretations: { 0: interp("Not detected", 0), 1: interp("Carrier", 2), 2: interp("Pathogenic", 5) },
        evidence: {},
        evidence_tier: "Tier A",
        tier_source: "clinvar_review",
        tier_rationale: null,
        tier_citation: null,
        evidence_sufficiency: "sufficient",
        limitation: null,
        role: "standard",
      },
    },
  };
}

function problemsOf(kb) {
  try {
    validateKb(kb);
  } catch (err) {
    assert.ok(err instanceof KbSchemaError, `unexpected error type ${err && err.name}`);
    return err.problems;
  }
  assert.fail("validateKb accepted an invalid knowledge base");
}

test("a valid knowledge base is indexed by rsid and by chrom:pos for each build, and frozen", () => {
  const kb = validateKb(goodKb());
  assert.equal(kb.loci.rs1.gene, "HFE");
  assert.equal(kb.byPosition.GRCh37.get("6:100"), "rs1");
  assert.equal(kb.byPosition.GRCh38.get("6:200"), "rs1");
  assert.ok(Object.isFrozen(kb));
  assert.ok(Object.isFrozen(kb.loci.rs1));
  assert.ok(Object.isFrozen(kb.loci.rs1.interpretations["1"]));
  assert.deepEqual(kb.lociList.map((l) => l.rsid), ["rs1"]);
});

test("validation does not alter its input", () => {
  const input = goodKb();
  validateKb(input);
  assert.equal(Object.isFrozen(input), false);
});

test("a wrong schema_version fails with a message that names it", () => {
  const kb = goodKb();
  kb.schema_version = 1;
  assert.match(problemsOf(kb).join("\n"), /schema_version/);
});

test("every problem is listed, not only the first", () => {
  const kb = goodKb();
  delete kb.loci.rs1.interpretations["2"];
  kb.loci.rs1.gene = "NOPE";
  delete kb.loci.rs1.limitation;
  const text = problemsOf(kb).join("\n");
  assert.match(text, /interpretations\.2/);
  assert.match(text, /unknown gene "NOPE"/);
  assert.match(text, /limitation/);
});

test("a clinical field is never defaulted: a missing interpretation field is an error", () => {
  const kb = goodKb();
  delete kb.loci.rs1.interpretations["1"].phenotype;
  assert.match(problemsOf(kb).join("\n"), /interpretations\.1\.phenotype/);
});

test("a non-ClinVar tier needs a rationale and a citation", () => {
  const kb = goodKb();
  kb.loci.rs1.tier_source = "curated";
  const text = problemsOf(kb).join("\n");
  assert.match(text, /tier_rationale/);
  assert.match(text, /tier_citation/);
});

test("enum fields are checked", () => {
  const kb = goodKb();
  kb.loci.rs1.evidence_tier = "Tier Z";
  kb.loci.rs1.role = "boss";
  kb.loci.rs1.evidence_sufficiency = "maybe";
  const text = problemsOf(kb).join("\n");
  assert.match(text, /evidence_tier/);
  assert.match(text, /role/);
  assert.match(text, /evidence_sufficiency/);
});

test("allele_codes must map D and I to ref or alt", () => {
  const kb = goodKb();
  kb.loci.rs1.allele_codes = { D: "alt", I: "middle" };
  assert.match(problemsOf(kb).join("\n"), /allele_codes/);
});

test("two loci on the same chrom:pos for one build are rejected", () => {
  const kb = goodKb();
  kb.loci.rs2 = { ...kb.loci.rs1, rsid: "rs2" };
  assert.match(problemsOf(kb).join("\n"), /duplicate position/);
});

test("a locus whose key differs from its rsid is rejected", () => {
  const kb = goodKb();
  kb.loci.rs9 = kb.loci.rs1;
  delete kb.loci.rs1;
  assert.match(problemsOf(kb).join("\n"), /rsid/);
});

test("a per-sample field must not appear in the knowledge base", () => {
  const kb = goodKb();
  kb.loci.rs1.coverage_state = "supported_and_observed";
  assert.match(problemsOf(kb).join("\n"), /coverage_state/);
});

test("APOE diplotypes, when present, need all six keys", () => {
  const kb = goodKb();
  kb.genes.HFE.diplotypes = { "e3/e3": interp("Not detected", 0) };
  assert.match(problemsOf(kb).join("\n"), /diplotypes/);
});

test("non-object input is a KbSchemaError, not a TypeError", () => {
  assert.throws(() => validateKb(null), KbSchemaError);
  assert.throws(() => validateKb("x"), KbSchemaError);
});
