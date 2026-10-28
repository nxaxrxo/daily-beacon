# The Daily Beacon

The Daily Beacon is a small, self-hosted newspaper that writes itself every night at 03:00. A scheduled
OpenCode session collects what happened in the last 24 hours across watched YouTube creators and gaming/AI/tech
news feeds, judges what is actually worth reading, writes a funny and optimistic dark-mode edition as a single
JSON file, builds a static site from it, and pushes that site to GitHub Pages. A SQLite memory store keeps it
from covering the same story twice within the cooldown window.

## How the 03:00 run works

The chain is collect -> judge -> write JSON -> build -> publish -> mark:

1. `python scripts/run_daily.py collect` pulls new videos (`yt_source.py`) and articles (`news_source.py`) into
   `state/workpack/<date>/candidates.json`, filters them through `memory.py`, fetches a few transcripts, and
   writes `state/workpack/<date>/packet.md` - the briefing the agent actually reads.
2. The agent judges the packet against `config/interests.md`, picks one lead and 4-13 further stories, and
   writes `editions/<date>.json`. No script decides what is interesting.
3. `python scripts/build_edition.py --date <date>` validates that JSON and renders `site/index.html`,
   `site/archive.html` and `site/assets/<date>/`.
4. `python scripts/publish.py` commits and pushes the built site; the `pages` workflow deploys `site/` to
   GitHub Pages, and `publish.py --verify` confirms the live URL returns 200 with the masthead.
5. `python scripts/memory.py mark --edition editions/<date>.json` records every story and topic so tomorrow
   knows what was already covered.

## Editing an edition by hand

Editions are plain JSON and safe to edit directly. The schema is in `docs/SPEC.md` section 6. A minimal,
valid edition:

```json
{
  "date": "2026-10-28",
  "number": 7,
  "generatedAt": "2026-10-28T03:14:00+01:00",
  "masthead": "THE DAILY BEACON",
  "tagline": "Your 3am briefing, slightly unhinged",
  "weatherStrip": "grey, with a chance of patch notes",
  "sections": [
    {
      "id": "gta6-trailer",
      "kind": "lead",
      "priority": 100,
      "kicker": "GAMING",
      "headline": "Rockstar blinks first",
      "standfirst": "One sentence of deck copy.",
      "body": ["First paragraph.", "Second paragraph with **bold** and a [link](https://example.com)."],
      "image": {"src": "../state/workpack/2026-10-28/img/abc123.jpg", "alt": "Trailer still", "credit": "YouTube / AngryJoeShow"},
      "source": {"label": "AngryJoeShow", "url": "https://youtu.be/xyz"},
      "tags": ["gta6"],
      "whyItMatters": "One line on why this is on the front page.",
      "aside": "Optional joke."
    }
  ],
  "quickHits": [{"text": "Short item.", "url": "https://example.com"}],
  "signoff": "Back tomorrow, same bat-time."
}
```

Exactly one section must have `kind: "lead"`. Body text supports only `**bold**`, `*italic*` and
`[text](url)`; everything else is escaped.

## Rebuilding the site

```
python scripts/build_edition.py --date 2026-10-28        # rebuild one edition
python scripts/build_edition.py --date 2026-10-28 --open # ... and open it (machine with a screen only)
python scripts/build_edition.py --fixture                # build from fixtures/, touches no real state
python scripts/publish.py --check                        # what would be published
python scripts/publish.py                                # commit + push, then print the live URL
python scripts/publish.py --verify --wait 240            # poll the live URL until the masthead appears
```

`publish.py` never force-pushes and refuses to commit anything that looks like a secret.

## Adding a channel

Append an object to the array in `config/channels.json`:

```json
{"id": "UCxxxxxxxxxxxxxxxxxxxxxx", "name": "Channel Name", "tier": 2, "tags": ["gaming", "news"], "enabled": true, "note": ""}
```

`tier` 1 means "check every day", 2 "check", 3 "only if something big". Find the `UC...` id from the channel
page source or any channel RSS URL.

## Adding a feed

Append an object to the array in `config/feeds.json`:

```json
{"name": "PC Gamer", "url": "https://www.pcgamer.com/rss/", "tags": ["gaming", "news"], "enabled": true, "weight": 1}
```

`weight` is the mechanical score hint (higher = more likely to survive the cap). Check reachability before
committing a new feed and record the status in `docs/FEEDS-CHECK.md`.

## Changing the schedule

The schedule lives in the scheduler plugin (`~/.config/opencode/plugins/scheduler/index.ts`, `schedules.json`
next to the runtime) and accepts these formats:

```
once:2026-10-28T03:00     every:30m | every:2h | every:3d     daily:03:00
weekly:mon@03:00          days:2@03:00                        hourly:45
monthly:1@03:00           weekly:mon,wed,fri@03:00
```

Change the record for this project to the desired time. The plugin only fires the session; the run itself is
driven by `docs/AGENTS.md`. Catch-up is intentional: a missed slot fires once on the next tick, never a burst.

## Troubleshooting

- **Live URL 404s.** Check `gh run list --workflow pages` for a failed run. If the workflow never ran, the
  Pages source is wrong: repository Settings -> Pages -> Source must be "GitHub Actions"
  (`gh api repos/nxaxrxo/daily-beacon/pages -X POST -f build_type=workflow`). Confirm `site/index.html` is
  actually committed - an empty `site/` produces an artifact with nothing to serve.
- **A feed is down.** See `docs/FEEDS-CHECK.md` for the recorded status of every feed, then either fix the URL
  or set `"enabled": false`; one dead feed never kills a run.
- **The build fails.** Run `python scripts/build_edition.py --check` and read the error: it names the missing
  key, the second `lead`, the empty body, the bad inline markup or the story without a source.
- **Publishing refuses.** `publish.py` blocks a staged `.env`, `*.pem`, `*.key`, `*_token*`,
  `credentials.json` or anything matching a token pattern. Unstage or remove the file; tokens never belong in
  this repository.
- **Nothing to publish.** `publish: no site built` means `site/index.html` is missing - build first.