# U4 - news_source.py (feeds -> normalised, de-duplicated news candidates)

Status: done. `scripts/news_source.py` rewritten to contract, run for real on the seeded config
(21 enabled feeds) -> `state/workpack/2026-10-28/news.json`: 60 items, 60 with image, 17 sources.
CLI `--out ... [--hours 26] [--limit N] [--root PATH]`, `--hours` default = settings `lookback_hours`,
`--limit` default = `max_news_items`, `--print-first N` debug. Exit 0 if one feed works, 2 = feeds.json
unreadable/not an array/no enabled feeds, 1 = every feed failed, 3 = output unwritable.

## Captured - real run, 26h window, exit 0

```
news_source: 21 feeds, window 26h, cap 60 (max 4 per source)
  ok   PC Gamer                 50 entries, 22 in window, 28 older
  ok   Rock Paper Shotgun       100 entries, 16 in window, 84 older
  ok   Eurogamer                100 entries, 12 in window, 88 older
  ok   GamesIndustry.biz        100 entries, 7 in window, 93 older
  ok   VGC                      10 entries, 10 in window
  ok   GameSpot                 15 entries, 13 in window, 2 older
  ok   IGN Games                20 entries, 20 in window
  ok   Digital Foundry          15 entries, 0 in window, 15 older
  ok   Tom's Hardware           50 entries, 19 in window, 31 older
  ok   The Verge AI             10 entries, 7 in window, 3 older
  ok   Ars Technica             20 entries, 1 in window, 19 older
  ok   TechCrunch AI            20 entries, 13 in window, 7 older
  ok   MIT Technology Review    10 entries, 3 in window, 7 older
  ok   Game Developer           50 entries, 6 in window, 44 older
  ok   Kyiv Independent         100 entries, 24 in window, 76 older
  ok   PCGamesN                 75 entries, 5 in window, 70 older
  ok   GamesRadar               50 entries, 45 in window, 5 older
  ok   Nintendo Life            25 entries, 13 in window, 12 older
  ok   Wccftech                 20 entries, 20 in window
  ok   Engadget                 20 entries, 20 in window
  ok   Ars Technica Gaming      20 entries, 0 in window, 20 older
  window: 276 items in 26h (0 undated kept)
  dedupe: 276 -> 276 stories (0 merged, also_on recorded)
  caps: 4/source dropped 174, overall cap 60 dropped 42
  images: 60/60 items have one (og:image fetches 8/10)
  wrote ...\state\workpack\2026-10-28\news.json
news_source done: 60 articles from 21/21 feeds (0 failed)
```

`--help` prints the argparse block for the CLI above. All 21 feeds returned 200 with entries - nothing
failed, no retry needed. Digital Foundry and Ars Technica Gaming parsed entries but had none inside 26h:
healthy feed, `ok` not failed.

## Captured - validation

`python -c` asserts: list, every required key present, every key `url:[0-9a-f]{16}`, no duplicate keys,
all summaries <= 600, source/kind, float score_hint + int weight, thumb_local null, also_on list.

```
news.json OK: 60 items, 60 with image, 17 unique sources
```

Exit paths checked: `--limit 5` -> 5 items exit 0; feeds.json "not json" -> one stderr line exit 2; a
single `example.invalid` feed -> `FAIL ... ConnectionError` + `every feed failed (1 feeds)` exit 1;
broken settings.json -> 26h/60 defaults, no crash.

## Dedupe: 0 merges here is real

0 in-window exact-title and 0 exact-url collisions across 21 feeds; max cross-feed Jaccard 0.67 (CoD MW4
review vs critical consensus = different articles). Synthetic `dedupe()` test: 4 items -> `kept 2 merged
2`, winner Eurogamer w3 with `also_on ['IGN Games']`, collapsing a `?utm_source=tw` url variant and a
"Playstation"/"PlayStation" headline variant from a w2 feed.

## Decisions

1. **Undated items kept, `publishedAt: null`**, counted in the `window:` line (0 today) - dropping them
   loses a feed silently when its date format is unreadable. All stamps carry a local offset with
   `timespec="seconds"`, so the descending sort in `(weight desc, publishedAt desc)` is chronological.
2. **og:image last resort: max 10 fetches/run, 8s timeout, silent.** media:content, media:thumbnail,
   image enclosure/link and first `<img>` in the summary go first and cost no network (52 of 60 items got
   one that way) - worst case 10x8s, never fails or blocks the run.
3. **Dedupe = exact normalised URL, exact normalised title, or Jaccard >= 0.8** on significant words
   (>= 4 chars, stopwords removed). 0.8 not 0.6-0.7: real 0.6 pairs are distinct articles. Winner =
   highest weight, tie -> earliest `publishedAt`; losers -> `also_on`.
4. **Cap 4 per sourceName first, then overall** - overall-first could fill all 60 slots from the four
   heaviest feeds; 17 sources in the output show this spreads coverage. Drops printed (174, then 42).
5. **`tags` = feed tags + up to 3 mechanical title words** (significant words not already a feed tag,
   deduped, no invented taxonomy); `feedTags` untouched.
6. **`key` reproduces memory.py's canonical-url family verbatim** - lowercase, no scheme/www, tracking
   params dropped, params sorted, trailing slash dropped, punctuation collapsed, sha1[:16]. The brief says
   "keep the path", but memory.py drops the trailing slash and `memory.py filter` recomputes this value
   from the item url, so divergence would make articles look new after a url tweak (verified equal).
7. **HTTP 200 with 0 parsed entries = `failed`** (spec 5 / FEEDS-CHECK.md); entries present but none in
   window = `ok` ("0 in window"). Summary: BeautifulSoup `html.parser` strip, whitespace collapsed, cut on
   a word boundary (no ellipsis), <= 600 chars. Output array `ensure_ascii=False`, `indent=2`, UTF-8,
   relative `--out` against `--root`; console forced ASCII via `ascii_safe()`; scratch `_url_norm` /
   `_title_norm` stripped, so items carry exactly the CONTRACTS.md keys. No image downloaded here:
   `image` = remote url or null, `thumb_local` null, `score_hint == float(weight)`, `weight` int.
