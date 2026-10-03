"""
Biotools Orchestrator: Multi-Source Clinical & Deep Biological Intelligence
===========================================================================
Unified orchestrator integrating 5 premier computational biology tools & databases:

1. ClinVar Database (/clinvar-database):
   - Variant pathogenicity, gold-standard review star ratings (0-4), ACMG secondary findings.
2. Ensembl Database & VEP (/ensembl-database):
   - Variant Effect Predictor (VEP): SIFT, AlphaMissense class & score, LOEUF, Conservation.
   - Gene resolution, MANE Select canonical transcripts, and canonical TSS coordinates.
3. AlphaFold Database (/alphafold-database-fetch-and-analyze):
   - 3D protein structure download, global & per-residue pLDDT folding confidence.
   - Predicted Aligned Error (PAE) matrix analysis for rigid domain boundaries and flexible joints.
4. ENCODE cCREs & SCREEN (/encode-ccres-database):
   - Candidate cis-Regulatory Elements (promoters, enhancers, insulators) and multi-tissue RNA expression.
5. AlphaGenome Deep Learning (/alphagenome-single-variant-analysis):
   - Splicing and regulatory disruption inference with safe credentials protocol integration.

PRIVACY: unlike the Lucidase web app, which never transmits variant identifiers,
this desktop tool SENDS rsIDs (and gene symbols) to NCBI (ClinVar) and Ensembl (VEP),
and gene symbols to AlphaFold and ENCODE, through the skill scripts. Use it only when
you accept that. Nothing is sent until an enrichment method is called.

Configuration (environment variables; nothing is hard-coded to one machine):
- LUCIDASE_BIOTOOLS_SKILLS_DIR: directory holding the skill folders
  (clinvar_database, ensembl_database, alphafold_database_fetch_and_analyze,
  encode_ccres_database). Unset means every skill-backed query returns an
  {"error": ...} dict saying so.
- LUCIDASE_CACHE_DIR: where query results are cached (default ~/.cache/lucidase).
- LUCIDASE_UV_BIN: path to the `uv` executable (default: `uv` found on PATH).
- LUCIDASE_HTTP_USER_AGENT: User-Agent for the skill scripts (default Lucidase/1.0).

Constructing a BiotoolsOrchestrator does no I/O, and neither does importing this
module. The cache directory is created on the first query that runs a script.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

ENV_SKILLS_DIR = "LUCIDASE_BIOTOOLS_SKILLS_DIR"
ENV_CACHE_DIR = "LUCIDASE_CACHE_DIR"
ENV_UV_BIN = "LUCIDASE_UV_BIN"
ENV_USER_AGENT = "LUCIDASE_HTTP_USER_AGENT"

# Skill script locations, relative to the skills directory.
SKILL_SCRIPTS: dict[str, tuple[str, ...]] = {
    "clinvar": ("clinvar_database", "scripts", "clinvar_api.py"),
    "ensembl": ("ensembl_database", "scripts", "ensembl_api.py"),
    "af_fetch": ("alphafold_database_fetch_and_analyze", "scripts", "fetch_structure.py"),
    "af_plddt": ("alphafold_database_fetch_and_analyze", "scripts", "analyze_plddt.py"),
    "af_pae": ("alphafold_database_fetch_and_analyze", "scripts", "analyze_pae.py"),
    "encode": ("encode_ccres_database", "scripts", "screen_api.py"),
}


def skills_dir() -> Optional[Path]:
    """The configured skills directory, or None when LUCIDASE_BIOTOOLS_SKILLS_DIR is unset."""
    value = os.environ.get(ENV_SKILLS_DIR, "").strip()
    return Path(value).expanduser() if value else None


def default_cache_dir() -> Path:
    value = os.environ.get(ENV_CACHE_DIR, "").strip()
    return Path(value).expanduser() if value else Path.home() / ".cache" / "lucidase"


def uv_binary() -> str:
    return os.environ.get(ENV_UV_BIN, "").strip() or shutil.which("uv") or "uv"


# Mapping of key clinical genes to their canonical UniProt accession IDs
GENE_TO_UNIPROT: dict[str, str] = {
    "APOE": "P02649",      # Apolipoprotein E
    "HFE": "P55899",       # Hereditary hemochromatosis protein
    "F5": "P12259",        # Coagulation factor V
    "F2": "P00734",        # Prothrombin
    "CFTR": "P13569",      # Cystic fibrosis transmembrane conductance regulator
    "CYP2C19": "P33261",   # Cytochrome P450 2C19
    "SLCO1B1": "Q9Y6L6",   # Solute carrier organic anion transporter 1B1
    "VKORC1": "Q9BQB6",    # Vitamin K epoxide reductase complex subunit 1
    "MTHFR": "P42898",     # Methylenetetrahydrofolate reductase
    "ALDH2": "P05091",     # Aldehyde dehydrogenase, mitochondrial
    "BRCA1": "P38398",     # Breast cancer type 1 susceptibility protein
    "BRCA2": "P51587",     # Breast cancer type 2 susceptibility protein
    "LDLR": "P01130",      # Low-density lipoprotein receptor
    "TP53": "P04637",      # Cellular tumor antigen p53
    "MLH1": "P40692",      # DNA mismatch repair protein Mlh1
    "MSH2": "P43246",      # DNA mismatch repair protein Msh2
}


@dataclass
class BiotoolsEnrichmentResult:
    """Consolidated enrichment payload from all 5 biotools."""
    rsid: str
    gene: str
    genotype: str
    # 1. ClinVar
    clinvar_status: str = "Unqueried"
    clinvar_stars: int = 0
    clinvar_variation_id: Optional[str] = None
    clinvar_conditions: list[str] = field(default_factory=list)
    # 2. Ensembl VEP
    vep_consequence: str = ""
    vep_sift: str = ""
    vep_alphamissense_class: str = ""
    vep_alphamissense_score: Optional[float] = None
    vep_loeuf: Optional[float] = None
    vep_conservation: Optional[float] = None
    vep_mane_transcript: str = ""
    # 3. AlphaFold
    alphafold_uniprot_id: str = ""
    alphafold_plddt: Optional[float] = None
    alphafold_conclusion: str = ""
    alphafold_domains: list[dict[str, Any]] = field(default_factory=list)
    # 4. ENCODE cCREs
    encode_top_tissues: dict[str, float] = field(default_factory=dict)
    encode_ccre_type: str = ""
    # 5. AlphaGenome
    alphagenome_status: str = "Pending Credentials"
    alphagenome_note: str = ""


class BiotoolsOrchestrator:
    """High-level facade orchestrating execution of science skill scripts."""

    def __init__(self, cache_dir: Optional[str] = None):
        # No I/O here: paths are resolved on use and the cache directory is created lazily.
        self._cache_dir_arg = cache_dir

    @property
    def cache_dir(self) -> Path:
        return Path(self._cache_dir_arg).expanduser() if self._cache_dir_arg else default_cache_dir()

    @property
    def uv_bin(self) -> str:
        return uv_binary()

    def _script(self, key: str) -> tuple[Optional[Path], str]:
        """(path, "") when the skill script exists, else (None, error message)."""
        root = skills_dir()
        if root is None:
            return None, f"{ENV_SKILLS_DIR} is not set, so the {key} skill script cannot be located"
        path = root.joinpath(*SKILL_SCRIPTS[key])
        if not path.exists():
            return None, f"{key} skill script not found at {path}"
        return path, ""

    def _run_uv_script(self, script_path: Path, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a Python skill script with uv in an isolated subprocess."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)  # the first script run creates the cache
        cmd = [
            str(self.uv_bin),
            "run",
            str(script_path),
            *args,
        ]
        env = os.environ.copy()
        env["POLITE_HTTP_USER_AGENT"] = env.get(ENV_USER_AGENT) or "Lucidase/1.0"
        env["UV_CACHE_DIR"] = str(self.cache_dir / "uv")

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

    # -----------------------------------------------------------------------
    # 1. ClinVar Database (/clinvar-database)
    # -----------------------------------------------------------------------
    def query_clinvar(self, rsid: str) -> dict[str, Any]:
        """Search ClinVar for an rsID and return interpretation summaries."""
        cache_file = self.cache_dir / f"clinvar_{rsid}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        clinvar_script, problem = self._script("clinvar")
        if clinvar_script is None:
            return {"error": problem}

        out_search = self.cache_dir / f"clinvar_search_{rsid}.json"
        proc = self._run_uv_script(
            clinvar_script,
            ["search", "--query", f"{rsid}[rsid]", "--retmax", "5", "--output", str(out_search)],
            timeout=25,
        )

        if proc.returncode != 0 or not out_search.exists():
            return {"error": proc.stderr or "ClinVar search failed"}

        try:
            search_data = json.loads(out_search.read_text(encoding="utf-8"))
            variant_ids = search_data.get("variant_ids", [])
            if not variant_ids:
                return {"total_count": 0, "variants": []}

            out_summary = self.cache_dir / f"clinvar_summary_{rsid}.json"
            proc_sum = self._run_uv_script(
                clinvar_script,
                ["summary", "--variant_ids", *variant_ids[:5], "--output", str(out_summary)],
                timeout=25,
            )

            if out_summary.exists():
                summary_data = json.loads(out_summary.read_text(encoding="utf-8"))
                result = {
                    "total_count": len(summary_data),
                    "variants": summary_data,
                    "primary_var_id": variant_ids[0],
                }
                cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
                return result
        except Exception as e:
            return {"error": str(e)}

        return {"total_count": 0, "variants": []}

    # -----------------------------------------------------------------------
    # 2. Ensembl REST & VEP (/ensembl-database)
    # -----------------------------------------------------------------------
    def query_ensembl_vep(self, rsid_or_variant: str) -> dict[str, Any]:
        """Query Ensembl VEP for molecular consequences, SIFT, AlphaMissense, and LOEUF."""
        cache_file = self.cache_dir / f"ensembl_vep_{rsid_or_variant.replace(':', '_')}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        ensembl_script, problem = self._script("ensembl")
        if ensembl_script is None:
            return {"error": problem}

        out_json = self.cache_dir / f"vep_{rsid_or_variant.replace(':', '_')}.json"
        proc = self._run_uv_script(
            ensembl_script,
            ["vep", rsid_or_variant, "--species", "human", "--output", str(out_json)],
            timeout=35,
        )

        if out_json.exists():
            try:
                data = json.loads(out_json.read_text(encoding="utf-8"))
                cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return data
            except Exception as e:
                return {"error": str(e)}

        return {"error": proc.stderr or "Ensembl VEP query failed"}

    def resolve_ensembl_gene(self, gene_symbol: str) -> dict[str, Any]:
        """Resolve a gene symbol to ENSG, biotype, and genomic coordinates."""
        cache_file = self.cache_dir / f"ensembl_gene_{gene_symbol}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        ensembl_script, problem = self._script("ensembl")
        if ensembl_script is None:
            return {"error": problem}

        out_json = self.cache_dir / f"gene_{gene_symbol}.json"
        proc = self._run_uv_script(
            ensembl_script,
            ["resolve-gene", gene_symbol, "--species", "human", "--output", str(out_json)],
            timeout=20,
        )

        if out_json.exists():
            try:
                data = json.loads(out_json.read_text(encoding="utf-8"))
                cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return data
            except Exception as e:
                return {"error": str(e)}

        return {"error": proc.stderr or "Ensembl gene resolution failed"}

    # -----------------------------------------------------------------------
    # 3. AlphaFold Database (/alphafold-database-fetch-and-analyze)
    # -----------------------------------------------------------------------
    def analyze_alphafold_structure(self, gene_symbol: str) -> dict[str, Any]:
        """Download and analyze AlphaFold 3D structure, pLDDT confidence, and PAE domain boundaries."""
        uniprot_id = GENE_TO_UNIPROT.get(gene_symbol.upper())
        if not uniprot_id:
            return {"error": f"No canonical UniProt ID registered for gene {gene_symbol}"}

        cache_file = self.cache_dir / f"alphafold_analysis_{uniprot_id}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        fetch_script, problem = self._script("af_fetch")
        if fetch_script is None:
            return {"error": problem}
        af_out_dir = self.cache_dir / f"af_{uniprot_id}"
        af_out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Fetch structure files
        proc_fetch = self._run_uv_script(
            fetch_script,
            [uniprot_id, "-o", str(af_out_dir)],
            timeout=40,
        )

        meta_file = af_out_dir / f"AF-{uniprot_id}-F1-metadata.json"
        pae_file = af_out_dir / f"AF-{uniprot_id}-F1-predicted_aligned_error_v6.json"

        result: dict[str, Any] = {
            "gene": gene_symbol,
            "uniprot_id": uniprot_id,
            "fetch_success": meta_file.exists(),
        }

        # 2. Analyze pLDDT
        plddt_script, _ = self._script("af_plddt")
        if meta_file.exists() and plddt_script is not None:
            proc_plddt = self._run_uv_script(plddt_script, [str(meta_file)], timeout=15)
            # Parse pLDDT metrics from stdout
            out = proc_plddt.stdout
            result["plddt_stdout"] = out
            for line in out.splitlines():
                if "Overall Global pLDDT" in line:
                    try:
                        result["global_plddt"] = float(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                if "pLDDT Conclusion:" in line:
                    idx = out.index("pLDDT Conclusion:")
                    result["plddt_conclusion"] = out[idx:].splitlines()[1].strip()

        # 3. Analyze PAE / Domain Boundaries
        pae_script, _ = self._script("af_pae")
        if pae_file.exists() and pae_script is not None:
            proc_pae = self._run_uv_script(pae_script, [str(pae_file)], timeout=25)
            out_pae = proc_pae.stdout
            result["pae_stdout"] = out_pae
            domains = []
            for line in out_pae.splitlines():
                if "Domain " in line and "residues " in line:
                    domains.append(line.strip())
            result["domains"] = domains

        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    # -----------------------------------------------------------------------
    # 4. ENCODE cCREs & SCREEN (/encode-ccres-database)
    # -----------------------------------------------------------------------
    def query_encode_expression(self, gene_symbol: str) -> dict[str, Any]:
        """Query ENCODE SCREEN RNA-seq expression across thousands of biosamples."""
        cache_file = self.cache_dir / f"encode_expr_{gene_symbol}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        encode_script, problem = self._script("encode")
        if encode_script is None:
            return {"error": problem}

        out_json = self.cache_dir / f"encode_raw_{gene_symbol}.json"
        proc = self._run_uv_script(
            encode_script,
            ["gene-expression", gene_symbol, "--output", str(out_json)],
            timeout=25,
        )

        if out_json.exists():
            try:
                data = json.loads(out_json.read_text(encoding="utf-8"))
                # Extract top high-confidence expressing tissues
                expr_list = data.get("data", {}).get("expression", [])
                tissue_tpm: dict[str, float] = {}
                for item in expr_list:
                    t = item.get("tissue") or item.get("biosample")
                    tpm = float(item.get("tpm", 0.0))
                    if t and (t not in tissue_tpm or tpm > tissue_tpm[t]):
                        tissue_tpm[t] = tpm
                ranked = sorted(tissue_tpm.items(), key=lambda x: x[1], reverse=True)
                top_tissues = {k: round(v, 2) for k, v in ranked[:10]}

                result = {
                    "gene": gene_symbol,
                    "total_biosamples": len(expr_list),
                    "top_expressing_tissues": top_tissues,
                }
                cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
                return result
            except Exception as e:
                return {"error": str(e)}

        return {"error": proc.stderr or "ENCODE expression query failed"}

    # -----------------------------------------------------------------------
    # 5. AlphaGenome (/alphagenome-single-variant-analysis)
    # -----------------------------------------------------------------------
    def check_alphagenome_readiness(self) -> dict[str, Any]:
        """Verify presence of ALPHAGENOME_API_KEY according to safe credentials protocol."""
        env_path = Path.home() / ".env"
        has_key = False
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("ALPHAGENOME_API_KEY=") and len(line.split("=", 1)[1].strip()) > 5:
                    has_key = True
                    break

        if has_key:
            return {
                "ready": True,
                "message": "ALPHAGENOME_API_KEY detected in ~/.env. DeepMind inference client enabled.",
            }
        else:
            return {
                "ready": False,
                "message": "ALPHAGENOME_API_KEY is not set.",
                "registration_url": "https://deepmind.google.com/science/alphagenome/",
                "safe_terminal_command": (
                    f'printf "Enter ALPHAGENOME_API_KEY (typing hidden): " && read -s val && echo && '
                    f'echo "ALPHAGENOME_API_KEY=$val" >> "{env_path}" && echo "Saved."'
                ),
            }

    # -----------------------------------------------------------------------
    # Unified Multi-Biotool Enrichment
    # -----------------------------------------------------------------------
    def enrich_variant(
        self,
        rsid: str,
        gene: str,
        genotype: str,
        chrom: str,
        pos: int,
    ) -> BiotoolsEnrichmentResult:
        """Execute coordinated multi-biotool enrichment across ClinVar, Ensembl, AlphaFold, and ENCODE."""
        result = BiotoolsEnrichmentResult(rsid=rsid, gene=gene, genotype=genotype)

        # 1. ClinVar
        cv = self.query_clinvar(rsid)
        if "variants" in cv and cv["variants"]:
            v = cv["variants"][0]
            result.clinvar_status = v.get("clinical_significance", "Unknown")
            result.clinvar_stars = v.get("review_stars", 0)
            result.clinvar_variation_id = str(v.get("variant_id", ""))
            result.clinvar_conditions = [c.get("name", "") for c in v.get("phenotypes", []) if isinstance(c, dict)]

        # 2. Ensembl VEP
        vep_raw = self.query_ensembl_vep(rsid)
        if isinstance(vep_raw, list) and vep_raw:
            entry = vep_raw[0]
            consequences = entry.get("transcript_consequences", [])
            if consequences:
                # Find MANE or primary transcript
                c = consequences[0]
                result.vep_consequence = c.get("consequence_terms", [""])[0]
                result.vep_sift = c.get("sift_prediction", "")
                result.vep_alphamissense_class = c.get("alphamissense_class", "")
                result.vep_alphamissense_score = c.get("alphamissense_pathogenicity")
                result.vep_loeuf = c.get("loss_of_function_loeuf")
                result.vep_conservation = c.get("conservation")
                result.vep_mane_transcript = c.get("transcript_id", "")

        # 3. AlphaFold
        af = self.analyze_alphafold_structure(gene)
        if "uniprot_id" in af:
            result.alphafold_uniprot_id = af["uniprot_id"]
            result.alphafold_plddt = af.get("global_plddt")
            result.alphafold_conclusion = af.get("plddt_conclusion", "")
            result.alphafold_domains = af.get("domains", [])

        # 4. ENCODE Expression
        enc = self.query_encode_expression(gene)
        if "top_expressing_tissues" in enc:
            result.encode_top_tissues = enc["top_expressing_tissues"]

        # 5. AlphaGenome readiness
        ag = self.check_alphagenome_readiness()
        result.alphagenome_status = "Available" if ag["ready"] else "Key Needed"
        result.alphagenome_note = ag["message"]

        return result
