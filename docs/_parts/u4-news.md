# u4 - news_source.py

Delivered: `scripts/news_source.py`. Run for real against the final 24-feed config:
`state/workpack/2026-10-28/news.json` = 60 items, every one with an image, from 17 distinct sources.

## CLI (CONTRACTS.md item 2)
`python scripts/news_source.py --out <path> [--hours 26] [--limit N] [--root PATH] [--print-first N]`
`--hours` defaults to settings `lookback_hours`, `--limit` to settings `max_news_items`.
Exit codes: 0 = at least one feed worked; 1 = every feed failed; 2 = feeds.json unreadable/not an array;
3 = output path unwritable. Last stdout line exactly
`news_source done: <n> articles from <ok>/<total> feeds (<failed> failed)`.

## Captured run (2026-10-28, 26h window, 24 feeds)
```
window: 281 items in 26h (0 undated kept)
dedupe: 281 -> 281 stories (0 merged, also_on recorded)
caps: 4/source dropped 181, overall cap 60 dropped 40
images: 60/60 items have one
wrote ...\state\workpack\2026-10-28\news.json
news_source done: 60 articles from 24/24 feeds (0 failed)
EXIT=0
```
Every feed printed `ok <name> <n> entries, <n> in window`; Digital Foundry, Ars Technica Gaming and
Game Developer parsed fine but had nothing inside 26h, which is a healthy-feed situation, not a failure.

## Item shape (canonical, CONTRACTS.md)
`source news`, `kind article`, `key url:<sha1-16>`, `title`, `url`, `publishedAt` (ISO with offset or null),
`score_hint float(weight)`, `tags` (feed tags + mechanical title tags), `thumb_local null`, `sourceName`,
`feedTags`, `summary <= 600`, `image`, `weight`, `also_on`. Validation one-liner asserts every key present,
every key `url:[0-9a-f]{16}`, no duplicate keys, all summaries <= 600 chars.

## Behaviour that matters
- Per-feed try/except: one dead feed is a count in the summary, never an abort.
- Window filter keeps undated items with `publishedAt: null` rather than silently losing a feed whose date
  format changed (0 such items in this run).
- Dedupe by normalised url AND normalised title (Jaccard >= 0.8 on significant words); the highest-weight
  source wins and the rest land in `also_on`. A synthetic 4-item case collapses 2 and records
  `also_on: ['IGN Games']`, including a `?utm_source=tw` url variant.
- Caps: 4 per source, then the overall `max_news_items`, so one prolific feed cannot fill the edition.
- Images: media:content / media:thumbnail / enclosure / first `<img>` in the summary, and at most 10
  `og:image` lazy fetches per run, 8s timeout, silent failure. 60/60 items ended up with an image.
- ASCII-only console, UTF-8 file writes, `--root` default `Path(__file__).parents[1]`.

## Notes
- A BeautifulSoup `MarkupResemblesLocatorWarning` is emitted to stderr when a summary is bare text; harmless,
  output goes to stderr and the run still exits 0.
- Nothing outside `scripts/news_source.py` and the workpack output path was modified.
