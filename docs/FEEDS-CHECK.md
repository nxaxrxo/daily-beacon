# FEEDS-CHECK - live verification of every configured feed

Checked 2026-10-28T11:24:51+01:00 (local), headless from this machine. One GET per feed, browser User-Agent
(`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0`),
20s timeout, redirects followed, `items` = `len(feedparser.parse(body).entries)` (feedparser 6.0.14,
requests 2.33.1, Python 3.11.9). Nothing was opened on screen.

Result: **24 of 24 configured feeds returned HTTP 200 with at least one parsed entry; 0 dead.**

| # | Feed | URL | Tags | W | HTTP | Items | Newest | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | PC Gamer | https://www.pcgamer.com/rss/ | gaming, news | 3 | 200 | 50 | 2026-10-28 | OK |
| 2 | Rock Paper Shotgun | https://www.rockpapershotgun.com/feed | gaming, news | 3 | 200 | 100 | 2026-10-28 | OK |
| 3 | Eurogamer | https://www.eurogamer.net/feed | gaming, news | 3 | 200 | 100 | 2026-10-28 | OK |
| 4 | GamesIndustry.biz | https://www.gamesindustry.biz/feed | gaming, business | 2 | 200 | 100 | 2026-10-28 | OK |
| 5 | VGC | https://www.videogameschronicle.com/feed/ | gaming, news | 2 | 200 | 10 | 2026-10-28 | OK |
| 6 | GameSpot | https://www.gamespot.com/feeds/mashup/ | gaming, news | 2 | 200 | 15 | 2026-10-27 | OK |
| 7 | IGN Games | https://feeds.ign.com/ign/games-all (redirects to https://www.ign.com/rss/articles/feed?tags=games) | gaming, news | 2 | 200 | 20 | 2026-10-28 | OK |
| 8 | PCGamesN | https://www.pcgamesn.com/mainrss.xml | gaming, news | 2 | 200 | 75 | 2026-10-27 | OK |
| 9 | GamesRadar | https://www.gamesradar.com/rss/ (redirects to https://www.gamesradar.com/feeds.xml) | gaming, news | 2 | 200 | 50 | 2026-10-28 | OK |
| 10 | Nintendo Life | https://www.nintendolife.com/feeds/latest | gaming, news | 2 | 200 | 25 | 2026-10-28 | OK |
| 11 | Digital Foundry | https://feeds.feedburner.com/digitalfoundry | gaming, hardware, tech | 2 | 200 | 15 | 2026-10-26 | OK |
| 12 | Tom's Hardware | https://www.tomshardware.com/feeds/all (redirects to https://www.tomshardware.com/feeds.xml) | hardware, tech | 2 | 200 | 50 | 2026-10-28 | OK |
| 13 | Wccftech | https://wccftech.com/feed/ | hardware, tech | 2 | 200 | 20 | 2026-10-28 | OK |
| 14 | Ars Technica Gaming | https://feeds.arstechnica.com/arstechnica/gaming | gaming, tech | 2 | 200 | 20 | 2026-10-23 | OK |
| 15 | Game Developer | https://www.gamedeveloper.com/rss.xml | gaming, business | 2 | 200 | 50 | 2026-10-27 | OK |
| 16 | The Verge AI | https://www.theverge.com/rss/ai-artificial-intelligence/index.xml | ai, tech | 2 | 200 | 10 | 2026-10-27 | OK |
| 17 | TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | ai, tech | 2 | 200 | 20 | 2026-10-28 | OK |
| 18 | Ars Technica | https://feeds.arstechnica.com/arstechnica/index | tech, science | 2 | 200 | 20 | 2026-10-27 | OK |
| 19 | MIT Technology Review | https://www.technologyreview.com/feed/ | tech, science | 1 | 200 | 10 | 2026-10-27 | OK |
| 20 | Google AI Blog | https://blog.google/technology/ai/rss/ (redirects to https://blog.google/innovation-and-ai/technology/ai/rss/) | ai, tech | 1 | 200 | 20 | 2026-10-26 | OK |
| 21 | Hugging Face | https://huggingface.co/blog/feed.xml | ai, tech | 1 | 200 | 891 | 2026-10-27 | OK |
| 22 | Godot Blog | https://godotengine.org/rss.xml | gamedev, tech | 1 | 200 | 15 | 2026-10-25 | OK |
| 23 | Unreal Engine | https://www.unrealengine.com/rss/news | gamedev, tech | 1 | 200 | 10 | 2026-10-27 | OK |
| 24 | Kyiv Independent | https://kyivindependent.com/feed/rss/ | ukraine, world | 1 | 200 | 100 | 2026-10-28 | OK |

Totals: 24 feeds, 24 reachable, 0 with zero entries. Tag mix: gaming 13, tech 12, news 9, ai 4, hardware 3, business 2, science 2, gamedev 2, ukraine 1, world 1.

## Rules applied
- Every feed in `config/feeds.json` is listed here with the status measured at the time above.
- A feed returning 200 with 0 parsed entries counts as DEAD, not as OK; none do right now.
- Spec section 3 cap is 18-25 feeds; this file holds 24.
- Kyiv Independent is the single Ukraine/world-awareness feed and carries the lowest weight (1).
- No politics-dominant outlet is configured. Every other feed is gaming, gaming-tech/hardware,
  AI, games-industry business, or a game-engine/dev blog.

