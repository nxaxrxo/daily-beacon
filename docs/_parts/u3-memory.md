# U3 - memory.py (sqlite anti-repeat store)

`scripts/memory.py`, 761 lines, stdlib only. CLI surface = CONTRACTS.md items 3-8 verbatim.

## Schema
items/topics/editions verbatim from SPEC 4, plus the additive table:

```sql
CREATE TABLE IF NOT EXISTS topic_seen(topic TEXT, edition TEXT, PRIMARY KEY(topic, edition));
```

**Additive-table decision:** `topics.times` must rise +1 per (topic, edition), but the spec row holds only
`times`/`last_covered`, so nothing distinguishes "already counted this edition" from "counted in an earlier
edition". `topic_seen` is that guard: `INSERT OR IGNORE` returning rowcount 0 means already-counted, so the
upsert never runs twice and re-marking leaves `times` byte-identical (SPEC 4 "dedupe on edition date + key"
in data, not in code). Authorised by CONTRACTS.md 115-116; `prune` cleans orphans out of it.
Indexes on items(edition), items(first_seen), topics(last_covered). WAL, busy_timeout 5000,
synchronous NORMAL, version in `PRAGMA user_version` (refuses a newer DB). All connections via a
`@contextmanager db_session()` - commit/rollback/close. Parameterised SQL only.

## Keys + normalisation (module-level, shared by filter AND mark)
- `canonical_url`: lowercase -> drop fragment -> drop `utm_*` and fbclid gclid msclkid ref referrer source mc_cid mc_eid igshid s si feature etc -> sort params -> drop `www.` -> `[^a-z0-9]+`->space -> collapse whitespace. `canonical_title`: lowercase -> punctuation->space -> collapse. `sha16`=sha1[:16].
- video `yt:<videoId>` (field, else parsed from url incl. youtu.be/shorts/embed/live); news `url:<sha16>`
  **and** `title:<sha16>`. filter checks all three; mark writes yt: for video-ish, url:+title: for news.

## Commands
`filter --candidates --out [--suppressed] [--cooldown]` (array or {"items":[...]}) -> exact contract object,
default suppressed `<out dir>/suppressed.json`, exit 0. `mark --edition [--date]` -> `marked: N new items,
N topics, edition <date>`. `query --topic [--days 60]` -> human lines, exit 0 even unknown. `stats` ->
counts + db size bytes + last edition date/path. `prune [--days 400]` -> only rows older than cutoff that no
kept edition references. `selftest` / `--selftest` -> temp db, mark twice, filter, prune guard.
Global: `--root` = `Path(__file__).resolve().parents[1]`, `--db` override, guarded stdout reconfigure,
UTF-8/utf-8-sig opens, ASCII console, one summary line, one-line stderr + exit 1 on real failure.

**topic_hits is report-only:** `seen` is set by yt/url/title keys only; a topic hit never sets it.

## Verification (real output, 2026-10-28, Python 3.11.9)

### 1 `selftest`
```
selftest: a/b/c/d ok
SELFTEST PASS
exit=0
```
(a) empty db sees 0; (b) first mark adds items+topics, second adds 0 with `times` and item count unchanged; (c) seen video -> `video`, seen news -> `url`, exactly 1 fresh; (d) `prune --days 0` deletes 0 referenced items and keeps the edition row.

### 2 `stats` (real DB, no edition built yet)
```
db: C:\Users\MarciNaro\Documents\VSCODE-PROJECTS\daily-beacon\state\seen.sqlite
items: 0    topics: 0    editions: 0
db size: 49152 bytes
last edition: none
exit=0
```

### 3 `query --topic gta6 --days 60`
```
topic 'gta6': never covered
exit=0
```

### 4 mark x2 + filter round trip (throwaway db, fixture edition in %TEMP%\opencode\u3)
```
### 4a mark 1
marked: 5 new items, 3 topics, edition 2026-10-25
### 4b mark 2
marked: 0 new items, 0 topics, edition 2026-10-25
### 4c filter
filter done: 3 total, 2 seen, 1 fresh, 3 cooling topics
  video   | GTA 6 trailer breakdown reaction         | seen=True  | reason=video  | hits=['gta6']
  article | Rockstar delays GTA 6 to who knows when  | seen=True  | reason=url    | hits=['gta6']
  article | Warframe 1999 gets a new frame           | seen=False | reason=None   | hits=['gta6']
  counts: {'total': 3, 'seen': 2, 'fresh': 1}
  recent_topics: [('gaming',1,'2026-10-25'), ('gta6',1,'2026-10-25'), ('industry',1,'2026-10-25')]
```
Tracked params, param order and a www. vs bare-host difference all still matched. 5 rows = 2 yt/video + 1 url + 1 title + 1 quick. The Warframe item is tagged `gta6` yet stays fresh - a topic hit alone never suppresses.

### 5 `--help` / `filter --help` (abridged, both exit 0)
```
usage: memory.py [-h] [--root ROOT] [--db DB] [--selftest] {filter,mark,query,stats,prune,selftest} ...
  filter  annotate candidates with seen/seen_reason/topic_hits   mark  record an edition (idempotent)
  query   when/how often a topic was covered                     stats counts, db size, last edition
  prune   drop rows older than N days not referenced by a kept edition
  --root ROOT  project root (default: parent of scripts/)   --db DB  sqlite path

usage: memory.py filter [-h] --candidates CANDIDATES --out OUT
                        [--suppressed SUPPRESSED] [--cooldown COOLDOWN]
  --suppressed  seen-only audit file (default: <out dir>/suppressed.json)
  --cooldown    default: settings.json repeat_topic_cooldown_days=21
```

### 6 extra checks
```
title-guard rewrite caught: seen=True reason=title
url normaliser: 'HTTPS://www.Example.com/GTA6-Delay/?utm_source=x&fbclid=y&b=2#frag'
             == 'https://example.com/GTA6-Delay?b=2'  -> True
title normaliser: 'Rockstar  delays GTA 6!!' == 'rockstar delays gta 6' -> True
journal_mode: wal | topic_seen rows 3 | topics [('gaming',1),('gta6',1),('industry',1)]
prune (cutoff 400d): (1,1) -> items ['yt:kept'], topics ['keptt'], topic_seen ['keptt']
cooldown default: 21 with key missing AND with no settings.json at all
object form {"items":[...]}: counts {'total':3,'seen':2,'fresh':1}, suppressed 2
non-ASCII chars in captured console output: 0
```

## Decisions (for DECISIONS.md)
- `topic_seen` additive table = mark() idempotency guard (CONTRACTS.md 115-116 authorises it).
- Topics come from section `tags` + lowercased `kicker` slug; quickHits add none (no tags in schema).
- Edition date from json `date`, `--date` overrides; `topics.last_covered`/`items.first_seen` store that date (YYYY-MM-DD) so `--days` maths is date-stable; `editions.created` keeps the real ISO stamp.
- `editions.items` recomputed as `COUNT(*) WHERE edition = ?` each mark, so re-marking cannot drift it.
- `recent_topics` ordered `last_covered DESC, topic ASC`; `filter --cooldown` overrides settings; `query --days` default 60, `prune --days` default 400.
- `--db` exists so selftest and this round trip never touch the real `state/seen.sqlite`.
