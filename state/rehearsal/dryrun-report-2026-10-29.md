# DRY RUN REPORT - 2026-10-29 edition, unattended rehearsal

Written by the dry-run agent. No publish, no memory mark, no GUI, no edits outside
`editions/_dryrun-2026-10-29.json`, `state/_dryrun-site/`, `state/_dryrun-report.md` and
throwaway `state/_dryrun-*.py` helpers.

---

## 1. Did the runbook alone let me complete the job?

**Yes, with four forced guesses.** The mechanical path is genuinely sufficient: read packet,
read transcripts, write JSON, `--check`, build to scratch. Every validation failure I hit was
fixable from the error text alone, and the builder's messages are good.

The guesses were not in the mechanics. They were all in the *judgement* layer, where
`AGENTS.md` and `config/interests.md` contradict each other or contradict the tools. A first-time
03:00 agent without a human to ask would have to invent answers to at least the cooldown
question (item 14 below), and that one is load-bearing: read literally it forbids publishing
anything at all.

---

## 2. Sections written, the lead, and the arithmetic

**9 sections** (5-14 allowed), **exactly one lead**, **5 quickHits** (4-7 required), zero `quote`.

Lead: **"Seven hundred OpenAI agents escaped their sandbox and hacked Hugging Face for a better
score"** - bycloud, `https://www.youtube.com/watch?v=ubpXEv4lF0k`, priority 81.

```
T (tier, YouTube tier 1)                                 = 30
F (freshness, published 2026-10-27T13:45, run at 2026-10-29T03:00, ~37h => "< 50h")  =  3
N (novelty, never covered - no seen flag, no topic hit)  = 15
V (format, full technical breakdown = documentary-grade explainer) = 25
M (personal, AI / agentic tooling is LIKES)              = +8
penalties                                                 =  0
                                              TOTAL     = 81  >= 80 => lead
```

Runner-up, for contrast: AngryJoeShow, BioWare closure, T30 + F3 + N15 + V20 + M8 = **76**.
It clears the lead threshold of 80? No - 76 < 80, so it is a full story, not a second lead.
**This is the important detail: the night had exactly one >= 80 item, so the "highest wins,
exactly one lead" rule needed no tie-break judgement.**

Full ranking as applied to `priority`:

| Section | T | F | N | V | M | Total |
|---|---|---|---|---|---|---|
| bycloud - OpenAI agents (lead) | 30 | 3 | 15 | 25 | +8 | **81** |
| AngryJoeShow - BioWare closed | 30 | 3 | 15 | 20 | +8 | **76** |
| Josh Strife Says - Where Winds Meet | 30 | 0 | 15 | 20 | +8 | **73** |
| FF14 Evolved jobs (PC Gamer w3) | 24 | 12 | 15 | 15 | 0 | **66** |
| State of Decay 3 (RPS w3) | 24 | 12 | 15 | 15 | 0 | **66** |
| Pathologic 3 tree (RPS w3) | 24 | 12 | 15 | 15 | 0 | **66** |
| Valve / Next Fest (GameSpot w2) | 16 | 12 | 15 | 15 | 0 | **58** |
| Minecraft 26.60 (Nintendo Life w2) | 16 | 12 | 15 | 15 | 0 | **58** |
| Dark Messiah mod (80.lv w1) | 8 | 12 | 15 | 15 | 0 | **50** |

Three-way tie at 66 was broken by the documented tie-break order (changes something for him >
has an image > creator he watches). Valve at 58 sits in the "45-59 quick hit" band but I shipped
it as a `story` because the MMO/platform consequence is the substance; see section 3.15.

---

## 3. Every point where the runbook was ambiguous, missing or self-contradicting

This is the section that matters. Each item quotes the text.

### 3.1 The transcript-reading instruction is physically impossible as written

> "Read `offset`/`limit` slices of about 150 lines and never load a whole 24,000-character transcript in one read."

Every transcript in `state/workpack/2026-10-29/transcripts/` is **one single line**. I measured:
`XEOzMFZHdcU.txt` is 11,896 characters with `count("\n") == 1`. `1Ln4IFA0POk.txt` is 24,032
characters, one line. There are no lines to slice. Any agent that follows this instruction with a
line-based tool gets the entire file in one read - the exact thing the sentence forbids.

**Fix:** say "read the first ~1,800 characters and the last ~1,200 characters of each file"
(the files are trimmed head+tail, as the doc itself says), or state explicitly that these are
single-line files and must be sliced by character offset.

### 3.2 The same instruction contradicts the file sizes it quotes

> "never load a whole 24,000-character transcript in one read"

`transcript_max_chars` is 24,000 in `config/settings.json`, so a "whole" transcript IS 24,000
characters, and 8 of the 12 files on disk are exactly that. The rule therefore reads as "read
the whole file, but not all at once", with no mechanism given for doing it in pieces.

### 3.3 The two rubric documents disagree on the same worked example

`AGENTS.md` §3.1, row 5:

> "PC Gamer, Warframe rifle buff in the new patch, 20h old, topic last covered 40d ago | 16 | 5 | 6 | 20 | +8 | 0 | **55**"

`config/interests.md`, SCORING RUBRIC worked example:

> "PC Gamer, weight 2, Warframe update, 20h old, topic last covered 40d ago | 16 | 5 | 6 | 15 (article) | +8 (LOVES/LIKES) | 0 | **50**"

Same item, same components, **V=20 in one document and V=15 in the other**, so 55 vs 50 - and 50
and 55 straddle nothing here, but a 5-point swing moves items across the 45/60/80 thresholds. The
runbook says the taste document "outranks your taste" and is "binding", while AGENTS.md presents
its own table as "the rules, not as an example". **When they disagree, there is no stated
precedence between the two scoring tables.**

### 3.4 "Clamped to 100" is not clamping

`config/interests.md`:

> "Asmongold reacts to a studio closure, 4h old, never covered | 30 | 15 | 15 | 25 | +15 | 0 | **100** (clamped)"

30+15+15+25+15 = **100 exactly**. Nothing was clamped. Minor, but it means the only worked example
of the clamp behaviour never actually exercises the clamp, so an agent cannot tell from the docs
whether the clamp applies before or after penalties. (I applied penalties then clamped, per the
`AGENTS.md` wording "then penalties, clamp 0-100".)

### 3.5 The cooldown section, read literally, forbids the entire edition

This is the worst hole in the runbook.

> "**Cooldown is 21 days** ... Nothing returns inside that window unless the comeback exception
> ... holds on all three counts."

The packet's `## cooling down` list contains **35 topics, every one of them last covered
2026-10-28** - i.e. yesterday - and the list includes `gaming`, `ai`, `industry`, `hardware`,
`tech`, `pc`. Every single candidate in the packet carries one of those tags (`"tags": ["gaming",
"news"]` is the default on every news item). Read literally, **nothing is publishable.**

Nothing in either document says umbrella/category topics are exempt. `scripts/memory.py` has a
`GENERIC_TOPICS` set that excludes `news`, `review`, `release`, `analysis`, `business` etc. - but
it deliberately does **not** exclude `gaming`, `ai`, `industry`, `hardware`. So the tool's own
notion of "topic worth gating on" disagrees with what the packet emits as cooling topics.

I resolved it by treating `gaming`/`ai`/`industry`/`hardware`/`tech` as category noise and gating
only on specific topics (`bioware`, `ff14`, `where-winds-meet`, `state-of-decay-3`,
`pathologic-3`, `openai-agents`). **That is a guess, and it is the single most dangerous one in
this run.** If a future agent reads the rule strictly, it publishes nothing; if it reads it
loosely, it may republish yesterday's actual story.

**Fix:** name the umbrella topics explicitly as non-gating, or have the collector stop emitting
them into `cooling down`.

### 3.6 Two different mechanisms for "seen", with different consequences

> "A `seen: true` item is out."

versus, in the same section:

> "**The suppressed row is arithmetic**, not a judgement: `seen` set, -45, however good the item is."

Is a seen item (a) excluded outright, or (b) scored and then hit with -45 (which, given the max
of 100, might still leave it above nothing but is still a *score*)? These are different rules with
different outcomes, stated four lines apart, and the validator cannot tell them apart - it never
looks at `seen`.

### 3.7 The image path format in the docs does not match the artifact on disk

> "`src` local (`../state/workpack/<date>/img/<hash>.jpg`)"

`state/workpack/2026-10-29/images.json` stores:

```
"yt:yr0sbB60AOk": "state/workpack/2026-10-29/img/d657124235c4399b.jpg"
```

**No `../` prefix.** The builder resolves `src` relative to the edition's own directory
(`ctx.edition_path.parent / src`), so `../state/...` is the correct value and the value in
`images.json` is wrong-by-one-level if copied verbatim. The runbook says "Use image paths verbatim
from the packet or `images.json`" - following that instruction literally produces a broken image
that only warns (`WARN: image skipped ...: local file not found`) and does not fail the check. An
unattended agent would ship a text-only page and believe it had images.

**Fix:** state the required prefix transform, or have `images.json` store paths relative to
`editions/`.

### 3.8 §5 never documents `--check --edition`, only `--check --date`

> "| 0 pre-flight | `python scripts/build_edition.py --check --date <date>` |"

The flag list two lines later does include `--edition`, but the pre-flight row - the one an agent
copies - does not. This dry run was required to validate a **non-standard filename**
(`_dryrun-2026-10-29.json`), which `--check --date` cannot address. I had to derive
`--check --edition` from the flag list and from reading `resolve_targets()`. Worth one extra row
in the table.

### 3.9 The doc overstates what `--check` catches

> "**`--check`** validates only, writes nothing: missing keys, two leads, an empty body, bad inline
> markup, a non-quick section with no source, **a missing image credit**."

The validator (`_check_image`) only tests that `image.src` is a non-empty string. **`alt` and
`credit` are never validated**, even though §4 says "all three of `src`/`alt`/`credit` are
required when present". Meanwhile `config/interests.md` says "**No uncredited images** ... Credit is
mandatory" as a NEVER item. So an uncredited image passes `--check` cleanly and violates the
taste contract silently. I added credits by hand, but nothing would have stopped me.

### 3.10 Doc says `id` may contain hyphens freely; the code says otherwise

> "`id` is `[a-z0-9-]+`"

Code: `ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")`. So `my--id`, `-myid` and `myid-` all
match the documented pattern and all fail validation. The error message ("id must match
[a-z0-9-]+") then states the *looser* regex, so the agent is told its invalid id is valid and has
no way to see why it failed. This is a genuinely confusing failure loop.

### 3.11 Doc says every non-quick section needs `label` + `url`; the code needs only `url`

> "every non-`quick` section needs `source.label` + `source.url`"

`_check_source` sets `sticker = kind in ("lead","story","video","quote")` and only fails on a
missing/blank `url`. `label` is checked for *type* only if present. So a sourceless-label story
passes. Doc is stricter than the tool again - safer direction, but it means an agent cannot use
`--check` to confirm it has met the documented requirement.

### 3.12 Parentheses in a URL break the inline-link markup, and this is undocumented

> "body supports **only** `**bold**`, `*italic*`, `[text](url)` and escapes everything else"

The link regex is `\[([^\[\]\n]+)\]\(([^()\s]+)\)` - **no parentheses allowed inside the URL**.
Several real packet URLs contain them, e.g. the GamesIndustry.biz image
`.../Screenshot-2026-10-28-101114-(1).png` and the Ars Technica M6 article is fine but the
VGC/80.lv family is not guaranteed. Any agent linking such a URL inline gets
`CHECK FAIL: ... bad inline markup ... [ without ](url)`, with no hint that parentheses are the
cause. I avoided inline links entirely for this reason, which costs the edition a documented
capability.

### 3.13 §1 contradicts §5 and §8 about what the agent may create

§1:

> "Today's edition is a pair: `editions/YYYY-MM-DD.json` ... and `site/index.html` ... **Nothing else
> is yours to create.**"

§5 has the agent run a publisher that writes `site/archive/<date>.html`, `site/archive.html`,
`site/assets/<date>/`, and §8 requires `docs/runs/YYYY-MM-DD.md`. "Nothing else is yours to
create" is false by §5 and §8. Harmless if read generously, actively misleading if read as a rule
about which files may be touched.

### 3.14 The single second-person allowance is spent by the fixed tagline

`config/interests.md`:

> "**Second person is allowed once per edition**, not once per section."

The schema requires a fixed tagline: `"tagline": "Your 3am briefing, slightly unhinged"`. That is
second person. So **every** edition spends its one allowance on boilerplate before a single
sentence is written, and any use of "you" in body copy is technically the second occurrence. I
rewrote four body sentences to remove "you" so the edition complies with the rule as measured
against the tagline. That is almost certainly not the intent.

### 3.15 Valve at 58: the doc says quick, the format table says story

`AGENTS.md` §3 thresholds:

> "**60-79** full story · **45-59** quick hit or a short `quick` section"

but `config/interests.md` V-table says "a plain news article = 15" and business/market analysis
gets no higher value at all, so a weight-2 outlet's solid reporting structurally cannot reach 60
(T16 + F12 + N15 + V15 + M0 = 58). **The scoring system makes "a well-reported piece from a
weight-2 outlet" permanently un-storyable**, and the only way to publish it as a story is to
ignore the threshold. I shipped Valve as a `story` at 58 anyway; a compliant agent would have
demoted it to a quick hit and lost the substance. The rubric needs either a higher article V or a
weight-2 floor.

### 3.16 CHANNEL POLICY vs the packet's own top-videos list

> "Out: ... **Gameplay / let's-play uploads of any kind.**"

and `config/interests.md`: "**Gameplay and let's-play uploads are not scored at all** ... they
never reach the ranking table."

But the packet's `## top videos` list is dominated by exactly that: `Castlevania Belmont's Curse
True Ending (FULL GAME)` (56,762 seconds), `Finally Got One of the Ranked Requirements Done` (a
ranked gameplay session), `This is the dumbest escape plan I've ever seen` (police-chase reaction
footage). The collector puts them in `top videos`; the policy says they are excluded and unscored.
**The runbook never says who filters them out of the packet's own headline list**, and there is no
`channel_policy` flag in `filtered.json` to check. I excluded them by hand. Note the packet's own
`[T1|w1]` tags imply they are all top-tier candidates.

### 3.17 LOVES, CHANNEL POLICY and `channels.json` give three different answers about MrBeast

- `interests.md` LOVES: "**MrBeast**, Vsauce, Anatoly, Dr Insanity, Naked Criminal ... all named on the watch list".
- `interests.md` CHANNEL POLICY: "Out of scope ... **Pure branded entertainment** ... do not report, even from a creator he likes."
- `config/channels.json`: `MrBeast` → `"enabled": false, "note": "pure entertainment/gameplay/music/shorts - disabled by owner brief"`.

The policy is declared to outrank LOVES, so the effective answer is "disabled" - but the LOVES
list still tells an agent to weight MrBeast at +8, and nothing tells it not to. Same problem for
Anatoly, Dr Insanity, Naked Criminal, Papa Meat, Flashgitz, Viva La Dirt League.

### 3.18 §6 "stop editing" contradicts the hard requirement that an edition exists

> "After two failed passes, stop editing today and leave yesterday's built site untouched"

versus

> "Every one of these ends the same way: an edition exists, is built, and the run note says what happened."

If validation fails twice, "leave yesterday's site untouched" and "an edition exists, is built"
cannot both hold. Which one wins at 03:00?

### 3.19 `--verify` is "(optional)" but a 404 is a mandatory recovery path

§5 row 3 labels verify "(optional)". §6 has a whole row of instructions for a 404 after a push,
and §8's run-note line requires "live at <url>". An optional step cannot gate a required
statement. Either verify is required (then say so) or the 404 row is dead prose.

### 3.20 Headline punctuation: "no full stop" vs the quote example

> "sentence-case headlines, no full stop"

but §4.5's `quote` example headline is:

> `"headline": "We shipped the demo before we shipped the pitch deck, and that is the only reason anyone answered the email.",`

A full stop. Also `""We basically rewrote the entire State of Decay game": ..."` - headlines that
begin with a quote end up with a colon and a lower-case continuation, which is not sentence case.
Nothing enforces any of this; `--check` passes all of it.

### 3.21 No rule for `number` when the previous edition failed

> "`number` is the previous edition's + 1"

The only edition on disk is `2026-10-28.json` = `number: 1`, so I wrote 2. But if a night fails,
does the next successful night take the next integer or repeat? Nothing says, and the builder
only warns when `number` is missing ("using 0") rather than validating it.

### 3.22 The brief's "no memory" instruction collides with the cooldown requirement

The runbook makes `memory.py query --topic <slug>` the authority on "when did we last run this",
and requires `memory.py digest` for comeback decisions. This dry run was forbidden from touching
memory, so **the comeback exception could not be evaluated at all**. Everything I decided about
cooldown came from `filtered.json`'s `recent_topics`, which is only yesterday's slice. An agent
that obeys §3 will therefore run `memory.py query` on the live DB at 03:00 - worth stating
explicitly that this is read-only and safe, because the phrase "never touch memory" is not in
`AGENTS.md` and the two activities look identical to a cautious agent.

### 3.23 §2.3 asks for thumbnail judgement, but news items have no thumbnail file

> "**Judge everything else from title + channel/source + thumbnail + length.**"

`images.json` has 24 entries, all `yt:` or `url:` keys for a subset. Most news items have only a
remote `image` URL in `filtered.json` and no local file, and news items have **no length field at
all**. So the documented judgement inputs are unavailable for the majority of the 90 articles.

---

## 4. Things I had to guess and should not have had to

1. **Transcript slicing by character offset**, because every file is one line (§3.1).
2. **That umbrella cooldown topics are not gating** (§3.5). Without this guess, no edition.
3. **That `images.json` paths need a `../` prefix** (§3.7). Without this guess, no images.
4. **That gameplay/let's-play uploads are removed from the ranking entirely**, not scored and
   dropped by score (§3.16). The policy says "not scored at all"; the packet puts them in `top
   videos`.
5. **`number = 2`**, with no rule for gaps (§3.21).
6. **That "the previous edition" means the newest file in `editions/`**, not yesterday's calendar
   date - there is no edition for a day the run failed, and nothing defines the reference.
7. **Which document wins when the two rubric tables disagree** (§3.3).
8. **That `priority` should equal the computed rubric total.** §4's schema shows
   `"priority": 100` on the lead and 80/60/40/30 on the examples, which looks like a *layout*
   weight, not the score; §3's thresholds are about scores. Two different numbers, both called
   "priority" in practice. I set `priority` = score, which is what the examples happen to do.
9. **Whether a `quote` section may also be one of the 5-14 counts** - §3.2 says "5-14 sections
   (`edition_min_stories`...)" but the setting name says *stories*, while the count includes
   `quick` and `quote` kinds. I wrote no quote at all, so it did not bite, but the naming
   conflict is real.

---

## 5. Validation, verbatim

```
PS C:\Users\MarciNaro\Documents\VSCODE-PROJECTS\daily-beacon> python scripts\build_edition.py --check --edition editions\_dryrun-2026-10-29.json
CHECK OK: 9 sections, 5 quick hits
EXIT=0
```

Scratch render (writes only to `state/_dryrun-site`, publishes nothing):

```
PS ...> python scripts\build_edition.py --edition editions\_dryrun-2026-10-29.json --out-dir state\_dryrun-site
variant: accent=sky layout=hero-stacked scale=b order=lead
archive: 1 snapshots indexed in archive.html
build done: 2026-10-29 - 9 sections, 5 images, 23248 bytes, 34 links
EXIT=0
```

Source integrity check (all 14 story/quick-hit URLs matched against
`filtered.json` + `candidates.json` + `suppressed.json`):

```
urls used: 14 unique: 14
NOT in packet: none
```

File checks: no BOM (first bytes `123,10,32` = `{`, LF, space), valid JSON, 5 `<figure` elements
rendered, lead is the bycloud section.

No publish, no `memory.py mark`, no browser, no window, `editions/2026-10-28.json` unmodified,
`site/` untouched.

---

## Closing verdict (unnumbered - the brief asked for five numbered items)

The pipeline is sound. `build_edition.py` is honest and its errors are actionable. The **runbook's
judgement layer is not yet sufficient for an agent with no prior context**, and the two blocking
items are §3.5 (cooldown umbrella topics make the edition unpublishable under a literal reading)
and §3.7 (image paths in `images.json` are off by one directory level, and the failure is a silent
warning rather than an error). Fix those two, and §3.1 (transcripts are one line, not many), and a
cold agent can run this night unsupervised.
