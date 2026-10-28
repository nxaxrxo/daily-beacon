# DECISIONS — where the spec was silent

One line each. Newest decisions at the bottom of their section.

## Site / presentation (U6)

- Wrote `docs/SITE-CONTRACT.md` as the binding HTML/CSS/JS interface, because `build_edition.py`,
  `style.css` and `app.js` are written in parallel and the spec fixes only the output, not the markup.
- Accent palette is 8 named keys (`amber coral rose sage teal sky gold clay`), not 8 raw hexes: the
  builder emits `data-accent="<key>"` so the CSS owns the actual value and cannot drift.
- Every accent measured against both page blacks rather than eyeballed; the lightest-scoring one (coral)
  still clears AA for normal text, so no combination of date seed can make the page unreadable:
  `amber 9.12:1 / ember 8.74`, `coral 7.03 / 6.74`, `rose 8.32 / 7.97`, `sage 10.19 / 9.77`,
  `teal 9.54 / 9.15`, `sky 9.18 / 8.80`, `gold 11.31 / 10.84`, `clay 8.15 / 7.81` (vs `#0b0b0d` / `#111114`).
  Body ink `#ece7dd` is 15.96:1. Accents still never carry body prose - they mark kickers, rules and links.
- The builder has no `--open` flag and opens nothing: verification is exit code, byte size, `--check`, HTTP,
  and headless screenshots into scratch. A stolen window while the owner is at the PC is not a trade worth
  making for a convenience flag.
- `--fixture` generates its own dark abstract images with Pillow under `state/workpack/_fixture/img/`, so
  the design can be verified with zero network.
- Archived editions are `site/archive/YYYY-MM-DD.html` (the spec asks for `editions/<date>.html` in one
  breath and `site/archive/<date>.html` in the next; the `site/` location wins because it must be inside
  the Pages artifact).
- Fonts: system-stack serif display + Georgia body serif + system sans for labels + mono for numerals.
  No webfont at all, not even with a Google-Fonts link — a runtime CDN dependency is a failure mode at 03:00.
- Print stylesheet prints the URL only after `.byline__link` (source links), never after every anchor.
- Density toggle persists in `localStorage["beacon.density"]` under `data-density="dense"`; default is comfy.
- Section anchor ids are the edition `id` verbatim; the validator enforces `[a-z0-9-]+` so anchors are stable
  across rebuilds and citable in the archive.
- Reading progress, masthead compaction, image fallback and density are the only JS. No analytics, no fetch.

- The colophon's "suppressed today" counts the items in `state/workpack/<date>/suppressed.json`, not
  the number of editions in the memory DB. The earlier query counted `editions` rows and printed `1
  suppressed today` on a morning where 15 candidates were actually dropped - a small-print number the
  owner reads on a phone, so it has to be the real one. `items` still comes from the DB for the
  "tracked" half of the line.

## Publishing (U7)

- Repo `nxaxrxo/daily-beacon`, public, default branch `main`.
- Pages is served from the `gh-pages` **branch** (`build_type=legacy`), not the Actions artifact: the
  fine-grained PAT is repo admin but carries no Pages permission, so both `POST` and `PUT /pages -f
  build_type=workflow` return 403 and enabling artifact publishing needs the owner's token. Pushing
  `gh-pages` was the only path that worked - GitHub detected it and built the site with no further call.
- `publish.py` pushes `main` and then mirrors `site/` onto `origin/gh-pages` in a throwaway worktree:
  fast-forward only, `.nojekyll` written, and a no-op print when the tree already matches. Pushing `main`
  alone updated the repo but not the live page - the one failure that would have gone unnoticed at 03:00.
- The mirror target is the `pages_branch` setting (`""` disables it) rather than a constant, so switching
  back to artifact publishing is a settings change, not a code change.
- `.nojekyll` travels with the mirror so `site/assets/<date>/` filenames survive; Jekyll would mangle them.
- `enablement: true` was removed from `actions/configure-pages`: the workflow token cannot create a Pages
  site either (`Resource not accessible by integration`), so every run failed and buried real failures
  under a red X.
- `pages.yml` now probes `build_type` first and skips build/deploy unless it is `workflow`; with a branch
  source a successful skip beats a failing deploy, and flipping Pages to "GitHub Actions" in repo settings
  re-arms the workflow with no file edit.
- `publish.py` refuses to commit anything matching a secret pattern and unstages it; the gh token is never
  written to disk.
- `site_base_url` is only written by an explicit `--set-url`, never guessed from a poll that has not seen 200.

## Editorial (U8)

- `interests.md` is distilled from real memory search output with cited `memory.md` line ranges; no invented
  tastes, no flattery.
- `AGENTS.md` is written for a fresh agent with zero session context and no ability to ask questions.

## Fact-check pass on the first edition (U9)

- Four sections of the first draft overstated their sources and were rewritten before publish: the lead
  said Rockstar staff *had voted* (the ballot is 12-26 November), Resident Evil was said to be ending
  within ten years (Wccftech explicitly reads the quote as one chapter, not the franchise), Dunkey's clip
  was called a review (it is a gameplay video), and Waddle World was described as launched (Philippines
  only, late September).
- Rule applied: a headline may not assert more than the fetched article states. Where an outlet's own
  follow-up walks back the framing, the Beacon carries the correction rather than the louder version.
- `memory.py mark` was re-run after the edits; it is idempotent on key+edition, so the corrected titles
  are what the 21-day cooldown now keys on.

## Runs (U9)

- First real edition shipped 2026-10-28: edition no. 1, 14 sections, 6 quick hits, live at
  `https://nxaxrxo.github.io/daily-beacon/`; run note is `docs/runs/2026-10-28.md`.
- All 20 source URLs in that edition were re-checked live (HTTP 200) before publishing, so nothing on the
  front page is a claim we did not fetch.
- `doctor.py` is the pre-flight self-check: config, imports, feed list, memory db, fixture build and a
  network probe; it exits non-zero on any failure so a bad morning is caught before anything is published.

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
- `settings.json` was seeded as the spec object verbatim, 13 keys in spec order, `site_base_url` empty. The publish unit later filled `site_base_url` with the live Pages URL and added one key, `pages_branch`, for the branch-deploy path it chose (see the Publishing section); the 13 spec keys and their values are otherwise untouched, and every consumer reads a missing key as its documented default rather than crashing.
- `channels.json` carries exactly the six spec keys; `subscribers`/`customUrl` from the portfolio were dropped at build time because the spec fixed the element shape.
- `channels.json` ships 79 channels; every id is a 24-char `UC...` copied verbatim from `channel_portfolio.json` except Cryton, whose id was resolved live from the channel page and cross-checked against the channel RSS and Invidious (both 200, title `Cryton`).
- Tiers not stated by the spec carry `"note":"tier guessed - confirm"`; shorts/clip/meme/podcast channels are tier 3.
- `feeds.json` ships 24 feeds, every one verified live (HTTP 200 with entries) in the same session it was written; HTTP status and item count per feed are recorded in `docs/FEEDS-CHECK.md`.
- Feeds dropped after verification: VentureBeat AI (HTTP 429 on every URL variant), OpenAI Blog (parses 1331 entries but is an undated marketing archive a 26h window cannot use), and every reachable-but-redundant candidate (Kotaku, Dexerto, Variety Gaming, Siliconera, Steam News, PlayStation Blog, Xbox Wire, 80.lv, Indie Games Plus, Anime News Network, Ukrinform, Hacker News, The Register, Engadget).
- `GameSpot` ships the `mashup` feed (news + reviews) rather than the news-only feed, because the news-only endpoint returned no entries on verification.
- `config/feeds.json` weights: 3 for the three flagship gaming feeds (PC Gamer, RPS, Eurogamer), 1 for Kyiv Independent only, 2 for everything else - so the single awareness feed can never outrank gaming/AI on volume.
- `Game Developer` ships `/rss.xml` because `/rss/` redirects to the homepage and parses to 0 entries; the news-only GameSpot endpoint returned a stale list, so `mashup` is used.
- `feeds.json` was written by more than one unit during this session (variants reached 21 and 38 entries, the latter mostly outside the spec's named categories); the final 24-feed set is the one verified line-by-line and the only one kept, so the spec's 18-25 target and its category list are both met exactly once.
- A feed counts as working only at HTTP 200 AND more than 0 parsed entries; a 200 with an empty body is treated as dead, because an empty feed silently starves the edition.

### Memory (U3)
- `state/seen.sqlite` is created on first use with the three spec tables plus the additive `topic_seen(topic, edition)` guard authorised by CONTRACTS.md; a `PRAGMA user_version` stamp makes a future schema bump explicit instead of a silent overwrite.
- News items get two rows (`url:` and `title:`); a topic hit is report-only and never sets `seen`, per DECISIONS section "Memory".
- `filter` on an unreadable candidates file exits 0 with an empty report rather than killing the nightly run; `run_daily.py` still treats that as a warning.
- `prune` never touches rows referenced by a kept edition, even past the cutoff.

### Sources (U4/U5)
- `yt_source.py` prefers Invidious (it returns `lengthSeconds` + views in one call) and falls back to channel RSS; a channel that fails both is counted failed and never fatal. Live run: 34 videos from 79/79 channels, 0 failed (later 26h runs gave 30-32 as the window moved; 0 failures throughout).
- Invidious reports `viewCount` as 0 for very fresh uploads; the value is stored as-is (0 is a real reading there, not "unknown"), while a genuinely absent field stays `null`.
- `yt_source.py` applies `max_videos_per_channel` from settings (3) as the per-channel cap, and `short_max_seconds` for the shorts classification.
- An RSS entry with no `<published>` is kept with `publishedAt: null` rather than dropped - hiding real content because of missing metadata is worse than an unsortable row.
- `news_source.py` keeps undated entries too, dedupes by normalised title and url (weighted winner, others in `also_on`), caps 4 per source, and spends at most 10 `og:image` fetches per run.
- `transcripts.py` is strictly sequential, checks `~\.config\opencode\notes\yt-cache` before any fetch, copies cache hits into the workpack rather than refetching, and records every failure in `transcripts/index.json` instead of aborting.
- Trimming is head+tail with a literal `[... trimmed N chars ...]` marker so the 03:00 agent can read the argument and the conclusion without the filler.
- `run_daily.py collect` degrades: a failed producer, filter or transcript batch is a WARN and the run continues to `packet.md`; only an unwritable `candidates.json` exits non-zero.
- `run_daily.py` keeps `candidates.json` immutable after the caps and writes the image map to `images.json`, patching `thumb_local` into `filtered.json` only.
- `run_daily.py` parses the producers' summary lines through one tolerant helper (`parse_producer_stats`) and falls back to the file's own item count when a line is missing, so a producer whose output was reformatted can never make the packet report `0/0 ok` while real data sits on disk.
- Transcripts default to `min(12, max_videos_total)`; `--limit-transcripts` overrides it, and a cached hit still counts toward the packet's `transcript:yes` flag because the file exists either way.

### Verification - every required run executed for real, output captured
- `node scripts/test_scheduler_formats.mjs` -> exit 0, 83 `PASS` lines and a final `ALL FORMATS PASS`
  (valid parse, invalid rejection and catch-up maths for once, every, daily, weekly-single, weekly-multi,
  days, hourly, monthly). Re-run after the last plugin edit.
- `python scripts/memory.py selftest` -> `SELFTEST PASS`, exit 0. A separate fixture round trip proved
  `mark` idempotency (`marked: 5 new items` then `marked: 0 new items, 0 topics`) and `filter` reporting
  `2 seen / 1 fresh` with reasons `video` and `url`.
- `python scripts/yt_source.py` live -> `yt_source done: 34 videos from 79/79 channels (0 failed)`; later
  26h runs gave 30-32 videos as the window moved. 0 channels failed in every run.
- `python scripts/news_source.py` live -> `news_source done: 60 articles from 24/24 feeds (0 failed)`
  (281 items inside 26h, 181 dropped by the 4-per-source cap, 40 by the overall 60 cap).
- `python scripts/transcripts.py` -> cache-hit path, fetch path and the `[... trimmed N chars ...]` marker
  all proven against real videos; 22 `.txt` files in the current workpack.
- `python scripts/run_daily.py collect --date 2026-10-28` -> exit 0. Cold run:
  `collect done: 34 videos, 60 articles, 14 transcripts, 0 repeats suppressed`. Final run on the marked
  edition (the workpack on disk now): `collect done: 32 videos, 60 articles, 22 transcripts, 15 repeats
  suppressed`, with `packet.md` carrying all six contract headings in order and 40 real candidate lines.
- The anti-repeat path is proven on real data: the 15 suppressed items are stories the edition marked
  earlier today already covered, and `filter` reports `92 total, 15 seen, 77 fresh`.
- `docs/FEEDS-CHECK.md` was regenerated from a live re-measurement after the final feeds.json was fixed:
  24 feeds, 24x HTTP 200, 24x entries > 0, 0 dead.

### Build notes worth knowing
- `run_daily.py` parses each producer's summary from the whole captured output, not just the last line:
  the producers write progress to stderr, which used to hide the `... done:` line and print
  "producer did not report a summary".
- `--reuse-source` reports what the files on disk actually hold (and says "reused from disk") instead of
  claiming zero, so a resumed run cannot look like an empty collection.
- A foreground producer run on this machine is killed at ~50s by the shell lane; verification runs were
  therefore started detached with a done-marker and polled, which is also how the 03:00 agent should run
  a long collect if it ever needs to.
- `config/feeds.json` was written twice during the build (one unit added 38 feeds, several outside the
  spec's named categories). The final file is the 24-feed set that was verified live, which is the only
  version kept and the one all numbers above refer to.


## 2026-10-28 - post-launch corrections (second pass)

Five real defects found by testing the system against itself, not just building it:

1. **Kickers were poisoning the anti-repeat index.** \mark_edition\ slugged the whole display label,
   so "GAMING . LABOUR" became the topic \gaminglabour\ - a string no article tag can ever match.
   The cooldown therefore never fired for real. Kickers are now split on their separators and each
   segment is slugged whole (\masseffect\, not \mass\ + \effect\), with a stopword list so
   "THE BIG ONE" does not become a topic either.
2. **Category words muted the whole paper.** Tags like \eview\, \elease\, \esearch\ appear on
   half of everything; as cooldown topics each one would suppress a section for three weeks. A
   \GENERIC_TOPICS\ gate keeps them on the item record but out of the topic index.
   Proof of the fix: re-filtering today's candidates reports 15 seen and 34 cooling topics.
3. **\--edition PATH\ was unusable for past editions.** The validator compared the file's date
   against *today*, so the README's own hand-edit workflow failed on any edition older than the
   current day. The file's declared date now wins when \--date\ is absent.
4. **No favicon** - the only console errors on the live page. Added an inline SVG mark (no extra
   request beyond the file itself) and threaded \prefix\ through \document()\ so archive snapshots
   point at \../favicon.svg\.
5. **No month-later mechanism.** The spec asked for a reminder, and only the 21-day block existed.
   \memory.py digest\ now reports coverage totals, the most-covered topics, everything currently
   cooling down, and what has been quiet 30+ days (ripe for a genuine follow-up, never a repeat).

Also hardened: \--db\ is accepted after the verb as well as before it, matching \--root\.

Day-to-day variety was proven, not assumed: building the same edition under five consecutive dates
produced five distinct looks (teal/sky/gold/clay/sky, with the hero layout changing twice).
