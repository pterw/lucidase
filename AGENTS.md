# AGENTS.md: engineering rules for this repository

These rules apply to every human and AI contributor. Where a rule and a
convenience conflict, the rule wins. If a rule blocks you, stop and ask.
Do not route around it.

## 1. What lives here

| Area | Path | Ships to users? | Role |
|---|---|---|---|
| GenomePulse web app | `web/` | **Yes** (Vercel static + `api/manifest.js`) | Parses raw DNA files and classifies them **in the browser**. |
| Knowledge-base build | `tools/` | No (build time) | Builds the one curated knowledge base, `web/src/knowledge-base.json`. |
| Desktop genomics | `genomic_parser.py`, `variant_annotator.py`, `segregation_engine.py`, `biotools_orchestrator.py`, `gui.py` | No (local tool) | Reference implementation of the same rules, which must match the web app. |
| de Bruijn explorer | `graph_core.py`, `assembly.py`, `bio_engine.py`, `ml_engine.py`, `debruijn_explorer.py` | No (local tool) | Standalone assembly and graph teaching tool. |
| Design tooling | `tools/font-kit-studio/`, `chrome-extension/` | No | Typography tooling. Never imported by the app. |

## 2. Architecture and boundaries

**Single source of truth.** All curated genomic knowledge (loci, alleles,
genotype interpretations, evidence, inheritance, gene insights) lives in
`web/src/knowledge-base.json`. Only `tools/build_canonical_kb.py` writes
it, and nobody edits it by hand. The build's hand-edited input is
`tools/curation/kb_curation.json`: change curated knowledge there, then
rebuild. The web app and the desktop tools both *load* the KB. No second
copy of the data may exist in JS or Python source.

**Web layers** (dependencies point downward only):

```
web/src/app.js, index.html     UI: renders view models, owns DOM, no genetics
web/src/worker.js              adapter: message in -> core -> message out
web/src/core/*.js              pure domain: parse, alleles, classify, apoe,
                               inheritance, qc. No DOM, no worker globals,
                               no fetch. Unit-tested in Node.
web/src/knowledge-base.json    data, validated against a schema on load
```

**Knowledge vs. sample (separation of concerns).** The KB describes loci and
what each *alt-allele count* means. Whatever depends on one person's sample
(observed genotype, coverage state, sample observation) is computed at
analysis time and never stored in the KB.

**Anti-Corruption Layer.** Only `tools/source_adapters.py` knows the shape
of upstream payloads (ClinVar, dbSNP, Ensembl VEP, gnomAD). It translates them
into our own models (`tools/variome_models.py`).
Nothing downstream reads a raw upstream field name. The adapters are tested
against **real captured payloads** pinned in `tools/fixtures/upstream/`,
each with retrieval URL and date. Never test them against fixtures written to
match the code.

## 3. Principles, made concrete

- **SRP**: one reason to change per module. A parser parses, a classifier
  classifies, the UI renders. If a function needs "and" to describe it,
  split it.
- **SoC**: domain logic never touches the DOM, the network or the
  filesystem. I/O happens at the edges (worker adapter, CLI `main`, GUI).
- **KISS / YAGNI**: build the simplest thing that is correct for the
  requirements we have. Don't add speculative options, plugin systems or
  unused exports.
- **DRY at the knowledge level**: one KB, one classification rule set, and
  one serializer behind every view or export of a record. The desktop and web
  engines share a spec (the test vectors in `tests/vectors/`), not code.
- **Fail fast, fail visibly**:
  - An unknown file format, a KB schema mismatch or an impossible genotype
    raises an explicit error at the boundary where it is detected.
  - The UI shows worker and KB errors to the user. Never swallow them into
    `console.error` with the UI left hanging.
  - KB validation runs at build time and again at load time.
  - No silent defaults for clinical fields (`|| "Tier B"`, `|| 0.0`,
    `|| "MANE Select"`). Missing data is shown as "not available", never
    as a value.
- **Fail closed on genetics**: if a genotype cannot be resolved
  unambiguously against the locus's ref/alt alleles (palindromic A/T or C/G
  sites, alleles outside ref/alt, no-calls, phase ambiguity), the result is
  *not interpretable*, never a match and never "wild-type".

## 4. Clinical honesty invariants (non-negotiable)

1. **Absence of a finding is never reported as absence of risk.** Wording
   is "not detected among the N variants tested", never "normal".
2. A genotype is "variant present" if and only if its alt-allele count is
   greater than 0. Interpretation category or magnitude never decides this.
3. Strand handling: alleles are compared with plus-strand ref/alt.
   Complementing is allowed only at non-palindromic sites, and only when the
   complemented alleles fall inside {ref, alt}.
4. Offspring and recurrence figures come from the patient's actual
   genotype and a stated partner model. They are shown only for loci whose
   KB entry is a Mendelian disease locus. Risk-factor, trait and
   pharmacogenomic loci get allele-transmission figures, not disease risk.
5. Provenance is never fabricated:
   - No invented accession versions and no "retrieved" timestamps for data
     that was not retrieved.
   - Hand-entered values are labelled `manually_curated`. QC output reports
     the real error count, and the build exits non-zero when it fails.
6. Single-variant tests of multi-variant genes (DPYD, CFTR, CYP2C19 star
   alleles, ACMG SF loci) carry their limitation on the row, in the drawer
   and in every export.

## 5. Privacy invariants

- Raw genotype data and rsIDs derived from a user's file never leave the
  browser. `connect-src 'self'` stays in the CSP. The only network calls
  allowed are same-origin static assets.
- No third-party script runs in the page. Styles are vendored, compiled CSS.

## 6. Testing rules

- **Every bug fix starts with a regression test that fails on the pre-fix
  code** for the reported symptom, and passes after the fix. Record the
  RED and GREEN output in the task report.
- Web domain logic: `node --test` over `web/tests/**/*.test.mjs`, using only
  built-in Node modules.
- Browser behaviour: Playwright tests under `tests/e2e/`. They serve `web/`
  themselves on an ephemeral port and fail on any page error or worker error.
- **Shared vectors**: `tests/vectors/*.json` hold input → expected output
  cases. The Node and pytest suites both run them, and a behaviour change
  starts with a vector change.
- Tests are deterministic and offline: no network, no wall clock, no
  randomness without a fixed seed.
- A file named `test_*.py` must contain collected tests. Script-style
  "tests" are not allowed.

## 7. Gates (run before every commit)

```
python -m pytest tests -q -p no:cacheprovider --ignore=tests/e2e
node --test "web/tests/**/*.test.mjs"
python -m pytest tests/e2e -q -p no:cacheprovider
python tools/build_canonical_kb.py --verify-only
```

`--verify-only` rebuilds the KB in memory and fails if the result differs
from the committed `web/src/knowledge-base.json`. That makes the build
deterministic and the committed file reproducible.

## 8. Change hygiene

- Commit subjects follow the existing convention: `type(scope): summary`
  (`fix(web)`, `feat(pipeline)`, `docs(audit)`, `test(e2e)`).
- Each remediated finding gets a row in `AUDIT_LEDGER.md` (next free
  `P0-/P1-/P2-` id) and a line in its Remediation Log.
- Stage files by name. Never commit caches, `canonical_variome.db`,
  screenshots or downloaded binaries (`bin/` is git-ignored).
- Python ≥ 3.11 with type hints. ES modules in the browser (no bundler). No
  new runtime dependency without an owner decision.
