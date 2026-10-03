"""Genotype-aware inheritance in the web app (T8: P0-008, P1-026, P1-027).

The drawer simulator and the CSV export used to ignore the patient's genotype: a wild-type
F5 locus showed a 50% chance, an e4/e4 patient showed 50/0/50, and trait or risk-factor genes
used disease and recurrence wording.
"""

from __future__ import annotations

import csv
from pathlib import Path

from playwright.sync_api import expect

from conftest import DEMO_FILE, wait_drawer_open

WILDTYPE = Path(__file__).parent / "fixtures" / "wildtype-23andme.txt"
FORBIDDEN_FOR_NON_MENDELIAN = ("affected", "recurrence", "disease risk")


def _wildtype_f5_file(tmp_path):
    """The wild-type fixture with a called, homozygous-reference F5 Leiden genotype (minus strand GG)."""
    text = WILDTYPE.read_text(encoding="utf-8").replace("rs6025\t1\t169519049\t--", "rs6025\t1\t169519049\tGG")
    # One observed variant (MTHFR het) so the CSV export has a findings list to write.
    text = text.replace("rs1801133\t1\t11856378\tGG", "rs1801133\t1\t11856378\tAG")
    assert "rs6025\t1\t169519049\tGG" in text and "rs1801133\t1\t11856378\tAG" in text
    path = tmp_path / "wildtype-f5-called.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _analyse(page, path):
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible(timeout=10000)


def _seg_text(page):
    return page.locator("#drawer-segregation-container").inner_text().lower()


def test_demo_apoe_e4e4_drawer_says_every_child_inherits_e4(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible(timeout=10000)
    page.locator("#btn-inspect-apoe").click()
    wait_drawer_open(page)
    page.locator(".partner-sim-btn[data-partner='wildtype']").click()
    expect(page.locator("#sim-p-affected")).to_have_text("100%")
    text = _seg_text(page)
    assert "inherits the e4 allele" in text or "inherits the c allele" in text, text
    for word in FORBIDDEN_FOR_NON_MENDELIAN:
        assert word not in text, f"'{word}' appears in the APOE e4/e4 drawer: {text}"


def test_wildtype_f5_drawer_has_no_affected_status_and_no_fifty_percent(loaded_page, tmp_path):
    page = loaded_page
    _analyse(page, _wildtype_f5_file(tmp_path))
    page.locator("[data-filter='negative']").click()
    page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs6025')")).click()
    wait_drawer_open(page)
    text = _seg_text(page)
    for word in FORBIDDEN_FOR_NON_MENDELIAN:
        assert word not in text, f"'{word}' appears in the wild-type F5 drawer: {text}"
    assert "50%" not in text, text
    page.locator(".partner-sim-btn[data-partner='wildtype']").click()
    expect(page.locator("#sim-p-affected")).to_have_text("0%")


def test_csv_has_no_half_risk_for_wildtype_loci(loaded_page, tmp_path):
    page = loaded_page
    _analyse(page, _wildtype_f5_file(tmp_path))
    with page.expect_download(timeout=5000) as info:
        page.evaluate("() => window.__lucidase.exportCsvReport()")
    rows = list(csv.DictReader(Path(info.value.path()).read_text(encoding="utf-8").splitlines()))
    wildtype = {r["rsID"]: r for r in rows if r["rsID"] in ("rs6025", "rs1799945", "rs1800562", "rs1799963")}
    assert set(wildtype) == {"rs6025", "rs1799945", "rs1800562", "rs1799963"}
    for rsid, row in wildtype.items():
        for column, value in row.items():
            assert value not in ("0.5", "0.50", "0.25"), f"{rsid} {column} = {value} for a wild-type locus"
    # Genotype-aware columns: a wild-type patient transmits nothing, and only Mendelian genes have an affected figure.
    assert wildtype["rs6025"]["Child_Inherits_Allele_Wildtype_Partner"] == "0"
    assert wildtype["rs6025"]["Child_Affected_Unscreened_Partner"] == "N/A"  # F5 is a risk factor, not Mendelian
    assert wildtype["rs1800562"]["Child_Affected_Unscreened_Partner"] == "0"  # HFE recessive, wild-type patient
    by_rsid = {r["rsID"]: r for r in rows}
    assert by_rsid["rs1801133"]["Child_Inherits_Allele_Wildtype_Partner"] == "0.5"  # MTHFR het patient
    assert by_rsid["rs1801133"]["Child_Affected_Unscreened_Partner"] == "N/A"  # trait: no disease wording


def test_demo_hfe_double_het_is_phase_unknown(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible(timeout=10000)
    section = page.locator("#assortment-cards-container").inner_text().lower()
    assert "possible compound heterozygote" in section, section
    assert "phase unknown" in section, section
    assert "trans phase" not in section
    assert "synergistic" not in section
