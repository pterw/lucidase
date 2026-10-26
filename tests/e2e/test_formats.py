from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import expect

from conftest import DEMO_FILE, apoe_row, open_apoe

FIXTURES = Path(__file__).parent / "fixtures"


def test_vcf_with_uppercase_header_renders_apoe(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "apoe-e3e4-uppercase-header.vcf"))
    expect(loaded_page.locator("#results-section")).to_be_visible()
    expect(loaded_page.locator("#qc-format")).to_contain_text("VCF (GRCh37)")
    expect(apoe_row(loaded_page)).to_be_visible()
    open_apoe(loaded_page)
    expect(loaded_page.locator("#drawer-ligature .lds-ligature-result")).to_have_text("APOE ε3/ε4")


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


def test_file_line_shows_name_format_and_genome_version_without_the_example_flag(loaded_page):
    loaded_page.set_input_files("#file-input", str(FIXTURES / "apoe-e3e4-uppercase-header.vcf"))
    expect(loaded_page.locator("#results-section")).to_be_visible()
    expect(loaded_page.locator("#file-line")).to_have_text("apoe-e3e4-uppercase-header.vcf · VCF · GRCh37")


def test_example_flag_follows_the_example_button_not_the_file_name(loaded_page):
    """A file named like the example is the person's own file; only the button's file is the made-up example."""
    loaded_page.set_input_files(
        "#file-input", {"name": "sample-23andme.txt", "mimeType": "text/plain", "buffer": DEMO_FILE.read_bytes()}
    )
    expect(loaded_page.locator("#results-section")).to_be_visible()
    line = loaded_page.locator("#file-line")
    expect(line).to_contain_text("sample-23andme.txt · 23andMe")
    expect(line).not_to_contain_text("made-up example")

    loaded_page.locator("#btn-use-another-file").click()
    loaded_page.locator("#btn-load-demo").click()
    expect(loaded_page.locator("#results-section")).to_be_visible()
    expect(line).to_have_text(re.compile(r"· made-up example$"))


def test_example_flag_does_not_outlive_the_example_when_the_person_loads_their_own_file(loaded_page):
    """After the example button, a real upload (directly or via "Use another file") never keeps the made-up flag."""
    vcf = str(FIXTURES / "apoe-e3e4-uppercase-header.vcf")
    line = loaded_page.locator("#file-line")
    loaded_page.locator("#btn-load-demo").click()
    expect(line).to_have_text(re.compile(r"· made-up example$"))

    # Example, then upload straight over it.
    loaded_page.set_input_files("#file-input", vcf)
    expect(line).to_have_text("apoe-e3e4-uppercase-header.vcf · VCF · GRCh37")

    # Example again, then "Use another file", then upload.
    loaded_page.locator("#btn-use-another-file").click()
    loaded_page.locator("#btn-load-demo").click()
    expect(line).to_have_text(re.compile(r"· made-up example$"))
    loaded_page.locator("#btn-use-another-file").click()
    loaded_page.set_input_files("#file-input", vcf)
    expect(line).to_have_text("apoe-e3e4-uppercase-header.vcf · VCF · GRCh37")
