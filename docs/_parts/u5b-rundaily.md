# u5b - run_daily.py (collect orchestrator)

Delivered: `scripts/run_daily.py` - `collect` chains yt_source -> news_source -> merge+caps -> memory
filter -> transcripts -> images -> packet.md, then prints the contract summary line.

## Contract compliance (CONTRACTS.md item 10, SPEC section 5 steps 1-6)
- CLI: `collect [--date YYYY-MM-DD] [--hours 26] [--limit-transcripts N] [--root PATH] [--skip-images]`,
  plus `--reuse-source` for resuming a run that died after fetching. `--help` works at both levels;
  subparsers leave room for `status` but expose no other verb (unknown verb -> usage, exit 2).
- Last stdout line exactly `collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed`.
- Exit non-zero only when candidates.json cannot be written. A failing producer, filter, transcript step
  or image batch is a WARN line plus a `warnings:` entry in packet.md, and the run continues.
- Summary counts are post-cap candidates; `t` = .txt files on disk; `r` = len(suppressed.json).

## Steps as implemented
1. yt_source.py and news_source.py as subprocesses (sys.executable, cwd=root, PYTHONIOENCODING=utf-8,
   1800 s each), their output echoed before each step line. Merge to the canonical object with every
   key present (absent numeric -> null), dedupe by key (videos first, so youtube wins an identical key;
   news also guarded on normalised url+title), then the CONTRACTS caps: youtube (tier asc, publishedAt
   desc) -> per-channel -> max_videos_total; news (weight desc, publishedAt desc) -> 4/source -> cap.
2. `memory.py filter` -> filtered.json + suppressed.json. If it fails, filtered.json is written here
   itself (seen=false, seen_reason=null, topic_hits=[], empty recent_topics) and a WARN is recorded.
3. `transcripts.py --candidates filtered.json --out-dir transcripts --limit` (arg, else
   min(12, max_videos_total)) -> `.txt` per video + index.json; last line parsed for fetched/cached/failed.
4. Images unless `--skip-images`: up to 24 candidates with an image URL, 10 s timeout, browser UA,
   >8 MB rejected on Content-Length and on real bytes, magic-byte sniff + Pillow `open().verify()`
   with a JPEG/PNG/WEBP whitelist, `ThreadPoolExecutor(max_workers=4)`. Name is `sha1(url)[:16]` +
   sniffed extension, so re-runs are idempotent. candidates.json is never touched; `images.json` is
   `{"<key>": "<relpath>"}` and filtered.json gets `thumb_local` patched (relative, forward slashes).
5. packet.md: one H1 line, then the five `##` sections in the contract order - counts, top videos,
   top articles, cooling down, next commands - ASCII only, project-relative paths, candidate lines
   `- [T<tier>|w<weight>] <title> | <source> | <published> | <url> | transcript:<yes|no>` with titles
   whitespace-collapsed and truncated to 120 chars. Cooling down reads suppressed.json.

## Real captured output - cold full run (network, 2026-10-28 12:09)
`python -u scripts/run_daily.py collect --date 2026-10-28 --hours 26`, launched detached, log redirected:
```
yt_source done: 32 videos from 79/79 channels (0 failed)
news_source: 24 feeds, window 26h, cap 60 (max 4 per source)   [24/24 ok, 0 failed]
  ok   PC Gamer 22 in window | Rock Paper Shotgun 17 | Eurogamer 12 | GamesIndustry.biz 8 | VGC 10
  ok   GameSpot 13 | IGN Games 20 | PCGamesN 5 | GamesRadar 46 | Nintendo Life 15 | Digital Foundry 0
  ok   Tom's Hardware 22 | Wccftech 20 | Ars Technica Gaming 0 | Game Developer 6 | The Verge AI 7
  ok   TechCrunch AI 13 | Ars Technica 16 | MIT Technology Review 2 | Google AI Blog 0
  ok   Hugging Face 2 of 891 | Godot Blog 0 | Unreal Engine 0 | Kyiv Independent 28
  window: 284 items in 26h (0 undated kept)
  dedupe: 284 -> 284 stories (0 merged, also_on recorded)
  caps: 4/source dropped 183, overall cap 60 dropped 41
  images: 60/60 items have one (og:image fetches 8/10)
news_source done: 60 articles from 24/24 feeds (0 failed)
step1 merged: 92 candidates (32 videos, 60 articles) -> candidates.json
filter done: 92 total, 15 seen, 77 fresh, 46 cooling topics
[1/12] WjmL7yBTObE cached 9101 chars
[2/12] M0ri49SozG4 cached 1648 chars
...
[12/12] _NecoHLsKPk cached 24031 chars
transcripts done: 0 fetched, 12 cached, 0 failed
step4 images: 24 downloaded -> img/
step5 packet: state/workpack/2026-10-28/packet.md
collect done: 32 videos, 60 articles, 22 transcripts, 15 repeats suppressed
EXIT=0
```
A `--reuse-source` rerun (11:57, smaller source set) also exited 0: `collect done: 29 videos, 60
articles, 20 transcripts, 16 repeats suppressed` - same packet shape, no duplicate images.

## CLI surface, checked by exit code
```
top-level --help  exit=0 | collect --help  exit=0 (--date --hours --limit-transcripts
                            --skip-images --reuse-source --root) | unknown verb  exit=2
```
`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` is wrapped in try/except.

## Structural validation (scripted, pasted)
```
PACKET OK: 5 headings in order, 40 candidate lines, line-format violations 0, ascii-only
headings: ['## counts', '## top videos', '## top articles', '## cooling down', '## next commands']
line1: generated 2026-10-28T12:17:53+01:00 | lookback 26h | 32 videos, 60 articles | 15 repeats suppressed
```
Assertions: first line starts `# DAILY BEACON - workpack `, the five `##` headings exactly in that
order, every char < 128, all 40 candidate lines match the contract line format.

## Data-shape checks
```
images.json keys 24 sample ('yt:17djB82ImkQ', 'state/workpack/2026-10-28/img/e019f3c359034020.jpg')
filtered thumb_local 24, forward-slash only True | candidates thumb_local all None True
candidates 92 filtered 92 suppressed 15
```

## Workpack on disk (state/workpack/2026-10-28/)
yt.json 19301 | news.json 64309 | candidates.json 74178 | filtered.json 89158 |
suppressed.json 16148 | images.json 1755 | packet.md 11737 | transcripts/ (22 .txt + index.json) |
img/ (65 files; all 24 paths in this run's images.json resolve - the rest belong to URLs that fell
out of the 26h window on earlier runs and are not pruned)

## Notes
- `py_compile scripts/run_daily.py` exits 0; 30338 bytes, SHA256 D28A940422E0B8D8...
- yt_source is serial over 79 channels (~5-6 min), so the full run is launched detached and polled via
  a done-file, never held in one shell call. No window shown, no browser opened.
- A healthy run can print `youtube: 0 videos | producer did not report a summary` while yt.json is
  complete; the counts come from candidates.json, not that line.
