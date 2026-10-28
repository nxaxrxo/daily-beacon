#!/usr/bin/env python3
"""test_channel_policy.py - the owner's brief, encoded as tests.

The 03:00 run must never publish a gameplay upload or a video from a disabled channel. Both
were once only enforced by the agent's judgement, which meant one bad night shipped a
15.7-hour "FULL GAME" stream into the candidates. These tests make the rules mechanical.

    python scripts/test_channel_policy.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    yt = load("yt_source")
    fails = []

    def check(cond, label):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("gameplay filter - must DROP raw footage:")
    for title, length in [
        ("Castlevania Belmonts Curse True Ending (FULL GAME)", 56762),
        ("Some Game - Part 3", 3000),
        ("Full playthrough no commentary", 9000),
        ("Asmongold plays it again live stream", 4000),
    ]:
        check(yt.looks_like_gameplay(title, length), title[:56])

    print("gameplay filter - must KEEP takes, reviews and reveals:")
    for title, length in [
        ("Castlevania Belmonts Curse Review", 900),
        ("Bleach Anime Just Ended After Two Decades", 1200),
        ("Gameplay Trailer - New RPG", 120),
        ("Official Gameplay Reveal: Phantom Blade Zero", 180),
        ("Launch date announced for Where Winds Meet", 300),
        ("WHY GAMES COST 80 DOLLARS NOW", 1500),
        ("Where Winds Meet review after 100 hours", 1800),
    ]:
        check(not yt.looks_like_gameplay(title, length), title[:56])

    print("channel config - the brief is actually enforced:")
    data = json.loads((ROOT / "config" / "channels.json").read_text(encoding="utf-8-sig"))
    rows = data if isinstance(data, list) else data["channels"]
    enabled = [c for c in rows if c.get("enabled")]
    check(len(enabled) == 48, f"48 channels enabled (got {len(enabled)})")
    disabled = [c for c in rows if not c.get("enabled")]
    check(all(c.get("note") for c in disabled), "every disabled channel says why")
    banned = {"MrBeast", "JT Music", "Teminite", "Asmongold Clips", "Viva La Dirt League"}
    names = {c["name"] for c in enabled}
    leaked = banned & names
    check(not leaked, "entertainment/music/clip channels stay off: " + (", ".join(sorted(leaked)) or "none on"))

    print("settings - the window matches the 48h cadence:")
    st = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8-sig"))
    check(st.get("lookback_hours", 0) >= 48, f"lookback >= 48h (got {st.get('lookback_hours')})")
    check(yt.DEFAULT_HOURS >= 48, f"yt_source fallback >= 48h (got {yt.DEFAULT_HOURS})")

    print()
    if fails:
        print(f"FAILED {len(fails)} check(s)")
        return 1
    print("CHANNEL POLICY PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
