# AGENTS - the 03:00 runbook

You are the agent that builds today's Daily Beacon, alone, at 03:00, with nobody awake to answer a
question. Everything you need is here and in `config/interests.md`. Read this file top to bottom.

Project root: `C:\Users\MarciNaro\Documents\VSCODE-PROJECTS\daily-beacon`. Every command runs from there.

**Operating skill:** load `daily-beacon` (`skill_search.py "daily-beacon"` -> skill-library\daily-beacon\SKILL.md) for any change to this project's config, taste rules, channels, feeds, schedule or an already-published edition. This runbook stays the authority on *how an edition is written*; the skill is the map of *where everything lives and how to change it*.

## 1. Where you are, and the one rule

Today's edition is a pair: `editions/YYYY-MM-DD.json`, the content file you write for today's **local**
date, and `site/index.html`, what `build_edition.py` renders from it, plus `site/archive/<date>.html`,
`site/archive.html` and `site/assets/<date>/`. Nothing else is yours to create. The scheduler calls you
once and expects a published page afterwards.

**The one hard rule, which no other rule here can override:**

> **Never invent news.** Every section must trace back to something that exists on disk or on the
> wire: a line in `state/workpack/<date>/packet.md`, a file in `state/workpack/<date>/transcripts/`,
> or a source you really fetched. No invented quotes, no estimated numbers, no "reportedly", no
> reconstructed reactions, no imagined patch notes. If the packet does not support a sentence, the
> sentence does not go in the edition.

Two consequences: **never present an unverified claim as fact** - attribute it ("the studio says") or
leave it out, hedging is not a source; and **every story carries a real `source.label` and
`source.url`**, because the builder fails a story without one (SPEC section 6) and a page of unsourced
summaries is worse than a short page.

The taste document is binding: **`config/interests.md`** (LOVES / LIKES / NEUTRAL / DISLIKES / NEVER,
the numeric rubric, tone rules, cooldown, "what the edition is not"). Read it in full before judging;
it outranks your taste.

**Read `## CHANNEL POLICY` in that file first.** It is the owner's direct instruction and it
**outranks the LOVES list**. In scope: gaming news, AI, MMORPGs, documentaries and long-form
essays. Out: pure branded entertainment, gameplay / let's-play uploads of any kind, music
artists, meme and shorts farms, clip channels, podcasts, art channels. The LOVES list still
names comedy channels from an older memory - ignore that, the policy wins. If a disabled
creator covers something genuinely huge, run the STORY from an outlet, never as "a video from X".

Reference contracts: `docs/SPEC.md` (sections 1, 6, 7, 8),
`docs/CONTRACTS.md` (CLI + `packet.md`), `docs/SITE-CONTRACT.md`, `docs/DECISIONS.md`.

## 2. Collect

```
python scripts/run_daily.py collect --date YYYY-MM-DD
```

Observed flags: `--date`, `--hours`, `--limit-transcripts`, `--skip-images`, `--reuse-source`,
`--root`; defaults from `config/settings.json` (`lookback_hours` = 50, because the run is every
second day - the window must cover the off day or half of the news is silently lost). Add `--reuse-source` only when
resuming a run that died after fetching sources. Expected last line:
`collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed`.

**Volume is the point now.** The caps are `max_videos_total` 80, `max_news_items` 140,
`max_videos_per_channel` 4, 6 per feed: high enough that a normal two-day window arrives almost whole
(measured 2026-10-28: 140 articles from 41 feeds, 726 in-window items before the cap), and per-source
caps low enough that one prolific channel or one aggregator cannot flood the packet. `--limit-transcripts`
stays at its default `min(12, max_videos_total)` - transcripts are for the handful of items you will
actually write from, not for everything you will mention.

Three of the feeds are Reddit aggregators (`r/Games`, `r/gamingnews`, `r/GamingLeaksAndRumours`, top of
the last 24h) and Reddit rate-limits hard. `news_source.py` uses the `.rss` endpoint with a browser UA,
paces Reddit requests 6s apart and retries a 429 with 20s/40s backoff before giving up on that feed for
the run. A `FAIL r/Games  http 429` line in the collect log is expected occasionally and is **not** a
failed run - it means that subreddit contributed nothing this time. Never retry the whole collect step
because of it. The `.rss` feed carries title, link, author and date but no score, so upvote count is not
available; judge those items on the title like any other headline.

**What the 41 feeds in `config/feeds.json` actually give you.** `r/Games`, `r/gamingnews` and
`r/GamingLeaksAndRumours` are three of them, at the top of the last 24h. A `429` from one of them comes
back as an empty list, not an error - `http 429` / `[]` in the log is the expected shape on a bad Reddit
day and the run is still healthy. Feeds worth knowing by name, because they map onto a taste lane:
`Godot Blog` and `Unreal Engine` (engine news), `Anime News Network` and `Siliconera` anime wires
(see `config/anime.json` below), `GamesIndustry.biz` and `Game Developer` (business events, section 3.2.1),
`Steam News` (patch notes for games on his list), `Indie Games Plus` and `80.lv` (indie breakouts).

**`config/anime.json` is a judging input, not a feed.** It is the owner's own MAL export: 100 titles, each
with `title`, `score`, `status`, `type`, `eps`, `genres`, and every entry scored 9 or 10 - so presence in
the file means "he loved it", full stop. Use it whenever an anime item is in the packet:

- Match the item's subject against `titles[].title`. A new season, sequel, finale, adaptation or studio
  problem for a listed title is a real subject and scores M = +15 (`config/interests.md`, LOVES).
- An anime item about a title that is NOT in the file is generic anime news and does not get the lane.
- `status: "dropped"` means he rated it and still stopped watching - Fullmetal Alchemist Brotherhood,
  Sakamoto desu ga?, Tonari no Kaibutsu-kun. Interest exists, execution lost him, so a remake or sequel
  there is a story but not an automatic lead.
- Read it with `python -c "import json;d=json.load(open('config/anime.json',encoding='utf-8'));..."` or just
  open it; it is 100 short records and greps cleanly by title. Do not edit it.

**Two lanes need a style rule at write time, so they are stated here as well.** Godot engine news is
plain language: say what a change means for someone making a game ("your 3D scenes should stutter less on
an 8GB card", "renaming a file now updates every reference"), never the changelog heading or the internal
API name - the owner's words, "everything should be written in a way that a layman could understand."
Actively-played games (Helldivers 2, Crimson Desert, Hytale, Warframe, Aion 2, DragonSword: Awakening,
No Man's Sky) are always relevant from any source; a followed creator's take is the preferred version.

It writes, under `state/workpack/<date>/`:

| File | What it is |
|---|---|
| `yt.json` / `news.json` | raw YouTube items per channel; raw RSS items per feed |
| `candidates.json` | both normalised into the canonical item shape |
| `filtered.json` | the same, annotated with `seen`, `seen_reason`, `topic_hits` |
| `suppressed.json` | items dropped as repeats, with the reason |
| `transcripts/` | `<videoId>.txt` slices plus `index.json` (fetched / cached / failed) |
| `img/`, `packet.md` | downloaded Pillow-verified thumbnails; the briefing you read first |

Then:

1. **Read `state/workpack/<date>/packet.md` in full.** Counts, every kept video, every kept article
   (up to 80 and 140 - nothing is truncated past the collection cap), what is cooling down, next
   commands. Trust its ordering, not its judgement - you judge.
2. **Read 3-8 transcripts, in slices.** Each `transcripts/<videoId>.txt` is trimmed head+tail, so the
   argument and conclusion sit at the ends and the middle is filler. **These files are effectively
   ONE LINE** - the prose arrives with almost no newlines (measured: 24,032 characters, 1-3 newlines),
   so line-based slicing gives you the whole file at once. Slice by CHARACTER instead: read roughly
   the first 1,800 and the last 1,200 characters of each file, which is where the thesis and the
   payoff sit. **Budget: at most 8 transcripts**, and only ones you intend to use.
3. **Judge everything else from title + channel/source + thumbnail + length.** You do not need a
   transcript to know that a 14-minute video called "the patch that broke everything" is worth a look.
4. **Image paths need one transform, not a copy.** `images.json` stores paths relative to the
   PROJECT ROOT (`state/workpack/<date>/img/<hash>.jpg`), but the builder resolves `image.src`
   relative to the EDITION file, which lives in `editions/`. So the value that works is
   `../state/workpack/<date>/img/<hash>.jpg` - prefix `../`. Copying verbatim produces a broken
   image that only WARNS (`image skipped: local file not found`) and still passes `--check`, so an
   unattended run would ship a text-only page believing it had images. Never invent a path; a
   missing image is a legal text-only section, a broken path is not.

> NOTE: a healthy run can still print `youtube: 0 videos | producer did not report a summary` and
> `warnings: yt_source exit 4294967295` - that is the producer's summary channel failing on Windows
> while `yt.json` itself is complete. Trust the candidate counts and the videos list, not that line.

**If collection fails, or the packet is thin:** run the command once more (with `--reuse-source` and
without) - a single feed timeout is normal. If it still fails, or there are fewer than five usable
items, publish a short honest edition anyway: three to five sections, the lead being what you *do*
know, plus one clearly labelled note naming the source that failed. Never a blank page, never silence.

## 3. Judge

**The edition is include-by-default. You are not curating a short list - you are reporting everything
of any substance and dropping only what is worthless.** The owner's instruction, verbatim: "as long as
it's even somewhat interesting, you can keep it in the news feed. Because you know what's sad? When you
waste tokens. You already wasted tokens by reading the news, might as well write about it."

That inverts the old bar. The packet is already paid for. An item that survived collection and the
channel policy has cost real tokens; a dropped-but-interesting story is a wasted night. So the question
per candidate is never "is this good enough for the front page" - it is **"is this worthless?"** and the
answer is usually no.

Score every candidate with the rubric in `config/interests.md` - one pass, no second looks - then sort:

```
score = T (tier/source 0-30) + F (freshness 0-15) + N (novelty vs memory -25..15)
      + V (format value 0-25) + M (personal multiplier -15..15), then penalties, clamp 0-100
```

The score now decides **placement, not survival**:

| Score | Slot |
|---|---|
| >= 80 | lead candidate (highest wins, exactly one lead) |
| 45-79 | a section - `story` if the body is worth two or more paragraphs, `video` for a video, `quick` for one paragraph |
| 30-44 | `quick` section or a `quickHits` line - **still shipped** |
| < 30 | only if the item is *worthless* by the test below; a low score alone is not a reason to drop |

**The only legitimate drop is worthless.** Worthless means the item contains nothing a reader could
learn or enjoy. Concrete, and this is the whole list:

- an Nth episode of a routine let's play or a series ("PewDiePie played Resident Evil again, episode
  147"). Nobody cares, and the format is out of scope anyway (CHANNEL POLICY).
- a livestream or premier announcement with no content behind it ("going live in an hour").
- a screenshot or meme post that carries no news, no number and no claim.
- a re-upload, a mirror, or the same video from a second channel.
- a rumour with no named source and no document behind it.

Everything else ships. A 40-minute devlog on a shader seam ships. A patch note for a game he does not
play ships as one line in `quickHits`. A studio's quarterly number ships. Two stories about the same
subject from different angles are two `quickHits`, not one - unless the cooldown rule kills the second,
which is a separate gate and still applies.

**`seen` and cooldown still remove items entirely** - that gate is unchanged and sits above this
section. Include-by-default is about taste, not about repeats.

### 3.1 Worked ranking, eight candidates

One real-shaped morning, components in rubric order, penalties applied once each.

| # | Candidate | T | F | N | V | M | Pen | Total | Slot |
|---|---|---|---|---|---|---|---|---|---|
| 1 | AngryJoeShow, "EA closes BioWare and Mass Effect", 20h old, never covered | 30 | 5 | 15 | 25 | +8 | 0 | **83** | **lead** |
| 2 | Asmongold TV, 14 min take on a studio's botched reveal, 4h old, never covered | 30 | 15 | 15 | 25 | +15 | 0 | **100** | story |
| 3 | Tier-2 devlog, smooth voxel terrain in GDScript, 9h old, never covered | 20 | 12 | 15 | 25 | +15 | 0 | **87** | story (hero alt) |
| 4 | Eurogamer, GTA 6 is a 210GB download, 1h old, never covered | 16 | 15 | 15 | 15 | 0 | 0 | **61** | story |
| 5 | PC Gamer, Warframe rifle buff in the new patch, 20h old, topic last covered 40d ago | 16 | 5 | 6 | 20 | +8 | 0 | **55** | quick section |
| 6 | PC Gamer, Rockstar union vote over the GTA 6 launch, 26h old, never covered | 16 | 5 | 15 | 15 | 0 | 0 | **51** | quick hit |
| 7 | r/Games, Austin recommends The Wolf Among Us Remastered, 6h old, never covered | 16 | 12 | 15 | 20 | 0 | 0 | **63** | story |
| 8 | videogamedunkey, "Dunky narrated a bag of chips", 12h old, never covered | 30 | 12 | 15 | 5 | +15 | 0 | **77** | quick (not a lead) |
| - | Same #3 review, but it shipped yesterday | 30 | 12 | -25 | 20 | +8 | -45 | **0** | suppressed |

Read the table as the rules, not as an example:

- **The lead is not simply the highest score - a business-changing event outranks everything.** #2
  scores 100 and #1 scores 83, yet #1 leads, because EA closing BioWare is a permanent change to the
  industry and #2 is a reaction to a marketing rollout. Rule 3.2 carries the full statement; the rubric
  number orders the page, the event class sets the top of it. If the top-scoring item is routine (#8, a
  creator narrating a snack) and a lower-scoring item is a closure, the closure leads and #8 becomes a
  `quick`. This is not a suggestion - edition 2026-10-28 shipped #8 as a `video` section while BioWare
  sat in the packet from AngryJoe. That was the bug this rule exists to prevent.
- **#2 and #3 are both 80+, and both ship** - one as a story, one as the second story with an image.
  There is exactly one `lead`; the next-best does not get dropped, it gets a different slot. Two leads
  fails validation; zero makes the builder promote #1.
- **Format value is why #3 sits under #2** despite double the source weight: a routine let's play is
  worth 5, a documentary-grade explainer 25. Commentary outranks gameplay because he respects it.
  A 5 in V is a *placement* signal, not a drop signal - #8 still ships.
- **#5 is an honest topic return** at 40 days out; inside 21 it would be -25 and -45, i.e. dead, so it
  ships as a `quick` brief and not a comeback. **The suppressed row is arithmetic**, not a judgement:
  `seen` set, -45, however good the item is.
- **Eight candidates gave eight slots plus one suppression.** With `edition_max_stories` at 24 and the
  collection caps at 80 videos / 140 articles, a normal night produces far more than the old six - and
  the old six-candidate habit is exactly the over-selection the owner complained about. If the packet
  has 30 usable items and the edition carries 12, you dropped eighteen stories you already paid to read.
  The failure mode is now under-reporting, not over-reporting.
- **Scoring does not have to be exhaustive arithmetic at 2am.** Score the head of the list carefully,
  then batch the tail: anything that is not worthless goes in a `quickHits` line. A `quickHits` line
  costs one sentence and one URL and it is not a lesser story.

### 3.2 What earns the front page

- **Everything of substance earns a slot.** The default is inclusion. Work down the judged list and
  place each item; a story is only absent because it is worthless (the list in section 3), because
  `seen` already shipped it, or because the cooldown covers the subject. "Not front-page material" is
  not a reason - that is what `quick` and `quickHits` are for.
- A big thing from the last 24h in his lanes: a creator he watches with a real take on a real event; a
  game/platform/business move; an AI or hardware change touching his work or his 8GB laptop; a
  game-dev technique that touches Godot, Hytale or Roblox.
- **Creator take vs routine let's play:** a take on a big event beats a routine let's play, a trailer
  reaction beats a podcast clip, a long-form documentary beats nearly everything on quality, and a
  3-hour stream VOD is last. The rubric encodes this - do not re-litigate it. It is an ordering, not a
  filter: the 3-hour VOD still gets a `quickHits` line unless it is worthless.

- **Cooldown is 21 days** (`repeat_topic_cooldown_days`). Nothing returns inside that window unless the
  comeback exception in `config/interests.md` holds on all three counts, and then you say in one clause
  that the earlier beat was covered. **Never repeat what memory says was covered**: `packet.md`,
  `filtered.json` and `suppressed.json` carry the evidence, and `python scripts/memory.py query --topic
  <slug>` answers "when did we last run this".

  **`seen: true` means OUT - it is not a score.** The -45 in the rubric is bookkeeping for the
  suppressed row, never a way for a repeat to survive: an item already shipped is removed from
  consideration entirely, however good it is.

  **Cooldown applies to SUBJECTS, not categories.** The packet's cooling list is generated from the
  topic index, and umbrella tags (`gaming`, `ai`, `tech`, `hardware`, `industry`, `pc`, `world`) tag
  110 of 113 candidates. Those words are now filtered out of the index on purpose (`GENERIC_TOPICS`
  in `scripts/memory.py`), so if one still appears in a cooling list, ignore it - the real gate is the
  specific topic (`bioware`, `ff14`, `gta6`, `where-winds-meet`). Reading the cooldown literally
  would forbid the whole edition; reading it as "same subject twice" is the intent.
  `python scripts/memory.py digest` is the wide view: most-covered topics, everything
  currently cooling down, and what has been quiet 30+ days. Anything on that last list may
  come back - but only with a genuinely new development, written as a follow-up, never as
  fresh news.
  After marking memory, run `python scripts\memory.py digest --write` - it saves a dated
  coverage report to `docs/coverage/<date>.md` and commits with the edition. That file is the
  owner's month-later reminder; it is not optional decoration.
- **Never lead with** a rumour, a benchmark chart with no product behind it, a 3-hour VOD, an
  unverifiable story, or anything in the NEVER list of `config/interests.md`.
- **Tone:** funny, warm, optimistic even on bad news, never cruel, no filler - enforced by
  `config/interests.md` section TONE RULES (one em dash per paragraph max, zero exclamation marks in
  body copy, sentence-case headlines, no full stop).
- **Length discipline:** 5-24 sections (`edition_min_stories` / `edition_max_stories`), **exactly one
  lead**, four to fourteen `quickHits`, at most one `quote`. Aim high: an edition that fits 20 real
  stories should carry 20. Never pad to reach a number, and never drop a real story to keep the count
  tidy - if you write 24, all 24 must be real.
- **Ties** break: (1) does it change something for him, (2) does it have an image, (3) is it a creator
  he actually watches.

#### 3.2.1 Business-changing events outrank everything

**A closure, an acquisition, a mass layoff, or the cancellation of a major title is top-tier news
regardless of which source carried it.** It is not a "story weight" question and it is not subject to
the tier ordering: a tier-3 feed reporting a studio closure outranks a tier-1 channel's snack video.

- **Source weight does not gate it.** If the only item in the packet is a small outlet or a low-weight
  aggregator reporting that a studio is closing, that is the lead. Two independent low-weight sources
  reporting the same closure is confirmation, and `also_on` already records it.
- **A creator's opinion video on such an event is a lead candidate**, even when the video is long, even
  when the creator is normally a commentary channel. The video is the take; the event is the story.
  Lead with the event and cite the creator, rather than filing it as "a video from X".
- **The whole class counts, not just closures:** studio shutdown, acquired-and-absorbed, mass layoff
  (anything reported as a mass or studio-wide cut), a major title cancelled, a flagship studio's
  leadership removed, a platform delisting a whole catalogue. A game being delayed is *not* in this
  class unless it is cancelled.
- **Never let a routine item from the same channel displace it.** One channel can produce both a
  "we played X for episode 147" upload and a "the studio is gone" video in the same window. The second
  is the lead; the first is worthless and gets dropped. Ranking them on T+F+V alone is how the
  2026-10-28 edition missed **EA closing BioWare** - present in the packet from AngryJoeShow, a channel
  the owner named - while shipping a Dunkey video about a bag of chips. That was a real defect, and it
  is the reason this subsection exists.

- **Detection is mechanical now, so you do not have to remember to look.** `scripts/run_daily.py` tags
  every candidate whose headline describes one of these events and, at the top of `packet.md`, prints a
  block headed `## business events (n) - these outrank everything below`. Each flagged line also ends in
  `**BUSINESS EVENT**`. Two consequences for you:

  1. **If that block is non-empty, you must cover it.** Not a quick hit at the bottom - a real section,
     usually near the top. Deciding it is "not that big" is the exact judgement that failed on
     2026-10-28; the detector exists because that judgement was wrong.
  2. **The detector is deliberately generous and the last word is still yours on nuance, not on
     omission.** It matches closures, layoffs, acquisitions, cancellations, delistings and bankruptcy.
     A false positive (say, a headline using "cancels" about a stream) still has to be *mentioned*; it
     just becomes a quick hit. A false negative is the dangerous direction - if you notice a
     business-changing story the detector missed, cover it and say so in the edition's notes.

  `python scripts\test_business_events.py` pins the detector at 19/19 including the real
  "EA CLOSES BIOWARE" headline; run it if you doubt the block.
- **Framing:** report the event plainly and attribute the claim ("EA confirmed", "the studio said"), then
  give the creator's take - section 3.3 is how you find out whether a followed creator made one. Do not soften a closure into a rumour to keep the tone light - the TONE RULES
  ask for optimism about the *mechanism* (what happens to the people, where they go next), never about
  the fact.

### 3.3 Before you write: did anyone I follow cover this?

For a story that is big - a business-changing event per 3.2.1, a game on his actively-played list, or a
studio he has invested in - run the creator search **before** writing the section, not after:

```
python scripts/creator_search.py "Helldivers 2" --hours 72 --tier 1 --title-only
python scripts/creator_search.py "BioWare" --hours 72 --tier 1 --title-only
python scripts/creator_search.py "Godot" --hours 72 --tier 1 --title-only
```

Swap the term for the story's key noun ("Warframe", "Crimson Desert", "studio closure" is too vague - use
the studio or game name). `--hours 72` is wider than the 50-hour collect window on purpose: a creator's
take often lands a day after the news, and a 60-hour-old take still strengthens today's section.
`--tier 1` keeps it to the channels he actually watches; drop the flag when the story is big enough that
a tier-2 take is worth having.

**If a followed creator covered it, the edition carries their take** - attributed by name, with a link,
inside the section that already covers the event. Not a separate "a video from X" section: lead with the
event, then give the take (3.2.1 says the same thing for lead selection). Their opinion is the point -
"especially if it comes from any of the YouTubers that I actively follow, because their opinions matter
the most."

**Honest limits, so a null result is not read as proof.** Default `--scope channel` asks each of the 48
enabled channels' own search index, which is complete but slow: roughly one to two minutes, and the
public Invidious instances throttle bursts, so a few channels can come back `unreachable` after the built-in
retry. That means **"no coverage found" only for the channels it actually reached** - it is not a statement
about YouTube as a whole. If the run matters and the list of unreachable channels is long, re-run it once;
do not conclude "nobody covered this" from one throttled pass.

**Use `--title-only`.** The channel index matches descriptions as well as titles, so a broad term returns
videos that merely mention it: a smoke test on "Godot" returned 32 hits of which 32 were description-only.
`--title-only` drops them and on "BioWare" cut 4 hits down to the 2 real takes. A description match is a
passing mention, not a take worth quoting - so filter them at the tool rather than trusting yourself to
ignore them at 03:00.

One more precision caveat, measured rather than assumed: the `published` value it prints is not the real
publish time. The instance derives it from the rounded relative text ("3 days ago", "1 year ago"), which
is why three consecutive results came back as exactly 72.0h, 120.0h and 144.0h old. The error is therefore
**up to ~24 hours at day scale** ("1 day ago" can be anywhere from 24 to 48 hours), and much larger at
"1 year ago" scale. So `--hours 72` means "roughly three days", not "exactly 72 hours": a hit just outside
the window may still be inside it. Treat a hit as "recent enough to check", then read the real date on the
video page before writing it as today's. Do not put the tool's date in a sentence as fact.

`--scope global` is the fast alternative (one query, then filtered to followed channels) but it ranks by
popularity, so a small channel's video about the topic can simply not appear - use it for a broad read,
never as the answer to "did he cover it".

**Expect nothing for Godot, and that is not a failure.** No followed channel covers engine releases, so
this step returns zero for that lane. Godot news arrives as articles (`Godot Blog` is in the feed list),
and that is the correct source for it. Do not skip an engine story because the creator step was empty.

**It is read-only.** It fetches, prints a table, and exits; `--json <path>` writes the payload for a
workpack and touches nothing else. Safe to run at 03:00, no browser, no window, no writes to editions or
memory. It also drops let's-play uploads by default, consistent with CHANNEL POLICY - so a hit it returns
is already a take, not gameplay.

## 4. Write the edition

`editions/YYYY-MM-DD.json`, UTF-8, no BOM. Full schema (SPEC section 6):

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

Rules the builder enforces, so learn them once: `date` equals the filename date and `number` is the
previous edition's + 1; `kind` drives layout (`lead` hero, exactly one; `story` article; `video`
thumbnail card; `quick` short brief; `quote` pull quote); body supports **only** `**bold**`,
`*italic*`, `[text](url)` and escapes everything else; `id` is `[a-z0-9-]+`, unique, and becomes the
`#id` anchor; every non-`quick` section needs `source.label` + `source.url`, and `quickHits[].url` is
http(s); `image` is optional but all three of `src`/`alt`/`credit` are required when present, with
`src` local (`../state/workpack/<date>/img/<hash>.jpg`) or http(s) for the builder to download,
optimise and rewrite; `tags` are topic slugs and are what the 21-day cooldown keys on.

### 4.0 The page never forces a click (owner's instruction, 2026-10-28)

Every section must be complete on the page. He reads the Beacon so he does *not* have to open the
video, the article or the store page - a source link is provenance and a route to more, never the
place the facts live.

- **Put the substance in the prose:** numbers, names, dates, prices, consequences. "The video explains
  why" is a failure.
- **Summarise a creator's take in their own voice**, attributed: what they argued and why. Name-dropping
  that a video exists is not a take.
- **Never write:** "watch the full video", "read the full report", "see the source for more", "details
  in the video", "click through".
- **The test before you publish:** delete every source link. Each section must still be a complete,
  useful paragraph.

This is enforced by `test_taste_contract.py` against the `SELF-CONTAINED WRITING` section of
`config/interests.md` - if the rule is deleted there, the suite fails.

### 4.1 `lead` - fully filled

```json
{
  "id": "studio-reveal-backfire",
  "kind": "lead",
  "priority": 100,
  "kicker": "GAMING",
  "headline": "A studio spent a week teasing a reveal and shipped a logo",
  "standfirst": "Fourteen minutes of commentary later, the interesting part is how fast the community rebuilt the announcement themselves.",
  "body": [
    "The teaser ran eleven seconds, showed **a logo and a date**, and the studio's own channel pinned a comment promising a full reveal in seven days.",
    "By the evening the subreddit had taken the frame apart: the reflection in the logo plate is a known engine screenshot, and the date matches a storefront listing live since spring. [The thread](https://example.com/thread) is the actual coverage of this thing - a studio announcing an announcement to an audience that has learned to read the pixels."
  ],
  "image": {"src": "../state/workpack/2026-10-28/img/9f2a11c04b7de833.jpg", "alt": "A dark studio logo plate with a faint reflection of a game environment", "credit": "YouTube / Asmongold TV"},
  "source": {"label": "Asmongold TV", "url": "https://www.youtube.com/watch?v=XEOzMFZHdcU"},
  "tags": ["studio-reveal", "marketing"],
  "whyItMatters": "He follows the reveal cycle, not the announcement - and the cycle is now shorter than the marketing plan.",
  "aside": "A logo, a date, and a pinned comment. Somebody's bonus depends on this."
}
```

### 4.2 `story` - fully filled

```json
{
  "id": "voxel-lod-seam",
  "kind": "story",
  "priority": 80,
  "kicker": "GAME DEV",
  "headline": "The voxel LOD seam that every Godot tutorial skips, solved in one shader mask",
  "standfirst": "Nineteen minutes, one mesh, and a transition band that stops the terrain turning into a sheet of paper at distance.",
  "body": [
    "Marching cubes is not the hard part any more - there are a dozen copyable implementations. The seam between LOD levels is, and this devlog spends most of its runtime there.",
    "The fix is a vertex-shader mask that lerps the two resolutions across a band rather than snapping at a distance threshold. The project files are linked in the description.",
    "*Caveat: the demo runs on a desktop GPU, and the author says nothing about integrated hardware.*"
  ],
  "image": {"src": "../state/workpack/2026-10-28/img/4471ab90cd12ef55.jpg", "alt": "Blocky green voxel terrain with a visible distance seam in the Godot editor", "credit": "YouTube / Game Dev Buddies"},
  "source": {"label": "Game Dev Buddies", "url": "https://www.youtube.com/watch?v=example-voxel"},
  "tags": ["godot", "procedural-generation"],
  "whyItMatters": "This is the exact seam the current terrain prototype will hit in month two.",
  "aside": "No intro animation, no sponsor read in the first thirty seconds. A gift."
}
```

### 4.3 `video` - fully filled

```json
{
  "id": "castlevania-full-run",
  "kind": "video",
  "priority": 60,
  "kicker": "REVIEW",
  "headline": "A four-hour Castlevania run that is really a review with a controller in hand",
  "standfirst": "The verdict arrives at hour three, after the movement tech has been demonstrated rather than described.",
  "body": [
    "Most of the runtime is play, but the argument is in the boss rooms: the dodge window is generous on purpose, and the game is built around that generosity rather than fighting it.",
    "It is a full-game video and it is long. Watch the first twenty minutes for the verdict, the rest for the feel."
  ],
  "image": {"src": "../state/workpack/2026-10-28/img/6b7f0c3d9a21ee44.jpg", "alt": "A gothic castle corridor rendered in a side-scrolling action game", "credit": "YouTube / MoistCr1TiKaL Gaming"},
  "source": {"label": "MoistCr1TiKaL Gaming", "url": "https://www.youtube.com/watch?v=Gzzhg_QGluw"},
  "tags": ["castlevania", "review"],
  "whyItMatters": "Movement feel is the thing he judges action games on, and this is four hours of it.",
  "aside": "Four hours. The man does not do short."
}
```

### 4.4 `quick` - fully filled

```json
{
  "id": "warframe-rifle-buff",
  "kind": "quick",
  "priority": 40,
  "kicker": "WARFRAME",
  "headline": "Mid-tier auto rifles get base damage, not a nerf, for once",
  "body": [
    "Base damage up on the auto rifles, multishot mods unchanged, and nothing in the patch requires platinum. The grind ladder is exactly where it was."
  ],
  "source": {"label": "PC Gamer", "url": "https://example.com/warframe-patch"},
  "tags": ["warframe"]
}
```

### 4.5 `quote` - fully filled

```json
{
  "id": "quote-shipping",
  "kind": "quote",
  "priority": 30,
  "kicker": "QUOTE",
  "headline": "We shipped the demo before we shipped the pitch deck, and that is the only reason anyone answered the email.",
  "body": ["A two-person studio, on how they got signed."],
  "source": {"label": "Visual Venture", "url": "https://www.youtube.com/watch?v=example-quote"},
  "tags": ["indie"]
}
```

## 5. Build, publish, mark

These four, in this exact order, one at a time, reading the last line of each.

| Step | Command | Expected last line |
|---|---|---|
| 0 pre-flight | `python scripts/build_edition.py --check --date <date>` | `CHECK OK: <n> sections, <k> quick hits` (exit 0) |
| 1 build | `python scripts/build_edition.py --date <date>` | `build done: <date> - <n> sections, <i> images, <b> bytes, <l> links` |
| 2 publish | `python scripts/publish.py` | `publish: pushed to origin/<branch>, live url <url>` |
| 3 verify (optional) | `python scripts/publish.py --verify --wait 120` | `verify: 200, masthead found, <n> bytes, <url>` |
| 4 mark | `python scripts/memory.py mark --edition editions/<date>.json` | `marked: <n> new items, <n> topics, edition <date>` |

Observed `build_edition.py` flags (do not guess others): `--date`, `--edition`, `--out-dir`, `--root`,
`--check`, `--fixture`, `--no-images`, `--quiet`. Exit 0 on success or `CHECK OK`, 1 on failure.

- **`--check`** validates only, writes nothing: missing keys, two leads, an empty body, bad inline
  markup, a non-quick section with no source, a missing image credit. Before publish, always.
- **`--date`** writes `site/index.html`, `site/archive/<date>.html`, `site/archive.html` and
  `site/assets/<date>/`. Success is exit 0 **plus** a rewritten `site/index.html`; a build can exit 0
  with one remote image skipped (`WARN: image skipped <id>: http 404`), which is fine if it still reads.
- **`publish.py`** commits, pushes `main`, then mirrors `site/` onto `origin/gh-pages` (which is what
  Pages actually serves) and prints the live URL. Variants: `publish: nothing to commit`,
  `publish: no site built - run build_edition.py first`, `publish: BLOCKED - possible secret in
  <file>`, `publish: origin/gh-pages already up to date`, `... live url not set ...`. It never
  force-pushes. A push to `main` that does not mirror is a live-page no-op, so treat a non-zero exit
  from `publish.py` as "the site did not update", whatever the earlier lines said.
- **`--verify`** GETs the live URL and requires HTTP 200 plus the masthead. Only after a push.
- **`memory.py mark`** is idempotent: twice prints the same shape of line and adds nothing. Skipping it
  is what makes tomorrow repeat today.

> NOTE: SPEC section 7 still shows `--open`, but the current builder has no such flag - passing it is
> an argparse error; build and verify headlessly (exit code, file size, `--check`), never by opening a
> browser. `site_base_url` is already set on this checkout, so the `live url not set` variant means the
> settings file was replaced, not that the run failed - fix it with `--set-url` and continue.
> `pages_branch` in `config/settings.json` names the branch Pages is served from (`gh-pages`); an empty
> value turns the mirror off. Do not edit it without checking `gh api repos/<owner>/<repo>/pages`.

## 6. When something fails

| Symptom | What you do | What you never do |
|---|---|---|
| `collect` exits non-zero, or no `packet.md` | Retry once with `--reuse-source`; if it fails again, build a 3-5 section edition from whatever workpack files exist | Skip the edition; fabricate items to fill it |
| `packet.md` shows a few channels/feeds failed | Publish normally; mention the failing source in one clause of one section and in the run note | Claim coverage you did not collect |
| No transcripts at all | Judge from titles, channels, thumbnails and article bodies; keep claims to what those state | Invent what a video "probably says" |
| Fewer than 5 usable candidates | Publish a short honest edition: one lead, two or three stories, three quick hits | Pad with repeats or rumours; publish an empty page |
| `--check` fails, or `--date` exits 1 | Read the message - it names the JSON path (`sections[2]: missing required key 'source'`) - fix the JSON, re-run. After two failed passes, stop editing today and leave yesterday's built site untouched | Edit or hand-patch `site/*.html`, `style.css`, `app.js` to make it pass |
| `publish.py` fails (git error, secret block, no network) | Leave the built site exactly as it is; write the first error line into the run note; the page is complete but not live | `git push --force`; rewrite history; delete the commit |
| Pages returns 404 after a push | Re-run `python scripts/publish.py --verify --wait 300`; if it still fails, record the 404 in the run note | Rebuild into a different directory; re-push in a loop |
| `publish: mirrored site/ to origin/gh-pages` is missing from the output, or `publish.py` exits 1 after pushing main | The live page did not update: re-run `python scripts/publish.py` once, then `--verify --wait 300`. If the mirror still refuses, publish `site/` to `gh-pages` by hand in a temp clone and note it | Leave it - a green commit on main looks published and is not |
| `state/seen.sqlite` locked or corrupt | Skip `mark`, note it in the run note; the edition still ships | Delete the database; recreate it by hand |
| Collection failed entirely | Still publish: a three-section edition whose lead says plainly which part failed and what it means | A blank page, silence, or a "sorry" page with no content |

Every one of these ends the same way: an edition exists, is built, and the run note says what happened.

## 7. Never

- **Never open a browser, a window, a folder or any GUI.** The owner may be at the PC and a stolen
  window ruins a session; all verification is headless - exit codes, file sizes, `--check`, HTTP.
- **Never ask a question.** Nobody is there: decide, or take the minimum-viable path in section 6.
- **Never touch another project.** Only paths inside `daily-beacon`.
- **Never edit generated or build files**: `site/index.html`, `site/archive*`, `site/style.css`,
  `site/app.js`, `build_edition.py`, `publish.py`. The edition is the input; the scripts are not.
- **Never `pip install`** anything. Python 3.11 stdlib plus the packages already present.
- **Never print a token, a secret, or a config value that could be one.**
- **Never `git push --force`**, rewrite history, or delete an existing edition file.
- **Never touch the scheduler** or any file outside the edition/site/run-note set.
- **Never invent, never overstate, never pad.** See section 1.

## 8. Finish

Write `docs/runs/YYYY-MM-DD.md` - **exactly three lines**, no heading, no bullets, no blanks:

```
shipped: edition <date> no. <n>, <s> sections, <k> quick hits, live at <url>
suppressed: <what you dropped and why, one clause, or "nothing">
note: <anything a human must know, or "clean run">
```

Literal filled example:

```
shipped: edition 2026-10-28 no. 1, 9 sections, 6 quick hits, live at https://nxaxrxo.github.io/daily-beacon/
suppressed: two Castlevania uploads (same topic as the story) and one GTA rumour with no source
note: yt producer summary failed, packet counts unreliable; publish ok, verify 200
```

Then stop: no chat summary, no extra files, no cleanup pass - the run note is the report, the live page
the deliverable.
