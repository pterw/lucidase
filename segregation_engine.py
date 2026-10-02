"""
Segregation Engine: Mendelian Inheritance, Carrier Transmission & Compound Haplotypes
=====================================================================================
Implements quantitative genetics calculations for clinical variome analysis:
1. Mendelian Inheritance Classification:
   - Autosomal Recessive (AR), Autosomal Dominant (AD), X-Linked (XLR/XLD), Mitochondrial.
2. Carrier Status & Offspring Transmission Risk:
   - Calculates recurrence probability: P(affected child) = P(partner carrier) * 0.25 for AR.
   - Computes partner carrier prior from gnomAD population allele frequencies (Hardy-Weinberg 2pq).
   - Evaluates 50% transmission risk for Autosomal Dominant variants.
3. Compound Heterozygosity & Linkage Phasing (Cis vs Trans):
   - Identifies multi-variant hits in the same gene (e.g. HFE C282Y + H63D, CFTR variants).
   - Models trans segregation (independent parental alleles) vs cis segregation (linked allele).
4. Mendel's Law of Independent Assortment (Multi-Locus Segregation):
   - Computes joint probabilities for unlinked loci on distinct chromosomes (e.g. F5 on chr1 + F2 on chr11).
5. Family Scenario Modeling (Pedigree Simulator):
   - Computes offspring genotype distribution for Unscreened, Tested Carrier, and Affected partners.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from genomic_parser import VariantCall


# ===========================================================================
# Clinical Gene Inheritance Catalog (Curated Ground Truth)
# ===========================================================================
GENE_INHERITANCE_CATALOG: dict[str, dict[str, Any]] = {
    # Autosomal Recessive Genes
    "CFTR": {
        "mode": "Autosomal Recessive",
        "disease": "Cystic Fibrosis",
        "omim": "219700",
        "carrier_freq_nfe": 0.04,   # ~1 in 25 in European descent
        "carrier_freq_global": 0.02,
        "penetrance": 1.0,
        "description": "Mutations impair CFTR chloride channel, causing viscous mucus in lungs and pancreas.",
    },
    "HFE": {
        "mode": "Autosomal Recessive",
        "disease": "Hereditary Hemochromatosis Type 1",
        "omim": "235200",
        "carrier_freq_nfe": 0.10,   # ~1 in 10 in European descent
        "carrier_freq_global": 0.04,
        "penetrance": 0.20,         # Incomplete penetrance: 10-25% homozygotes develop clinical disease
        "description": "Excess iron absorption and hepatic/cardiac storage.",
        "compound_heterozygote_pairs": [("rs1800562", "rs1799945")], # C282Y + H63D
    },
    "ATP7B": {
        "mode": "Autosomal Recessive",
        "disease": "Wilson Disease",
        "omim": "277900",
        "carrier_freq_nfe": 0.011,
        "carrier_freq_global": 0.01,
        "penetrance": 0.95,
        "description": "Impaired biliary copper excretion leading to hepatic and neurological degeneration.",
    },
    "GBA": {
        "mode": "Autosomal Recessive",
        "disease": "Gaucher Disease",
        "omim": "230800",
        "carrier_freq_nfe": 0.015,
        "carrier_freq_global": 0.008,
        "penetrance": 0.85,
        "description": "Glucocerebrosidase deficiency with hepatosplenomegaly and cytopenias.",
    },
    "MUTYH": {
        "mode": "Autosomal Recessive",
        "disease": "MUTYH-Associated Polyposis (MAP)",
        "omim": "608456",
        "carrier_freq_nfe": 0.02,
        "carrier_freq_global": 0.01,
        "penetrance": 0.90,
        "description": "Base excision repair deficiency causing colorectal adenomas and early-onset carcinoma.",
    },
    "ALDH2": {
        "mode": "Autosomal Dominant / Incomplete Dominant",
        "disease": "Alcohol Flush Reaction / Acetaldehyde Toxicity",
        "omim": "100650",
        "carrier_freq_nfe": 0.001,
        "carrier_freq_global": 0.08,  # Highly prevalent in East Asian (~35-45%)
        "penetrance": 0.95,
        "description": "Dominant negative Glu504Lys inactivation of mitochondrial aldehyde dehydrogenase.",
    },

    # Autosomal Dominant Genes
    "F5": {
        "mode": "Autosomal Dominant / Incomplete Dominant",
        "disease": "Thrombophilia due to Factor V Leiden",
        "omim": "188055",
        "carrier_freq_nfe": 0.05,   # ~5% in Europeans
        "carrier_freq_global": 0.02,
        "penetrance": 0.10,         # ~10% lifetime VTE risk in heterozygotes
        "description": "Resistance to activated protein C (APC) leading to hypercoagulability.",
    },
    "F2": {
        "mode": "Autosomal Dominant / Incomplete Dominant",
        "disease": "Thrombophilia due to Prothrombin G20210A",
        "omim": "176930",
        "carrier_freq_nfe": 0.025,
        "carrier_freq_global": 0.015,
        "penetrance": 0.08,
        "description": "Elevated prothrombin biosynthesis and increased venous thromboembolism risk.",
    },
    "BRCA1": {
        "mode": "Autosomal Dominant",
        "disease": "Hereditary Breast and Ovarian Cancer Syndrome (HBOC)",
        "omim": "113705",
        "carrier_freq_nfe": 0.0025, # ~1 in 400
        "carrier_freq_global": 0.002,
        "penetrance": 0.72,         # ~70% lifetime breast cancer risk
        "description": "DNA double-strand break homologous recombination repair defect.",
    },
    "BRCA2": {
        "mode": "Autosomal Dominant",
        "disease": "Hereditary Breast and Ovarian Cancer Syndrome (HBOC)",
        "omim": "600185",
        "carrier_freq_nfe": 0.0025,
        "carrier_freq_global": 0.002,
        "penetrance": 0.69,
        "description": "Homologous recombination DNA repair defect.",
    },
    "LDLR": {
        "mode": "Autosomal Dominant / Co-Dominant",
        "disease": "Familial Hypercholesterolemia",
        "omim": "143890",
        "carrier_freq_nfe": 0.004,  # ~1 in 250
        "carrier_freq_global": 0.003,
        "penetrance": 0.90,
        "description": "Defective LDL clearance resulting in severe premature atherosclerotic cardiovascular disease.",
    },
    "MLH1": {
        "mode": "Autosomal Dominant",
        "disease": "Lynch Syndrome (HNPCC Type 1)",
        "omim": "120436",
        "carrier_freq_nfe": 0.001,
        "carrier_freq_global": 0.0008,
        "penetrance": 0.75,
        "description": "Mismatch repair deficiency predisposing to colorectal and endometrial carcinomas.",
    },

    # Pharmacogenomics / Complex Multi-Locus
    "CYP2C19": {
        "mode": "Codominant Pharmacogenomic",
        "disease": "Clopidogrel / Antidepressant Metabolism",
        "omim": "124020",
        "carrier_freq_nfe": 0.28,
        "carrier_freq_global": 0.35,
        "penetrance": 1.0,
        "description": "Alters conversion of clopidogrel prodrug into active platelet-inhibiting thiol metabolite.",
    },
    "SLCO1B1": {
        "mode": "Codominant Pharmacogenomic",
        "disease": "Statin-Induced Myopathy Sensitivity",
        "omim": "604843",
        "carrier_freq_nfe": 0.25,
        "carrier_freq_global": 0.20,
        "penetrance": 0.40,
        "description": "Hepatic OATP1B1 transporter deficiency causes elevated plasma statin exposure.",
    },
    "VKORC1": {
        "mode": "Codominant Pharmacogenomic",
        "disease": "Warfarin Sensitivity",
        "omim": "608547",
        "carrier_freq_nfe": 0.38,
        "carrier_freq_global": 0.45,
        "penetrance": 1.0,
        "description": "Altered vitamin K epoxide reductase promoter sensitivity to warfarin inhibition.",
    },
    "APOE": {
        "mode": "Co-Dominant Complex Alleles (ε2/ε3/ε4)",
        "disease": "Late-Onset Alzheimer's Disease & Dysbetalipoproteinemia",
        "omim": "107741",
        "carrier_freq_nfe": 0.25,
        "carrier_freq_global": 0.22,
        "penetrance": 0.60,
        "description": "Lipid transport and amyloid-beta clearance kinetics determined by linked haplotype alleles.",
    },
    "MTHFR": {
        "mode": "Autosomal Recessive / Biomarker Modifier",
        "disease": "Homocysteine & Folate Metabolism Variation",
        "omim": "607093",
        "carrier_freq_nfe": 0.45,
        "carrier_freq_global": 0.35,
        "penetrance": 0.05,
        "description": "Thermolabile enzyme variant with modest reduction in 5-MTHF synthesis.",
    },
}


@dataclass
class OffspringGenotypeProb:
    """Predicted probability and phenotype for an offspring genotype."""
    genotype: str
    probability: float
    carrier_status: str  # "Affected", "Carrier", "Unaffected Non-Carrier"
    risk_assessment: str


@dataclass
class SegregationReport:
    """Mendelian segregation and transmission risk report for a genomic locus."""
    rsid: str
    gene: str
    patient_genotype: str
    chrom: str
    pos: int
    mode_of_inheritance: str
    clinical_condition: str
    omim_id: str
    is_carrier: bool
    is_affected: bool
    penetrance: float
    partner_carrier_prior: float
    offspring_risk_unscreened_partner: float
    offspring_risk_carrier_partner: float
    offspring_distribution: list[OffspringGenotypeProb]
    segregation_notes: str
    independent_assortment_group: str  # e.g. "Chromosome 1 locus"
    compound_heterozygote_flag: bool = False
    compound_notes: str = ""


@dataclass
class MultiLocusSegregation:
    """Joint independent assortment calculations across multiple unlinked chromosomes."""
    loci: list[str]
    genes: list[str]
    chromosomes: list[str]
    are_unlinked: bool
    independent_transmission_prob: float
    combined_clinical_impact: str
    recommendation: str


class SegregationEngine:
    """Comprehensive engine for analyzing Mendelian independent segregation, carrier risk,
    and multi-locus independent assortment."""

    def __init__(self, catalog: Optional[dict[str, dict[str, Any]]] = None):
        self.catalog = catalog or GENE_INHERITANCE_CATALOG

    def classify_inheritance(self, gene: str) -> dict[str, Any]:
        """Look up curated inheritance profile for a gene."""
        return self.catalog.get(
            gene.upper(),
            {
                "mode": "Unknown / Complex",
                "disease": f"Associated with {gene}",
                "omim": "N/A",
                "carrier_freq_nfe": 0.01,
                "carrier_freq_global": 0.01,
                "penetrance": 0.50,
                "description": "Inheritance pattern not cataloged in standard curated panel.",
            },
        )

    def analyze_variant_segregation(
        self,
        call: VariantCall,
        gene: str,
        category: str = "Carrier",
        significance: str = "Pathogenic",
    ) -> SegregationReport:
        """Evaluate Mendelian segregation, transmission risk, and partner scenarios for a variant call."""
        info = self.classify_inheritance(gene)
        mode = info["mode"]
        disease = info["disease"]
        penetrance = info.get("penetrance", 1.0)
        pop_carrier_prior = info.get("carrier_freq_nfe", 0.02)
        gt = call.genotype.upper()
        zygosity = call.zygosity

        is_carrier = False
        is_affected = False

        if "Recessive" in mode:
            if zygosity == "het":
                is_carrier = True
                is_affected = False
            elif zygosity == "hom" and "Pathogenic" in significance:
                is_carrier = False
                is_affected = True
        elif "Dominant" in mode:
            if zygosity in ("het", "hom") and ("Pathogenic" in significance or "Risk" in category):
                is_affected = True
                is_carrier = False

        # Calculate Mendelian Offspring Risks
        # 1. Partner is untested (general population prior)
        if "Recessive" in mode:
            if is_carrier:
                # User (Aa) x Partner (? = Aa with prob pop_carrier_prior)
                # P(affected child) = P(partner Aa) * 0.25
                risk_unscreened = round(pop_carrier_prior * 0.25, 4)
                risk_carrier = 0.25  # 1 in 4 if partner is known carrier
                distribution = [
                    OffspringGenotypeProb(
                        genotype="Aa (Heterozygote)",
                        probability=0.50,
                        carrier_status="Carrier",
                        risk_assessment="50% chance offspring is an asymptomatic carrier.",
                    ),
                    OffspringGenotypeProb(
                        genotype="aa (Homozygous Variant)",
                        probability=0.25,
                        carrier_status="Affected (if partner carrier)",
                        risk_assessment=f"25% chance offspring is clinically affected if partner is also a carrier (Penetrance: {int(penetrance*100)}%).",
                    ),
                    OffspringGenotypeProb(
                        genotype="AA (Homozygous Wild-Type)",
                        probability=0.25,
                        carrier_status="Unaffected Non-Carrier",
                        risk_assessment="25% chance offspring inherits neither risk allele from carrier parents.",
                    ),
                ]
                notes = (
                    f"Autosomal Recessive Carrier: Individual carries one mutant allele. "
                    f"Recurrence risk with an unscreened partner is ~{round(risk_unscreened*100, 2)}% "
                    f"(1 in {round(1/max(risk_unscreened, 0.0001))}). If partner is a confirmed carrier, "
                    f"recurrence risk is 25% (1 in 4) per pregnancy."
                )
            elif is_affected:
                # User (aa) x Partner (AA or Aa)
                risk_unscreened = round(pop_carrier_prior * 0.50, 4)
                risk_carrier = 0.50  # 1 in 2 if partner is carrier
                distribution = [
                    OffspringGenotypeProb(
                        genotype="Aa (Obligate Carrier)",
                        probability=1.0 if pop_carrier_prior < 0.05 else 0.85,
                        carrier_status="Carrier",
                        risk_assessment="100% of offspring inherit mutant allele from homozygous parent.",
                    ),
                ]
                notes = "Autosomal Recessive Affected: 100% of offspring will be obligate carriers unless partner is also a carrier."
            else:
                risk_unscreened = 0.0
                risk_carrier = 0.0
                distribution = []
                notes = "Wild-type genotype; baseline population risk."
        elif "Dominant" in mode:
            if is_affected or "Pathogenic" in significance or "Risk" in category:
                # User (Aa) x Partner (aa) -> 50% transmission
                risk_unscreened = 0.50
                risk_carrier = 0.50
                clinical_risk_prob = round(0.50 * penetrance, 3)
                distribution = [
                    OffspringGenotypeProb(
                        genotype="Aa (Heterozygote)",
                        probability=0.50,
                        carrier_status="Affected / Risk Carrier",
                        risk_assessment=f"50% transmission probability to offspring. Clinical penetrance: {int(penetrance*100)}% (Effective penetrant risk: ~{int(clinical_risk_prob*100)}%).",
                    ),
                    OffspringGenotypeProb(
                        genotype="aa (Wild-Type)",
                        probability=0.50,
                        carrier_status="Unaffected Non-Carrier",
                        risk_assessment="50% probability offspring inherits wild-type allele.",
                    ),
                ]
                notes = (
                    f"Autosomal Dominant Transmission: 50% probability of passing risk allele to each offspring. "
                    f"Because clinical penetrance is {int(penetrance*100)}%, effective lifetime risk is ~{int(clinical_risk_prob*100)}%."
                )
            else:
                risk_unscreened = 0.0
                risk_carrier = 0.0
                distribution = []
                notes = "Wild-type genotype; baseline population risk."
        else:
            # Pharmacogenomic / Complex
            risk_unscreened = 0.50 if zygosity == "het" else (1.0 if zygosity == "hom" else 0.0)
            risk_carrier = risk_unscreened
            distribution = [
                OffspringGenotypeProb(
                    genotype=f"{gt} Segregation",
                    probability=0.50 if zygosity == "het" else 1.0,
                    carrier_status="Pharmacogenomic Modifier",
                    risk_assessment="Codominant allele transmission influences drug response/metabolism kinetics.",
                ),
            ]
            notes = "Pharmacogenomic allele: transmits codominantly. Influences enzyme activity and dosing requirements."

        return SegregationReport(
            rsid=call.rsid,
            gene=gene,
            patient_genotype=gt,
            chrom=str(call.chrom),
            pos=call.pos,
            mode_of_inheritance=mode,
            clinical_condition=disease,
            omim_id=info.get("omim", "N/A"),
            is_carrier=is_carrier,
            is_affected=is_affected,
            penetrance=penetrance,
            partner_carrier_prior=pop_carrier_prior,
            offspring_risk_unscreened_partner=risk_unscreened,
            offspring_risk_carrier_partner=risk_carrier,
            offspring_distribution=distribution,
            segregation_notes=notes,
            independent_assortment_group=f"Chromosome {call.chrom} locus",
        )

    def detect_compound_heterozygosity(
        self, variants: dict[str, VariantCall]
    ) -> list[dict[str, Any]]:
        """Identify multi-variant compound heterozygosity in the same gene (e.g. HFE C282Y + H63D)."""
        compound_findings = []

        # Check HFE (rs1800562 C282Y and rs1799945 H63D)
        v_c282y = variants.get("rs1800562")
        v_h63d = variants.get("rs1799945")

        if v_c282y and v_h63d:
            gt_c282y = v_c282y.genotype.upper()
            gt_h63d = v_h63d.genotype.upper()

            is_c282y_het = gt_c282y in ("AG", "GA", "CT", "TC")
            is_h63d_het = gt_h63d in ("CG", "GC")

            if is_c282y_het and is_h63d_het:
                compound_findings.append({
                    "gene": "HFE",
                    "type": "Compound Heterozygote (C282Y / H63D)",
                    "rsids": ["rs1800562", "rs1799945"],
                    "genotypes": f"rs1800562:{gt_c282y}, rs1799945:{gt_h63d}",
                    "inheritance": "Autosomal Recessive (Compound)",
                    "clinical_significance": "Pathogenic / Moderate Hemochromatosis Risk",
                    "phenotype": (
                        "HFE C282Y/H63D Compound Heterozygote: Carrying both C282Y and H63D on separate homologous "
                        "chromosomes (trans configuration) confers a 1.5–3× increased risk of mild to moderate iron overload. "
                        "Clinical penetrance is lower than C282Y homozygosity (~1.5–2% develop severe clinical disease), "
                        "but regular serum ferritin and transferrin saturation monitoring is recommended."
                    ),
                    "segregation_analysis": (
                        "Trans Phasing: In ~98% of European individuals with this genotype, C282Y and H63D reside on "
                        "opposite chromosomes (inherited from different parents). Each child has a 50% chance of inheriting "
                        "C282Y and a 50% chance of inheriting H63D (they segregate independently to gametes as separate parental alleles)."
                    ),
                    "actionable": True,
                })

        # Check CFTR multi-variant loci
        cftr_calls = [
            (rsid, call)
            for rsid, call in variants.items()
            if rsid in ("rs113993960", "rs75527207", "rs121908745")
            and call.zygosity == "het"
        ]
        if len(cftr_calls) >= 2:
            compound_findings.append({
                "gene": "CFTR",
                "type": "Compound Heterozygote (CFTR Multi-Locus)",
                "rsids": [rs for rs, _ in cftr_calls],
                "genotypes": ", ".join(f"{rs}:{c.genotype}" for rs, c in cftr_calls),
                "inheritance": "Autosomal Recessive (Compound)",
                "clinical_significance": "Pathogenic (Compound Heterozygous Cystic Fibrosis)",
                "phenotype": "Two distinct CFTR pathogenic mutations detected; compound heterozygotes typically manifest classic cystic fibrosis.",
                "segregation_analysis": "Likely trans phase; offspring have 50% chance of receiving variant 1 and 50% chance of receiving variant 2.",
                "actionable": True,
            })

        return compound_findings

    def evaluate_independent_assortment(
        self, reports: list[SegregationReport]
    ) -> list[MultiLocusSegregation]:
        """Compute joint inheritance probabilities under Mendel's Law of Independent Assortment
        for risk variants located on different chromosomes."""
        pathogenic_reports = [
            r for r in reports
            if r.is_affected or (r.is_carrier and r.mode_of_inheritance == "Autosomal Dominant")
            or "Pharmacogenomics" in r.mode_of_inheritance
        ]

        results = []

        # Find multi-locus pairs on different chromosomes
        for i in range(len(pathogenic_reports)):
            for j in range(i + 1, len(pathogenic_reports)):
                r1 = pathogenic_reports[i]
                r2 = pathogenic_reports[j]

                # Mendel's second law requires unlinked loci (different chromosomes)
                if r1.chrom != r2.chrom:
                    # Transmission probability for each locus is typically 0.50 (for heterozygous state)
                    p1 = 0.50 if "het" in r1.patient_genotype.lower() or len(set(r1.patient_genotype)) > 1 else 1.0
                    p2 = 0.50 if "het" in r2.patient_genotype.lower() or len(set(r2.patient_genotype)) > 1 else 1.0
                    joint_p = round(p1 * p2, 4)

                    combined_desc = f"Joint Segregation: {r1.gene} ({r1.clinical_condition}) on Chr {r1.chrom} + {r2.gene} ({r2.clinical_condition}) on Chr {r2.chrom}."

                    # Check for known synergetic combinations
                    # Case 1: Thrombophilia dual risk (Factor V Leiden + Prothrombin G20210A)
                    if {r1.gene, r2.gene} == {"F5", "F2"}:
                        combined_desc = (
                            "Compound Thrombophilia Multi-Locus Risk: Factor V Leiden (Chr 1) and Prothrombin G20210A (Chr 11) "
                            "segregate completely independently on non-homologous chromosomes. An individual carrying both variants "
                            "has a dramatically compounded (20–40×) risk of venous thromboembolism. Offspring have a 25% (0.50 × 0.50) "
                            "independent probability of inheriting BOTH risk factors."
                        )
                        rec = "High-risk prothrombotic state. Prophylaxis during surgery, pregnancy, or long travel strongly indicated."
                    # Case 2: Warfarin dual PGx (VKORC1 + CYP2C19/CYP2C9)
                    elif {r1.gene, r2.gene} == {"VKORC1", "CYP2C19"}:
                        combined_desc = (
                            "Dual Pharmacogenomic Co-Segregation: VKORC1 (Chr 16) and CYP2C19 (Chr 10) segregate independently. "
                            "Simultaneous carrier status alters both pharmacodynamics (receptor sensitivity) and pharmacokinetics (drug clearance)."
                        )
                        rec = "CPIC algorithms require aggressive dose reductions (~50%) when both pathways are impaired."
                    else:
                        rec = "Independent assortment indicates offspring inheritance of one locus does not alter the inheritance of the other."

                    results.append(
                        MultiLocusSegregation(
                            loci=[r1.rsid, r2.rsid],
                            genes=[r1.gene, r2.gene],
                            chromosomes=[r1.chrom, r2.chrom],
                            are_unlinked=True,
                            independent_transmission_prob=joint_p,
                            combined_clinical_impact=combined_desc,
                            recommendation=rec,
                        )
                    )

        return results

    def simulate_offspring_pedigree(
        self,
        gene: str,
        patient_genotype: str,
        partner_status: str = "unscreened", # "unscreened", "carrier", "affected", "wildtype"
    ) -> dict[str, Any]:
        """Simulate offspring risk distribution given a defined partner screening status."""
        info = self.classify_inheritance(gene)
        mode = info["mode"]
        penetrance = info.get("penetrance", 1.0)
        carrier_freq = info.get("carrier_freq_nfe", 0.02)

        # Autosomal Recessive Model
        if "Recessive" in mode:
            if partner_status == "carrier":
                p_affected = 0.25
                p_carrier = 0.50
                p_wildtype = 0.25
            elif partner_status == "affected":
                p_affected = 0.50
                p_carrier = 0.50
                p_wildtype = 0.00
            elif partner_status == "wildtype":
                p_affected = 0.00
                p_carrier = 0.50
                p_wildtype = 0.50
            else:  # unscreened
                p_affected = round(carrier_freq * 0.25, 4)
                p_carrier = round(0.50 + carrier_freq * 0.25, 4)
                p_wildtype = round(1.0 - p_affected - p_carrier, 4)

            effective_penetrant_risk = round(p_affected * penetrance, 4)

            return {
                "gene": gene,
                "disease": info["disease"],
                "mode": mode,
                "partner_status": partner_status,
                "p_affected_genotype": p_affected,
                "p_carrier_genotype": p_carrier,
                "p_wildtype_genotype": p_wildtype,
                "penetrance": penetrance,
                "effective_clinical_risk": effective_penetrant_risk,
                "summary": (
                    f"Under partner status '{partner_status}', the predicted risk of an affected child is "
                    f"{round(p_affected * 100, 2)}% (Effective penetrant risk: {round(effective_penetrant_risk * 100, 2)}%). "
                    f"Probability of a carrier child is {round(p_carrier * 100, 2)}%."
                ),
            }

        # Autosomal Dominant Model
        elif "Dominant" in mode:
            p_transmits = 0.50
            effective_risk = round(p_transmits * penetrance, 4)
            return {
                "gene": gene,
                "disease": info["disease"],
                "mode": mode,
                "partner_status": partner_status,
                "p_transmits_risk_allele": p_transmits,
                "penetrance": penetrance,
                "effective_clinical_risk": effective_risk,
                "summary": (
                    f"Autosomal Dominant inheritance: 50% probability of transmitting the risk allele. "
                    f"With {int(penetrance*100)}% penetrance, the effective probability of an affected child is {round(effective_risk * 100, 1)}%."
                ),
            }

        else:
            return {
                "gene": gene,
                "disease": info["disease"],
                "mode": mode,
                "partner_status": partner_status,
                "summary": "Complex or pharmacogenomic inheritance: alleles transmit codominantly without simple Mendelian recurrence.",
            }
