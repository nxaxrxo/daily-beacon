# u5b - run_daily.py (collect orchestrator)

Delivered: `scripts/run_daily.py` - `collect` chains yt_source -> news_source -> merge+caps -> memory filter
-> transcripts -> images -> packet.md, and prints the contract summary line.

## Contract compliance
- `python scripts/run_daily.py collect [--date YYYY-MM-DD] [--hours 26] [--limit-transcripts N] [--root PATH] [--skip-images] [--reuse-source]`, argparse `--help` on both the top level and the subcommand.
- Last stdout line exactly `collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed`; exit 1 only when candidates.json cannot be written.
- Every producer/filter/transcript/image failure is a WARN in the packet, never an abort (spec section 5 failure rule: a short edition still ships).
- `--reuse-source` reuses an existing yt.json/news.json so a killed run can resume without refetching 79 channels.

## What each step does
1. Producers: `yt_source.py --out ... --hours H`, `news_source.py --out ... --hours H` as subprocesses with `PYTHONIOENCODING=utf-8`, 1800s each; their last line is regex-parsed for ok/total/failed counts.
2. Merge: union, canonical object completed for every item, `score_hint` mechanical (youtube 4-tier, news weight), dedupe by `key`, then the CONTRACTS caps - youtube (tier asc, published desc) with max_videos_per_channel then max_videos_total; news (weight desc, published desc) with max_news_items and 4 per source.
3. `memory.py filter` -> filtered.json + suppressed.json. If it fails, run_daily writes its own unfiltered filtered.json with `seen=false` and a WARN, so the pipeline never dies on the memory step.
4. `transcripts.py --candidates filtered.json --out-dir transcripts --limit L`; fetched/cached/failed parsed from its last line.
5. Images: up to 24 candidates, 10s timeout, browser UA, >8MB rejected by header AND by bytes, jpeg/png/webp sniffed with Pillow, all failures silent; written as `img/<sha1-16>.<ext>` with the relative path in images.json and patched into filtered.json's `thumb_local` (candidates.json stays immutable).
6. packet.md with the six required headings in order.

## Verification (real runs, 2026-10-28)

`python scripts/run_daily.py --help` -> usage, exit 2 (no subcommand) as designed; `collect --help` lists
every flag.

Full run:
```
collect done: 31 videos, 60 articles, 9 transcripts, 0 repeats suppressed
```
(packet.md written; 24 images downloaded; memory filter produced 91 total / 0 seen / 91 fresh - a fresh DB
means nothing is suppressed yet, which is correct on day one.)

packet.md head:
```
# DAILY BEACON - workpack 2026-10-28
generated 2026-10-28T11:02:17+01:00 | lookback 26h | 31 videos, 60 articles | 0 repeats suppressed

## counts
- youtube: 34 videos | 79/79 ok, 0 failed
- news: 60 articles | 21/21 ok, 0 failed
...
## top videos
- [T1|w1] I Befriended A Serial Killer... | MeatCanyon | 2026-10-28T10:46+01:00 | https://www.youtube.com/watch?v=DQJ3F4ZOkzk | transcript:yes
...
```

## Structural validation
Asserted by script: first line starts `# DAILY BEACON - workpack <date>`; all six `## ` headings present in
the contract order (`counts`, `top videos`, `top articles`, `cooling down`, `next commands`); at least one
`- [T` candidate line; every candidate line has the five ` | ` separated fields plus the transcript flag.

## Workpack on disk
```
state/workpack/2026-10-28/
  yt.json          videos from 79 channels
  news.json        60 articles from 21 feeds
  candidates.json  91 after caps (31 videos + 60 articles)
  filtered.json    memory-annotated, thumb_local patched
  suppressed.json  0 seen items on a fresh DB
  images.json      24 verified images
  packet.md        the agent briefing
  transcripts/     9 .txt + index.json
  img/             24 files
```

## Honest notes
- The per-channel cap of 3 plus a 26h window yields 31-34 videos; that is the config working as specified, not a shortfall.
- A second identical run overwrote packet.md and re-used the transcript cache; no duplicate images, no crash.
- Two `collect` invocations were left running in parallel early in the session and were killed; the numbers
  above come from a single clean run.
