#!/usr/bin/env python3
"""Pin the taste contract.

`config/interests.md` is the file that decides what the 03:00 edition may publish, and until now nothing
tested it: doctor only checked that it existed and had a plausible size. A taste edit could quietly delete
a NEVER entry or let CHANNEL POLICY stop outranking LOVES and no test would notice.

This asserts the things that must never silently disappear. It is deliberately about PRESENCE, not wording -
prose may be rewritten, rules may not be dropped.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERESTS = ROOT / "config" / "interests.md"

fails = []


def check(label, condition, detail=""):
    if condition:
        print("  ok   " + label)
    else:
        fails.append(label)
        print("  FAIL " + label + ((" - " + detail) if detail else ""))


text = INTERESTS.read_text(encoding="utf-8")

# Scope the NEVER checks to the NEVER section, not the whole file: several rules are also referenced
# from the lanes above (e.g. "no cruelty" appears in the YouTube-drama bullet too), so a whole-file
# search would pass even after the actual NEVER entry was deleted. Proven by deleting it and watching
# this version fail where the loose one passed.
def section_of(name: str, body: str) -> str:
    start = body.find(name)
    if start < 0:
        return ""
    nxt = body.find("\n## ", start + len(name))
    return body[start:] if nxt < 0 else body[start:nxt]


NEVER_TEXT = section_of("## NEVER", text)
DISLIKE_TEXT = section_of("## DISLIKES", text)

# --- section structure -------------------------------------------------------------------------
sections = ["## LOVES", "## LIKES", "## NEUTRAL", "## DISLIKES", "## NEVER",
            "## SCORING RUBRIC", "## TONE RULES", "## COOLDOWN", "## WHAT THE EDITION IS NOT"]
for name in sections:
    check("section present: " + name, text.count(name) == 1, "count=%d" % text.count(name))

check("CHANNEL POLICY section present", "## CHANNEL POLICY" in text)

# --- CHANNEL POLICY must still outrank LOVES ---------------------------------------------------
check("CHANNEL POLICY declares it outranks LOVES",
      re.search(r"CHANNEL POLICY.*OUTRANKS", text, re.I | re.S) is not None)
check("disabled-channel rule survives", "disabled" in text.lower())

# --- the hard NEVER rules, each one still in the file ------------------------------------------
check("NEVER section is non-trivial", len(NEVER_TEXT) > 600, "len=%d" % len(NEVER_TEXT))

NEVER_RULES = {
    "no invented facts": r"invent a story",
    "no political outrage bait": r"outrage bait",
    "no cruelty / humiliation": r"cruelty",
    "no spoilers for active games": r"spoiler",
    "no doom framing": r"doom framing",
    "no loot-box / gacha promotion": r"gacha",
    "no uncredited images": r"uncredited",
    "no 3-hour VOD as lead": r"3-hour VOD",
}
for label, pattern in NEVER_RULES.items():
    check("NEVER survives: " + label, re.search(pattern, NEVER_TEXT, re.I) is not None)

# --- the anti-interest the owner stated explicitly ---------------------------------------------
check("RuneScape anti-interest present in NEVER", "RuneScape" in NEVER_TEXT)
check("RuneScape exception is scoped, not absolute",
      re.search(r"exception", NEVER_TEXT, re.I) is not None)

# --- the lanes added 2026-10-28 ----------------------------------------------------------------
for lane, pattern in {
    "anime lane": r"anime",
    "anime.json is cited as the authority": r"anime\.json",
    "Godot lane": r"Godot",
    "Godot plain-language rule": r"layman|plain",
    "YouTube drama lane": r"YouTube drama",
    "indie breakout lane": r"indie",
    "actively-played lane": r"actively-played|active games",
}.items():
    check("lane present: " + lane, re.search(pattern, text, re.I) is not None)

check("anime is NOT still listed as NEUTRAL",
      re.search(r"\*\*Anime[^\n]*NEUTRAL", text, re.I) is None)

# --- rubric integrity --------------------------------------------------------------------------
check("rubric still scores 0-100", "0-100" in text)
for component in ("T", "F", "N", "V", "M"):
    check("rubric component present: " + component,
          re.search(r"\|\s*\*\*%s" % component, text) is not None)
check("penalty -45 still defined", "-45" in text)
check("cooldown is 21 days", "21 day" in text.lower() or "21-day" in text.lower())

# --- tone rules the validator and the owner care about -----------------------------------------
for rule, pattern in {
    "one em dash per paragraph": r"em dash",
    "no exclamation marks in body": r"exclamation",
    "sentence-case headlines": r"sentence case|sentence-case",
    "standfirst is one sentence": r"standfirst",
}.items():
    check("tone rule survives: " + rule, re.search(pattern, text, re.I) is not None)

# --- self-contained writing rule (owner 2026-10-28: never force a click for the news) ---------
SELF_TEXT = section_of("## SELF-CONTAINED WRITING", text)
check("SELF-CONTAINED WRITING section present", len(SELF_TEXT.strip()) > 200, "len=%d" % len(SELF_TEXT))
for rule, pattern in {
    "states the page must never force a click": r"never force a click",
    "source link is provenance, not homework": r"provenance",
    "creator take summarised in prose": r"in their voice|the take|summarise",
    "banned pointer phrasings listed": r"watch the full video",
    "delete-the-link test stated": r"delete the source link",
}.items():
    check("self-contained rule: " + rule, re.search(pattern, SELF_TEXT, re.I) is not None)

# --- owner's 2026-10-30 feedback: plain English, context, and three taste bans -----------------
PLAIN_TEXT = section_of("## PLAIN ENGLISH", text)
check("PLAIN ENGLISH section present", len(PLAIN_TEXT.strip()) > 400, "len=%d" % len(PLAIN_TEXT))
for rule, pattern in {
    "states advanced vocabulary is banned": r"advanced vocabulary|complex words",
    "quotes are the exception and get explained": r"quote",
    "jargon-explained-in-the-same-breath rule": r"jargon",
    "15-year-old vocabulary test": r"15-year-old",
}.items():
    check("plain English rule: " + rule, re.search(pattern, PLAIN_TEXT, re.I) is not None)

TONE_TEXT = section_of("## TONE RULES", text)
for rule, pattern in {
    "headline must work with no prior knowledge": r"no prior knowledge",
    "wire phrasing banned in headlines": r"wire|press release",
    "headline is a reason to read, not a label": r"reason to (keep )?read|fun",
}.items():
    check("headline rule: " + rule, re.search(pattern, TONE_TEXT, re.I) is not None)

for rule, pattern in {
    "assume he knows nothing": r"knows nothing|assume",
    "one clause saying what the company/game/person is": r"company, game or person|what is this thing|appositive",
    "length is never the problem": r"length is never the problem|large text blocks",
}.items():
    check("context rule: " + rule, re.search(pattern, SELF_TEXT, re.I) is not None)

for ban, pattern in {
    "one layoff story per edition": r"one layoff story\s+per edition",
    "world of warcraft updates are out": r"world of warcraft",
    "art-craft video essays are out": r"art-craft|art craft",
}.items():
    check("taste ban present: " + ban, re.search(pattern, DISLIKE_TEXT, re.I) is not None)

check("quickHits is not the bin",
      re.search(r"quickHits`? is not the bin", text, re.I) is not None)

total = len(sections) + 3 + len(NEVER_RULES) + 2 + 7 + 8 + 4 + 6 + 4 + 3 + 3 + 3 + 1
if fails:
    print("\nTASTE CONTRACT FAIL: %d of %d" % (len(fails), total))
    sys.exit(1)
print("\nTASTE CONTRACT PASS: %d/%d" % (total, total))
