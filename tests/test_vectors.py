"""Runner for the shared vectors (contracts C6): every tests/vectors/*.json file.

Vector: { id, description, input, expected }. `expected` holds genetics or format
facts, compared as a SUBSET of the real output (same semantics as
web/tests/vectors.test.mjs):
  - plain keys (format, build, assay, stats, ...): objects recursively, scalars and
    lists by deep equality;
  - `calls`: the exact call list;  `calls_include`: calls that must be present;
  - `error`: the parser must raise an error whose class name equals it.

A vector file whose area has no entry in AREAS fails, so a new area cannot be
silently ignored. Per-area input shapes follow web/tests/vectors.test.mjs. Numbers
in the alleles/classify/apoe/inheritance areas compare within 1e-12; `absent` lists
dotted paths that must not exist; `text_includes` / `text_excludes` check the
lower-cased JSON of the result.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

VECTOR_DIR = Path(__file__).parent / "vectors"


def _assert_subset(actual, expected, path):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected an object, got {actual!r}"
        for key, want in expected.items():
            assert key in actual, f"{path}.{key}: missing"
            _assert_subset(actual[key], want, f"{path}.{key}")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def _run_parse(vector):
    from genomic_parser import parse_genotype_file

    text, file_name = vector["input"]["text"], vector["input"].get("fileName", "")
    exp = vector["expected"]
    if "error" in exp:
        with pytest.raises(Exception) as info:
            parse_genotype_file(text, file_name)
        assert type(info.value).__name__ == exp["error"], vector["id"]
        return
    result = asdict(parse_genotype_file(text, file_name))
    for key, want in exp.items():
        if key == "calls_include":
            for call in want:
                assert call in result["calls"], f"{vector['id']}: missing call {call}"
        else:
            _assert_subset(result[key], want, f"{vector['id']}.{key}")


def _assert_close(actual, expected, path):
    """Subset comparison: numbers within 1e-12, lists element by element."""
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        assert actual == expected and type(actual) is type(expected), f"{path}: {actual!r} != {expected!r}"
    elif isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool), f"{path}: not a number: {actual!r}"
        assert abs(actual - expected) <= 1e-12, f"{path}: {actual} != {expected}"
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected a list, got {actual!r}"
        assert len(actual) == len(expected), f"{path}: length {len(actual)} != {len(expected)}"
        for i, want in enumerate(expected):
            _assert_close(actual[i], want, f"{path}[{i}]")
    else:
        assert isinstance(actual, dict), f"{path}: expected an object, got {actual!r}"
        for key, want in expected.items():
            assert key in actual, f"{path}.{key}: missing"
            _assert_close(actual[key], want, f"{path}.{key}")


def _assert_text_and_absent(result, expected, vector_id):
    for dotted in expected.get("absent", []):
        value = result
        for key in dotted.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        assert value is None, f"{vector_id}: {dotted} must be absent"
    text = json.dumps(result, ensure_ascii=False).lower()
    for want in expected.get("text_includes", []):
        assert want.lower() in text, f"{vector_id}: missing {want!r}"
    for banned in expected.get("text_excludes", []):
        assert banned.lower() not in text, f"{vector_id}: must not contain {banned!r}"


def _run_alleles(vector):
    from variant_annotator import resolve_alt_count

    result = resolve_alt_count(vector["input"]["locus"], vector["input"]["alleles"])
    _assert_close(result, vector["expected"], vector["id"])


def _to_parse_result(parse):
    from genomic_parser import Call, ParseResult, ParseStats

    return ParseResult(
        parse["format"], parse["build"], parse["assay"],
        [Call(**c) for c in parse["calls"]], ParseStats(**parse["stats"]),
    )


def _run_classify(vector):
    from variant_annotator import classify, validate_kb

    kb = validate_kb(vector["input"]["kb"])
    out = classify(_to_parse_result(vector["input"]["parse"]), kb)
    for rsid, want in vector["expected"].get("records", {}).items():
        rec = next((r for r in out["records"] if r["rsid"] == rsid), None)
        assert rec is not None, f"{vector['id']}: no record for {rsid}"
        _assert_close(rec, want, f"{vector['id']}.{rsid}")
    if "summary" in vector["expected"]:
        _assert_close(out["summary"], vector["expected"]["summary"], f"{vector['id']}.summary")


def _run_apoe(vector):
    from variant_annotator import resolve_apoe

    kb = SimpleNamespace(genes=vector["input"]["kb"]["genes"], loci=vector["input"]["kb"]["loci"])
    rec = resolve_apoe(copy.deepcopy(vector["input"]["components"]), kb)
    expected = dict(vector["expected"])
    caveats = expected.pop("caveats_include", [])
    _assert_close(rec, expected, vector["id"])
    for want in caveats:
        assert want in rec["interpretation"]["caveats"], f"{vector['id']}: missing caveat {want!r}"


def _run_inheritance(vector):
    import segregation_engine as seg

    inp = vector["input"]
    fn = inp["fn"]
    if fn == "scenario":
        dist = seg.offspring_distribution(inp["altCount"], inp["partner"], inp.get("af"))
        result = {"dist": dist, "outcome": seg.gene_outcome(inp["gene"], dist, inp["allele"])}
    elif fn == "status":
        result = {"status": seg.patient_status(inp["gene"], inp["altCount"])}
    elif fn == "multi_locus":
        result = {"findings": seg.detect_multi_locus(inp["records"], inp["genes"])}
    elif fn == "compound":
        result = {"findings": seg.detect_compound_heterozygosity(inp["records"], inp["genes"])}
    else:
        pytest.fail(f"{vector['id']}: unknown fn {fn}")
    facts = {k: v for k, v in vector["expected"].items() if k not in ("absent", "text_includes", "text_excludes")}
    _assert_close(result, facts, vector["id"])
    _assert_text_and_absent(result, vector["expected"], vector["id"])


AREAS = {
    "parse": _run_parse,
    "alleles": _run_alleles,
    "classify": _run_classify,
    "apoe": _run_apoe,
    "inheritance": _run_inheritance,
}


def _cases():
    for path in sorted(VECTOR_DIR.glob("*.json")):
        for vector in json.loads(path.read_text(encoding="utf-8")):
            yield pytest.param(path.stem, vector, id=f"{path.name}:{vector['id']}")


def test_vector_directory_is_not_empty():
    assert list(VECTOR_DIR.glob("*.json"))


@pytest.mark.parametrize("area, vector", _cases())
def test_vector(area, vector):
    if area in AREAS:
        AREAS[area](vector)
    else:
        pytest.fail(f"no runner for tests/vectors/{area}.json; add one to tests/test_vectors.py")


def test_an_unknown_vector_area_fails_instead_of_being_skipped():
    with pytest.raises(pytest.fail.Exception, match="no runner for tests/vectors/not_an_area.json"):
        test_vector("not_an_area", {"id": "x"})
