"""tools/check_vendored_css.py: stale, fresh and missing-CLI behaviour."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "check_vendored_css.py"

FAKE_COMPILER = """
import sys
out = sys.argv[sys.argv.index("-o") + 1]
open(out, "w", encoding="utf-8").write(".compiled{color:red}")
"""


def _fake_cli(tmp_path: Path) -> Path:
    script = tmp_path / "fake_tailwind.py"
    script.write_text(FAKE_COMPILER, encoding="utf-8")
    if os.name == "nt":
        cli = tmp_path / "fake-tailwind.cmd"
        cli.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        cli = tmp_path / "fake-tailwind"
        cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    return cli


def _repo(tmp_path: Path, committed: str) -> Path:
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    (root / "web" / "src" / "vendor").mkdir(parents=True)
    (root / "tools" / "check_vendored_css.py").write_text(TOOL.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "web" / "src" / "vendor" / "tailwind.css").write_text(committed, encoding="utf-8")
    return root


def _run(root: Path, cli: Path | None):
    env = {k: v for k, v in os.environ.items() if k != "TAILWIND_CLI"}
    if cli is not None:
        env["TAILWIND_CLI"] = str(cli)
    return subprocess.run(
        [sys.executable, str(root / "tools" / "check_vendored_css.py")],
        capture_output=True, text=True, env=env,
    )


def test_fresh_css_passes(tmp_path):
    root = _repo(tmp_path, ".compiled{color:red}")
    result = _run(root, _fake_cli(tmp_path))
    assert result.returncode == 0, result.stderr


def test_stale_css_fails_with_regenerate_hint(tmp_path):
    root = _repo(tmp_path, ".old{color:blue}")
    result = _run(root, _fake_cli(tmp_path))
    assert result.returncode == 1
    assert "stale" in result.stderr and "tailwind.css" in result.stderr


def test_missing_cli_fails_fast_with_install_hint(tmp_path):
    root = _repo(tmp_path, ".compiled{color:red}")
    result = _run(root, tmp_path / "does-not-exist")
    assert result.returncode == 1
    assert "Tailwind CLI not found" in result.stderr


def test_missing_cli_without_override_or_bin(tmp_path):
    root = _repo(tmp_path, ".compiled{color:red}")
    result = _run(root, None)
    assert result.returncode == 1
    assert "Tailwind CLI not found" in result.stderr


def test_check_writes_nothing_in_repo(tmp_path):
    root = _repo(tmp_path, ".old{color:blue}")
    before = sorted(p.relative_to(root) for p in root.rglob("*") if "__pycache__" not in p.parts)
    _run(root, _fake_cli(tmp_path))
    after = sorted(p.relative_to(root) for p in root.rglob("*") if "__pycache__" not in p.parts)
    assert before == after


def test_real_repo_css_is_fresh():
    repo = TOOL.parents[1]
    if not any((repo / "bin" / n).is_file() for n in ("tailwindcss.exe", "tailwindcss")) and not os.environ.get("TAILWIND_CLI"):
        pytest.skip("Tailwind CLI not installed")
    result = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
