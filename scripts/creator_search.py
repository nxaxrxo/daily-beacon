#!/usr/bin/env python3
"""
creator_search.py - "did anyone I follow cover this?"

The owner's ask, in his words: "a tool that would allow you to search a particular term, like
Helldivers 2, and the only videos that pop up are from YouTubers that I follow." That is the whole
purpose: given a story, find the creator take he actually cares about instead of a headlined article.

Two modes, and the difference matters:

  --scope global   One query, then filter to followed channels. Fast, but INVIDIOUS RANKS BY
                   POPULARITY, so a small channel's video about a topic can simply not appear in the
                   top page at all. Use for a broad read of who is talking.

  --scope channel  DEFAULT. Query each followed channel's own search endpoint. Slower (N requests)
                   but COMPLETE - if a followed creator made a video with the term in it, this finds
                   it regardless of view count. This is the mode that answers "did Asmongold cover
                   the BioWare shutdown?" with a reliable no. Channels the instance throttles are
                   retried once, slowly; anything still unreachable is LISTED in the output, because
                   an unreachable channel is not the same answer as "no coverage".

Output is JSON (for run_daily / a workpack) or a plain text table (for a human reading a terminal).
A row whose term appears only in the video DESCRIPTION, not the title, is marked `title_match: false` /
"(desc match)" - the channel index searches both, and a passing mention is not a story.

DATE PRECISION, measured 2026-10-28: Invidious derives `published` from the rounded relative label it
scrapes ("3 days ago", "1 year ago"), not from the real upload time - three consecutive results came back
as exactly 72.0h / 120.0h / 144.0h old. So `--hours` is a rough window: the error is up to ~24h at day
scale and much larger at "1 year" scale. Never write this tool's date as fact in an edition; open the
video and use the real date.
Read-only: it never writes into editions or memory.

Usage
  python scripts/creator_search.py "Helldivers 2"
  python scripts/creator_search.py "BioWare" --hours 72 --tier 1
  python scripts/creator_search.py "Godot 4" --scope global --json tools/creator-hits.json
  python scripts/creator_search.py --list               # what counts as "followed"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

INVIDIOUS = ["https://yt.chocolatemoo53.com", "https://inv.nadeko.net"]
USER_AGENT = "DailyBeacon/1.0 (+personal reader)"
TIMEOUT = 25
DEFAULT_WORKERS = 4


# --------------------------------------------------------------------------- io
def project_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def load_channels(root: Path) -> list[dict]:
    path = root / "config" / "channels.json"
    if not path.exists():
        raise SystemExit(f"creator_search: missing {path}")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    return raw if isinstance(raw, list) else raw.get("channels", [])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: float | int | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OSError, OverflowError):
        return ""


# ------------------------------------------------------------------------ fetch
def _get_json(url: str) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
            json.JSONDecodeError, ValueError):
        return None


def search_channel(channel: dict, term: str) -> list[dict] | None:
    """Ask one channel's own search index. None means 'the instance failed us', [] means 'no hits'."""
    quoted = urllib.parse.quote(term)
    for base in INVIDIOUS:
        data = _get_json(f"{base}/api/v1/channels/{channel['id']}/search?q={quoted}")
        if isinstance(data, list):
            return [
                {
                    "channel": channel.get("name"),
                    "channel_id": channel.get("id"),
                    "tier": channel.get("tier"),
                    "video_id": v.get("videoId"),
                    "title": v.get("title"),
                    "published": iso(v.get("published")),
                    "published_ts": v.get("published") or 0,
                    "length_seconds": v.get("lengthSeconds"),
                    "views": v.get("viewCount"),
                    "url": "https://www.youtube.com/watch?v=" + str(v.get("videoId")),
                    "thumbnail": f"https://i.ytimg.com/vi/{v.get('videoId')}/hqdefault.jpg",
                }
                for v in data
                if v.get("videoId")
            ]
    return None


def search_global(term: str, pages: int) -> list[dict]:
    """One query, popularity-ranked, then the caller filters to followed channels."""
    quoted = urllib.parse.quote(term)
    out: list[dict] = []
    for page in range(1, max(1, pages) + 1):
        data = None
        for base in INVIDIOUS:
            data = _get_json(f"{base}/api/v1/search?q={quoted}&type=video&page={page}")
            if isinstance(data, list) and data:
                break
            data = None
        if not data:
            break
        for v in data:
            if v.get("videoId"):
                out.append(
                    {
                        "channel": v.get("author"),
                        "channel_id": v.get("authorId"),
                        "video_id": v.get("videoId"),
                        "title": v.get("title"),
                        "published": iso(v.get("published")),
                        "published_ts": v.get("published") or 0,
                        "length_seconds": v.get("lengthSeconds"),
                        "views": v.get("viewCount"),
                        "url": "https://www.youtube.com/watch?v=" + str(v.get("videoId")),
                        "thumbnail": f"https://i.ytimg.com/vi/{v.get('videoId')}/hqdefault.jpg",
                    }
                )
        time.sleep(1.0)
    return out


# ---------------------------------------------------------------------- filters
def keep(row: dict, hours: int, tiers: set[int] | None) -> bool:
    if hours > 0 and row.get("published_ts"):
        cutoff = now_utc() - timedelta(hours=hours)
        if datetime.fromtimestamp(int(row["published_ts"]), timezone.utc) < cutoff:
            return False
    if tiers and row.get("tier") and int(row["tier"]) not in tiers:
        return False
    return True


def drop_gameplay(rows: list[dict]) -> tuple[list[dict], int]:
    """Reuse the site's own policy so this tool and the edition agree on what a video is."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from yt_source import looks_like_gameplay  # type: ignore
    except Exception:
        return rows, 0
    kept, dropped = [], 0
    for row in rows:
        title = str(row.get("title") or "")
        length = row.get("length_seconds") or 0
        try:
            if looks_like_gameplay(title, int(length)):
                dropped += 1
                continue
        except Exception:
            pass
        kept.append(row)
    return kept, dropped


# ------------------------------------------------------------------------- main
def run(term: str, root: Path, scope: str, hours: int, tiers: set[int] | None,
        workers: int, pages: int, keep_gameplay: bool, title_only: bool = False) -> dict:
    channels = [c for c in load_channels(root) if c.get("enabled")]

    if scope == "global":
        rows = search_global(term, pages)
        followed_ids = {c["id"] for c in channels}
        followed_names = {str(c["name"]).lower() for c in channels}
        tier_of = {c["id"]: c.get("tier") for c in channels}
        filtered = []
        for row in rows:
            if row.get("channel_id") in followed_ids or str(row.get("channel") or "").lower() in followed_names:
                row["tier"] = tier_of.get(row.get("channel_id"))
                row["title_match"] = True  # the global search already matched the term
                filtered.append(row)
        missing = []
    else:
        filtered, missing = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(search_channel, c, term): c for c in channels}
            for future in as_completed(futures):
                channel = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result is None:
                    missing.append(channel.get("name"))
                else:
                    filtered.extend(result)

        # The public Invidious instances throttle a burst of ~50 queries, so a first pass can come back
        # empty on a third of the channels. Those are NOT "no coverage" - retry them, slowly, once.
        if missing:
            retry = [c for c in channels if c.get("name") in set(missing)]
            time.sleep(2.5)
            still_missing = []
            for channel in retry:
                result = search_channel(channel, term)
                if result is None:
                    still_missing.append(channel.get("name"))
                else:
                    filtered.extend(result)
                time.sleep(0.6)
            missing = still_missing

    # Invidious channel search matches the description as well as the title, so a video can come back
    # for a term it never says out loud. Annotate it rather than hiding it: the caller decides.
    needle = term.lower()
    for row in filtered:
        row["title_match"] = needle in str(row.get("title") or "").lower()

    if title_only:
        filtered = [r for r in filtered if r.get("title_match", True)]

    before = len(filtered)
    filtered = [r for r in filtered if keep(r, hours, tiers)]
    after_window = len(filtered)
    dropped_gameplay = 0
    if not keep_gameplay:
        filtered, dropped_gameplay = drop_gameplay(filtered)

    filtered.sort(key=lambda r: (int(r.get("published_ts") or 0)), reverse=True)
    return {
        "term": term,
        "generated": iso(datetime.now(timezone.utc).timestamp()),
        "scope": scope,
        "channels_checked": len(channels),
        "channels_unreachable": missing,
        "matches_raw": before,
        "matches_in_window": after_window,
        "gameplay_dropped": dropped_gameplay,
        "matches": filtered,
    }


def render_text(payload: dict) -> str:
    lines = []
    head = (f'"{payload["term"]}"  scope={payload["scope"]}  '
            f'channels={payload["channels_checked"]}  '
            f'matches={len(payload["matches"])}')
    lines.append(head)
    if payload.get("channels_unreachable"):
        lines.append(f'  ! unreachable: {", ".join(str(x) for x in payload["channels_unreachable"])}')
    if not payload["matches"]:
        lines.append("  (nobody you follow has a video matching this term in the window)")
        return "\n".join(lines)
    for row in payload["matches"]:
        when = (row.get("published") or "")[:10] or "?"
        mins = int((row.get("length_seconds") or 0) / 60)
        views = row.get("views")
        view_bit = f"{views:,}" if isinstance(views, int) else str(views or "?")
        flag = "" if row.get("title_match", True) else "  (desc match)"
        lines.append(f"  {when}  T{row.get('tier') or '-'}  {row.get('channel'):<20} "
                     f"{mins:>3}m  {view_bit:>10}  {row.get('title')}{flag}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Search a term across only the followed creators.")
    ap.add_argument("term", nargs="?", help="what to search for, e.g. \"Helldivers 2\"")
    ap.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    ap.add_argument("--scope", choices=("channel", "global"), default="channel",
                    help="channel = query every followed channel (complete); global = one search then "
                         "filter (fast, popularity-biased)")
    ap.add_argument("--hours", type=int, default=0,
                    help="only videos published within N hours (0 = no limit)")
    ap.add_argument("--tier", type=int, action="append", default=None,
                    help="restrict to a channel tier (repeatable), e.g. --tier 1")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--pages", type=int, default=2, help="global mode: result pages to read")
    ap.add_argument("--title-only", action="store_true",
                    help="drop description-only matches. The channel index searches descriptions too, "
                         "so a broad term can return a video that merely mentions it - at 03:00 that is "
                         "noise mistaken for a take.")
    ap.add_argument("--keep-gameplay", action="store_true",
                    help="do not drop let's-play uploads (they are dropped by default)")
    ap.add_argument("--json", default=None, help="write full JSON payload to this path")
    ap.add_argument("--list", action="store_true", help="list the followed channels and exit")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root(args.root)

    if args.list:
        channels = [c for c in load_channels(root) if c.get("enabled")]
        print(f"{len(channels)} followed (enabled) channels:")
        for c in sorted(channels, key=lambda c: (c.get("tier") or 9, str(c.get("name")).lower())):
            print(f"  T{c.get('tier')}  {c.get('name')}")
        return 0

    if not args.term:
        print("creator_search: give a search term, or --list", file=sys.stderr)
        return 2

    tiers = set(args.tier) if args.tier else None
    payload = run(args.term, root, args.scope, args.hours, tiers,
                  max(1, args.workers), max(1, args.pages), args.keep_gameplay, args.title_only)

    if args.json:
        out = Path(args.json)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out}")

    print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
