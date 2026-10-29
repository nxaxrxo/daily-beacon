# SITE-CONTRACT - the binding HTML/CSS/JS interface for the Daily Beacon site

Authored by the orchestrator. `scripts/build_edition.py` MUST emit exactly these elements/classes;
`site/style.css` + `site/app.js` MUST style/behave them. Neither side invents names. If something is
genuinely missing here, add one line to docs/DECISIONS.md and report it - do not silently diverge.

## 1. Files the builder writes

- `site/index.html`                       - today's edition, asset prefix `""`
- `site/archive/YYYY-MM-DD.html`          - byte-identical snapshot except asset prefix `"../"`
- `site/archive.html`                     - index of every snapshot, prefix `""`
- `site/assets/<date>/<slug>-<hash8>.jpg` - optimised images (max width 1400, JPEG q82, RGB)
- static `site/style.css`, `site/app.js`  - written by the CSS worker, referenced as
  `style.css?v=<sha1[:8] of the file>` and `app.js?v=<same>`. Builder never edits their content.

`--out-dir` overrides the site root (default `site`). `--fixture` defaults `--out-dir site/_fixture` and
never reads or writes `editions/` or `state/`.

## 2. Document skeleton (element order is part of the contract)

```
<!DOCTYPE html>
<html lang="en" data-accent="amber" class="layout-hero-left scale-a order-lead">
<head>
  meta charset utf-8 / viewport width=device-width,initial-scale=1 / color-scheme dark light
  <title>{masthead} - {long date}</title>
  <meta name="description" content="{tagline}">
  <link rel="stylesheet" href="style.css?v=XXXXXXXX">
  <meta property="og:title|og:description|og:type=website|og:image(optional)">
</head>
<body id="top">
  <div id="progress" aria-hidden="true"><span id="progress-bar"></span></div>

  <header class="masthead" id="masthead">
    <div class="masthead__rule masthead__rule--thick"></div>
    <div class="masthead__rule"></div>
    <p class="masthead__ear masthead__ear--left">No. {number}</p>
    <p class="masthead__ear masthead__ear--right">{weekday, long date}</p>
    <h1 class="masthead__title">{masthead}</h1>
    <p class="masthead__tagline">{tagline}</p>
    <div class="masthead__rule"></div>
    <div class="masthead__rule masthead__rule--thick"></div>
    <p class="masthead__weather">{weatherStrip}</p>
  </header>

  <nav class="toc" aria-label="In this edition">
    <ul class="toc__list">
      <li><a class="toc__link" href="#{section id}"><span class="toc__kicker">{kicker}</span>
              <span class="toc__label">{headline, <= 42 chars, plain text}</span></a></li>   (one per section)
    </ul>
  </nav>
  <!-- the TOC is a static, single-row, horizontally scrolling jump strip. It must never be
       position:sticky and must never wrap onto a second row: a wrapped sticky strip is what made
       the top of the page eat most of the viewport on a 1440px screen. -->

  <main class="paper" id="paper">

    <!-- LEAD: exactly one. class varies by layout variant -->
    <article class="lead lead--{lead_layout}" id="{id}">
      <p class="kicker">{kicker}</p>
      <h2 class="lead__headline"><a href="{source.url}">{headline}</a></h2>
      <p class="standfirst">{standfirst}</p>
      <figure class="media media--lead">
        <div class="media__box" style="--ar:16/9">
          <img class="media__img" src="{img}" alt="{alt}" loading="lazy" decoding="async" width="1400" height="788">
        </div>
        <figcaption class="media__credit">{credit}</figcaption>
      </figure>
      <div class="lead__body body">
        <p>...</p>  (inline **bold** -> <strong>, *italic* -> <em>, [t](u) -> <a href="u" rel="noopener">)
      </div>
      <p class="whymatters"><span class="whymatters__label">Why it matters</span> {whyItMatters}</p>
      <p class="aside">{aside}</p>
      <p class="source-line"><a class="source" href="{url}" target="_blank" rel="noopener">{label}</a><button type="button" class="share" aria-label="Copy this story as text">Share</button></p>
    </article>

    <!-- everything else, in `order` sequence -->
    <article class="story" id="{id}">            kind=story
      <p class="kicker">, <h2 class="story__headline"> with <a>, <p class="standfirst">,
      <figure class="media"> (optional), <div class="body">, <p class="whymatters">, <p class="aside">,
      <p class="source-line">
    </article>
    <article class="story card card--video" id="{id}">   kind=video (same internals; class added)
    <blockquote class="pullquote" id="{id}">      kind=quote
      <p class="pullquote__text">{headline or first body para}</p>
      <footer class="pullquote__cite">{source.label}</footer>
    </blockquote>
    <article class="story story--brief" id="{id}"> kind=quick (short body)

    <aside class="quick-hits" id="quick-hits" aria-labelledby="quick-hits-title">
      <h2 class="quick-hits__title" id="quick-hits-title">Quick Hits</h2>
      <ul class="quick-hits__list">
        <li><a href="{url}" target="_blank" rel="noopener">{text}</a></li>
      </ul>
    </aside>
  </main>

  <footer class="colophon">
    <div class="colophon__rule"></div>
    <ul class="colophon__meta">
      <li>Edition {number}</li>
      <li>Generated {generatedAt humanised}</li>
      <li>{n} stories, {k} quick hits</li>
      <li>{covered} items tracked, {suppressed} suppressed today</li>
    </ul>
    <p class="colophon__signoff">{signoff}</p>
    <p class="colophon__archive">Previous 30 editions are archived at
      <a href="archive.html">archive.html</a>.</p>
    <p class="colophon__fine">Compiled automatically at 03:00 from public feeds and creators'
      uploads. No story is invented; every item links to its source.</p>
  </footer>

  <a class="to-top" href="#top" aria-label="Back to top">Top</a>
  <script src="app.js?v=XXXXXXXX" defer></script>
</body></html>
```

Archive index page: same head/masthead shape with `masthead__title` = "THE DAILY BEACON",
`masthead__tagline` = "Archive", then `<main class="paper archive"><ul class="archive__list">` with
`<li class="archive__item"><a class="archive__link" href="archive/DATE.html"><span class="archive__date">DATE</span><span class="archive__head">{lead headline}</span></a></li>`,
newest first, then the same colophon (no nav). Body class `page-archive`.

## 3. Variant classes (date-seeded, set on <html>)

- `data-accent` one of: amber, coral, rose, sage, teal, sky, gold, clay
- `class` includes exactly one of: `layout-hero-left` | `layout-hero-centre` | `layout-hero-stacked`
- exactly one of: `scale-a` | `scale-b`
- exactly one of: `order-lead` | `order-rail`

Seed rule (builder): `seed = int(date.replace("-", ""))`; `accent = ACCENTS[seed % 8]`;
`layout = ["hero-left","hero-centre","hero-stacked"][(seed // 7) % 3]`;
`scale = "a" if (seed // 11) % 2 == 0 else "b"`; `order = "lead" if (seed // 13) % 2 == 0 else "rail"`.
`order-rail` puts the Quick Hits aside before the first non-lead story in the DOM; `order-lead` puts it
after the last story. CSS must not reorder with flex/grid `order` - the DOM order is the contract.

Accent palette (verified vs #0b0b0d: all >= 6.7:1; dark ink on accent >= 7:1):
amber #e8a33d | coral #ec7a5c | rose #e88fa2 | sage #a6c48a | teal #6fc3ba | sky #82b6e8 |
gold #dcc36e | clay #de9670

## 4. CSS variables the builder may rely on (declared in style.css on :root)

`--accent`, `--accent-ink`, `--paper`, `--paper-2`, `--ink`, `--ink-muted`, `--rule`, `--rule-strong`,
`--measure`, `--serif`, `--sans`, `--mono`. `style.css` maps `[data-accent="x"]` to a concrete
`--accent`. Media boxes read `--ar` from the inline style; CSS supplies a default of `16/9`.

## 5. app.js behaviour (no libraries, defer, <= 160 lines)

1. Reading progress: `#progress-bar` width = scroll ratio (0-100%), hidden when `#progress` absent.
2. Smooth anchor scroll for `a[href^="#"]` honouring `prefers-reduced-motion`.
3. Image fallback: on `error`, replace with `figure.media--failed` (builder also emits
   `onerror`-free markup - JS is the only fallback path) and hide the credit line.
4. `body.is-scrolled` past 80px (a class toggle only; CSS decides what it does - today it reveals the
   back-to-top control). The masthead and TOC are NOT pinned: they scroll away with the page. There is
   deliberately no density/comfy toggle and no localStorage dependency left.
5. Section copy: the `button.share` handler and its composer are emitted **inline** by the builder
   (`SHARE_JS` in `build_edition.py`), not in `app.js`. Reasons: it survives a stale/cached `app.js`,
   it works on archive snapshots for free, and it keeps `app.js` inside its 160-line budget. The
   composer reads the article from the DOM (never a parallel data copy, so the text cannot drift),
   writes to `navigator.clipboard` with a `document.execCommand` fallback, and appends the article's
   canonical URL *without* the fragment for the page line. One click copies headline, standfirst,
   body, why-it-matters, aside, source label + URL: the whole story as plain text.
6. Nothing else. No analytics, no fetches, no external URLs.

## 6. Hard design constraints (both sides)

- Dark paper: `--paper` #0b0b0d, `--paper-2` #111114, `--ink` #ece7dd, `--ink-muted` #a8a29a
  (7.77:1 on paper). Body text never below 4.5:1. No purple hue 240-280 anywhere (no glassmorphism,
  no glow shadows, no gradient text, no animated gradients, no gradient orbs).
- Mobile first: single column below 760px, no horizontal scroll at 320px, tap targets >= 44px,
  fluid type via clamp() only.
- Print: `@media print` -> white paper, black ink, hide `#progress`, `.toc`, `.to-top`, `.share`;
  show link URLs for `.source` in `::after`.