#!/usr/bin/env python3
"""transcripts.py - batch, cache-first, sequential transcript fetching.

The 03:00 agent judges a video by what is SAID in it, so every video needs a transcript on disk
before the packet is written. This script only orchestrates that:

  cache first  - notes/yt-cache/<videoId>*.txt is shared with every other tool. A hit is copied and
                 the fetcher is never called, so a video seen yesterday costs nothing today.
  sequential   - the ASR fallback is GPU bound. Videos are handled one at a time, never in parallel.
  failure is data - one dead/blocked/captionless video must never abort the batch. It lands in
                 index.json with a reason and the run still exits 0.

Fetching itself belongs to tools/yt_transcript.py (captions -> yt-dlp -> third-party site -> audio
ASR). Reimplementing those routes here would fork behaviour; this file treats it as a black box and
reads the "TXT <path>" line it prints.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
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
DEFAULT_LIMIT_CAP = 12
DEFAULT_TIMEOUT = 180
MISSING_TIER = 9
REASON_LIMIT = 200

OPENCODE_HOME = Path.home() / ".config" / "opencode"
WRAPPER = OPENCODE_HOME / "tools" / "yt_transcript.py"
CACHE_DIR = OPENCODE_HOME / "notes" / "yt-cache"

ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
URL_ID_RE = re.compile(r"(?:v=|/vi/|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


# --------------------------------------------------------------------------- plumbing

def project_root(explicit: str | None = None) -> Path:
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


def as_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def ascii_only(value, limit: int | None = None) -> str:
    """Console and index.json stay ASCII: Windows consoles choke on the rest."""
    text = " ".join(str(value or "").split())
    text = text.encode("ascii", "replace").decode("ascii")
    if limit and len(text) > limit:
        text = text[: max(limit - 3, 0)] + "..."
    return text


# --------------------------------------------------------------------------- selection

def video_id_of(item: dict) -> str | None:
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
    raw = str(item.get("publishedAt") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def select_video_ids(items: list, limit: int) -> list[str]:
    videos = [
        it for it in items
        if isinstance(it, dict)
        and it.get("kind") == "video"
        and it.get("seen") is not True
        and video_id_of(it)
    ]
    # two stable passes: newest first, then tier ascending -> (tier asc, publishedAt desc)
    videos.sort(key=published_ts, reverse=True)
    videos.sort(key=tier_of)

    picked, seen = [], set()
    for item in videos:
        vid = video_id_of(item)
        if vid in seen:
            continue
        seen.add(vid)
        picked.append(vid)
    return picked[:limit] if limit > 0 else picked


def parse_ids(raw: str) -> list[str]:
    ids, seen = [], set()
    for part in str(raw or "").split(","):
        vid = part.strip()
        if not vid:
            continue
        if not ID_RE.fullmatch(vid):
            print(f"! skipped invalid id '{ascii_only(vid, 40)}'")
            continue
        if vid in seen:
            continue
        seen.add(vid)
        ids.append(vid)
    return ids


def resolve_limit(explicit, settings: dict) -> int:
    if explicit is not None:
        return as_int(explicit, DEFAULT_LIMIT_CAP)
    total = as_int(settings.get("max_videos_total"), DEFAULT_LIMIT_CAP)
    if total <= 0:
        return DEFAULT_LIMIT_CAP
    return min(DEFAULT_LIMIT_CAP, total)


# --------------------------------------------------------------------------- cache / trim

def cached_text(video_id: str) -> str | None:
    """Cache is shared with every other tool: read, never modify, never delete."""
    try:
        matches = sorted(CACHE_DIR.glob(f"{video_id}*.txt"),
                         key=lambda p: p.stat().st_size, reverse=True)
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


def trim_text(text: str, max_chars: int) -> str:
    """Head + tail kept, so the intro (what the video is) and the outro (the verdict) survive."""
    text = text.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head_len = max_chars // 2
    tail_len = max_chars - head_len
    removed = len(text) - head_len - tail_len
    marker = f"\n[... trimmed {removed} chars ...]\n"
    return text[:head_len].rstrip() + marker + text[-tail_len:].lstrip()


# --------------------------------------------------------------------------- fetching

def parse_txt_path(stdout: str, work_dir: Path, video_id: str) -> Path | None:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith("TXT "):
            path = Path(line[4:].strip())
            if path.is_file():
                return path
    try:
        candidates = sorted(work_dir.glob(f"{video_id}*.txt"),
                            key=lambda p: p.stat().st_size, reverse=True)
    except OSError:
        return None
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            continue
    return None


def describe_failure(returncode: int, output: str) -> str:
    lines = [ln.strip() for ln in (output or "").splitlines() if ln.strip()]
    key_lines = [ln for ln in lines
                 if ln.startswith(("NO TRANSCRIPT", "ASR FAILED", "FAILED", "last:", "! "))]
    picked = key_lines[-2:] or lines[-2:]
    detail = " | ".join(picked) or "no output"
    prefix = {1: "fetch failed", 2: "no transcript"}.get(returncode, f"exit {returncode}")
    return ascii_only(f"{prefix}: {detail}", REASON_LIMIT)


def run_wrapper(video_id: str, work_dir: Path, timeout: int) -> tuple[Path | None, str | None]:
    if not WRAPPER.is_file():
        return None, ascii_only(f"tool missing: {WRAPPER}", REASON_LIMIT)
    cmd = [sys.executable, str(WRAPPER), video_id, "--out", str(work_dir)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", cwd=str(work_dir), timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, ascii_only(f"timeout after {int(timeout)}s", REASON_LIMIT)
    except OSError as exc:
        return None, ascii_only(f"could not start tool: {exc}", REASON_LIMIT)

    produced = parse_txt_path(res.stdout or "", work_dir, video_id)
    if res.returncode == 0 and produced is not None:
        return produced, None
    return None, describe_failure(res.returncode, (res.stdout or "") + "\n" + (res.stderr or ""))


def store_fetched(produced: Path) -> None:
    """Keep the fetched file in the shared cache so tonight's work is free tomorrow."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / produced.name
    # an existing non-empty cache entry is never touched; a zero-byte one is worth replacing
    if target.exists() and target.stat().st_size > 0:
        return
    shutil.copyfile(produced, target)


def write_transcript(out_dir: Path, video_id: str, text: str, max_chars: int) -> str:
    trimmed = trim_text(text, max_chars)
    (out_dir / f"{video_id}.txt").write_text(trimmed + "\n", encoding="utf-8")
    return trimmed


def handle_video(video_id: str, out_dir: Path, temp_root: Path,
                 max_chars: int, timeout: int) -> tuple[str, int, str | None]:
    cached = cached_text(video_id)
    if cached is not None:
        trimmed = write_transcript(out_dir, video_id, cached, max_chars)
        return "cached", len(trimmed), None

    temp_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=f"tr-{video_id}-", dir=str(temp_root)))
    try:
        produced, reason = run_wrapper(video_id, work_dir, timeout)
        if produced is None:
            return "failed", 0, reason
        text = produced.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return "failed", 0, "empty transcript file"
        try:
            store_fetched(produced)
        except OSError as exc:
            print(f"! cache write skipped for {video_id}: {ascii_only(exc, 80)}")
        trimmed = write_transcript(out_dir, video_id, text, max_chars)
        return "ok", len(trimmed), None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# --------------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="transcripts.py",
        description="Batch, cache-first, sequential transcript fetcher for the daily workpack.")
    ap.add_argument("--candidates", default=None,
                    help="filtered.json (array, or object with an 'items' array)")
    ap.add_argument("--out-dir", required=True,
                    help="where <videoId>.txt and index.json are written")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the number of videos (default: min(12, max_videos_total))")
    ap.add_argument("--ids", default=None,
                    help="comma separated videoIds; overrides --candidates entirely")
    ap.add_argument("--max-chars", type=int, default=None,
                    help="per transcript cap (default: settings transcript_max_chars)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help=f"per-video timeout in seconds (default: {DEFAULT_TIMEOUT})")
    ap.add_argument("--root", default=None,
                    help="project root (default: parent of scripts/)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root(args.root)
    settings = load_settings(root)

    max_chars = args.max_chars if args.max_chars is not None \
        else as_int(settings.get("transcript_max_chars"), DEFAULT_MAX_CHARS)
    if max_chars <= 0:
        max_chars = DEFAULT_MAX_CHARS
    timeout = args.timeout if args.timeout and args.timeout > 0 else DEFAULT_TIMEOUT
    limit = resolve_limit(args.limit, settings)

    if args.ids:
        video_ids = parse_ids(args.ids)
        if limit > 0:
            video_ids = video_ids[:limit]
    else:
        if not args.candidates:
            print("transcripts: --candidates is required unless --ids is given", file=sys.stderr)
            return 2
        data = read_json(args.candidates, None)
        if data is None:
            print(f"transcripts: cannot read candidates file: {args.candidates}", file=sys.stderr)
            return 2
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            print(f"transcripts: no item array in {args.candidates}", file=sys.stderr)
            return 2
        video_ids = select_video_ids(items, limit)

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_root = root / "state" / "tmp"

    index: dict[str, dict] = {}
    counts = {"ok": 0, "cached": 0, "failed": 0}
    total = len(video_ids)

    for position, video_id in enumerate(video_ids, 1):
        status, chars, reason = handle_video(video_id, out_dir, temp_root, max_chars, timeout)
        counts[status] += 1
        index[video_id] = {"status": status, "chars": chars, "reason": reason}
        suffix = f" - {reason}" if reason else ""
        print(f"[{position}/{total}] {video_id} {status} {chars} chars{suffix}")

    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print(f"transcripts done: {counts['ok']} fetched, {counts['cached']} cached, "
          f"{counts['failed']} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())