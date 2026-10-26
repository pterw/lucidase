"""tools/precommit_scope.py: which test files a set of staged paths selects.

Every test builds a throwaway tree under ``tmp_path`` and never touches the
repository. ``main`` is driven with a fake runner, except for the exit-code
test, which runs a real pytest in the temporary tree.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "precommit_scope.py"
_spec = importlib.util.spec_from_file_location("precommit_scope", MODULE_PATH)
precommit_scope = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(precommit_scope)


def write(root: Path, relative: str, text: str = "") -> None:
    """Create ``root/relative`` (and its parents) with ``text``."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_staged_unit_test_selects_itself(tmp_path):
    """A staged tests/test_*.py selects exactly that file."""
    write(tmp_path, "tests/test_a.py", "def test_a(): pass\n")
    write(tmp_path, "tests/test_b.py", "def test_b(): pass\n")
    assert precommit_scope.select_tests(tmp_path, ["tests/test_a.py"]) == [
        "tests/test_a.py"
    ]


IMPORT_FORMS = {
    "plain": "import foo\n",
    "from_stem": "from foo import x\n",
    "from_tools_dot": "from tools.foo import x\n",
    "from_tools_import": "from tools import foo\n",
    "from_tools_list": "from tools import bar, foo\n",
    "names_file": "PATH = 'tools/foo.py'\n",
}
LOOKALIKES = {
    "test_lookalike_import.py": "from tools.foobar import y\nimport foobar\n",
    "test_lookalike_word.py": "# only mentions foobar\n",
}


@pytest.mark.parametrize("staged", ["tools/foo.py", "tools\\foo.py"])
@pytest.mark.parametrize("form", IMPORT_FORMS)
def test_staged_module_selects_each_import_form(tmp_path, form, staged):
    """tools/foo.py selects a test using this import form, and only that one.

    Every other form and the foobar lookalikes sit in the same tree, so a rule
    that stops matching its own form (or matches a lookalike) fails here. The
    backslash spelling of the staged path must select the same file.
    """
    write(tmp_path, "tools/foo.py", "x = 1\n")
    for name, text in IMPORT_FORMS.items():
        write(tmp_path, f"tests/test_{name}.py", text if name == form else "# n/a\n")
    for name, text in LOOKALIKES.items():
        write(tmp_path, f"tests/{name}", text)
    assert precommit_scope.select_tests(tmp_path, [staged]) == [f"tests/test_{form}.py"]


def test_test_file_with_byte_order_mark_is_matched(tmp_path):
    """A BOM before the import on line 1 does not hide the import."""
    write(tmp_path, "tools/foo.py", "x = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_bom.py").write_bytes(b"\xef\xbb\xbfimport foo\n")
    assert precommit_scope.select_tests(tmp_path, ["tools/foo.py"]) == [
        "tests/test_bom.py"
    ]


@pytest.mark.parametrize("helper", ["tests/conftest.py", "tests/helpers.py"])
def test_staged_shared_test_helper_selects_every_unit_test(tmp_path, helper):
    """conftest.py or a helper under tests/ can change all tests, so all run."""
    write(tmp_path, helper, "x = 1\n")
    write(tmp_path, "tests/test_a.py", "def test_a(): pass\n")
    write(tmp_path, "tests/test_b.py", "def test_b(): pass\n")
    write(tmp_path, "tests/e2e/test_page.py", "def test_p(): pass\n")
    assert precommit_scope.select_tests(tmp_path, [helper]) == [
        "tests/test_a.py",
        "tests/test_b.py",
    ]


def test_file_name_match_is_a_substring_match(tmp_path):
    """app.js also selects a test naming webapp.js: over-selecting is safe."""
    write(tmp_path, "web/app.js", "")
    write(tmp_path, "tests/test_web.py", "PATH = 'web/webapp.js'\n")
    assert precommit_scope.select_tests(tmp_path, ["web/app.js"]) == [
        "tests/test_web.py"
    ]


def test_staged_asset_selects_test_naming_its_file(tmp_path):
    """web/src/app.js selects a test whose text contains app.js."""
    write(tmp_path, "web/src/app.js", "")
    write(tmp_path, "tests/test_app.py", "PATH = 'web/src/app.js'\n")
    write(tmp_path, "tests/test_other.py", "PATH = 'web/src/other.js'\n")
    assert precommit_scope.select_tests(tmp_path, ["web/src/app.js"]) == [
        "tests/test_app.py"
    ]


def test_e2e_and_unreferenced_docs_select_nothing_and_skip_runner(tmp_path):
    """e2e files and an unreferenced doc select nothing; main never runs pytest."""
    write(tmp_path, "tests/e2e/test_page.py", "def test_p(): pass\n")
    write(tmp_path, "docs/x.md", "")
    write(tmp_path, "tests/test_a.py", "# runs tests/e2e/test_page.py\n")
    staged = ["tests/e2e/test_page.py", "docs/x.md"]
    assert precommit_scope.select_tests(tmp_path, staged) == []

    calls = []
    code = precommit_scope.main(
        staged, runner=lambda argv: calls.append(argv) or 1, root=tmp_path
    )
    assert code == 0
    assert calls == []


def test_main_passes_selection_to_pytest_and_returns_runner_code(tmp_path):
    """main hands the selected files to the runner and returns its exit code."""
    write(tmp_path, "tests/test_a.py", "def test_a(): pass\n")
    calls = []
    code = precommit_scope.main(
        ["tests/test_a.py"], runner=lambda argv: calls.append(argv) or 7, root=tmp_path
    )
    assert code == 7
    assert calls == [
        ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_a.py"]
    ]


def _real_runner(cwd: Path):
    """A runner that really starts pytest (this interpreter) inside ``cwd``."""

    def run(argv):
        return subprocess.call([sys.executable, *argv[1:]], cwd=cwd, timeout=120)

    return run


def test_failing_selected_test_gives_nonzero_exit(tmp_path):
    """A failing selected test file makes main fail; a passing one gives 0."""
    write(tmp_path, "tests/test_bad.py", "def test_bad():\n    assert False\n")
    write(tmp_path, "tests/test_good.py", "def test_good():\n    assert True\n")
    runner = _real_runner(tmp_path)
    assert precommit_scope.main(["tests/test_bad.py"], runner=runner, root=tmp_path) != 0
    assert precommit_scope.main(["tests/test_good.py"], runner=runner, root=tmp_path) == 0


def test_missing_staged_path_selects_nothing(tmp_path):
    """A staged path that does not exist is ignored, not an error."""
    write(tmp_path, "tests/test_a.py", "x = 'gone.py'\n")
    assert precommit_scope.select_tests(tmp_path, ["tools/gone.py", "nope.js"]) == []
