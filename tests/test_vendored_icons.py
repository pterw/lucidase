"""The design system's icons are vendored Lucide SVGs, served same-origin and drawn as CSS masks (`lds-i-<name>`).

A class with no rule, or a rule pointing at a file that was never vendored, draws nothing: the button keeps its
label, but the icon silently disappears. These checks catch both before a browser would.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
STYLES = WEB / "src" / "styles.css"
ICONS = WEB / "src" / "icons"

RULE = re.compile(r'\.lds-i-([a-z0-9-]+)\s*\{\s*--lds-icon:\s*url\("icons/([a-z0-9-]+)\.svg"\)')
USE = re.compile(r"\blds-i-([a-z0-9-]+)")


def _rules():
    return dict(RULE.findall(STYLES.read_text(encoding="utf-8")))


def test_every_icon_rule_points_at_a_vendored_svg_of_the_same_name():
    rules = _rules()
    assert rules, "no lds-i-* rules found in styles.css"
    for name, file in rules.items():
        assert name == file, f"lds-i-{name} points at icons/{file}.svg"
        assert (ICONS / f"{file}.svg").is_file(), f"icons/{file}.svg is not vendored"


def test_every_icon_class_used_by_the_pages_has_a_rule():
    rules = _rules()
    sources = [*WEB.glob("*.html"), *(p for p in (WEB / "src").rglob("*.js") if "vendor" not in p.parts)]
    used = {name for path in sources for name in USE.findall(path.read_text(encoding="utf-8"))}
    assert used, "no lds-i-* classes found in the pages"
    missing = sorted(used - set(rules))
    assert not missing, f"icon classes with no rule in styles.css: {missing}"


def test_every_vendored_svg_has_a_rule():
    rules = set(_rules().values())
    unused = sorted(p.stem for p in ICONS.glob("*.svg") if p.stem not in rules)
    assert not unused, f"vendored icons with no lds-i-* rule: {unused}"


def test_every_vendored_icon_is_drawn_by_a_page():
    """An icon whose class no page or script uses is dead weight: its rule and SVG ship but nothing draws it.

    The class must appear in web/ outside styles.css (where it is only defined), so removing the last use of an
    icon fails here until the icon and its rule go too.
    """
    sources = [*WEB.glob("*.html"), *(p for p in (WEB / "src").rglob("*.js") if "vendor" not in p.parts)]
    used = {name for path in sources for name in USE.findall(path.read_text(encoding="utf-8"))}
    unused = sorted(set(_rules()) - used)
    assert not unused, f"icons vendored but never drawn: {unused}"
