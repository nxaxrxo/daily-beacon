# DECISIONS — where the spec was silent

One line each. Newest decisions at the bottom of their section.

## Site / presentation (U6)

- Wrote `docs/SITE-CONTRACT.md` as the binding HTML/CSS/JS interface, because `build_edition.py`,
  `style.css` and `app.js` are written in parallel and the spec fixes only the output, not the markup.
- Accent palette is 8 named keys (`amber ember rust olive teal steel rose brass`), not 8 raw hexes:
  the builder emits `data-accent="<key>"` so the CSS owns the actual value and cannot drift.
- All accents pre-verified >= 4.5:1 against both `#0b0b0d` and `#111114`; accents never used for body prose.
- `--open` exists for CLI compatibility but prints `open: skipped (headless-only policy)` — the owner may
  be at the PC and a stolen window ruins a game.
- `--fixture` generates its own dark abstract images with Pillow under `state/workpack/_fixture/img/`, so
  the design can be verified with zero network.
- Archived editions are `site/archive/YYYY-MM-DD.html` (spec §7 asks for `editions/<date>.html` in one
  breath and `site/archive/<date>.html` in the next; the `site/` location wins because it must be inside
  the Pages artifact).
- Fonts: system-stack serif display + Georgia body serif + system sans for labels + mono for numerals.
  No webfont at all, not even with a Google-Fonts link — a runtime CDN dependency is a failure mode at 03:00.
- Print stylesheet prints the URL only after `.byline__link` (source links), never after every anchor.
- Density toggle persists in `localStorage["beacon.density"]` under `data-density="dense"`; default is comfy.
- Section anchor ids are the edition `id` verbatim; the validator enforces `[a-z0-9-]+` so anchors are stable
  across rebuilds and citable in the archive.
- Reading progress, masthead compaction, image fallback and density are the only JS. No analytics, no fetch.

## Publishing (U7)

- Repo `nxaxrxo/daily-beacon`, public, default branch `main`.
- Pages source = GitHub Actions (`build_type=workflow`), artifact path `site`, because Jekyll would mangle
  `site/assets/` filenames and `.nojekyll` alone still runs the default build step.
- `publish.py` refuses to commit anything matching a secret pattern and unstages it; the gh token is never
  written to disk.
- `site_base_url` is only written by an explicit `--set-url`, never guessed from a poll that has not seen 200.

## Editorial (U8)

- `interests.md` is distilled from real memory search output with cited `memory.md` line ranges; no invented
  tastes, no flattery.
- `AGENTS.md` is written for a fresh agent with zero session context and no ability to ask questions.

## Runs (U9)

- (recorded when the first real edition is built)