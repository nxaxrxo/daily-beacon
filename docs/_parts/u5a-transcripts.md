# u5a - transcripts.py

Delivered: `scripts/transcripts.py` - batch, cache-first, SEQUENTIAL transcript fetcher wrapping
`%USERPROFILE%\.config\opencode\tools\yt_transcript.py`.

## Contract (CONTRACTS.md item 9)
`python scripts/transcripts.py --candidates <filtered.json> --out-dir <dir> [--limit N] [--ids a,b,c]
[--max-chars 24000] [--timeout 180] [--root PATH]`
Last stdout line exactly `transcripts done: <fetched> fetched, <cached> cached, <failed> failed`.
Exit 0 always (a per-video failure is data); exit 2 only when `--candidates` is unreadable and no `--ids`.

## Behaviour
- Selection: `kind == "video"`, `seen is not True`, sorted `(tier asc, publishedAt desc)`, missing tier
  treated as 9, capped by `--limit` else `min(12, settings.max_videos_total)`. `--ids` overrides selection.
- Cache first: `~\.config\opencode\notes\yt-cache\<videoId>*.txt` is read and copied into the out-dir as
  `cached`; the wrapper is never invoked for a hit, and nothing in the shared cache is deleted or modified.
- Fetch: one subprocess at a time (never parallel - ASR is GPU-bound), per-video timeout, `--out` into a
  private scratch dir, `TXT <path>` parsed from the tool's stdout with a `<id>*.txt` glob fallback.
- Trim: head + tail halves with a literal `[... trimmed N chars ...]` marker, result <= `max_chars`.
- `index.json`: `{"<videoId>": {"status": "ok|cached|failed", "chars": int, "reason": str|null}}`.
- ASCII console, UTF-8 writes, `--root` default `Path(__file__).parents[1]`.

## Verification (real captured runs)
```
python scripts/transcripts.py --help                     -> full usage block, exit 0
[1/2] Pw81QQyFROI cached 4030 chars
[2/2] 4FOOKUfUWzg ok 4030 chars
transcripts done: 1 fetched, 1 cached, 0 failed        EXIT=0
```
Second identical run (cache proof):
```
[1/2] Pw81QQyFROI cached 4030 chars
[2/2] 4FOOKUfUWzg cached 4030 chars
transcripts done: 0 fetched, 2 cached, 0 failed        EXIT=0
```
Trim marker:
```
4FOOKUfUWzg.txt | marker True | N=8767  | len 4031 | <= max_chars+60 True
Pw81QQyFROI.txt | marker True | N=14182 | len 4031 | <= max_chars+60 True
TRIM MARKER OK on every transcript
```
Failure is data: a bogus id produced `[3/3] AAAAAAAAAAA failed 0 chars - timeout after 60s`, then
`0 fetched, 2 cached, 1 failed`, exit 0, with `"reason": "timeout after 60s"` in index.json.

In the live workpack: `transcripts done: 0 fetched, 12 cached, 0 failed`, 20 .txt files on disk and
`index.json` statuses `{cached: 12}` - the cache dir is doing its job.

## Bug found and fixed
A real videoId may begin with `-` (`-Y6Cp6e-VbI`, videogamedunkey). Passed bare, the wrapper's argparse read
it as a flag and the video failed for a reason unrelated to captions. Fixed by terminating the wrapper's
command line with `--` before the id; re-verified, that id then fetched normally.

## Risk noted
`yt_transcript.py` retries four routes with sleeps, so a genuinely dead id can burn the full per-video
timeout. Default 180s kept; `--timeout` lowers it.
