#!/usr/bin/env python3
"""transcripts.py - batch wrapper around %USERPROFILE%\.config\opencode\tools\yt_transcript.py.

Route: captions first. yt_transcript.py already tries youtube-transcript-api -> yt-dlp captions ->
site scrape -> audio ASR, but this wrapper always passes --no-asr: a 03:00 run must never download
audio and grind whisper for an hour. A video without captions is recorded as failed and the batch
moves on.

Cache: %USERPROFILE%\.config\opencode\notes\yt-cache is READ ONLY here. Any <videoId>.*.txt already
present (any language, nested) is copied into the out-dir and never refetched.

Sequential always: caption endpoints throttle per IP and the shared tool's ASR path is GPU bound.
One dead video is data, not a crash -> always exit 0.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_MAX_CHARS = 24000
DEFAULT_TIMEOUT = 180
MISSING_TIER = 9
ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
URL_ID_RE = re.compile(r"(?:v=|/vi/|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")

OPENCODE_HOME = Path.home() / ".config" / "opencode"
WRAPPER = OPENCODE_HOME / "tools" / "yt_transcript.py"
CACHE_DIR = OPENCODE_HOME / "notes" / "yt-cache"


def project_root(explicit=None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def read_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def load_settings(root: Path) -> dict:
    data = read_json(root / "config" / "settings.json", {})
    return data if isinstance(data, dict) else {}


def as_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def ascii_only(value, limit=None) -> str:
    text = " ".join(str(value if value is not None else "").split())
    text = text.encode("ascii", "replace").decode("ascii")
    if limit and len(text) > limit:
        text = text[: max(limit - 3, 0)] + "..."
    return text


def video_id_of(item: dict):
    vid = str(item.get("videoId") or "").strip()
    if ID_RE.fullmatch(vid):
        return vid
    match = URL_ID_RE.search(str(item.get("url") or ""))
    return match.group(1) if match else None


def tier_of(item: dict) -> int:
    tier = item.get("tier")
    if isinstance(tier, bool) or not isinstance(tier, (int, float)):
        return MISSING_TIER
    return int(tier)


def published_ts(item: dict) -> float:
    try:
        return datetime.fromisoformat(str(item.get("publishedAt") or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def trim_text(text: str, max_chars: int) -> str:
    """Head 60 percent + tail 40 percent: the setup survives and so does the verdict."""
    text = text.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head_len = int(max_chars * 0.6)
    tail_len = max_chars - head_len
    head = text[:head_len].rstrip()
    tail = text[-tail_len:].lstrip()
    removed = len(text) - len(head) - len(tail)
    if removed <= 0:
        return text
    return head + "\n[... trimmed " + str(removed) + " chars ...]\n" + tail


def cached_text(video_id: str):
    """Read only. Empty cache dir (or no hit) -> None, and the fetcher runs."""
    if not CACHE_DIR.is_dir():
        return None
    try:
        matches = sorted(CACHE_DIR.rglob(video_id + "*.txt"),
                         key=lambda p: (0 if ".en." in p.name else 1, -p.stat().st_size))
    except OSError:
        return None
    for path in matches:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            return text
    return None


def run_wrapper(video_id: str, work_dir: Path, timeout: int):
    if not WRAPPER.is_file():
        return None, ascii_only("tool missing: " + str(WRAPPER), 200)
    cmd = [sys.executable, str(WRAPPER), "--out", str(work_dir), "--no-asr", "--lang", "en", "--", video_id]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", cwd=str(work_dir), timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout after " + str(int(timeout)) + "s"
    except OSError as exc:
        return None, ascii_only("could not start tool: " + str(exc), 200)

    produced = None
    for line in reversed((res.stdout or "").splitlines()):
        if line.startswith("TXT "):
            candidate = Path(line[4:].strip())
            if candidate.is_file():
                produced = candidate
                break
    if produced is None:
        try:
            for candidate in sorted(work_dir.glob(video_id + "*.txt"),
                                    key=lambda p: p.stat().st_size, reverse=True):
                if candidate.is_file() and candidate.stat().st_size > 0:
                    produced = candidate
                    break
        except OSError:
            produced = None
    if res.returncode == 0 and produced is not None:
        return produced, None

    lines = [ln.strip() for ln in ((res.stdout or "") + "\n" + (res.stderr or "")).splitlines() if ln.strip()]
    keys = [ln for ln in lines if ln.startswith(("NO TRANSCRIPT", "ASR FAILED", "FAILED", "last:", "! ", "no caption"))]
    detail = " | ".join(keys[-2:] or lines[-2:]) or "no output"
    prefix = {1: "fetch failed", 2: "no transcript"}.get(res.returncode, "exit " + str(res.returncode))
    return None, ascii_only(prefix + ": " + detail, 200)


def handle_video(video_id: str, out_dir: Path, temp_root: Path, max_chars: int, timeout: int):
    cached = cached_text(video_id)
    if cached is not None:
        body = trim_text(cached, max_chars)
        (out_dir / (video_id + ".txt")).write_text(body + "\n", encoding="utf-8", newline="\n")
        return "cached", len(body), None

    temp_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="tr-" + video_id + "-", dir=str(temp_root)))
    try:
        produced, reason = run_wrapper(video_id, work_dir, timeout)
        if produced is None:
            return "failed", 0, reason
        text = produced.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return "failed", 0, "empty transcript file"
        body = trim_text(text, max_chars)
        (out_dir / (video_id + ".txt")).write_text(body + "\n", encoding="utf-8", newline="\n")
        return "ok", len(body), None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def select_video_ids(items: list, limit: int):
    videos = [it for it in items if isinstance(it, dict)
              and it.get("kind") == "video" and it.get("seen") is not True and video_id_of(it)]
    videos.sort(key=published_ts, reverse=True)
    videos.sort(key=tier_of)
    picked, seen = [], set()
    for item in videos:
        vid = video_id_of(item)
        if vid in seen:
            continue
        seen.add(vid)
        picked.append(vid)
        if limit and limit > 0 and len(picked) >= limit:
            break
    return picked


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="transcripts.py",
        description="Batch, cache-first, sequential transcript fetcher (captions only, no ASR).")
    ap.add_argument("--candidates", default=None, help="filtered.json (array, or object with an 'items' array)")
    ap.add_argument("--ids", default=None, help="comma separated videoIds; overrides --candidates")
    ap.add_argument("--out-dir", default=None,
                    help="where <videoId>.txt and index.json go (default state/workpack/<date>/transcripts)")
    ap.add_argument("--date", default=None, help="workpack date for the default out-dir (YYYY-MM-DD)")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of videos")
    ap.add_argument("--max-chars", type=int, default=None,
                    help="per transcript cap (default: settings transcript_max_chars)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help="per-video timeout in seconds (default: " + str(DEFAULT_TIMEOUT) + ")")
    ap.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root(args.root)
    settings = load_settings(root)
    date = args.date or datetime.now().astimezone().strftime("%Y-%m-%d")

    max_chars = args.max_chars if args.max_chars is not None \
        else as_int(settings.get("transcript_max_chars"), DEFAULT_MAX_CHARS)
    if max_chars <= 0:
        max_chars = DEFAULT_MAX_CHARS
    timeout = args.timeout if args.timeout and args.timeout > 0 else DEFAULT_TIMEOUT
    limit = args.limit if args.limit is not None else min(12, as_int(settings.get("max_videos_total"), 40))

    if args.ids:
        video_ids = []
        for raw in str(args.ids).split(","):
            vid = raw.strip()
            if ID_RE.fullmatch(vid):
                video_ids.append(vid)
            elif vid:
                print("transcripts: ignoring bad id " + ascii_only(vid, 40), file=sys.stderr)
        if limit and limit > 0:
            video_ids = video_ids[:limit]
    else:
        if not args.candidates:
            print("transcripts: --candidates is required unless --ids is given", file=sys.stderr)
            print("transcripts done: 0 fetched, 0 cached, 0 failed")
            return 0
        data = read_json(args.candidates, None)
        if data is None:
            print("transcripts: cannot read candidates file: " + str(args.candidates), file=sys.stderr)
            print("transcripts done: 0 fetched, 0 cached, 0 failed")
            return 0
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            print("transcripts: no item array in " + str(args.candidates), file=sys.stderr)
            print("transcripts done: 0 fetched, 0 cached, 0 failed")
            return 0
        video_ids = select_video_ids(items, limit)

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else root / "state" / "workpack" / date / "transcripts"
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_root = root / "state" / "tmp"

    index = {}
    counts = {"ok": 0, "cached": 0, "failed": 0}
    total = len(video_ids)

    for position, video_id in enumerate(video_ids, 1):
        status, chars, reason = handle_video(video_id, out_dir, temp_root, max_chars, timeout)
        counts[status] += 1
        index[video_id] = {"status": status, "chars": chars, "reason": reason}
        suffix = " - " + reason if reason else ""
        print("[" + str(position) + "/" + str(total) + "] " + video_id + " " + status + " "
              + str(chars) + " chars" + suffix)

    (out_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=True) + "\n",
                                        encoding="utf-8", newline="\n")
    print("transcripts done: " + str(counts["ok"]) + " fetched, " + str(counts["cached"])
          + " cached, " + str(counts["failed"]) + " failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())