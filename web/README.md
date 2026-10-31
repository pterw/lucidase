# Lucidase web app

See the [root README](../README.md) for an overview of Lucidase.

A privacy-first consumer genomics analysis page supporting **23andMe**, **AncestryDNA**, **MyHeritage**, and **VCF 4.2** raw genotyping files. It interprets 55 curated loci in 34 genes, in the browser, and nothing else.

---

## Privacy architecture

**Raw DNA data never leaves your device.**

| Stage | Where it runs | What is transmitted |
|:---|:---|:---|
| File parsing (23andMe / AncestryDNA / MyHeritage / VCF) | Browser Web Worker | Nothing |
| Variant classification | Browser Web Worker, against the bundled knowledge base | Nothing |
| APOE diplotype, inheritance and multi-locus figures | Browser | Nothing |
| Exports (Markdown / CSV) | Browser (a downloaded Blob) | Nothing |

There is no enrichment endpoint, no cache and no Redis. The page makes no network request that carries variant data: the CSP is `connect-src 'self'`, and there are two same-origin GETs, each of a bundled static demo file that carries no user data: the main page's `demo-data/sample-23andme.txt` and the karyogram page's `demo-data/sample-karyogram-23andme.txt`.

The one server function is `GET /api/manifest` (`web/api/manifest.js`, Vercel only). It accepts no input and returns a static manifest of the shipped knowledge base: its release, locus count and sha256. Every value is read from `src/knowledge-base.json` at request time, so the manifest cannot drift from the file the app loads. CORS is same-origin; set `ALLOWED_ORIGIN` in Vercel env vars for a custom domain.

---

## Knowledge base and pipeline

All curated genomic knowledge lives in **one file**, `web/src/knowledge-base.json`. The page loads it with a JSON module import and validates it against the schema on load (`src/core/kb.js`). No second copy of the data exists in JS or Python source.

The file is built, never hand-edited, by `tools/build_canonical_kb.py` from:

- `tools/curation/kb_curation.json`, the hand-edited curation input (loci, alleles, genotype interpretations, inheritance models, gene insights, and each gene's `topic`, the plain-language result title from the design system, such as "Clopidogrel (Plavix) response");
- the pinned upstream payloads in `tools/fixtures/upstream/real/` (ClinVar, dbSNP, Ensembl VEP, gnomAD), captured once by `tools/fetch_upstream.py` and read only through `tools/source_adapters.py`.
- the pinned UCSC `chromInfo` and `cytoBand` tables (hg19 and hg38), captured by `tools/fetch_upstream.py --ucsc-only`, which give the reference assembly geometry (`assemblies`: GRCh37 and GRCh38 chromosome lengths and centromeres); each source carries its URL, retrieval date and sha256.

Imported values carry provenance `machine_imported` with the capture's real retrieval date and URL. Hand-entered values are labelled `manually_curated`. The build is deterministic: the same inputs give byte-identical JSON.

```
User opens a file
       │
       ▼
 [Web Worker — browser only]
 ├─ Format and build detection (core/parse.js)
 ├─ Allele resolution against the locus ref/alt, fail closed (core/alleles.js)
 ├─ Classification by alt-allele count, coverage state per locus (core/classify.js)
 ├─ APOE diplotype from rs429358 + rs7412 (core/apoe.js)
 └─ Inheritance, compound heterozygosity, multi-locus (core/inheritance.js)
       │
       ▼
 [Main thread — browser only]
 └─ One view model per record feeds the grouped report, Inspector, table, Markdown and CSV (view-model.js)
```

### Coverage taxonomy

Each curated locus lands in exactly one state per sample:

| State | Meaning |
|:---|:---|
| Supported & observed | The variant allele is present among the variants tested. |
| Supported, not observed | "<allele> not detected (N variant(s) tested in <gene>)". Never worded as "normal" or as absence of risk. |
| Not tested by array | The locus is absent from the file, or the call is a no-call. A variants-only VCF reads "absent from VCF (variants-only VCFs omit reference calls)". |
| Outside coverage | Markers in the file that the knowledge base does not curate. Counted only. |
| Insufficient evidence | A conflicting or weak locus, or a genotype that cannot be resolved against ref/alt. Fail-closed results land here, never as wild-type. |

Absence of a finding is never reported as absence of risk.

---

## Security headers (Vercel and Docker)

`vercel.json` and `Dockerfile` carry the same CSP. A test compares the `vercel.json` policy with both `add_header Content-Security-Policy` values in the `Dockerfile` (the server-level one that serves `index.html` and the asset-location one). It does not check what a deployed host sends:

| Header | Value |
|:---|:---|
| `Content-Security-Policy` | Scripts: self only. Styles: self, inline, Typekit. Fonts: self, Typekit. `connect-src 'self'`. No frames, no objects |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Camera, microphone, geolocation all denied |

Typekit (fonts) is the only external host. daisyUI and the compiled Tailwind CSS are vendored in `src/vendor/`.

---

## Deployment options

### 1. Vercel (Recommended)

1. Push the repository to GitHub.
2. Import into [Vercel](https://vercel.com), set **Root Directory** to `web/`.
3. *(Optional)* Set `ALLOWED_ORIGIN` in Project Settings → Environment Variables to your custom domain.
4. Click **Deploy**. `vercel.json` uses the current form (`functions`, with no `builds` or `routes`, which Vercel cannot combine with `headers`) and bundles `src/knowledge-base.json` with the manifest function. A preview deploy has not been run here: confirm that the response headers and `/api/manifest` work before relying on it.

### 2. Docker & Docker Compose

```bash
docker compose up -d   # Web: http://localhost:8080
docker compose down
```

The container is a static nginx image. `/api/manifest` is a Vercel function and is not served by it.

### 3. Local Development

```bash
cd web
python -m http.server 8000
# Open http://localhost:8000
```

---

## Karyogram page

`karyogram.html` (linked from the header of `index.html`, and back) draws the file's markers on the 24 chromosome columns of the build the file declares (GRCh37 or GRCh38). It reuses the analysis worker through the `"karyogram"` action, which parses, classifies and lays out with `src/core/karyogram.js`; `src/karyogram-view.js` renders the SVG and `src/karyogram-page.js` owns the DOM. Dots are 4 Mb bins; an empty bin is a faint r 0.9 dot, a bin with markers is r 1.6 to 3.2 by the square root of its count, and the busiest bin sets the largest dot. The 55 curated loci carry the coverage state the analysis assigns. When the build is unknown, nothing is placed by position, density is reported as unavailable and the loci still carry their states. Rows that cannot be placed (MT, unplaced names, out-of-range positions) are counted in the totals panel, never dropped. The page makes same-origin requests only. Its geometry comes from the KB `assemblies` section, built by `tools/build_canonical_kb.py` from the pinned UCSC tables. Both pages share the theme logic in `src/theme.js`. `demo-data/sample-karyogram-23andme.txt` is a deterministic synthetic file made by `tools/make_synthetic_karyogram_sample.py`.

---

## Gates, rebuilds

Run these from the repository root before every commit (`AGENTS.md` section 7):

```
python -m pytest tests -q -p no:cacheprovider --ignore=tests/e2e
node --test --test-reporter=spec "web/tests/**/*.test.mjs"
python -m pytest tests/e2e -q -p no:cacheprovider
python tools/build_canonical_kb.py --verify-only
python tools/check_vendored_css.py
```

The end-to-end tests serve `web/` themselves on an ephemeral port with Playwright's bundled Chromium. Tests never use the network.

**Rebuild the knowledge base** after editing `tools/curation/kb_curation.json`:

```
python tools/build_canonical_kb.py                 # validate and write web/src/knowledge-base.json
python tools/build_canonical_kb.py --verify-only   # rebuild in memory; exit 1 on any difference or QC error
```

**Rebuild the vendored CSS** after adding or removing any Tailwind class in `index.html` or `src/**/*.js`. The Tailwind standalone CLI v3.4.17 is not committed; see `src/vendor/README.md` for where to put it:

```
bin/tailwindcss.exe -c web/tailwind.config.js -i web/src/tailwind.input.css -o web/src/vendor/tailwind.css --minify
python tools/check_vendored_css.py
```

---

## File format support

| Format | Auto-Detection | Allele Merging | Genome Builds |
|:---|:---|:---|:---|
| **23andMe** (v3, v4, v5) | `# rsid chromosome position genotype` | Native | Read from the header comment |
| **AncestryDNA** | `# rsid chromosome position allele1 allele2` | Automatic | Read from the header comment |
| **MyHeritage** | `"RSID","CHROMOSOME","POSITION","RESULT"` | CSV unquoting | Read from the header comment |
| **VCF 4.2** | `##fileformat=VCFv4.2` | GT parsing (`0/1`, `1/1`) | Read from `##reference` and `##contig` |

An unrecognised format is rejected with a visible error. The parser never guesses.

---

## Known limitations

These all fail closed, with a visible error or an explicit state:

- A MyHeritage file that lacks its "MyHeritage" comment and has a trailing-comma or extra-column header is rejected.
- A headerless 23andMe file with no header signal is rejected.
- An array file with no build comment reports build "unknown", so matching without rsIDs is unavailable.
- A variant absent from a variants-only VCF is "not tested", not reference.
- Only the 55 curated loci (34 genes) are interpreted.
- Evidence tiers for genes not tiered by ClinVar, and their citations, are manually curated from guideline and paper names: the CPIC levels and the curated tiers for APOE, F5, F2, MTHFR, LCT/MCM6 and ALDH2. They are pending verification against the primary sources.
- Human Protein Atlas tissue and subcellular values are manually curated.
- Multi-locus findings cover only `risk_factor` genes on different chromosomes (F5 and F2 today). This scope was set by the owner and is pinned by test vectors.
- The APOE row is one record built from rs429358 and rs7412. Its internal row id `APOE-STATUS` is never shown as an rsID.

---

---

## Visual design: the Lucidase design system

The pages use the Lucidase design system (owner ruling, 2026-10-03). Its tokens are vendored unchanged in `src/ds/` (see [`src/ds/README.md`](src/ds/README.md)); `src/styles.css` imports them and holds the daisyUI theme bridge and the design system's components as `lds-*` classes; `tailwind.config.js` uses its preset (`src/ds/lucidase.preset.cjs`). The logo and favicon are in `src/brand/`, and the 17 Lucide icons are served from `src/icons/`, same-origin. The theme follows the device setting; a footer link overrides it, and `src/theme-boot.js` applies the override before first paint. [`../docs/design-handoff.md`](../docs/design-handoff.md) records the provisional look this replaced.

---

## Audit

See [`AUDIT_LEDGER.md`](../AUDIT_LEDGER.md) for the full architecture and ground truth audit log, issue register, and remediation history.
