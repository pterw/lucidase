# GenomePulse — Architecture & Ground Truth Audit Ledger

> **Deployment target:** Vercel (static frontend + serverless `/api/enrich`)
> **Privacy model:** Local-First / Client-Side Only — raw genotyping data never leaves the browser
> **Auditor:** Antigravity AI Coding Agent
> **Definition of Done:** All P0 issues remediated; all P1 issues remediated; P2 documented

---

## 2026-10-02 — Initial Comprehensive Audit

### Methodology
Full static read of all production-path files:
- `web/api/enrich.js` (Vercel serverless endpoint)
- `web/src/app.js`, `redis-client.js`, `knowledge-base.js`, `font-studio.js`
- `web/index.html`, `web/vercel.json`
- `segregation_engine.py`, `biotools_orchestrator.py`

---

## Issue Register

### P0 — Critical (Ground Truth Violations)

| ID | File | Lines | Finding | Status |
|---|---|---|---|---|
| P0-001 | `web/api/enrich.js` | 139–213 | `generateFallbackEnrichment()` returns fabricated clinical data on every Redis cache miss: `evidence_tier: Tier 1 Verified` (false); `stars: 4` (false); `review_status: practice guideline` (false); `accession: VCV_rs...` (invalid — VCV accessions are numeric, not rsID-derived); `citation_count: 18` (hardcoded); `recent_pubmed_ids` (may not correspond to actual papers); `acmg_classification_rationale` (generic boilerplate). Header comment also falsely claims misses query live upstream sources. | REMEDIATED |
| P0-002 | `web/api/enrich.js` | 13 | `Access-Control-Allow-Origin: *` wildcard CORS on a clinical endpoint processing derived genomic identifiers. Frontend and /api are co-deployed on the same Vercel domain — CORS is not required; wildcard violates the zero-knowledge privacy posture. | REMEDIATED |
| P0-003 | `web/src/redis-client.js` | 41–55 | Offline mock returns `evidence_tier: Tier 1 Verified` and `cached: true` for locally fabricated data. Misleads the UI into displaying a verified-tier badge for unverified fallback. | REMEDIATED |

---

### P1 — High (Architecture / Privacy Integrity)

| ID | File | Lines | Finding | Status |
|---|---|---|---|---|
| P1-001 | `web/src/app.js` | 10, 29, 38, 45 | FontStudio still imported and instantiated in production clinical bundle despite tooling extraction to `tools/font-kit-studio/`. Adds ~20 KB and exposes design state on `window.__genomePulse`. | REMEDIATED |
| P1-002 | `web/index.html` | 57–59 | `#btn-font-studio` button present in production navbar; `web/src/font-studio.js` remains in the production source path. | REMEDIATED |
| P1-003 | `web/vercel.json` | 24–41 | Missing `Content-Security-Policy` header. Without CSP the app is vulnerable to XSS that could exfiltrate locally-parsed genomic identifiers. | REMEDIATED |
| P1-004 | `segregation_engine.py` | 183–191 | MTHFR `omim: 607093` is the gene entry OMIM, not a disease phenotype OMIM. Common MTHFR variants (C677T, A1298C) are biomarker modifiers; the severe-deficiency phenotype OMIM is 236250. | REMEDIATED |
| P1-005 | `biotools_orchestrator.py` | 31–43, 102, 116 | Hardcoded absolute Windows paths (`C:\Users\peter\...`). Non-portable — Vercel/Linux would not resolve these. Python orchestrator is desktop-only tooling (not Vercel-deployed), so this is a documentation note. | DOCUMENTED — deferred |

---

### P2 — Medium (Hygiene / Technical Debt)

| ID | File | Finding | Status |
|---|---|---|---|
| P2-001 | Root | `test_vep.json` (24 MB) and `test_encode_expr.json` (871 KB) committed. Inflates repo and slows clones. | DOCUMENTED — deferred |
| P2-002 | Root | 15+ development screenshot PNGs in root (230–430 KB each). Should move to `docs/screenshots/` or be gitignored. | DOCUMENTED — deferred |
| P2-003 | `web/src/knowledge-base.js` | Header cites `ClinVar 2026.1` — ClinVar does not publish named versioned releases. Should cite `ClinVar (curated 2026-Q1)` or similar. | DOCUMENTED — deferred |

---

## Remediation Log

### 2026-10-02

| Commit | Scope | Description |
|---|---|---|
| `fix(api): remove fabricated clinical evidence from fallback enrichment` | P0-001, P0-003 | Rewrote `generateFallbackEnrichment()` in `enrich.js` and `redis-client.js` offline mock to use honest labels (`offline_embedded_kb`, `evidence_tier: embedded_kb_fallback`) and removed fake PubMed IDs, ClinVar stars, ACMG boilerplate, invalid VCV accessions. Fixed misleading comment. |
| `fix(api): restrict CORS to same-origin on enrichment endpoint` | P0-002 | Replaced wildcard CORS with same-origin default; `ALLOWED_ORIGIN` env-var override available for custom domain. |
| `fix(web): remove FontStudio from production clinical bundle` | P1-001, P1-002 | Removed import and instantiation from `app.js`; removed `#btn-font-studio` from navbar in `index.html`; deleted `web/src/font-studio.js`. |
| `fix(vercel): add Content-Security-Policy security header` | P1-003 | Added strict CSP allowing only same-origin scripts, Typekit CDN fonts, Tailwind/DaisyUI CDNs. |
| `fix(engine): correct MTHFR OMIM from gene entry to disease phenotype` | P1-004 | Updated `omim` from `607093` (gene) to `236250` (severe deficiency phenotype); amended description. |
| `docs(readme): update pipeline docs and privacy guarantees` | — | Updated `web/README.md` with accurate privacy pipeline, fallback enrichment behavior, CSP notes. |

---

*Ledger maintained in ISO YYYY-MM-DD order. Outstanding items tracked under P2.*
