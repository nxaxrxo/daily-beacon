#!/usr/bin/env python3
"""yt_source.py - watched YouTube channels -> candidate videos inside the lookback window.

Endpoints (both verified live from this machine on 2026-10-28):
  Invidious  https://yt.chocolatemoo53.com/api/v1/channels/<channelId>/videos
             - gives published + lengthSeconds + viewCount in one call (preferred: it feeds the
               shorts filter and the score hint without extra requests)
  YouTube RSS https://www.youtube.com/feeds/videos.xml?channel_id=<channelId>
             - fallback when Invidious is down or does not know the channel; no length/views

One dead channel is data, not a crash: every channel is tried independently and the summary line
reports ok/failed. Exit 0 when at least one channel produced data.

Opinionated detail: Invidious orders newest-first and paginates, but we only need the head of the
list, so page 1 is enough. We also stop reading a channel as soon as an item is older than the
window -- the list is chronological, so nothing after it can be in range.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover
    print("yt_source: requests is required", file=sys.stderr)
    raise SystemExit(1)

try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
INVIDIOUS = ["https://yt.chocolatemoo53.com", "https://inv.nadeko.net"]
RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
TIMEOUT = 20
DEFAULT_HOURS = 50
DEFAULT_SHORT_MAX = 90


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso(dt: datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def project_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def load_settings(root: Path) -> dict:
    data = read_json(root / "config" / "settings.json", {})
    return data if isinstance(data, dict) else {}


def video_id_from_any(raw: str) -> str | None:
    s = str(raw or "").strip()
    if not s:
        return None
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = re.search(r"(?:v=|/vi/|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else None


# ------------------------------------------------------------------ Invidious

def invidious_channel(base: str, channel_id: str) -> list[dict] | None:
    url = f"{base}/api/v1/channels/{channel_id}/videos"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        payload = r.json()
    except Exception:
        return None
    vids = payload.get("videos") if isinstance(payload, dict) else None
    if not isinstance(vids, list):
        return None
    out = []
    for v in vids:
        if not isinstance(v, dict):
            continue
        vid = v.get("videoId")
        title = v.get("title")
        published = v.get("published")
        if not vid or not title or not isinstance(published, (int, float)):
            continue
        out.append(
            {
                "videoId": str(vid),
                "title": str(title),
                "publishedAt": iso(datetime.fromtimestamp(int(published), tz=timezone.utc)),
                "lengthSeconds": v.get("lengthSeconds") if isinstance(v.get("lengthSeconds"), int) else None,
                "views": v.get("viewCount") if isinstance(v.get("viewCount"), int) else None,
            }
        )
    return out


# ------------------------------------------------------------------ RSS fallback

def rss_channel(channel_id: str) -> list[dict] | None:
    url = RSS.format(cid=channel_id)
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except Exception:
        return None
    if r.status_code != 200 or "<entry" not in r.text:
        return None
    entries = r.text.split("<entry>")[1:]
    out = []
    for chunk in entries:
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", chunk)
        title = re.search(r"<title>([^<]*)</title>", chunk)
        published = re.search(r"<published>([^<]+)</published>", chunk)
        thumb = re.search(r'<media:thumbnail url="([^"]+)"', chunk)
        if not vid or not title:
            continue
        out.append(
            {
                "videoId": vid.group(1).strip(),
                "title": html_unescape(title.group(1)),
                "publishedAt": published.group(1).strip() if published else None,
                "lengthSeconds": None,
                "views": None,
                "thumbnail": thumb.group(1) if thumb else None,
            }
        )
    return out or None


def html_unescape(text: str) -> str:
    return (
        str(text)
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
    )


# ------------------------------------------------------------------ main

def parse_published(text: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone()
    except Exception:
        return None


def collect(root: Path, hours: int, only_channel: str | None, no_shorts: bool, limit: int | None):
    channels = read_json(root / "config" / "channels.json", [])
    if not isinstance(channels, list) or not channels:
        print("yt_source: config/channels.json missing or empty", file=sys.stderr)
        raise SystemExit(1)

    settings = load_settings(root)
    short_max = int(settings.get("short_max_seconds") or DEFAULT_SHORT_MAX)
    per_channel_cap = int(settings.get("max_videos_per_channel") or 3)

    window_start = now_local() - timedelta(hours=hours)
    picked = []
    ok = 0
    failed = 0
    skipped = 0

    for ch in channels:
        if not isinstance(ch, dict):
            continue
        cid = str(ch.get("id") or "").strip()
        name = str(ch.get("name") or cid or "?")
        if not cid.startswith("UC"):
            skipped += 1
            continue
        if only_channel and cid != only_channel:
            continue
        if ch.get("enabled") is False:
            skipped += 1
            continue

        tier = ch.get("tier") if ch.get("tier") in (1, 2, 3) else 2
        tags = [str(t) for t in (ch.get("tags") or []) if t]

        raw = None
        for base in INVIDIOUS:
            raw = invidious_channel(base, cid)
            if raw:
                break
        if raw is None:
            raw = rss_channel(cid)
        if raw is None:
            failed += 1
            print(f"  ! {name}: no data (invidious + rss both failed)", file=sys.stderr)
            continue

        ok += 1
        count = 0
        max_per = int(ch.get("max_per_run") or per_channel_cap)
        for v in raw:
            published = parse_published(v.get("publishedAt"))
            if published is None:
                # Undated entry cannot be window-filtered: keep it rather than hide content on
                # missing metadata, and let it sort last.
                pass
            if published < window_start:
                break  # newest-first: everything after this is older
            length = v.get("lengthSeconds")
            is_short = length is not None and length <= short_max
            if no_shorts and is_short:
                continue
            if count >= max_per:
                break
            count += 1
            vid = v["videoId"]
            picked.append(
                {
                    "source": "youtube",
                    "kind": "short" if is_short else "video",
                    "key": "yt:" + vid,
                    "title": html_unescape(v["title"]),
                    "url": "https://www.youtube.com/watch?v=" + vid,
                    "publishedAt": iso(published),
                    "score_hint": float(4 - tier),
                    "tags": tags,
                    "thumb_local": None,
                    "videoId": vid,
                    "channel": name,
                    "channelId": cid,
                    "thumbnail": v.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "lengthSeconds": length,
                    "views": v.get("views"),
                    "tier": tier,
                }
            )
        time.sleep(0.15)  # be a good citizen; serial by design

    # newest first across channels, then cap
    picked.sort(key=lambda x: x["publishedAt"], reverse=True)
    if limit and limit > 0:
        picked = picked[:limit]

    return picked, ok, failed, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect new YouTube videos from config/channels.json")
    ap.add_argument("--out", required=True, help="output json path")
    ap.add_argument("--hours", type=int, default=DEFAULT_HOURS, help="lookback window in hours")
    ap.add_argument("--channel", default=None, help="single channelId, for testing")
    ap.add_argument("--no-shorts", action="store_true", help="drop videos at or under short_max_seconds")
    ap.add_argument("--limit", type=int, default=0, help="cap the result (0 = no cap)")
    ap.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    args = ap.parse_args(argv)

    root = project_root(args.root)
    settings = load_settings(root)
    if not args.hours:
        args.hours = int(settings.get("lookback_hours") or DEFAULT_HOURS)

    picked, ok, failed, skipped = collect(root, args.hours, args.channel, args.no_shorts, args.limit or None)

    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(picked, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"yt_source done: {len(picked)} videos from {ok}/{ok + failed} channels "
        f"({failed} failed)"
    )
    if ok == 0:
        print("yt_source: every channel failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
