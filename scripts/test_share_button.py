#!/usr/bin/env python3
"""test_share_button.py - every article must carry a working one-click copy button.

The share button is the owner's feature (2026-10-29): one click on any story copies the whole thing -
headline, deck, body, why-it-matters, aside, source name + link - as plain text, plus the article's
own URL. It is not "share to social"; it is "give me the whole story to paste into a chat".

Two failure modes this pins:
  1. the builder stops emitting the button on some section kind (a silent regression),
  2. the button is emitted but the composer loses the inline script, so the click does nothing.

    python scripts/test_share_button.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / "scripts" / "build_edition.py"
CSS = ROOT / "site" / "style.css"
APP = ROOT / "site" / "app.js"


def main() -> int:
    fails: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("builder emits the button:")
    src = BUILDER.read_text(encoding="utf-8")
    check('class="share"' in src, "source line carries button.share")
    check('aria-label="Copy this story as text"' in src, "button has an accessible label")
    check('type="button"' in src, "button is type=button (never submits)")
    check("SHARE_JS" in src, "composer is defined in the builder")
    check("<script>{SHARE_JS}</script>" in src, "composer is inlined into every document")

    print("composer copies the whole story:")
    for fragment, label in [
        (".story__headline, .lead__headline", "reads the headline"),
        (".standfirst", "reads the standfirst"),
        ('querySelector(".body")', "reads the body"),
        (".whymatters", "reads why-it-matters"),
        ('querySelector(".source")', "reads the source link"),
        ("navigator.clipboard", "uses the async clipboard"),
        ("execCommand", "has a legacy fallback"),
        ("location.origin + location.pathname", "appends a canonical article URL"),
    ]:
        check(fragment in src, label)

    print("it cannot break the page:")
    check("fetch(" not in src.split("SHARE_JS")[1].split('"""')[1], "composer performs no fetch")
    check(APP.exists() and len(APP.read_text(encoding="utf-8").splitlines()) <= 160,
          "app.js still inside its 160-line contract budget")

    print("styling and print:")
    css = CSS.read_text(encoding="utf-8")
    check(".share {" in css, "share has styles")
    check("min-height: 44px" in css, "tap target is at least 44px")
    # brace-aware: the print block contains nested rules, so a [^}] regex cannot see past them
    start = css.find("@media print")
    depth, end = 0, -1
    for i in range(start, len(css)) if start != -1 else []:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    print_block = css[start:end] if start != -1 and end != -1 else ""
    check(".share" in print_block, "share is hidden in print")

    total = 18
    if fails:
        print("\nSHARE BUTTON FAIL: %d of %d" % (len(fails), total))
        for f in fails:
            print("  -", f)
        return 1
    print("\nSHARE BUTTON PASS: %d/%d" % (total, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())