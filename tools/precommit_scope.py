"""Run only the unit tests that the staged files can affect (pre-commit helper).

Usage: ``python tools/precommit_scope.py <staged file>...``. The exit code is
the exit code of the pytest run it starts, or 0 when no test is selected.

Selection rules, applied to each staged path that exists (tests/e2e/ is never
selected, those tests need a browser and run in their own gate):

* a staged ``tests/test_*.py`` selects itself;
* any other staged ``tests/*.py`` (``tests/conftest.py``, a shared helper)
  selects every ``tests/test_*.py``, because it can change all of them;
* any other ``*.py`` selects every ``tests/test_*.py`` whose text imports it
  (``import <stem>``, ``from <stem> import``, ``from tools.<stem> import``,
  ``from tools import <stem>`` or ``from tools import a, <stem>`` on one line)
  or names its file (``<stem>.py``);
* any other file selects every ``tests/test_*.py`` whose text contains its
  file name with extension (for example ``app.js``). The file-name match is a
  substring match on purpose: ``app.js`` also selects a test that names
  ``webapp.js``. Over-selecting is the safe side of a silent miss.

Backslash separators in staged paths are accepted. Known gaps: the matching is
textual, so a multi-line ``from tools import (a, b)`` and a relative import
are not matched; a module reached only through another module (``bio_engine``
imported by a test via ``gui``) selects nothing, since CI runs the full suite;
absolute staged paths are not supported, pre-commit passes relative ones.

An empty selection never reaches pytest: a bare ``pytest`` with no file
arguments runs the whole suite, which is the opposite of what a scoped
pre-commit hook is for.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _is_unit_test(relative: str) -> bool:
    """True for ``tests/test_*.py`` directly under tests/ (not tests/e2e/)."""
    path = Path(relative)
    return path.parent.as_posix() == "tests" and re.fullmatch(r"test_.*\.py", path.name)


def _mentions(text: str, path: Path) -> bool:
    """Whether a test's ``text`` refers to the staged ``path``."""
    if path.suffix != ".py":
        return path.name in text
    stem = re.escape(path.stem)
    imports = (
        rf"^\s*(import {stem}\b|from {stem} import\b"
        rf"|from tools\.{stem} import\b|from tools import [^#\n(]*\b{stem}\b"
        rf"|from debruijn\.{stem} import\b|from debruijn import [^#\n(]*\b{stem}\b|import debruijn\.{stem}\b)"
    )
    return bool(re.search(imports, text, re.MULTILINE)) or path.name in text


def select_tests(root: Path, staged: list[str]) -> list[str]:
    """Return the sorted, duplicate-free unit test files the staged paths select.

    Paths are repository-relative and posix-style. Staged paths that do not
    exist under ``root`` and anything under ``tests/e2e/`` select nothing.
    """
    texts = {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8-sig", errors="replace")
        for p in (root / "tests").glob("test_*.py")
    }
    selected: set[str] = set()
    for relative in staged:
        path = Path(relative.replace("\\", "/"))
        if not (root / path).is_file() or path.parts[:2] == ("tests", "e2e"):
            continue
        if _is_unit_test(path.as_posix()):
            selected.add(path.as_posix())
        elif path.parent.as_posix() == "tests" and path.suffix == ".py":
            selected.update(texts)
        else:
            selected.update(name for name, text in texts.items() if _mentions(text, path))
    return sorted(selected)


def main(
    argv: list[str], *, runner=subprocess.call, root: Path | None = None
) -> int:
    """Run pytest on the tests selected for ``argv`` and return its exit code.

    ``runner`` receives the pytest argument list and returns an exit code. With
    nothing selected it prints one line and returns 0 without calling it.
    """
    selected = select_tests(root or REPO_ROOT, argv)
    if not selected:
        print("precommit_scope: no unit tests selected for the staged files.")
        return 0
    return runner(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", *selected])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
