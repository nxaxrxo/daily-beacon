# FEEDS-CHECK - live verification of every configured feed

Verified: 2026-10-28 (headless, no window opened). Python 3.11.9 + `requests` 2.33.1 + `feedparser` 6.0.14,
browser User-Agent `Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/124.0.0.0 Safari/537.36`,
`Accept: application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5`, 20s timeout,
one GET per feed, redirects followed. `items` = `len(feedparser.parse(response.content).entries)`.

A feed counts as WORKING only at HTTP 200 **and** at least one parsed entry. A 200 with an empty or
undated body is treated as dead, because an empty feed silently starves the edition.

Result: **24 of 24 configured feeds returned HTTP 200 with entries. 0 dropped. 0 dead.**

| # | Feed | URL | Tags | Weight | HTTP | Items | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | PC Gamer | https://www.pcgamer.com/rss/ | gaming, news | 3 | 200 | 50 | OK |
| 2 | Rock Paper Shotgun | https://www.rockpapershotgun.com/feed | gaming, news | 3 | 200 | 100 | OK |
| 3 | Eurogamer | https://www.eurogamer.net/feed | gaming, news | 3 | 200 | 100 | OK |
| 4 | GamesIndustry.biz | https://www.gamesindustry.biz/feed | gaming, business | 2 | 200 | 100 | OK |
| 5 | VGC | https://www.videogameschronicle.com/feed/ | gaming, news | 2 | 200 | 10 | OK |
| 6 | GameSpot | https://www.gamespot.com/feeds/mashup/ | gaming, news | 2 | 200 | 15 | OK |
| 7 | IGN Games | https://feeds.ign.com/ign/games-all | gaming, news | 2 | 200 | 20 | OK |
| 8 | PCGamesN | https://www.pcgamesn.com/mainrss.xml | gaming, news | 2 | 200 | 75 | OK |
| 9 | GamesRadar | https://www.gamesradar.com/rss/ | gaming, news | 2 | 200 | 50 | OK |
| 10 | Nintendo Life | https://www.nintendolife.com/feeds/latest | gaming, news | 2 | 200 | 25 | OK |
| 11 | Digital Foundry | https://feeds.feedburner.com/digitalfoundry | gaming, hardware, tech | 2 | 200 | 15 | OK |
| 12 | Tom's Hardware | https://www.tomshardware.com/feeds/all | hardware, tech | 2 | 200 | 50 | OK |
| 13 | Wccftech | https://wccftech.com/feed/ | hardware, tech | 2 | 200 | 20 | OK |
| 14 | Ars Technica Gaming | https://feeds.arstechnica.com/arstechnica/gaming | gaming, tech | 2 | 200 | 20 | OK |
| 15 | Game Developer | https://www.gamedeveloper.com/rss.xml | gaming, business | 2 | 200 | 50 | OK |
| 16 | The Verge AI | https://www.theverge.com/rss/ai-artificial-intelligence/index.xml | ai, tech | 2 | 200 | 10 | OK |
| 17 | TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | ai, tech | 2 | 200 | 20 | OK |
| 18 | Ars Technica | https://feeds.arstechnica.com/arstechnica/index | tech, science | 2 | 200 | 20 | OK |
| 19 | MIT Technology Review | https://www.technologyreview.com/feed/ | tech, science | 1 | 200 | 10 | OK |
| 20 | Google AI Blog | https://blog.google/technology/ai/rss/ | ai, tech | 1 | 200 | 20 | OK |
| 21 | Hugging Face | https://huggingface.co/blog/feed.xml | ai, tech | 1 | 200 | 891 | OK (archive feed; the 26h window filters it) |
| 22 | Godot Blog | https://godotengine.org/rss.xml | gamedev, tech | 1 | 200 | 15 | OK |
| 23 | Unreal Engine | https://www.unrealengine.com/rss/news | gamedev, tech | 1 | 200 | 10 | OK |
| 24 | Kyiv Independent | https://kyivindependent.com/feed/rss/ | ukraine, world | 1 | 200 | 100 | OK |

Mix: 10 gaming-news, 4 gaming-tech/hardware, 1 games-industry business, 3 AI, 2 general tech/science,
2 gamedev, 3 AI/tech extras, 1 Ukraine/world at the lowest weight. That satisfies the spec's "18-25
working feeds" with room to spare and keeps every named category populated.

## Spec candidates that were tried and replaced

| Candidate | Spec / first-tried URL | Result | Shipped instead |
|---|---|---|---|
| Digital Foundry | https://www.eurogamer.net/digitalfoundry/rss | 404 | https://feeds.feedburner.com/digitalfoundry (200, 15) |
| Digital Foundry (own site) | https://www.digitalfoundry.net/feed | 403 (bot block) | same Feedburner feed |
| GamesIndustry.biz | https://www.gamesindustry.biz/feed/rss | 404 | https://www.gamesindustry.biz/feed (200, 100) |
| Game Developer | https://www.gamedeveloper.com/rss/ | 200 but redirects to the homepage, 0 entries | https://www.gamedeveloper.com/rss.xml (200, 50) |
| GameSpot news | https://www.gamespot.com/feeds/news/ | 200, stale list | https://www.gamespot.com/feeds/mashup/ (200, 15) |
| Kyiv Independent | https://kyivindependent.com/api/v1/feed | 404 | https://kyivindependent.com/feed/rss/ (200, 100) |
| Kyiv Independent variants | /feed/, /rss/, /.rss/full/, /news-archive/rss/ | 404 / 404 / 403 / 200-but-stale | the /feed/rss/ URL above |

## Dropped after verification

| Feed | Reason |
|---|---|
| VentureBeat AI | HTTP 429 on `venturebeat.com/category/ai/feed/` and `venturebeat.com/feed/` on repeated attempts over ~5 minutes. AI coverage is carried by The Verge AI, TechCrunch AI, MIT Technology Review and Ars Technica. |
| OpenAI Blog | `openai.com/news/rss.xml` returns 200 and parses 1331+ entries, but it is an undated marketing archive: a 26-hour window cannot select anything from it. Dropped rather than shipped as a feed that can never contribute. |
| Ukrainska Pravda | `pravda.com.ua/rss/` works (200, 20) but duplicates the single Ukraine/awareness slot already held at weight 1 by Kyiv Independent. |
| Kotaku / Dexerto / TheGamer / Variety Gaming / Siliconera | All reachable, all clickbait-heavy or redundant against PC Gamer / RPS / Eurogamer / VGC / GamesRadar. Quality, not reachability, is the reason. |
| Steam News / PlayStation Blog / Xbox Wire | Reachable but promotional first-party feeds with almost no editorial content; the edition would read as a store page. |
| 80.lv / Indie Games Plus / Anime News Network / Ukrinform / Hacker News | Reachable, but outside the spec's named categories or duplicated by a stronger feed in the same lane. |
| The Register / Engadget | Reachable general-tech desks; the hardware lane is covered by Tom's Hardware + Wccftech + Digital Foundry. |

Politics-dominant outlets were excluded by design (spec section 3: "Explicitly EXCLUDE politics-dominant
outlets"). No general politics desk, no opinion column, no aggregator is configured. Kyiv Independent and
Ukrinform were the two awareness candidates; one of them ships, at weight 1.

## Score mapping

`weight` goes straight into `candidates.json` `score_hint` for news items (CONTRACTS.md: news ->
`float(weight)`). Weight 3 = flagship gaming press, 2 = major gaming/tech/AI/business/gamedev,
1 = supplementary and the single awareness feed, so Kyiv Independent can never outrank gaming or AI on
volume alone.
