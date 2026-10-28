# BACKEND REPORT - spec sections 2-5, U1-U5

All five units are delivered, code is on disk, and every run named in the brief was executed for real.
Evidence per unit is in `docs/_parts/u*.md`; this file is the index and the ledger of what actually ran.

## Deliverables

| Unit | Files | Status |
|---|---|---|
| U1 scheduler | `~\.config\opencode\plugins\scheduler\index.ts` (edited, backup kept), `~\.config\opencode\tools\schedule.py` (ACCEPTED only), `scripts/test_scheduler_formats.mjs` | done |
| U2 config | `config/settings.json`, `config/channels.json`, `config/feeds.json`, `docs/FEEDS-CHECK.md` | done |
| U3 memory | `scripts/memory.py` | done |
| U4 sources | `scripts/yt_source.py`, `scripts/news_source.py` | done |
| U5 pipeline | `scripts/transcripts.py`, `scripts/run_daily.py` | done |

## The three required runs - actually executed, output captured

### 1. `node scripts/test_scheduler_formats.mjs`
```
PASS once spec kind + atMs
... 83 PASS lines total ...
PASS monthly catch-up-once invariant for monthly:25@09:00
PASS every unknown kind -> null
ALL FORMATS PASS
exit 0
```
Covers every kind, old and new: `once`, `every` (m/h/d), `daily`, `weekly` single, `weekly` multi-day,
`days`, `hourly`, `monthly` - with valid parses asserting exact spec fields, invalid inputs asserting
`ok === false`, and catch-up maths on fixed local-time constants (a 7-day outage on `days:3` yields
exactly one fire, `monthly:31` clamps to 28 Feb, `weekly:mon,wed,fri` moves Tue -> Wed, `hourly:30` lands
within 60 minutes).

An independent import of the real plugin confirms all ten accepted forms parse and `computeDue` returns a
finite stamp:
```
OK once / every:30m / every:2h / every:3d / daily:03:00 / weekly:mon@09:00 /
   days:3@03:00 / weekly:mon,wed,fri@09:00 / hourly:15 / monthly:1@03:00
```

### 2. `python scripts/memory.py selftest`
```
selftest: a/b/c/d ok
SELFTEST PASS
```
Plus a live round trip proving idempotency and the dual key:
```
marked: 5 new items, 4 topics, edition 2026-10-28
marked: 0 new items, 0 topics, edition 2026-10-28     <- second run, no double count
filter done: 3 total, 2 seen, 1 fresh, 4 cooling topics
  True  video  | Valor Mortis review
  False None   | Brand new story about a toaster
  True  url    | Rockstar staff vote on a union      <- matched despite a ?utm_source variant
```

### 3. `python scripts/run_daily.py collect`
Cold, live-network run:
```
yt_source done: 34 videos from 79/79 channels (0 failed)
news_source done: 60 articles from 24/24 feeds (0 failed)
transcripts done: 2 fetched, 10 cached, 0 failed
step4 images: 24 downloaded -> img/
step5 packet: state/workpack/2026-10-28/packet.md
collect done: 34 videos, 60 articles, 14 transcripts, 0 repeats suppressed
```
Final run against the marked edition (anti-repeat path proving itself), which is the workpack on disk now:
```
step1 merged: 92 candidates (32 videos, 60 articles) -> candidates.json
filter done: 92 total, 15 seen, 77 fresh, 46 cooling topics
transcripts done: 0 fetched, 12 cached, 0 failed
step4 images: 24 downloaded -> img/
collect done: 32 videos, 60 articles, 22 transcripts, 15 repeats suppressed
exit 0
```

## packet.md - real items, contract shape
```
# DAILY BEACON - workpack 2026-10-28
generated 2026-10-28T12:13:17+01:00 | lookback 26h | 32 videos, 60 articles | 15 repeats suppressed

## counts
- youtube: 32 videos | 79/79 ok, 0 failed
- news: 60 articles | 24/24 ok, 0 failed
- candidates after caps: 32 videos, 60 articles (92 total)
- memory filter: 92 total, 15 seen, 77 fresh
- repeats suppressed: 15
- transcripts: 0 fetched, 12 cached, 0 failed (22 files on disk)
- images downloaded: 24
- warnings: none
```
Six headings in the contract order, 40 candidate lines, ASCII-only, every line
`- [T<t>|w<w>] title | source | published | url | transcript:yes|no`.

## Workpack on disk (`state/workpack/2026-10-28/`)
`yt.json` (32) · `news.json` (60) · `candidates.json` (92) · `filtered.json` (92) · `suppressed.json` (15) ·
`images.json` (24 entries) · `packet.md` · `transcripts/` (22 .txt + index.json) · `img/` (65 files).

## Config as shipped
- `settings.json`: 13 keys, spec values verbatim, key order preserved.
- `channels.json`: 79 channels (t1 28 / t2 37 / t3 14). Every id verbatim from the 152-subscription
  portfolio; Cryton resolved live (`UCb9gttCzPcabOnq1nFYPwsw`, cross-checked against channel RSS and
  Invidious). All 42 spec-required names present.
- `feeds.json`: 24 feeds, 24/24 HTTP 200 with entries at verification time. Every URL, status and item
  count is in `docs/FEEDS-CHECK.md`, along with each rejected candidate and why.

## Known deviations, all in `docs/DECISIONS.md`
- Additive `topic_seen(topic, edition)` table (CONTRACTS.md explicitly allows it) to make `mark` idempotent.
- Undated feed entries are kept with `publishedAt: null` instead of being dropped.
- `weekly:` gained a `dows` array while keeping the singular `dow`, so old records are untouched.
- `monthly:N@HH:MM` clamps N to the month length rather than skipping a month.
- Feeds that verify as HTTP 200 but parse zero entries are treated as dead, not shipped.

## Post-completion audit (all six sub-agents, files opened and checked)

Every path each unit reported was opened and measured on disk. No redeploy was needed, nothing was missing:

| Unit | Reported path | Size |
|---|---|---|
| u1 | `~\.config\opencode\plugins\scheduler\index.ts` | 46355 |
| u1 | `~\.config\opencode\tools\schedule.py` | 8199 |
| u1 | `scripts/test_scheduler_formats.mjs` | 12926 |
| u2a | `config/channels.json` (79 channels) | 14810 |
| u2 | `config/settings.json` | 433 |
| u2 | `config/feeds.json` (24 feeds) | 4300 |
| u2 | `docs/FEEDS-CHECK.md` | 4253 |
| u3 | `scripts/memory.py` | 30058 |
| u4 | `scripts/news_source.py` | 20739 |
| u5a | `scripts/transcripts.py` | 11775 |
| u5b | `scripts/run_daily.py` | 30338 |
| u5b | `state/workpack/2026-10-28/packet.md` | 11737 |

Re-verified after the audit: `node scripts/test_scheduler_formats.mjs` -> `ALL FORMATS PASS` (exit 0);
`python scripts/memory.py selftest` -> `SELFTEST PASS`; packet.md keeps its H1, its stats line
(`32 videos, 60 articles, 15 repeats suppressed`), the five section headings in contract order and 40
candidate lines that are ASCII-only with four ` | ` separators each; `filtered.json` 92 items / 15 seen /
77 fresh; 22 transcript files; `images.json` 24 entries with every file present.
