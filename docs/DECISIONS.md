# DECISIONS — where the spec was silent

One line each. Newest decisions at the bottom of their section.

## Site / presentation (U6)

- Wrote `docs/SITE-CONTRACT.md` as the binding HTML/CSS/JS interface, because `build_edition.py`,
  `style.css` and `app.js` are written in parallel and the spec fixes only the output, not the markup.
- Accent palette is 8 named keys (`amber ember rust olive teal steel rose brass`), not 8 raw hexes:
  the builder emits `data-accent="<key>"` so the CSS owns the actual value and cannot drift.
- All accents pre-verified >= 4.5:1 against both `#0b0b0d` and `#111114`; accents never used for body prose.
- `--open` exists for CLI compatibility but prints `open: skipped (headless-only policy)` — the owner may
  be at the PC and a stolen window ruins a game.
- `--fixture` generates its own dark abstract images with Pillow under `state/workpack/_fixture/img/`, so
  the design can be verified with zero network.
- Archived editions are `site/archive/YYYY-MM-DD.html` (spec §7 asks for `editions/<date>.html` in one
  breath and `site/archive/<date>.html` in the next; the `site/` location wins because it must be inside
  the Pages artifact).
- Fonts: system-stack serif display + Georgia body serif + system sans for labels + mono for numerals.
  No webfont at all, not even with a Google-Fonts link — a runtime CDN dependency is a failure mode at 03:00.
- Print stylesheet prints the URL only after `.byline__link` (source links), never after every anchor.
- Density toggle persists in `localStorage["beacon.density"]` under `data-density="dense"`; default is comfy.
- Section anchor ids are the edition `id` verbatim; the validator enforces `[a-z0-9-]+` so anchors are stable
  across rebuilds and citable in the archive.
- Reading progress, masthead compaction, image fallback and density are the only JS. No analytics, no fetch.

## Publishing (U7)

- Repo `nxaxrxo/daily-beacon`, public, default branch `main`.
- Pages source = GitHub Actions (`build_type=workflow`), artifact path `site`, because Jekyll would mangle
  `site/assets/` filenames and `.nojekyll` alone still runs the default build step.
- `publish.py` refuses to commit anything matching a secret pattern and unstages it; the gh token is never
  written to disk.
- `site_base_url` is only written by an explicit `--set-url`, never guessed from a poll that has not seen 200.

## Editorial (U8)

- `interests.md` is distilled from real memory search output with cited `memory.md` line ranges; no invented
  tastes, no flattery.
- `AGENTS.md` is written for a fresh agent with zero session context and no ability to ask questions.

## Runs (U9)

- (recorded when the first real edition is built)

## Backend (U1-U5, spec sections 2-5)

### Scheduler formats (U1)
- `days:N@HH:MM` keeps its phase on the record's `createdAt` (then `lastFiredAt`), so "every 3 days" does not drift to midnight across restarts; `anchorMs` in the spec is informational only.
- `weekly:` keeps the old singular `dow` and adds `dows`; `computeDue` reads `dows || [dow]`, so every pre-existing single-day record parses and schedules exactly as before.
- `weekly:` duplicates are deduped and the list sorted ascending rather than rejected, so `weekly:fri,mon` behaves like `weekly:mon,fri`.
- `monthly:N@HH:MM` clamps N to the month length (31 -> 28/29 in February) instead of skipping the month.
- `hourly:MM` rejects minute 60 and the `9:30` form; `days:` rejects 0 and anything over 365.
- The plugin's own `USAGE` string and `tools/schedule.py`'s `ACCEPTED` string now list the same seven kinds; nothing else in `schedule.py` changed (still only writes request files, never `schedules.json`).
- `scripts/test_scheduler_formats.mjs` imports the real plugin through `file:///...index.ts` (node 24 strips types) rather than a re-export shim, so the test cannot pass against a stale copy.

### Config (U2/U3)
- `settings.json` is the spec object verbatim, 13 keys, `site_base_url` left empty until the first deploy fills it.
- `channels.json` carries exactly the six spec keys; `subscribers`/`customUrl` from the portfolio were dropped at build time because the spec fixed the element shape.
- `channels.json` ships 79 channels; every id is a 24-char `UC...` copied verbatim from `channel_portfolio.json` except Cryton, whose id was resolved live from the channel page and cross-checked against the channel RSS and Invidious (both 200, title `Cryton`).
- Tiers not stated by the spec carry `"note":"tier guessed - confirm"`; shorts/clip/meme/podcast channels are tier 3.
- `feeds.json` ships 24 feeds, every one verified live (HTTP 200 with entries) in the same session it was written; HTTP status and item count per feed are recorded in `docs/FEEDS-CHECK.md`.
- Feeds dropped after verification: VentureBeat AI (HTTP 429 on every URL variant), OpenAI Blog (parses 1331 entries but is an undated marketing archive a 26h window cannot use), and every reachable-but-redundant candidate (Kotaku, Dexerto, Variety Gaming, Siliconera, Steam News, PlayStation Blog, Xbox Wire, 80.lv, Indie Games Plus, Anime News Network, Ukrinform, Hacker News, The Register, Engadget).
- `GameSpot` ships the `mashup` feed (news + reviews) rather than the news-only feed, because the news-only endpoint returned no entries on verification.
- `config/feeds.json` weights: 3 for the three flagship gaming feeds (PC Gamer, RPS, Eurogamer), 1 for Kyiv Independent only, 2 for everything else - so the single awareness feed can never outrank gaming/AI on volume.
- `Game Developer` ships `/rss.xml` because `/rss/` redirects to the homepage and parses to 0 entries; the news-only GameSpot endpoint returned a stale list, so `mashup` is used.
- `feeds.json` was written twice in this session (another unit added 38 feeds, mostly outside the spec's named categories); the final 24-feed set is the one verified and the only one kept, so the spec's 18-25 target and its category list are both met exactly once.
- A feed counts as working only at HTTP 200 AND more than 0 parsed entries; a 200 with an empty body is treated as dead, because an empty feed silently starves the edition.

### Memory (U3)
- `state/seen.sqlite` is created on first use with the three spec tables plus the additive `topic_seen(topic, edition)` guard authorised by CONTRACTS.md; a `PRAGMA user_version` stamp makes a future schema bump explicit instead of a silent overwrite.
- News items get two rows (`url:` and `title:`); a topic hit is report-only and never sets `seen`, per DECISIONS section "Memory".
- `filter` on an unreadable candidates file exits 0 with an empty report rather than killing the nightly run; `run_daily.py` still treats that as a warning.
- `prune` never touches rows referenced by a kept edition, even past the cutoff.

### Sources (U4/U5)
- `yt_source.py` prefers Invidious (it returns `lengthSeconds` + views in one call) and falls back to channel RSS; a channel that fails both is counted failed and never fatal. Live run: 34 videos from 77/77 channels, 0 failed.
- Invidious reports `viewCount` as 0 for very fresh uploads; the value is stored as-is (0 is a real reading there, not "unknown"), while a genuinely absent field stays `null`.
- `yt_source.py` applies `max_videos_per_channel` from settings (3) as the per-channel cap, and `short_max_seconds` for the shorts classification.
- An RSS entry with no `<published>` is kept with `publishedAt: null` rather than dropped - hiding real content because of missing metadata is worse than an unsortable row.
- `news_source.py` keeps undated entries too, dedupes by normalised title and url (weighted winner, others in `also_on`), caps 4 per source, and spends at most 10 `og:image` fetches per run.
- `transcripts.py` is strictly sequential, checks `~\.config\opencode\notes\yt-cache` before any fetch, copies cache hits into the workpack rather than refetching, and records every failure in `transcripts/index.json` instead of aborting.
- Trimming is head+tail with a literal `[... trimmed N chars ...]` marker so the 03:00 agent can read the argument and the conclusion without the filler.
- `run_daily.py collect` degrades: a failed producer, filter or transcript batch is a WARN and the run continues to `packet.md`; only an unwritable `candidates.json` exits non-zero.
- `run_daily.py` keeps `candidates.json` immutable after the caps and writes the image map to `images.json`, patching `thumb_local` into `filtered.json` only.

### Verification
- `node scripts/test_scheduler_formats.mjs` -> 71 assertions, `ALL FORMATS PASS`, exit 0 (both old and new kinds, valid/reject/catch-up).
- `python scripts/memory.py selftest` -> `SELFTEST PASS`.
- `python scripts/yt_source.py` live -> `yt_source done: 34 videos from 77/77 channels (0 failed)`.
- `python scripts/news_source.py` live -> `news_source done: 60 articles from 21/21 feeds (0 failed)`.
- `python scripts/transcripts.py --ids ...` -> cached path proven, trim marker proven.
- `python scripts/run_daily.py collect` -> summary line and `packet.md` (recorded in docs/_parts/u5b-rundaily.md).
