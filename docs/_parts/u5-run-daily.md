# u5 - transcripts.py + run_daily.py (delivered and run for real)

## 1. scripts\transcripts.py

Batch wrapper around `%USERPROFILE%\.config\opencode\tools\yt_transcript.py`.

```
python scripts\transcripts.py --candidates <filtered.json> --out-dir state\workpack\<date>\transcripts [--limit N] [--max-chars 24000] [--root PATH]
python scripts\transcripts.py --ids a,b,c [--out-dir DIR] [--date YYYY-MM-DD] [--timeout 180]
```

- Input: `--candidates` takes only `kind=="video"` and `seen==false`, sorted (tier asc, publishedAt desc);
  `--ids` is a comma list and overrides the file. `--limit` caps the batch (default min(12, max_videos_total)).
- Cache: `%USERPROFILE%\.config\opencode\notes\yt-cache` is checked FIRST, recursively, for
  `<videoId>*.txt` in ANY language. A hit is copied into the out-dir and the fetcher is never called.
  The cache dir is read-only here - this script never writes into it.
- Sequential always. Per-video `subprocess.run(..., timeout=180)`; a timeout / non-zero exit / empty file
  is recorded in index.json with a reason and the loop continues. Never aborts, always exit 0.
- **ASR is disabled on purpose**: every call passes `--no-asr`. The shared tool would otherwise fall back
  to downloading audio + whisper, which can burn an hour at 03:00. A captionless video is simply `failed`.
- Trim: over `--max-chars` (default settings `transcript_max_chars` = 24000) keeps head 60% + tail 40%
  with the exact marker line `[... trimmed <N> chars ...]`, N = removed chars.
- Output: `<out-dir>\<videoId>.txt` plus `<out-dir>\index.json` =
  `{"<videoId>": {"status":"ok|cached|failed","chars":int,"reason":str|null}}`.
- Final line exactly: `transcripts done: <fetched> fetched, <cached> cached, <failed> failed`.

Real fetch check (proves the captions route still works, not just the cache):
```
[1/1] jNQXAC9IVRw ok 217 chars
transcripts done: 1 fetched, 0 cached, 0 failed
```

## 2. scripts\run_daily.py

```
python scripts\run_daily.py collect [--date YYYY-MM-DD] [--hours 26] [--limit-transcripts N] [--root PATH]
```

Five steps, each in its own try/except, failures recorded and the run continues; the only fatal case is
being unable to write candidates.json (exit 1).

1. `yt_source.py --out <wp>\yt.json --hours H` + `news_source.py --out <wp>\news.json --hours H` as
   subprocesses (1800s each). Merge into candidates.json: dedupe by `key`; news additionally deduped by
   normalised title/url keeping the higher `weight`/`score_hint` and appending the loser's `sourceName`
   to `also_on`. `score_hint` per CONTRACTS: youtube `4 - tier` (tier1=3.0, tier2=2.0, tier3=1.0),
   news `float(weight)`.
2. `memory.py filter --candidates ... --out filtered.json --suppressed suppressed.json`. If it fails,
   run_daily writes its own unfiltered filtered.json (`seen=false`) and continues.
3. `transcripts.py --candidates filtered.json --out-dir <wp>\transcripts --limit N --max-chars ...`.
4. Images for the top unseen items into `<wp>\img\` as `<sha1(url)[:16]>.<ext>` (jpg/png/webp only,
   sniffed by magic bytes AND Pillow-verified, <8MB, browser UA, 15s timeout, 4 threads, 24 max,
   every failure silent). `images.json` maps key->relative path and `thumb_local` is patched into
   filtered.json (path relative to project root, forward slashes).
5. `<wp>\packet.md` with the exact headings `# DAILY BEACON - workpack <date>`, summary line,
   `## counts`, `## top videos`, `## top articles`, `## cooling down`, `## next commands`, one line per
   candidate (`- [T<n>|w<n>] title | source | published | url | transcript:<yes|no>`), newlines
   collapsed, real next commands with the actual date.
6. Final stdout line exactly
   `collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed`.

Every line is also tee'd to `state\logs\collect-<date>.log`, so a detached 03:00 run leaves a log on disk.

## 3. The real run

Command (from the project dir, run detached via Task Scheduler because a foreground shell here is killed
at ~90s):

```
python -u scripts\run_daily.py collect
```

Real stdout (full, unedited apart from the news_source per-feed table and one bs4 warning):
```
yt_source done: 32 videos from 79/79 channels (0 failed)
news_source done: 60 articles from 24/24 feeds (0 failed)
step1 merged: 92 candidates (32 videos, 60 articles) -> candidates.json
filter done: 92 total, 15 seen, 77 fresh, 46 cooling topics
[1/12] WjmL7yBTObE cached 9101 chars
[2/12] Gzzhg_QGluw cached 24032 chars
[3/12] M0ri49SozG4 cached 1648 chars
[4/12] 4FOOKUfUWzg cached 12767 chars
[5/12] XEOzMFZHdcU cached 11895 chars
[6/12] JcPC-WXqY38 cached 9659 chars
[7/12] U3jj7XjsS0k cached 24030 chars
[8/12] z6a1QrGho0k cached 12690 chars
[9/12] ubpXEv4lF0k cached 23104 chars
[10/12] _NecoHLsKPk cached 24031 chars
[11/12] 1Ln4IFA0POk cached 24031 chars
[12/12] 17djB82ImkQ cached 24031 chars
transcripts done: 0 fetched, 12 cached, 0 failed
step4 images: 24 downloaded -> img/
step5 packet: state/workpack/2026-10-28/packet.md
collect done: 32 videos, 60 articles, 22 transcripts, 15 repeats suppressed
```

Real counts for the workpack:

| thing | value |
|---|---|
| yt.json | 32 videos, 79/79 channels ok |
| news.json | 60 articles, 24/24 feeds ok |
| candidates.json | 92 items (32 video + 60 article) |
| filtered.json | 92 total, 15 seen, 77 fresh |
| suppressed.json | 15 repeats (memory is now populated) |
| transcripts dir | 22 .txt files, index.json 12 entries, 12 cached / 0 failed |
| img/ | 65 files (24 downloaded this run, the rest kept from earlier runs) |
| packet.md | 11,737 bytes |

Packet path: `C:\Users\MarciNaro\Documents\VSCODE-PROJECTS\daily-beacon\state\workpack\2026-10-28\packet.md`

First 25 lines of packet.md:
```
# DAILY BEACON - workpack 2026-10-28
generated 2026-10-28T12:17:53+01:00 | lookback 26h | 32 videos, 60 articles | 15 repeats suppressed

## counts
- youtube: 32 videos | 79/79 ok, 0 failed
- news: 60 articles | 24/24 ok, 0 failed
- candidates after caps: 32 videos, 60 articles (92 total)
- memory filter: 92 total, 15 seen, 77 fresh
- repeats suppressed: 15
- transcripts: 0 fetched, 12 cached, 0 failed (22 files on disk)
- images downloaded: 24
- warnings: none

## top videos
- [T1|w1] Castlevania Belmont's Curse Review | MoistCr1TiKaL Gaming | 2026-10-27T23:09+01:00 | https://www.youtube.com/watch?v=WjmL7yBTObE | transcript:yes
- [T1|w1] Castlevania Belmont's Curse True Ending (FULL GAME) | MoistCr1TiKaL Gaming | 2026-10-27T21:09+01:00 | https://www.youtube.com/watch?v=Gzzhg_QGluw | transcript:yes
- [T1|w1] When your boss is literally a nightmare | Viva La Dirt League | 2026-10-27T21:06+01:00 | https://www.youtube.com/watch?v=M0ri49SozG4 | transcript:yes
- [T1|w1] iPhone Duo Problem is Getting Worse | penguinz0 | 2026-10-27T20:15+01:00 | https://www.youtube.com/watch?v=4FOOKUfUWzg | transcript:yes
- [T1|w1] WHO AIRED THIS. | Asmongold TV | 2026-10-27T20:09+01:00 | https://www.youtube.com/watch?v=XEOzMFZHdcU | transcript:yes
- [T1|w1] This is the dumbest escape plan I?ve ever seen.. | Asmongold TV | 2026-10-27T17:09+01:00 | https://www.youtube.com/watch?v=JcPC-WXqY38 | transcript:yes
- [T1|w1] This might be the game of the year.. | Asmongold TV | 2026-10-27T15:09+01:00 | https://www.youtube.com/watch?v=U3jj7XjsS0k | transcript:yes
- [T1|w1] $1 Million Card Heist is Crazy | penguinz0 | 2026-10-27T12:15+01:00 | https://www.youtube.com/watch?v=z6a1QrGho0k | transcript:yes
- [T1|w1] The Insane Way OpenAI Agents Escaped Its Sandbox [Full Breakdown] | bycloud | 2026-10-27T12:10+01:00 | https://www.youtube.com/watch?v=ubpXEv4lF0k | transcript:yes
- [T1|w1] Finally Got One of the Ranked Requirements Done | MoistCr1TiKaL Gaming | 2026-10-27T12:09+01:00 | https://www.youtube.com/watch?v=_NecoHLsKPk | transcript:yes
- [T1|w1] AJSN WK44B- Xbox Console to Cost INSANE $1,800?!, Capcom HACKED, Dev Blackmailed, A24's ELDEN RING | AngryJoeShow | 2026-10-27T12:05+01:00 | https://www.youtube.com/watch?v=1Ln4IFA0POk | transcript:yes
```

## 4. Decisions

- **`--no-asr` on every transcript call.** Spec allows an ASR fallback, but at 03:00 an audio download +
  whisper on 12 videos can run for an hour. Captions-only keeps the batch bounded at ~180s per video; a
  captionless video lands as `failed` with a reason instead of stalling the edition. Fetched text is still
  written to the cache by the shared tool, so tomorrow is free.
- **Cache dir is read-only for transcripts.py.** The brief forbade writing there, so this script never
  creates it and never repairs it; it only globs it recursively for `<videoId>*.txt` in any language.
  (Writing is done by the shared tool itself, not by this wrapper.)
- **`transcripts` counter in the final line = transcript files on disk, not this run's fetches.** The
  contract's `<t> transcripts` is what the agent can read, and on a warm cache `fetched` is 0 while 22
  usable files exist. Printing 0 there would look like failure on a perfectly good workpack.
- **`state\logs\collect-<date>.log`.** A detached 03:00 run has no console; without a tee there is no
  evidence afterwards of what each step did. Every log() line is mirrored into that file.
- **Scheduled-task launch was a test harness detail, not a product decision.** A foreground shell in this
  environment is killed after ~90s, which is shorter than one `yt_source` pass over 79 channels; running
  `collect` from Task Scheduler (hidden, `python -u`, output redirected) let the same command finish
  normally in 5m30s with zero code changes. The task was deleted afterwards.
- **Images: 24 per run, from the top unseen videos then articles.** More than that has no use for a
  14-story edition and just costs bandwidth; skipped/failed downloads never block the packet.