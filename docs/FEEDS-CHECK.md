# FEEDS-CHECK - live verification of every configured feed

Verified: 2026-10-28, headless, Python 3.11.9 + requests + feedparser, browser User-Agent
(`Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/124.0`), 20s timeout, one GET per feed,
`items` = `len(feedparser.parse(response.content).entries)`.

Result: **21 of 21 configured feeds returned HTTP 200 with at least one parsed entry. 0 dropped.**

| # | Feed | URL | Tags | Weight | HTTP | Items | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | PC Gamer | https://www.pcgamer.com/rss/ | gaming, news | 3 | 200 | 50 | OK |
| 2 | Rock Paper Shotgun | https://www.rockpapershotgun.com/feed | gaming, news | 3 | 200 | 100 | OK |
| 3 | Eurogamer | https://www.eurogamer.net/feed | gaming, news | 3 | 200 | 100 | OK |
| 4 | GamesIndustry.biz | https://www.gamesindustry.biz/feed | gaming, news | 2 | 200 | 100 | OK |
| 5 | VGC | https://www.videogameschronicle.com/feed/ | gaming, news | 2 | 200 | 10 | OK |
| 6 | GameSpot | https://www.gamespot.com/feeds/mashup/ | gaming, news | 2 | 200 | 15 | OK |
| 7 | IGN Games | https://feeds.ign.com/ign/games-all | gaming, news | 2 | 200 | 20 | OK |
| 8 | Digital Foundry | https://feeds.feedburner.com/digitalfoundry | gaming, hardware, tech | 2 | 200 | 15 | OK |
| 9 | Tom's Hardware | https://www.tomshardware.com/feeds/all | hardware, tech | 2 | 200 | 50 | OK |
| 10 | The Verge AI | https://www.theverge.com/rss/ai-artificial-intelligence/index.xml | ai, tech | 2 | 200 | 10 | OK |
| 11 | Ars Technica | https://feeds.arstechnica.com/arstechnica/technology-lab | tech, science | 2 | 200 | 20 | OK |
| 12 | TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | ai, tech | 2 | 200 | 20 | OK |
| 13 | MIT Technology Review | https://www.technologyreview.com/feed/ | tech, science | 2 | 200 | 10 | OK |
| 14 | Game Developer | https://www.gamedeveloper.com/rss.xml | gaming, tech | 2 | 200 | 50 | OK |
| 15 | Kyiv Independent | https://kyivindependent.com/feed/rss/ | news | 1 | 200 | 100 | OK |
| 16 | PCGamesN | https://www.pcgamesn.com/mainrss.xml | gaming, news | 2 | 200 | 75 | OK |
| 17 | GamesRadar | https://www.gamesradar.com/rss/ | gaming, news | 2 | 200 | 50 | OK |
| 18 | Nintendo Life | https://www.nintendolife.com/feeds/latest | gaming, news | 2 | 200 | 25 | OK |
| 19 | Wccftech | https://wccftech.com/feed/ | gaming, hardware, tech | 2 | 200 | 20 | OK |
| 20 | Engadget | https://www.engadget.com/rss.xml | tech, hardware | 2 | 200 | 20 | OK |
| 21 | Ars Technica Gaming | https://feeds.arstechnica.com/arstechnica/gaming | gaming, tech | 2 | 200 | 20 | OK |

Downloaded totals: 21 feeds, 100% reachable with entries. Mix = 11 gaming-news, 4 gaming-tech/hardware,
4 AI, 1 games-industry business (GamesIndustry.biz doubles as gaming news), 1 Ukraine/world at weight 1.

## URLs that were tried and replaced (spec candidates that no longer work)

| Candidate | Spec URL | Result | Replacement shipped |
|---|---|---|---|
| Digital Foundry | https://www.eurogamer.net/digitalfoundry/rss | 404 | https://feeds.feedburner.com/digitalfoundry (200, 15) |
| Digital Foundry (own site) | https://www.digitalfoundry.net/feed | 403 | same Feedburner feed |
| GamesIndustry.biz | https://www.gamesindustry.biz/feed/rss | 404 | https://www.gamesindustry.biz/feed (200, 100) |
| Game Developer | https://www.gamedeveloper.com/rss/ | 200 but redirects to the homepage, 0 entries | https://www.gamedeveloper.com/rss.xml (200, 50) |
| GameSpot news | https://www.gamespot.com/feeds/news/ | 200, 30 entries but stale | https://www.gamespot.com/feeds/mashup/ (200, 15) |
| Kyiv Independent | https://kyivindependent.com/api/v1/feed | 404 | https://kyivindependent.com/feed/rss/ (200, 100) |
| Kyiv Independent variants | /feed/, /rss/, /.rss/full/, /news-archive/rss/ | 404 / 404 / 403 / 200-but-stale | /feed/rss/ |

## Dropped after verification

| Feed | Reason |
|---|---|
| VentureBeat AI | HTTP 429 on `venturebeat.com/category/ai/feed/`, `venturebeat.com/feed/` and the AI category root, on repeated attempts. AI coverage is carried by The Verge AI, TechCrunch AI, MIT Technology Review and Ars Technica. |
| OpenAI Blog | `openai.com/news/rss.xml` parses 1331 entries but is a marketing archive with no usable publication window for a 26h lookback. |
| Hugging Face Blog | `huggingface.co/blog/feed.xml` parses 891 entries, same archive problem; too noisy for a 60-item cap. |
| Ukrainska Pravda | `pravda.com.ua/rss/` works (200, 20) but duplicates the single Ukraine/awareness slot already held by Kyiv Independent at weight 1. |
| Kotaku / Dexerto / TheGamer | Clickbait-heavy, redundant against PC Gamer / RPS / Eurogamer / VGC. |
| The Register | Works (200, 50) but general tech with no gaming/AI focus; Engadget + Tom's Hardware + Wccftech cover the hardware lane. |

Politics-dominant outlets were excluded by design (spec section 3: "Explicitly EXCLUDE
politics-dominant outlets"). No general politics desk, no opinion columns, no aggregators are configured.

## Score mapping

`weight` goes straight into `candidates.json` `score_hint` for news items (CONTRACTS.md: news -> float(weight)).
Weight 3 = flagship gaming press. Weight 2 = major gaming/tech/AI/business. Weight 1 = the single
awareness feed (Kyiv Independent), so it can never outrank gaming or AI on volume.
