"""One honest rendering across the table, drawer and both exports (P1-028, P1-024).

A missing value used to render as a placeholder presented as data ("MANE Select Transcript", "Tier B", a one-star
default), a gap row printed "undefined", the APOE row showed an internal row id, and the page carried provenance claims
that no data backed ("ClinVar 2024-06", "Redis Edge Ready"). Every view now reads one view model, so the same record
shows the same tier, stars and limitation everywhere.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from conftest import DEMO_FILE, WEB_DIR, goto_ready, show_table, wait_drawer_closed, wait_drawer_open

WILDTYPE = Path(__file__).parent / "fixtures" / "wildtype-23andme.txt"
MANIFEST = json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))["manifest"]

# Matched case-insensitively: CSS `uppercase` changes the text that innerText reports.
PLACEHOLDERS = [
    "MANE Select Transcript",
    "MANE Select Pending",
    "Score Available in API",
    "Constraint Available",
    "N/A (Non-missense)",
    "N/A (Not characterized)",
    "Domain boundaries computed from PAE matrix.",
    "Tested Normal",
    "Normal Baseline",
    "APOE-STATUS",
    "known variants",
]
STATIC_CLAIMS = ["Redis", "ClinVar 2026.1", "ClinVar 2024-06", "dbSNP 156", "Evidence Tier 1", "81 Genes"]
# The jargon the design system's plain result words replaced, and star glyphs for ClinVar review (case-sensitive).
OLD_RESULT_WORDS = re.compile(r"State [1-5]|Supported|Observed|Tested WT|Array Gap|Wild-Type|Conflicting|[★☆]")
BAD_WORDS = re.compile(r"\b(undefined|null|nan)\b", re.IGNORECASE)


def _violations(text: str, banned=PLACEHOLDERS) -> list[str]:
    found = [m.group(0) for m in BAD_WORDS.finditer(text)]
    found += [s for s in banned if s.lower() in text.lower()]
    return found


def _analyse(page, path):
    page.set_input_files("#file-input", str(path))
    expect(page.locator("#results-section")).to_be_visible()


def _sparse_file(tmp_path):
    """The demo with six KB loci removed, including one APOE component."""
    drop = ("rs6025", "rs1799963", "rs4149056", "rs671", "rs113993960", "rs7412")
    lines = [ln for ln in DEMO_FILE.read_text(encoding="utf-8").splitlines() if not ln.startswith(drop)]
    path = tmp_path / "sparse-23andme.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _export(page, fn):
    with page.expect_download() as info:
        page.evaluate(f"() => window.__lucidase.{fn}()")
    return Path(info.value.path()).read_text(encoding="utf-8")


def test_product_name_is_lucidase_everywhere_the_user_sees_it(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    assert page.locator('[data-design-id="brand.wordmark"]').inner_text().strip() == "Lucidase"
    assert "Lucidase" in page.locator("footer").inner_text()
    assert "genomepulse" not in page.locator("body").inner_text().lower().replace(" ", "")
    names = []
    texts = []
    for fn in ("exportMarkdownReport", "exportCsvReport"):
        with page.expect_download() as info:
            page.evaluate(f"() => window.__lucidase.{fn}()")
        names.append(info.value.suggested_filename)
        texts.append(Path(info.value.path()).read_text(encoding="utf-8"))
    assert texts[0].splitlines()[0] == "# Lucidase variome clinical report"
    assert names[0].startswith("Lucidase_Report_")
    assert names[1].startswith("Lucidase_Variants_")


def _screens(page) -> str:
    """Page text plus the text of every table under every filter and every row's drawer."""
    show_table(page)
    chunks = [page.locator("body").inner_text()]
    for name in ("all", "negative", "gaps", "insufficient", "carrier", "pathogenic", "acmg", "pgx", "risk"):
        page.locator(f"[data-filter='{name}']").click()
        chunks.append(page.locator("#variants-tbody").inner_text())
        for i in range(page.locator("#variants-tbody tr").count()):
            row = page.locator("#variants-tbody tr").nth(i)
            if "No variants match" in row.inner_text():
                continue
            row.click()
            wait_drawer_open(page)
            chunks.append(page.locator("#variant-drawer").inner_text())
            page.locator("#btn-close-drawer").click()
            wait_drawer_closed(page)
    page.locator("[data-filter='all']").click()
    return "\n".join(chunks)


def _check_run(page, label):
    screens = _screens(page)
    markdown = _export(page, "exportMarkdownReport")
    csv_text = _export(page, "exportCsvReport")
    for name, text in (("page", screens), ("markdown", markdown), ("csv", csv_text)):
        assert not _violations(text), f"{label} {name}: {_violations(text)}"
        assert not _violations(text, STATIC_CLAIMS), f"{label} {name}: static claim {_violations(text, STATIC_CLAIMS)}"
        old = OLD_RESULT_WORDS.findall(text)
        assert not old, f"{label} {name}: old result wording {sorted(set(old))}"
    return screens, markdown, csv_text


def test_demo_renders_honestly_everywhere(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    _screens_text, markdown, csv_text = _check_run(page, "demo")
    rows = list(csv.DictReader(csv_text.splitlines()))
    assert any(r["rsID"] == "rs429358;rs7412" and r["Position"] == "45411941;45412079" for r in rows)


def test_wildtype_fixture_renders_honestly_everywhere(loaded_page):
    page = loaded_page
    _analyse(page, WILDTYPE)
    _check_run(page, "wildtype")


def test_sparse_file_renders_honestly_everywhere(loaded_page, tmp_path):
    page = loaded_page
    _analyse(page, _sparse_file(tmp_path))
    _screens_text, markdown, csv_text = _check_run(page, "sparse")
    rows = {r["rsID"]: r for r in csv.DictReader(csv_text.splitlines())}
    gap = rows["rs6025"]
    assert gap["Coverage_State"] == "not_tested_by_array"
    assert gap["Magnitude"] == "" and gap["Repute"] == "" and gap["Category"] == ""
    assert "magnitude" in gap["Missing_Fields"].split(";")
    assert gap["Position"] == "169519049"
    # The APOE row has no diplotype when a component is missing, and still names both loci.
    assert rows["rs429358;rs7412"]["Coverage_State"] == "not_tested_by_array"
    assert "rs429358;rs7412" in markdown


def test_apoe_drawer_labels_each_component_evidence_by_rsid(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    kb = json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))["loci"]
    page.locator("#btn-inspect-apoe").click()
    wait_drawer_open(page)
    stars = page.locator("#drawer-stars").inner_text()
    assert "rs429358:" in stars and "rs7412:" in stars, stars
    af = page.locator("#drawer-af").inner_text()
    assert "rs429358:" in af and "rs7412:" in af, af
    links = page.locator("#drawer-clinvar-link, [data-extra-clinvar-link]")
    assert links.count() == 2
    hrefs = [links.nth(i).get_attribute("href") for i in range(2)]
    expected = [
        f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{int(kb[r]['evidence']['clinvar']['accession'][3:])}"
        for r in ("rs429358", "rs7412")
    ]
    assert hrefs == expected
    assert "(rs429358)" in links.nth(0).inner_text() and "(rs7412)" in links.nth(1).inner_text()
    # Opening a single-locus record afterwards leaves exactly one unlabelled link.
    page.locator("#btn-close-drawer").click()
    show_table(page)
    page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs6025')")).click()
    wait_drawer_open(page)
    assert page.locator("#drawer-clinvar-link, [data-extra-clinvar-link]").count() == 1
    assert "(rs" not in page.locator("#drawer-clinvar-link").inner_text()


def test_index_html_carries_no_static_clinical_defaults():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for text in (
        "ENST00000252486",
        "likely_benign",
        "1.26 (Tolerant)",
        "Population Baseline",
        "Incomplete star-allele coverage refusal",
    ):
        assert text not in html, f"index.html still carries the static default {text!r}"


@pytest.mark.allow_console_errors
def test_a_kb_that_fails_validation_makes_no_page_claims(page):
    kb = json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))
    kb["schema_version"] = 1
    page.route(
        "**/knowledge-base.json",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(kb)),
    )
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    goto_ready(page, page.base_url)
    page.wait_for_function("() => document.getElementById('kb-provenance-text').textContent.includes('Not available')")
    badge = page.locator("#kb-provenance-badge")
    assert MANIFEST["release"] not in badge.inner_text()
    assert MANIFEST["sha256"][:12] not in badge.get_attribute("title")
    assert "Not available" in page.locator("#hero-scope").inner_text()
    assert any("schema_version" in e for e in errors), errors


@pytest.mark.allow_console_errors
def test_kb_text_is_escaped_where_it_reaches_innerhtml(page):
    payload = "<img src=x onerror=window.__xss=1>"
    kb = json.loads((WEB_DIR / "src" / "knowledge-base.json").read_text(encoding="utf-8"))
    interp = kb["loci"]["rs6025"]["interpretations"]["1"]
    interp["caveats"] = [payload]
    interp["phenotype"] = payload
    page.route(
        "**/knowledge-base.json",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(kb)),
    )
    goto_ready(page, page.base_url)
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    finding = page.locator('#report-groups article.lds-finding[data-finding-id="rs6025"]')
    assert payload in finding.locator(".lds-finding-statement").inner_text(), "the phenotype shows literally in the report"
    show_table(page)
    row = page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs6025')"))
    assert payload in row.inner_text(), "the phenotype shows literally in the table row"
    row.click()
    wait_drawer_open(page)
    assert payload in page.locator("#drawer-caveats-list").inner_text()
    assert page.locator("#report-groups img, #variants-tbody img, #drawer-caveats-list img").count() == 0
    assert page.evaluate("() => window.__xss") is None


def test_cyp2c19_row_carries_the_star_allele_limitation(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    show_table(page)
    row = page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs4244285')"))
    badge = row.locator("[data-role='limitation']")
    expect(badge).to_be_visible()
    assert "star-allele" in badge.get_attribute("title")
    row.click()
    wait_drawer_open(page)
    assert "star-allele" in page.locator("#drawer-refusal-text").inner_text()
    csv_text = _export(page, "exportCsvReport")
    cyp = next(r for r in csv.DictReader(csv_text.splitlines()) if r["rsID"] == "rs4244285")
    assert "star-allele" in cyp["Limitation"]
    assert "star-allele" in _export(page, "exportMarkdownReport")


def test_tested_wildtype_rows_state_the_count_and_the_limitation(loaded_page):
    page = loaded_page
    _analyse(page, WILDTYPE)
    show_table(page)
    page.locator("[data-filter='negative']").click()
    dpyd = page.locator("#variants-tbody tr", has=page.locator("td:first-child:text-is('rs3918290')"))
    text = dpyd.inner_text()
    assert "rs3918290 variant not detected (1 variant tested in DPYD)" in text
    assert "normal" not in text.lower()
    assert "Single-variant test" in dpyd.locator("[data-role='limitation']").get_attribute("title")
    dpyd.click()
    wait_drawer_open(page)
    assert "Single-variant test" in page.locator("#drawer-refusal-text").inner_text()


def test_static_claims_come_from_the_kb_manifest(loaded_page):
    page = loaded_page
    page.wait_for_function("() => document.getElementById('kb-provenance-badge').title.includes('sha256')")
    text = page.locator("body").inner_text()
    assert not _violations(text, STATIC_CLAIMS), _violations(text, STATIC_CLAIMS)
    badge = page.locator("#kb-provenance-badge")
    assert badge.inner_text().strip() == f"KB {MANIFEST['release']} · Offline"
    title = badge.get_attribute("title")
    assert MANIFEST["sha256"][:12] in title
    assert f"{MANIFEST['locus_count']} loci in {MANIFEST['gene_count']} genes" in title
    assert "ClinVar" not in title and "dbSNP" not in title
    hero = page.locator("#hero-scope").inner_text()
    assert hero.endswith(f"{MANIFEST['locus_count']} loci in {MANIFEST['gene_count']} genes tested")
    assert MANIFEST["acmg_sf_version"] in hero
    assert page.locator("#redis-status-indicator").count() == 0


def test_drawer_footer_shows_the_open_records_tier(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    show_table(page)
    page.locator("#variants-tbody tr").first.click()
    wait_drawer_open(page)
    tier = page.locator("#drawer-tier-badge").text_content().strip()
    assert tier.startswith("Tier ")
    assert page.locator("#drawer-footer-tier").inner_text().strip() == f"Evidence {tier}"


def test_apoe_drawer_names_both_loci_and_positions(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    page.locator("#btn-inspect-apoe").click()
    wait_drawer_open(page)
    assert page.locator("#drawer-rsid").inner_text().strip() == "APOE (rs429358 + rs7412)"
    coord = page.locator("#drawer-coord").inner_text()
    assert "45,411,941" in coord and "45,412,079" in coord
    assert "APOE-STATUS" not in page.locator("body").inner_text()


def test_ar_drawer_labels_the_two_affected_figures_and_states_the_partner_model(loaded_page):
    page = loaded_page
    page.locator("#btn-load-demo").click()
    expect(page.locator("#results-section")).to_be_visible()
    page.locator("button.btn-inspect-gene[data-gene='HFE']").first.click()
    wait_drawer_open(page)
    first = page.locator("#sim-p-affected").locator("xpath=preceding-sibling::span").inner_text()
    adjusted = page.locator("#sim-effective-risk").locator("xpath=preceding-sibling::span").inner_text()
    assert "genotype" in first.lower() and "penetrance" not in first.lower(), first
    assert "penetrance" in adjusted.lower(), adjusted
    note = page.locator("#drawer-partner-model-note")
    assert "unscreened" in note.inner_text().lower()
    assert "Hardy-Weinberg" in note.inner_text() and "gnomAD allele frequency" in note.inner_text()
    page.locator(".partner-sim-btn[data-partner='carrier']").click()
    assert "heterozygous" in note.inner_text().lower()


def test_filereader_failure_uses_the_analysis_error_alert(loaded_page):
    page = loaded_page
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.evaluate(
        """() => {
          FileReader.prototype.readAsText = function () {
            setTimeout(() => this.onerror && this.onerror(new Event('error')), 0);
          };
        }"""
    )
    page.set_input_files("#file-input", str(WILDTYPE))
    alert = page.locator("#analysis-error")
    expect(alert).to_be_visible()
    assert "Failed to read file" in page.locator("#analysis-error-detail").inner_text()
    expect(page.locator("#results-section")).to_be_hidden()
    assert dialogs == [], f"a blocking alert() was used: {dialogs}"
    # The inputs are usable again.
    expect(page.locator("#file-input")).to_be_enabled()


@pytest.mark.allow_console_errors
def test_page_claims_say_not_available_when_the_kb_cannot_load(page):
    page.route(
        "**/knowledge-base.json",
        lambda route: route.fulfill(status=500, content_type="application/json", body="{}"),
    )
    goto_ready(page, page.base_url)
    page.wait_for_function("() => document.getElementById('kb-provenance-text').textContent.includes('Not available')")
    assert "Not available" in page.locator("#hero-scope").inner_text()
    assert not _violations(page.locator("body").inner_text(), STATIC_CLAIMS)
