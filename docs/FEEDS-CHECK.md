# FEEDS CHECK

Checked: 2026-10-28T10:42:47+01:00 (local time, machine clock)

User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36`

Method: `python` + `requests.get(url, headers={UA}, timeout=20, allow_redirects=True)` then `feedparser.parse(r.content)`; `entries` = number of parsed entries; `newest` = newest `published`/`updated` across the first 30 entries. A 200 with 0 parsed entries is treated as DEAD.

Command: `python C:\Users\MarciNaro\AppData\Local\Temp\opencode\u2\final_feeds.py`

| feed | url | http | entries | newest | verdict |
|---|---|---|---|---|---|
| PC Gamer | https://www.pcgamer.com/rss/ | 200 | 50 | 2026-10-28T02:00 | OK |
| Rock Paper Shotgun | https://www.rockpapershotgun.com/feed | 200 | 100 | 2026-10-28T09:30 | OK |
| Eurogamer | https://www.eurogamer.net/feed | 200 | 100 | 2026-10-28T09:14 | OK |
| GamesIndustry.biz | https://www.gamesindustry.biz/feed | 200 | 100 | 2026-10-28T09:28 | OK |
| VGC | https://www.videogameschronicle.com/feed/ | 200 | 10 | 2026-10-27T18:07 | OK |
| GameSpot | https://www.gamespot.com/feeds/mashup/ | 200 | 15 | 2026-10-27T22:07 | OK |
| IGN Games | https://feeds.ign.com/ign/games-all | 200 | 20 | 2026-10-28T03:39 | OK |
| Digital Foundry | https://feeds.feedburner.com/digitalfoundry | 200 | 15 | 2026-10-26T16:00 | OK |
| Tom's Hardware | https://www.tomshardware.com/feeds/all | 200 | 50 | 2026-10-27T20:09 | OK |
| The Verge AI | https://www.theverge.com/rss/ai-artificial-intelligence/index.xml | 200 | 10 | 2026-10-27T20:48 | OK |
| Ars Technica | https://feeds.arstechnica.com/arstechnica/technology-lab | 200 | 20 | 2026-10-27T20:25 | OK |
| TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | 200 | 20 | 2026-10-28T01:15 | OK |
| MIT Technology Review | https://www.technologyreview.com/feed/ | 200 | 10 | 2026-10-27T12:10 | OK |
| Game Developer | https://www.gamedeveloper.com/rss.xml | 200 | 50 | 2026-10-27T19:34 | OK |
| Kyiv Independent | https://kyivindependent.com/feed/rss/ | 200 | 100 | 2026-10-28T09:05 | OK |
| PCGamesN | https://www.pcgamesn.com/mainrss.xml | 200 | 75 | 2026-10-27T16:48 | OK |
| GamesRadar | https://www.gamesradar.com/rss/ | 200 | 50 | 2026-10-28T03:00 | OK |
| Nintendo Life | https://www.nintendolife.com/feeds/latest | 200 | 25 | 2026-10-28T07:00 | OK |
| Wccftech | https://wccftech.com/feed/ | 200 | 20 | 2026-10-28T09:30 | OK |
| Engadget | https://www.engadget.com/rss.xml | 200 | 20 | 2026-10-28T08:40 | OK |
| Ars Technica Gaming | https://feeds.arstechnica.com/arstechnica/gaming | 200 | 20 | 2026-10-23T16:35 | OK |

Shipped feeds: 21 - all HTTP 200 with more than 0 parsed entries.

## Notes on fixed and dropped sources

- **Rock Paper Shotgun** - kept - spec candidate https://www.rockpapershotgun.com/feed returned 200.
- **GamesIndustry.biz** - URL fixed - spec candidate https://www.gamesindustry.biz/feed/rss returned 404; https://www.gamesindustry.biz/feed returned 200.
- **IGN Games** - kept - feeds.ign.com/ign/games-all redirects to ign.com/rss/articles/feed?tags=games, 200, 20 entries.
- **Digital Foundry** - URL fixed - eurogamer.net/tech/feed and eurogamer.net/digitalfoundry/feed both 404; https://feeds.feedburner.com/digitalfoundry returned 200.
- **Tom's Hardware** - kept - tomshardware.com/feeds/all redirects to tomshardware.com/feeds.xml, 200, 50 entries.
- **Ars Technica** - kept - technology-lab feed used for AI/tech coverage; the gaming sibling feed is also shipped separately.
- **Game Developer** - URL fixed - https://www.gamedeveloper.com/rss/ redirects to the homepage with 0 entries; https://www.gamedeveloper.com/rss.xml returned 200.
- **Kyiv Independent** - URL fixed - spec candidate https://kyivindependent.com/feed/ returned 404; https://kyivindependent.com/feed/rss/ returned 200.
- **PCGamesN** - added to replace the dropped VentureBeat AI slot (gaming news, same category).
- **GamesRadar** - added as a gaming-news substitute for the dropped VentureBeat AI slot.
- **Nintendo Life** - added - gaming news, low weight.
- **Wccftech** - added - gaming-tech/hardware, low weight.
- **Engadget** - added - consumer tech, low weight.
- **Ars Technica Gaming** - added - same publisher as Ars Technica, gaming section.
- **VentureBeat AI** - dropped, see above. No replacement with a different name was invented; the shipped set stays at 21 feeds inside the named categories.

## Weights

- weight 3 (strongest fit, core gaming news): PC Gamer, Eurogamer, Rock Paper Shotgun
- weight 2: all other gaming news, gaming-tech/hardware, AI, games-industry business
- weight 1: Kyiv Independent only - the unique lowest weight in the file

