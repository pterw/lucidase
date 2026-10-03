"""
Tests for the build's cross-checks against the pinned upstream captures (S3b-C-2 follow-ups C-5, C-6, C-7).

Every case runs the real CLI (`--verify-only`) against a temp copy of the pinned directory with the
changed file's meta re-pinned (as tests/test_three_layer_architecture.py does), so the sha256 check
passes and only the branch under test can fail. The committed fixtures are never touched.
"""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.build_canonical_kb import DEFAULT_CURATION_PATH, build_kb, load_curation, render_kb

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "build_canonical_kb.py"
UPSTREAM = ROOT / "tools" / "fixtures" / "upstream" / "real"


@pytest.fixture(scope="module")
def curation():
    return load_curation(DEFAULT_CURATION_PATH)


@pytest.fixture()
def upstream(tmp_path):
    root = tmp_path / "real"
    shutil.copytree(UPSTREAM, root)
    return root


@pytest.fixture()
def good_kb(tmp_path, curation):
    path = tmp_path / "kb.json"
    path.write_text(render_kb(build_kb(copy.deepcopy(curation))[0]), encoding="utf-8", newline="\n")
    return path


def repin(root: Path, source: str, name: str, data: bytes) -> None:
    """Write `data` as the capture body and record its sha256 and size in the meta beside it."""
    (root / source / f"{name}.json").write_bytes(data)
    meta = root / source / f"{name}.meta.json"
    info = json.loads(meta.read_text(encoding="utf-8"))
    info["sha256_of_body"], info["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    meta.write_text(json.dumps(info), encoding="utf-8")


def edit_capture(root: Path, source: str, name: str, old: bytes, new: bytes) -> None:
    data = (root / source / f"{name}.json").read_bytes()
    assert data.count(old) == 1, (name, old)
    repin(root, source, name, data.replace(old, new))


def drop_capture(root: Path, source: str, name: str) -> None:
    for suffix in (".json", ".meta.json"):
        (root / source / f"{name}{suffix}").unlink()


def verify(tmp_path, good_kb, curation, upstream, doc=None):
    path = tmp_path / "curation.json"
    path.write_text(json.dumps(doc or curation, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--verify-only", "--kb-path", str(good_kb), "--curation-path", str(path),
         "--upstream-path", str(upstream)],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )


def assert_one_qc_error(result, *fragments):
    assert result.returncode == 1, result.stdout + result.stderr
    assert "QC errors: 1" in result.stdout, result.stdout
    for fragment in fragments:
        assert fragment in result.stdout, (fragment, result.stdout)


def test_the_real_captures_build_with_no_qc_error(tmp_path, good_kb, curation, upstream):
    result = verify(tmp_path, good_kb, curation, upstream)
    assert result.returncode == 0, result.stdout + result.stderr


# --- C-6: one test per previously untested branch of _overlay_imported -----------------------------------------
def test_gnomad_capture_for_another_variant_fails_the_build(tmp_path, good_kb, curation, upstream):
    edit_capture(upstream, "gnomad", "rs671", b'"variant_id":"12-111803962-G-A"', b'"variant_id":"12-111803962-G-T"')
    result = verify(tmp_path, good_kb, curation, upstream)
    assert_one_qc_error(result, "rs671", "gnomAD capture is for 12-111803962-G-T", "12-111803962-G-A")


def test_gnomad_constraint_capture_for_another_gene_fails_the_build(tmp_path, good_kb, curation, upstream):
    edit_capture(upstream, "gnomad", "constraint_HFE", b'"symbol":"HFE"', b'"symbol":"TFR2"')
    result = verify(tmp_path, good_kb, curation, upstream)
    assert result.returncode == 1 and "gnomAD constraint capture is for TFR2, the locus gene is HFE" in result.stdout


def test_incomplete_selected_clinvar_record_fails_the_build(tmp_path, good_kb, curation, upstream):
    edit_capture(upstream, "clinvar", "rs671", b'"description":"drug response"', b'"description":""')
    result = verify(tmp_path, good_kb, curation, upstream)
    assert_one_qc_error(result, "rs671", "selected ClinVar record is incomplete", "significance")


def test_no_matching_clinvar_record_fails_the_build(tmp_path, good_kb, curation, upstream):
    edit_capture(upstream, "clinvar", "rs671", b'{"db_source":"dbSNP","db_id":"671"}', b'{"db_source":"dbSNP","db_id":"672"}')
    result = verify(tmp_path, good_kb, curation, upstream)
    assert_one_qc_error(result, "rs671", "no ClinVar record matches the locus alleles", "VCV000018390")


def test_unreadable_upstream_payload_fails_the_build(tmp_path, good_kb, curation, upstream):
    edit_capture(upstream, "ensembl", "rs671", b'"allele_string":"G/A","id":"rs671"', b'"allele_string":"G/A","id":"rs672"')
    result = verify(tmp_path, good_kb, curation, upstream)
    assert_one_qc_error(result, "rs671", "upstream payload cannot be imported", "VEP payload is not for rs671")


# --- C-5: a missing or empty capture is an error, never a skipped check ----------------------------------------
@pytest.mark.parametrize(
    "source,name",
    [
        ("dbsnp", "rs671"),
        ("clinvar", "rs671"),
        ("gnomad", "rs671"),
        ("ensembl", "rs671"),
        ("gnomad", "constraint_ALDH2"),
    ],
)
def test_a_missing_capture_fails_the_build_and_names_the_file(tmp_path, good_kb, curation, upstream, source, name):
    drop_capture(upstream, source, name)
    result = verify(tmp_path, good_kb, curation, upstream)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{source}/{name}.json" in result.stdout and "rs671" in result.stdout, result.stdout
    assert "QC errors: 0" not in result.stdout


@pytest.mark.parametrize("source,name", [("dbsnp", "rs671"), ("gnomad", "rs671"), ("ensembl", "rs671"),
                                         ("gnomad", "constraint_ALDH2")])
@pytest.mark.parametrize("body", [b"{}", b"[]", b"null"])
def test_an_empty_capture_fails_the_build_and_names_the_file(tmp_path, good_kb, curation, upstream, source, name, body):
    repin(upstream, source, name, body)
    result = verify(tmp_path, good_kb, curation, upstream)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{source}/{name}.json" in result.stdout and "empty" in result.stdout, result.stdout


def test_the_per_variant_capture_satisfies_the_gnomad_requirement(tmp_path, good_kb, curation, upstream):
    """rs4244285 has no usable rsid-level capture (L6), so its per-variant file is the expected one."""
    drop_capture(upstream, "gnomad", "rs4244285")
    result = verify(tmp_path, good_kb, curation, upstream)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_gnomad_af_with_a_reason_while_curation_holds_an_af_fails_the_build(tmp_path, good_kb, curation, upstream):
    """gnomAD returns a variant whose records have an of 0: af is None with a reason, the curated af would stand unchecked."""
    body = b'{"data":{"variant":{"variant_id":"12-111803962-G-A","rsid":"rs671","exome":{"ac":0,"an":0},"genome":null}}}'
    repin(upstream, "gnomad", "rs671", body)
    result = verify(tmp_path, good_kb, curation, upstream)
    assert_one_qc_error(result, "rs671", "gnomAD af is unavailable", "no exome or genome record with an > 0")


def test_a_gnomad_af_with_a_reason_is_fine_where_curation_holds_no_af(tmp_path, good_kb, curation, upstream):
    doc = copy.deepcopy(curation)
    doc["loci"]["rs671"]["evidence"]["gnomad"]["af"] = None
    body = b'{"data":{"variant":{"variant_id":"12-111803962-G-A","rsid":"rs671","exome":{"ac":0,"an":0},"genome":null}}}'
    repin(upstream, "gnomad", "rs671", body)
    result = verify(tmp_path, good_kb, curation, upstream, doc)
    assert "gnomAD af is unavailable" not in result.stdout


# --- C-7: an identity the payload omits is an error ------------------------------------------------------------
def test_a_gnomad_capture_without_a_variant_id_fails_the_build(tmp_path, good_kb, curation, upstream):
    edit_capture(upstream, "gnomad", "rs671", b'"variant_id":"12-111803962-G-A",', b"")
    result = verify(tmp_path, good_kb, curation, upstream)
    assert_one_qc_error(result, "rs671", "gnomAD capture is for None")


def test_a_constraint_capture_without_a_symbol_fails_the_build(tmp_path, good_kb, curation, upstream):
    edit_capture(upstream, "gnomad", "constraint_HFE", b'"symbol":"HFE",', b"")
    result = verify(tmp_path, good_kb, curation, upstream)
    assert result.returncode == 1 and "gnomAD constraint capture is for None, the locus gene is HFE" in result.stdout
