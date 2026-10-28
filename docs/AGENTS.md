# AGENTS - the 03:00 unattended runbook

You are the agent that builds today's Daily Beacon. Nobody is awake. Nobody will answer a question.
Everything you need is in this file and in `config/interests.md`. Follow it top to bottom.

## Quick reference

| Command | What it does | Expected last line |
|---|---|---|
| `python scripts/run_daily.py collect --date <date>` | fetch channels + feeds, filter seen, fetch transcripts, download images, write the work packet | `collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed` |
| `python scripts/build_edition.py --date <date>` | validate the JSON and render the site | exit 0, one summary line starting `build:`, `site/index.html` rewritten |
| `python scripts/build_edition.py --date <date> --check` | validate only, write nothing | `CHECK OK` (exit 0) |
| `python scripts/publish.py` | commit + push, print the live URL | `publish: pushed to origin/<branch>, live url <url>` |
| `python scripts/memory.py mark --edition editions/<date>.json` | record what shipped, so tomorrow cannot repeat it | `marked: <n> new items, <n> topics, edition <date>` |

## What good looks like

The finished page is a dark newspaper that reads as one person's briefing, not a feed. The lead dominates
the fold: one headline at twice the size of anything else, a small-caps kicker above it, a standfirst
carrying the fact the headline could not, one credited image, three or four paragraphs, a "Why it
matters" line, then the aside. Below it: a few thumbnail cards, one pull quote set large and alone, the
Quick Hits rail of four to seven one-line links, then the colophon (edition number, generated timestamp,
story count, tracked/suppressed counts, signoff, archive link). Anchors work, the table of contents jumps
to them, and every headline and Quick Hit goes somewhere real. If a reader clicks three links and all
three are genuine, the edition is good.

## 1. You are here / the contract

- Project root: `C:\Users\MarciNaro\Documents\VSCODE-PROJECTS\daily-beacon`. Every command below is run
  from there, with the project's own Python. Never `cd` anywhere else.
- Today's edition is `editions/<YYYY-MM-DD>.json` for today's local date, plus the site it renders to.
- **The absolute rules, no exceptions, no clever readings:**
  - **Never invent a news item.** If it is not in `state/workpack/<date>/packet.md`, a transcript, or a
    source you actually fetched, it does not go in the edition.
  - **Never present an unverified claim as fact.** Attribute it ("the studio says", "the patch notes
    claim"), or leave it out. No hedging words are a substitute for a real source.
  - **Every story links to its real source.** A section without a working `source.url` fails the build
    anyway (docs/SPEC.md §6).
- **The taste sheet is binding: `config/interests.md`.** It holds LOVES / LIKES / NEUTRAL / DISLIKES /
  NEVER, the numeric scoring rubric, the tone rules, the cooldown rule and "what the edition is not".
  Read it in full before you judge anything. It outranks your own taste; you are not the reader.
  Do not duplicate its rubric here - use it.
- Full contracts: `docs/SPEC.md` (schema §6, directory §1), `docs/CONTRACTS.md` (CLI + packet format),
  `docs/SITE-CONTRACT.md` (what the builder emits), `docs/DECISIONS.md` (settled choices).

## 2. Collect

Run, in this order, one command at a time:

1. `python scripts/run_daily.py collect --date <today>`
   Last line: `collect done: <v> videos, <a> articles, <t> transcripts, <r> repeats suppressed`.
   Any non-zero exit here is a collection failure - see §5.
2. Read `state/workpack/<date>/packet.md` in full. It is the briefing: counts, top videos, top articles,
   what is cooling down, and the next commands. Trust its ordering, not its judgement.
3. Read 3-8 transcripts from `state/workpack/<date>/transcripts/<videoId>.txt`. **Read them in slices of
   150 lines** (`read` with `offset`/`limit`), head first then tail if the file is long: transcripts are
   trimmed head+tail with a `[... trimmed N chars ...]` marker, so head and tail carry the argument and the
   conclusion while the middle is filler. Only read more than 8 when the packet is thin.
4. Judge everything else from title + channel/source + thumbnail + length. You do not need a transcript to
   know that a 14-minute video called "the patch that broke everything" is worth a look.
5. Sanity-check images: `state/workpack/<date>/img/` holds the downloaded, Pillow-verified files. Use the
   packet paths verbatim; never invent an image path.

**If `collect` fails or the packet is thin:** run it once more (a single feed timeout is normal). If it
still fails, or the packet has fewer than 5 usable items, publish a short honest edition anyway - 3-5
sections, the lead being what you *do* know, plus one clearly labelled note saying collection was partial
and which source failed. **Minimum viable is still publishing.** Never a blank page, never silence.

## 3. Judge

Apply the rubric in `config/interests.md` §SCORING RUBRIC mechanically - it is numeric and one-pass, so
there is no reason to improvise. Then:

- **Front page** = a big thing that happened in the last 24h in his lanes: a creator he watches having a
  real take on a real event, a game/platform/business move, an AI or hardware change that touches his work
  or his 8GB laptop, a game-dev tool or technique that touches Godot/Hytale/Roblox.
- **Creator take vs routine let's play:** a creator's take on a big event beats a routine let's play; a
  trailer or reveal reaction beats a podcast clip; a long-form documentary beats everything on quality; a
  3-hour let's play is last. The rubric already encodes this in format value - do not re-litigate it.
- **Cooldown:** nothing returns inside 21 days unless the comeback exception in `config/interests.md`
  §COOLDOWN holds, and if it does you must say in one clause that the earlier beat was covered.
- **Never repeat what memory says was covered.** `packet.md` and `filtered.json` carry `seen` flags,
  `seen_reason` and `topic_hits`; `memory.py` reports, you decide. A `seen: true` item is out.
- **Tone:** funny, warm, optimistic even on bad news, never cruel, no filler. Details in
  `config/interests.md` §TONE RULES.
- **Length discipline:** 5-14 sections (`edition_min_stories` / `edition_max_stories`), **exactly one
  lead**, and if you write 14 you had better have 14 real stories. Four to seven Quick Hits, one pull
  quote at most.
- **Picking the lead:** highest rubric score wins, ties broken by (1) does it change something for him,
  (2) does it have an image, (3) is it a creator he actually watches. Never lead with a rumour, a
  benchmark chart with no product behind it, or a story you could not verify.
- **Quick hits** are one line each, a fact plus a link: short, dry, no setup, no "meanwhile".

## 4. Write

### 4.1 The schema - `editions/<YYYY-MM-DD>.json`

Top level, every key:

| Key | Type | Notes |
|---|---|---|
| `date` | string | `YYYY-MM-DD`, must equal the filename date or the build fails |
| `number` | int | edition number, previous edition number + 1 |
| `generatedAt` | string | ISO 8601 with offset, e.g. `2026-10-28T03:14:00+01:00` |
| `masthead` | string | `THE DAILY BEACON` |
| `tagline` | string | one short line, changes with the day if you like |
| `weatherStrip` | string | one-line mood of the day, under the masthead rules |
| `sections` | array | 5-14 objects, exactly one with `kind: "lead"` |
| `quickHits` | array | `{"text": "...", "url": "https://..."}` - both required, url must be http(s) |
| `signoff` | string | one closing line in the colophon |

Section object, every key:

| Key | Required | Notes |
|---|---|---|
| `id` | yes | `[a-z0-9-]+`, unique, becomes the anchor `#id` - keep it stable across rebuilds |
| `kind` | yes | `lead` / `story` / `video` / `quick` / `quote` (rendering below) |
| `priority` | no | number, higher sorts first among non-lead sections |
| `kicker` | no | small-caps label, e.g. `GAMING`, `AI`, `WARFRAME` |
| `headline` | yes | sentence case, no full stop |
| `standfirst` | lead/story/video | one sentence, 12-30 words |
| `body` | yes | array of paragraph strings, non-empty |
| `image` | no | `{"src", "alt", "credit"}` - all three required if the object exists |
| `source` | lead/story/video/quote | `{"label", "url"}` - url must be http(s) |
| `tags` | no | array of topic slugs; these drive the 21-day cooldown, so use the real topic |
| `whyItMatters` | no | one line, rendered as a labelled block |
| `aside` | no | one-sentence joke, rendered last before the source line |

`kind` -> what it renders as:
- `lead` - the hero: biggest headline, image first, kicker above, standfirst, body, Why it matters, aside.
  Exactly one per edition; two is a validation failure, zero makes the builder promote the first section.
- `story` - a standard article block with optional image.
- `video` - the same internals as `story` but card-styled and thumbnail-led; use it for a creator's video.
- `quick` - a short brief: headline plus 1-2 paragraphs. `source` is optional here.
- `quote` - a large pull quote: `headline` is the quoted text, `body` is one short attribution paragraph,
  `source` is required. No image.

Inline markup inside every text field: **only** `**bold**`, `*italic*`, `[text](url)`. Anything else -
raw HTML, backticks, emoji shortcodes, `<br>` - is escaped and shows up as literal characters. Keep
markup out of `headline` where you can; it is rendered, but plain reads better.

Images: `src` is either a local path relative to the edition file (e.g.
`../state/workpack/2026-10-28/img/9f2a11c04b7de833.jpg`) or an `http(s)` URL the builder downloads.
`alt` is mandatory and describes the picture, not the story. `credit` is mandatory and names the source
(`YouTube / Asmongold`, `Digital Extremes`, `PC Gamer`). Wrong or missing credit fails the build.

### 4.2 A filled example (valid, 5 sections)

```json
{
  "date": "2026-10-28",
  "number": 1,
  "generatedAt": "2026-10-28T03:14:00+01:00",
  "masthead": "THE DAILY BEACON",
  "tagline": "Your 3am briefing, slightly unhinged",
  "weatherStrip": "Cold, clear, and one studio lighter than yesterday.",
  "sections": [
    {
      "id": "studio-closure",
      "kind": "lead",
      "priority": 100,
      "kicker": "GAMING",
      "headline": "A studio closes, and its two leads open a new one the same week",
      "standfirst": "Forty people lost their jobs on Monday; by Friday two of them had a company, a prototype and a publisher call.",
      "body": [
        "The closure was announced on the studio's own channel, in a video that ran **four minutes** and said nothing about severance.",
        "What it did not report: two of the leads had been building a prototype on weekends since spring. [Their new page](https://example.com/new-studio) went up on Friday with a 40-second clip and a one-line pitch."
      ],
      "image": {"src": "../state/workpack/2026-10-28/img/9f2a11c04b7de833.jpg", "alt": "Two developers at a kitchen table with a laptop showing a grey test level", "credit": "YouTube / Asmongold"},
      "source": {"label": "Asmongold", "url": "https://youtu.be/example-lead"},
      "tags": ["studio-closure", "indie"],
      "whyItMatters": "The jobs are gone either way. The prototype is the part that survives.",
      "aside": "Four minutes of video and not one of them was the severance meeting."
    },
    {
      "id": "warframe-update",
      "kind": "story",
      "priority": 80,
      "kicker": "WARFRAME",
      "headline": "The new update finally makes rifles worth holding down",
      "standfirst": "Multishot mods are cheaper on the market this week, and the patch notes explain why.",
      "body": ["Base damage on the mid-tier auto rifles went up, not down, which is the opposite of what the last three patches did.", "The grind ladder is unchanged. Apollodorus still works, and nothing here requires platinum."],
      "image": {"src": "https://example.com/warframe-shot.jpg", "alt": "A Warframe character firing a rifle in a dark corridor", "credit": "Digital Extremes"},
      "source": {"label": "PC Gamer", "url": "https://example.com/warframe-update"},
      "tags": ["warframe"],
      "whyItMatters": "A buff to the guns he already owns is the cheapest patch note there is.",
      "aside": "Held trigger, big magazine, no clicking. Somebody read the feedback form."
    },
    {
      "id": "godot-voxel",
      "kind": "video",
      "priority": 60,
      "kicker": "GAME DEV",
      "headline": "Somebody rebuilt smooth voxel terrain in GDScript and it holds at distance",
      "standfirst": "Nineteen minutes, one mesh, and a LOD seam that does not turn into a sheet of paper.",
      "body": ["The interesting part is not the marching cubes. It is the transition mask on the vertex shader, which is the step every tutorial skips."],
      "image": {"src": "../state/workpack/2026-10-28/img/4471ab90cd12ef55.jpg", "alt": "A blocky green terrain mesh rendered in the Godot editor", "credit": "YouTube / Game Dev Buddies"},
      "source": {"label": "Game Dev Buddies", "url": "https://youtu.be/example-voxel"},
      "tags": ["godot", "procedural-generation"],
      "whyItMatters": "This is the exact seam problem the current project will hit in month two.",
      "aside": "Nineteen minutes with no intro animation. A gift."
    },
    {
      "id": "quote-of-the-day",
      "kind": "quote",
      "priority": 40,
      "kicker": "QUOTE",
      "headline": "We shipped the demo before we shipped the pitch deck, and that is the only reason anyone answered the email.",
      "body": ["A two-person studio, on how they got signed."],
      "source": {"label": "Visual Venture", "url": "https://youtu.be/example-quote"},
      "tags": ["indie"]
    },
    {
      "id": "ai-price-cut",
      "kind": "quick",
      "priority": 20,
      "kicker": "AI",
      "headline": "A frontier model drops its price by a third and keeps the benchmark",
      "body": ["Same eval numbers, lower input rate, no new rate limit on the cheap tier."],
      "source": {"label": "The Verge AI", "url": "https://example.com/ai-price"},
      "tags": ["ai-models"]
    }
  ],
  "quickHits": [
    {"text": "A 400GB install is now a normal install size, apparently.", "url": "https://example.com/install-size"},
    {"text": "Roblox co-op horror still has fewer than ten serious entries.", "url": "https://example.com/roblox-horror"}
  ],
  "signoff": "That is the night. Sleep, and the next one writes itself."
}
```

### 4.3 Ship it, in this order

1. `python scripts/build_edition.py --date <date>` - writes `site/index.html`, `site/archive/<date>.html`,
   `site/archive.html` and `site/assets/<date>/`. Judge success by **exit 0 plus a rewritten
   `site/index.html`**; the builder prints one ASCII summary line starting `build:`.
2. `python scripts/build_edition.py --date <date> --check` - validation only, writes nothing. Must print
   `CHECK OK` with exit 0. **This runs before publish, always.** It catches: missing keys, two leads, empty
   body, bad inline markup, a story with no source, a missing image credit.
3. `python scripts/publish.py` - commits and pushes, then prints
   `publish: pushed to origin/<branch>, live url <url>`. If `site_base_url` is not set yet it prints the
   url-missing variant instead; that is not a failure of the run, note it in §7.
4. `python scripts/memory.py mark --edition editions/<date>.json` - prints
   `marked: <n> new items, <n> topics, edition <date>`. This is what makes tomorrow unable to repeat today.
   Never skip it, never run it twice expecting different output (it is idempotent by design).
5. Done. §7.

## 5. Failure handling

- **Collection failed** (non-zero `collect`, or a packet with almost nothing in it): publish a short,
  honest edition - 3-5 sections built from whatever did arrive, one section stating plainly that
  collection was partial and naming the failing part. Never a blank page. Never silence.
- **Build failed** (exit 1, `CHECK OK` absent): read the error, it names the JSON path (`sections[2]:
  missing required key 'source'`). Fix the JSON and rebuild. **Never hand-edit HTML** in `site/`. If it
  cannot be fixed within a few passes, stop editing today's edition, leave the previous edition's built
  site untouched, and publish nothing - a stale page beats a broken one.
- **Publish failed** (git error, secret block, no network): leave the built site on disk exactly as it is,
  and say in your run note that the build is complete but not live, with the error's first line.
- **Never**: force-push, commit a secret, delete or overwrite an existing edition, or "fix" history.
- Every failure is reported in §7, in the same three lines, not hidden.

## 6. Hard limits

- **Never open a browser, a window, a folder, or any GUI.** The owner may be at the PC; a stolen window
  ruins a game or a session. All verification is headless: exit codes, file checks, `--check`, HTTP.
  (memory: he runs all visible testing himself and the agent is forbidden from anything on screen.)
- **Never ask a question.** Nobody is there. Decide, or use the minimum-viable path in §5.
- **Never touch another project.** Only files inside `daily-beacon`.
- **Never modify `site/*.html`, `site/style.css` or `site/app.js` by hand** - they are generated.
- **Never `pip install`** anything, ever. Stdlib plus the packages already present.
- **Never touch the scheduler plugin or `tools/schedule.py`.** The run does not manage its own schedule.
- **ASCII-only console output.** Redirected stdout is cp1252 and emoji crash it.
- **UTF-8 on every file open**, explicit `encoding="utf-8"`.
- Keep the edition JSON valid UTF-8 with no BOM.

## 7. Finish

Write your run note as **exactly three lines** - no heading, no bullets:

```
shipped: edition <date> no. <n>, <s> sections, <k> quick hits, live at <url>
suppressed: <what you dropped and why, in one clause, or "nothing">
note: <anything a human must know, or "clean run">
```

Path: `docs/runs/YYYY-MM-DD.md`.

**Only if `docs/runs/` already exists.** Do not create that directory and do not create any other file
under it - if the folder is absent, print the same three lines to stdout instead and move on. The point is
that the three facts exist somewhere a human will look tomorrow morning: what shipped, what was held back,
and whether the page is actually live.
