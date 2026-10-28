#!/usr/bin/env python3
"""Pin the business-event detector.

The 2026-10-28 edition shipped a Dunkey bag-of-chips video while the packet held "EA CLOSES BIOWARE"
from AngryJoeShow. The runbook already said to look for closures; prose did not survive a 03:00 run.
This test exists so the mechanical replacement cannot silently regress - especially the one real
headline that started it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_daily as rd  # noqa: E402

POSITIVE = [
    ("AJSN WK44A- Star Wars BATTLEFRONT 3?!, EA CLOSES BIOWARE & MASS EFFECT, Clayface BOX", "the real miss"),
    ("EA shuts down BioWare after Mass Effect flop", "plain closure"),
    ("Studio closure confirmed after 12 years", "closure noun"),
    ("Embracer lays off 200 staff across three studios", "layoffs"),
    ("Sony acquires Kadokawa", "acquisition"),
    ("Ubisoft delists three classic titles from Steam", "delisting"),
    ("Blizzard cancels its survival game", "cancellation"),
    ("Studio files for bankruptcy", "insolvency"),
    ("BioWare reportedly shuts down two studios", "reported closure is still a closure"),
    ("Publisher closes its doors after 20 years", "closes its doors"),
]

NEGATIVE = [
    ("Rockstar's UK staff will vote on a union", "labour action, not a closure"),
    ("GTA 6 is 210GB on PS5", "a download size"),
    ("Warhorse Studios hit by a serious cyberattack", "incident, not a business change"),
    ("BioWare delays Mass Effect 5", "a delay is not in the class"),
    ("Rumour: studio may shut down, reportedly", "outright rumour"),
    ("Dunkey spent a Call of Duty 24 match narrating a bag of chips", "the item that displaced BioWare"),
    ("Dandadan 2nd Season finale date announced", "anime scheduling"),
    ("The shop closes at five on Sundays", "lowercase object is not a company"),
    ("Our review of the new Helldivers 2 warbond", "routine content news"),
]

fails = 0
for title, why in POSITIVE:
    got = rd.business_event({"title": title})
    if got is not True:
        fails += 1
        print(f"  FAIL expected FLAG  ({why}): {title}")
    else:
        print(f"  ok   flag           ({why})")
for title, why in NEGATIVE:
    got = rd.business_event({"title": title})
    if got is not False:
        fails += 1
        print(f"  FAIL expected SKIP  ({why}): {title}")
    else:
        print(f"  ok   skip           ({why})")

total = len(POSITIVE) + len(NEGATIVE)
if fails:
    print(f"\nBUSINESS EVENT FAIL: {fails} of {total}")
    sys.exit(1)
print(f"\nBUSINESS EVENT PASS: {total}/{total}")
