from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect

FIXTURES = Path(__file__).parent / "fixtures"


def test_vcf_with_uppercase_header_renders_apoe_card(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "apoe-e3e4-uppercase-header.vcf"))
    expect(loaded_page.locator("#results-section")).to_be_visible()
    expect(loaded_page.locator("#qc-format")).to_contain_text("VCF (GRCh37)")
    expect(loaded_page.locator("#apoe-status-card")).to_be_visible()
    expect(loaded_page.locator("#apoe-diplotype-title")).to_contain_text("ε3/ε4")


def test_ancestry_header_row_is_not_counted_as_a_snp(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "ancestry-with-header-row.txt"))
    expect(loaded_page.locator("#results-section")).to_be_visible()
    expect(loaded_page.locator("#qc-format")).to_contain_text("ANCESTRY")
    # five data rows (one is a no-call) and the column-header row is not a SNP
    expect(loaded_page.locator("#qc-total-snps")).to_have_text("5")


def test_sex_badge_shows_qc_signal_not_a_karyotype(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "ancestry-with-header-row.txt"))
    badge = loaded_page.locator("#qc-inferred-sex")
    expect(badge).to_have_text("Indeterminate (too few X markers)")


def test_unrecognised_text_shows_unsupported_error(loaded_page):
    loaded_page.set_input_files(
        "#file-input",
        {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"hello world\nthis is not genotype data\n"},
    )
    alert = loaded_page.locator("#analysis-error")
    expect(alert).to_be_visible()
    assert "unsupported" in alert.inner_text().lower()
    expect(loaded_page.locator("#results-section")).to_be_hidden()
