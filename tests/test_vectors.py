"""Runner for the shared vectors (contracts C6): every tests/vectors/*.json file.

Vector: { id, description, input, expected }. `expected` holds genetics or format
facts, compared as a SUBSET of the real output (same semantics as
web/tests/vectors.test.mjs):
  - plain keys (format, build, assay, stats, ...): objects recursively, scalars and
    lists by deep equality;
  - `calls`: the exact call list;  `calls_include`: calls that must be present;
  - `error`: the parser must raise an error whose class name equals it.

A vector file whose area has no entry in AREAS fails, so a new area cannot be
silently ignored. Areas still waiting for a Python implementation are listed in
PENDING_T10 and skipped.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

VECTOR_DIR = Path(__file__).parent / "vectors"
PENDING_T10 = {"alleles", "classify", "apoe", "inheritance"}


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


AREAS = {"parse": _run_parse}


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
    elif area in PENDING_T10:
        pytest.skip("pending T10")
    else:
        pytest.fail(f"no runner for tests/vectors/{area}.json; add one to tests/test_vectors.py")
