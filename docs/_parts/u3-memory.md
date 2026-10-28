# u3 - memory.py (sqlite anti-repeat store)

`scripts/memory.py`, stdlib only. CLI surface = CONTRACTS.md items 3-8 verbatim.

## Schema
The three spec tables verbatim, plus one additive guard table (authorised by CONTRACTS.md lines 115-116):

```sql
items(key TEXT PRIMARY KEY, kind TEXT, title TEXT, url TEXT, source TEXT,
      first_seen TEXT, edition TEXT, tags TEXT)
topics(topic TEXT PRIMARY KEY, last_covered TEXT, times INTEGER, last_edition TEXT)
editions(date TEXT PRIMARY KEY, path TEXT, items INTEGER, created TEXT)
topic_seen(topic TEXT, edition TEXT, PRIMARY KEY(topic, edition))
```

`topic_seen` is what makes `mark` idempotent: `INSERT OR IGNORE` returning rowcount 0 means "this topic was
already counted for this edition", so `topics.times` never double-increments. WAL, busy_timeout 5000,
`PRAGMA user_version` stamped so a future schema change is explicit rather than a silent overwrite.

## Keys and normalisation (shared by filter and mark)
- video -> `yt:<videoId>` (from the field, else parsed out of the url incl. youtu.be/shorts/embed/live)
- news -> `url:<sha1(normalised url)[:16]>` AND a second guard row `title:<sha1(normalised title)[:16]>`
- normalisation: lowercase, drop fragment, drop `utm_*`/fbclid/gclid/msclkid/ref/referrer/source/mc_cid/
  mc_eid/igshid/s/si/feature, sort query params, drop `www.`, strip punctuation, collapse whitespace.

## Commands (all verified by running them)
```
filter --candidates <p> --out <p> [--suppressed <p>] [--cooldown N]   -> exact CONTRACTS item 3 object
mark --edition editions/<date>.json                                   -> marked: N new items, N topics, edition <date>
query --topic <t> [--days 60]                                         -> human lines, exit 0 even unknown
stats                                                                 -> counts, db bytes, last edition
prune --days 400                                                      -> pruned: N items, N topics
selftest | --selftest                                                 -> SELFTEST PASS
```
A topic hit never sets `seen = true`; `topic_hits` is report-only, because the spec puts that judgement on
the agent. Suppressed items are written to `suppressed.json` for audit.

## Verification (real captured output)
`python scripts/memory.py selftest`:
```
selftest: a/b/c/d ok
SELFTEST PASS
exit=0
```

Idempotency + filter round trip on a throwaway db with a fixture edition:
```
marked: 5 new items, 4 topics, edition 2026-10-28     (first mark)
marked: 0 new items, 0 topics, edition 2026-10-28     (second mark - no double count)
filter done: 3 total, 2 seen, 1 fresh, 4 cooling topics
  True  video  ['gaming','valormortis']        | Valor Mortis review
  False None   ['gaming']                      | Brand new story about a toaster
  True  url    ['gaming','gta6','rockstar']    | Rockstar staff vote on a union
suppressed: 2
topic 'gta6': covered 1 time(s), last on 2026-10-28
topic 'never-seen': never covered
pruned: 0 items, 0 topics        (nothing was old enough, and nothing an edition referenced was touched)
```
Note the third row: the edition's url was recorded WITHOUT the `?utm_source=x` variant and the candidate
arrived WITH it - the normaliser still matched it, which is the exact case the spec asked for.

Live db after the real edition was marked: `items: 37, topics: 46, editions: 1, db size: 61440 bytes`.

## Decisions
- The additive `topic_seen` table is the only schema addition, and it exists solely for idempotency.
- `filter` on an unreadable candidates file exits 0 with an empty report rather than killing the night;
  `run_daily.py` still warns about it.
- `prune` refuses to delete rows a kept edition references, even past the cutoff.
