#!/usr/bin/env python3
"""build_edition.py - turn editions/YYYY-MM-DD.json into the Daily Beacon static site.

Pipeline
--------
1. load + validate the edition JSON against the schema in docs/SPEC.md section 6
2. resolve every image (download remote / read local), optimise to JPEG q82 max width 1400
3. render one HTML document per edition (index.html + a dated archive snapshot)
4. rebuild site/archive.html from the snapshots on disk
5. self-check the generated HTML (tag balance, anchors, alt text, size)

Exit codes: 0 success, 1 validation/build failure, 2 usage error.

Console output is ASCII only; every file is opened with an explicit UTF-8 encoding.
Nothing here opens a browser, a window or a network call outside image downloads.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Any

# Optional third-party imports. The script degrades to a clear error instead of a traceback.
try:  # pragma: no cover - environment dependent
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore[assignment]

try:  # pragma: no cover - environment dependent
    from PIL import Image, ImageDraw
except Exception:  # noqa: BLE001
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EDITION_DIR = ROOT / "editions"
SITE_DIR = ROOT / "site"
SETTINGS_PATH = ROOT / "config" / "settings.json"
FIXTURE_DIR = ROOT / "state" / "workpack" / "_fixture"
FIXTURE_IMG_DIR = FIXTURE_DIR / "img"

# Accent keys and the exact seed formulas are fixed by docs/SITE-CONTRACT.md section 3.
ACCENTS = ["amber", "coral", "rose", "sage", "teal", "sky", "gold", "clay"]
LAYOUTS = ["hero-left", "hero-centre", "hero-stacked"]

KINDS = ("lead", "story", "video", "quick", "quote")
REQUIRED_TOP_KEYS = ("date", "number", "generatedAt", "masthead", "tagline", "sections")

# HTML elements that never take a closing tag.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

DEFAULT_SETTINGS = {
    "edition_min_stories": 5,
    "edition_max_stories": 14,
    "keep_editions": 30,
    "site_base_url": "",
}

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TIMEOUT = 25
IMAGE_MAX_WIDTH = 1400
IMAGE_QUALITY = 82
MAX_HTML_BYTES = 3 * 1024 * 1024
DARK_BACKDROP = (0x0B, 0x0B, 0x0D)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

ID_RE = re.compile(r"^[a-z0-9-]+$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINK_INLINE_RE = re.compile(r"\[([^\[\]]+)\]\(([^()\s]*)\)")


# ---------------------------------------------------------------------------
# console helpers
# ---------------------------------------------------------------------------

def say(message: str) -> None:
    """Print one line, forced to ASCII so a cp1252 console never dies."""
    text = message.encode("ascii", "replace").decode("ascii")
    print(text, flush=True)


def warn(message: str) -> None:
    say("warning: " + message)


def fail(message: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    say("error: " + message)
    raise SystemExit(code)


def reconfigure_stdout() -> None:
    """Best-effort UTF-8 stdout; guarded because sys.stdout can be None in a frozen exe."""
    stream = sys.stdout
    if stream is None:
        return
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

def sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def slugify(value: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    slug = slug[:limit].strip("-")
    return slug or "image"


def esc(value: Any) -> str:
    """Escape a value for HTML text/attribute context."""
    return html.escape("" if value is None else str(value), quote=True)


def plain(value: Any) -> str:
    """Drop inline markup markers, returning readable plain text."""
    text = "" if value is None else str(value)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = LINK_INLINE_RE.sub(r"\1", text)
    return text.strip()


def truncate_str(text: Any, limit: int) -> str:
    value = plain(text).replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _human_date_portable(d: _date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')} {d.year}"


def human_date(iso_date: str) -> str:
    """2026-10-28 -> 'Wednesday 28 October 2026'."""
    try:
        return _human_date_portable(datetime.strptime(iso_date, "%Y-%m-%d").date())
    except ValueError:
        return iso_date


def human_timestamp(value: str) -> str:
    """ISO timestamp -> '28 October 2026, 03:14' (falls back to the raw string)."""
    if not value:
        return ""
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return f"{stamp.day} {stamp.strftime('%B')} {stamp.year}, {stamp.strftime('%H:%M')}"


def seed_for(iso_date: str) -> int:
    digits = re.sub(r"\D", "", iso_date)
    return int(digits) if digits else 0


def seed_variants(iso_date: str) -> dict[str, str]:
    """Deterministic per-date design variant, exactly as SITE-CONTRACT section 3 prescribes."""
    seed = seed_for(iso_date)
    return {
        "seed": str(seed),
        "accent": ACCENTS[seed % 8],
        "layout": LAYOUTS[(seed // 7) % 3],
        "scale": "a" if (seed // 11) % 2 == 0 else "b",
        "order": "lead" if (seed // 13) % 2 == 0 else "rail",
    }


def load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            settings.update(loaded)
    except Exception:  # noqa: BLE001 - settings are advisory, defaults keep the build alive
        pass
    return settings


def file_version(path: Path) -> str:
    """sha1[:8] of a static asset, 'dev' when the other worker has not written it yet."""
    try:
        return sha1_hex(path.read_bytes())[:8]
    except Exception:  # noqa: BLE001
        return "dev"


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)

# ---------------------------------------------------------------------------
# inline markup: **bold**, *italic*, [text](url)
# ---------------------------------------------------------------------------

MARKUP_URL_OK = re.compile(r"^(?:https?://|\.{0,2}/|#)", re.IGNORECASE)


def sanitise_url(raw: str) -> str | None:
    """Return a safe href, or None when the URL scheme is not allowed."""
    candidate = (raw or "").strip()
    if not candidate:
        return None
    # Control characters and whitespace inside a URL are never legitimate here.
    if any(ch in candidate for ch in ("\n", "\r", "\t", " ")):
        return None
    if MARKUP_URL_OK.match(candidate):
        return candidate
    return None


def render_inline(text: Any) -> str:
    """Escape every byte of HTML first, then layer the three allowed inline markers on top.

    Because escaping happens first, no user-supplied angle bracket can ever become a tag, and
    the regexes below can only match the literal marker characters we introduce ourselves.
    """
    safe = esc(text)

    def _link(match: re.Match[str]) -> str:
        label, href = match.group(1), match.group(2)
        clean = sanitise_url(html.unescape(href))
        if clean is None:
            # Unsafe scheme: keep the words, drop the link. Never emit the bad URL.
            return label
        return f'<a href="{esc(clean)}" rel="noopener">{label}</a>'

    safe = LINK_INLINE_RE.sub(_link, safe)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
    safe = re.sub(r"\*(.+?)\*", r"<em>\1</em>", safe)
    return safe


def render_paragraphs(body: Any) -> str:
    """Body may be a list of paragraphs or a single string; each paragraph becomes a <p>."""
    if body is None:
        return ""
    items = body if isinstance(body, list) else [body]
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        out.append(f"      <p>{render_inline(text)}</p>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class Report:
    """Collects violations with their JSON path so --check can print all of them at once."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []

    def error(self, path: str, message: str) -> None:
        self.errors.append((path, message))

    def warn(self, path: str, message: str) -> None:
        self.warnings.append((path, message))

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_inline(report: Report, path: str, text: Any) -> None:
    """Reject stray '<', unbalanced brackets and unclosed emphasis markers."""
    if text is None:
        return
    value = str(text)
    if "<" in value or ">" in value:
        report.error(path, "raw angle bracket in text (HTML is escaped, use no tags at all)")
    if value.count("**") % 2 != 0:
        report.error(path, "unclosed '**' emphasis")
    if value.replace("**", "").count("*") % 2 != 0:
        report.error(path, "unclosed '*' emphasis")
    if value.count("[") != value.count("]"):
        report.error(path, "unbalanced square brackets")
    if value.count("(") != value.count(")"):
        report.error(path, "unbalanced parentheses")
    for match in LINK_INLINE_RE.finditer(value):
        href = match.group(2).strip()
        if sanitise_url(href) is None:
            report.error(path, f"disallowed link target '{truncate_str(href, 40)}' (http/https/relative only)")


def _check_body(report: Report, path: str, body: Any) -> int:
    if body is None:
        return 0
    items = body if isinstance(body, list) else [body]
    texts = [str(x).strip() for x in items if x is not None and str(x).strip()]
    for index, text in enumerate(texts):
        _check_inline(report, f"{path}[{index}]", text)
    return len(texts)


def _check_source(report: Report, path: str, source: Any, required: bool) -> None:
    if not isinstance(source, dict):
        if required:
            report.error(path, "missing source object with label + url")
        return
    label = str(source.get("label") or "").strip()
    url = str(source.get("url") or "").strip()
    if required and not label:
        report.error(f"{path}.label", "empty source label")
    if required and not url:
        report.error(f"{path}.url", "empty source url")
    if url and sanitise_url(url) is None:
        report.error(f"{path}.url", f"source url '{truncate_str(url, 50)}' is not http(s)")


def _check_image(report: Report, path: str, image: Any, edition_dir: Path) -> None:
    if image is None:
        return
    if not isinstance(image, dict):
        report.error(path, "image must be an object with src + alt")
        return
    src = str(image.get("src") or "").strip()
    if not src:
        report.error(f"{path}.src", "empty image src")
    alt = image.get("alt")
    if alt is None or not str(alt).strip():
        report.error(f"{path}.alt", "missing alt text (mandatory)")
    if src:
        if re.match(r"^https?://", src, re.IGNORECASE):
            pass
        else:
            local = Path(src)
            if not local.is_absolute():
                local = (edition_dir / local)
            if not local.exists():
                report.error(f"{path}.src", f"local image not found: {src}")


def validate_edition(edition: Any, edition_path: Path, settings: dict[str, Any]) -> Report:
    """Full schema validation. Returns a Report; the caller decides whether to abort."""
    report = Report()
    if not isinstance(edition, dict):
        report.error("$", "edition root must be a JSON object")
        return report

    for key in REQUIRED_TOP_KEYS:
        if key not in edition:
            report.error(f"$.{key}", "required key missing")

    iso = str(edition.get("date") or "")
    if not ISO_DATE_RE.match(iso):
        report.error("$.date", "date must be YYYY-MM-DD")
    else:
        if edition_path.stem != iso:
            report.error("$.date", f"date '{iso}' does not match filename '{edition_path.stem}'")
        try:
            datetime.strptime(iso, "%Y-%m-%d")
        except ValueError:
            report.error("$.date", "date is not a real calendar date")

    number = edition.get("number")
    if not isinstance(number, int) or number < 1:
        report.error("$.number", "number must be a positive integer")

    for key in ("masthead", "tagline"):
        if not str(edition.get(key) or "").strip():
            report.error(f"$.{key}", "must be a non-empty string")

    if "generatedAt" in edition:
        try:
            datetime.fromisoformat(str(edition.get("generatedAt")).replace("Z", "+00:00"))
        except ValueError:
            report.error("$.generatedAt", "not an ISO 8601 timestamp")

    if "weatherStrip" in edition:
        _check_inline(report, "$.weatherStrip", edition.get("weatherStrip"))
    if "signoff" in edition:
        _check_inline(report, "$.signoff", edition.get("signoff"))

    sections = edition.get("sections")
    if not isinstance(sections, list) or not sections:
        report.error("$.sections", "must be a non-empty array")
        return report

    seen_ids: set[str] = set()
    lead_count = 0
    counted = 0
    edition_dir = edition_path.parent

    for index, section in enumerate(sections):
        base = f"$.sections[{index}]"
        if not isinstance(section, dict):
            report.error(base, "section must be an object")
            continue

        raw_id = str(section.get("id") or "")
        if not raw_id:
            report.error(f"{base}.id", "missing id")
        elif not ID_RE.match(raw_id):
            report.error(f"{base}.id", f"id '{raw_id}' must match [a-z0-9-]+")
        elif raw_id in seen_ids:
            report.error(f"{base}.id", f"duplicate id '{raw_id}'")
        else:
            seen_ids.add(raw_id)

        kind = str(section.get("kind") or "")
        if kind not in KINDS:
            report.error(f"{base}.kind", f"kind '{kind}' not one of {', '.join(KINDS)}")
        if kind == "lead":
            lead_count += 1
        if kind in ("lead", "story", "video"):
            counted += 1

        if not str(section.get("kicker") or "").strip():
            report.error(f"{base}.kicker", "missing kicker")
        else:
            _check_inline(report, f"{base}.kicker", section.get("kicker"))

        headline = str(section.get("headline") or "").strip()
        if not headline:
            report.error(f"{base}.headline", "missing headline")
        else:
            _check_inline(report, f"{base}.headline", headline)

        for field in ("standfirst", "whyItMatters", "aside"):
            if section.get(field) is not None:
                _check_inline(report, f"{base}.{field}", section.get(field))

        body_paragraphs = _check_body(report, f"{base}.body", section.get("body"))
        if kind == "quote":
            if body_paragraphs == 0 and not headline:
                report.error(f"{base}.body", "quote needs a quote line (body) or a headline")
        elif kind != "quick":
            if body_paragraphs == 0:
                report.error(f"{base}.body", "non-empty body required")

        _check_source(report, f"{base}.source", section.get("source"), required=kind != "quick")
        _check_image(report, f"{base}.image", section.get("image"), edition_dir)

        tags = section.get("tags")
        if tags is not None and not isinstance(tags, list):
            report.error(f"{base}.tags", "tags must be an array")

    # exactly one lead; zero is repairable, two is a hard failure
    if lead_count > 1:
        report.error("$.sections", f"{lead_count} sections of kind 'lead' (exactly one allowed)")
    elif lead_count == 0:
        report.warn("$.sections", "no 'lead' section; the highest-priority section will be promoted")

    quick_hits = edition.get("quickHits")
    if quick_hits is not None:
        if not isinstance(quick_hits, list):
            report.error("$.quickHits", "must be an array")
        else:
            for index, hit in enumerate(quick_hits):
                base = f"$.quickHits[{index}]"
                if isinstance(hit, dict):
                    if not str(hit.get("text") or "").strip():
                        report.error(f"{base}.text", "missing text")
                    else:
                        _check_inline(report, f"{base}.text", hit.get("text"))
                    url = str(hit.get("url") or "").strip()
                    if url and sanitise_url(url) is None:
                        report.error(f"{base}.url", "url must be http(s)")
                elif isinstance(hit, str):
                    _check_inline(report, base, hit)
                else:
                    report.error(base, "quick hit must be a string or {text,url}")

    minimum = int(settings.get("edition_min_stories", 5) or 5)
    maximum = int(settings.get("edition_max_stories", 14) or 14)
    if counted < minimum:
        report.warn("$.sections", f"{counted} stories, below edition_min_stories={minimum}")
    elif counted > maximum:
        report.warn("$.sections", f"{counted} stories, above edition_max_stories={maximum}")

    return report

# ---------------------------------------------------------------------------
# lead promotion + section ordering
# ---------------------------------------------------------------------------

def promote_lead(edition: dict[str, Any]) -> bool:
    """If no section is a lead, promote the highest-priority one. Returns True when it changed."""
    sections = edition.get("sections") or []
    if any(str(s.get("kind")) == "lead" for s in sections if isinstance(s, dict)):
        return False
    candidates = [s for s in sections if isinstance(s, dict) and str(s.get("kind")) in ("story", "video")]
    if not candidates:
        return False
    best = max(candidates, key=lambda s: (int(s.get("priority") or 0)))
    best["kind"] = "lead"
    return True


def order_sections(edition: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Split the lead out and sort the remainder so the reading order is stable per edition.

    The JSON `order` field wins when present; otherwise priority descending, then declaration order.
    """
    sections = [s for s in (edition.get("sections") or []) if isinstance(s, dict)]
    lead = next((s for s in sections if str(s.get("kind")) == "lead"), None)
    rest = [s for s in sections if s is not lead]

    def key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, section = item
        explicit = section.get("order")
        if isinstance(explicit, int):
            return (0, explicit, index)
        return (1, -int(section.get("priority") or 0), index)

    ordered = [s for _, s in sorted(enumerate(rest), key=key)]
    return lead, ordered


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------

class ImageBudget:
    """Resolves each image exactly once per build, caching by source string."""

    def __init__(self, out_dir: Path, iso_date: str) -> None:
        self.out_dir = out_dir
        self.asset_dir = out_dir / "assets" / iso_date
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.cache: dict[str, dict[str, Any] | None] = {}
        self.count = 0
        self.failures = 0

    def resolve(self, src: str, edition_dir: Path) -> dict[str, Any] | None:
        key = str(src or "").strip()
        if not key:
            return None
        if key in self.cache:
            return self.cache[key]
        try:
            resolved = self._resolve(key, edition_dir)
        except Exception as exc:  # noqa: BLE001 - one bad image never kills a build
            say(f"image skipped: {truncate_str(key, 60)} ({type(exc).__name__})")
            self.failures += 1
            resolved = None
        self.cache[key] = resolved
        if resolved:
            self.count += 1
        return resolved

    # -- internals ---------------------------------------------------------

    def _fetch(self, url: str) -> tuple[bytes, str]:
        if requests is None:
            raise RuntimeError("requests is not installed")
        response = requests.get(
            url,
            timeout=IMAGE_TIMEOUT,
            headers={"User-Agent": BROWSER_UA, "Accept": "image/*,*/*;q=0.8"},
            stream=True,
        )
        response.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise ValueError("image larger than 8 MB")
            chunks.append(chunk)
        return b"".join(chunks), url

    def _optimise(self, raw: bytes, slug: str) -> dict[str, Any]:
        if Image is None:
            raise RuntimeError("Pillow is not installed")
        import io

        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            image = _to_rgb(image)
            width, height = image.size
            if width > IMAGE_MAX_WIDTH:
                ratio = IMAGE_MAX_WIDTH / float(width)
                image = image.resize((IMAGE_MAX_WIDTH, max(1, int(round(height * ratio)))), Image.LANCZOS)
                width, height = image.size
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=IMAGE_QUALITY, optimize=True, progressive=True)
            payload = buffer.getvalue()

        filename = f"{slug}-{sha1_hex(payload)[:8]}.jpg"
        target = self.asset_dir / filename
        if not target.exists():
            with open(target, "wb") as handle:
                handle.write(payload)
        return {"file": filename, "width": width, "height": height}

    def _resolve(self, src: str, edition_dir: Path) -> dict[str, Any] | None:
        if re.match(r"^https?://", src, re.IGNORECASE):
            raw, _ = self._fetch(src)
        else:
            local = Path(src)
            if not local.is_absolute():
                local = edition_dir / local
            if not local.exists():
                say(f"image skipped: missing local file {truncate_str(str(src), 60)}")
                self.failures += 1
                return None
            raw = local.read_bytes()
            if len(raw) > MAX_IMAGE_BYTES:
                say(f"image skipped: {truncate_str(str(src), 60)} is larger than 8 MB")
                self.failures += 1
                return None
        slug = slugify(Path(src.split("?")[0]).stem or "image")
        return self._optimise(raw, slug)


def _to_rgb(image: "Image.Image") -> "Image.Image":
    """Flatten any mode onto the near-black paper so a transparent PNG keeps the dark look."""
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        backdrop = Image.new("RGB", rgba.size, DARK_BACKDROP)
        backdrop.paste(rgba, mask=rgba.split()[-1])
        return backdrop
    if image.mode == "P":
        return image.convert("RGB")
    if image.mode in ("L", "1"):
        return image.convert("RGB")
    return image.convert("RGB")

# ---------------------------------------------------------------------------
# HTML fragments
# ---------------------------------------------------------------------------

def render_figure(section: dict[str, Any], image: dict[str, Any] | None,
                  prefix: str, kind: str) -> str:
    """One <figure class="media"> block, or '' when the image could not be resolved."""
    if not image:
        return ""
    alt = str((section.get("image") or {}).get("alt") or "").strip()
    if not alt:
        return ""
    credit = str((section.get("image") or {}).get("credit") or "").strip()
    width, height = image["width"], image["height"]
    extra = " media--lead" if kind == "lead" else ""
    src = f"{prefix}assets/{image['date']}/{image['file']}"
    credit_html = f'\n        <figcaption class="media__credit">{esc(credit)}</figcaption>' if credit else ""
    return f'''      <figure class="media{extra}">
        <div class="media__box" style="--ar:{width}/{height};aspect-ratio:{width}/{height}">
          <img class="media__img" src="{esc(src)}" alt="{esc(alt)}" loading="lazy" decoding="async" width="{width}" height="{height}">
        </div>{credit_html}
      </figure>'''


def render_kicker(section: dict[str, Any]) -> str:
    kicker = str(section.get("kicker") or "").strip()
    return f'      <p class="kicker">{render_inline(kicker)}</p>' if kicker else ""


def render_whymatters(section: dict[str, Any]) -> str:
    value = str(section.get("whyItMatters") or "").strip()
    if not value:
        return ""
    return ('      <p class="whymatters"><span class="whymatters__label">Why it matters</span> '
            f"{render_inline(value)}</p>")


def render_aside(section: dict[str, Any]) -> str:
    value = str(section.get("aside") or "").strip()
    if not value:
        return ""
    return f'      <p class="aside">{render_inline(value)}</p>'


def render_source_line(section: dict[str, Any], prefix: str = "") -> str:
    source = section.get("source") or {}
    url = sanitise_url(str(source.get("url") or ""))
    label = str(source.get("label") or "").strip()
    if not url or not label:
        return ""
    return (f'      <p class="source-line"><a class="source" href="{esc(url)}" '
            f'target="_blank" rel="noopener">{esc(label)}</a></p>')


def render_lead(section: dict[str, Any], image: dict[str, Any] | None, prefix: str,
                layout: str) -> str:
    headline = str(section.get("headline") or "")
    source = section.get("source") or {}
    url = sanitise_url(str(source.get("url") or ""))
    inner = esc(plain(headline))
    title = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{inner}</a>' if url else inner)
    standfirst = str(section.get("standfirst") or "").strip()
    stand_html = f'\n      <p class="standfirst">{render_inline(standfirst)}</p>' if standfirst else ""
    body = render_paragraphs(section.get("body"))
    body_html = f'\n      <div class="lead__body body">\n{body}\n      </div>' if body else ""
    parts = [
        f'    <article class="lead lead--{layout}" id="{esc(section.get("id"))}">',
        render_kicker(section),
        f'      <h2 class="lead__headline">{title}</h2>',
    ]
    if stand_html:
        parts.append(stand_html.strip("\n"))
    figure = render_figure(section, image, prefix, "lead")
    if figure:
        parts.append(figure)
    if body_html:
        parts.append(body_html.strip("\n"))
    for block in (render_whymatters(section), render_aside(section), render_source_line(section, prefix)):
        if block:
            parts.append(block)
    parts.append("    </article>")
    return "\n".join(parts)


def render_story(section: dict[str, Any], image: dict[str, Any] | None, prefix: str) -> str:
    kind = str(section.get("kind") or "story")
    classes = "story"
    if kind == "video":
        classes += " card card--video"
    elif kind == "quick":
        classes += " story--brief"
    headline = str(section.get("headline") or "")
    source = section.get("source") or {}
    url = sanitise_url(str(source.get("url") or ""))
    inner = esc(plain(headline))
    title = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{inner}</a>' if url else inner)
    standfirst = str(section.get("standfirst") or "").strip()
    stand_html = f'      <p class="standfirst">{render_inline(standfirst)}</p>' if standfirst else ""
    body = render_paragraphs(section.get("body"))
    body_html = f'      <div class="body">\n{body}\n      </div>' if body else ""
    parts = [f'    <article class="{classes}" id="{esc(section.get("id"))}">', render_kicker(section)]
    parts.append(f'      <h2 class="story__headline">{title}</h2>')
    for block in (stand_html, render_figure(section, image, prefix, kind), body_html,
                  render_whymatters(section), render_aside(section), render_source_line(section, prefix)):
        if block:
            parts.append(block)
    parts.append("    </article>")
    return "\n".join(parts)


def render_quote(section: dict[str, Any], prefix: str) -> str:
    body = section.get("body") or []
    items = body if isinstance(body, list) else [body]
    quote = next((str(x).strip() for x in items if x is not None and str(x).strip()), "")
    if not quote:
        quote = str(section.get("headline") or "")
    source = section.get("source") or {}
    cite = str(source.get("label") or "").strip()
    url = sanitise_url(str(source.get("url") or ""))
    if cite and url:
        cite_html = f'<a class="source" href="{esc(url)}" target="_blank" rel="noopener">{esc(cite)}</a>'
    else:
        cite_html = esc(cite)
    footer = f'\n      <footer class="pullquote__cite">{cite_html}</footer>' if cite else ""
    return (f'    <blockquote class="pullquote" id="{esc(section.get("id"))}">\n'
            f'      <p class="pullquote__text">{render_inline(quote)}</p>{footer}\n'
            f'    </blockquote>')


def render_quick_hits(edition: dict[str, Any]) -> str:
    hits = edition.get("quickHits") or []
    if not hits:
        return ""
    lines: list[str] = []
    for hit in hits:
        if isinstance(hit, dict):
            text = str(hit.get("text") or "").strip()
            url = sanitise_url(str(hit.get("url") or ""))
        else:
            text, url = str(hit).strip(), None
        if not text:
            continue
        inner = render_inline(text)
        if url:
            lines.append(f'        <li><a href="{esc(url)}" target="_blank" rel="noopener">{inner}</a></li>')
        else:
            lines.append(f"        <li>{inner}</li>")
    if not lines:
        return ""
    return ('    <aside class="quick-hits" id="quick-hits" aria-labelledby="quick-hits-title">\n'
            '      <h2 class="quick-hits__title" id="quick-hits-title">Quick Hits</h2>\n'
            '      <ul class="quick-hits__list">\n'
            + "\n".join(lines) + "\n      </ul>\n    </aside>")

# ---------------------------------------------------------------------------
# colophon counts (memory.py is optional)
# ---------------------------------------------------------------------------

def memory_counts() -> dict[str, int] | None:
    """Ask scripts/memory.py for its counts. None when absent, slow or failing - never fatal."""
    script = ROOT / "scripts" / "memory.py"
    if not script.exists():
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "stats"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except Exception:  # noqa: BLE001 - timeout, permissions and missing modules all read the same
        return None
    if proc.returncode != 0:
        return None
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    counts: dict[str, int] = {}
    for label, pattern in (
        ("items", r"(?:items?|tracked)\s*[:=]?\s*(\d+)"),
        ("suppressed", r"(?:suppressed|topics?)\s*[:=]?\s*(\d+)"),
    ):
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            counts[label] = int(match.group(1))
    return counts or None


# ---------------------------------------------------------------------------
# page assembly (docs/SITE-CONTRACT.md section 2 - element order is the contract)
# ---------------------------------------------------------------------------

def build_masthead(edition: dict[str, Any], heading_tag: str = "h1") -> str:
    iso = str(edition.get("date") or "")
    weather = str(edition.get("weatherStrip") or "").strip()
    title = esc(edition.get("masthead") or "THE DAILY BEACON")
    parts = [
        '  <header class="masthead" id="masthead">',
        '    <div class="masthead__rule masthead__rule--thick"></div>',
        '    <div class="masthead__rule"></div>',
        '    <p class="masthead__ear masthead__ear--left">No. %s</p>' % esc(edition.get("number")),
        '    <p class="masthead__ear masthead__ear--right">%s</p>' % esc(human_date(iso)),
        '    <%s class="masthead__title">%s</%s>' % (heading_tag, title, heading_tag),
        '    <p class="masthead__tagline">%s</p>' % esc(edition.get("tagline") or ""),
        '    <div class="masthead__rule"></div>',
        '    <div class="masthead__rule masthead__rule--thick"></div>',
    ]
    if weather:
        parts.append('    <p class="masthead__weather">%s</p>' % render_inline(weather))
    parts.append("  </header>")
    return "\n".join(parts)


def build_toc(sections: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for index, section in enumerate(sections, start=1):
        kicker = plain(section.get("kicker") or "")
        label = truncate_str(section.get("headline") or "", 42)
        rows.append(
            '      <li><a class="toc__link" href="#%s">'
            '<span class="toc__kicker">%02d / %s</span>'
            '<span class="toc__label">%s</span></a></li>'
            % (esc(section.get("id")), index, esc(kicker), esc(label))
        )
    return ('  <nav class="toc" aria-label="In this edition">\n'
            '    <ul class="toc__list">\n' + "\n".join(rows) + "\n    </ul>\n"
            '    <button class="density-toggle" type="button" aria-pressed="false">Dense</button>\n'
            '  </nav>')


def build_colophon(edition: dict[str, Any], sections: list[dict[str, Any]],
                   counts: dict[str, int] | None, prefix: str) -> str:
    story_count = sum(1 for s in sections if str(s.get("kind")) in ("lead", "story", "video"))
    hit_count = len(edition.get("quickHits") or [])
    if counts:
        count_line = "%d items tracked, %d suppressed today" % (
            counts.get("items", 0), counts.get("suppressed", 0))
    else:
        count_line = "counts unavailable"
    signoff = str(edition.get("signoff") or "").strip()
    signoff_html = ('\n    <p class="colophon__signoff">%s</p>' % render_inline(signoff)) if signoff else ""
    meta = [
        '      <li>Edition %s</li>' % esc(edition.get("number")),
        '      <li>Generated %s</li>' % esc(human_timestamp(str(edition.get("generatedAt") or ""))),
        '      <li>%d stories, %d quick hits</li>' % (story_count, hit_count),
        '      <li>%s</li>' % esc(count_line),
    ]
    return ('  <footer class="colophon">\n'
            '    <div class="colophon__rule"></div>\n'
            '    <ul class="colophon__meta">\n' + "\n".join(meta) + "\n    </ul>" + signoff_html + "\n"
            '    <p class="colophon__archive">Previous 30 editions are archived at '
            '<a href="' + prefix + 'archive.html">archive.html</a>.</p>\n'
            '    <p class="colophon__fine">Compiled automatically at 03:00 from public feeds and '
            "creators' uploads. No story is invented; every item links to its source.</p>\n"
            '  </footer>')


def build_head(edition: dict[str, Any], variants: dict[str, str], prefix: str,
               css_v: str, body_class: str) -> str:
    iso = str(edition.get("date") or "")
    masthead = esc(edition.get("masthead") or "THE DAILY BEACON")
    tagline = esc(edition.get("tagline") or "")
    page_title = "%s - %s" % (masthead, esc(human_date(iso)))
    html_class = "layout-%s scale-%s order-%s" % (
        variants["layout"], variants["scale"], variants["order"])
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en" data-accent="%s" data-layout="%s" data-scale="%s" data-emphasis="%s" '
        'data-seed="%s" class="%s">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '  <meta name="color-scheme" content="dark light">\n'
        '  <meta name="theme-color" content="#0b0b0d">\n'
        "  <title>%s</title>\n"
        '  <meta name="description" content="%s">\n'
        '  <link rel="stylesheet" href="%sstyle.css?v=%s">\n'
        '  <meta property="og:title" content="%s">\n'
        '  <meta property="og:description" content="%s">\n'
        '  <meta property="og:type" content="website">\n'
        "</head>\n"
        '<body id="top" class="%s">\n'
        '  <div id="progress" aria-hidden="true"><span id="progress-bar"></span></div>'
        % (variants["accent"], variants["layout"], variants["scale"], variants["order"],
           variants["seed"], html_class, page_title, tagline,
           prefix, css_v, page_title, tagline, body_class)
    )


def render_page(edition: dict[str, Any], images: dict[str, dict[str, Any] | None],
                prefix: str, out_dir: Path, counts: dict[str, int] | None) -> str:
    """Render one complete document. prefix is '' for index.html and '../' for snapshots."""
    variants = seed_variants(str(edition.get("date") or ""))
    lead, rest = order_sections(edition)
    sections_all = ([lead] if lead else []) + rest

    css_v = file_version(out_dir / "style.css")
    js_v = file_version(out_dir / "app.js")

    parts: list[str] = [
        build_head(edition, variants, prefix, css_v, "page-edition"),
        "",
        build_masthead(edition),
        "",
        build_toc(sections_all),
        "",
        '  <main class="paper" id="paper">',
    ]

    if lead:
        parts.append(render_lead(lead, images.get(str(lead.get("id"))), prefix,
                                 variants["layout"]))

    quick_block = render_quick_hits(edition)
    if quick_block and variants["order"] == "rail":
        parts.append(quick_block)

    for section in rest:
        if str(section.get("kind")) == "quote":
            parts.append(render_quote(section, prefix))
        else:
            parts.append(render_story(section, images.get(str(section.get("id"))), prefix))

    if quick_block and variants["order"] == "lead":
        parts.append(quick_block)

    parts.extend([
        "  </main>",
        "",
        build_colophon(edition, sections_all, counts, prefix),
        "",
        '  <a class="to-top" href="#top" aria-label="Back to top">Top</a>',
        '  <script src="%sapp.js?v=%s" defer></script>' % (prefix, js_v),
        "</body></html>",
    ])
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# archive index (site/archive.html)
# ---------------------------------------------------------------------------

def gather_archive(out_dir: Path) -> list[dict[str, Any]]:
    """Scan snapshots on disk; enrich from editions/<date>.json when it still exists.

    A snapshot whose edition JSON was moved to editions/archive/ or deleted must still be listed,
    so every row degrades to a labelled fallback instead of disappearing.
    """
    archive_dir = out_dir / "archive"
    rows: list[dict[str, Any]] = []
    if not archive_dir.exists():
        return rows
    for snapshot in sorted(archive_dir.glob("*.html"), reverse=True):
        day = snapshot.stem
        if not ISO_DATE_RE.match(day):
            continue
        row: dict[str, Any] = {
            "date": day,
            "headline": f"Edition for {day}",
            "number": "",
            "stories": "",
        }
        for candidate in (EDITION_DIR / f"{day}.json", EDITION_DIR / "archive" / f"{day}.json",
                          FIXTURE_DIR / f"{day}.json"):
            if not candidate.exists():
                continue
            try:
                edition = read_json(candidate)
            except Exception:  # noqa: BLE001 - a broken JSON must not hide the snapshot
                continue
            lead, rest = order_sections(edition)
            headline = ""
            if lead:
                headline = truncate_str(lead.get("headline") or "", 90)
                if not headline:
                    headline = truncate_str((lead.get("body") or [""])[0], 90)
            else:
                headline = "Untitled edition"
            sections = [s for s in (edition.get("sections") or []) if isinstance(s, dict)]
            count = sum(1 for s in sections if str(s.get("kind")) in ("lead", "story", "video"))
            row.update({
                "headline": headline or f"Edition for {day}",
                "number": str(edition.get("number") or ""),
                "stories": str(count),
            })
            break
        rows.append(row)
    return rows


def render_archive_page(rows: list[dict[str, Any]], out_dir: Path, settings: dict[str, Any]) -> str:
    css_v = file_version(out_dir / "style.css")
    js_v = file_version(out_dir / "app.js")
    variants = seed_variants(datetime.now().strftime("%Y-%m-%d"))
    title = "THE DAILY BEACON"
    items: list[str] = []
    for row in rows:
        number = f"No. {row['number']} - " if row["number"] else ""
        items.append(
            '      <li class="archive__item">'
            f'<a class="archive__link" href="archive/{esc(row["date"])}.html">'
            f'<span class="archive__date">{esc(row["date"])}</span>'
            f'<span class="archive__head">{esc(row["headline"])}</span></a></li>'
        )
    if not items:
        items.append('      <li class="archive__item"><span class="archive__head">'
                     "No editions archived yet.</span></li>")
    keep = int(settings.get("keep_editions") or 30)
    return f'''<!DOCTYPE html>
<html lang="en" data-accent="{variants["accent"]}" data-seed="{variants["seed"]}" class="layout-{variants["layout"]} scale-{variants["scale"]} order-{variants["order"]}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark light">
  <meta name="theme-color" content="#0b0b0d">
  <title>{esc(title)} - Archive</title>
  <meta name="description" content="Every archived edition of {esc(title)}.">
  <link rel="stylesheet" href="style.css?v={css_v}">
  <meta property="og:title" content="{esc(title)} - Archive">
  <meta property="og:description" content="Every archived edition of {esc(title)}.">
  <meta property="og:type" content="website">
</head>
<body id="top" class="page-archive">
  <div id="progress" aria-hidden="true"><span id="progress-bar"></span></div>

  <header class="masthead" id="masthead">
    <div class="masthead__rule masthead__rule--thick"></div>
    <div class="masthead__rule"></div>
    <p class="masthead__ear masthead__ear--left">Archive</p>
    <p class="masthead__ear masthead__ear--right">{esc(human_date(datetime.now().strftime("%Y-%m-%d")))}</p>
    <h1 class="masthead__title">{esc(title)}</h1>
    <p class="masthead__tagline">Archive</p>
    <div class="masthead__rule"></div>
    <div class="masthead__rule masthead__rule--thick"></div>
  </header>

  <main class="paper archive" id="paper">
    <ul class="archive__list">
{chr(10).join(items)}
    </ul>
  </main>

  <footer class="colophon">
    <div class="colophon__rule"></div>
    <ul class="colophon__meta">
      <li>{len(rows)} editions archived</li>
      <li>Previous {keep} editions kept on disk</li>
    </ul>
    <p class="colophon__archive">Back to <a href="index.html">today's edition</a>.</p>
    <p class="colophon__fine">Compiled automatically at 03:00 from public feeds and creators' uploads.</p>
  </footer>

  <a class="to-top" href="#top" aria-label="Back to top">Top</a>
  <script src="app.js?v={js_v}" defer></script>
</body>
</html>
'''

# ---------------------------------------------------------------------------
# HTML self-check (tag balance, anchors, alt text, size)
# ---------------------------------------------------------------------------

TAG_SCAN = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)([^>]*?)(/?)>", re.DOTALL)


def check_html(markup: str, label: str) -> tuple[bool, str]:
    """Validate the generated document. Returns (ok, human summary)."""
    problems: list[str] = []

    # 1. tag balance -------------------------------------------------------
    # Raw-text element bodies (script/style) are blanked first: their contents are not markup.
    scan = re.sub(r"(<(script|style)\b[^>]*>).*?(</\2>)", r"\1\3", markup, flags=re.DOTALL | re.IGNORECASE)
    stack: list[str] = []
    for match in TAG_SCAN.finditer(scan):
        closing, name, _attrs, self_closed = match.groups()
        tag = name.lower()
        if tag in VOID_TAGS or self_closed:
            continue
        if closing:
            if not stack:
                problems.append(f"stray </{tag}>")
            elif stack[-1] != tag:
                problems.append(f"unexpected </{tag}> (open: <{stack[-1]}>)")
                if tag in stack:
                    while stack and stack.pop() != tag:
                        pass
            else:
                stack.pop()
        else:
            stack.append(tag)
    if stack:
        problems.append("unclosed " + ", ".join(f"<{t}>" for t in reversed(stack)))

    # 2. anchors resolve ---------------------------------------------------
    ids = set(re.findall(r'\bid="([^"]+)"', markup))
    for target in set(re.findall(r'href="#([^"]*)"', markup)):
        if target and target not in ids:
            problems.append(f"href='#{target}' has no matching id")

    # 3. every image carries alt ------------------------------------------
    for tag in re.findall(r"<img\b[^>]*>", markup, re.IGNORECASE):
        alt = re.search(r'\balt="([^"]*)"', tag)
        if not alt or not alt.group(1).strip():
            problems.append("img without non-empty alt")

    # 4. size --------------------------------------------------------------
    size = len(markup.encode("utf-8"))
    if size >= MAX_HTML_BYTES:
        problems.append(f"document is {size / 1024 / 1024:.2f} MB (limit 3 MB)")

    if problems:
        for item in problems[:12]:
            say(f"html: {label}: {item}")
        return False, f"{label}: {len(problems)} html problem(s)"

    summary = (
        "check: ok (%d ids, %d anchors, %d imgs, %d KB)"
        % (len(ids), len(set(re.findall('href="#([^"]*)"', markup))), imgs_count(markup), size // 1024)
    )
    return True, summary


def imgs_count(markup: str) -> int:
    """Count <img> occurrences in a document."""
    return len(re.findall("<img[ >]", markup, re.IGNORECASE))


# ---------------------------------------------------------------------------
# fixture edition (no network, images generated with Pillow)
# ---------------------------------------------------------------------------

FIXTURE_ISO = datetime.now().strftime("%Y-%m-%d")


def _fixture_palettes() -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    """One distinct duotone per fixture image (six images, six looks)."""
    return [
        ((232, 163, 61), (28, 20, 10)),
        ((111, 195, 186), (8, 26, 28)),
        ((236, 122, 92), (32, 14, 10)),
        ((130, 182, 232), (10, 20, 32)),
        ((166, 196, 138), (14, 24, 12)),
        ((232, 143, 162), (30, 12, 18)),
    ]


def make_fixture_images() -> list[Path]:
    """Draw abstract duotone gradients under state/workpack/_fixture/img/. No text, no network."""
    FIXTURE_IMG_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    sizes = [(1400, 788), (800, 450), (1400, 788), (800, 450), (1400, 788), (800, 450)]
    for index, (width, height) in enumerate(sizes):
        palettes = _fixture_palettes()
        bright, dark = palettes[index % len(palettes)]
        target = FIXTURE_IMG_DIR / f"fixture-{index + 1}.jpg"
        if not target.exists():
            if Image is None or ImageDraw is None:
                continue
            image = Image.new("RGB", (width, height), DARK_BACKDROP)
            draw = ImageDraw.Draw(image, "RGBA")
            # diagonal bands: cheap, deterministic, and reads as a photo thumbnail at small size
            steps = 26
            for step in range(steps):
                frac = step / float(steps - 1)
                shade = tuple(int(dark[i] + (bright[i] - dark[i]) * (frac ** 1.7)) for i in range(3))
                alpha = 46 + int(150 * frac)
                skew = 0.72 + 0.09 * (index % 4)
                x0 = int(width * (frac * skew - 0.35))
                draw.polygon(
                    [(x0, height), (x0 + width // 3, 0), (x0 + width // 3 + width // 2, 0), (x0 + width // 2, height)],
                    fill=shade + (alpha,),
                )
            draw.rectangle([0, int(height * 0.62), width, height], fill=DARK_BACKDROP + (150,))
            image.save(target, format="JPEG", quality=88, optimize=True)
        paths.append(target)
    return paths


def build_fixture_edition(images: list[Path]) -> dict[str, Any]:
    """A realistic 12-section edition: 1 lead, 3 videos, 5 stories, 2 quotes, 1 quick + quickHits."""
    def img(index: int, alt: str, credit: str) -> dict[str, Any] | None:
        if index >= len(images):
            return None
        return {"src": str(images[index]), "alt": alt, "credit": credit}

    sections: list[dict[str, Any]] = [
        {
            "id": "lead-source-2-engine",
            "kind": "lead",
            "priority": 100,
            "kicker": "the big one",
            "headline": "Source 2 engine ships, and half the modding scene breathes again",
            "standfirst": "Valve quietly pushed the **Source 2** toolchain to everyone, and the first "
                          "wave of ports landed inside 48 hours.",
            "body": [
                "For years the community treated *Source 2* as a rumour with a beta attached. That "
                "changed overnight: the toolchain is now part of the default install, and three "
                "high-profile mods published playable builds before lunch.",
                "The interesting part is not the renderer. It is the **[Hammer editor](https://developer.valvesoftware.com/wiki/Hammer)** "
                "workflow: map files are now plain assets, so a workshop upload no longer needs a "
                "custom launcher.",
                "Modders are already reporting *dramatically* shorter iteration loops. One mapper "
                "timed a full rebuild at 40 seconds, down from nine minutes on the same machine.",
            ],
            "image": img(0, "Abstract duotone gradient standing in for the Source 2 announcement art",
                         "Fixture / generated art"),
            "source": {"label": "PC Gamer", "url": "https://www.pcgamer.com/"},
            "tags": ["source2", "modding"],
            "whyItMatters": "The modding pipeline is the reason half these games still have players.",
            "aside": "Nine minutes to 40 seconds. Somewhere a mapper is crying into a warm energy drink.",
        },
        {
            "id": "video-df-steam-machine",
            "kind": "video",
            "priority": 92,
            "kicker": "hardware",
            "headline": "Digital Foundry tears down the new console-handheld hybrid",
            "standfirst": "A 30-minute technical autopsy, and the thermals are the story.",
            "body": [
                "The teardown is worth the watch for the cooling design alone: a vapour chamber "
                "roughly the size of a phone, ducted toward a single rear vent.",
                "Sustained clocks hold up better than the launch firmware suggested, though the "
                "fan curve is described as *enthusiastic*.",
            ],
            "image": img(1, "Abstract duotone gradient standing in for the handheld teardown thumbnail",
                         "YouTube / Digital Foundry"),
            "source": {"label": "Digital Foundry", "url": "https://www.eurogamer.net/digitalfoundry"},
            "tags": ["hardware"],
            "whyItMatters": "Thermals decide whether this thing is a console or a hand warmer.",
        },
        {
            "id": "story-ai-agents",
            "kind": "story",
            "priority": 88,
            "kicker": "ai",
            "headline": "Agent frameworks converge on the same boring answer: files and logs",
            "standfirst": "Three vendors, one architecture, zero magic.",
            "body": [
                "The newest generation of agent tooling dropped the orchestration graph and kept the "
                "filesystem. State lives in a directory; the model reads it, writes it, and every step "
                "is a line in a log.",
                "It is less impressive in a keynote and *far* more debuggable at 3am, which is the only "
                "review that matters here.",
            ],
            "source": {"label": "The Verge", "url": "https://www.theverge.com/ai-artificial-intelligence"},
            "tags": ["ai", "agents"],
            "whyItMatters": "Boring architectures survive contact with production.",
        },
        {
            "id": "quote-night-shift",
            "kind": "quote",
            "priority": 80,
            "kicker": "from the transcript",
            "headline": "We are not shipping a game, we are shipping a patch pipeline with a game attached.",
            "body": ["We are not shipping a game, we are shipping a patch pipeline with a game attached."],
            "source": {"label": "GDC talk, 2026", "url": "https://gdconf.com/"},
            "tags": ["gamedev"],
        },
        {
            "id": "story-godot-4-6",
            "kind": "story",
            "priority": 76,
            "kicker": "gamedev",
            "headline": "Godot 4.6 lands with a renderer that finally stops surprising people",
            "standfirst": "Fewer knobs, better defaults, and a migration path that mostly works.",
            "body": [
                "The headline feature is restraint: the forward+ renderer now picks sane defaults "
                "instead of exposing twelve switches nobody understood.",
                "Projects ported cleanly in our test, with the usual caveat that custom shaders still "
                "need a pass.",
                "The release notes are unusually honest about the rough edges, which is worth more "
                "than the feature list.",
            ],
            "image": img(2, "Abstract duotone gradient standing in for the Godot release header",
                         "Fixture / generated art"),
            "source": {"label": "Godot Engine", "url": "https://godotengine.org/blog"},
            "tags": ["godot", "gamedev"],
            "whyItMatters": "Default quality is what most small teams actually ship with.",
        },
        {
            "id": "video-asmongold-reaction",
            "kind": "video",
            "priority": 70,
            "kicker": "reaction",
            "headline": "A 40-minute reaction that accidentally becomes an industry post-mortem",
            "standfirst": "Half rant, half surprisingly sharp analysis of studio closures.",
            "body": [
                "The clip starts as a reaction and ends somewhere close to a lecture on runway "
                "economics. The middle third is the part worth clipping.",
            ],
            "image": img(4, "Abstract duotone gradient standing in for the reaction stream thumbnail",
                         "YouTube / Asmongold TV"),
            "source": {"label": "Asmongold TV", "url": "https://www.youtube.com/@AsmongoldTV"},
            "tags": ["youtube", "industry"],
            "whyItMatters": "The reaction economy is how a lot of people actually follow this industry.",
        },
        {
            "id": "story-steam-deck-price",
            "kind": "story",
            "priority": 64,
            "kicker": "business",
            "headline": "Handheld prices drift upward, and the second-hand market notices",
            "standfirst": "Nothing dramatic, just a slow squeeze that is now visible in listings.",
            "body": [
                "Component pricing moved first; retail followed three weeks later. The used market "
                "is now the cheapest way into the category, which is a strange sentence to write.",
                "Analysts expect the correction to hold through the next hardware cycle.",
            ],
            "source": {"label": "GamesIndustry.biz", "url": "https://www.gamesindustry.biz/"},
            "tags": ["hardware", "business"],
            "whyItMatters": "Price floors decide who can join the hobby.",
        },
        {
            "id": "quick-directive",
            "kind": "quick",
            "priority": 60,
            "kicker": "quick",
            "headline": "Short version: the patch is 11 GB and it fixes the crashing",
            "body": ["Short version: the patch is 11 GB and it fixes the crashing."],
            "source": {"label": "Steam news", "url": "https://store.steampowered.com/news/"},
            "tags": ["patch"],
        },
        {
            "id": "video-meatcanyon-short",
            "kind": "video",
            "priority": 56,
            "kicker": "animation",
            "headline": "A four-minute short that nails the exact texture of a 2004 tutorial CD",
            "standfirst": "Uncomfortably accurate, as usual.",
            "body": [
                "Every frame is a reference, from the compression artefacts to the cursor trail. "
                "Watch it on a big screen if you can.",
            ],
            "image": img(3, "Abstract duotone gradient standing in for the animation thumbnail",
                         "YouTube / MeatCanyon"),
            "source": {"label": "MeatCanyon", "url": "https://www.youtube.com/@MeatCanyon"},
            "tags": ["animation", "youtube"],
            "whyItMatters": "Craft this specific is worth ten trend-chasing uploads.",
        },
        {
            "id": "story-roblox-scale",
            "kind": "story",
            "priority": 48,
            "kicker": "platforms",
            "headline": "Roblox publishes the boring numbers, and they are the interesting ones",
            "standfirst": "Session length down, creator payouts up.",
            "body": [
                "The quarterly numbers show engagement flattening while payouts rose. That is either "
                "maturity or a plateau, and the deck argues hard for the first.",
                "Creator tooling got the largest single line item, which is a notable shift.",
            ],
            "image": img(5, "Abstract duotone gradient standing in for the platform report art",
                         "Fixture / generated art"),
            "source": {"label": "Game Developer", "url": "https://www.gamedeveloper.com/"},
            "tags": ["roblox", "platforms"],
            "whyItMatters": "Where the money goes tells you what the platform thinks it is.",
        },
        {
            "id": "quote-small-team",
            "kind": "quote",
            "priority": 40,
            "kicker": "from the interview",
            "headline": "We had four people and a deadline. The deadline had more people.",
            "body": ["We had four people and a deadline. The deadline had more people."],
            "source": {"label": "Interview, Game Developer", "url": "https://www.gamedeveloper.com/"},
            "tags": ["gamedev"],
        },
        {
            "id": "story-ukraine-tech",
            "kind": "story",
            "priority": 32,
            "kicker": "world",
            "headline": "A studio relocates twice and keeps shipping, on generators",
            "standfirst": "The logistics story behind a studio that never missed a patch window.",
            "body": [
                "Two relocations, a generator budget, and a build pipeline mirrored across three "
                "countries. The engineering is unglamorous and completely effective.",
                "The team's public post is a practical checklist for anyone planning for outages.",
            ],
            "source": {"label": "Kyiv Independent", "url": "https://kyivindependent.com/"},
            "tags": ["world", "gamedev"],
            "whyItMatters": "Resilience is a build-system feature, not a personality trait.",
        },
    ]

    return {
        "date": FIXTURE_ISO,
        "number": 1,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "masthead": "THE DAILY BEACON",
        "tagline": "Your 3am briefing, slightly unhinged",
        "weatherStrip": "Overcast with a chance of patch notes.",
        "sections": sections,
        "quickHits": [
            {"text": "Steam Next Fest dates confirmed for February.", "url": "https://store.steampowered.com/"},
            {"text": "A 12-year-old MMO got a new renderer and it looks great.", "url": "https://www.pcgamer.com/"},
            {"text": "Open-source audio tool hits 1.0 after nine years.", "url": "https://github.com/"},
            {"text": "The weekend's biggest trailer was 40 seconds of fog.", "url": "https://www.youtube.com/"},
        ],
        "signoff": "Sleep well. The feeds will still be there in the morning.",
    }

# ---------------------------------------------------------------------------
# build pipeline
# ---------------------------------------------------------------------------

def resolve_images(edition: dict[str, Any], edition_path: Path, out_dir: Path,
                   iso_date: str) -> tuple[dict[str, dict[str, Any] | None], int, int]:
    """Resolve every section image once. Returns (by section id, ok count, fail count)."""
    budget = ImageBudget(out_dir, iso_date)
    # Assets for one date are fully deterministic, so stale files from an earlier run are removed
    # first: a rebuild never leaves orphans behind, and hash names cannot collide by accident.
    for stale in budget.asset_dir.glob("*.jpg"):
        try:
            stale.unlink()
        except OSError:
            pass
    resolved: dict[str, dict[str, Any] | None] = {}
    for section in edition.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        image = section.get("image")
        if not isinstance(image, dict) or not str(image.get("src") or "").strip():
            resolved[section_id] = None
            continue
        asset = budget.resolve(str(image["src"]), edition_path.parent)
        if asset:
            asset = dict(asset)
            asset["date"] = iso_date
        resolved[section_id] = asset
    return resolved, budget.count, budget.failures


def build_edition_file(edition_path: Path, out_dir: Path, settings: dict[str, Any],
                       counts: dict[str, int] | None, stamp: bool = True) -> dict[str, Any]:
    """Validate, render and write index.html + the dated snapshot. Returns build stats."""
    started = time.perf_counter()
    edition = read_json(edition_path)
    report = validate_edition(edition, edition_path, settings)

    for path, message in report.warnings:
        warn(f"{path}: {message}")
    if not report.ok:
        say(f"validation failed: {edition_path.name}")
        for path, message in report.errors:
            say(f"  {path}: {message}")
        raise SystemExit(1)

    if promote_lead(edition):
        say(f"warning: no lead in {edition_path.name}; promoted the highest-priority section")

    iso = str(edition.get("date"))
    images, ok_images, failed_images = resolve_images(edition, edition_path, out_dir, iso)

    index_html = render_page(edition, images, "", out_dir, counts)
    snapshot_html = render_page(edition, images, "../", out_dir, counts)

    ok, message = check_html(index_html, "index.html")
    if not ok:
        raise SystemExit(1)
    say(message)

    ok2, message2 = check_html(snapshot_html, "archive/" + iso + ".html")
    if not ok2:
        raise SystemExit(1)

    index_path = out_dir / "index.html"
    snapshot_path = out_dir / "archive" / f"{iso}.html"
    write_text(index_path, index_html)

    # --fixture keeps snapshots out of the real archive unless it writes to the real site root
    write_text(snapshot_path, snapshot_html)

    elapsed = time.perf_counter() - started
    size_kb = len(index_html.encode("utf-8")) / 1024.0
    sections = [s for s in (edition.get("sections") or []) if isinstance(s, dict)]
    try:
        rel_index = index_path.relative_to(index_path.parent.parent).as_posix()
    except ValueError:  # site root, no parent to speak of
        rel_index = index_path.name
    return {
        "edition": edition,
        "index": index_path,
        "rel_index": rel_index,
        "snapshot": snapshot_path,
        "sections": len(sections),
        "images": ok_images,
        "image_failures": failed_images,
        "kb": size_kb,
        "seconds": elapsed,
        "number": edition.get("number"),
        "date": iso,
    }


def rebuild_archive(out_dir: Path, settings: dict[str, Any]) -> Path:
    """Regenerate archive.html from the snapshots present on disk."""
    rows = gather_archive(out_dir)
    page = render_archive_page(rows, out_dir, settings)
    ok, message = check_html(page, "archive.html")
    if not ok:
        raise SystemExit(1)
    target = out_dir / "archive.html"
    write_text(target, page)
    return target


def newest_edition_path() -> Path | None:
    """Newest editions/YYYY-MM-DD.json, ignoring anything that is not a real date."""
    candidates: list[Path] = []
    for path in EDITION_DIR.glob("*.json"):
        if ISO_DATE_RE.match(path.stem):
            candidates.append(path)
    return max(candidates, key=lambda p: p.stem) if candidates else None


def summary_line(stats: dict[str, Any]) -> str:
    return (
        f"built: edition {stats['number']} ({stats['date']}) -> "
        f"{stats['rel_index']}, {stats['sections']} sections, "
        f"{stats['images']} images, {stats['kb']:.1f} KB html, {stats['seconds']:.1f}s"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_check(target: str | None, settings: dict[str, Any]) -> int:
    """Validate one or all editions; print every violation with its JSON path."""
    if target and target != "today":
        path = EDITION_DIR / f"{target}.json"
        if not path.exists():
            fixture_path = FIXTURE_DIR / f"{target}.json"
            if fixture_path.exists():
                path = fixture_path
        if not path.exists():
            say(f"error: edition not found: {EDITION_DIR / (target + '.json')}")
            return 1
        paths = [path]
    else:
        paths = sorted(p for p in EDITION_DIR.glob("*.json") if ISO_DATE_RE.match(p.stem))
        if not paths:
            say("error: no editions found")
            return 1

    total_errors = 0
    for path in paths:
        try:
            edition = read_json(path)
        except Exception as exc:  # noqa: BLE001
            say(f"{path.name}: invalid JSON ({type(exc).__name__})")
            total_errors += 1
            continue
        report = validate_edition(edition, path, settings)
        for where, message in report.warnings:
            say(f"{path.name}: warning: {where}: {message}")
        for where, message in report.errors:
            say(f"{path.name}: {where}: {message}")
        total_errors += len(report.errors)
        if not report.errors:
            sections = [s for s in (edition.get("sections") or []) if isinstance(s, dict)]
            say(f"{path.name}: ok ({len(sections)} sections)")

    if total_errors:
        say(f"check: failed ({total_errors} violation(s))")
        return 1
    say("check: ok")
    return 0


def cmd_fixture(args: argparse.Namespace, settings: dict[str, Any],
                counts: dict[str, int] | None) -> int:
    """Build the built-in fixture edition without touching the network or editions/."""
    out_dir = Path(args.out).resolve() if args.out else SITE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    images = make_fixture_images()
    if not images:
        say("error: fixture images could not be generated (Pillow missing?)")
        return 1
    edition = build_fixture_edition(images)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    edition_path = FIXTURE_DIR / f"{edition['date']}.json"
    write_text(edition_path, json.dumps(edition, indent=2, ensure_ascii=False))

    report = validate_edition(edition, edition_path, settings)
    for where, message in report.warnings:
        warn(f"{where}: {message}")
    if not report.ok:
        for where, message in report.errors:
            say(f"  {where}: {message}")
        say("error: built-in fixture edition is invalid")
        return 1

    stats = build_edition_file(edition_path, out_dir, settings, counts)
    rebuild_archive(out_dir, settings)
    say(summary_line(stats))
    return 0


def cmd_build(args: argparse.Namespace, settings: dict[str, Any],
              counts: dict[str, int] | None) -> int:
    iso = args.date or datetime.now().strftime("%Y-%m-%d")
    if not ISO_DATE_RE.match(iso):
        say(f"error: --date must be YYYY-MM-DD, got '{iso}'")
        return 2
    edition_path = EDITION_DIR / f"{iso}.json"
    if not edition_path.exists():
        archived = EDITION_DIR / "archive" / f"{iso}.json"
        if archived.exists():
            edition_path = archived
        else:
            say(f"error: edition not found: {edition_path}")
            return 1

    out_dir = Path(args.out).resolve() if args.out else SITE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = build_edition_file(edition_path, out_dir, settings, counts)
    rebuild_archive(out_dir, settings)
    say(summary_line(stats))
    return 0


def cmd_all(args: argparse.Namespace, settings: dict[str, Any],
            counts: dict[str, int] | None) -> int:
    """Rebuild index.html from the newest edition and refresh archive.html from all snapshots."""
    out_dir = Path(args.out).resolve() if args.out else SITE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    newest = newest_edition_path()
    if newest is None:
        say("error: no editions available to rebuild from")
        return 1
    stats = build_edition_file(newest, out_dir, settings, counts)
    rebuild_archive(out_dir, settings)
    say(summary_line(stats))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_edition.py",
        description="Build the Daily Beacon static site from an edition JSON file.",
        epilog="Exit codes: 0 ok, 1 validation/build failure, 2 usage error.",
    )
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="edition date to build (default: today)")
    parser.add_argument("--check", nargs="?", const="today", metavar="DATE",
                        help="validate only; exit 1 on any violation")
    parser.add_argument("--fixture", action="store_true",
                        help="build the built-in 12-section fixture (no network)")
    parser.add_argument("--all", action="store_true",
                        help="rebuild index from the newest edition and refresh archive.html")
    parser.add_argument("--open", action="store_true", help="ignored (headless-only policy)")
    parser.add_argument("--out", metavar="DIR", help="output directory (default: site)")
    return parser


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()

    if args.open:
        say("open: skipped (headless-only policy)")

    try:
        if args.check is not None:
            target = None if args.check == "today" else args.check
            return cmd_check(target, settings)

        counts = memory_counts()
        if args.fixture:
            return cmd_fixture(args, settings, counts)
        if args.all:
            return cmd_all(args, settings, counts)
        return cmd_build(args, settings, counts)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        say(f"error: {exc}")
        return 1
    except KeyboardInterrupt:
        say("error: interrupted")
        return 1


if __name__ == "__main__":
    sys.exit(main())