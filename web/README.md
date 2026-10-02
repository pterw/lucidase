# GenomePulse — Zero-Knowledge Clinical Variome Explorer

A modern, privacy-first consumer genomics analysis platform supporting **23andMe**, **AncestryDNA**, **MyHeritage**, and **VCF 4.2** raw genotyping files.

---

## 🛡️ Privacy Architecture

**Raw DNA data never leaves your device.**

| Stage | Where it runs | What is transmitted |
|:---|:---|:---|
| File parsing (23andMe / VCF) | Browser Web Worker | Nothing |
| Variant classification & segregation | Browser (JS knowledge base) | Nothing |
| Compound heterozygote detection | Browser | Nothing |
| Redis enrichment (optional) | Vercel `/api/enrich` serverless | **rsID identifiers only** (~150–500 variant IDs, ~2 KB) |

The `/api/enrich` endpoint receives only rsID identifiers — not genotypes, not personal data. It returns cached clinical annotations from the embedded knowledge base or Upstash Redis.

> **Note on enrichment data:** When Upstash Redis is not configured or a variant is not yet cached, the endpoint returns an **offline embedded knowledge-base stub** labelled `evidence_tier: embedded_kb_fallback`. This is not a live query to ClinVar, Ensembl, or AlphaFold. Verified live-source data requires wiring a live enrichment step into the cache-miss path of `api/enrich.js`.

---

## 🧬 Genomic Pipeline

```
User uploads 23andMe / VCF file
       │
       ▼
 [Web Worker — browser only]
 ├─ File format detection (23andMe v3-v5, AncestryDNA, MyHeritage, VCF 4.2)
 ├─ SNP line parsing (~700K–1M variants)
 ├─ Genotype normalization (strand flip, GT parsing)
 └─ Variant classification against embedded knowledge base
       │
       ▼
 [Main Thread — browser only]
 ├─ APOE ε diplotype synthesis (rs429358 × rs7412)
 ├─ Compound heterozygote detection (HFE C282Y/H63D, CFTR multi-locus)
 ├─ Mendelian segregation reports (Hardy-Weinberg, carrier prior, offspring risk)
 ├─ Independent assortment multi-locus joint probability (Mendel's 2nd Law)
 └─ Pedigree partner scenario simulation
       │
       ▼ (optional, rsIDs only)
 [Vercel /api/enrich — serverless]
 ├─ Upstash Redis MGET (~3 ms cache hit)
 └─ Embedded KB fallback stub (evidence_tier: embedded_kb_fallback)
       │
       ▼
 UI: variant table, drawer inspection, biotools panel, export (Markdown / CSV)
```

---

## 🔒 Security Headers (Vercel)

All responses include:

| Header | Value |
|:---|:---|
| `Content-Security-Policy` | Scripts: self + Tailwind CDN; Fonts: Typekit; No frames |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Camera, microphone, geolocation all denied |

CORS on `/api/enrich` defaults to **same-origin** (no wildcard). Set `ALLOWED_ORIGIN` in Vercel env vars if your frontend is on a custom domain.

---

## 🚀 Deployment Options

### 1. Vercel (Recommended)

1. Push repository to GitHub.
2. Import into [Vercel](https://vercel.com), set **Root Directory** to `web/`.
3. *(Optional)* Add Upstash Redis env vars in Project Settings → Environment Variables:
   - `UPSTASH_REDIS_REST_URL` — `https://...upstash.io`
   - `UPSTASH_REDIS_REST_TOKEN` — `A...`
   - `ALLOWED_ORIGIN` — your custom domain (e.g. `https://genomepulse.example.com`) if not on `.vercel.app`
4. Click **Deploy**.

### 2. Docker & Docker Compose

```bash
docker compose up -d   # Web: http://localhost:8080  Redis: localhost:6379
docker compose down
```

### 3. Local Development

```bash
cd web
python -m http.server 8000
# Open http://localhost:8000
```

---

## 📊 File Format Support

| Format | Auto-Detection | Allele Merging | Genome Builds |
|:---|:---|:---|:---|
| **23andMe** (v3, v4, v5) | `# rsid chromosome position genotype` | Native | GRCh37, GRCh38 |
| **AncestryDNA** | `# rsid chromosome position allele1 allele2` | Automatic | GRCh37 |
| **MyHeritage** | `"RSID","CHROMOSOME","POSITION","RESULT"` | CSV unquoting | GRCh37 |
| **VCF 4.2** | `##fileformat=VCFv4.2` | GT parsing (`0/1`, `1/1`) | GRCh37, GRCh38 |

---

## 🎨 Developer Tooling: Font Kit Studio

Font Kit Studio is isolated as dedicated design tooling in `tools/font-kit-studio/` and is **not bundled** in the production clinical app.

- **Standalone Workbench:** Open `tools/font-kit-studio/font_kit_studio_v0.1.1.html` directly in your browser.
- **External Previewing:** Point Font Kit Studio's Target URL at your running GenomePulse local instance to inspect typography tokens externally.

---

## 📋 Audit

See [`AUDIT_LEDGER.md`](../AUDIT_LEDGER.md) for the full architecture and ground truth audit log, issue register, and remediation history.
