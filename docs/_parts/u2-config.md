# u2 - config seed

Delivered: `config/settings.json`, `config/channels.json`, `config/feeds.json`, `docs/FEEDS-CHECK.md`.

## settings.json
The spec section 3 object verbatim: 13 keys, original order, 2-space indent, UTF-8 without BOM.
Verified `list(d) == [timezone_note, lookback_hours, max_videos_per_channel, max_videos_total,
max_news_items, short_max_seconds, transcript_max_chars, edition_max_stories, edition_min_stories,
repeat_topic_cooldown_days, keep_editions, site_base_url, publish]` and every value equals the spec.
`site_base_url` stays `""` until the first deploy fills it.

## channels.json - 79 channels (t1 28 / t2 37 / t3 14)
Source of truth: `~\.config\opencode\home\youtube-manager\channel_portfolio.json` (152 subscriptions).
Every `id` is a 24-char `UC...` copied verbatim from `channelId`; nothing invented, nothing derived from a
customUrl. Element shape is exactly the six spec keys `{id, name, tier, tags, enabled, note}` - the
portfolio's `subscribers`/`customUrl` were dropped because the spec fixed the element shape.

Required coverage: **all 42 required entries present.** 41 came straight from the portfolio (matching
case-insensitively on title, so `fern`->Fern, `poi`->POI, `h3h3Productions`->h3h3, `MoistCr1TiKaL Gaming`
counts for MoistCr1TiKaL, both Asmongold variants families, both MeatCanyon and Papa Meat).
**Cryton** is not in the portfolio and was resolved live: `https://www.youtube.com/@Cryton` exposes
`"externalId":"UCb9gttCzPcabOnq1nFYPwsw"`, and the id was cross-checked twice - the channel RSS returns 200
with 15 entries titled `Cryton`, Invidious returns 200 with author `Cryton`. Shipped tier 1.

Tiers: tier 1 = the spec's must-check-daily names (28 incl. Cryton); tier 3 = the meme/short/clip/podcast
channels (14); tier 2 = the rest of the watch list worth checking (37). Every inferred tier carries
`"note":"tier guessed - confirm"` (38 entries); entries whose tier the spec states carry `""`.

## feeds.json - 24 feeds, every one verified live
HTTP status and item count per feed are recorded in `docs/FEEDS-CHECK.md`. Summary: 24/24 returned HTTP 200
with at least one parsed entry, 0 dead, 0 dropped-for-emptiness.

Mix: 10 gaming news, 4 gaming-tech/hardware (Digital Foundry, Tom's Hardware, Wccftech, Ars Technica Gaming),
1 games-business (GamesIndustry.biz) + Game Developer, 3 AI (The Verge AI, TechCrunch AI, Google AI Blog),
2 general tech/science (Ars Technica, MIT Tech Review), 2 gamedev (Godot, Unreal), 1 AI archive
(Hugging Face), 1 Ukraine/world at weight 1 (Kyiv Independent). No politics-dominant outlet.

Weights: 3 = PC Gamer, RPS, Eurogamer; 1 = Kyiv Independent, MIT Tech Review, Google AI, Hugging Face,
Godot, Unreal; 2 = everything else. `weight` is what becomes `score_hint`, so the awareness feed can never
outrank gaming or AI on volume alone.

## Verification output
```
channels.json OK: 79 channels (t1=28 t2=37 t3=14)
  every element has exactly {enabled, id, name, note, tags, tier}
  every id matches ^UC[A-Za-z0-9_-]{22}$   ids unique (79/79)
  tiers in {1,2,3}   tags lowercase from the fixed vocabulary
feeds.json OK: 24 feeds, unique urls, weights {1,2,3}
24/24 feeds HTTP 200 with entries
```

## Notes
- Two other units wrote these same paths during the session with different shapes (a 78-channel variant and
  a 38-feed variant). The files above are the final, verified ones: 79 channels / 24 feeds, and the shape
  assertions in `docs/_parts/u2a-channels.md` and `docs/FEEDS-CHECK.md` are the ones that must keep passing.
- No channel was invented and no feed is unverified; anything that failed verification is listed with its
  reason in `docs/FEEDS-CHECK.md` rather than quietly removed.
