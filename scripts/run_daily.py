#!/usr/bin/env python3
"""run_daily.py - the one command the 03:00 agent runs first.

    python scripts/run_daily.py collect [--date YYYY-MM-DD] [--hours 26] [--limit-transcripts N]

Each step lives in its own try/except: a dead feed, a blocked YouTube IP or a failed transcript is
data, not an abort. The only fatal condition is being unable to write candidates.json at all,
because everything downstream reads it.

Steps: yt_source + news_source -> candidates.json -> memory filter -> transcripts -> images ->
packet.md -> one summary line.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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
    "lookback_hours": 26,
    "max_videos_per_channel": 3,
    "max_videos_total": 40,
    "max_news_items": 60,
    "transcript_max_chars": 24000,
    "repeat_topic_cooldown_days": 21,
}
MAX_IMAGES = 25
IMG_MAX_BYTES = 8 * 1024 * 1024
IMG_TIMEOUT = 15
NEWS_PER_SOURCE_CAP = 4
TRACKING = {"fbclid", "gclid", "ref", "referrer", "source", "mc_cid", "mc_eid", "igshid",
            "cmpid", "si", "feature", "spm", "s", "share", "at_medium", "at_campaign"}

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg)


def ascii_safe(text) -> str:
    s = str(text if text is not None else "")
    return s.encode("ascii", "replace").decode("ascii")


# ----------------------------------------------------------------- helpers

def project_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_settings(root: Path) -> dict:
    data = read_json(root / "config" / "settings.json", {})
    out = dict(DEFAULTS)
    if isinstance(data, dict):
        for key, default in DEFAULTS.items():
            val = data.get(key, default)
            out[key] = val if isinstance(val, (int, float)) and not isinstance(val, bool) else default
    return out


def iso(dt: datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def parse_dt(text) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def collapse(text) -> str:
    return re.sub(r"\s+", " ", str(text if text is not None else "")).strip()


def norm_title(title) -> str:
    s = collapse(title).lower()
    s = re.sub(r"^[^a-z0-9]+", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_url(url: str) -> str:
    try:
        parts = urlsplit(str(url or "").strip())
    except Exception:
        return str(url or "")
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING
    )
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    q = "&".join(k + "=" + v for k, v in query)
    return host + path + ("?" + q if q else "")


def sha16(text: str) -> str:
    return hashlib.sha1(str(text).encode("utf-8", "replace")).hexdigest()[:16]


def video_key(item: dict) -> str | None:
    vid = str(item.get("videoId") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        return "yt:" + vid
    m = re.search(r"(?:v=|/vi/|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})",
                  str(item.get("url") or ""))
    return "yt:" + m.group(1) if m else None


def run_step(cmd: list[str], root: Path, timeout: int = 600) -> tuple[int, str]:
    env = dict(__import__("os").environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return 124, "timeout after " + str(timeout) + "s"
    except Exception as exc:  # noqa: BLE001
        return 125, type(exc).__name__ + ": " + str(exc)[:200]
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


def tail_line(output: str) -> str:
    lines = [ln for ln in str(output or "").splitlines() if ln.strip()]
    return lines[-1].strip() if lines else ""


# ----------------------------------------------------------------- step 1: merge

def score_youtube(item: dict) -> float:
    tier = item.get("tier")
    if isinstance(tier, int) and tier in (1, 2, 3):
        return float(4 - tier)
    return 1.0


def merge_candidates(yt: list, news: list) -> list[dict]:
    merged: list[dict] = []
    by_key: dict[str, dict] = {}
    news_title_index: dict[str, dict] = {}
    news_url_index: dict[str, dict] = {}

    for raw in yt if isinstance(yt, list) else []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "") or video_key(raw)
        if not key:
            continue
        item = dict(raw)
        item["source"] = "youtube"
        item["kind"] = "video" if str(raw.get("kind") or "video") != "short" else "short"
        item["key"] = key
        item["title"] = collapse(raw.get("title"))
        item["score_hint"] = score_youtube(raw)
        item["tags"] = list(raw.get("tags") or [])
        item.setdefault("thumb_local", None)
        if key in by_key:
            continue
        by_key[key] = item
        merged.append(item)

    for raw in news if isinstance(news, list) else []:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url:
            continue
        weight = raw.get("weight")
        weight = int(weight) if isinstance(weight, int) else 1
        ntitle = norm_title(raw.get("title"))
        nurl = norm_url(url)
        source_name = str(raw.get("sourceName") or "").strip()

        loser = None
        for idx in (news_url_index.get(nurl), news_title_index.get(ntitle) if ntitle else None):
            if isinstance(idx, dict):
                loser = idx
                break
        if loser is not None:
            if weight > int(loser.get("weight") or 0):
                loser["also_on"] = list(loser.get("also_on") or [])
                if source_name and source_name != loser.get("sourceName") and source_name not in loser["also_on"]:
                    loser["also_on"].append(source_name)
                loser["weight"] = weight
                loser["score_hint"] = float(weight)
            else:
                also = list(loser.get("also_on") or [])
                if source_name and source_name != loser.get("sourceName") and source_name not in also:
                    also.append(source_name)
                loser["also_on"] = also
            continue

        item = dict(raw)
        item["source"] = "news"
        item["kind"] = "article"
        item["key"] = str(raw.get("key") or ("url:" + sha16(url)))
        item["title"] = collapse(raw.get("title"))
        item["weight"] = weight
        item["score_hint"] = float(weight)
        item["tags"] = list(raw.get("tags") or raw.get("feedTags") or [])
        item["feedTags"] = list(raw.get("feedTags") or item["tags"])
        item["also_on"] = list(raw.get("also_on") or [])
        item["summary"] = collapse(raw.get("summary"))[:600]
        item.setdefault("thumb_local", None)
        if item["key"] in by_key:
            continue
        by_key[item["key"]] = item
        merged.append(item)
        news_url_index[nurl] = item
        if ntitle:
            news_title_index[ntitle] = item

    return merged


def order_videos(items: list[dict], settings: dict) -> list[dict]:
    vids = [i for i in items if i.get("source") == "youtube"]
    vids.sort(key=lambda i: (
        i.get("tier") if isinstance(i.get("tier"), int) else 9,
        -((parse_dt(i.get("publishedAt")).timestamp()) if parse_dt(i.get("publishedAt")) else 0),
    ))
    per_channel: dict[str, int] = {}
    cap_channel = int(settings["max_videos_per_channel"])
    out = []
    for item in vids:
        ch = str(item.get("channelId") or item.get("channel") or "")
        if per_channel.get(ch, 0) >= cap_channel:
            continue
        per_channel[ch] = per_channel.get(ch, 0) + 1
        out.append(item)
    return out[: int(settings["max_videos_total"])]


def order_articles(items: list[dict], settings: dict) -> list[dict]:
    arts = [i for i in items if i.get("source") == "news"]
    arts.sort(key=lambda i: (
        -float(i.get("weight") or 0),
        -((parse_dt(i.get("publishedAt")).timestamp()) if parse_dt(i.get("publishedAt")) else 0),
    ))
    per_source: dict[str, int] = {}
    out = []
    for item in arts:
        src = str(item.get("sourceName") or "")
        if per_source.get(src, 0) >= NEWS_PER_SOURCE_CAP:
            continue
        per_source[src] = per_source.get(src, 0) + 1
        out.append(item)
    return out[: int(settings["max_news_items"])]


# ----------------------------------------------------------------- step 4: images

def image_ext(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def download_image(url: str, img_dir: Path) -> str | None:
    if requests is None or not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=IMG_TIMEOUT, stream=True)
        if resp.status_code != 200:
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
        ext = image_ext(data)
        if not ext:
            return None
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
        except Exception:
            return None
        name = sha16(url) + "." + ext
        path = img_dir / name
        path.write_bytes(data)
        return name
    except Exception:
        return None


def download_images(items: list[dict], root: Path, img_dir: Path) -> int:
    img_dir.mkdir(parents=True, exist_ok=True)
    targets = []
    for item in items:
        if len(targets) >= MAX_IMAGES:
            break
        url = item.get("image") or item.get("thumbnail")
        if not url:
            continue
        targets.append((item, str(url)))

    def work(pair):
        item, url = pair
        name = download_image(url, img_dir)
        if name:
            rel = (img_dir / name).relative_to(root).as_posix()
            item["thumb_local"] = rel
        return 1 if name else 0

    if not targets or requests is None:
        return 0
    ok = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(work, targets):
            ok += result
    return ok


# ----------------------------------------------------------------- step 5: packet

def transcript_index(out_dir: Path) -> dict:
    data = read_json(out_dir / "index.json", {})
    return data if isinstance(data, dict) else {}


def fmt_published(text) -> str:
    dt = parse_dt(text)
    if dt is None:
        return str(text or "unknown")[:19]
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def item_line(item: dict, tx: dict) -> str:
    title = collapse(item.get("title"))[:180]
    if item.get("source") == "youtube":
        tag = "T" + str(item.get("tier") if isinstance(item.get("tier"), int) else 9)
    else:
        tag = "w" + str(item.get("weight") or 0)
    vid = str(item.get("videoId") or "")
    entry = tx.get(vid) if vid else None
    has_tx = "yes" if isinstance(entry, dict) and entry.get("status") in ("ok", "cached") else "no"
    published = fmt_published(item.get("publishedAt"))
    return "- [" + tag + "] " + title + " | " + str(item.get("source")) + " | " + published + " | " + \
        str(item.get("url") or "") + " | transcript:" + has_tx


def build_packet(date: str, settings: dict, hours: int, filtered: dict, tx: dict,
                 counts: dict, suppressed_n: int, videos: list, articles: list,
                 recent_topics: list, errors: list[str]) -> str:
    now = iso(datetime.now().astimezone())
    lines = []
    lines.append("# DAILY BEACON - workpack " + date)
    lines.append(
        "generated " + now + " | lookback " + str(hours) + "h | "
        + str(counts["videos"]) + " videos, " + str(counts["articles"]) + " articles | "
        + str(suppressed_n) + " repeats suppressed"
    )
    lines.append("")
    lines.append("## counts")
    totals = filtered.get("counts") if isinstance(filtered.get("counts"), dict) else {}
    lines.append("- candidates total: " + str(totals.get("total", counts["total"])))
    lines.append("- unseen: " + str(counts["videos"] + counts["articles"])
                 + " (" + str(counts["videos"]) + " videos, " + str(counts["articles"]) + " articles)")
    lines.append("- repeats suppressed: " + str(suppressed_n))
    lines.append("- transcripts available: " + str(counts["transcripts"]))
    lines.append("- images downloaded: " + str(counts["images"]))
    if errors:
        lines.append("- step warnings: " + " ; ".join(collapse(e)[:140] for e in errors))
    lines.append("")
    lines.append("## top videos")
    if videos:
        for item in videos:
            lines.append(item_line(item, tx))
    else:
        lines.append("- (none in window)")
    lines.append("")
    lines.append("## top articles")
    if articles:
        for item in articles:
            lines.append(item_line(item, tx))
    else:
        lines.append("- (none in window)")
    lines.append("")
    lines.append("## cooling down")
    if recent_topics:
        shown = 0
        for topic in recent_topics[:20]:
            if not isinstance(topic, dict):
                continue
            lines.append(
                "- " + str(topic.get("topic")) + " | last " + str(topic.get("last_covered") or "?")
                + " | times " + str(topic.get("times") or 0)
            )
            shown += 1
        if not shown:
            lines.append("- (no topics recorded yet)")
    else:
        lines.append("- (no topics recorded yet)")
    lines.append("")
    lines.append("## next commands")
    lines.append("python scripts/build_edition.py --date " + date)
    lines.append("python scripts/memory.py mark --edition editions/" + date + ".json")
    lines.append("python scripts/publish.py --check")
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------- main

def cmd_collect(args) -> int:
    root = project_root(args.root)
    settings = load_settings(root)
    date = args.date or datetime.now().astimezone().strftime("%Y-%m-%d")
    hours = args.hours if args.hours else int(settings["lookback_hours"])
    wp = root / "state" / "workpack" / date
    wp.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    py = sys.executable or "python"

    # ---- step 1: producers -> candidates.json
    yt_path, news_path = wp / "yt.json", wp / "news.json"
    rc, out = run_step([py, "scripts/yt_source.py", "--out", str(yt_path), "--hours", str(hours)], root)
    yt_last = tail_line(out)
    log("step1 yt_source: " + (yt_last or ("exit " + str(rc))))
    if rc != 0:
        errors.append("yt_source exit " + str(rc))
    rc, out = run_step([py, "scripts/news_source.py", "--out", str(news_path), "--hours", str(hours)], root)
    news_last = tail_line(out)
    log("step1 news_source: " + (news_last or ("exit " + str(rc))))
    if rc != 0:
        errors.append("news_source exit " + str(rc))

    yt_data = read_json(yt_path, [])
    news_data = read_json(news_path, [])
    candidates = merge_candidates(yt_data, news_data)
    try:
        write_json(wp / "candidates.json", candidates)
    except Exception as exc:  # noqa: BLE001
        print("collect failed: cannot write candidates.json: " + ascii_safe(exc), file=sys.stderr)
        return 1
    log("step1 merged: " + str(len(candidates)) + " candidates -> candidates.json")

    # ---- step 2: memory filter
    filtered_path = wp / "filtered.json"
    suppressed_path = wp / "suppressed.json"
    filtered: dict = {}
    rc, out = run_step([
        py, "scripts/memory.py", "filter",
        "--candidates", str(wp / "candidates.json"),
        "--out", str(filtered_path),
        "--suppressed", str(suppressed_path),
    ], root, timeout=180)
    if rc == 0 and filtered_path.exists():
        filtered = read_json(filtered_path, {})
        if isinstance(filtered, list):
            filtered = {"items": filtered}
        log("step2 memory filter: " + (tail_line(out) or "ok"))
    else:
        errors.append("memory filter exit " + str(rc))
        log("step2 memory filter FAILED: " + (tail_line(out) or str(rc)))
        items = []
        for item in candidates:
            copy = dict(item)
            copy["seen"] = False
            copy["seen_reason"] = None
            copy["topic_hits"] = []
            items.append(copy)
        filtered = {
            "generatedAt": iso(datetime.now().astimezone()),
            "date": date,
            "cooldown_days": int(settings["repeat_topic_cooldown_days"]),
            "recent_topics": [],
            "counts": {"total": len(items), "seen": 0, "fresh": len(items)},
            "items": items,
        }
        write_json(filtered_path, filtered)

    items = filtered.get("items") if isinstance(filtered.get("items"), list) else []
    suppressed = read_json(suppressed_path, {})
    suppressed_items = suppressed.get("items") if isinstance(suppressed.get("items"), list) else []
    suppressed_n = len(suppressed_items)

    fresh = [i for i in items if isinstance(i, dict) and i.get("seen") is not True]
    videos = order_videos(fresh, settings)
    articles = order_articles(fresh, settings)

    # ---- step 3: transcripts
    tx_dir = wp / "transcripts"
    limit_default = min(12, int(settings["max_videos_total"]))
    limit_tx = args.limit_transcripts if args.limit_transcripts is not None else limit_default
    rc, out = run_step([
        py, "scripts/transcripts.py",
        "--candidates", str(filtered_path),
        "--out-dir", str(tx_dir),
        "--limit", str(limit_tx),
        "--root", str(root),
    ], root, timeout=3600)
    tx = transcript_index(tx_dir)
    tx_ok = sum(1 for v in tx.values() if isinstance(v, dict) and v.get("status") in ("ok", "cached"))
    if rc != 0:
        errors.append("transcripts exit " + str(rc))
    log("step3 transcripts: " + (tail_line(out) or ("exit " + str(rc))) + " -> " + str(tx_ok) + " available")

    # ---- step 4: images
    img_dir = wp / "img"
    img_ok = 0
    try:
        target_items = videos + articles
        target_items.sort(key=lambda i: (0 if i.get("source") == "youtube" else 1))
        img_ok = download_images(target_items, root, img_dir)
        write_json(filtered_path, filtered)
        log("step4 images: " + str(img_ok) + " downloaded -> img/")
    except Exception as exc:  # noqa: BLE001
        errors.append("images " + type(exc).__name__ + ": " + str(exc)[:120])
        log("step4 images: skipped (" + type(exc).__name__ + ")")

    # ---- step 5: packet.md
    counts = {
        "videos": len(videos),
        "articles": len(articles),
        "total": len(items),
        "transcripts": tx_ok,
        "images": img_ok,
    }
    packet = build_packet(
        date, settings, hours, filtered, tx, counts, suppressed_n,
        videos, articles, filtered.get("recent_topics") or [], errors,
    )
    try:
        write_text(wp / "packet.md", packet)
        log("step5 packet: " + str(wp / "packet.md"))
    except Exception as exc:  # noqa: BLE001
        errors.append("packet " + type(exc).__name__)
        log("step5 packet FAILED: " + type(exc).__name__)

    print(
        "collect done: " + str(len(videos)) + " videos, " + str(len(articles)) + " articles, "
        + str(tx_ok) + " transcripts, " + str(suppressed_n) + " repeats suppressed"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="run_daily.py",
        description="Daily Beacon orchestrator: producers -> filter -> transcripts -> images -> packet.",
    )
    ap.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    sub = ap.add_subparsers(dest="command")
    col = sub.add_parser("collect", help="run the whole morning collection into state/workpack/<date>/")
    col.add_argument("--date", default=None, help="workpack date YYYY-MM-DD (default: today)")
    col.add_argument("--hours", type=int, default=None, help="lookback hours (default: settings lookback_hours)")
    col.add_argument("--limit-transcripts", type=int, default=None,
                     help="cap transcripts (default: min(12, max_videos_total))")
    col.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    args = ap.parse_args()

    if args.command != "collect":
        ap.print_help()
        return 2
    return cmd_collect(args)


if __name__ == "__main__":
    raise SystemExit(main())