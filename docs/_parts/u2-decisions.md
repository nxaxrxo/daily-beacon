# u2 decisions (config seed)

- Tiers not stated by the spec were inferred from the watch-list context and channel format; all such entries carry `"note":"tier guessed - confirm"` (35 of 77).
- Asmongold family: `Asmongold TV` tier 1; `Asmongold Clips` / `Asmongold Shorts` / `Asmongold Gaming` tier 2 per the spec's explicit carve-out.
- `penguinz0` and `MoistCr1TiKaL Gaming` are two portfolio entries; both shipped tier 1 (spec names them as one required item).
- `MeatCanyon` and `Papa Meat` are two portfolio entries; both shipped tier 1.
- `Fern` ships as `Fern` (portfolio title `fern`) and `POI` as `POI` (portfolio title `poi`); display names only, ids verbatim.
- `h3h3` resolves to portfolio title `h3h3Productions`; shipped under the portfolio title.
- `TEMINATION` (UCLonTAxE8cjkGUTnDLShaPw) and `Teminite` (UCc_bv_5nmxy2xnPNg9kP3Rg) are two entries; `Teminite` is required tier 2, `TEMINATION` is tier 3.
- `Cryton` absent from the 152-element portfolio. Id `UCb9gttCzPcabOnq1nFYPwsw` resolved live from https://www.youtube.com/@Cryton (200, externalId) and cross-checked via https://www.youtube.com/feeds/videos.xml?channel_id=UCb9gttCzPcabOnq1nFYPwsw (200, 15 entries). Shipped tier 1, note `tier guessed - confirm`.
- 77 channels shipped (t1 25 / t2 28 / t3 24): 42 required + 35 extra portfolio channels with inferred tiers. Portfolio entries with no obvious signal were skipped (e.g. `Gen Nova` at 18 subs, `TIRELESS ... - Topic` auto-channel).
- `anime` is not in the allowed tag vocabulary, so Gigguk / Super Eyepatch Wolf / Darkk Mane / Daddyphatsnaps use `film` / `comedy` / `memes` instead.
- `GamesIndustry.biz`: spec candidate `https://www.gamesindustry.biz/feed/rss` returned 404; shipped `https://www.gamesindustry.biz/feed` (200, 100 entries).
- `Digital Foundry`: `eurogamer.net/tech/feed` and `eurogamer.net/digitalfoundry/feed` both 404; shipped `https://feeds.feedburner.com/digitalfoundry` (200, 15 entries).
- `Kyiv Independent`: `https://kyivindependent.com/feed/` 404; shipped `https://kyivindependent.com/feed/rss/` (200, 100 entries).
- `Game Developer`: `https://www.gamedeveloper.com/rss/` redirects to the homepage and parses to 0 entries; shipped `https://www.gamedeveloper.com/rss.xml` (200, 50 entries).
- `VentureBeat AI`: DROPPED. All three URL variants returned HTTP 429 on three attempts over ~5 minutes. Per the brief no dead feed ships; AI coverage carried by The Verge AI, TechCrunch AI, MIT Technology Review, Ars Technica.
- 6 feeds added inside the named categories to reach 21: PCGamesN, GamesRadar, Ars Technica Gaming, Nintendo Life, Wccftech, Engadget. No feed outside gaming / gaming-tech / AI / games-business / the single Ukraine feed.
- Weights: 3 = PC Gamer, Eurogamer, Rock Paper Shotgun; 2 = all other gaming/tech/AI/business; 1 = Kyiv Independent only (unique lowest).
- Another unit concurrently wrote `config/channels.json` and `config/feeds.json` with different shapes (78 channels with out-of-vocabulary tags; 37 feeds with 12 tied at weight 1). This unit's spec-compliant files were written last and re-validated.
