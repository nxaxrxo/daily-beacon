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
2. **Category words muted the whole paper.** Tags like \
eview\, \
elease\, \
esearch\ appear on
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


## 2026-10-28 - owner brief: cadence, channel policy, and the 50-hour window

The owner answered the open questions directly: every **second** day at 03:00 rather than daily
(24 hours is too thin to make a paper), channels restricted to **gaming news, AI, MMORPGs and
documentaries/long-form essays**, and explicitly *not* pure branded entertainment, gameplay or
let's-play uploads, music artists, meme/shorts farms, clip channels or podcasts.

1. **Channel list cut 79 -> 48 enabled** (tier 1: 26, tier 2: 13, tier 3: 9; 31 disabled). Every
   disabled record carries a note naming the reason, so a later pass cannot quietly re-enable one.
   Backup kept at config/channels.json.bak-tierpass.
2. **config/interests.md gained a ## CHANNEL POLICY section** that *outranks* the LOVES list,
   because the memory-derived rubric still named Papa Meat, Flashgitz and Viva La Dirt League as
   loves. The owner's live instruction wins over an inferred preference, and the precedence is
   written down so the 03:00 agent is not handed contradictory orders.
3. **The window had to grow with the cadence: 26h -> 50h.** This is the non-obvious consequence of
   the 48-hour schedule. A 26-hour lookback on a every-second-day run drops everything published on
   the off day, silently - the paper would simply have been half as full and nobody would have known
   why. Caps raised with it (max_videos_total 40 -> 55, max_news_items 60 -> 90).
4. **The freshness scale had to grow with the window too.** It was < 6h = 15, < 12h = 12,
   < 18h = 8, < 26h = 5, older = 0, so at a 50-hour window every off-day story scored **zero** on
   freshness and the lower half of the window became unselectable. Now < 30h = 5, < 50h = 3: a
   two-day-old story still scores, it is just worth less than this morning's.
5. **Fallback defaults aligned to 50** in yt_source.py, 
ews_source.py and 
un_daily.py. Live
   runs read settings.json and were already correct; a fresh clone missing that file would have
   fallen back to 26 and quietly reproduced bug 3.
6. **Schedule replaced**: sch_mvrykw11eot (daily:03:00) removed, sch_mvs3tk2f0cb
   (days:2@03:00) armed, next fire 2026-10-30 03:00.

The scheduler needed a new format for this (days:N@HH:MM), verified by

ode scripts/test_scheduler_formats.mjs -> 71/71 ALL FORMATS PASS.


## 2026-10-28 - the brief becomes mechanical, not aspirational

Testing the real 50-hour collect showed the policy was only being *asked for*, not *enforced*: a
**15.7-hour "Castlevania Belmont's Curse True Ending (FULL GAME)"** stream from a kept channel
reached the candidates and depended on the 03:00 agent catching it by eye. A rule that needs
re-judging every night is not a rule.

1. **`yt_source.looks_like_gameplay()`** drops unambiguous raw footage at collection time: "full
   game", "playthrough", "walkthrough", "part N", "no commentary", "live stream", plus long
   session-shaped uploads. Conservative by design - and with an explicit **trailer/reveal
   exemption**, because the rubric prices a reveal at 22 and "Gameplay Trailer" must survive.
   Verified on a live run: 1 upload dropped, 22 kept, 48/48 channels, 0 failures.
2. **`scripts/test_channel_policy.py`** (17 assertions) pins the behaviour: four titles that must
   drop, seven that must survive, 48 enabled, every disabled channel carrying a reason, and the
   window still >= 48h. A future refactor cannot quietly undo the brief.
3. **`doctor.py` grew a `channel policy` check** (13 checks now). Proved it can fail: enabling
   MrBeast by hand flips it to `[FAIL] entertainment channels are enabled: MrBeast`, and it
   returns to PASS once restored. A check that has never failed is not evidence of anything.
4. **`docs/AGENTS.md` now opens with `## CHANNEL POLICY`** as the first thing the judging agent
   reads, with the explicit note that it outranks the older LOVES list.

Six channels were proposed and staged **disabled** rather than added: Bellular News, Skill Up,
Force Gaming, Preach Gaming, Rhykker, MrLlamaSC. All six verified live (RSS returns 15 entries
each) because the IDs I had written from memory were fabricated placeholders that 404'd - a
reminder that a plausible-looking channel ID is not a channel.


## 2026-10-28 - retention: the colophon was making a promise nothing kept

The footer has always read "Previous 30 editions are archived", and `keep_editions` was read in
exactly one place - to print that sentence. Nothing rotated the folder, so at 48-hour cadence the
archive would have grown unbounded and the claim would have quietly become a lie.

- **`prune_archive()`** now deletes the oldest snapshots past `keep_editions` and returns the
  trimmed list. Scoped strictly to `site/archive/*.html`; `editions/*.json` is the source of truth
  and is never touched. Verified: 35 synthetic snapshots -> 30 files, exactly the oldest 5 deleted,
  the current edition and newest snapshot surviving.
- **`state/seen.sqlite` is deliberately NOT capped.** `prune` exists and is conservative by design
  (it refuses to delete rows a kept edition references). More importantly, old rows are *useful*:
  the rubric scores a 60-day-old topic higher than a 21-day-old one, so deleting history would
  make the paper repeat itself sooner. At ~61 KB per edition this is not a growth problem.
- **`prune` was tested, not assumed**: `prune --days 400` and even `--days 0` delete nothing at one
  edition, which is correct behaviour, not a bug. Left alone deliberately.

## 2026-10-28 - the month-later reminder now actually happens

The owner asked for anti-repeat memory "and a month-later reminder or analytics". The cooldown and
the \digest\ command both existed, but nothing ever ran the digest - a command nobody invokes is
not a reminder.

\memory.py digest --write\ now saves a dated report to \docs/coverage/<date>.md\, and the runbook
tells the 03:00 agent to run it right after marking memory so it commits with the edition. The
report carries: edition count and date span, most-covered topics, everything currently cooling
down, and the topics quiet 30+ days that are ripe for a genuine follow-up.

Implementation note: the first attempt shadowed \print\ inside \cmd_digest\, which raised
\UnboundLocalError\ - the wrapper printed nothing at all. Capturing \sys.stdout\ instead keeps the
human-readable output on screen and gives the file the exact same text, so there is no second
rendering path to drift.


## 2026-10-28 - unattended rehearsal: a fresh agent wrote an edition, and found the holes

The writing step had only ever been done by hand. A fresh-context agent was given nothing but
`docs/AGENTS.md`, `config/interests.md` and the real packet, and asked to produce a valid edition
without publishing. It succeeded (9 sections, one lead, 5 images, all credited, `CHECK OK`) - but
its friction report exposed defects that would have bitten the first unattended run:

1. **The cooldown, read literally, forbade the entire paper.** The cooling list contained `gaming`,
   `ai`, `hardware`, `tech`, `industry`, `pc` - and those umbrella tags sit on **110 of 113**
   candidates. `GENERIC_TOPICS` excluded `news`/`review`/`release` but not the umbrellas, so the
   index was gating on words that describe a section rather than a subject. Fixed in
   `memory.py`; the index rebuilt to **28 specific topics with zero umbrella tags**. Dedup still
   works (8 seen preserved), and a strict-reading agent would previously have suppressed 110 of 113.
2. **The transcript instruction was physically impossible.** It said "read `offset`/`limit` slices
   of about 150 lines". The files have **1-3 newlines in 24,032 characters** - they are one line, so
   line-slicing returns the whole file, which is the exact thing the rule forbade. Now says to slice
   by character: first ~1,800 and last ~1,200.
3. **`images.json` paths are relative to the project root, the builder resolves them relative to
   `editions/`.** Following "use paths verbatim" produced a broken image that only WARNS and still
   passes `--check` - an unattended run would ship a textless page believing it had images. The
   required `../` prefix is now documented.
4. **An uncredited image passed validation silently.** Credit is a NEVER-list item in
   `config/interests.md`, but `_check_image` only tested `src`. Now `alt` and `credit` are checked,
   and **soft issues are printed** - they were collected and then dropped, so nothing ever surfaced.
   Proved: stripping a credit from the real edition now prints a `CHECK WARN` naming the section.
5. **`seen: true` was defined twice, differently** - "is out" four lines above "seen set, -45".
   Resolved explicitly: out means out, the -45 is bookkeeping for the suppressed row.

Docs also corrected where they were stricter than the code (`--check --edition` was never in the
pre-flight table; the documented `id` regex was looser than the enforced one, so the error message
told an agent its invalid id was valid).
