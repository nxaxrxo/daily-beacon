# DAILY BEACON — MASTER SPEC (the contract)

Project root: `C:\Users\MarciNaro\Documents\VSCODE-PROJECTS\daily-beacon`
Status: greenfield. Directories already created: config/ scripts/ editions/ site/ state/ docs/

Purpose: every night at 03:00 a scheduled OpenCode session collects what happened in the last 24h in
the owner's interest areas (YouTube creators + gaming/AI/tech news), writes a funny, optimistic
dark-mode newspaper edition, rebuilds the static site and pushes it to GitHub Pages.

Golden rule: **scripts do the deterministic lifting; the agent does the judging and the writing.**
No script ever decides what is "interesting". No agent ever hand-edits generated HTML.

---

## 1. DIRECTORY CONTRACT

```
config/
  channels.json      # watched YouTube creators (seeded from youtube-manager/channel_portfolio.json)
  feeds.json         # RSS news sources
  interests.md       # the interest reference sheet (human+agent readable rubric)
  settings.json      # lookback hours, caps, paths, publish toggle
scripts/
  yt_source.py       # channels -> new videos in window
  news_source.py     # feeds -> normalised news candidates
  memory.py          # seen-store (sqlite) - the anti-repeat memory
  transcripts.py     # batch transcript fetch via tools/yt_transcript.py, cached
  run_daily.py       # orchestrator: collect -> work packet for the agent
  build_edition.py   # editions/<date>.json -> site/index.html + assets
  publish.py         # git commit + push to GitHub Pages
  doctor.py          # self-check: config valid, paths writable, network reachable, site builds from fixture
editions/
  YYYY-MM-DD.json    # THE edition content (hand-editable, agent-written)
  archive/           # older editions moved here after N days (keep last 30 in root)
site/
  index.html         # generated - never hand-edit
  archive.html       # generated index of past editions
  assets/<date>/*.jpg# downloaded + optimised images
  style.css, app.js  # static, versioned by build_edition.py
state/
  seen.sqlite        # memory store
  workpack/<date>/   # candidates.json, transcripts/, img/, packet.md
docs/
  AGENTS.md          # the 03:00 run playbook (agent reads this first)
  SPEC.md            # this file
```

Every script: Python 3.11, stdlib + already-installed pkgs only (`requests`, `feedparser`,
`beautifulsoup4`, `Pillow`). No new pip installs without asking. No npm. Each script is CLI-first,
`--help` works, exit 0 on success / non-zero with a clear stderr message on failure, and prints a
short human line summarising what it did.

UTF-8 everywhere: open files with `encoding="utf-8"`. On Windows never rely on default encoding.
Never print emoji to a redirected stdout (cp1252 crashes) — use plain ASCII in console output.

---

## 2. SCHEDULER PLUGIN — recurring extensions

File: `C:\Users\MarciNaro\.config\opencode\plugins\scheduler\index.ts` (edit in place; it reloads on
the next OpenCode start). `~\.opencode-runtime\scheduler\scheduler.log` is the runtime log — watch it.

Already supported: `once:YYYY-MM-DDTHH:mm`, `every:30m|2h|3d`, `daily:HH:MM`,
`weekly:mon@HH:MM`. Catch-up already exists (a missed slot fires on the next tick).

ADD, keeping every existing behaviour intact:
| format | meaning |
|---|---|
| `every:Nd` | already works — keep, verify with a test |
| `days:N@HH:MM` | every N days at a wall-clock time (catch-up aware, anchor = createdAt/lastFired) |
| `weekly:mon,wed,fri@HH:MM` | multiple weekdays in one record (comma-separated, 1..7 days) |
| `hourly:MM` | every hour at minute MM (00-59) |
| `monthly:N@HH:MM` | day-of-month N (1-31; clamp to month length), at HH:MM |

Rules: `parseWhen()` returns `{ok,spec}` — extend the spec kinds, never break the existing return
shape. `computeDue()` must stay strictly "next occurrence after ref". Every new kind must be
catch-up safe: if the machine was off for a week, it fires ONCE, not seven times. Update `USAGE`
and the header comment block. Update `C:\Users\MarciNaro\.config\opencode\tools\schedule.py` ACCEPTED
text to match (that file only builds a request file; do not add a second writer of schedules.json).
Write `scripts/test_scheduler_formats.mjs` (plain node, no deps, import the plugin's parseWhen/
computeDue via a tiny re-export shim or dynamic import) covering: valid, invalid, and catch-up maths
for every kind including the old ones. It must run and pass: `node scripts/test_scheduler_formats.mjs`.

**Error ownership does not change**: the plugin only fires; the watcher owns everything after.

---

## 3. CONFIG FILES

`config/settings.json`
```json
{
  "timezone_note": "all times local",
  "lookback_hours": 26,
  "max_videos_per_channel": 3,
  "max_videos_total": 40,
  "max_news_items": 60,
  "short_max_seconds": 90,
  "transcript_max_chars": 24000,
  "edition_max_stories": 14,
  "edition_min_stories": 5,
  "repeat_topic_cooldown_days": 21,
  "keep_editions": 30,
  "site_base_url": "",
  "publish": true
}
```

`config/channels.json` — array of
`{"id":"UC...","name":"AngryJoeShow","tier":1,"tags":["gaming","news"],"enabled":true,"note":""}`
`tier` 1 = must-check daily, 2 = check, 3 = only if something big. Seed from
`~\.config\opencode\home\youtube-manager\channel_portfolio.json` (152 subscriptions) + the names in
`~\.config\opencode\home\_mem\memory.md` (search: "Current watch list" around line 1745). Include
ALL of: Asmongold (+TV/Clips/Shorts/Gaming variants), penguinz0/MoistCr1TiKaL, AngryJoeShow,
videogamedunkey, MeatCanyon/Papa Meat, Viva La Dirt League, Flashgitz, Fern, Visual Venture, POI,
Cryton(if present), Ahoy, Internet Historian, NakeyJakey, Drew Gooden, Super Eyepatch Wolf, h3h3,
Gigguk, Dr Insanity, Naked Criminal, Vsauce, ANATOLY, MrBeast, JT Music, Teminite, skeler., AI
Explained, Matt Wolfe, AI Search, Two Minute Papers, bycloud, Dr. Plants, Odd Animal Specimens,
Scary Interesting, blameitonjorge, Nexpo, Curious Archive, Real Science. Tier 3 for meme/short
channels. Mark every guessed tier with `"note":"tier guessed - confirm"`.

`config/feeds.json` — array of
`{"name":"PC Gamer","url":"https://www.pcgamer.com/rss/","tags":["gaming","news"],"enabled":true,"weight":1}`
Seed 18-25 working feeds, verified reachable with a real HEAD/GET during the build: gaming news
(PC Gamer, RPS, Eurogamer, GamesIndustry.biz, VGC, GameSpot news, IGN games), gaming-tech/hardware
(Digital Foundry, Tom's Hardware), AI (The Verge AI, Ars Technica, TechCrunch AI, VentureBeat AI,
MIT Tech Review), games-industry business (GamesIndustry.biz, Game Developer), and one
Ukraine/world-awareness feed used at low weight (e.g. Kyiv Independent). Explicitly EXCLUDE
politics-dominant outlets. Record the HTTP status of each feed in `docs/FEEDS-CHECK.md`.

`config/interests.md` — the reference sheet the 3AM agent reads. Written from real memory, not
invented: run `python "$env:USERPROFILE\.config\opencode\tools\mem_search.py" "<query>"` for
(youtube, gaming, ai models, tech, warframe, hytale, godot, roblox, ukraine, anime, music, hardware,
memes) and distil into: LOVES / LIKES / NEUTRAL / DISLIKES / NEVER + a scoring rubric (how much an
item matters, how to trade off "let's play" vs "trailer reaction", the cooldown rule, tone rules).
Facts only, no flattery, cite the memory line ranges where it matters.

---

## 4. MEMORY — `scripts/memory.py` (the anti-repeat brain)

SQLite at `state/seen.sqlite`.
```sql
items(key TEXT PRIMARY KEY, kind TEXT, title TEXT, url TEXT, source TEXT,
      first_seen TEXT, edition TEXT, tags TEXT)
topics(topic TEXT PRIMARY KEY, last_covered TEXT, times INTEGER, last_edition TEXT)
editions(date TEXT PRIMARY KEY, path TEXT, items INTEGER, created TEXT)
```
Keys: video -> `yt:<videoId>`; news -> `url:<sha1(normalised url)[:16]>` plus `title:<sha1(normalised
title)[:16]>` as a second guard. Normalisation = lowercase, strip tracking params, strip punctuation,
collapse whitespace.

CLI:
- `memory.py filter --candidates state/workpack/<date>/candidates.json`
  -> writes `filtered.json`, each item gains `seen: bool`, `seen_reason`, `topic_hits: []`.
  Also emits `recent_topics`: topics covered in the last `repeat_topic_cooldown_days`.
- `memory.py mark --edition editions/<date>.json` -> records every story + topic. Idempotent.
- `memory.py query --topic gta6 --days 60` -> when it was last covered, how many times.
- `memory.py stats` -> counts, DB size, last edition.
- `memory.py prune --days 400` -> drop ancient rows.
Behaviour: never delete what an edition covered. Re-running `mark` twice must not double-count
`times` (dedupe on edition date + key). A topic seen N days ago is still "seen" — the AGENT decides
whether a comeback is worth it; the DB only reports.

---

## 5. SOURCES

`scripts/yt_source.py`
- Input: `config/channels.json`, lookback window, `--out` path.
- Primary: YouTube channel RSS `https://www.youtube.com/feeds/videos.xml?channel_id=UC...` with a
  browser User-Agent (verified working 2026-10-28). Gives id/title/published/thumbnail.
- Enrichment + fallback: Invidious `https://yt.chocolatemoo53.com/api/v1/channels/<id>/videos`
  (verified working, gives `viewCount`, `lengthSeconds`, `published`). Try the API first actually —
  it gives length + views in one call, which the RSS lacks. Use RSS as fallback.
- Output items: `{source:"youtube", videoId, channel, channelId, title, publishedAt, url,
  thumbnail, lengthSeconds, views, tier, tags, kind:"video"|"short"}` + `thumb_local` filled later.
- Serial with a short delay (never hammer); per-channel try/except, one failed channel must not kill
  the run; report `channels_ok/channels_failed` in the summary line.
- `--channel UC...` single-channel mode for testing. `--no-shorts` filter by `short_max_seconds`.

`scripts/news_source.py`
- Input: `config/feeds.json`. feedparser with 20s timeout, browser UA, per-feed try/except.
- Item: `{source:"news", title, url, sourceName, feedTags, publishedAt, summary(<=600 chars, tags
  stripped), image (best of media:content / media:thumbnail / enclosure / first <img> in summary /
  og:image lazy fetch - only when cheap), kind:"article"}`.
- Dedupe inside the run by normalised title/url so 5 feeds carrying the same story collapse to one
  (keep the highest-weight source, note the others in `also_on`).
- `--out` path, `--limit`.

`scripts/transcripts.py`
- Batch wrapper around `$env:USERPROFILE\.config\opencode\tools\yt_transcript.py` (route: captions
  first, ASR fallback). Cache dir `~\.config\opencode\notes\yt-cache` is shared — check it first and
  never refetch.
- SEQUENTIAL always (ASR is GPU-bound). Per-video timeout, per-video failure tolerated.
- Output per video: `state/workpack/<date>/transcripts/<videoId>.txt`, truncated head+tail to
  `transcript_max_chars` with a `[... trimmed N chars ...]` marker in the middle.
- `--ids` list or `--candidates` json; `--limit N`; prints fetched/cached/failed counts.

`scripts/run_daily.py` (orchestrator, the thing the 03:00 agent runs FIRST)
`python scripts/run_daily.py collect [--date YYYY-MM-DD] [--hours 26]`
1. yt_source -> news_source -> merged `candidates.json` (each item with `score_hint` = tier/weight
   only, no editorialising).
2. `memory.py filter` -> `filtered.json` (drop seen items, keep them in `suppressed.json` for audit).
3. `transcripts.py` on the top N unseen videos (video only, ordered by tier then recency — cap by
   `max_videos_total`).
4. Download candidate thumbnails / article images to `state/workpack/<date>/img/` (Pillow-verified,
   <8MB, jpg/png/webp only, skipped silently on failure).
5. Write `state/workpack/<date>/packet.md`: a compact human/agent briefing — the day's candidate
   list with one line each, which videos have transcripts, which items are repeats, what topics are
   cooling down, plus the exact next commands. THIS is what the agent reads instead of raw JSON.
6. Print `collect done: <n> videos, <n> articles, <n> transcripts, <n> repeats suppressed`.

---

## 6. EDITION SCHEMA — `editions/YYYY-MM-DD.json` (the easy-to-edit content file)

```json
{
  "date": "2026-10-28",
  "number": 1,
  "generatedAt": "2026-10-28T03:14:00+01:00",
  "masthead": "THE DAILY BEACON",
  "tagline": "Your 3am briefing, slightly unhinged",
  "weatherStrip": "one-line mood of the day",
  "sections": [
    {
      "id": "gta6-trailer",
      "kind": "lead|story|video|quick|quote",
      "priority": 100,
      "kicker": "GAMING",
      "headline": "...",
      "standfirst": "one sentence deck",
      "body": ["paragraph", "paragraph"],
      "image": {"src": "../state/workpack/2026-10-28/img/abc.jpg", "alt": "...", "credit": "YouTube / AngryJoeShow"},
      "source": {"label": "AngryJoeShow", "url": "https://youtu.be/xyz"},
      "tags": ["gta6"],
      "whyItMatters": "one line",
      "aside": "the joke / the aside, optional"
    }
  ],
  "quickHits": [{"text": "...", "url": "https://..."}],
  "signoff": "one closing line"
}
```
- `kind` drives layout: `lead` = hero (exactly one per edition, else the builder promotes the first),
  `story` = standard article, `video` = thumbnail-led card, `quick` = one-liner, `quote` = pull quote.
- Body supports ONLY inline `**bold**`, `*italic*`, `[text](url)`. Everything else is escaped.
- `image.src` may be an http(s) URL or a local path relative to the edition file — the builder
  resolves, downloads if remote, optimises (max width 1400, JPEG q82), and rewrites the path.
- Section count drives page length by design. 5 stories = one screen, 14 = a long scroll. That is
  the intended behaviour, not a bug.
- Validation: `build_edition.py --check` fails loudly on missing keys, >1 lead, empty body, bad
  inline markup, or a story with no source. Never build a broken edition silently.

---

## 7. SITE — `scripts/build_edition.py`

`python scripts/build_edition.py --date 2026-10-28 [--open]` -> `site/index.html` + `site/assets/<date>/`
+ `site/archive.html`. Also `--fixture` to build from a test edition without touching real state.

Design requirements (non-negotiable):
- **Dark-mode newspaper.** Near-black paper (#0b0b0d / #111114), warm off-white ink (#ece7dd),
  hairline rules, real masthead with thin double rules, small-caps kickers with letterspacing,
  serif display face for headlines + a clean sans for body/labels. System font stacks only, no
  external font CDN dependency at runtime (a Google-Fonts link may be added with a local fallback).
- **Different every day, always readable**: the builder derives a seed from the date and rotates
  (a) accent colour from a curated 8-colour palette, (b) one of 3 lead layouts (hero-left,
  hero-centred, hero-stacked with a side rail), (c) one of 2 headline scale sets, (d) the
  section-order emphasis (lead first vs "Quick Hits" rail first). Never rotate into unreadable
  contrast — light-on-dark minimum ratio 4.5:1 for body text.
- **Mobile first**: single column < 760 px, fluid type via clamp(), thumbnails full-bleed, tap
  targets >= 44 px, no horizontal scroll at 320 px. Sticky compact masthead on scroll.
- **Images**: lazy-loaded, aspect-ratio boxes to prevent layout shift, `alt` mandatory, credit line
  under the image, graceful text-only fallback when an image fails.
- **Navigation**: a top index of the day's sections (anchor links) + a "back to top" pill; video
  cards link straight to the video (new tab). Every section has a stable `#id`.
- **Small print**: edition number, generated timestamp, "what was covered and suppressed" count
  from memory.py stats, link to archive.html, a line stating the previous 30 editions are archived.
- Zero external JS libraries. Inline `app.js` only for: smooth anchor scroll, reading progress bar,
  image error fallback, and a "compact/dense" density toggle persisted in localStorage.
- Output must be a single HTML file + one CSS + one JS + images (no bundler, no build step).
- Print stylesheet: white background, ink text, no nav (one `@media print` block).
- Also write `site/edition-YYYY-MM-DD.html` copies? NO — keep one index.html plus archive links to
  `editions/<date>.html` generated as static snapshots (`site/archive/YYYY-MM-DD.html`) so old
  editions stay browsable after index.html moves on.

---

## 8. PUBLISH — `scripts/publish.py` + GitHub Pages

- Repo: GitHub account `nxaxrxo` (gh CLI already authenticated). Repo name `daily-beacon` unless the
  owner says otherwise. Create it with `gh repo create` (public — Pages needs it) if missing.
- `publish.py` steps: `--check` (git status, is the build newer than the last commit) -> `git add -A`
  -> commit `"edition: YYYY-MM-DD"` (skip if nothing staged) -> `git push` -> print the live URL.
  Never force-push. Never commit secrets (`config/` holds no tokens; state/seen.sqlite is fine to
  commit but keep it out of the Pages artifact).
- Deploy: `.github/workflows/pages.yml` using `actions/upload-pages-artifact` with `path: site` and
  `actions/deploy-pages`. Enable via `gh api repos/nxaxrxo/daily-beacon/pages -X POST -f build_type=workflow`
  (fall back to `-X PUT` if it already exists). Verify the final URL returns 200 with the masthead.
- `.gitignore`: `state/workpack/`, `__pycache__/`, `*.pyc`, `site/assets/*/tmp*`.
- README.md: what it is, how the 03:00 run works, how to edit an edition by hand, how to rebuild,
  how to add a channel/feed, how to change the schedule, troubleshooting.
- `site_base_url` in settings.json is filled with the real Pages URL after the first deploy.

---

## 9. THE 03:00 AGENT PLAYBOOK — `docs/AGENTS.md`

The file the scheduled session reads first. Must contain, in order and unambiguous:
1. Where you are, what today's edition must contain, and the hard rule that you never invent news.
2. `run_daily.py collect` -> read `packet.md` -> read 3-8 transcripts (in slices) -> for the rest,
   judge from title/source/thumbnail.
3. Editorial rubric: what is worth the front page, how to weigh a creator's take on a big event vs
   a routine let's-play, the ~3-week topic cooldown, "never repeat what memory says was covered",
   the tone (funny, warm, optimistic even on bad news, never cruel, no politics unless it materially
   affects people), length discipline (5-14 stories, one lead).
4. Write `editions/<date>.json` (schema + a filled example), then:
   `build_edition.py --date <date>` -> `publish.py` -> `memory.py mark` -> done.
5. Failure handling: if collection fails, still publish a short edition saying what failed (never a
   blank page / never silence); if publishing fails, leave the built site on disk and say so.
6. Never open windows, never ask questions (unattended), never touch other projects.
7. Finish with a 3-line summary written into `docs/runs/YYYY-MM-DD.md`.

---

## 10. ACCEPTANCE — what "done" means

- `node scripts/test_scheduler_formats.mjs` passes; every old schedule format still parses.
- `python scripts/doctor.py` passes: config valid, all feeds reachable, memory DB writable, a fixture
  edition builds, site HTML validates (no unclosed tags via a simple stack check), page < 3 MB
  without images.
- One REAL edition generated end-to-end for today's date, published, and the live URL returns 200.
- `docs/AGENTS.md` complete enough that a fresh agent can run tomorrow's edition without asking.
- No file outside this project is modified except the scheduler plugin + `tools/schedule.py`
  ACCEPTED text, both named above.
- Nothing visible on the owner's screen: no browser, no window, no folder opens. All verification is
  headless (curl/Invoke-WebRequest/HTML parse).

Write every decision you made where the spec was silent into `docs/DECISIONS.md` (one line each).
