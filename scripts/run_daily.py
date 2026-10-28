#!/usr/bin/env python3
"""run_daily.py - the one command the 03:00 agent runs first.

    python scripts/run_daily.py collect [--date YYYY-MM-DD] [--hours 50] [--limit-transcripts N]

Chains the deterministic steps and writes state/workpack/<date>/packet.md, the file the 03:00
agent reads instead of raw JSON.

  step 1  yt_source.py + news_source.py -> candidates.json (canonical, capped, deduped)
  step 2  memory.py filter              -> filtered.json + suppressed.json
  step 3  transcripts.py                -> transcripts/<videoId>.txt + index.json
  step 4  images                        -> img/<sha1-16>.<ext> + images.json
  step 5  packet.md

Every step is isolated: a dead feed, a blocked YouTube IP or a failed transcript is data, not an
abort. A short edition still gets published. The only fatal condition is being unable to write
candidates.json at all.

Counts convention: the headline "<v> videos, <a> articles" is the candidate set AFTER the
mechanical caps (what the day actually offers), not the raw producer totals; the transcript step
may touch fewer videos than that by design.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

DEFAULTS = {
    "lookback_hours": 50,
    "max_videos_per_channel": 4,
    "max_videos_total": 80,
    "max_news_items": 140,
    "transcript_max_chars": 24000,
    "repeat_topic_cooldown_days": 21,
}
# kept in step with news_source.MAX_PER_SOURCE - the collector and the merge must agree, or a
# resumed run silently re-caps what the producer already allowed through
NEWS_PER_SOURCE_CAP = 6
# Was 24, which silently starved the page: up to 220 candidates with a thumbnail each meant the
# images ran out after the first dozen items, so most sections shipped as text with no figure.
# The owner asked for images; an edition can carry up to 24 sections, so allow ~2 per section.
MAX_IMAGES = 60
IMG_MAX_BYTES = 8 * 1024 * 1024
IMG_TIMEOUT = 10
IMG_WORKERS = 4
TITLE_MAX = 120
TOP_LINES = 20
TRACKING = {"fbclid", "gclid", "ref", "referrer", "source", "mc_cid", "mc_eid", "igshid",
            "cmpid", "si", "feature", "spm", "s", "share", "at_medium", "at_campaign"}

_log_lock = threading.Lock()
_log_path = None  # set by cmd_collect: every line also lands in the workpack's collect.log


def log(msg: str = "") -> None:
    with _log_lock:
        print(msg, flush=True)
        if _log_path is not None:
            try:
                with open(_log_path, "a", encoding="utf-8", errors="replace") as fh:
                    fh.write(str(msg) + "\n")
            except OSError:
                pass


def ascii_safe(value, limit: int | None = None) -> str:
    text = str(value if value is not None else "").encode("ascii", "replace").decode("ascii")
    if limit and len(text) > limit:
        text = text[: max(limit - 3, 0)] + "..."
    return text


# --------------------------------------------------------------------------- plumbing

def project_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def read_json(path: Path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def write_json(path: Path, payload) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(path)


def write_text(path: Path, payload: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_settings(root: Path) -> dict:
    data = read_json(root / "config" / "settings.json", {})
    out = dict(DEFAULTS)
    if isinstance(data, dict):
        for key, default in DEFAULTS.items():
            value = data.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                value = default
            out[key] = value
    return out


def iso(dt: datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def parse_dt(text) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def ts_of(item: dict) -> float:
    dt = parse_dt(item.get("publishedAt"))
    return dt.timestamp() if dt else 0.0


def collapse(value) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def sha16(text: str) -> str:
    return hashlib.sha1(str(text).encode("utf-8", "replace")).hexdigest()[:16]


def norm_title(value) -> str:
    s = collapse(value).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_url(url: str) -> str:
    try:
        parts = urlsplit(str(url or "").strip())
    except Exception:
        return str(url or "")
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
                   if k.lower() not in TRACKING)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    tail = "&".join(k + "=" + v for k, v in query)
    return host + path + ("?" + tail if tail else "")


def video_id_of(item: dict) -> str | None:
    vid = str(item.get("videoId") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        return vid
    match = re.search(r"(?:v=|/vi/|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})",
                      str(item.get("url") or ""))
    return match.group(1) if match else None


def run_step(cmd: list[str], root: Path, timeout: int) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 124, "timeout after %ds" % timeout
    except Exception as exc:  # noqa: BLE001
        return 125, "%s: %s" % (type(exc).__name__, str(exc)[:200])
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def parse_producer_stats(output: str, prefix: str, fallback_count: int, count_key: str) -> dict:
    """Pull ok/total/failed out of a producer's summary line.

    The producers are separate processes and their summary line is the only place the channel/feed
    counts exist, so it is parsed with a tolerant pattern (extra whitespace, either "channels" or
    "feeds"). If it cannot be found, the item count still comes from the file that was written -
    a missing summary must never turn real data into a zero.
    """
    text = str(output or "")
    pattern = (r"%s done:\s*(\d+)\s+\w+\s+from\s+(\d+)\s*/\s*(\d+)\s+\w+\s*\(\s*(\d+)\s+failed\s*\)"
               % re.escape(prefix))
    hit = re.search(pattern, text) or re.search(pattern, "\n".join(text.splitlines()[-8:]))
    if hit:
        return {count_key: int(hit.group(1)), "ok": int(hit.group(2)),
                "total": int(hit.group(3)), "failed": int(hit.group(4))}
    return {count_key: fallback_count, "ok": None, "total": None, "failed": None}


def tail_line(output: str) -> str:
    lines = [ln.strip() for ln in str(output or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def read_array(path: Path) -> list:
    data = read_json(path, [])
    if isinstance(data, dict):
        data = data.get("items")
    return data if isinstance(data, list) else []


# --------------------------------------------------------------------------- step 1: merge

def canon_video(raw: dict) -> dict:
    tier = raw.get("tier")
    if isinstance(tier, bool) or tier not in (1, 2, 3):
        tier = 2
    vid = video_id_of(raw) or ""
    length = raw.get("lengthSeconds")
    views = raw.get("views")
    kind = "short" if str(raw.get("kind") or "") == "short" else "video"
    return {
        "source": "youtube",
        "kind": kind,
        "key": "yt:" + vid if vid else str(raw.get("key") or ""),
        "title": collapse(raw.get("title")),
        "url": str(raw.get("url") or ("https://www.youtube.com/watch?v=" + vid if vid else "")),
        "publishedAt": raw.get("publishedAt") or None,
        "score_hint": float(4 - tier),
        "tags": [str(t) for t in (raw.get("tags") or []) if t],
        "thumb_local": None,
        "videoId": vid or None,
        "channel": str(raw.get("channel") or raw.get("channelId") or ""),
        "channelId": str(raw.get("channelId") or "") or None,
        "thumbnail": str(raw.get("thumbnail") or "") or None,
        "lengthSeconds": int(length) if isinstance(length, (int, float)) and not isinstance(length, bool) else None,
        "views": int(views) if isinstance(views, (int, float)) and not isinstance(views, bool) else None,
        "tier": int(tier),
    }


def canon_article(raw: dict) -> dict:
    weight = raw.get("weight")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        weight = 1
    weight = int(weight)
    url = str(raw.get("url") or "").strip()
    feed_tags = [str(t) for t in (raw.get("feedTags") or raw.get("tags") or []) if t]
    return {
        "source": "news",
        "kind": "article",
        "key": str(raw.get("key") or ("url:" + sha16(norm_url(url)))),
        "title": collapse(raw.get("title")),
        "url": url,
        "publishedAt": raw.get("publishedAt") or None,
        "score_hint": float(weight),
        "tags": feed_tags,
        "thumb_local": None,
        "sourceName": str(raw.get("sourceName") or ""),
        "feedTags": feed_tags,
        "summary": collapse(raw.get("summary"))[:600],
        "image": str(raw.get("image") or "") or None,
        "weight": weight,
        "also_on": [str(s) for s in (raw.get("also_on") or []) if s],
    }


def cap_videos(items: list[dict], settings: dict) -> list[dict]:
    ordered = sorted(items, key=lambda i: (i.get("tier", 2), -ts_of(i)))
    per_channel: dict[str, int] = {}
    out = []
    cap_channel = int(settings["max_videos_per_channel"])
    for item in ordered:
        channel = str(item.get("channelId") or item.get("channel") or "")
        if per_channel.get(channel, 0) >= cap_channel:
            continue
        per_channel[channel] = per_channel.get(channel, 0) + 1
        out.append(item)
    return out[: int(settings["max_videos_total"])]


def cap_articles(items: list[dict], settings: dict) -> list[dict]:
    ordered = sorted(items, key=lambda i: (-float(i.get("weight") or 0), -ts_of(i)))
    per_source: dict[str, int] = {}
    out = []
    for item in ordered:
        source = str(item.get("sourceName") or "")
        if per_source.get(source, 0) >= NEWS_PER_SOURCE_CAP:
            continue
        per_source[source] = per_source.get(source, 0) + 1
        out.append(item)
    return out[: int(settings["max_news_items"])]


# Business-changing events outrank every scoring rule: a studio closing is not a "tier-2 item".
# On 2026-10-28 the packet contained "EA CLOSES BIOWARE" from AngryJoeShow and the edition still shipped
# a Dunkey bag-of-chips video instead. Prose telling the writer to look for closures did not survive a
# 03:00 run, so detection is mechanical here and the packet labels the item.
BUSINESS_EVENT_RE = re.compile(
    r"\b(?:"
    r"shuts?\s+down|shutting\s+down|shut\s+down|shuttered|"
    r"studio\s+closure|closing\s+down|"
    r"ceases?\s+operations|closes?\s+(?:its|their|the)\s+doors|"
    r"lays?\s+off|laid\s+off|layoffs?|mass\s+layoffs?|redundancies|"
    r"acquires?|acquired\s+by|acquisition|buys?\s+out|bought\s+out|"
    r"cancels?|cancelled|canceled|"
    r"delists?|delisted|delisting|"
    r"files?\s+for\s+bankruptcy|bankruptcy|insolvency|"
    r"resigns?|steps?\s+down|removed\s+as\s+(?:ceo|director)"
    r")\b",
    re.IGNORECASE,
)

# "closes <Name>" is the one stem that needs its object capitalised: "the shop closes at five" is not
# a business event, but "EA CLOSES BIOWARE" and "closes BioWare" both are. Case-sensitive on purpose.
BUSINESS_EVENT_CLOSES_RE = re.compile(
    r"\b(?:closes|closed|closing)\s+(?:its|their|the)?\s*(?-i:[A-Z])",
    re.IGNORECASE,
)

# A delay is not in the class on its own - only a cancellation is. Neither is "layoffs rumoured".
# Deliberately narrow. "reportedly" or "could" must NOT veto: a reported closure is still a closure, and
# a false negative here is the exact failure this detector exists to prevent. Only an outright rumour
# label drops it, and even then the writer still sees the item - it just is not promoted.
BUSINESS_EVENT_VETO_RE = re.compile(r"\b(?:rumou?rs?)\b", re.IGNORECASE)


def business_event(item: dict) -> bool:
    """True when a headline describes something that changes a company, not just a game's content."""
    title = str(item.get("title") or "")
    if not title:
        return False
    if not (BUSINESS_EVENT_RE.search(title) or BUSINESS_EVENT_CLOSES_RE.search(title)):
        return False
    return not BUSINESS_EVENT_VETO_RE.search(title)


def tag_business_events(items: list[dict]) -> int:
    hits = 0
    for item in items:
        flag = business_event(item)
        item["business_event"] = flag
        if flag:
            hits += 1
    return hits


def merge_candidates(yt_raw: list, news_raw: list, settings: dict) -> list[dict]:
    # The gameplay filter also lives in yt_source, but --reuse-source reads an existing yt.json
    # verbatim - the resume path the runbook recommends. Without this second gate a resumed run
    # would reintroduce exactly the uploads the channel policy excludes.
    videos = [canon_video(r) for r in yt_raw if isinstance(r, dict)]
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("yt_source", Path(__file__).resolve().parent / "yt_source.py")
        _yt = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_yt)
        before = len(videos)
        videos = [v for v in videos
                  if not _yt.looks_like_gameplay(v.get("title", ""), v.get("lengthSeconds"))]
        dropped = before - len(videos)
        if dropped:
            print("merge: %d gameplay upload(s) dropped by channel policy" % dropped)
    except Exception:
        pass  # never let the policy filter break a run
    articles = [canon_article(r) for r in news_raw if isinstance(r, dict)]
    videos = cap_videos([v for v in videos if v["key"]], settings)
    articles = cap_articles([a for a in articles if a["key"] and a["url"]], settings)

    merged: list[dict] = []
    seen: set[str] = set()
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()

    for item in videos + articles:
        key = item["key"]
        if key in seen:
            continue
        if item["source"] == "news":
            nurl = norm_url(item["url"])
            ntitle = norm_title(item["title"])
            if nurl in seen_urls or (ntitle and ntitle in seen_titles):
                continue
            seen_urls.add(nurl)
            if ntitle:
                seen_titles.add(ntitle)
        seen.add(key)
        merged.append(item)

    flagged = tag_business_events(merged)
    if flagged:
        # stable: flagged items first, original order preserved inside each group
        merged.sort(key=lambda i: 0 if i.get("business_event") else 1)
    return merged


# --------------------------------------------------------------------------- step 4: images

def image_extension(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def fetch_image(url: str, img_dir: Path) -> str | None:
    """Download one image. Any failure is a silent skip: a missing picture is not an error."""
    if requests is None or not url:
        return None
    name = sha16(url)
    exist = sorted(img_dir.glob(name + ".*")) if img_dir.is_dir() else []
    for path in exist:
        try:
            if path.is_file() and 0 < path.stat().st_size <= IMG_MAX_BYTES:
                return path.name
        except OSError:
            continue
    try:
        resp = requests.get(url, headers=HEADERS, timeout=IMG_TIMEOUT, stream=True)
        if resp.status_code != 200:
            return None
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > IMG_MAX_BYTES:
            return None
        chunks, total = [], 0
        for chunk in resp.iter_content(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > IMG_MAX_BYTES:
                return None
            chunks.append(chunk)
        data = b"".join(chunks)
        if not data:
            return None
        ext = image_extension(data)
        if ext is None:
            return None
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as probe:
                if probe.format not in ("JPEG", "PNG", "WEBP"):
                    return None
                probe.verify()
        except Exception:
            return None
        img_dir.mkdir(parents=True, exist_ok=True)
        target = img_dir / (name + "." + ext)
        target.write_bytes(data)
        return target.name
    except Exception:
        return None


def download_images(items: list[dict], root: Path, img_dir: Path, settings: dict | None = None) -> dict[str, str]:
    targets = []
    for item in items:
        if len(targets) >= int((settings or {}).get("max_images") or MAX_IMAGES):
            break
        url = item.get("thumbnail") if item.get("source") == "youtube" else item.get("image")
        if url:
            targets.append((str(item["key"]), str(url)))
    if not targets or requests is None:
        return {}

    mapping: dict[str, str] = {}
    lock = threading.Lock()

    def work(pair):
        key, url = pair
        name = fetch_image(url, img_dir)
        if not name:
            return
        rel = (img_dir / name).relative_to(root).as_posix()
        with lock:
            mapping[key] = rel

    with ThreadPoolExecutor(max_workers=IMG_WORKERS) as pool:
        list(pool.map(work, targets))
    return mapping


# --------------------------------------------------------------------------- step 5: packet

def packet_published(item: dict) -> str:
    dt = parse_dt(item.get("publishedAt"))
    if dt is None:
        return "unknown"
    return dt.astimezone().isoformat(timespec="minutes")


def item_line(item: dict, workpack: Path) -> str:
    title = ascii_safe(collapse(item.get("title")).replace("\r", " ").replace("\n", " "), TITLE_MAX)
    if item.get("source") == "youtube":
        number = item.get("tier") if isinstance(item.get("tier"), int) else 9
        source = str(item.get("channel") or "?")
        vid = video_id_of(item) or ""
        has_tx = "yes" if vid and (workpack / "transcripts" / (vid + ".txt")).is_file() else "no"
    else:
        number = int(item.get("weight") or 0)
        source = str(item.get("sourceName") or "?")
        has_tx = "no"
    tag = "T%d|w%d" % (number, number)
    # A flagged business event is marked in the packet itself, so the writer cannot miss it even if it
    # never reads the runbook section that explains why the mark exists.
    mark = " **BUSINESS EVENT**" if item.get("business_event") else ""
    return "- [%s] %s | %s | %s | %s | transcript:%s%s" % (
        tag, title, ascii_safe(source, 60), packet_published(item), str(item.get("url") or ""),
        has_tx, mark)


def build_packet(date: str, hours: int, counts: dict, videos: list, articles: list,
                 recent_topics: list, cooldown_days: int, settings: dict | None = None) -> str:
    now = iso(datetime.now().astimezone())
    lines = [
        "# DAILY BEACON - workpack " + date,
        "generated %s | lookback %dh | %d videos, %d articles | %d repeats suppressed" % (
            now, hours, counts["videos"], counts["articles"], counts["suppressed"]),
        "",
        "## counts",
    ]
    lines.extend(counts["lines"])
    # The packet is the agent's whole view of the night. Capping it at TOP_LINES while the collector
    # keeps 80 videos and 140 articles meant the raise was invisible: everything past line 20 was
    # collected, paid for, and then never seen by the only reader. Show every kept item instead, with
    # the collector's own caps as the bound so the two can never disagree.
    settings = settings or {}
    video_lines = int(settings.get("max_videos_total") or TOP_LINES)
    article_lines = int(settings.get("max_news_items") or TOP_LINES)
    # Business-changing events first, in their own block, before the ranked run. On 2026-10-28 the
    # closure of BioWare sat in the packet alphabetically and the edition never touched it.
    # Deduplicated on the item key: the same story often arrives from two feeds and the block is a
    # "read this first" list, so a repeated line is noise.
    flagged, seen_keys = [], set()
    for item in (videos + articles):
        if item.get("business_event") and item.get("key") not in seen_keys:
            seen_keys.add(item.get("key"))
            flagged.append(item)
    if flagged:
        lines.extend(["", "## business events (%d) - these outrank everything below" % len(flagged)])
        lines.extend(item_line(i, counts["workpack"]) for i in flagged)

    lines.extend(["", "## videos (%d kept, all listed)" % len(videos)])
    if videos:
        lines.extend(item_line(i, counts["workpack"]) for i in videos[:video_lines])
    else:
        lines.append("- none")
    lines.extend(["", "## articles (%d kept, all listed)" % len(articles)])
    if articles:
        lines.extend(item_line(i, counts["workpack"]) for i in articles[:article_lines])
    else:
        lines.append("- none")
    lines.extend(["", "## cooling down"])
    shown = 0
    for topic in recent_topics:
        if not isinstance(topic, dict):
            continue
        last = str(topic.get("last_covered") or "")[:10] or "unknown"
        lines.append("- %s | last %s | %dx" % (ascii_safe(topic.get("topic")), last,
                                               int(topic.get("times") or 0)))
        shown += 1
    if not shown:
        lines.append("- none")
    lines.append("topic cooldown: %d days" % cooldown_days)
    lines.extend([
        "",
        "## next commands",
        "1. read this packet, open 3-8 transcripts from state/workpack/%s/transcripts/" % date,
        "2. write editions/%s.json" % date,
        "3. python scripts/build_edition.py --date %s" % date,
        "4. python scripts/publish.py",
        "5. python scripts/memory.py mark --edition editions/%s.json" % date,
        "",
    ])
    return "\n".join(lines)


# --------------------------------------------------------------------------- main

def cmd_collect(args) -> int:
    root = project_root(args.root)
    settings = load_settings(root)
    now = datetime.now().astimezone()
    date = args.date or now.strftime("%Y-%m-%d")
    hours = args.hours if args.hours else int(settings["lookback_hours"])
    cooldown_days = int(settings["repeat_topic_cooldown_days"])

    workpack = root / "state" / "workpack" / date
    workpack.mkdir(parents=True, exist_ok=True)
    global _log_path
    try:
        (root / "state" / "logs").mkdir(parents=True, exist_ok=True)
        _log_path = root / "state" / "logs" / ("collect-" + date + ".log")
        _log_path.write_text("", encoding="utf-8")
    except OSError:
        _log_path = None
    img_dir = workpack / "img"
    tx_dir = workpack / "transcripts"
    img_dir.mkdir(exist_ok=True)
    tx_dir.mkdir(exist_ok=True)

    py = sys.executable or "python"
    warnings: list[str] = []
    yt_stats = {"videos": 0, "ok": None, "total": None, "failed": None}
    news_stats = {"articles": 0, "ok": None, "total": None, "failed": None}

    # ---- step 1: producers
    # --reuse-source exists because the collection is genuinely long (77 channels, serial by design).
    # If the run is interrupted after a producer finished, there is no reason to pay for it twice.
    yt_path, news_path = workpack / "yt.json", workpack / "news.json"
    reuse = bool(getattr(args, "reuse_source", False))
    have_yt = reuse and yt_path.exists() and yt_path.stat().st_size > 2
    have_news = reuse and news_path.exists() and news_path.stat().st_size > 2
    out = ""
    rc = 0
    if have_yt:
        log("step1 yt: reusing yt.json (--reuse-source)")
        yt_stats.update(videos=len(read_array(yt_path)), ok=0, total=0, failed=0)
    else:
        rc, out = run_step([py, "scripts/yt_source.py", "--out", str(yt_path),
                            "--hours", str(hours), "--root", str(root)], root, 1800)
    if out:
        log(ascii_safe(out))
    yt_stats.update(parse_producer_stats(out, "yt_source", len(read_array(yt_path)), "videos"))
    if not have_yt and rc != 0:
        warnings.append("yt_source exit %d" % rc)
        log("WARN yt_source exited %d - continuing with whatever it wrote" % rc)

    out = ""
    rc = 0
    if have_news:
        log("step1 news: reusing news.json (--reuse-source)")
        news_stats.update(articles=len(read_array(news_path)), ok=0, total=0, failed=0)
    else:
        rc, out = run_step([py, "scripts/news_source.py", "--out", str(news_path),
                            "--hours", str(hours), "--root", str(root)], root, 1800)
    if out:
        log(ascii_safe(out))
    news_stats.update(parse_producer_stats(out, "news_source", len(read_array(news_path)), "articles"))
    if rc != 0:
        warnings.append("news_source exit %d" % rc)
        log("WARN news_source exited %d - continuing with whatever it wrote" % rc)

    candidates = merge_candidates(read_array(yt_path), read_array(news_path), settings)
    try:
        write_json(workpack / "candidates.json", candidates)
    except Exception as exc:  # noqa: BLE001
        print("collect failed: cannot write candidates.json: %s" % ascii_safe(exc), file=sys.stderr)
        return 1
    videos = [c for c in candidates if c["source"] == "youtube"]
    articles = [c for c in candidates if c["source"] == "news"]
    log("step1 merged: %d candidates (%d videos, %d articles) -> candidates.json"
        % (len(candidates), len(videos), len(articles)))

    # ---- step 2: memory filter
    filtered_path = workpack / "filtered.json"
    suppressed_path = workpack / "suppressed.json"
    filtered = {}
    rc, out = run_step([py, "scripts/memory.py", "filter",
                        "--candidates", str(workpack / "candidates.json"),
                        "--out", str(filtered_path),
                        "--suppressed", str(suppressed_path),
                        "--root", str(root)], root, 300)
    if out:
        log(ascii_safe(out))
    if rc == 0:
        filtered = read_json(filtered_path, {})
        if not isinstance(filtered, dict) or not isinstance(filtered.get("items"), list):
            filtered = {}
    if not filtered:
        warnings.append("memory filter failed (exit %d)" % rc)
        log("WARN memory filter failed (exit %d) - writing an unfiltered filtered.json" % rc)
        items = []
        for item in candidates:
            row = dict(item)
            row.update({"seen": False, "seen_reason": None, "topic_hits": []})
            items.append(row)
        filtered = {
            "generatedAt": iso(datetime.now().astimezone()),
            "date": date,
            "cooldown_days": cooldown_days,
            "recent_topics": [],
            "counts": {"total": len(items), "seen": 0, "fresh": len(items)},
            "items": items,
        }
        try:
            write_json(filtered_path, filtered)
            write_json(suppressed_path, {"generatedAt": filtered["generatedAt"], "items": []})
        except Exception as exc:  # noqa: BLE001
            log("WARN could not write filtered.json: %s" % ascii_safe(exc))

    items = filtered.get("items") if isinstance(filtered.get("items"), list) else []
    fresh = [i for i in items if isinstance(i, dict) and i.get("seen") is not True]
    suppressed_items = read_json(suppressed_path, {})
    suppressed_items = (suppressed_items.get("items")
                        if isinstance(suppressed_items, dict) and isinstance(suppressed_items.get("items"), list)
                        else [])
    suppressed_n = len(suppressed_items)
    fcounts = filtered.get("counts") if isinstance(filtered.get("counts"), dict) else {}
    fresh_videos = [i for i in fresh if i.get("source") == "youtube"]
    fresh_articles = [i for i in fresh if i.get("source") == "news"]

    # ---- step 3: transcripts
    limit_tx = (args.limit_transcripts if args.limit_transcripts is not None
                else min(12, int(settings["max_videos_total"])))
    tx_stats = {"fetched": 0, "cached": 0, "failed": 0}
    rc, out = run_step([py, "scripts/transcripts.py",
                        "--candidates", str(filtered_path),
                        "--out-dir", str(tx_dir),
                        "--limit", str(limit_tx),
                        "--max-chars", str(int(settings["transcript_max_chars"])),
                        "--root", str(root)], root, 7200)
    if out:
        log(ascii_safe(out))
    hit = re.search(r"transcripts done: (\d+) fetched, (\d+) cached, (\d+) failed", tail_line(out))
    if hit:
        tx_stats.update(fetched=int(hit.group(1)), cached=int(hit.group(2)),
                        failed=int(hit.group(3)))
    elif rc != 0:
        warnings.append("transcripts exit %d" % rc)
        log("WARN transcripts exited %d - continuing with 0 transcripts" % rc)
    tx_files = len(list(tx_dir.glob("*.txt")))

    # ---- step 4: images
    image_map: dict[str, str] = {}
    if args.skip_images:
        log("step4 images: skipped (--skip-images)")
    else:
        try:
            image_map = download_images(fresh_videos + fresh_articles, root, img_dir)
        except Exception as exc:  # noqa: BLE001
            warnings.append("images %s" % type(exc).__name__)
            log("WARN images step failed: %s" % type(exc).__name__)
        log("step4 images: %d downloaded -> img/" % len(image_map))
    try:
        write_json(workpack / "images.json", dict(sorted(image_map.items())))
    except Exception as exc:  # noqa: BLE001
        log("WARN could not write images.json: %s" % ascii_safe(exc))

    if image_map:
        try:
            patched = read_json(filtered_path, {})
            if isinstance(patched, dict) and isinstance(patched.get("items"), list):
                for row in patched["items"]:
                    if isinstance(row, dict) and row.get("key") in image_map:
                        row["thumb_local"] = image_map[row["key"]]
                write_json(filtered_path, patched)
                filtered = patched
        except Exception as exc:  # noqa: BLE001
            log("WARN could not patch filtered.json with thumb_local: %s" % ascii_safe(exc))

    # ---- step 5: packet
    def pair_line(stats: dict, key: str, unit: str) -> str:
        if stats["ok"] is None:
            if stats[unit]:
                return "- %s: %d %s | reused from disk (--reuse-source)" % (key, stats[unit], unit)
            return "- %s: %d %s | producer did not report a summary" % (key, stats[unit], unit)
        if stats["ok"] == 0 and stats["total"] == 0:
            return "- %s: %d %s | reused from disk (--reuse-source), no fetch this run" % (
                key, stats[unit], unit)
        return "- %s: %d %s | %d/%d ok, %d failed" % (
            key, stats[unit], unit, stats["ok"], stats["total"], stats["failed"])

    counts = {
        "videos": len(videos),
        "articles": len(articles),
        "suppressed": suppressed_n,
        "workpack": workpack,
        "lines": [
            pair_line(yt_stats, "youtube", "videos"),
            pair_line(news_stats, "news", "articles"),
            "- candidates after caps: %d videos, %d articles (%d total)"
            % (len(videos), len(articles), len(candidates)),
            "- memory filter: %s total, %s seen, %s fresh"
            % (fcounts.get("total", len(items)), fcounts.get("seen", 0), fcounts.get("fresh", len(fresh))),
            "- repeats suppressed: %d" % suppressed_n,
            "- transcripts: %d fetched, %d cached, %d failed (%d files on disk)"
            % (tx_stats["fetched"], tx_stats["cached"], tx_stats["failed"], tx_files),
            "- images downloaded: %d" % len(image_map),
            "- warnings: %s" % (" ; ".join(ascii_safe(w, 80) for w in warnings) if warnings else "none"),
        ],
    }
    try:
        packet = build_packet(date, hours, counts, fresh_videos, fresh_articles,
                              filtered.get("recent_topics") or [], cooldown_days, settings)
        write_text(workpack / "packet.md", packet)
        log("step5 packet: %s" % (workpack / "packet.md").relative_to(root).as_posix())
    except Exception as exc:  # noqa: BLE001
        log("WARN could not write packet.md: %s" % ascii_safe(exc))

    log("collect done: %d videos, %d articles, %d transcripts, %d repeats suppressed"
        % (len(videos), len(articles), tx_files, suppressed_n))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run_daily.py",
        description="Daily Beacon orchestrator: producers -> filter -> transcripts -> images -> packet.",
        epilog="The 03:00 agent runs 'collect' and then reads state/workpack/<date>/packet.md.")
    ap.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    sub = ap.add_subparsers(dest="command")
    # room reserved for a future 'status' verb; no other verbs may be added silently
    col = sub.add_parser("collect", help="run the whole collection into state/workpack/<date>/")
    col.add_argument("--date", default=None, help="workpack date YYYY-MM-DD (default: today local)")
    col.add_argument("--hours", type=int, default=None,
                     help="lookback hours (default: settings lookback_hours = 50)")
    col.add_argument("--limit-transcripts", type=int, default=None,
                     help="cap transcripts (default: min(12, max_videos_total))")
    col.add_argument("--skip-images", action="store_true", help="do not download thumbnails/images")
    col.add_argument("--reuse-source", action="store_true",
                     help="reuse an existing yt.json/news.json instead of refetching (resume a killed run)")
    col.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command != "collect":
        ap.print_help()
        return 2
    return cmd_collect(args)


if __name__ == "__main__":
    raise SystemExit(main())
