# The Daily Beacon

A small self-hosted newspaper that writes itself every night at 03:00. A scheduled OpenCode session
collects what happened in the last 24 hours across watched YouTube creators and gaming/AI/tech news
feeds, judges what is worth reading, writes a funny and optimistic dark-mode edition as a single JSON
file, builds a static site from it, and pushes that site to GitHub Pages. A SQLite memory store stops
it from covering the same story twice inside the cooldown window.

Live site: https://nxaxrxo.github.io/daily-beacon/

## The 03:00 flow

1. `python scripts/run_daily.py collect` pulls new videos (`yt_source.py`) and articles
   (`news_source.py`) into `state/workpack/<date>/candidates.json`, runs them through `memory.py`,
   fetches a few transcripts and writes `state/workpack/<date>/packet.md`.
2. The agent reads `docs/AGENTS.md`, then `packet.md`, and judges it against `config/interests.md`.
   It picks one lead plus 4-13 further stories and writes `editions/<date>.json`. No script decides
   what is interesting.
3. `python scripts/build_edition.py --date <date>` validates that JSON and renders `site/index.html`,
   `site/archive.html` and `site/assets/<date>/`.
4. `python scripts/publish.py` commits and pushes the built site. The `pages` workflow uploads `site/`
   and deploys it to GitHub Pages; `publish.py --verify --wait 180` confirms the live URL returns 200
   with the masthead.
5. `python scripts/memory.py mark --edition editions/<date>.json` records every story and topic so
   tomorrow knows what was already covered.

## Editing an edition by hand

Editions are plain JSON and safe to edit directly. The full schema is `docs/SPEC.md` section 6. The
smallest valid edition:

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
      "body": ["First paragraph.", "Second with **bold** and a [link](https://example.com)."],
      "source": {"label": "AngryJoeShow", "url": "https://youtu.be/xyz"},
      "tags": ["gta6"],
      "whyItMatters": "One line on why this leads the paper."
    }
  ],
  "quickHits": [{"text": "Short item.", "url": "https://example.com"}],
  "signoff": "Back tomorrow, same bat-time."
}
```

Exactly one section must be `"kind": "lead"`. Body text supports only `**bold**`, `*italic*` and
`[text](url)`; everything else is escaped. Section `kind` drives layout: `lead`, `story`, `video`,
`quote`.

## Rebuilding the site

```
python scripts/build_edition.py --date 2026-10-28    # rebuild one edition
python scripts/build_edition.py --fixture            # build from fixtures/, touches no real state
python scripts/build_edition.py --check              # validate only
python scripts/publish.py --check                    # what would be published
python scripts/publish.py                            # commit + push, then print the live URL
python scripts/publish.py --verify --wait 240        # poll the live URL until the masthead appears
```

`publish.py` never force-pushes and refuses to commit anything that looks like a secret.

## Adding a channel

Append one object to the array in `config/channels.json`:

```json
{"id": "UCxxxxxxxxxxxxxxxxxxxxxx", "name": "Channel Name", "tier": 2, "tags": ["gaming", "news"], "enabled": true, "note": ""}
```

`tier` 1 = check every day, 2 = check, 3 = only if something big. The `UC...` id is in any channel
RSS URL.

## Adding a feed

Append one object to the array in `config/feeds.json`:

```json
{"name": "PC Gamer", "url": "https://www.pcgamer.com/rss/", "tags": ["gaming", "news"], "enabled": true, "weight": 1}
```

`weight` is the mechanical score hint, higher wins a tie at the cap. Prove the feed resolves before
committing it and record the result in `docs/FEEDS-CHECK.md`.

## Changing the schedule

The record lives in the scheduler plugin (`~/.config/opencode/plugins/scheduler/`, `schedules.json`
next to the runtime), never in this project. Accepted formats:

```
daily:03:00                  days:2@03:00               weekly:mon@03:00
weekly:mon,wed,fri@03:00     hourly:45                  monthly:1@03:00
once:2026-10-28T03:00        every:30m | every:2h | every:3d
```

Edit the record for this project to the time you want. The plugin only fires a session; the run is
driven by `docs/AGENTS.md`. Catch-up is deliberate: a missed slot fires once on the next tick, never a
burst.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Live URL 404s | Pages source must be "GitHub Actions", not a branch. Check `gh api repos/nxaxrxo/daily-beacon/pages`. If it 404s, Pages is not enabled: `gh api repos/nxaxrxo/daily-beacon/pages -X POST -f build_type=workflow`. Then confirm the `pages` workflow actually ran: `gh run list --workflow pages`. |
| Workflow ran, still 404 | `site/index.html` must be committed. An empty `site/` uploads nothing to serve. Run `python scripts/build_edition.py --date <date>` then `python scripts/publish.py`. |
| A feed is down | See `docs/FEEDS-CHECK.md` for each feed's recorded status. Fix the URL or set `"enabled": false`; one dead feed never kills a run. |
| The build fails | `python scripts/build_edition.py --check` names the problem: a missing key, a second `lead`, an empty body, bad inline markup, a story with no source. |
| Publishing refuses | The secret guard blocked a staged `.env`, `*.pem`, `*.key`, `*_token*`, `credentials.json` or a token pattern. The file was unstaged automatically. Tokens never belong in this repo. |
| `publish: no site built` | `site/index.html` is missing. Build first, then publish. |
| `publish: nothing to commit` | The site is already committed. Publishing continues to the push, which is normal. |
