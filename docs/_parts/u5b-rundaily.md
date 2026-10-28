# u5b - run_daily.py (collect orchestrator)

Delivered: `scripts/run_daily.py` - `collect` chains yt_source -> news_source -> merge+caps -> memory filter
-> transcripts -> images -> packet.md and prints the contract summary line.

## Contract compliance (CONTRACTS.md item 10)
- `python scripts/run_daily.py collect [--date YYYY-MM-DD] [--hours 26] [--limit-transcripts N] [--root PATH] [--skip-images] [--reuse-source]`;
  `--help` works at both levels.
- Final stdout line exactly `collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed`.
- Exit non-zero only when `candidates.json` cannot be written; every producer/filter/transcript/image
  failure is a WARN recorded in packet.md and the run continues (spec section 5: a short edition still ships).
- `--reuse-source` reuses an existing yt.json/news.json, so an interrupted run does not pay for 79 channels twice.

## Steps
1. producers as subprocesses (`PYTHONIOENCODING=utf-8`, 1800s each); ok/total/failed parsed from their summary
   line by `parse_producer_stats()`, which falls back to the file's own item count when the line is absent.
2. merge to the canonical object, `score_hint` mechanical (youtube `4-tier`, news `float(weight)`), dedupe by
   `key`, then the CONTRACTS caps: youtube (tier asc, published desc) with `max_videos_per_channel` then
   `max_videos_total`; news (weight desc, published desc) with `max_news_items` and 4 per source.
3. `memory.py filter` -> filtered.json + suppressed.json; on failure it writes an unfiltered filtered.json
   with `seen=false` and a WARN instead of dying.
4. `transcripts.py --candidates filtered.json --out-dir transcripts --limit L --max-chars 24000`.
5. images: up to 24, 10s timeout, browser UA, >8MB rejected by header and by bytes, jpeg/png/webp verified
   with Pillow, silent skip on failure; `img/<sha1-16>.<ext>` plus `images.json`, and `thumb_local` patched
   into filtered.json (candidates.json stays immutable).
6. packet.md with the six headings in the contract order.

## Verification (real captured runs, 2026-10-28)

Full cold run (network):
```
yt_source done: 34 videos from 79/79 channels (0 failed)
news_source done: 60 articles from 21/21 feeds (0 failed)
transcripts done: 2 fetched, 10 cached, 0 failed
step4 images: 24 downloaded -> img/
step5 packet: state/workpack/2026-10-28/packet.md
collect done: 34 videos, 60 articles, 14 transcripts, 0 repeats suppressed
EXIT=0
```

`--reuse-source` run (after the real edition was marked, so memory now suppresses):
```
transcripts done: 0 fetched, 12 cached, 0 failed
collect done: 29 videos, 60 articles, 20 transcripts, 16 repeats suppressed
EXIT=0
```
Memory correctly reports `89 total, 16 seen, 73 fresh` - those 16 are the stories the edition already
covered, which is the whole point of the anti-repeat store.

packet.md head:
```
# DAILY BEACON - workpack 2026-10-28
generated 2026-10-28T11:43:48+01:00 | lookback 26h | 29 videos, 60 articles | 16 repeats suppressed

## counts
- youtube: 29 videos | reused from disk (--reuse-source)
- news: 60 articles | reused from disk (--reuse-source)
- candidates after caps: 29 videos, 60 articles (89 total)
- memory filter: 89 total, 16 seen, 73 fresh
- repeats suppressed: 16
- transcripts: 0 fetched, 12 cached, 0 failed (20 files on disk)
- images downloaded: 24
- warnings: none
```

## Structural validation (scripted)
- first line `# DAILY BEACON - workpack 2026-10-28`
- headings exactly `## counts`, `## top videos`, `## top articles`, `## cooling down`, `## next commands`, in that order
- 40 candidate lines, every one `- [T<t>|w<w>] title | source | published | url | transcript:yes|no` (4 ` | ` separators)
- whole file ASCII-only

## Workpack on disk (state/workpack/2026-10-28/)
`yt.json`, `news.json`, `candidates.json`, `filtered.json`, `suppressed.json`, `images.json`, `packet.md`,
`transcripts/` (20 .txt + index.json), `img/` (24 verified images).

## Notes
- The per-channel cap of 3 with a 26h window yields 29-34 videos; that is the configured behaviour.
- A second identical run rewrites packet.md and reuses the transcript cache: no duplicate images, no crash.
- Several orphaned `collect` runs from earlier in the session were killed; the numbers above are from single
  clean runs.
