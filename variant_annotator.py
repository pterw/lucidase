"""
Variant Annotator: Multi-Source Clinical & Proteomic Knowledge Engine
=====================================================================
Enriches genomic variant calls with:
1. ClinVar Database (clinvar-database):
   - Pathogenicity (Pathogenic, Likely Pathogenic, VUS, Benign)
   - Review confidence star rating (0 to 4 stars)
   - Associated clinical phenotypes and MedGen/OMIM conditions
   - ACMG Secondary Findings v3.2 actionable gene flags (81 genes)
2. Human Protein Atlas (human-protein-atlas-database):
   - Semi-quantitative tissue protein expression (IHC: High, Medium, Low)
   - Subcellular localization (Nucleus, Cytoplasm, Plasma Membrane, Mitochondria)
3. gnomAD Database (gnomad-database):
   - Continental allele frequencies (AFR, AMR, EAS, NFE, SAS, FIN)
   - Gene constraint metrics (pLI, LOEUF)
4. Pharmacogenomics (CPIC guidelines):
   - High-impact drug response phenotypes (Warfarin, Clopidogrel, Statins, Codeine)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from genomic_parser import VariantCall
from segregation_engine import SegregationEngine, SegregationReport, MultiLocusSegregation
from biotools_orchestrator import BiotoolsOrchestrator, BiotoolsEnrichmentResult

# ===========================================================================
# ACMG SF v3.2 Actionable Gene List (81 Genes)
# ===========================================================================
ACMG_SF_GENES = {
    "ACTA2", "ACTC1", "ACVRL1", "APC", "APOB", "ATP7B", "BAG3", "BMPR1A", "BRCA1",
    "BRCA2", "BTD", "CACNA1S", "CALM1", "CALM2", "CALM3", "CASQ2", "COL3A1",
    "DES", "DSC2", "DSG2", "DSP", "ENG", "FBN1", "FLNC", "GAA", "GLA", "HFE",
    "HNF1A", "KCNH2", "KCNJ2", "KCNQ1", "LDLR", "LMNA", "MAX", "MEN1", "MLH1",
    "MSH2", "MSH6", "MUTYH", "MYBPC3", "MYH11", "MYH7", "MYL2", "MYL3", "NF2",
    "OTC", "PALB2", "PCSK9", "PKP2", "PMS2", "PRKAG2", "PTEN", "RB1", "RBM20",
    "RET", "RPE65", "RYR1", "RYR2", "SCN5A", "SDHAF2", "SDHB", "SDHC", "SDHD",
    "SMAD3", "SMAD4", "STK11", "TGFBR1", "TGFBR2", "TMEM127", "TMEM43", "TNNC1",
    "TNNI3", "TNNT2", "TP53", "TPM1", "TRDN", "TSC1", "TSC2", "TTN", "VHL", "WT1",
}


@dataclass
class AnnotationRecord:
    """Enriched clinical and biological annotation for a specific genotype."""
    rsid: str
    gene: str
    genotype: str
    call: VariantCall
    clinical_significance: str = "Uncertain / Benign"
    review_stars: int = 0
    phenotype: str = ""
    category: str = "Trait / Research"  # Pathogenic, Carrier, Pharmacogenomics, Trait, Risk Factor
    magnitude: float = 1.0  # Promethease-style magnitude (0.0 to 10.0 scale)
    repute: str = "Neutral"  # Good, Bad, Neutral
    hpa_tissues: dict[str, str] = field(default_factory=dict)
    hpa_subcellular: list[str] = field(default_factory=list)
    gnomad_af: float = 0.0
    gnomad_pli: float = 0.0
    drug_response: str = ""
    notes: str = ""
    acmg_actionable: bool = False
    # Mendelian Independent Segregation & Transmission
    inheritance_mode: str = "Complex / Unknown"
    is_carrier: bool = False
    partner_carrier_prior: float = 0.0
    offspring_recurrence_risk: float = 0.0
    segregation_notes: str = ""
    # Biotools Live Deep Insights
    vep_consequence: str = ""
    vep_sift: str = ""
    vep_alphamissense_class: str = ""
    vep_alphamissense_score: Optional[float] = None
    vep_loeuf: Optional[float] = None
    alphafold_plddt: Optional[float] = None
    alphafold_domains: list[str] = field(default_factory=list)
    encode_tissues: dict[str, float] = field(default_factory=dict)
    alphagenome_status: str = "Ready / Key Needed"


# ===========================================================================
# Built-in High-Impact Knowledge Base (ClinVar, HPA, CPIC, gnomAD)
# ===========================================================================
CURATED_KB: dict[str, dict[str, Any]] = {
    # ---- APOE: Alzheimer's & Cardiovascular ----
    "rs429358": {
        "gene": "APOE",
        "name": "APOE-e4 determinant (Cys130Arg)",
        "acmg": False,
        "gnomad_af": 0.15,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "cerebral cortex": "Medium", "plasma": "High"},
            "subcellular": ["Secreted", "Endoplasmic reticulum"],
        },
        "alleles": {
            "CC": {
                "significance": "Risk Factor",
                "stars": 3,
                "magnitude": 5.0,
                "repute": "Bad",
                "phenotype": "APOE e4/e4 homozygote: ~12-15x elevated risk for late-onset Alzheimer's disease.",
                "category": "Risk Factor",
            },
            "CT": {
                "significance": "Risk Factor",
                "stars": 3,
                "magnitude": 3.5,
                "repute": "Bad",
                "phenotype": "APOE e4 carrier (e3/e4 or e2/e4): ~3-4x increased risk for late-onset Alzheimer's disease.",
                "category": "Risk Factor",
            },
            "TT": {
                "significance": "Common / Benign",
                "stars": 3,
                "magnitude": 1.0,
                "repute": "Good",
                "phenotype": "Non-e4 carrier at rs429358 (e3 or e2 allele). Average or baseline Alzheimer's risk.",
                "category": "Trait",
            },
        },
    },
    "rs7412": {
        "gene": "APOE",
        "name": "APOE-e2 determinant (Arg176Cys)",
        "acmg": False,
        "gnomad_af": 0.08,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "cerebral cortex": "Medium"},
            "subcellular": ["Secreted"],
        },
        "alleles": {
            "TT": {
                "significance": "Protective / Benign",
                "stars": 3,
                "magnitude": 2.5,
                "repute": "Good",
                "phenotype": "APOE e2/e2: Protective against Alzheimer's disease; rare association with Type III hyperlipoproteinemia.",
                "category": "Trait",
            },
            "CT": {
                "significance": "Protective / Benign",
                "stars": 3,
                "magnitude": 2.0,
                "repute": "Good",
                "phenotype": "APOE e2 carrier: Moderate protective effect against Alzheimer's disease.",
                "category": "Trait",
            },
            "CC": {
                "significance": "Common / Benign",
                "stars": 3,
                "magnitude": 1.0,
                "repute": "Neutral",
                "phenotype": "Common allele (encodes normal Arg176).",
                "category": "Trait",
            },
        },
    },

    # ---- HFE: Hereditary Hemochromatosis ----
    "rs1800562": {
        "gene": "HFE",
        "name": "HFE C282Y",
        "acmg": True,
        "gnomad_af": 0.06,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "duodenum": "High", "spleen": "Medium"},
            "subcellular": ["Plasma membrane", "Endoplasmic reticulum"],
        },
        "alleles": {
            "AA": {
                "significance": "Pathogenic",
                "stars": 4,
                "magnitude": 4.5,
                "repute": "Bad",
                "phenotype": "Hereditary Hemochromatosis Type 1 (C282Y homozygote). High risk of iron overload; regular ferritin monitoring advised.",
                "category": "Pathogenic",
            },
            "AG": {
                "significance": "Pathogenic (Carrier)",
                "stars": 4,
                "magnitude": 2.0,
                "repute": "Neutral",
                "phenotype": "Carrier for Hereditary Hemochromatosis (C282Y heterozygote). Low individual risk unless compound heterozygous with H63D.",
                "category": "Carrier",
            },
            "GG": {
                "significance": "Benign",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal wild-type HFE C282 allele.",
                "category": "Benign",
            },
        },
    },
    "rs1799945": {
        "gene": "HFE",
        "name": "HFE H63D",
        "acmg": True,
        "gnomad_af": 0.14,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "duodenum": "High"},
            "subcellular": ["Plasma membrane"],
        },
        "alleles": {
            "GG": {
                "significance": "Risk Factor",
                "stars": 3,
                "magnitude": 2.0,
                "repute": "Neutral",
                "phenotype": "H63D homozygote: mild modifier for iron absorption; rarely causes clinical hemochromatosis alone.",
                "category": "Risk Factor",
            },
            "CG": {
                "significance": "Risk Factor (Carrier)",
                "stars": 3,
                "magnitude": 1.5,
                "repute": "Neutral",
                "phenotype": "H63D carrier: common variant with minimal clinical significance unless paired with C282Y.",
                "category": "Carrier",
            },
            "CC": {
                "significance": "Benign",
                "stars": 3,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal wild-type HFE H63 allele.",
                "category": "Benign",
            },
        },
    },

    # ---- Factor V Leiden & Prothrombin: Thrombophilia ----
    "rs6025": {
        "gene": "F5",
        "name": "Factor V Leiden (R506Q)",
        "acmg": False,
        "gnomad_af": 0.03,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "plasma": "High"},
            "subcellular": ["Secreted"],
        },
        "alleles": {
            "AA": {
                "significance": "Pathogenic",
                "stars": 4,
                "magnitude": 5.0,
                "repute": "Bad",
                "phenotype": "Factor V Leiden homozygote: 50-80x increased lifetime risk of deep vein thrombosis (DVT) and pulmonary embolism.",
                "category": "Pathogenic",
            },
            "AG": {
                "significance": "Pathogenic",
                "stars": 4,
                "magnitude": 3.0,
                "repute": "Bad",
                "phenotype": "Factor V Leiden heterozygote: 4-8x increased risk of venous thromboembolism. Caution with oral contraceptives or prolonged immobility.",
                "category": "Risk Factor",
            },
            "GG": {
                "significance": "Benign",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal wild-type Factor V.",
                "category": "Benign",
            },
        },
    },
    "rs1799963": {
        "gene": "F2",
        "name": "Prothrombin G20210A",
        "acmg": False,
        "gnomad_af": 0.02,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "plasma": "High"},
            "subcellular": ["Secreted"],
        },
        "alleles": {
            "AA": {
                "significance": "Pathogenic",
                "stars": 4,
                "magnitude": 4.5,
                "repute": "Bad",
                "phenotype": "Prothrombin G20210A homozygote: markedly elevated prothrombin levels and substantial thrombophilia risk.",
                "category": "Pathogenic",
            },
            "AG": {
                "significance": "Pathogenic",
                "stars": 4,
                "magnitude": 2.8,
                "repute": "Bad",
                "phenotype": "Prothrombin G20210A heterozygote: ~2-3x increased risk of venous thrombosis.",
                "category": "Risk Factor",
            },
            "GG": {
                "significance": "Benign",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal wild-type Prothrombin.",
                "category": "Benign",
            },
        },
    },

    # ---- Pharmacogenomics: CYP2C19 (Plavix / Clopidogrel) ----
    "rs4244285": {
        "gene": "CYP2C19",
        "name": "CYP2C19*2 (Loss of Function)",
        "acmg": False,
        "gnomad_af": 0.15,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "duodenum": "Medium"},
            "subcellular": ["Endoplasmic reticulum membrane"],
        },
        "alleles": {
            "AA": {
                "significance": "Drug Response",
                "stars": 4,
                "magnitude": 4.0,
                "repute": "Bad",
                "phenotype": "CYP2C19 Poor Metabolizer (*2/*2): Significantly impaired clopidogrel (Plavix) activation; alternative antiplatelet (ticagrelor/prasugrel) strongly indicated by CPIC.",
                "category": "Pharmacogenomics",
                "drug": "Clopidogrel, Omeprazole, Escitalopram",
            },
            "AG": {
                "significance": "Drug Response",
                "stars": 4,
                "magnitude": 2.5,
                "repute": "Neutral",
                "phenotype": "CYP2C19 Intermediate Metabolizer (*1/*2): Reduced clopidogrel activation; CPIC recommends alternative agent for acute coronary syndrome.",
                "category": "Pharmacogenomics",
                "drug": "Clopidogrel",
            },
            "GG": {
                "significance": "Normal Response",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "CYP2C19 Normal Metabolizer (*1/*1): Standard clopidogrel dosing effective.",
                "category": "Pharmacogenomics",
                "drug": "Clopidogrel",
            },
        },
    },

    # ---- Pharmacogenomics: VKORC1 (Warfarin Sensitivity) ----
    "rs9923231": {
        "gene": "VKORC1",
        "name": "VKORC1 -1639G>A (Warfarin Sensitivity)",
        "acmg": False,
        "gnomad_af": 0.39,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "placenta": "Medium"},
            "subcellular": ["Endoplasmic reticulum membrane"],
        },
        "alleles": {
            "AA": {
                "significance": "Drug Response",
                "stars": 4,
                "magnitude": 3.5,
                "repute": "Neutral",
                "phenotype": "High Warfarin sensitivity: Requires significantly reduced starting dose to avoid bleeding complications (CPIC Level A guideline).",
                "category": "Pharmacogenomics",
                "drug": "Warfarin",
            },
            "AG": {
                "significance": "Drug Response",
                "stars": 4,
                "magnitude": 2.0,
                "repute": "Neutral",
                "phenotype": "Intermediate Warfarin sensitivity: Moderate dose reduction typically required.",
                "category": "Pharmacogenomics",
                "drug": "Warfarin",
            },
            "GG": {
                "significance": "Normal Response",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal Warfarin dose requirement.",
                "category": "Pharmacogenomics",
                "drug": "Warfarin",
            },
        },
    },

    # ---- Pharmacogenomics: SLCO1B1 (Statin Myopathy) ----
    "rs4149056": {
        "gene": "SLCO1B1",
        "name": "SLCO1B1*5 (Statin-Induced Myopathy)",
        "acmg": False,
        "gnomad_af": 0.15,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High"},
            "subcellular": ["Plasma membrane"],
        },
        "alleles": {
            "CC": {
                "significance": "Drug Response",
                "stars": 4,
                "magnitude": 4.0,
                "repute": "Bad",
                "phenotype": "Poor SLCO1B1 transport function: 17x elevated risk of simvastatin-induced skeletal myopathy / rhabdomyolysis. CPIC recommends rosuvastatin or lower dose.",
                "category": "Pharmacogenomics",
                "drug": "Simvastatin, Atorvastatin",
            },
            "CT": {
                "significance": "Drug Response",
                "stars": 4,
                "magnitude": 2.5,
                "repute": "Neutral",
                "phenotype": "Intermediate SLCO1B1 function: 4.5x elevated risk of simvastatin-induced myopathy.",
                "category": "Pharmacogenomics",
                "drug": "Simvastatin",
            },
            "TT": {
                "significance": "Normal Response",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal SLCO1B1 transporter function: Standard statin tolerance.",
                "category": "Pharmacogenomics",
                "drug": "Statins",
            },
        },
    },

    # ---- MTHFR: Folate & Homocysteine ----
    "rs1801133": {
        "gene": "MTHFR",
        "name": "MTHFR C677T (Ala222Val)",
        "acmg": False,
        "gnomad_af": 0.32,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "kidney": "Medium", "brain": "Medium"},
            "subcellular": ["Cytoplasm"],
        },
        "alleles": {
            "AA": {
                "significance": "Risk Factor",
                "stars": 3,
                "magnitude": 2.5,
                "repute": "Neutral",
                "phenotype": "MTHFR 677TT homozygote (~30% normal enzyme activity): Mild predisposition to elevated plasma homocysteine if folate intake is inadequate.",
                "category": "Risk Factor",
            },
            "AG": {
                "significance": "Trait",
                "stars": 3,
                "magnitude": 1.0,
                "repute": "Neutral",
                "phenotype": "MTHFR 677CT heterozygote (~65% normal enzyme activity): Generally benign with normal dietary folate.",
                "category": "Trait",
            },
            "GG": {
                "significance": "Benign",
                "stars": 3,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal MTHFR 677CC wild-type activity.",
                "category": "Benign",
            },
        },
    },

    # ---- LCT: Lactase Persistence ----
    "rs4988235": {
        "gene": "MCM6 / LCT",
        "name": "Lactase Persistence C/T-13910",
        "acmg": False,
        "gnomad_af": 0.50,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"small intestine": "High", "duodenum": "High"},
            "subcellular": ["Brush border membrane"],
        },
        "alleles": {
            "AA": {
                "significance": "Trait",
                "stars": 3,
                "magnitude": 1.0,
                "repute": "Good",
                "phenotype": "Lactase persistent: Capable of digesting dairy lactose normally in adulthood.",
                "category": "Trait",
            },
            "AG": {
                "significance": "Trait",
                "stars": 3,
                "magnitude": 1.0,
                "repute": "Good",
                "phenotype": "Lactase persistent (carrier): Normal adult dairy lactose tolerance.",
                "category": "Trait",
            },
            "GG": {
                "significance": "Trait",
                "stars": 3,
                "magnitude": 1.2,
                "repute": "Neutral",
                "phenotype": "Lactase non-persistent: Predisposition to adult lactose intolerance / dairy sensitivity.",
                "category": "Trait",
            },
        },
    },

    # ---- ALDH2: Alcohol Flush Reaction ----
    "rs671": {
        "gene": "ALDH2",
        "name": "ALDH2*2 Glu504Lys (Alcohol Flush)",
        "acmg": False,
        "gnomad_af": 0.05,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"liver": "High", "kidney": "High", "heart": "Medium"},
            "subcellular": ["Mitochondria"],
        },
        "alleles": {
            "AA": {
                "significance": "Trait / Risk",
                "stars": 4,
                "magnitude": 3.0,
                "repute": "Bad",
                "phenotype": "ALDH2 inactive homozygote: Severe facial flushing, nausea, and tachycardia with alcohol ingestion. Strong protection against alcoholism.",
                "category": "Trait",
            },
            "AG": {
                "significance": "Trait / Risk",
                "stars": 4,
                "magnitude": 2.0,
                "repute": "Neutral",
                "phenotype": "ALDH2*2 carrier: Moderate facial flushing and acetaldehyde buildup upon alcohol consumption.",
                "category": "Trait",
            },
            "GG": {
                "significance": "Benign",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal ALDH2 wild-type activity.",
                "category": "Benign",
            },
        },
    },

    # ---- CFTR: Cystic Fibrosis deltaF508 ----
    "rs113993960": {
        "gene": "CFTR",
        "name": "CFTR p.Phe508del (deltaF508)",
        "acmg": False,
        "gnomad_af": 0.015,
        "gnomad_pli": 0.0,
        "hpa": {
            "tissues": {"pancreas": "High", "lung": "High", "duodenum": "High"},
            "subcellular": ["Plasma membrane", "Apical membrane"],
        },
        "alleles": {
            "DD": {
                "significance": "Pathogenic",
                "stars": 4,
                "magnitude": 5.0,
                "repute": "Bad",
                "phenotype": "Cystic Fibrosis homozygote (F508del/F508del): Severe classical cystic fibrosis.",
                "category": "Pathogenic",
            },
            "DI": {
                "significance": "Pathogenic (Carrier)",
                "stars": 4,
                "magnitude": 3.0,
                "repute": "Neutral",
                "phenotype": "Cystic Fibrosis Carrier (deltaF508 heterozygote). Asymptomatic carrier; 1 in 4 risk with carrier partner.",
                "category": "Carrier",
            },
            "II": {
                "significance": "Benign",
                "stars": 4,
                "magnitude": 0.0,
                "repute": "Good",
                "phenotype": "Normal wild-type CFTR.",
                "category": "Benign",
            },
        },
    },
}


class VariantAnnotator:
    """Enriches parsed VariantCalls with clinical, proteomic, and population annotations."""

    def __init__(self, custom_kb: dict[str, Any] | None = None):
        self.kb = dict(CURATED_KB)
        if custom_kb:
            self.kb.update(custom_kb)
        self.segregation_engine = SegregationEngine()
        self.biotools = BiotoolsOrchestrator()

    def annotate_call(self, call: VariantCall) -> AnnotationRecord | None:
        """Annotate a single VariantCall using the curated database and segregation engine."""
        entry = self.kb.get(call.rsid)
        if not entry:
            return None

        gene = entry.get("gene", "Unknown")
        alleles_map = entry.get("alleles", {})
        hpa_data = entry.get("hpa", {})

        # Match exact genotype or reversed allele order
        allele_info = alleles_map.get(call.genotype)
        if not allele_info and len(call.genotype) == 2:
            rev_gt = call.genotype[1] + call.genotype[0]
            allele_info = alleles_map.get(rev_gt)

        # Watson-Crick reverse complement lookup for minus-strand genotyping calls
        if not allele_info and len(call.genotype) == 2:
            comp_map = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}
            comp_gt = "".join(comp_map.get(b, b) for b in call.genotype)
            allele_info = alleles_map.get(comp_gt)
            if not allele_info:
                allele_info = alleles_map.get(comp_gt[1] + comp_gt[0])

        if not allele_info:
            # Fallback for alleles not explicitly cataloged
            seg = self.segregation_engine.analyze_variant_segregation(call, gene, "Research", "Unannotated Allele")
            return AnnotationRecord(
                rsid=call.rsid,
                gene=gene,
                genotype=call.genotype,
                call=call,
                clinical_significance="Unannotated Allele",
                review_stars=entry.get("default_stars", 1),
                phenotype=f"Observed genotype: {call.genotype} at {entry.get('name', call.rsid)}",
                category="Research",
                magnitude=1.0,
                repute="Neutral",
                hpa_tissues=hpa_data.get("tissues", {}),
                hpa_subcellular=hpa_data.get("subcellular", []),
                gnomad_af=entry.get("gnomad_af", 0.0),
                gnomad_pli=entry.get("gnomad_pli", 0.0),
                acmg_actionable=bool(gene in ACMG_SF_GENES or entry.get("acmg")),
                inheritance_mode=seg.mode_of_inheritance,
                is_carrier=seg.is_carrier,
                partner_carrier_prior=seg.partner_carrier_prior,
                offspring_recurrence_risk=seg.offspring_risk_unscreened_partner,
                segregation_notes=seg.segregation_notes,
            )

        cat = allele_info.get("category", "Trait")
        sig = allele_info.get("significance", "Uncertain")
        seg = self.segregation_engine.analyze_variant_segregation(call, gene, cat, sig)

        return AnnotationRecord(
            rsid=call.rsid,
            gene=gene,
            genotype=call.genotype,
            call=call,
            clinical_significance=sig,
            review_stars=allele_info.get("stars", 1),
            phenotype=allele_info.get("phenotype", ""),
            category=cat,
            magnitude=allele_info.get("magnitude", 1.0),
            repute=allele_info.get("repute", "Neutral"),
            hpa_tissues=hpa_data.get("tissues", {}),
            hpa_subcellular=hpa_data.get("subcellular", []),
            gnomad_af=entry.get("gnomad_af", 0.0),
            gnomad_pli=entry.get("gnomad_pli", 0.0),
            drug_response=allele_info.get("drug", ""),
            notes=entry.get("name", ""),
            acmg_actionable=bool(gene in ACMG_SF_GENES or entry.get("acmg")),
            inheritance_mode=seg.mode_of_inheritance,
            is_carrier=seg.is_carrier,
            partner_carrier_prior=seg.partner_carrier_prior,
            offspring_recurrence_risk=seg.offspring_risk_carrier_partner if seg.is_carrier else seg.offspring_risk_unscreened_partner,
            segregation_notes=seg.segregation_notes,
        )

    def resolve_apoe_diplotype(
        self, variants: dict[str, VariantCall]
    ) -> tuple[AnnotationRecord | None, dict[str, Any] | None]:
        """
        Synthesize the compound APOE diplotype (epsilon 2/3/4) from rs429358 and rs7412.
        Normalizes forward/reverse strand calls and assigns definitive clinical risk.
        """
        call_429 = variants.get("rs429358")
        call_741 = variants.get("rs7412")

        if not call_429 and not call_741:
            return None, None

        def norm_429(gt: str) -> str:
            # Forward: T (ref/e3), C (alt/e4). Reverse: A (ref/e3), G (alt/e4)
            gt = gt.upper()
            if gt in ("TT", "AA"):
                return "TT"
            elif gt in ("CT", "TC", "AG", "GA"):
                return "CT"
            elif gt in ("CC", "GG"):
                return "CC"
            return gt

        def norm_741(gt: str) -> str:
            # Forward: C (ref/e3), T (alt/e2). Reverse: G (ref/e3), A (alt/e2)
            gt = gt.upper()
            if gt in ("CC", "GG"):
                return "CC"
            elif gt in ("CT", "TC", "AG", "GA"):
                return "CT"
            elif gt in ("TT", "AA"):
                return "TT"
            return gt

        gt_429 = norm_429(call_429.genotype) if call_429 and call_429.zygosity != "nocall" else None
        gt_741 = norm_741(call_741.genotype) if call_741 and call_741.zygosity != "nocall" else None

        if not gt_429 and not gt_741:
            return None, None

        diplotype = ""
        label = ""
        phenotype = ""
        category = "Carrier"
        significance = ""
        magnitude = 1.0
        repute = "Neutral"
        risk_ratio = ""
        lifetime_risk = ""

        if gt_429 == "TT" and gt_741 == "CC":
            diplotype = "ε3/ε3"
            label = "APOE ε3/ε3 (Normal Baseline)"
            category = "Carrier"  # Accessible in Carrier tab & All
            significance = "Normal / Baseline"
            magnitude = 1.5
            repute = "Good"
            risk_ratio = "1.0× (Average Population Baseline)"
            lifetime_risk = "10–15% lifetime Alzheimer's risk"
            phenotype = (
                "APOE ε3/ε3: The most common human genotype (~60–65% population frequency). "
                "Represents the normal population baseline for late-onset Alzheimer's disease "
                "risk and standard lipid metabolism."
            )
        elif gt_429 == "CT" and gt_741 == "CC":
            diplotype = "ε3/ε4"
            label = "APOE ε3/ε4 Carrier"
            category = "Carrier"
            significance = "Risk Factor / Carrier"
            magnitude = 4.2
            repute = "Bad"
            risk_ratio = "3–4× Increased Risk"
            lifetime_risk = "25–35% lifetime Alzheimer's risk"
            phenotype = (
                "APOE ε3/ε4 Heterozygous Carrier: One ε4 copy conferring ~3–4× elevated risk "
                "for late-onset Alzheimer's disease (~20–25% population prevalence; ~25–35% lifetime risk). "
                "Cardiovascular health, regular aerobic exercise, ApoB management, and quality sleep are "
                "protective modulators."
            )
        elif gt_429 == "CC" and gt_741 == "CC":
            diplotype = "ε4/ε4"
            label = "APOE ε4/ε4 Homozygote"
            category = "Risk Factor"
            significance = "High Risk Factor"
            magnitude = 6.0
            repute = "Bad"
            risk_ratio = "12–15× Markedly Elevated Risk"
            lifetime_risk = "50–65% lifetime Alzheimer's risk"
            phenotype = (
                "APOE ε4/ε4 Homozygote: Two copies of the ε4 allele (~2% population prevalence). "
                "Associated with ~12–15× increased lifetime risk of late-onset Alzheimer's disease and "
                "higher LDL-cholesterol/atherosclerosis susceptibility."
            )
        elif gt_429 == "TT" and gt_741 == "CT":
            diplotype = "ε2/ε3"
            label = "APOE ε2/ε3 Carrier"
            category = "Carrier"
            significance = "Protective / Carrier"
            magnitude = 2.2
            repute = "Good"
            risk_ratio = "0.6× (Protective Effect)"
            lifetime_risk = "5–8% lifetime Alzheimer's risk"
            phenotype = (
                "APOE ε2/ε3 Heterozygous Carrier: One protective ε2 allele and one neutral ε3 allele "
                "(~10–15% population prevalence). Associated with ~40–50% lower lifetime risk of "
                "Alzheimer's disease and lower circulating LDL-cholesterol."
            )
        elif gt_429 == "TT" and gt_741 == "TT":
            diplotype = "ε2/ε2"
            label = "APOE ε2/ε2 Homozygote"
            category = "Carrier"
            significance = "Protective AD / Lipid Risk"
            magnitude = 3.5
            repute = "Bad"
            risk_ratio = "Protective AD / Type III HLP Risk"
            lifetime_risk = "<5% AD risk; Monitor blood lipid panels"
            phenotype = (
                "APOE ε2/ε2 Homozygote: Protective against Alzheimer's disease, but strongly associated "
                "with genetic predisposition to Type III Hyperlipoproteinemia (familial dysbetalipoproteinemia; "
                "requires secondary metabolic triggers like obesity or diabetes for clinical expression)."
            )
        elif gt_429 == "CT" and gt_741 == "CT":
            diplotype = "ε2/ε4"
            label = "APOE ε2/ε4 Double Heterozygote"
            category = "Carrier"
            significance = "Risk Factor / Carrier"
            magnitude = 3.2
            repute = "Bad"
            risk_ratio = "1.5–2× Intermediate Risk"
            lifetime_risk = "15–20% lifetime Alzheimer's risk"
            phenotype = (
                "APOE ε2/ε4 Double Heterozygote: Carries one protective ε2 allele and one risk-elevating ε4 "
                "allele (~2% population prevalence). Overall Alzheimer's risk is intermediate between ε3/ε3 "
                "and ε3/ε4, as the ε2 allele partially mitigates ε4 risk."
            )
        elif not gt_429 or not gt_741:
            diplotype = "Indeterminate"
            label = "APOE Indeterminate (Missing rs429358 or rs7412)"
            category = "Trait"
            significance = "Incomplete Loci"
            magnitude = 1.0
            repute = "Neutral"
            risk_ratio = "Unknown"
            lifetime_risk = "Cannot determine without both loci"
            phenotype = (
                "Both rs429358 (codon 112) and rs7412 (codon 158) must be genotyped to determine an APOE diplotype. "
                "A single locus cannot distinguish ε3 from ε2 or ε4 without unsupported population assumptions."
            )
        else:
            diplotype = "Indeterminate"
            label = f"APOE ({gt_429 or '?'}/{gt_741 or '?'})"
            category = "Carrier"
            significance = "Uncertain"
            magnitude = 1.0
            repute = "Neutral"
            risk_ratio = "Uncertain"
            lifetime_risk = "Average population risk"
            phenotype = f"Atypical APOE combination: rs429358={gt_429}, rs7412={gt_741}."

        raw_calls_str = f"rs429358:{call_429.genotype if call_429 else '--'}, rs7412:{call_741.genotype if call_741 else '--'}"
        dummy_call = VariantCall(
            rsid="APOE-STATUS",
            chrom="19",
            pos=45411941,
            genotype=diplotype,
            zygosity="het" if "Carrier" in label or "Heterozygote" in label else "hom",
        )

        apoe_info = {
            "diplotype": diplotype,
            "label": label,
            "risk_ratio": risk_ratio,
            "lifetime_risk": lifetime_risk,
            "phenotype": phenotype,
            "repute": repute,
            "magnitude": magnitude,
            "category": category,
            "rs429358": call_429.genotype if call_429 else None,
            "rs7412": call_741.genotype if call_741 else None,
            "raw_summary": raw_calls_str,
        }

        record = AnnotationRecord(
            rsid="APOE-STATUS",
            gene="APOE",
            genotype=f"{diplotype} ({raw_calls_str})",
            call=dummy_call,
            clinical_significance=significance,
            review_stars=4,
            phenotype=phenotype,
            category=category,
            magnitude=magnitude,
            repute=repute,
            hpa_tissues={"liver": "High", "cerebral cortex": "Medium", "plasma": "High"},
            hpa_subcellular=["Secreted", "Endoplasmic reticulum"],
            gnomad_af=0.15,
            gnomad_pli=0.0,
            acmg_actionable=False,
            notes=label,
            inheritance_mode="Co-Dominant Complex Alleles (ε2/ε3/ε4)",
            is_carrier=bool("Carrier" in label or "Heterozygote" in label),
            partner_carrier_prior=0.25,
            offspring_recurrence_risk=0.50 if "Carrier" in label or "Heterozygote" in label else 0.0,
            segregation_notes=(
                "APOE Haplotype Segregation: rs429358 and rs7412 reside on chromosome 19q13.32 in tight linkage disequilibrium. "
                "They do not segregate independently, but transmit as discrete ε2, ε3, or ε4 maternal and paternal haplotypes."
            ),
        )

        return record, apoe_info

    def enrich_record_with_biotools(self, record: AnnotationRecord) -> AnnotationRecord:
        """Deeply enrich an AnnotationRecord with live data from ClinVar, Ensembl, AlphaFold, and ENCODE."""
        if record.rsid == "APOE-STATUS":
            # Query gene-level AlphaFold and ENCODE for APOE
            af = self.biotools.analyze_alphafold_structure("APOE")
            if "uniprot_id" in af:
                record.alphafold_plddt = af.get("global_plddt")
                record.alphafold_domains = af.get("domains", [])
            enc = self.biotools.query_encode_expression("APOE")
            if "top_expressing_tissues" in enc:
                record.encode_tissues = enc["top_expressing_tissues"]
            return record

        enriched = self.biotools.enrich_variant(
            rsid=record.rsid,
            gene=record.gene,
            genotype=record.genotype,
            chrom=str(record.call.chrom),
            pos=record.call.pos,
        )

        # Update record with biotools insights
        if enriched.vep_consequence:
            record.vep_consequence = enriched.vep_consequence
        if enriched.vep_sift:
            record.vep_sift = enriched.vep_sift
        if enriched.vep_alphamissense_class:
            record.vep_alphamissense_class = enriched.vep_alphamissense_class
        if enriched.vep_alphamissense_score is not None:
            record.vep_alphamissense_score = enriched.vep_alphamissense_score
        if enriched.vep_loeuf is not None:
            record.vep_loeuf = enriched.vep_loeuf
        if enriched.alphafold_plddt is not None:
            record.alphafold_plddt = enriched.alphafold_plddt
        if enriched.alphafold_domains:
            record.alphafold_domains = enriched.alphafold_domains
        if enriched.encode_top_tissues:
            record.encode_tissues = enriched.encode_top_tissues
        record.alphagenome_status = enriched.alphagenome_status

        return record

    def annotate_genome(
        self, variants: dict[str, VariantCall]
    ) -> list[AnnotationRecord]:
        """Scan full genome dictionary and return sorted list of matched clinical annotations."""
        records: list[AnnotationRecord] = []
        for rsid, call in variants.items():
            if rsid in self.kb and call.zygosity != "nocall":
                rec = self.annotate_call(call)
                if rec:
                    records.append(rec)

        # Synthesize compound APOE Diplotype
        apoe_rec, _ = self.resolve_apoe_diplotype(variants)
        if apoe_rec:
            records.append(apoe_rec)

        # Sort: Highest clinical magnitude & review stars first
        records.sort(key=lambda r: (r.magnitude, r.review_stars), reverse=True)
        return records

    def summarize_annotations(
        self, records: list[AnnotationRecord], variants: dict[str, VariantCall] | None = None
    ) -> dict[str, Any]:
        """Produce structured categorized summary with segregation and compound findings for UI and reporting."""
        categories = {
            "Pathogenic": [],
            "Carrier": [],
            "Pharmacogenomics": [],
            "Risk Factor": [],
            "Trait": [],
            "Benign": [],
        }

        acmg_findings = []
        carrier_findings = []
        dominant_findings = []
        recessive_findings = []

        for r in records:
            cat = r.category if r.category in categories else "Trait"
            categories[cat].append(r)
            if r.acmg_actionable and r.category in ("Pathogenic", "Risk Factor", "Carrier"):
                acmg_findings.append(r)
            if r.is_carrier:
                carrier_findings.append({
                    "rsid": r.rsid,
                    "gene": r.gene,
                    "genotype": r.genotype,
                    "condition": r.phenotype,
                    "recurrence_risk_unscreened": r.offspring_recurrence_risk,
                    "partner_prior": r.partner_carrier_prior,
                })
            if "Dominant" in r.inheritance_mode:
                dominant_findings.append(r)
            elif "Recessive" in r.inheritance_mode:
                recessive_findings.append(r)

        # Evaluate Compound Heterozygosity and Independent Assortment
        compound_hits = []
        assortment_hits = []
        if variants:
            compound_hits = self.segregation_engine.detect_compound_heterozygosity(variants)

        seg_reports = [
            self.segregation_engine.analyze_variant_segregation(
                r.call, r.gene, r.category, r.clinical_significance
            )
            for r in records
            if r.rsid != "APOE-STATUS" and r.call
        ]
        if seg_reports:
            multi_seg = self.segregation_engine.evaluate_independent_assortment(seg_reports)
            assortment_hits = [
                {
                    "loci": s.loci,
                    "genes": s.genes,
                    "chromosomes": s.chromosomes,
                    "independent_prob": s.independent_transmission_prob,
                    "description": s.combined_clinical_impact,
                    "recommendation": s.recommendation,
                }
                for s in multi_seg
            ]

        return {
            "total_annotated": len(records),
            "pathogenic_count": len(categories["Pathogenic"]),
            "carrier_count": len(categories["Carrier"]),
            "pgx_count": len(categories["Pharmacogenomics"]),
            "risk_factor_count": len(categories["Risk Factor"]),
            "acmg_actionable_findings": len(acmg_findings),
            "categories": categories,
            "acmg_findings": acmg_findings,
            "carrier_findings": carrier_findings,
            "compound_heterozygote_findings": compound_hits,
            "independent_assortment_findings": assortment_hits,
            "segregation_summary": {
                "autosomal_recessive_carriers": len(carrier_findings),
                "autosomal_dominant_loci": len(dominant_findings),
                "compound_heterozygotes_detected": len(compound_hits),
                "multi_locus_independent_pairs": len(assortment_hits),
            },
        }
