#!/usr/bin/env python3
"""news_source.py - RSS feeds -> normalised, de-duplicated news candidates.

One RSS GET per feed (browser UA, 20s timeout), feedparser over the raw bytes so the HTTP status is
ours to report. A dead feed is data, never a crash: it is counted, not raised.

Pipeline: fetch -> filter to the lookback window -> normalise to the canonical news item ->
de-duplicate (url key, normalised title, or Jaccard >= 0.8 on significant words) -> sort
(weight desc, publishedAt desc) -> cap 4 per sourceName -> cap overall -> optional og:image top-up.

Decisions the contract leaves open, and how they are settled here:
  - Undated entries are KEPT with publishedAt = null. Dropping them silently would lose whole feeds
    whose date format feedparser cannot read. They sort after dated items of the same weight.
  - The og:image lazy fetch is a last resort only: the cheap sources (media:*, image enclosure,
    first <img> in the summary) are tried first, and at most OG_BUDGET requests leave the process
    per run, each with an 8s timeout, failures silent. It never blocks the run, never raises.
  - De-duplication matches on the memory.py canonical-url family, so the url keys written here are
    the same keys memory.py derives from the item url later.

CLI: python scripts/news_source.py --out state/workpack/<date>/news.json [--hours 50] [--limit N] [--root PATH]
Last stdout line: news_source done: <n> articles from <ok>/<total> feeds (<failed> failed)
Exit 0 when at least one feed works; non-zero + one stderr line only when feeds.json is unreadable or
every feed fails. No image is downloaded here - run_daily.py owns that.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

try:
    import feedparser
    import requests
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - environment problem, one line, non-zero
    print("news_source: requests, feedparser and beautifulsoup4 are required", file=sys.stderr)
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
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*",
    "Accept-Language": "en-GB,en;q=0.9",
}
FEED_TIMEOUT = 20
OG_TIMEOUT = 8
OG_BUDGET = 10
DEFAULT_HOURS = 50
DEFAULT_MAX_NEWS = 60
MAX_PER_SOURCE = 4
SUMMARY_MAX = 600
MAX_TOPIC_TAGS = 3
JACCARD_MIN = 0.8

PUNCT_RE = re.compile(r"[^a-z0-9]+")
IMG_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|avif)(?:\?|$)", re.IGNORECASE)

# same family as scripts/memory.py - kept in sync by hand (memory.py is not imported, it opens sqlite)
TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "ref", "referrer", "source",
    "mc_cid", "mc_eid", "igshid", "s", "xtor", "cmpid", "si", "feature",
    "spm", "yclid", "gbraid", "wbraid", "_ga", "at_medium", "at_campaign",
    "ito", "ncid", "smid", "smtyp", "sr_share", "share", "share_id",
    "__twitter_impression", "oly_anon_id", "oly_enc_id", "trk", "trkcampaign",
    "sc_cid",
}

STOPWORDS = {
    "about", "after", "again", "against", "along", "among", "another", "because", "been", "before",
    "behind", "being", "below", "between", "both", "could", "does", "doing", "down", "during", "each",
    "every", "from", "gets", "goes", "have", "having", "here", "hers", "into", "itself", "just",
    "like", "made", "make", "many", "more", "most", "much", "must", "near", "need", "only", "other",
    "over", "same", "should", "since", "some", "such", "than", "that", "their", "them", "then",
    "there", "these", "they", "this", "those", "through", "under", "until", "very", "want", "were",
    "what", "when", "where", "which", "while", "will", "with", "within", "without", "would", "your",
    "yours", "says", "said", "also", "even", "first", "last", "next", "back", "best",
    "news", "week", "year", "today", "still", "already", "review", "update", "updates",
}


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso(dt):
    if dt is None:
        return None
    return dt.astimezone().isoformat(timespec="seconds")


def project_root(explicit=None) -> Path:
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


def ascii_safe(text) -> str:
    """Console output must stay ASCII on any code page."""
    s = str(text if text is not None else "")
    return s.encode("ascii", "replace").decode("ascii")


def collapse(text) -> str:
    return " ".join(PUNCT_RE.sub(" ", str(text or "").lower()).split())


def canonical_url(url: str) -> str:
    """memory.py-compatible canonical form: no scheme, no www, sorted kept params, punctuation gone."""
    if not url:
        return ""
    raw = str(url).strip().lower()
    parts = urlsplit(raw if "://" in raw else "http://" + raw)
    host = parts.netloc
    if host.startswith("www."):
        host = host[4:]
    kept = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        kl = k.lower()
        if kl.startswith("utm_") or kl in TRACKING_PARAMS:
            continue
        kept.append((kl, v))
    kept.sort()
    joined = host + " " + parts.path
    if kept:
        joined += " " + " ".join("%s %s" % (k, v) for k, v in kept)
    return collapse(joined)


def sha16(text: str) -> str:
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:16]


def significant_words(text) -> list:
    return [w for w in collapse(text).split() if len(w) >= 4 and w not in STOPWORDS]


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def clean_html(raw, limit: int = SUMMARY_MAX) -> str:
    """Strip tags with BeautifulSoup, collapse whitespace, cut on a word boundary (no ellipsis)."""
    txt = str(raw or "")
    if not txt:
        return ""
    try:
        txt = BeautifulSoup(txt, "html.parser").get_text(" ")
    except Exception:
        txt = re.sub(r"<[^>]+>", " ", txt)
    txt = " ".join(txt.split())
    if len(txt) <= limit:
        return txt
    cut = txt[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" ,;:-")


def parse_date(entry):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(key) if hasattr(entry, "get") else None
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc).astimezone()
            except Exception:
                pass
    for key in ("published", "updated", "created", "dc_date"):
        txt = entry.get(key) if hasattr(entry, "get") else None
        if not txt:
            continue
        s = str(txt).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone()
        except Exception:
            pass
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone()
            except Exception:
                continue
    return None


def first_img_from_html(raw):
    txt = str(raw or "")
    if not txt:
        return None
    try:
        soup = BeautifulSoup(txt, "html.parser")
        for tag in soup.find_all("img"):
            src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
            if src and str(src).strip():
                return str(src).strip()
    except Exception:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', txt, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def pick_cheap_image(entry, summary_html: str):
    """media:content / media:thumbnail / image enclosure / first <img> in the summary. No network."""
    for key in ("media_content", "media_thumbnail"):
        val = entry.get(key) if hasattr(entry, "get") else None
        if isinstance(val, list):
            for it in val:
                if isinstance(it, dict) and it.get("url"):
                    return str(it["url"]).strip()
        elif isinstance(val, dict) and val.get("url"):
            return str(val["url"]).strip()
    for enc in entry.get("enclosures", []) or []:
        if not isinstance(enc, dict):
            continue
        href = str(enc.get("href") or enc.get("url") or "").strip()
        if not href:
            continue
        ctype = str(enc.get("type") or "")
        if ctype.startswith("image/") or IMG_RE.search(href):
            return href
    for link in entry.get("links", []) or []:
        if not isinstance(link, dict):
            continue
        href = str(link.get("href") or "").strip()
        ctype = str(link.get("type") or "")
        if href and link.get("rel") == "enclosure" and ctype.startswith("image/"):
            return href
    return first_img_from_html(summary_html)


def og_image(url: str):
    """Last resort: one cheap GET for <meta property="og:image">. Silent on any failure."""
    if not url:
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=OG_TIMEOUT, allow_redirects=True)
        if r.status_code != 200:
            return None
        text = r.text[:300000]
    except Exception:
        return None
    try:
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.find_all("meta"):
            prop = str(tag.get("property") or tag.get("name") or "").lower()
            if prop in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image"):
                content = tag.get("content")
                if content and str(content).strip():
                    return str(content).strip()
    except Exception:
        return None
    return None


def topic_tags(title: str, already) -> list:
    """Up to 3 mechanical tags from the headline: words >= 4 chars, not stopwords, first occurrence."""
    have = {str(t).lower() for t in already}
    out = []
    for w in significant_words(title):
        if w in have or w in out:
            continue
        out.append(w)
        if len(out) >= MAX_TOPIC_TAGS:
            break
    return out


def fetch_feed(feed: dict, window_start: datetime):
    """Return (items, entries_seen, note). Never raises: a dead feed is [] plus a note."""
    name = str(feed.get("name") or "?")
    url = str(feed.get("url") or "").strip()
    try:
        weight = int(feed.get("weight"))
    except Exception:
        weight = 1
    feed_tags = [str(t).strip() for t in (feed.get("tags") or []) if str(t).strip()]
    if not url:
        return [], 0, "no url"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=FEED_TIMEOUT, allow_redirects=True)
    except Exception as exc:
        return [], 0, "request failed: " + exc.__class__.__name__
    if resp.status_code != 200:
        return [], 0, "http %d" % resp.status_code

    try:
        parsed = feedparser.parse(resp.content)
    except Exception as exc:
        return [], 0, "parse failed: " + exc.__class__.__name__
    entries = list(getattr(parsed, "entries", []) or [])
    if not entries:
        return [], 0, "0 entries"

    items = []
    old = 0
    skipped = 0
    for entry in entries:
        title = clean_html(entry.get("title") or "", 300)
        link = str(entry.get("link") or "").strip()
        if not title or not link:
            skipped += 1
            continue
        published = parse_date(entry)
        if published is not None and published < window_start:
            old += 1
            continue
        summary_html = ""
        for key in ("summary", "description", "content"):
            val = entry.get(key)
            if isinstance(val, list) and val:
                val = val[0].get("value") if isinstance(val[0], dict) else val[0]
            if val:
                summary_html = str(val)
                break
        image = pick_cheap_image(entry, summary_html)
        tags = list(feed_tags)
        for t in topic_tags(title, feed_tags):
            if t not in tags:
                tags.append(t)
        items.append(
            {
                "source": "news",
                "kind": "article",
                "key": "url:" + sha16(canonical_url(link)),
                "title": title,
                "url": link,
                "publishedAt": iso(published),
                "score_hint": float(weight),
                "tags": tags,
                "thumb_local": None,
                "sourceName": name,
                "feedTags": feed_tags,
                "summary": clean_html(summary_html, SUMMARY_MAX),
                "image": image,
                "weight": weight,
                "also_on": [],
                "_url_norm": canonical_url(link),
                "_title_norm": collapse(title),
            }
        )
    note = "%d entries, %d in window" % (len(entries), len(items))
    if old:
        note += ", %d older" % old
    if skipped:
        note += ", %d unusable" % skipped
    return items, len(entries), note


def sort_key(item: dict):
    """(weight desc, publishedAt desc) - undated items land after dated ones of the same weight."""
    return (item.get("weight", 0), item.get("publishedAt") or "")


def dedupe(items: list[dict]):
    """Collapse one story reported by several feeds. Returns (keepers, merged_count).

    Ordered so the FIRST item of a cluster is already the winner: highest weight, then earliest
    publishedAt. Every other feed name is appended to also_on (unique, in encounter order).
    """
    ordered = sorted(items, key=lambda it: (-it.get("weight", 0), it.get("publishedAt") or "9999"))
    keepers = []
    words = []
    merged = 0
    for it in ordered:
        wset = set(significant_words(it["title"]))
        hit = None
        for idx, keeper in enumerate(keepers):
            if it["_url_norm"] and it["_url_norm"] == keeper["_url_norm"]:
                hit = idx
                break
            if it["_title_norm"] and it["_title_norm"] == keeper["_title_norm"]:
                hit = idx
                break
            if jaccard(wset, words[idx]) >= JACCARD_MIN:
                hit = idx
                break
        if hit is None:
            keepers.append(it)
            words.append(wset)
            continue
        keeper = keepers[hit]
        merged += 1
        if it["sourceName"] != keeper["sourceName"] and it["sourceName"] not in keeper["also_on"]:
            keeper["also_on"].append(it["sourceName"])
        if not keeper.get("image") and it.get("image"):
            keeper["image"] = it["image"]
        if not keeper.get("summary") and it.get("summary"):
            keeper["summary"] = it["summary"]
    return keepers, merged


def apply_caps(items: list[dict], limit: int):
    """Cap 4 per sourceName, then the overall cap. Returns (kept, dropped_by_source_cap, dropped_rest)."""
    per_source = {}
    kept = []
    dropped_source = 0
    for it in items:
        name = it["sourceName"]
        if per_source.get(name, 0) >= MAX_PER_SOURCE:
            dropped_source += 1
            continue
        if len(kept) >= limit:
            continue
        per_source[name] = per_source.get(name, 0) + 1
        kept.append(it)
    dropped_total = max(0, len(items) - len(kept) - dropped_source)
    return kept, dropped_source, dropped_total


def strip_private(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="news_source.py",
        description="Collect news items from config/feeds.json into the canonical news item shape.",
    )
    ap.add_argument("--out", required=True, help="output json path (relative paths resolve against --root)")
    ap.add_argument("--hours", type=int, default=0, help="lookback window in hours (default: settings lookback_hours, else 50)")
    ap.add_argument("--limit", type=int, default=0, help="overall cap (default: settings max_news_items, else 60)")
    ap.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    ap.add_argument("--print-first", type=int, default=0, metavar="N", help="debug: print the first N titles")
    args = ap.parse_args(argv)

    root = project_root(args.root)
    settings = load_settings(root)

    try:
        hours = int(args.hours) if args.hours else int(settings.get("lookback_hours") or DEFAULT_HOURS)
    except Exception:
        hours = DEFAULT_HOURS
    if hours <= 0:
        hours = DEFAULT_HOURS
    try:
        max_news = int(settings.get("max_news_items") or DEFAULT_MAX_NEWS)
    except Exception:
        max_news = DEFAULT_MAX_NEWS
    limit = args.limit if args.limit and args.limit > 0 else max_news
    if limit <= 0:
        limit = DEFAULT_MAX_NEWS

    feeds_path = root / "config" / "feeds.json"
    feeds_raw = read_json(feeds_path, None)
    if not isinstance(feeds_raw, list):
        print("news_source: %s missing or not a JSON array" % ascii_safe(feeds_path), file=sys.stderr)
        return 2
    feeds = [f for f in feeds_raw if isinstance(f, dict) and f.get("enabled") is not False and f.get("url")]
    total = len(feeds)
    if total == 0:
        print("news_source: no enabled feeds in config/feeds.json", file=sys.stderr)
        return 2

    window_start = now_local() - timedelta(hours=hours)
    print("news_source: %d feeds, window %dh, cap %d (max %d per source)" % (total, hours, limit, MAX_PER_SOURCE))

    collected = []
    ok = 0
    failed = 0
    undated = 0
    for feed in feeds:
        items, entries, note = fetch_feed(feed, window_start)
        if items or entries:
            ok += 1
            collected.extend(items)
            undated += sum(1 for it in items if it["publishedAt"] is None)
            print("  ok   %-24s %s" % (ascii_safe(feed.get("name") or "?"), ascii_safe(note)))
        else:
            failed += 1
            print("  FAIL %-24s %s" % (ascii_safe(feed.get("name") or "?"), ascii_safe(note)))

    if ok == 0:
        print("news_source: every feed failed (%d feeds)" % total, file=sys.stderr)
        return 1

    keepers, merged = dedupe(collected)
    print("  window: %d items in %dh (%d undated kept)" % (len(collected), hours, undated))
    print("  dedupe: %d -> %d stories (%d merged, also_on recorded)" % (len(collected), len(keepers), merged))

    keepers.sort(key=sort_key, reverse=True)
    kept, dropped_source, dropped_total = apply_caps(keepers, limit)
    print("  caps: 4/source dropped %d, overall cap %d dropped %d" % (dropped_source, limit, dropped_total))

    og_used = 0
    for it in kept:
        if it.get("image"):
            continue
        if og_used >= OG_BUDGET:
            break
        og_used += 1
        img = og_image(it.get("url"))
        if img:
            it["image"] = img
    print("  images: %d/%d items have one (og:image fetches %d/%d)" % (
        sum(1 for it in kept if it.get("image")), len(kept), og_used, OG_BUDGET))

    payload = [strip_private(it) for it in kept]
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print("news_source: cannot write %s (%s)" % (ascii_safe(out), exc.__class__.__name__), file=sys.stderr)
        return 3

    if args.print_first and args.print_first > 0:
        for it in payload[: args.print_first]:
            print("  - [w%d] %s | %s" % (it["weight"], ascii_safe(it["title"])[:90], ascii_safe(it["sourceName"])))

    print("  wrote %s" % ascii_safe(out))
    print("news_source done: %d articles from %d/%d feeds (%d failed)" % (len(payload), ok, total, failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
