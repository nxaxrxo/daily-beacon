# u2a - config/channels.json (watched YouTube creators)

Output: `config/channels.json` - 78 channels (t1=27, t2=37, t3=14). Every `id` copied verbatim from
`~\.config\opencode\home\youtube-manager\channel_portfolio.json` `channelId` (152 subscriptions).
No id invented, none derived from a customUrl. Element shape is exactly the six spec keys; UTF-8,
2-space indent, no extra fields.

## Coverage of the SPEC section 3 list (programmatic, case-insensitive title match)

REQUIRED | RESULT | id
--- | --- | ---
Asmongold + variants | FOUND x4 | TV `UCQeRaTukNYft1_6AZPACnog` / Gaming `UCsxS7yzZC9gKYcgL4pvN3rA` / Shorts `UCkQ774ot9mhH3wWMsjzGq2g` / Clips `UCMwJJL5FJFuTRT55ksbQ4GQ`
penguinz0 / MoistCr1TiKaL | FOUND x2 | `UCq6VFHwMzcMXbuKyG7SQYIg` + `UCxfr3b8IuHSzu22UHnAvHWg`
AngryJoeShow, videogamedunkey | FOUND | `UCsgv2QHkT2ljEixyulzOnUQ`, `UCsvn_Po0SmunchJYOWpOxMg`
MeatCanyon / Papa Meat | FOUND x2 | `UC91V6D3nkhP89wUb9f_h17g` / `UCYF1kiTFCcYPqGTqXKt3JJg`
Viva La Dirt League, Flashgitz | FOUND | `UCchBatdUMZoMfJ3rIzgV84g`, `UCNnKprAG-MWLsk-GsbsC2BA`
Fern, POI | FOUND | `UCODHrzPMGbNv67e84WDZhQQ`, `UCRVXfhLRsLWi3_IKnMDiI1Q` (portfolio titles lowercase)
Visual Venture, Ahoy | FOUND | `UCt3JiNkefsfbA2N4SgEkoiQ`, `UCE1jXbVAGJQEORz9nZqb5bQ`
Cryton | MISSING | omitted - see Gaps
Internet Historian, NakeyJakey | FOUND | `UCR1D15p_vdP3HkrH8wgjQRw`, `UCSdma21fnJzgmPodhC9SJ3g`
Drew Gooden, Super Eyepatch Wolf | FOUND | `UCTSRIY3GLFYIpkR2QwyeklA`, `UCtGoikgbxP4F3rgI9PldI9g`
h3h3, Gigguk | FOUND | `UCDWIvJwLJsE4LG1Atne2blQ`, `UC7dF9qfBMXrSlaaFFDvV_Yg`
Dr Insanity, Naked Criminal | FOUND | `UCjnYCUIym8wNRjLtZCc6gNg`, `UCfUzdRue-huCAV9FOn9a0pw`
Vsauce, ANATOLY, MrBeast | FOUND | `UC6nSFpj9HTCZ5t-N3Rm3-HA`, `UCwYQXYfPHTZKANHzBHdYo2w`, `UCX6OQ3DkcsbYNE6H8uQQuVA`
JT Music, Teminite, skeler. | FOUND | `UCzTdZz7z2sPRGCImodwOw0g`, `UCc_bv_5nmxy2xnPNg9kP3Rg`, `UCpoKdKVhH-jcr3Pu0auKjmw`
AI Explained, Matt Wolfe, AI Search | FOUND | `UCNJ1Ymd5yFuUPtn21xtRbbw`, `UChpleBmo18P08aKCIgti38g`, `UCIgnGlGkVRhd4qNFcEwLL4A`
Two Minute Papers, bycloud | FOUND | `UCbfYPyITQ-7l4upoX8nvctg`, `UCgfe2ooZD3VJPB6aJAnuQng`
Dr. Plants, Odd Animal Specimens | FOUND | `UCYmna5rFHIesFteksAvFOfg`, `UCSz8X-JAmenxLH-uXlgVaCg`
Scary Interesting, blameitonjorge | FOUND | `UCNXvmGafmrtJ7VPSqjRRbwg`, `UCU3oAyhHDXjgbxazqOEG2UA`
Nexpo, Curious Archive, Real Science | FOUND | `UCpFFItkfZz1qz5PpHpqzYBw`, `UCweDKPSF65wRw5VHFUJYiow`, `UC176GAQozKKjhz62H8u9vQQ`

Result: 41 of 42 required entries present. Only Cryton is absent (accepted per brief).

## Gaps / omissions

- **Cryton** - not in the portfolio (no title or customUrl match across all 152). One headless GET of
  `https://www.youtube.com/@Cryton` returned HTTP 200 but no machine-readable channel page (no
  `"channelId":"UC..."` in the HTML), so it did not resolve in the single allowed attempt => OMITTED.
  No invented id substituted. Effect: the collector never sees Cryton; re-add when a real id exists.
- `Holo` (gameplay), `Fillion`, `Joss Drive Hayes`, `Tech Tone` from the memory watch list - not in the
  portfolio and not on the spec list => omitted.
- No live resolution needed for any other name, so zero network calls beyond the Cryton attempt.
- No politics-dominant or news-desk channel exists in the portfolio under a matching title, so nothing
  had to be filtered for that rule; the file holds creators only.
- Excluded from the 152 by design: asmr (Asmr Lucky Girl), dead/placeholder (Invictus 190 subs,
  Gen Nova 18 subs, `??????` 9.6k), Topic/auto-generated music (TIRELESS - Topic), duplicate second
  channels with no original output (Cryy+), regional channels. Kept 78, inside the 55-90 range.

## How tiers were assigned

- **tier 1 (27)** - exactly the names the brief marks must-check daily: Asmongold TV, penguinz0,
  MoistCr1TiKaL Gaming, AngryJoeShow, videogamedunkey, Gigguk, Internet Historian, h3h3Productions,
  Super Eyepatch Wolf, Drew Gooden, NakeyJakey, AI Explained, Matt Wolfe, Two Minute Papers, bycloud,
  AI Search, Curious Archive, Nexpo, blameitonjorge, Real Science, Viva La Dirt League, MeatCanyon,
  fern, Ahoy, Vsauce, MrBeast, JT Music. note = "" (clear rule, not guessed).
- **tier 3 (14)** - the brief's tier-3 rule verbatim: Asmongold Shorts, Asmongold Clips, Papa Meat,
  Visual Venture, Dr Insanity, Naked Criminal, Zack D. Films, UnusualVideos, TEMINATION, skeler.,
  Teminite, Steak and Eggs Podcast, TBH, Scroll Gang - so a tier cap of 2 keeps them out of the run.
- **tier 2 (37)** - everything else worth watching that the rules do not name: Asmongold Gaming,
  Flashgitz, poi, Dr. Plants, Odd Animal Specimens, Scary Interesting, ANATOLY, KiraTV, Corridor Crew,
  Corridor Digital, Nerd City, Pyrocynical, Tectone, Josh Strife Says, Nerdwriter1, Spikima Movies,
  MattVidPro, Aitrepreneur, Daniel Thrasher, Steven He, Daily Dose Of Internet, High Boi, Code Bullet,
  The Paint Explainer, TheOdd1sOut, ExplosmEntertainment, CarbotAnimations, Elvis The Alien,
  Jim Browning, Threat Interactive, Hartnett Media, Marc Brunet, LazarBeam, PewDiePie, I did a thing,
  Daryl Talks Games, The Theorizer.
- **guessed (38)** carry note `"tier guessed - confirm"`: all 37 tier-2 placements plus Scroll Gang,
  whose tier-3 slot was inference not a listed rule. Everything else note "".
- `enabled` true for all 78 by design - the collector filters by tier cap, not by enabled.
- `tags` from the fixed vocabulary only (gaming, gaming-news, ai, tech, music, comedy, animation,
  science, essay, horror, movies, shorts, memes, podcast, art, reaction), 1-3 each. MrBeast is
  `comedy`+`shorts` (vocabulary has no `entertainment`); KiraTV and Threat Interactive get `gaming-news`.
- Portfolio titles kept verbatim (`fern`, `poi`, `skeler.`, `Dr Insanity`, `h3h3Productions`); the
  spec-list match is case-insensitive at read time.

## Validation output

```
channels.json OK: 78 channels (t1=27 t2=37 t3=14)
```

One-liner asserts: loads as a list; every element has exactly {id, name, tier, tags, enabled, note};
every id matches ^UC[A-Za-z0-9_-]{22}$; ids unique; tiers in {1,2,3}; tags lowercase and in the fixed
vocabulary; enabled boolean; note a string. 78 unique ids, 78 unique names.

## Caveats

- A competing channels.json was written to the same path by another worker during this unit (extra
  `subscribers`/`customUrl` keys, 55-79 entries). This file was regenerated last and re-validated
  after that write; if a later wave re-seeds the path, re-run the validation one-liner.
- TEMINATION has 2,650 subs but a real id and is on the required list, so it stays at tier 3.
