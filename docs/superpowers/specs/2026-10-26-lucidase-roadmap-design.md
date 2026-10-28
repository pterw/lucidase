# Lucidase roadmap design: a free, honest, lightweight alternative to Promethease

Date: 2026-10-26. Status: planning note agreed with the owner, untracked until the owner commits it. Starting point:
`main` at 1ed4273 (PRs #1 to #10 merged; 14 curated loci in 12 genes; zero-upload analysis in the browser).

## 1. Purpose

Promethease runs a raw-data file against roughly a hundred thousand SNPedia entries on its server for a one-off fee.
Its weaknesses are the noise that comes with that breadth (thousands of low-evidence rows, crude good/bad labels), an
upload requirement and a dated interface. Lucidase competes by being free, private and clear, and grows breadth later
without importing the noise.

Owner ordering: near term, trust and clarity (axis 2) plus privacy and ownership (axis 3); medium term, research and
learning tools (axis 4); long term, breadth (axis 1).

## 2. The two bars for the near-term phase

1. **Parity on the owner's own reports.** Every high-magnitude finding that Promethease or Genecept flagged on the
   owner's 23andMe file and that sits on the chip is either reported by Lucidase with a better explanation, or listed
   explicitly as outside coverage with the reason. (The owner's personal files are never committed, read by tests or
   copied anywhere; the comparison is run by the owner locally.)
2. **The reader test.** Someone with no genetics background reads each result row and can say what it means and what
   to do next, without needing the glossary twice for one row.

## 3. Phases

### Phase A (near term): trust, clarity, privacy

Scope, in build order:
1. **Knowledge-base record schema with evidence and provenance.** Each locus carries: evidence grade, source and its
   version (ClinVar review status and stars, CPIC level, ACMG SF list version), population or ancestry caveat, a
   "what to do with this" line (confirmatory test, genetic counsellor, nothing), and provenance (which pinned
   payload, fetched when). The schema is designed for the Phase C import pipeline so breadth later fills the same
   fields instead of forcing a rewrite. Guarded by `validate_kb` on both the web loader and the desktop annotator.
2. **Build-time enrichment step** (`tools/`): the existing `biotools_orchestrator.py` sources (ClinVar, dbSNP,
   Ensembl, Human Protein Atlas) fill those fields for the 14 loci into `tools/curation/kb_curation.json` and the
   pinned fixtures under `tools/fixtures/upstream/real/`, offline-reproducible through `build_canonical_kb.py`.
   Network access only in this step, with owner approval per run; never from the web app.
3. **AlphaGenome context.** Precompute predicted molecular effects (splicing, expression) for the curated loci at
   build time with the owner's key, ship them in the KB payload, show them inside the Inspector's gene and protein
   disclosure labelled as a research prediction. Never changes a result word. Blocked until the owner confirms the
   model's terms allow redistributing its outputs in a public app.
4. **UI reading the new fields**: evidence grade and source version on the row's details, the "what to do" line,
   the ancestry caveat; sentence case, no new colours or components outside the design system.
5. **Privacy and ownership features**: an installable PWA (service worker, manifest), a visible "works with the
   network off" proof in the privacy section, and "re-run against the new knowledge base" when the manifest's
   release changes (the file never left the browser, so re-analysis is a local action). Local notes per result are
   optional and only if cheap.
6. **Small UI fixes** folded in as atomic patches: the logo karyogram's visibility, and the items on the owner's
   list as they are named.

Acceptance: the two bars above, run by the owner; every gate green; the reader test done by one person who is not
the owner.

### Phase B (medium term): research and learning tools

A "Learn" page with a JavaScript port of the de Bruijn core (k-mer collection, graph build, Eulerian trail, contig
extraction, assembly metrics) from `graph_core.py` and `assembly.py`, held in parity with the Python through shared
test vectors, the same pattern the app uses for the analysis rules. The Biopython and scikit-learn parts (`bio_engine`,
`ml_engine`) stay desktop only. The page is its own route and shares the design system, so the results flow stays
simple.

### Phase C (long term): breadth without the noise

A tiered knowledge base built by the Phase A pipeline:
- Tier 1, curated: ACMG secondary-findings genes and CPIC pharmacogenes, each with a human review.
- Tier 2, imported: ClinVar pathogenic or likely-pathogenic entries with two-star review or better that fall on
  common array sites.
- Tier 3, shown only with effect sizes or not at all: GWAS trait associations.

The realistic target is a few thousand interpreted sites, not SNPedia's hundred thousand. The Gemini life-science
skills act as a curation assistant that proposes candidates and citations; the pinned fixtures, the KB verify gate and
a review decide what lands. The assistant never writes the KB directly. The exact tier rules are an owner decision
still open (section 6).

## 4. Rules that hold in every phase

- Zero upload: API keys and enrichment calls exist only in the build pipeline; the web app keeps
  `connect-src 'self'` and works offline.
- Clinical honesty: anything model-predicted is context with its own label and never changes Found or Not found;
  absence wording and coverage states stay as `AGENTS.md` defines them.
- One source of genomic knowledge: `web/src/knowledge-base.json`, built from the curation file and pinned payloads;
  never hand-edited.
- The desktop stack stays the reference, held in parity by shared vectors.

## 5. Hosting and offline

A static host (GitHub Pages or Cloudflare Pages) suits a zero-knowledge app and provides the HTTPS a PWA needs. The
one external request is Adobe Fonts; the kit licence most likely forbids self-hosting, so the service worker caches
the Typekit response and the fallback font stack covers a cold offline start. Hosting choice is an owner decision.

## 6. Owner decisions still open

- Hosting provider and the Vercel project name (already pending in CLAUDE.md).
- AlphaGenome terms: may its predictions be redistributed in a public app?
- Phase C tier rules and the breadth target.
- Whether local per-result notes are worth building.
- The decisions recorded as reversible in the PR #7 ledger (Position row, "KB release" text, disclosure persistence,
  the recessive row label rule, the pre-commit conftest selection).

## 7. Non-goals

Matching Promethease's row count; interpreting markers outside the curated and imported tiers; accounts, payments
or any server-side processing of genotype data; running enrichment or model calls from the browser.

## 8. Testing

Each phase keeps the existing gates (pytest, node, e2e, kb-verify, css-fresh, pre-commit). New behaviour gets one
test per intended behaviour: the schema validator rejects a locus missing an evidence grade; the UI shows the grade
and source version from the KB (non-live numbers in tests); the PWA serves the app with the network stubbed off; the
Learn page's port matches the Python vectors. No test pins wording or pixel fit measured with fallback fonts.
