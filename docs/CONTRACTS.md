# CONTRACTS - the shared data/CLI contract (build-time, binding for every backend script)

Binding for: scripts/memory.py, scripts/yt_source.py, scripts/news_source.py, scripts/transcripts.py,
scripts/run_daily.py. Any deviation must be written into docs/DECISIONS.md, never silently made.

## Global rules
- Python 3.11. Imports: stdlib + requests, feedparser, beautifulsoup4, Pillow only. No new packages.
- Every file open has encoding="utf-8" (or "utf-8-sig" for reading BOM-tolerant config).
- Console output ASCII only: no emoji, no box drawing, no non-ASCII punctuation.
- Each script: argparse with --help, exit 0 on success, exit non-zero + one-line stderr message on failure,
  and a single final human summary line on stdout.
- Paths: project root is the parent of scripts/, resolved with Path(__file__).resolve().parents[1],
  overridable with --root. Never depend on cwd.
- Call sys.stdout.reconfigure(encoding="utf-8", errors="replace") (guarded for None) at module import so a
  redirected console never crashes on a stray character.
- Dates: local time. ISO 8601 with offset for timestamps. --date is YYYY-MM-DD.

## Canonical item object (candidates.json element)
```
{
  "source": "youtube" | "news",
  "kind": "video" | "short" | "article",
  "key": "yt:<videoId>" | "url:<sha1-16>" | "title:<sha1-16>",
  "title": str,
  "url": str,
  "publishedAt": "2026-10-28T01:23:45+01:00" | null,
  "score_hint": float,          # mechanical only: youtube tier 3/2/1 -> 1.0/2.0/3.0 (see note), news = feed weight
  "tags": [str],
  "thumb_local": str | null,    # filled by run_daily step 4, path relative to project root

  youtube only: "videoId", "channel", "channelId", "thumbnail", "lengthSeconds": int|null,
                "views": int|null, "tier": 1|2|3
  news only:    "sourceName", "feedTags": [str], "summary": str(<=600), "image": str|null,
                "weight": int, "also_on": [str]
}
```
score_hint rule (single, unambiguous): youtube -> 4 - tier  (tier 1 = 3.0, tier 2 = 2.0, tier 3 = 1.0);
news -> float(weight). Producers write candidates.json as a JSON array of these objects.
Unknown/absent numeric fields are null, never 0-means-unknown.

## CLI contract (each one is called by run_daily.py exactly like this)

1. `python scripts/yt_source.py --out state/workpack/<date>/yt.json [--hours 26] [--channel UC...] [--no-shorts] [--limit N]`
   stdout last line: `yt_source done: <n> videos from <ok>/<total> channels (<failed> failed)`
   exit 0 even when some channels fail. Non-zero only when channels.json is unreadable or every channel fails.

2. `python scripts/news_source.py --out state/workpack/<date>/news.json [--hours 26] [--limit N]`
   stdout last line: `news_source done: <n> articles from <ok>/<total> feeds (<failed> failed)`
   exit 0 when at least one feed works.

3. `python scripts/memory.py filter --candidates <candidates.json> --out <filtered.json> [--suppressed <suppressed.json>]`
   Reads a JSON array (or an object with an "items" array). Writes:
   ```
   { "generatedAt": iso, "date": "YYYY-MM-DD", "cooldown_days": 21,
     "recent_topics": [{"topic": str, "last_covered": iso, "times": int}],
     "counts": {"total": n, "seen": n, "fresh": n},
     "items": [ ...original item object + "seen": bool, "seen_reason": str|null, "topic_hits": [str] ] }
   ```
   seen_reason values: "video", "url", "title", "topic:<name>", or null when fresh.
   suppressed.json gets `{"generatedAt": iso, "items": [ only the seen ones ]}`. Exit 0.

4. `python scripts/memory.py mark --edition editions/<date>.json` -> idempotent; prints `marked: <n> new items, <n> topics, edition <date>`
5. `python scripts/memory.py query --topic gta6 [--days 60]` -> human lines, exit 0.
6. `python scripts/memory.py stats` -> counts + db size + last edition, exit 0.
7. `python scripts/memory.py prune --days 400` -> deletes only rows older than N days that are NOT referenced by a kept edition. Prints `pruned: <n> items, <n> topics`.
8. `python scripts/memory.py selftest` (also accepted: `--selftest`) -> temp DB, marks twice, filters; final line `SELFTEST PASS`.

9. `python scripts/transcripts.py --candidates <filtered.json> --out-dir state/workpack/<date>/transcripts [--limit N] [--ids a,b,c] [--max-chars 24000]`
   Sequential. stdout last line: `transcripts done: <fetched> fetched, <cached> cached, <failed> failed`.
   Writes `<out-dir>/<videoId>.txt` (trimmed head+tail with `[... trimmed N chars ...]` marker) and
   `<out-dir>/index.json`: {"<videoId>": {"status":"ok|cached|failed","chars":int,"reason":str|null}}.
   Exit 0 always (a per-video failure is data, not a crash).

10. `python scripts/run_daily.py collect [--date YYYY-MM-DD] [--hours 26] [--limit-transcripts N]`
    stdout last line exactly: `collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed`
    Non-zero only if candidates.json could not be written at all.

## Workpack layout (state/workpack/<date>/)
- yt.json, news.json            raw producer output (arrays)
- candidates.json               merged array, score_hint set, deduped
- filtered.json, suppressed.json
- transcripts/<videoId>.txt + index.json
- img/                          downloaded+verified images, named <sha1-16>.<ext>
- packet.md                     agent-facing briefing (structure below)

## packet.md required structure (ASCII, no emoji)
```
# DAILY BEACON - workpack <date>
generated <iso> | lookback <h>h | <v> videos, <a> articles | <r> repeats suppressed

## counts
## videos (<n> kept, all listed)
## articles (<n> kept, all listed)
## cooling down
## next commands
```
Every kept item is listed, bounded only by `max_videos_total` / `max_news_items` - the packet is the
agent's entire view of the night, so capping it below the collection cap silently discards items that
were already fetched (the bug fixed 2026-10-28: 20 of 32 videos and 20 of 60 articles were never shown).
Each candidate line, one line per item, newlines collapsed:
`- [T<tier>|w<weight>] <title> | <source> | <published> | <url> | transcript:<yes|no>`

## Ordering / caps (mechanical, spec-driven)
- youtube: sort by (tier asc, publishedAt desc), cap max_videos_per_channel then max_videos_total.
- news: sort by (weight desc, publishedAt desc), cap max_news_items, cap 6 per source
  (`news_source.MAX_PER_SOURCE` and `run_daily.NEWS_PER_SOURCE_CAP` must match).
- transcripts: only kind == "video", unseen, sorted (tier asc, publishedAt desc), capped by --limit-transcripts
  (run_daily default: min(12, max_videos_total)).

## settings.json keys consumed (exact names)
lookback_hours, max_videos_per_channel, max_videos_total, max_news_items, short_max_seconds,
transcript_max_chars, edition_max_stories, edition_min_stories, repeat_topic_cooldown_days,
keep_editions, site_base_url, publish. Missing key -> documented default in code, never a crash.

## memory.py DB schema (exactly spec section 4)
items(key TEXT PRIMARY KEY, kind TEXT, title TEXT, url TEXT, source TEXT, first_seen TEXT, edition TEXT, tags TEXT)
topics(topic TEXT PRIMARY KEY, last_covered TEXT, times INTEGER, last_edition TEXT)
editions(date TEXT PRIMARY KEY, path TEXT, items INTEGER, created TEXT)
Plus (allowed, additive): table `topic_seen(topic TEXT, edition TEXT, PRIMARY KEY(topic, edition))` used ONLY to
make mark() idempotent without touching the spec's three tables. Document it in docs/DECISIONS.md.