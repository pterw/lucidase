"""Fail if web/src/vendor/tailwind.css is stale relative to its sources.

Recompiles to a temp file with the documented command and compares bytes with
the committed CSS. Writes nothing inside the repo. The CLI is found via the
TAILWIND_CLI environment variable, else bin/tailwindcss.exe, else bin/tailwindcss.
Run `python tools/check_vendored_css.py`; exit 0 = fresh, 1 = stale or error.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

INSTALL_HINT = (
    "Download the Tailwind standalone CLI v3.4.17 "
    "(https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17) "
    "to bin/tailwindcss.exe (or bin/tailwindcss), or set TAILWIND_CLI."
)


def find_cli(root: Path) -> Path | None:
    override = os.environ.get("TAILWIND_CLI")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    for name in ("tailwindcss.exe", "tailwindcss"):
        candidate = root / "bin" / name
        if candidate.is_file():
            return candidate
    return None


def check(root: Path) -> int:
    cli = find_cli(root)
    if cli is None:
        print(f"ERROR: Tailwind CLI not found. {INSTALL_HINT}", file=sys.stderr)
        return 1
    committed = root / "web" / "src" / "vendor" / "tailwind.css"
    if not committed.is_file():
        print(f"ERROR: {committed} is missing. Regenerate it (see web/src/vendor/README.md).", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tailwind.css"
        cmd = [
            str(cli), "-c", "web/tailwind.config.js", "-i", "web/src/tailwind.input.css",
            "-o", str(out), "--minify",
        ]
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        if result.returncode != 0 or not out.is_file():
            print(f"ERROR: Tailwind compile failed:\n{result.stderr}", file=sys.stderr)
            return 1
        fresh = out.read_bytes()
    # Compare modulo line endings: git may check the file out with CRLF.
    def normalise(data: bytes) -> bytes:
        return data.replace(bytes([13, 10]), bytes([10]))

    if normalise(fresh) != normalise(committed.read_bytes()):
        print(
            "ERROR: web/src/vendor/tailwind.css is stale. Regenerate it:\n"
            "  bin/tailwindcss.exe -c web/tailwind.config.js -i web/src/tailwind.input.css "
            "-o web/src/vendor/tailwind.css --minify",
            file=sys.stderr,
        )
        return 1
    print("web/src/vendor/tailwind.css is up to date.")
    return 0


def main() -> int:
    return check(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    sys.exit(main())
