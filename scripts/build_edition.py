"""Build the Daily Beacon static site from one edition JSON file.

    python scripts/build_edition.py [--date YYYY-MM-DD] [--edition PATH] [--out-dir PATH]
                                    [--root PATH] [--check] [--fixture] [--no-images] [--quiet]

The edition is validated against SPEC.md section 6 and then rendered into
`site/index.html`, a snapshot at `site/archive/<date>.html` and the archive index
`site/archive.html`, with images optimised into `site/assets/<date>/`.

docs/SITE-CONTRACT.md is the binding element/class/attribute contract: every tag,
class and attribute below is emitted exactly as written there. Change the contract
first, never this file alone.

Markup is built in memory and installed through a .tmp file, so a failure never
leaves a half-written page behind. Console output is ASCII only.

Exit codes: 0 success (or CHECK OK), 1 validation or build failure.
"""

from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import io
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

try:  # optional at import time so --help never dies on a broken environment
    import requests
except Exception:  # pragma: no cover - declared dependency
    requests = None  # type: ignore[assignment]

try:
    from PIL import Image
except Exception:  # pragma: no cover - declared dependency
    Image = None  # type: ignore[assignment]

ACCENTS = ("amber", "coral", "rose", "sage", "teal", "sky", "gold", "clay")
LAYOUTS = ("hero-left", "hero-centre", "hero-stacked")
KINDS = ("lead", "story", "video", "quick", "quote")
BODY_KINDS = ("lead", "story", "video", "quick")
VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
RAW_TEXT_TAGS = frozenset(("script", "style"))
RESERVED_IDS = frozenset( {"top", "masthead", "paper", "progress", "progress-bar", "quick-hits", "quick-hits-title"}
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# No leading/trailing dash and no doubled dash, as the pattern enforces - the old error message
# quoted "[a-z0-9-]+", which told an agent its invalid id was valid and left no way to see why.
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_IMAGE_BYTES, MAX_IMAGE_WIDTH, JPEG_QUALITY = 8 * 1024 * 1024, 1400, 82
MAX_HTML_BYTES, TOC_LABEL_MAX, ARCHIVE_HEAD_MAX, REQUEST_TIMEOUT = 3 * 1024 * 1024, 42, 120, 20
USER_AGENT = ( "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_SETTINGS = {"edition_min_stories": 5, "edition_max_stories": 24, "keep_editions": 60}

_LINK_RE = re.compile(r"\[([^\[\]\n]+)\]\(([^()\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^\n]+?)\*\*")
_ITAL_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_TAG_TOKEN = re.compile( r"<!--.*?-->|<!DOCTYPE[^>]*>|<\?[^>]*>"
    r"|<(/?)([A-Za-z][A-Za-z0-9:-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)(/?)>", re.S | re.I,
)
_TAGS_ONLY = re.compile(r"<[^>]+>")
_ANCHOR_LINK_RE = re.compile(r"<a\s[^>]*href=", re.I)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ( "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December", )

class MarkupError(ValueError):
    """Raised when inline markup is unbalanced or unsafe."""

@dataclass
class Issue:
    hard: bool
    message: str

@dataclass
class Asset:
    rel: str
    width: int
    height: int

@dataclass
class Context:
    root: Path
    out_dir: Path
    edition_path: Path
    date_str: str
    captured: date_cls
    edition: dict[str, Any]
    settings: dict[str, Any]
    variant: tuple[str, str, str, str]
    assets: dict[str, Asset] = field(default_factory=dict)
    prefix: str = ""
    css_q: str = ""
    js_q: str = ""
    no_images: bool = False
    quiet: bool = False
    stats: dict[str, int] = field(default_factory=lambda: {"covered": 0, "suppressed": 0})

def _reconfigure_streams() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

def fail(message: str) -> int:
    print(f"BUILD FAIL: {message}", file=sys.stderr)
    return 1

def warn(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"WARN: {message}")

def ascii_safe(value: str) -> str:
    return value.encode("ascii", "replace").decode("ascii")

def attr(value: Any) -> str:
    return htmllib.escape("" if value is None else str(value), quote=True)

def text(value: Any) -> str:
    return htmllib.escape("" if value is None else str(value), quote=False)

def is_http(url: str) -> bool:
    return bool(re.match(r"^https?://[^\s]+$", url, re.I))

def host_of(url: str) -> str:
    match = re.match(r"^https?://([^/?#]+)", url, re.I)
    return match.group(1) if match else ""

def inline_errors(value: Any) -> list[str]:
    """Reject unbalanced **bold**, *italic* and [text](url) markers."""
    if not isinstance(value, str):
        return ["not a string"]
    problems: list[str] = []
    if value.count("**") % 2:
        problems.append("odd number of ** markers")
    if value.replace("**", "").count("*") % 2:
        problems.append("odd number of * markers")
    links = _LINK_RE.findall(value)
    if value.count("[") != len(links) or value.count("](") != len(links):
        problems.append("[ without ](url)")
    for _, url in links:
        if not is_http(htmllib.unescape(url)):
            problems.append(f"link is not http(s): {url[:50]}")
    return problems

def render_inline(value: Any, where: str = "") -> str:
    """Escape everything first, then apply only the three allowed transforms."""
    raw = "" if value is None else str(value)
    problems = inline_errors(raw)
    if problems:
        raise MarkupError(f"{where}: {'; '.join(problems)}")
    out = htmllib.escape(raw, quote=False)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = _ITAL_RE.sub(r"<em>\1</em>", out)

    def _link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        if not is_http(htmllib.unescape(url)):
            raise MarkupError(f"{where}: link is not http(s): {url[:50]}")
        return f'<a href="{attr(htmllib.unescape(url))}" rel="noopener">{label}</a>'

    return _LINK_RE.sub(_link, out)

def plain_text(value: Any) -> str:
    raw = "" if value is None else str(value)
    raw = _LINK_RE.sub(lambda m: m.group(1), raw)
    raw = _TAGS_ONLY.sub(" ", raw)
    return re.sub(r"\s+", " ", raw.replace("**", "").replace("*", "")).strip()

def truncate(value: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", value).strip()
    if len(flat) <= limit:
        return flat
    return flat[: max(1, limit - 3)].rstrip(" ,.;:-") + "..."

def slugify_id(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", ("" if value is None else str(value)).lower()).strip("-")

def priority_of(section: dict[str, Any]) -> float:
    value = section.get("priority")
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0

def parse_date(value: Any) -> date_cls | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

def long_date(day: date_cls) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"

def weekday_date(day: date_cls) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {long_date(day)}"

def humanise_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value.strip()
    return f"{stamp.day} {MONTHS[stamp.month - 1]} {stamp.year}, {stamp.hour:02d}:{stamp.minute:02d}"

def variant_for(date_str: str) -> tuple[str, str, str, str]:
    """The contract's date-seed rotation: accent, layout, scale, order."""
    seed = int(date_str.replace("-", ""))
    return ( ACCENTS[seed % len(ACCENTS)],
        LAYOUTS[(seed // 7) % len(LAYOUTS)], "a" if (seed // 11) % 2 == 0 else "b",
        "lead" if (seed // 13) % 2 == 0 else "rail", )

def load_settings(root: Path) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    try:
        payload = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(payload, dict):
        for key in DEFAULT_SETTINGS:
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                settings[key] = value
    return settings

def load_edition(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"edition not found: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"
    except ValueError as exc:
        return None, f"edition is not valid JSON: {path} ({exc})"
    if not isinstance(payload, dict):
        return None, f"edition root must be a JSON object: {path}"
    return payload, None

def read_memory_stats(root: Path, date_str: str = "") -> dict[str, int]:
    """Best-effort counts for the small print; never fatal."""
    stats = {"covered": 0, "suppressed": 0}
    db = root / "state" / "seen.sqlite"
    if db.exists():
        try:
            import sqlite3

            with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2) as conn:
                row = conn.execute("SELECT COUNT(*) FROM items").fetchone()
                stats["covered"] = int(row[0]) if row else 0
        except Exception:
            stats["covered"] = 0
    # "suppressed today" means the day's dropped candidates, not the number of editions on file:
    # collect writes them to suppressed.json, the only honest source for that phrase.
    if date_str:
        path = root / "state" / "workpack" / date_str / "suppressed.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("items") if isinstance(payload, dict) else None
            if isinstance(items, list):
                stats["suppressed"] = len(items)
        except (OSError, ValueError):
            pass
    return stats

# ---------------------------------------------------------------- validation

def _check_field(section: dict[str, Any], key: str, label: str, out: list[Issue], *, required: bool = False) -> None:
    """Presence (when required) plus inline-markup validity for one string field."""
    value = section.get(key)
    if value is None:
        if required:
            out.append(Issue(True, f"{label}: missing required key '{key}'"))
        return
    if not isinstance(value, str):
        out.append(Issue(True, f"{label}: '{key}' must be a string"))
        return
    if required and not value.strip():
        out.append(Issue(True, f"{label}: missing required key '{key}'"))
        return
    for problem in inline_errors(value):
        out.append(Issue(True, f"{label}: bad inline markup in '{key}' ({problem})"))

def _check_body(section: dict[str, Any], kind: str, label: str, out: list[Issue]) -> None:
    body = section.get("body")
    if body is None:
        if kind in BODY_KINDS:
            out.append(Issue(True, f"{label}: missing required key 'body'"))
        return
    paragraphs = body if isinstance(body, list) else [body]
    if kind in BODY_KINDS and not any(isinstance(p, str) and p.strip() for p in paragraphs):
        out.append(Issue(True, f"{label}: empty body"))
        return
    for index, para in enumerate(paragraphs):
        if not isinstance(para, str):
            out.append(Issue(True, f"{label}: body[{index}] must be a string"))
            continue
        for problem in inline_errors(para):
            out.append(Issue(True, f"{label}: bad inline markup in body[{index}] ({problem})"))

def _check_source(section: dict[str, Any], label: str, kind: str, out: list[Issue]) -> None:
    sticker = kind in ("lead", "story", "video", "quote")
    source = section.get("source")
    if not isinstance(source, dict):
        if sticker:
            out.append(Issue(True, f"{label}: story has no source.url"))
        return
    url = source.get("url")
    if not isinstance(url, str) or not url.strip():
        if sticker:
            out.append(Issue(True, f"{label}: story has no source.url"))
        return
    if not is_http(url):
        out.append(Issue(True, f"{label}: source.url is not http(s): {url[:60]}"))
    if "label" in source and not isinstance(source["label"], str):
        out.append(Issue(True, f"{label}: source.label must be a string"))

def _check_image(section: dict[str, Any], label: str, out: list[Issue]) -> None:
    image = section.get("image")
    if image is None:
        return
    if not isinstance(image, dict):
        out.append(Issue(True, f"{label}: 'image' must be an object"))
        return
    src = image.get("src")
    if not isinstance(src, str) or not src.strip():
        out.append(Issue(True, f"{label}: image.src is empty"))
        return
    # `config/interests.md` lists an uncredited image under NEVER, and the docs require all three,
    # but the validator only ever looked at src - so an uncredited image passed --check cleanly.
    alt = image.get("alt")
    if not isinstance(alt, str) or not alt.strip():
        out.append(Issue(False, f"{label}: image.alt is missing (accessibility + docs require it)"))
    credit = image.get("credit")
    if not isinstance(credit, str) or not credit.strip():
        out.append(Issue(False, f"{label}: image.credit is missing (an uncredited image is a NEVER item)"))

def _check_quick_hits(edition: dict[str, Any], issues: list[Issue]) -> None:
    hits = edition.get("quickHits")
    if hits is None:
        return
    if not isinstance(hits, list):
        issues.append(Issue(True, "edition 'quickHits' must be a list"))
        return
    for index, hit in enumerate(hits):
        if not isinstance(hit, dict):
            issues.append(Issue(True, f"quickHits[{index}] must be an object"))
            continue
        label = f"quickHits[{index}]"
        if not isinstance(hit.get("text"), str) or not hit["text"].strip():
            issues.append(Issue(True, f"{label}: missing 'text'"))
        elif inline_errors(hit["text"]):
            issues.append(Issue(True, f"{label}: bad inline markup in 'text'"))
        if not isinstance(hit.get("url"), str) or not hit["url"].strip():
            issues.append(Issue(True, f"{label}: missing 'url'"))
        elif not is_http(hit["url"]):
            issues.append(Issue(True, f"{label}: url is not http(s)"))

def _check_sections(sections: list[Any], issues: list[Issue]) -> None:
    seen: set[str] = set()
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            issues.append(Issue(True, f"sections[{index}] must be an object"))
            continue
        sid = section.get("id")
        label = f"sections[{index}]"
        if not isinstance(sid, str) or not sid.strip():
            issues.append(Issue(True, f"{label}: missing required key 'id'"))
        else:
            label = f"section '{sid}'"
            if not ID_RE.match(sid):
                issues.append(Issue(True, f"{label}: id must match [a-z0-9-]+"))
            elif sid in RESERVED_IDS:
                issues.append(Issue(True, f"{label}: id is reserved by the page skeleton"))
            elif sid in seen:
                issues.append(Issue(True, f"{label}: duplicate section id (anchors must be unique)"))
            seen.add(sid if isinstance(sid, str) else "")

        kind = section.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            issues.append(Issue(True, f"{label}: missing required key 'kind'"))
            continue
        if kind not in KINDS:
            issues.append(Issue(True, f"{label}: unknown kind '{kind}'"))
            continue
        _check_field(section, "headline", label, issues, required=kind in BODY_KINDS)
        _check_field(section, "standfirst", label, issues, required=kind in ("lead", "story", "video"))
        if kind == "quote":
            body = section.get("body")
            has_body = isinstance(body, list) and any(isinstance(p, str) and p.strip() for p in body)
            if not isinstance(section.get("headline"), str) and not has_body:
                issues.append(Issue(True, f"{label}: quote needs a headline or a body paragraph"))
        for key in ("whyItMatters", "aside"):
            _check_field(section, key, label, issues)
        _check_body(section, kind, label, issues)
        _check_source(section, label, kind, issues)
        _check_image(section, label, issues)

def validate_edition( edition: dict[str, Any], date_str: str, settings: dict[str, Any]
) -> tuple[list[Issue], list[str]]:
    """Return (issues, notes). Hard issues fail the build; notes only warn."""
    issues: list[Issue] = []
    notes: list[str] = []

    declared = edition.get("date")
    if not isinstance(declared, str) or not declared.strip():
        issues.append(Issue(True, "edition is missing the 'date' field"))
    elif parse_date(declared) is None:
        issues.append(Issue(True, f"edition date is not YYYY-MM-DD: {declared}"))
    elif declared != date_str:
        issues.append(Issue(True, f"date field '{declared}' disagrees with the edition date '{date_str}'"))

    for key in ("masthead", "tagline"):
        if not isinstance(edition.get(key), str) or not edition[key].strip():
            issues.append(Issue(True, f"edition is missing '{key}'"))
    if not isinstance(edition.get("number"), int) or isinstance(edition.get("number"), bool):
        notes.append("edition 'number' missing or not an integer - using 0")
    for key in ("weatherStrip", "signoff"):
        value = edition.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            issues.append(Issue(True, f"edition '{key}' must be a string"))
        else:
            for problem in inline_errors(value):
                issues.append(Issue(True, f"edition: bad inline markup in '{key}' ({problem})"))

    sections = edition.get("sections")
    if not isinstance(sections, list) or not sections:
        issues.append(Issue(True, "edition has no sections"))
        return issues, notes
    _check_sections(sections, issues)

    leads = [s for s in sections if isinstance(s, dict) and s.get("kind") == "lead"]
    if len(leads) > 1:
        issues.append(Issue(True, f"{len(leads)} sections are kind 'lead' - exactly one is allowed"))
    elif not leads:
        notes.append("no lead section - promoting the highest-priority section")
        candidates = [ s for s in order_sections(sections)
            if isinstance(s, dict) and s.get("kind") in ("story", "video")
        ]
        if candidates:
            candidates[0]["kind"] = "lead"

    _check_quick_hits(edition, issues)

    low = int(settings.get("edition_min_stories") or 0)
    high = int(settings.get("edition_max_stories") or 0)
    count = len(sections)
    if low and count < low:
        notes.append(f"only {count} sections, below edition_min_stories ({low})")
    if high and count > high:
        notes.append(f"{count} sections, above edition_max_stories ({high})")
    return issues, notes

def order_sections(sections: Sequence[Any]) -> list[dict[str, Any]]:
    """Priority descending, ties keep the original array order."""
    indexed = [(priority_of(s), -i, s) for i, s in enumerate(sections) if isinstance(s, dict)]
    indexed.sort(key=lambda triple: (triple[0], triple[1]), reverse=True)
    return [item for _, _, item in indexed]

def lead_of(sections: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    return next((s for s in sections if s.get("kind") == "lead"), None)

# ------------------------------------------------------------------- images

def _measure(path: Path) -> tuple[int, int] | None:
    if Image is None:
        return None
    try:
        with Image.open(path) as probe:
            return probe.width, probe.height
    except Exception:
        return None

def _optimise(raw: bytes) -> tuple[bytes, int, int] | None:
    """Verify, flatten to RGB, cap width at 1400 without upscaling, JPEG q82."""
    if Image is None:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            frame = source
            if frame.mode in ("RGBA", "LA", "P", "PA"):
                rgba = frame.convert("RGBA")
                canvas = Image.new("RGB", rgba.size, (11, 11, 13))
                canvas.paste(rgba, mask=rgba.split()[-1])
                frame = canvas
            elif frame.mode != "RGB":
                frame = frame.convert("RGB")
            if frame.width > MAX_IMAGE_WIDTH:
                height = max(1, round(frame.height * MAX_IMAGE_WIDTH / frame.width))
                frame = frame.resize((MAX_IMAGE_WIDTH, height), Image.LANCZOS)
            buffer = io.BytesIO()
            frame.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            return buffer.getvalue(), frame.width, frame.height
    except Exception:
        return None

def _download(url: str) -> tuple[bytes | None, str | None]:
    if requests is None:
        return None, "requests is not installed"
    try:
        response = requests.get( url,
            timeout=REQUEST_TIMEOUT, stream=True,
            headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"}, )
    except Exception as exc:
        return None, f"request failed ({type(exc).__name__})"
    with response:
        if response.status_code != 200:
            return None, f"http {response.status_code}"
        declared = response.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
            return None, "larger than 8 MB"
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_content(65536):
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    return None, "larger than 8 MB"
                chunks.append(chunk)
        except Exception as exc:
            return None, f"download aborted ({type(exc).__name__})"
    if not chunks:
        return None, "empty response body"
    return b"".join(chunks), None

def _source_bytes(src: str, edition_dir: Path) -> tuple[bytes | None, str | None]:
    if is_http(src):
        return _download(src)
    local = (edition_dir / src).resolve()
    if not local.exists():
        return None, "local file not found"
    if local.stat().st_size > MAX_IMAGE_BYTES:
        return None, "larger than 8 MB"
    try:
        return local.read_bytes(), None
    except OSError as exc:
        return None, f"cannot read local file ({type(exc).__name__})"

def build_assets(ctx: Context) -> None:
    """Resolve every section image into assets/<date>/; a failure only warns."""
    if ctx.no_images:
        return
    assets_dir = ctx.out_dir / "assets" / ctx.date_str
    for section in ctx.edition.get("sections", []):
        if not isinstance(section, dict):
            continue
        image = section.get("image")
        if not isinstance(image, dict):
            continue
        src = image.get("src")
        if not isinstance(src, str) or not src.strip():
            continue
        sid = str(section.get("id") or "")
        slug = slugify_id(image.get("slug") or sid or "image") or "image"
        key = src if is_http(src) else str((ctx.edition_path.parent / src).resolve())
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
        target = assets_dir / f"{slug}-{digest}.jpg"
        if target.exists():  # same source already cached on disk: no download
            size = _measure(target)
            if size:
                ctx.assets[sid] = Asset(f"assets/{ctx.date_str}/{target.name}", *size)
                continue
        raw, problem = _source_bytes(src, ctx.edition_path.parent)
        if raw is None:
            warn(f"image skipped {sid or slug}: {problem}", ctx.quiet)
            continue
        optimised = _optimise(raw)
        if optimised is None:
            warn(f"image skipped {sid or slug}: not a valid image", ctx.quiet)
            continue
        payload, width, height = optimised
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".jpg.tmp")
            tmp.write_bytes(payload)
            tmp.replace(target)
        except OSError as exc:
            warn(f"image skipped {sid or slug}: cannot write asset ({type(exc).__name__})", ctx.quiet)
            continue
        ctx.assets[sid] = Asset(f"assets/{ctx.date_str}/{target.name}", width, height)

def asset_query(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()[:8]
    except OSError:
        return ""

# ------------------------------------------------------------------ render

def render_masthead(ctx: Context, *, title: str | None = None, tagline: str | None = None) -> str:
    edition = ctx.edition
    number = edition.get("number") if isinstance(edition.get("number"), int) else 0
    bits = [ '<header class="masthead" id="masthead">',
        '<div class="masthead__rule masthead__rule--thick"></div>', '<div class="masthead__rule"></div>',
        f'<p class="masthead__ear masthead__ear--left">No. {number}</p>',
        f'<p class="masthead__ear masthead__ear--right">{text(weekday_date(ctx.captured))}</p>',
        f'<h1 class="masthead__title">{text(title or edition.get("masthead") or "THE DAILY BEACON")}</h1>',
        f'<p class="masthead__tagline">{text(tagline or edition.get("tagline"))}</p>',
        '<div class="masthead__rule"></div>', '<div class="masthead__rule masthead__rule--thick"></div>',
    ]
    weather = edition.get("weatherStrip")
    if title is None and isinstance(weather, str) and weather.strip():
        bits.append(f'<p class="masthead__weather">{text(weather)}</p>')
    bits.append("</header>")
    return "\n".join(bits)

def render_toc(ordered: Sequence[dict[str, Any]]) -> str:
    items = []
    for section in ordered:
        kicker = section.get("kicker")
        kicker_text = kicker if isinstance(kicker, str) and kicker.strip() else str(section.get("kind", ""))
        label = truncate(plain_text(section.get("headline")), TOC_LABEL_MAX)
        items.append(
            f'<li><a class="toc__link" href="#{attr(section.get("id"))}">'
            f'<span class="toc__kicker">{text(kicker_text)}</span>'
            f'<span class="toc__label">{text(label)}</span></a></li>'
        )
    return ( '<nav class="toc" aria-label="In this edition">\n<ul class="toc__list">\n'
        + "\n".join(items)
        + "\n</ul>\n</nav>"
    )

def render_media(ctx: Context, section: dict[str, Any], lead: bool = False) -> str:
    if ctx.no_images:
        return ""
    asset = ctx.assets.get(str(section.get("id")))
    if asset is None:
        return ""
    image = section.get("image") if isinstance(section.get("image"), dict) else {}
    alt = image.get("alt")
    if not isinstance(alt, str) or not alt.strip():
        alt = plain_text(section.get("headline")) or "Illustration for this story"
    classes = "media media--lead" if lead else "media"
    parts = [ f'<figure class="{classes}">',
        f'<div class="media__box" style="--ar:{asset.width}/{asset.height}">',
        f'<img class="media__img" src="{attr(ctx.prefix + asset.rel)}" alt="{attr(alt)}" '
        f'loading="lazy" decoding="async" width="{asset.width}" height="{asset.height}">', "</div>",
    ]
    credit = image.get("credit")
    if isinstance(credit, str) and credit.strip():
        parts.append(f'<figcaption class="media__credit">{text(credit)}</figcaption>')
    parts.append("</figure>")
    return "\n".join(parts)

def render_body_block(section: dict[str, Any], css_class: str = "body") -> str:
    body = section.get("body")
    paragraphs = body if isinstance(body, list) else [body] if body else []
    rendered = [ f"<p>{render_inline(para, 'body')}</p>"
        for para in paragraphs
        if isinstance(para, str) and para.strip()
    ]
    if not rendered:
        return ""
    return f'<div class="{css_class}">\n' + "\n".join(rendered) + "\n</div>"

def render_tail(section: dict[str, Any], body_class: str = "body") -> list[str]:
    """Body, whymatters, aside, source line - the exact contract order."""
    out = []
    body = render_body_block(section, body_class)
    if body:
        out.append(body)
    why = section.get("whyItMatters")
    if isinstance(why, str) and why.strip():
        out.append( '<p class="whymatters"><span class="whymatters__label">Why it matters</span> '
            f"{render_inline(why, 'whyItMatters')}</p>"
        )
    aside = section.get("aside")
    if isinstance(aside, str) and aside.strip():
        out.append(f'<p class="aside">{render_inline(aside, "aside")}</p>')
    source = render_source_line(section)
    if source:
        out.append(source)
    return out

def render_source_line(section: dict[str, Any]) -> str:
    source = section.get("source") if isinstance(section.get("source"), dict) else {}
    url = source.get("url")
    if not isinstance(url, str) or not url.strip():
        return ""
    label = source.get("label")
    if not isinstance(label, str) or not label.strip():
        label = host_of(url) or "Source"
    return ( f'<p class="source-line"><a class="source" href="{attr(url)}" '
        f'target="_blank" rel="noopener">{text(label)}</a></p>'
    )

def _kicker(section: dict[str, Any]) -> str:
    kicker = section.get("kicker")
    return f'<p class="kicker">{text(kicker)}</p>' if isinstance(kicker, str) and kicker.strip() else ""

def _headline(section: dict[str, Any], tag: str, css: str, *, new_tab: bool = True) -> str:
    source = section.get("source") if isinstance(section.get("source"), dict) else {}
    url = source.get("url") if isinstance(source.get("url"), str) else ""
    label = render_inline(section.get("headline"), "headline")
    if not url:
        return f'<{tag} class="{css}">{label}</{tag}>'
    extra = ' target="_blank" rel="noopener"' if new_tab else ""
    return f'<{tag} class="{css}"><a href="{attr(url)}"{extra}>{label}</a></{tag}>'

def render_article(ctx: Context, section: dict[str, Any], *, lead: bool = False) -> str:
    """One article. The contract fixes the order of its children per kind."""
    kind = section.get("kind")
    sid = attr(section.get("id"))
    if lead:
        classes = f"lead lead--{ctx.variant[1]}"
    elif kind == "video":
        classes = "story card card--video"
    elif kind == "quick":
        classes = "story story--brief"
    else:
        classes = "story"
    kicker = section.get("kicker")
    parts = [f'<article class="{classes}" id="{sid}">']
    if isinstance(kicker, str) and kicker.strip():
        parts.append(f'<p class="kicker">{text(kicker)}</p>')
    if lead:  # the lead headline is the in-page hero, so it does not open a new tab
        parts.append(_headline(section, "h2", "lead__headline", new_tab=False))
    elif kind == "video":  # media first, headline links straight to the video
        media = render_media(ctx, section)
        if media:
            parts.append(media)
        parts.append(_headline(section, "h2", "story__headline"))
    else:
        parts.append(_headline(section, "h2", "story__headline"))
    standfirst = section.get("standfirst")
    if isinstance(standfirst, str) and standfirst.strip():
        parts.append(f'<p class="standfirst">{render_inline(standfirst, "standfirst")}</p>')
    if not lead and kind != "video":
        media = render_media(ctx, section)
        if media:
            parts.append(media)
    if lead:
        media = render_media(ctx, section, lead=True)
        if media:
            parts.append(media)
    parts += render_tail(section, "lead__body body" if lead else "body")
    parts.append("</article>")
    return "\n".join(parts)

def render_quote(section: dict[str, Any]) -> str:
    body = section.get("body")
    paragraph = ""
    if isinstance(body, list):
        paragraph = next((item for item in body if isinstance(item, str) and item.strip()), "")
    elif isinstance(body, str):
        paragraph = body
    headline = section.get("headline") if isinstance(section.get("headline"), str) else ""
    quote_text = headline.strip() or paragraph.strip()
    source = section.get("source") if isinstance(section.get("source"), dict) else {}
    cite = source.get("label") if isinstance(source.get("label"), str) else ""
    cite = cite or host_of(str(source.get("url", "")))
    parts = [ f'<blockquote class="pullquote" id="{attr(section.get("id"))}">',
        f'<p class="pullquote__text">{render_inline(quote_text, "quote")}</p>', ]
    if cite:
        parts.append(f'<footer class="pullquote__cite">{text(cite)}</footer>')
    parts.append("</blockquote>")
    return "\n".join(parts)

def render_quick_hits(edition: dict[str, Any]) -> str:
    hits = edition.get("quickHits")
    if not isinstance(hits, list):
        return ""
    # The list item already carries the anchor, so hit text is flat: no nested <a>.
    items = [ f'<li><a href="{attr(hit.get("url"))}" target="_blank" rel="noopener">'
        f'{text(plain_text(hit.get("text")))}</a></li>'
        for hit in hits
        if isinstance(hit, dict) and isinstance(hit.get("url"), str)
    ]
    if not items:
        return ""
    return ( '<aside class="quick-hits" id="quick-hits" aria-labelledby="quick-hits-title">\n'
        '<h2 class="quick-hits__title" id="quick-hits-title">Quick Hits</h2>\n'
        '<ul class="quick-hits__list">\n' + "\n".join(items) + "\n</ul>\n</aside>"
    )

def render_main(ctx: Context) -> str:
    ordered = order_sections(ctx.edition.get("sections", []))
    lead = lead_of(ordered)
    bodies: list[str] = []
    if lead is not None:
        bodies.append(render_article(ctx, lead, lead=True))
    rail = ctx.variant[3] == "rail"
    hits = render_quick_hits(ctx.edition)
    if rail and hits:  # order-rail puts Quick Hits before the first non-lead story
        bodies.append(hits)
        hits = ""
    for section in ordered:
        if section is lead:
            continue
        if section.get("kind") == "quote":
            bodies.append(render_quote(section))
        elif section.get("kind") in ("story", "video", "quick"):
            bodies.append(render_article(ctx, section))
    if hits:
        bodies.append(hits)
    return '<main class="paper" id="paper">\n' + "\n\n".join(bodies) + "\n</main>"

def render_colophon(ctx: Context, *, prefix: str | None = None) -> str:
    edition = ctx.edition
    sections = [s for s in edition.get("sections", []) if isinstance(s, dict)]
    stories = sum(1 for s in sections if s.get("kind") in ("lead", "story", "video"))
    hits = edition.get("quickHits")
    quick_count = len(hits) if isinstance(hits, list) else 0
    number = edition.get("number") if isinstance(edition.get("number"), int) else 0
    keep = int(ctx.settings.get("keep_editions") or 30)
    base = ctx.prefix if prefix is None else prefix
    parts = [ '<footer class="colophon">',
        '<div class="colophon__rule"></div>', '<ul class="colophon__meta">',
        f"<li>Edition {number}</li>", f"<li>Generated {text(humanise_timestamp(edition.get('generatedAt')))}</li>",
        f"<li>{stories} stories, {quick_count} quick hits</li>",
        f"<li>{ctx.stats['covered']} items tracked, {ctx.stats['suppressed']} suppressed today</li>", "</ul>",
    ]
    signoff = edition.get("signoff")
    if isinstance(signoff, str) and signoff.strip():
        parts.append(f'<p class="colophon__signoff">{render_inline(signoff, "signoff")}</p>')
    parts += [ '<p class="colophon__archive">Previous '
        f'{keep} editions are archived at <a href="{attr(base)}archive.html">archive.html</a>.</p>',
        '<p class="colophon__fine">Compiled automatically at 03:00 from public feeds and '
        "creators' uploads. No story is invented; every item links to its source.</p>", "</footer>",
    ]
    return "\n".join(parts)

def document( *,
    title: str, accent: str,
    classes: str, header: str,
    nav: str, main: str,
    colophon: str, body_class: str,
    css_url: str, js_url: str,
    description: str, og_image: str = "",
    prefix: str = "",
) -> str:
    """Assemble one complete page. Element order follows SITE-CONTRACT section 2."""
    body_attr = f' class="{body_class}"' if body_class else ""
    meta = [ f'<meta property="og:title" content="{attr(title)}">',
        f'<meta property="og:description" content="{attr(description)}">',
        '<meta property="og:type" content="website">', ]
    if og_image:
        meta.append(f'<meta property="og:image" content="{attr(og_image)}">')
    chunks = [ "<!DOCTYPE html>",
        f'<html lang="en" data-accent="{accent}" class="{classes}">', "<head>",
        '<meta charset="utf-8">', '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="color-scheme" content="dark light">', f"<title>{text(title)}</title>",
        # without this the phone paints a white status bar above a near-black page
        '<meta name="theme-color" content="#131516">',
        f'<meta name="description" content="{attr(description)}">',
        f'<link rel="icon" href="{attr(prefix)}favicon.svg" type="image/svg+xml">',
        f'<link rel="apple-touch-icon" href="{attr(prefix)}favicon.svg">',
        f'<link rel="stylesheet" href="{attr(css_url)}">',
        *meta, "</head>",
        f'<body id="top"{body_attr}>', '<div id="progress" aria-hidden="true"><span id="progress-bar"></span></div>',
        "", header,
        "", nav,
        "", main,
        "", colophon,
        "",
        '<a class="to-top" href="#top" aria-label="Back to top">Top</a>',
        f'<script src="{attr(js_url)}" defer></script>', "</body>",
        "</html>", "",
    ]
    return "\n".join(chunk for chunk in chunks if chunk != "")

def build_page(ctx: Context, *, prefix: str) -> str:
    ctx.prefix = prefix
    edition = ctx.edition
    accent, layout, scale, order = ctx.variant
    ordered = order_sections(edition.get("sections", []))
    css_url = prefix + ("style.css?v=" + ctx.css_q if ctx.css_q else "style.css")
    js_url = prefix + ("app.js?v=" + ctx.js_q if ctx.js_q else "app.js")
    og = ""
    lead = lead_of(ordered)
    if lead is not None:
        image = lead.get("image")
        if isinstance(image, dict) and isinstance(image.get("src"), str) and is_http(image["src"]):
            og = image["src"]
    return document( prefix=ctx.prefix, title=f'{edition.get("masthead") or "THE DAILY BEACON"} - {long_date(ctx.captured)}',
        accent=accent, classes=f"layout-{layout} scale-{scale} order-{order}",
        header=render_masthead(ctx), nav=render_toc(ordered),
        main=render_main(ctx), colophon=render_colophon(ctx),
        body_class="", css_url=css_url,
        js_url=js_url, description=str(edition.get("tagline") or ""),
        og_image=og, )

def lead_headline_of(markup: str) -> str:
    """Tolerant scrape of the first lead headline from a snapshot."""
    match = re.search(r'<h2 class="lead__headline">(.*?)</h2>', markup, re.S | re.I)
    if not match:
        return "Edition"
    flat = re.sub(r"\s+", " ", htmllib.unescape(_TAGS_ONLY.sub(" ", match.group(1)))).strip()
    return truncate(flat, ARCHIVE_HEAD_MAX) or "Edition"

def prune_archive(out_dir: Path, entries: list, keep: int, current: str) -> list:
    """Drop the oldest snapshots past `keep`, and delete their files.

    The colophon has always claimed "previous N editions are archived" but nothing ever rotated,
    so the folder grew forever and the claim quietly became false. Deleting is scoped to
    site/archive/*.html only - never an edition file in editions/, which is the source of truth.
    """
    if keep <= 0 or len(entries) <= keep:
        return entries
    keep_dates = {str(e.get("date")) for e in entries[:keep]} | {current}
    folder = out_dir / "archive"
    if folder.is_dir():
        for path in folder.glob("*.html"):
            if path.stem not in keep_dates:
                try:
                    path.unlink()
                except OSError:
                    pass
    return entries[:keep]


def collect_archive(out_dir: Path, current: str, current_html: str) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    folder = out_dir / "archive"
    if folder.is_dir():
        for path in folder.glob("*.html"):
            if parse_date(path.stem) is None:
                continue
            try:
                seen[path.stem] = lead_headline_of(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                seen[path.stem] = "Edition"
    seen[current] = lead_headline_of(current_html)
    return sorted(seen.items(), key=lambda pair: pair[0], reverse=True)

def render_archive_page(ctx: Context, entries: Sequence[tuple[str, str]], *, prefix: str) -> str:
    accent, layout, scale, order = ctx.variant
    css_url = prefix + ("style.css?v=" + ctx.css_q if ctx.css_q else "style.css")
    js_url = prefix + ("app.js?v=" + ctx.js_q if ctx.js_q else "app.js")
    items = []
    for day, headline in entries:
        stamp = parse_date(day)
        label = weekday_date(stamp) if stamp else day
        items.append( f'<li class="archive__item"><a class="archive__link" '
            f'href="{attr(prefix)}archive/{attr(day)}.html">'
            f'<span class="archive__date">{text(label)}</span>'
            f'<span class="archive__head">{text(headline)}</span></a></li>'
        )
    if not items:
        items.append( '<li class="archive__item"><span class="archive__head">No editions archived yet.</span></li>'
        )
    main = '<main class="paper archive">\n<ul class="archive__list">\n' + "\n".join(items) + "\n</ul>\n</main>"
    return document( prefix=prefix, title="THE DAILY BEACON - Archive",
        accent=accent, classes=f"layout-{layout} scale-{scale} order-{order}",
        header=render_masthead(ctx, title="THE DAILY BEACON", tagline="Archive"), nav="",
        main=main, colophon=render_colophon(ctx, prefix=prefix),
        body_class="page-archive", css_url=css_url,
        js_url=js_url, description="Every archived Daily Beacon edition, newest first.",
    )

def check_tag_balance(markup: str) -> str | None:
    """Stack check over the emitted markup; returns an error string or None."""
    stack: list[str] = []
    skip_until = ""
    for match in _TAG_TOKEN.finditer(markup):
        closing, name, _, self_closing = match.groups()
        if name is None:
            continue
        tag = name.lower()
        if skip_until:
            if closing and tag == skip_until:
                skip_until = ""
                if stack and stack[-1] == tag:
                    stack.pop()
            continue
        if tag in RAW_TEXT_TAGS and not closing:
            skip_until = tag
            stack.append(tag)
            continue
        if tag in VOID_TAGS or self_closing:
            continue
        if closing:
            if not stack:
                return f"unbalanced tag </{tag}> with no opener"
            opened = stack.pop()
            if opened != tag:
                return f"unbalanced tag: <{opened}> closed by </{tag}>"
        else:
            stack.append(tag)
    return f"unbalanced tag: <{stack[-1]}> never closed" if stack else None

def verify_markup(markup: str, sections: Sequence[dict[str, Any]]) -> str | None:
    """Tag balance, unique section anchors, resolving toc links, size ceiling."""
    problem = check_tag_balance(markup)
    if problem:
        return problem
    for section in sections:
        sid = str(section.get("id"))
        count = len(re.findall(rf'id="{re.escape(sid)}"', markup))
        if count != 1:
            return f"section id '{sid}' appears {count} times (expected exactly once)"
    for href in re.findall(r'href="#([^"]+)"', markup):
        if href != "top" and not re.search(rf'id="{re.escape(href)}"', markup):
            return f"toc href '#{href}' has no matching id"
    size = len(markup.encode("utf-8"))
    if size > MAX_HTML_BYTES:
        return f"html is {size} bytes without images, limit is {MAX_HTML_BYTES}"
    return None

def write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    tmp.replace(path)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser( prog="build_edition.py",
        description="Build the Daily Beacon static site from one edition JSON file.",
        epilog="Exit codes: 0 success or CHECK OK, 1 validation or build failure.", )
    parser.add_argument("--date", help="edition date, YYYY-MM-DD (default: today, local)")
    parser.add_argument("--edition", help="path to the edition JSON (default: editions/<date>.json)")
    parser.add_argument("--out-dir", help="site output directory (default: site)")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="project root")
    parser.add_argument("--check", action="store_true", help="validate only, write nothing")
    parser.add_argument("--fixture", action="store_true", help="build fixtures/edition-fixture.json")
    parser.add_argument("--no-images", action="store_true", help="emit no figure elements at all")
    parser.add_argument("--quiet", action="store_true", help="suppress WARN lines")
    return parser

def resolve_targets(args: argparse.Namespace) -> tuple[Path, Path, str] | None:
    """(edition path, out dir, date string) or None when the arguments are unusable."""
    root = Path(args.root).resolve()
    date_str = args.date or date_cls.today().isoformat()
    if args.date and parse_date(args.date) is None:
        fail(f"--date must be YYYY-MM-DD, got '{args.date}'")
        return None

    if args.fixture:
        edition_path = Path(args.edition) if args.edition else root / "fixtures" / "edition-fixture.json"
        out_dir = Path(args.out_dir) if args.out_dir else root / "site" / "_fixture"
        if not edition_path.exists():
            fail(f"fixture edition not found: {edition_path}")
            return None
        if not args.date:  # take the fixture's own date so the filename check passes
            payload, problem = load_edition(edition_path)
            declared = payload.get("date") if problem is None and payload else None
            if parse_date(declared):
                date_str = str(declared)
    else:
        edition_path = Path(args.edition) if args.edition else root / "editions" / f"{date_str}.json"
        out_dir = Path(args.out_dir) if args.out_dir else root / "site"
        if args.edition and not args.date:
            # "--edition path/to/2026-10-20.json" is the documented way to rebuild an older edition
            # by hand. Comparing it against TODAY made every re-build of a past edition fail
            # validation, so the file's own date wins when no --date was passed.
            if not edition_path.is_absolute():
                edition_path = (Path.cwd() / edition_path).resolve()
            payload, problem = load_edition(edition_path)
            declared = payload.get("date") if problem is None and payload else None
            if parse_date(declared):
                date_str = str(declared)

    if not edition_path.is_absolute():
        edition_path = (Path.cwd() / edition_path).resolve()
    if not out_dir.is_absolute():
        out_dir = (root / out_dir).resolve()
    return edition_path, out_dir, date_str

def run_check(edition: dict[str, Any], issues: Sequence[Issue], notes: Sequence[str]) -> int:
    hard = [issue for issue in issues if issue.hard]
    soft = [issue for issue in issues if not issue.hard]
    for issue in hard:
        print(f"CHECK FAIL: {ascii_safe(issue.message)}")
    # soft issues used to be collected and then dropped on the floor, so a missing image credit
    # passed silently. They do not fail the build, but the agent has to be able to see them.
    for issue in soft:
        print(f"CHECK WARN: {ascii_safe(issue.message)}")
    for note in notes:
        print(f"WARN: {ascii_safe(note)}")
    if hard:
        print(f"CHECK FAILED: {len(hard)} problems")
        return 1
    sections = edition.get("sections")
    hits = edition.get("quickHits")
    print( f"CHECK OK: {len(sections) if isinstance(sections, list) else 0} sections, "
        f"{len(hits) if isinstance(hits, list) else 0} quick hits"
    )
    return 0

def make_context( root: Path,
    edition_path: Path, out_dir: Path,
    date_str: str, edition: dict[str, Any],
    settings: dict[str, Any], args: argparse.Namespace,
) -> Context:
    ctx = Context( root=root,
        out_dir=out_dir, edition_path=edition_path,
        date_str=date_str, captured=parse_date(date_str) or date_cls.today(),
        edition=edition, settings=settings,
        variant=variant_for(date_str), no_images=args.no_images,
        quiet=args.quiet, )
    ctx.css_q = asset_query(out_dir / "style.css")
    ctx.js_q = asset_query(out_dir / "app.js")
    ctx.stats = read_memory_stats(root, date_str)
    return ctx

def report(ctx: Context, markup: str, archived: int) -> int:
    sections = [s for s in ctx.edition.get("sections", []) if isinstance(s, dict)]
    hits = ctx.edition.get("quickHits")
    if not ctx.quiet:
        print( f"variant: accent={ctx.variant[0]} layout={ctx.variant[1]} "
            f"scale={ctx.variant[2]} order={ctx.variant[3]}"
        )
        print(f"archive: {archived} snapshots indexed in archive.html")
    print( f"build done: {ctx.date_str} - {len(sections)} sections, {len(ctx.assets)} images, "
        f"{(ctx.out_dir / 'index.html').stat().st_size} bytes, "
        f"{len(_ANCHOR_LINK_RE.findall(markup))} links"
    )
    return 0

def build_site(args: argparse.Namespace) -> int:
    targets = resolve_targets(args)
    if targets is None:
        return 1
    edition_path, out_dir, date_str = targets
    root = Path(args.root).resolve()

    edition, problem = load_edition(edition_path)
    if edition is None:
        return fail(problem or "cannot load edition")

    settings = load_settings(root)
    issues, notes = validate_edition(edition, date_str, settings)
    if args.check:
        return run_check(edition, issues, notes)
    hard = [issue for issue in issues if issue.hard]
    if hard:
        for issue in hard:
            print(f"CHECK FAIL: {ascii_safe(issue.message)}", file=sys.stderr)
        return fail(f"{len(hard)} validation problems in {edition_path.name}")
    for note in notes:
        warn(note, args.quiet)

    ctx = make_context(root, edition_path, out_dir, date_str, edition, settings, args)
    build_assets(ctx)
    sections = [s for s in edition.get("sections", []) if isinstance(s, dict)]
    try:
        live_html = build_page(ctx, prefix="")
        snapshot_html = build_page(ctx, prefix="../")
    except MarkupError as exc:
        return fail(f"bad inline markup - {exc}")

    for label, markup in (("index.html", live_html), ("snapshot", snapshot_html)):
        problem = verify_markup(markup, sections)
        if problem:
            return fail(f"{label} self-check failed: {problem}")

    entries = collect_archive(out_dir, date_str, live_html)
    entries = prune_archive(out_dir, entries, int(ctx.settings.get("keep_editions") or 30), date_str)
    archive_html = render_archive_page(ctx, entries, prefix="")
    problem = check_tag_balance(archive_html)
    if problem:
        return fail(f"archive.html self-check failed: {problem}")

    try:
        write_text(out_dir / "archive" / f"{date_str}.html", snapshot_html)
        write_text(out_dir / "index.html", live_html)
        write_text(out_dir / "archive.html", archive_html)
    except OSError as exc:
        return fail(f"cannot write site files: {exc}")
    return report(ctx, live_html, len(entries))

def main(argv: Sequence[str] | None = None) -> int:
    _reconfigure_streams()
    try:
        return build_site(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        return fail("interrupted")

if __name__ == "__main__":
    raise SystemExit(main())
