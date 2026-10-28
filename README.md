# The Daily Beacon

A personal newspaper, compiled every second night at 03:00 from the YouTubers I actually watch and the news
feeds I actually care about. It writes itself, builds itself, and publishes itself.

**Live site:** `https://nxaxrxo.github.io/daily-beacon/`

---

## What happens at 03:00

An OpenCode session fires and works through `docs/AGENTS.md`:

1. `run_daily.py collect` pulls the last 50 hours of uploads (48 enabled channels) and RSS items (38 feeds),
   filters out anything already covered, fetches transcripts for the best videos, downloads images,
   and writes `state/workpack/<date>/packet.md` - one readable briefing instead of raw JSON.
2. The agent reads that packet, reads 3-8 transcripts, and judges what is worth printing using
   `config/interests.md` as the rubric.
3. It writes `editions/<date>.json` - plain content, no HTML.
4. `build_edition.py` renders it into a dark-mode newspaper that looks different every day.
5. `publish.py` pushes it and mirrors `site/` onto the `gh-pages` branch, which is what Pages
   actually serves - a push to `main` alone would leave the live page unchanged.
6. `memory.py mark` records every story so tomorrow cannot repeat it.

If the PC was off at 3am, the scheduler's catch-up fires the run as soon as OpenCode next loads.
One run, not seven.

## Why it never repeats itself

`state/seen.sqlite` tracks every story and topic ever printed. A news item is stored under both a
canonical URL key and a title key, so the same story from a different outlet is still caught. Topics
get a 21-day cooldown: after that a subject can return, but only with a genuinely new development,
and framed as a follow-up rather than fresh news.

### The month-later check

```powershell
python scripts\memory.py digest
```

Prints what the Beacon has covered: edition count, most-covered topics, what is cooling down
(and therefore must not be re-reported as news), and which topics have been quiet 30+ days and
are ripe for a genuine follow-up. Nothing here is automatable into a story - it is a reminder
that the subject exists, not a licence to write about it again without something new.

## Editing by hand

The content is just JSON. Open `editions/<today>.json`, change the words, rebuild:

```powershell
cd "$env:USERPROFILE\Documents\VSCODE-PROJECTS\daily-beacon"
python scripts\build_edition.py --check    # validate
python scripts\build_edition.py            # render
python scripts\publish.py                  # ship it
```

`sections[]` drives the layout: `lead` (hero, exactly one), `story`, `video`, `quote`, `quick`.
Body text supports only `**bold**`, `*italic*` and `[links](url)`. Point `image.src` at a URL or a
local file and the builder downloads, resizes and embeds it.

## Adding a creator or a feed

- Creator: add `{"id": "UC...", "name": "...", "tier": 1|2|3, "tags": [...], "enabled": true}` to
  `config/channels.json`. Tier 1 = always checked, tier 3 = only if something big.
- Feed: add `{"name": "...", "url": "...", "tags": [...], "weight": 1-3, "enabled": true}` to
  `config/feeds.json`.
- Taste itself lives in `config/interests.md` - edit that and the 3am judgement changes.

## Changing the schedule

```powershell
python "$env:USERPROFILE\.config\opencode\tools\schedule.py" list
```

The live schedule is `days:2@03:00`. Supported formats: `once:2026-10-30T09:00`, `every:30m`, `days:3@09:00`,
`hourly:15`, `days:2@03:00`, `weekly:mon@09:00`, `weekly:mon,wed,fri@09:00`, `monthly:1@09:00`.

## Scripts

| script | job |
|---|---|
| `yt_source.py` | channels -> new videos in the window |
| `news_source.py` | feeds -> deduped articles with images |
| `transcripts.py` | batch transcript fetch (cache-first, sequential) |
| `memory.py` | the anti-repeat store; `filter`, `mark`, `query`, `stats`, `digest`, `prune`, `selftest` |
| `run_daily.py` | the orchestrator that produces `packet.md` |
| `build_edition.py` | edition JSON -> the site |
| `publish.py` | commit, push, verify the live URL |
| `test_scheduler_formats.mjs` | proves every scheduler format still parses |

## Troubleshooting

- **Nothing was published.** Check `docs/runs/<date>.md` and `state/workpack/<date>/packet.md`.
  A quiet day produces a short edition on purpose; silence means something failed.
- **The collection died halfway.** Rerun with `--reuse-source` so finished steps are not repeated.
- **A feed stopped working.** `python scripts\news_source.py --out test.json` names the failing feeds;
  check `docs/FEEDS-CHECK.md` for what was verified last time.
- **Scheduler not firing.** Read `~\.opencode-runtime\scheduler\scheduler.log`.

---

Built for one reader. No analytics, no accounts, no tracking.
