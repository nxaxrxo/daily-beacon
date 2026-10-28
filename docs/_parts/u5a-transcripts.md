# u5a - scripts/transcripts.py

Delivered: `scripts/transcripts.py` - batch, cache-first, sequential transcript fetcher.

## Contract compliance
- CLI `--candidates --out-dir [--limit] [--ids] [--max-chars] [--timeout] [--root]`, argparse `--help`.
- Last stdout line `transcripts done: <fetched> fetched, <cached> cached, <failed> failed`; exit 0 always,
  2 only when `--candidates` is unreadable/missing and no `--ids`.
- Selection: `kind == "video"`, `seen is not True`, sort `(tier asc, publishedAt desc)`, missing tier = 9,
  cap `--limit` else `min(12, settings.max_videos_total)`. `--ids` overrides selection entirely (spaces
  stripped, empties skipped, limit not applied).
- Cache first: `notes/yt-cache/<id>*.txt` copied to out-dir as `cached`, wrapper never called.
- Fetch: sequential subprocess, `cwd` = private dir under `state/tmp`, per-video `--timeout` (180s),
  `TXT <path>` parsed from stdout with `<id>*.txt` glob fallback; produced file copied to cache and out-dir
  (never over a non-empty cache entry).
- Failure: ASCII reason from tool stdout/stderr, `<= 200` chars, lands in index.json, batch continues.
- Trim: head + tail halves with a `[... trimmed N chars ...]` line, result `<= max_chars`.
- `index.json`: `{"<id>": {"status": "ok|cached|failed", "chars": int, "reason": str|null}}`, one per attempt.
- Progress `[3/12] <id> cached 18234 chars`, ASCII only. `--max-chars` defaults to
  `settings.transcript_max_chars` (24000). `--root` = `Path(__file__).resolve().parents[1]`. utf-8 opens,
  guarded stdout reconfigure, stdlib only.

## Verification (real captured output)

### 1. `--help`
```
usage: transcripts.py [-h] [--candidates CANDIDATES] --out-dir OUT_DIR
                      [--limit LIMIT] [--ids IDS] [--max-chars MAX_CHARS]
                      [--timeout TIMEOUT] [--root ROOT]
Batch, cache-first, sequential transcript fetcher for the daily workpack.
```
(full per-option help rendered; `EXIT=0`)

### 2. Fixture
Real recent ids from `scripts/yt_source.py --hours 720 --channel UCq6VFHwMzcMXbuKyG7SQYIg`: two
`kind="video"` (`Pw81QQyFROI`, `4FOOKUfUWzg`, tier 1) plus one `kind="article"` that must be ignored.
Only `[1/2]` and `[2/2]` ran - the article never entered the selection.

### 3. Run 1 - `--limit 2 --max-chars 4000`
```
[1/2] Pw81QQyFROI cached 4030 chars
[2/2] 4FOOKUfUWzg ok 4030 chars
transcripts done: 1 fetched, 1 cached, 0 failed
EXIT=0
```
`Pw81QQyFROI` was already cached; only `4FOOKUfUWzg` was actually fetched.

### 4. Run 2 - identical arguments (cache proof)
```
[1/2] Pw81QQyFROI cached 4030 chars
[2/2] 4FOOKUfUWzg cached 4030 chars
transcripts done: 0 fetched, 2 cached, 0 failed
EXIT=0
```
0 fetched: the cache entry written by run 1 was reused, no refetch.

### 5. Trim marker
```
4FOOKUfUWzg.txt | marker: True | N = 8767  | len = 4031 | <= max_chars+60 (4060): True
Pw81QQyFROI.txt | marker: True | N = 14182 | len = 4031 | <= max_chars+60 (4060): True
TRIM MARKER OK on every transcript
```
Sources 12767 and 18182 chars, both capped at 4031 written chars.

### 6. `index.json`
```
{ "Pw81QQyFROI": {"status":"cached","chars":4030,"reason":null},
  "4FOOKUfUWzg":  {"status":"cached","chars":4030,"reason":null} }
```
Out-dir: `Pw81QQyFROI.txt`, `4FOOKUfUWzg.txt`, `index.json`.

## Extra checks
- Failure is data: bogus id -> `[3/3] AAAAAAAAAAA failed 0 chars - timeout after 60s`, then `0 fetched, 2 cached, 1 failed`, exit 0, `"reason": "timeout after 60s"`.
- Missing `--candidates` / unreadable candidates -> one stderr line, `EXIT=2`. No `--max-chars` ->
  24000 used (18182 / 12767 chars untrimmed). No `--limit` -> `min(12, 40)` = 12. `--ids` without
  `--candidates` -> `1 cached`, exit 0.
- Sorting unit-checked: (t1 newest), (t1 older), (t3 newest), (t1 seen), (no tier), a `short` and an
  `article` -> `[t1-newest, t1-older, t3, t9]`; seen/short/article excluded.

## Bug found and fixed
A real videoId may start with `-` (`-Y6Cp6e-VbI`, videogamedunkey). Passed bare, the wrapper's argparse read
it as a flag (`error: the following arguments are required: video`) and the video failed for a reason
unrelated to captions. Fixed by terminating the wrapper command line with `--` before the id; re-verified,
that id then fetched normally (`OK source=auto lang=en segments=127 chars=3336`).

## Notes / risks
- `yt_transcript.py` retries four routes with sleeps, so a dead id can burn the full per-video timeout.
  Default 180s kept; `--timeout` lowers it.
- Temp work dirs sit under `<root>/state/tmp` and are removed per video in `finally` - no ASR scratch left.
- The shared cache is only read and appended to; nothing in it is deleted or modified.

## Files
- `scripts/transcripts.py` (new)
- `docs/_parts/u5a-transcripts.md` (this file)