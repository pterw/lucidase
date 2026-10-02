# GenomePulse — Zero-Knowledge Variome Explorer

A modern, privacy-first consumer genomics analysis platform designed for **23andMe**, **AncestryDNA**, **MyHeritage**, and **VCF 4.2** raw genotyping files.

---

## 🛡️ Core Architecture

- **Zero-Knowledge Client-Side Processing**: Raw DNA files (15–30 MB, ~700,000 to 1,000,000 SNPs) are streamed and parsed entirely inside the user's browser using a multi-threaded **Web Worker**. The raw genetic sequence never leaves the client device.
- **Embedded Clinical Knowledge Base**: Instant 0ms offline annotation for high-priority loci:
  - **ClinVar 2026.1**: Pathogenicity, review stars (0–4), and conditions.
  - **ACMG Secondary Findings v3.2**: 81 actionable genes (*BRCA1/2*, *HFE*, *LDLR*, *TP53*, etc.).
  - **Human Protein Atlas (HPA)**: Normal human tissue protein abundance and subcellular localization.
  - **CPIC Pharmacogenomics (PGx)**: Drug metabolism alerts for Clopidogrel (*CYP2C19*), Warfarin (*VKORC1*), Statins (*SLCO1B1*), and 5-FU (*DPYD*).
  - **gnomAD**: Continental allele frequencies and gene constraint pLI scores.
- **Redis Edge Caching**:
  - The browser extracts only the flagged/relevant rsIDs (~150–500 variants, ~2 KB payload) and queries `/api/enrich`.
  - Redis returns cached clinical data in **~3 milliseconds**.
  - Cache misses query upstream APIs and write to Redis with a 30-day TTL (`SETEX`).

---

## 🚀 Deployment Options

### 1. Vercel Deployment (Recommended)

1. Push your repository to GitHub.
2. Import the project into [Vercel](https://vercel.com).
3. Set the Root Directory to `web` (or leave default).
4. (Optional) In the Vercel Project Settings, add your Upstash Redis credentials:
   - `UPSTASH_REDIS_REST_URL`: `https://...upstash.io`
   - `UPSTASH_REDIS_REST_TOKEN`: `A...`
5. Click **Deploy**. Your app is globally distributed at zero cost.

---

### 2. Docker & Docker Compose

Run the web application together with a persistent Redis container with one command:

```bash
docker compose up -d
```

- Web App: `http://localhost:8080`
- Redis Cache: `localhost:6379`

To stop:
```bash
docker compose down
```

---

### 3. Local Development (Instant Browser Preview)

You can launch a local HTTP server with Python:

```bash
cd web
python -m http.server 8000
```

Open `http://localhost:8000` in any browser.

---

## 📊 File Format Support

| Format | Auto-Detection | Allele Merging | Genome Builds |
| :--- | :--- | :--- | :--- |
| **23andMe** (v3, v4, v5) | `# rsid chromosome position genotype` | Native | GRCh37, GRCh38 |
| **AncestryDNA** | `# rsid chromosome position allele1 allele2` | Automatic | GRCh37 |
| **MyHeritage** | `"RSID","CHROMOSOME","POSITION","RESULT"` | CSV unquoting | GRCh37 |
| **VCF 4.2** | `##fileformat=VCFv4.2` | GT parsing (`0/1`, `1/1`) | GRCh37, GRCh38 |

---

## 🎨 Developer Tooling: Font Kit Studio

Font Kit Studio is maintained as dedicated developer and design tooling located in `tools/font-kit-studio/`:
- **Standalone Workbench**: Open `tools/font-kit-studio/font_kit_studio_v0.1.1.html` directly in your browser.
- **External Previewing**: Enter GenomePulse's local URL (e.g. `http://localhost:8788`) into Font Kit Studio's Target URL input to inspect typography, design tokens, and breakpoints externally without embedding developer tooling in the clinical app bundle.
- **Production Cleanliness**: Zero developer iframe modals or bridge overhead inside the core clinical application.

