# u2 - config seed

Delivered: `config/settings.json`, `config/channels.json`, `config/feeds.json`, `docs/FEEDS-CHECK.md`, `docs/_parts/u2-decisions.md`.

## settings.json

Exact spec section 3 object: 13 keys, original order, 2-space indent, UTF-8 no BOM, 364 bytes, parses clean.

## channels.json - 77 channels (t1 25 / t2 28 / t3 24)

Source of truth: `channel_portfolio.json` (152 elements) read with `json.load`, matched on `title`. Every `id` is a 24-char `UC...` copied verbatim; none invented, none derived from a customUrl. Element shape = the six spec keys only.

Required list: **42 of 42 present.** Portfolio-resolved (41): Asmongold TV/Clips/Shorts/Gaming, penguinz0, MoistCr1TiKaL Gaming, AngryJoeShow, videogamedunkey, MeatCanyon, Papa Meat, Viva La Dirt League, Flashgitz, Fern (`fern`), Visual Venture, POI (`poi`), Ahoy, Internet Historian, NakeyJakey, Drew Gooden, Super Eyepatch Wolf, h3h3Productions, Gigguk, Dr Insanity, Naked Criminal, Vsauce, ANATOLY, MrBeast, JT Music, Teminite, skeler., AI Explained, Matt Wolfe, AI Search, Two Minute Papers, bycloud, Dr. Plants, Odd Animal Specimens, Scary Interesting, blameitonjorge, Nexpo, Curious Archive, Real Science.

Web-resolved (1): **Cryton** is absent from the portfolio. Proven live headless: `GET https://www.youtube.com/@Cryton` -> 200, `"externalId":"UCb9gttCzPcabOnq1nFYPwsw"`; cross-check `GET https://www.youtube.com/feeds/videos.xml?channel_id=UCb9gttCzPcabOnq1nFYPwsw` -> 200, 15 entries, title `Cryton`. Shipped tier 1.

Dropped: none. `TEMINATION` (LonTA) and `Teminite` (c_bv_) are separate entries, both shipped. 32 extra portfolio channels added with inferred tiers.

35 entries carry `"note":"tier guessed - confirm"` - every inferred tier plus every tier-3 memes/shorts/podcast channel. `""` only where the spec states the tier. Tags restricted to the 15 allowed (1-3 each).

## feeds.json - 21 feeds, all live

| # | feed | http | entries | newest | w |
|---|---|---|---|---|---|
| 1 | PC Gamer | 200 | 50 | 2026-10-28T02:00 | 3 |
| 2 | Rock Paper Shotgun | 200 | 100 | 2026-10-28T09:30 | 3 |
| 3 | Eurogamer | 200 | 100 | 2026-10-28T09:14 | 3 |
| 4 | GamesIndustry.biz | 200 | 100 | 2026-10-28T09:28 | 2 |
| 5 | VGC | 200 | 10 | 2026-10-27T18:07 | 2 |
| 6 | GameSpot | 200 | 15 | 2026-10-27T22:07 | 2 |
| 7 | IGN Games | 200 | 20 | 2026-10-28T03:39 | 2 |
| 8 | Digital Foundry | 200 | 15 | 2026-10-26T16:00 | 2 |
| 9 | Tom's Hardware | 200 | 50 | 2026-10-27T20:09 | 2 |
| 10 | The Verge AI | 200 | 10 | 2026-10-27T20:48 | 2 |
| 11 | Ars Technica | 200 | 20 | 2026-10-27T20:25 | 2 |
| 12 | TechCrunch AI | 200 | 20 | 2026-10-28T01:15 | 2 |
| 13 | MIT Technology Review | 200 | 10 | 2026-10-27T12:10 | 2 |
| 14 | Game Developer | 200 | 50 | 2026-10-27T19:34 | 2 |
| 15 | Kyiv Independent | 200 | 100 | 2026-10-28T09:05 | 1 |
| 16 | PCGamesN | 200 | 75 | 2026-10-27T16:48 | 2 |
| 17 | GamesRadar | 200 | 50 | 2026-10-28T03:00 | 2 |
| 18 | Nintendo Life | 200 | 25 | 2026-10-28T07:00 | 2 |
| 19 | Wccftech | 200 | 20 | 2026-10-28T09:30 | 2 |
| 20 | Engadget | 200 | 20 | 2026-10-28T08:40 | 2 |
| 21 | Ars Technica Gaming | 200 | 20 | 2026-10-23T16:35 | 2 |

- All 21 shipped feeds: HTTP 200 **and** more than 0 parsed entries. Nothing dead shipped.
- **Dropped:** VentureBeat AI - all 3 URL variants returned HTTP 429 on 3 attempts over ~5 min.
- **URL fixed:** GamesIndustry.biz `/feed/rss` 404 -> `/feed` 200; Digital Foundry eurogamer paths 404 -> `feeds.feedburner.com/digitalfoundry` 200; Kyiv Independent `/feed/` 404 -> `/feed/rss/` 200; Game Developer `/rss/` 0 entries -> `/rss.xml` 200.
- **Added in-category (6)** to hold 21: PCGamesN, GamesRadar, Ars Technica Gaming, Nintendo Life, Wccftech, Engadget. No politics outlet.
- Weights: 3 = PC Gamer, Eurogamer, RPS; 2 = all other gaming/tech/AI/business; 1 = **Kyiv Independent only**, the unique lowest.

## Verification commands

```powershell
python C:\Users\MarciNaro\AppData\Local\Temp\opencode\u2\final_feeds.py  # fetch+parse all feeds -> feeds_final.json
python C:\Users\MarciNaro\AppData\Local\Temp\opencode\u2\build_config.py  # settings.json + feeds.json
python C:\Users\MarciNaro\AppData\Local\Temp\opencode\u2\build_channels.py # portfolio -> channels.json
python C:\Users\MarciNaro\AppData\Local\Temp\opencode\u2\mk_check.py     # docs/FEEDS-CHECK.md
python C:\Users\MarciNaro\AppData\Local\Temp\opencode\u2\audit.py        # name/tier/tag/id audit
```

Fetch: `requests.get(url, headers={browser UA}, timeout=20, allow_redirects=True)` then `feedparser.parse(response.content)`.

## CONFLICT - parent must read

A parallel unit wrote the same paths with a different shape during 10:44-10:48:

- `config/channels.json` was rewritten 4x; `docs/_parts/u2a-channels.md` documents a 78-entry variant using tags outside the allowed vocabulary (`essay`, `horror`, `movies`, `podcast`, `art`, `reaction`, `gaming-news`).
- `config/feeds.json` was rewritten at 10:47:19 with 37 feeds (`Dexerto`, `Kotaku`, `Variety Gaming`, `80.lv`, `Anime News Network`, `Godot Blog`, `Hacker News`, `Hugging Face`, `Indie Games Plus`, `PlayStation Blog`, `Siliconera`, `Ukrinform`, `Unreal Engine`, `Xbox Wire`, `Google AI Blog`, `OpenAI Blog`) - outside the named categories, with 12 feeds tied at weight 1, breaking the Kyiv-lowest rule.
- This unit wrote last (10:48) and re-validated after. If the parent later sees 78 channels or 37 feeds, the other unit won the final write - re-run `build_channels.py` + `build_config.py` to restore the spec set.

`config/interests.md` is a 4th section-3 artifact but is **not** in this unit's WHAT list; left untouched.

