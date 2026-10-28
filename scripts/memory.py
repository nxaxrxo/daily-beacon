#!/usr/bin/env python3
"""memory.py - Daily Beacon anti-repeat seen-store (stdlib sqlite3 only).

DB: state/seen.sqlite (override with --db). Schema version lives in PRAGMA user_version.

KEY + NORMALISATION RULE (one rule, used everywhere)
  video   -> "yt:<videoId>"                       videoId from the item, else from the url
  url     -> "url:<sha1(canonical_url)[:16]>"
  title   -> "title:<sha1(canonical_title)[:16]>"

  A news item stores BOTH a url row and a title row, so the title guard still
  fires after a url change. A video counts as seen when its yt key OR its url
  key OR its title key is already in items.

  canonical_url(url), in order:
    1. lowercase
    2. drop the #fragment
    3. drop tracking params: every utm_* plus fbclid gclid dclid msclkid ref
       referrer source mc_cid mc_eid igshid s xtor cmpid si feature spm yclid
       gbraid wbraid _ga at_medium at_campaign ito ncid smid smtyp sr_share
       share share_id __twitter_impression oly_anon_id oly_enc_id trk
       trkcampaign sc_cid
    4. sort the surviving params
    5. drop a leading "www."
    6. strip punctuation: [^a-z0-9] -> space
    7. collapse whitespace
  canonical_title(title), in order:
    1. lowercase
    2. strip punctuation: [^a-z0-9] -> space
    3. collapse whitespace
  sha1 = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

  mark() writes a title: row only for a substantial headline (>= 3 words and
  >= 20 canonical chars), so a one-word label cannot become a false-positive
  title guard. Topic matching in filter() reads a slug as a regex that allows
  spaces between characters, so topic "gta6" also hits the text "GTA 6".

Tables: items / topics / editions exactly as spec 4, plus the additive helper
topic_seen(topic, edition) whose only job is making mark() idempotent.
"""

import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCHEMA_VERSION = 1
DEFAULT_COOLDOWN_DAYS = 21
SETTING_DEFAULTS = {"repeat_topic_cooldown_days": DEFAULT_COOLDOWN_DAYS}

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "ref", "referrer", "source",
    "mc_cid", "mc_eid", "igshid", "s", "xtor", "cmpid", "si", "feature",
    "spm", "yclid", "gbraid", "wbraid", "_ga", "at_medium", "at_campaign",
    "ito", "ncid", "smid", "smtyp", "sr_share", "share", "share_id",
    "__twitter_impression", "oly_anon_id", "oly_enc_id", "trk", "trkcampaign",
    "sc_cid",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS items(
    key TEXT PRIMARY KEY,
    kind TEXT,
    title TEXT,
    url TEXT,
    source TEXT,
    first_seen TEXT,
    edition TEXT,
    tags TEXT
);
CREATE TABLE IF NOT EXISTS topics(
    topic TEXT PRIMARY KEY,
    last_covered TEXT,
    times INTEGER,
    last_edition TEXT
);
CREATE TABLE IF NOT EXISTS editions(
    date TEXT PRIMARY KEY,
    path TEXT,
    items INTEGER,
    created TEXT
);
CREATE TABLE IF NOT EXISTS topic_seen(
    topic TEXT,
    edition TEXT,
    PRIMARY KEY (topic, edition)
);
CREATE INDEX IF NOT EXISTS idx_items_edition ON items(edition);
CREATE INDEX IF NOT EXISTS idx_items_first_seen ON items(first_seen);
CREATE INDEX IF NOT EXISTS idx_topics_last_covered ON topics(last_covered);
"""

PUNCT_RE = re.compile(r"[^a-z0-9]+")
VIDEO_ID_RE = re.compile(r"(?:v=|/shorts/|/embed/|/live/|youtu\.be/)([A-Za-z0-9_-]{6,})")


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_str():
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def days_ago(days):
    d = datetime.now().astimezone() - timedelta(days=int(days))
    return d.strftime("%Y-%m-%d")


def project_root(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[1]


def load_settings(root):
    out = dict(SETTING_DEFAULTS)
    p = Path(root) / "config" / "settings.json"
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if v is not None})
    return out


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, payload):
    p = Path(path)
    if str(p.parent) not in ("", "."):
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collapse(text):
    return " ".join(PUNCT_RE.sub(" ", (text or "").lower()).split())


def canonical_url(url):
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


def canonical_title(title):
    return collapse(title)


def sha16(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def url_key(url):
    c = canonical_url(url)
    return ("url:" + sha16(c)) if c else ""


def title_key(title):
    c = canonical_title(title)
    return ("title:" + sha16(c)) if c else ""


def video_id_from_url(url):
    if not url:
        return ""
    m = VIDEO_ID_RE.search(str(url))
    return m.group(1) if m else ""


def topic_name(text):
    """Topic identity: lowercase alphanumerics only, separators removed.

    "GTA 6", "gta-6", "gta_6" and tag "GTA6" all collapse to the single topic
    "gta6", so mark(), query() and filter() can never disagree about a topic.
    """
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def connect(db):
    p = Path(db)
    if str(p.parent) not in ("", "."):
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        conn.executescript(SCHEMA_SQL)
        conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
        conn.commit()
    elif version > SCHEMA_VERSION:
        conn.close()
        raise RuntimeError("db schema version %d is newer than %d" % (version, SCHEMA_VERSION))
    return conn


@contextmanager
def db_session(db):
    """Context manager around a connection: commit on clean exit, always close."""
    conn = connect(db)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# --------------------------------------------------------------------------
# key derivation
# --------------------------------------------------------------------------
def item_keys(item):
    """All keys a candidate/news item should be found under."""
    src = (item.get("source") or "").lower()
    kind = (item.get("kind") or "").lower()
    keys = []
    if src == "youtube" or kind in ("video", "short"):
        vid = item.get("videoId") or video_id_from_url(item.get("url"))
        if vid:
            keys.append("yt:" + str(vid).strip())
    for k in (url_key(item.get("url")), title_key(item.get("title"))):
        if k and k not in keys:
            keys.append(k)
    return keys


def key_for(item):
    """Primary key of an item (first derived key, or its declared key)."""
    declared = (item.get("key") or "").strip()
    if declared:
        return declared
    keys = item_keys(item)
    return keys[0] if keys else ""


# --------------------------------------------------------------------------
# filter
# --------------------------------------------------------------------------
# Kickers are typographic labels ("GAMING . AI", "MUSIC . MASS EFFECT"). Slugging the whole
# string produced topics like "gaminglabour" and "animepenguinz0", which no article tag can ever
# match - so the cooldown silently never fired. Each word is a topic; these words are not.
KICKER_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "your", "our", "its", "his", "her", "their",
    "new", "now", "out", "off", "all", "not", "but", "you", "are", "was", "has", "had", "how",
    "why", "what", "when", "who", "this", "that", "these", "those", "more", "most", "than",
    "than", "then", "over", "after", "before", "under", "about", "again", "just", "still",
    "week", "day", "today", "news", "review", "reviews", "update", "updates", "report",
    "first", "last", "next", "back", "top", "big", "one", "two", "ago", "get", "got",
}


KICKER_SPLIT_RE = re.compile(r"[\u00b7|/\u2014\u2013\u2192,;:()\[\]]+")


# Tags this broad would each shut down a whole section for three weeks ("review" appears in half
# of everything). They stay on the item record, but never become cooldown topics.
GENERIC_TOPICS = {
    # umbrella tags: they sit on 110 of 113 candidates, so a cooldown on any of them would forbid
    # the entire edition. They describe a section, never a story.
    "gaming", "ai", "hardware", "tech", "technology", "industry", "pc", "world", "dev",
    # media/genre broad enough that a 21-day cooldown would mute a whole interest he follows
    "anime", "music", "indie", "apps", "movies", "film", "animation", "comedy", "drama",
    "development", "entertainment", "business", "culture", "media", "software", "games", "game",
    "news", "review", "reviews", "release", "released", "research", "update", "updates",
    "report", "reports", "video", "videos", "feature", "features", "analysis", "opinion",
    "business", "rumour", "rumor", "leak", "leaks", "trailer", "preview", "editorial",
    "world", "general", "misc", "other", "top", "best", "how", "why", "what",
}


def cooldown_topics(tags, kicker):
    """The topic slugs that legitimately gate a repeat: specific, matchable, not category noise."""
    raw = [topic_name(str(t)) for t in (tags or [])]
    raw.extend(kicker_topics(kicker))
    return [t for t in dict.fromkeys(raw) if t and t not in GENERIC_TOPICS]


def kicker_topics(kicker):
    """Split a kicker label into matchable topic slugs.

    Kickers are editorial labels: "MUSIC . MASS EFFECT" is two subjects, not four words.
    Splitting on the separator first keeps multi-word subjects intact ("masseffect"), and
    dropping stopwords keeps "THE BIG ONE" from becoming a topic.
    """
    out = []
    for segment in KICKER_SPLIT_RE.split(str(kicker or "").lower()):
        words = [w for w in PUNCT_RE.split(segment) if w and w not in KICKER_STOPWORDS]
        if not words:
            continue
        slug = "".join(words)
        if len(slug) < 3 or slug.isdigit():
            continue
        out.append(slug)
    return out


def recent_topics(conn, cooldown_days):
    cutoff = days_ago(cooldown_days)
    rows = conn.execute(
        "SELECT topic, last_covered, times FROM topics WHERE last_covered >= ? "
        "ORDER BY last_covered DESC, topic ASC",
        (cutoff,),
    ).fetchall()
    return [{"topic": r["topic"], "last_covered": r["last_covered"], "times": r["times"] or 0} for r in rows]


def existing_keys(conn, keys):
    found = set()
    keys = [k for k in keys if k]
    for i in range(0, len(keys), 400):
        chunk = keys[i:i + 400]
        marks = ",".join("?" * len(chunk))
        for row in conn.execute("SELECT key FROM items WHERE key IN (%s)" % marks, chunk):
            found.add(row["key"])
    return found


def topic_pattern(topic):
    """Regex that finds a slug in prose, allowing spaces between its characters.

    "gta6" therefore matches both "gta6" and "GTA 6"; whole-token boundaries on
    both sides stop "gta6" from firing inside a longer word.
    """
    body = r"[\s]*".join(re.escape(ch) for ch in topic)
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")


def hits_topic(item, cooling):
    """Cooling topics this item touches: exact tag slug, or the slug inside the title."""
    text = canonical_title(item.get("title") or "")
    tags = []
    for tag in list(item.get("tags") or []) + list(item.get("feedTags") or []):
        s = topic_name(str(tag))
        if s:
            tags.append(s)
    hits = []
    for topic in cooling:
        if topic in tags or (text and topic_pattern(topic).search(text)):
            hits.append(topic)
    return hits


def annotate(conn, items, cooldown_days):
    cooling = [r["topic"] for r in recent_topics(conn, cooldown_days)]
    all_keys = []
    per_item = []
    for it in items:
        ks = item_keys(it)
        per_item.append(ks)
        all_keys.extend(ks)
    seen_set = existing_keys(conn, all_keys)
    out = []
    n_seen = 0
    for it, ks in zip(items, per_item):
        reason = None
        if any(k in seen_set for k in ks):
            if any(k.startswith("yt:") and k in seen_set for k in ks):
                reason = "video"
            elif any(k.startswith("url:") and k in seen_set for k in ks):
                reason = "url"
            elif any(k.startswith("title:") and k in seen_set for k in ks):
                reason = "title"
            else:
                reason = "video"
        hits = hits_topic(it, cooling)
        row = dict(it)
        row["seen"] = reason is not None
        row["seen_reason"] = reason
        row["topic_hits"] = hits
        if reason is not None:
            n_seen += 1
        out.append(row)
    return out, n_seen, cooling


def filter_candidates(conn, payload, cooldown_days):
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("candidates must be a JSON array or an object with an items array")
    rows, n_seen, cooling = annotate(conn, items, cooldown_days)
    result = {
        "generatedAt": now_iso(),
        "date": today_str(),
        "cooldown_days": int(cooldown_days),
        "recent_topics": [r for r in recent_topics(conn, cooldown_days)],
        "counts": {"total": len(rows), "seen": n_seen, "fresh": len(rows) - n_seen},
        "items": rows,
    }
    suppressed = {"generatedAt": result["generatedAt"], "items": [r for r in rows if r["seen"]]}
    return result, suppressed


def cmd_filter(args, root):
    settings = load_settings(root)
    cooldown = args.cooldown if args.cooldown is not None else settings.get(
        "repeat_topic_cooldown_days", DEFAULT_COOLDOWN_DAYS)
    conn = connect(args.db)
    try:
        payload = read_json(args.candidates)
        result, suppressed = filter_candidates(conn, payload, cooldown)
    finally:
        conn.close()
    write_json(args.out, result)
    sup_path = args.suppressed or (Path(args.out).parent / "suppressed.json")
    write_json(sup_path, suppressed)
    c = result["counts"]
    print("filter done: %d total, %d seen, %d fresh, %d cooling topics"
          % (c["total"], c["seen"], c["fresh"], len(result["recent_topics"])))
    return 0

# --------------------------------------------------------------------------
# mark
# --------------------------------------------------------------------------
def edition_story_keys(kind, url, title):
    """Keys one story/quickHit covers: video -> yt:<id>; article -> url: + title:.

    The title: row is the second guard: it still fires after the url changes.
    """
    keys = []
    url = (url or "").strip()
    if not url:
        return keys
    vid = video_id_from_url(url)
    if vid and (kind in ("video", "short", "quick") or "youtu" in url.lower()):
        return ["yt:" + vid]
    uk = url_key(url)
    if uk:
        keys.append(uk)
    tk = title_key((title or "").strip())
    if tk and tk not in keys:
        keys.append(tk)
    return keys


def insert_item(conn, key, kind, title, url, source, first_seen, edition, tags):
    cur = conn.execute(
        "INSERT OR IGNORE INTO items(key, kind, title, url, source, first_seen, edition, tags) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (key, kind, title, url, source, first_seen, edition, tags),
    )
    return cur.rowcount > 0


def bump_topic(conn, topic, edition, covered_at):
    """Upsert last_covered/times/last_edition, at most once per (topic, edition)."""
    guard = conn.execute(
        "INSERT OR IGNORE INTO topic_seen(topic, edition) VALUES (?,?)", (topic, edition))
    if guard.rowcount == 0:
        return False
    conn.execute(
        "INSERT INTO topics(topic, last_covered, times, last_edition) VALUES (?,?,1,?) "
        "ON CONFLICT(topic) DO UPDATE SET "
        "times = COALESCE(topics.times,0) + 1, "
        "last_covered = CASE WHEN topics.last_covered IS NULL OR topics.last_covered < excluded.last_covered "
        "THEN excluded.last_covered ELSE topics.last_covered END, "
        "last_edition = CASE WHEN topics.last_covered IS NULL OR topics.last_covered <= excluded.last_covered "
        "THEN excluded.last_edition ELSE topics.last_edition END",
        (topic, covered_at, edition),
    )
    return True


def mark_edition(conn, edition_path, edition_date=None):
    """Record an edition's stories + topics. Idempotent by key and by (topic, edition)."""
    data = read_json(edition_path)
    date = (edition_date or data.get("date") or today_str()).strip()
    stamp = now_iso()
    new_items = 0
    new_topics = 0

    for section in data.get("sections") or []:
        src = section.get("source") or {}
        url = (src.get("url") or "").strip()
        title = (section.get("headline") or "").strip()
        kind = section.get("kind") or "story"
        tags = cooldown_topics(section.get("tags"), section.get("kicker"))
        tags = [t for t in dict.fromkeys(tags) if t]
        for key in edition_story_keys(kind, url, title):
            if insert_item(conn, key, kind, title, url, src.get("label") or "",
                           stamp, date, ",".join(tags)):
                new_items += 1
        for topic in tags:
            if bump_topic(conn, topic, date, date):
                new_topics += 1

    for qh in data.get("quickHits") or []:
        url = (qh.get("url") or "").strip()
        text = (qh.get("text") or "").strip()
        if not url:
            continue
        for key in edition_story_keys("quick", url, text):
            if insert_item(conn, key, "quick", text, url, "", stamp, date, ""):
                new_items += 1

    n_items = conn.execute("SELECT COUNT(*) FROM items WHERE edition = ?", (date,)).fetchone()[0]
    conn.execute(
        "INSERT INTO editions(date, path, items, created) VALUES (?,?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET path = excluded.path, items = excluded.items",
        (date, str(edition_path), n_items, stamp),
    )
    conn.commit()
    return date, new_items, new_topics, n_items


def cmd_mark(args, root):
    with db_session(args.db) as conn:
        date, new_items, new_topics, _ = mark_edition(conn, args.edition, args.date)
    print("marked: %d new items, %d topics, edition %s" % (new_items, new_topics, date))
    return 0


# --------------------------------------------------------------------------
# query / stats / prune
# --------------------------------------------------------------------------
def query_topic(conn, topic, days=None):
    name = topic_name(topic)
    row = conn.execute(
        "SELECT topic, last_covered, times, last_edition FROM topics WHERE topic = ?", (name,)
    ).fetchone()
    sql = "SELECT edition FROM topic_seen WHERE topic = ?"
    params = [name]
    if days is not None:
        sql += " AND edition >= ?"
        params.append(days_ago(days))
    sql += " ORDER BY edition ASC"
    editions = [r["edition"] for r in conn.execute(sql, params)]
    return name, row, editions


def cmd_query(args, root):
    with db_session(args.db) as conn:
        _, row, editions = query_topic(conn, args.topic, args.days)
    if row is None:
        print("topic '%s': never covered" % args.topic)
        return 0
    print("topic '%s': covered %d time(s), last on %s"
          % (args.topic, int(row["times"] or 0), row["last_covered"] or "unknown"))
    print("  last edition: %s" % (row["last_edition"] or "unknown"))
    if editions:
        print("  editions in last %d days: %s" % (args.days, ", ".join(editions)))
    else:
        print("  editions in last %d days: none" % args.days)
    return 0


def db_size_bytes(conn):
    """On-disk size of the database file in bytes."""
    db_file = str(conn.execute("PRAGMA database_list").fetchone()[2])
    path = Path(db_file)
    return path.stat().st_size if path.is_file() else 0


def cmd_stats(args, root):
    with db_session(args.db) as conn:
        items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        topics = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        editions = conn.execute("SELECT COUNT(*) FROM editions").fetchone()[0]
        last = conn.execute(
            "SELECT date, path FROM editions ORDER BY date DESC LIMIT 1").fetchone()
        size = db_size_bytes(conn)
    print("db: %s" % Path(args.db))
    print("items: %d" % items)
    print("topics: %d" % topics)
    print("editions: %d" % editions)
    print("db size: %d bytes" % size)
    if last is None:
        print("last edition: none")
    else:
        print("last edition: %s (%s)" % (last["date"], last["path"] or "no path"))
    return 0


def days_since(date_str):
    """Whole days between a YYYY-MM-DD string and today. None when unparseable."""
    try:
        then = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (datetime.now().astimezone().date() - then).days


def resurface_candidates(conn, after_days, limit):
    """Topics that fell out of the cooldown window and can come back as retrospectives.

    The spec asks for a reminder a month later. This is that: a topic quiet for at least
    `after_days` is no longer "news" (never re-report it as fresh), but it IS fair game to
    revisit with a genuinely new development, framed as a follow-up.
    """
    cutoff = days_ago(after_days)
    return conn.execute(
        "SELECT topic, last_covered, times, last_edition FROM topics "
        "WHERE last_covered IS NOT NULL AND last_covered <= ? "
        "ORDER BY last_covered ASC LIMIT ?",
        (cutoff, int(limit)),
    ).fetchall()


def cmd_digest(args, root):
    """Coverage analytics + the month-later resurface list, optionally saved as markdown."""
    if not args.write:
        return _digest_body(args, root)

    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        result = _digest_body(args, root)
    finally:
        sys.stdout = saved
    text = buf.getvalue()
    sys.stdout.write(text)

    target = args.write
    if target is True:
        target = root / "docs" / "coverage" / ("%s.md" % today_str())
    else:
        target = Path(str(target))
        if not target.is_absolute():
            target = root / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Coverage report - %s\n\n```text\n%s```\n" % (today_str(), text),
                      encoding="utf-8")
    print("digest written: %s" % target)
    return result


def _digest_body(args, root):
    if args.cooldown is None:
        settings = load_settings(root)
        args.cooldown = settings.get("repeat_topic_cooldown_days", DEFAULT_COOLDOWN_DAYS)
    with db_session(args.db) as conn:
        n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        n_topics = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        first = conn.execute("SELECT MIN(date) AS d FROM editions").fetchone()["d"]
        last = conn.execute("SELECT MAX(date) AS d FROM editions").fetchone()["d"]
        n_editions = conn.execute("SELECT COUNT(*) FROM editions").fetchone()[0]
        run = conn.execute(
            "SELECT COUNT(*) AS c FROM (SELECT DISTINCT date(first_seen) AS d FROM items)"
        ).fetchone()["c"]
        hottest = conn.execute(
            "SELECT topic, times, last_covered FROM topics ORDER BY times DESC, last_covered DESC "
            "LIMIT ?", (int(args.top),)).fetchall()
        cooling = recent_topics(conn, args.cooldown)
        ripe = resurface_candidates(conn, args.after, args.top)

    print("DIGEST - what the Beacon has covered")
    print("db: %s" % Path(args.db))
    if first:
        print("editions: %d (%s .. %s)" % (n_editions, first, last))
    else:
        print("editions: 0 (nothing published yet)")
    print("items kept: %d | topics tracked: %d | days with coverage: %d" % (n_items, n_topics, run))
    if not n_topics:
        print()
        print("Nothing to digest yet - the store fills up after the first few editions.")
        return 0

    print()
    print("most covered topics:")
    for row in hottest:
        age = days_since(row["last_covered"])
        when = "today" if age == 0 else ("%d days ago" % age if age is not None else "unknown")
        print("  %-32s %2d time(s)  last %s" % (row["topic"][:32], int(row["times"] or 0), when))

    print()
    if cooling:
        print("cooling down (do not re-report as news, %d-day window):" % int(args.cooldown))
        print("  " + ", ".join(str(c["topic"]) if isinstance(c, dict) else str(c) for c in cooling))
    else:
        print("cooling down: nothing (empty store or all quiet)")

    print()
    if ripe:
        print("ripe for a month-later follow-up (quiet %d+ days):" % int(args.after))
        for row in ripe:
            age = days_since(row["last_covered"])
            print("  %-32s quiet %s days, %d time(s) - needs a NEW development"
                  % (row["topic"][:32], age if age is not None else "?", int(row["times"] or 0)))
    else:
        print("ripe for a follow-up: nothing yet (needs %d days of quiet)" % int(args.after))
    return 0


def prune(conn, days):
    """Delete rows older than the cutoff that NO kept edition references."""
    cutoff = days_ago(days)
    n_items = conn.execute(
        "DELETE FROM items WHERE first_seen < ? "
        "AND (edition IS NULL OR edition NOT IN (SELECT date FROM editions))",
        (cutoff,),
    ).rowcount
    n_topics = conn.execute(
        "DELETE FROM topics WHERE last_covered < ? "
        "AND (last_edition IS NULL OR last_edition NOT IN (SELECT date FROM editions))",
        (cutoff,),
    ).rowcount
    conn.execute("DELETE FROM topic_seen WHERE topic NOT IN (SELECT topic FROM topics)")
    conn.commit()
    return max(n_items, 0), max(n_topics, 0)


def cmd_prune(args, root):
    with db_session(args.db) as conn:
        n_items, n_topics = prune(conn, args.days)
    print("pruned: %d items, %d topics" % (n_items, n_topics))
    return 0


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------
def _sample_candidates():
    return [
        {"source": "youtube", "kind": "video", "videoId": "abc123XYZ", "title": "GTA 6 Trailer Breakdown",
         "url": "https://www.youtube.com/watch?v=abc123XYZ&utm_source=x", "tags": ["gta6"], "score_hint": 2.0},
        {"source": "news", "kind": "article", "title": "Rockstar delays GTA 6 again",
         "url": "https://example.com/gta6-delay?utm_campaign=y&fbclid=z", "tags": ["gta6", "gaming"],
         "score_hint": 1.0},
        {"source": "youtube", "kind": "video", "videoId": "fresh999", "title": "Warframe 1999 gameplay",
         "url": "https://youtu.be/fresh999", "tags": ["warframe"], "score_hint": 1.0},
    ]


def _sample_edition(path):
    data = {
        "date": "2026-01-15",
        "number": 1,
        "masthead": "THE DAILY BEACON",
        "sections": [
            {"id": "gta6-trailer", "kind": "lead", "headline": "GTA 6 trailers everywhere",
             "body": ["x"], "source": {"label": "AngryJoeShow",
                                       "url": "https://youtu.be/abc123XYZ"},
             "tags": ["gta6"]},
            {"id": "delay", "kind": "story", "headline": "Rockstar delays again",
             "body": ["x"], "source": {"label": "PC Gamer",
                                       "url": "https://example.com/gta6-delay"},
             "tags": ["gta6", "gaming"]},
        ],
        "quickHits": [{"text": "quick one", "url": "https://example.com/quick?utm_medium=rss"}],
    }
    write_json(path, data)
    return Path(path)


def selftest():
    tmp = tempfile.mkdtemp(prefix="beacon-memtest-")
    try:
        db = Path(tmp) / "test.sqlite"
        edition_path = _sample_edition(Path(tmp) / "edition.json")
        cands = _sample_candidates()

        conn = connect(db)
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise RuntimeError("schema version not set")

            res, sup = filter_candidates(conn, cands, DEFAULT_COOLDOWN_DAYS)
            if res["counts"]["seen"] != 0 or sup["items"]:
                raise RuntimeError("(a) empty db should see 0, saw %d" % res["counts"]["seen"])

            date1, new1, topics1, _ = mark_edition(conn, edition_path)
            if new1 <= 0:
                raise RuntimeError("(b) first mark added no items")
            if topics1 <= 0:
                raise RuntimeError("(b) first mark added no topics")
            before = {r["topic"]: int(r["times"]) for r in conn.execute("SELECT topic, times FROM topics")}
            items_before = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

            date2, new2, topics2, _ = mark_edition(conn, edition_path)
            after = {r["topic"]: int(r["times"]) for r in conn.execute("SELECT topic, times FROM topics")}
            items_after = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            if new2 != 0:
                raise RuntimeError("(b) second mark added %d items, expected 0" % new2)
            if topics2 != 0:
                raise RuntimeError("(b) second mark counted %d topics, expected 0" % topics2)
            if before != after:
                raise RuntimeError("(b) times changed on re-mark: %s -> %s" % (before, after))
            if items_before != items_after:
                raise RuntimeError("(b) item count changed on re-mark")
            if date1 != date2:
                raise RuntimeError("(b) edition date unstable")

            res2, _ = filter_candidates(conn, cands, DEFAULT_COOLDOWN_DAYS)
            seen2 = [it for it in res2["items"] if it["seen"]]
            if len(seen2) != 2:
                raise RuntimeError("(c) expected 2 seen items, got %d" % len(seen2))
            reasons = {it["title"]: it["seen_reason"] for it in res2["items"]}
            if reasons.get("GTA 6 Trailer Breakdown") != "video":
                raise RuntimeError("(c) video reason wrong: %r" % reasons.get("GTA 6 Trailer Breakdown"))
            if reasons.get("Rockstar delays GTA 6 again") not in ("url", "title"):
                raise RuntimeError("(c) news reason wrong: %r" % reasons.get("Rockstar delays GTA 6 again"))
            fresh = [it for it in res2["items"] if not it["seen"]]
            if len(fresh) != 1:
                raise RuntimeError("(c) expected 1 fresh item, got %d" % len(fresh))
            if fresh[0].get("seen_reason") is not None:
                raise RuntimeError("(c) fresh item has a seen_reason")
            if "warframe" in (fresh[0].get("topic_hits") or []):
                raise RuntimeError("(c) warframe is not cooling down but was reported")

            n_before = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            pr_items, pr_topics = prune(conn, 0)
            n_after = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            if n_before != n_after:
                raise RuntimeError("(d) prune --days 0 deleted %d referenced items" % (n_before - n_after))
            editions_left = conn.execute("SELECT COUNT(*) FROM editions").fetchone()[0]
            if editions_left != 1:
                raise RuntimeError("(d) prune dropped the kept edition row")
            if pr_items != 0:
                raise RuntimeError("(d) prune reported %d item deletions, expected 0" % pr_items)
        finally:
            conn.close()
        print("selftest: a/b/c/d ok")
        print("SELFTEST PASS")
        return 0
    except Exception as exc:
        print("SELFTEST FAIL: %s" % exc)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="memory.py",
        description="Daily Beacon anti-repeat seen-store (sqlite).",
        epilog="Keys: video=yt:<videoId>, news=url:<sha1-16> + title:<sha1-16>.")
    p.add_argument("--root", default=None, help="project root (default: parent of scripts/)")
    p.add_argument("--db", default=None, help="sqlite path (default: state/seen.sqlite)")
    p.add_argument("--selftest", action="store_true", help="alias for the selftest subcommand")
    sub = p.add_subparsers(dest="cmd")

    # --root is also accepted AFTER the verb: callers (run_daily.py, scripts, humans) naturally
    # write "memory.py filter ... --root X". argparse would reject that, so every subparser gets
    # its own copy with SUPPRESS, which leaves the parent default untouched when it is absent.
    def add_root(sp):
        # Both --root and --db are accepted before OR after the verb: people (and scripts) write
        # "memory.py digest --db X" as naturally as "memory.py --db X digest". SUPPRESS keeps the
        # parent default intact when the flag is absent from the subcommand.
        sp.add_argument("--root", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--db", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sp

    f = add_root(sub.add_parser("filter", help="annotate candidates with seen/seen_reason/topic_hits"))
    f.add_argument("--candidates", required=True, help="candidates.json (array or {items:[...]})")
    f.add_argument("--out", required=True, help="filtered.json output path")
    f.add_argument("--suppressed", default=None,
                   help="seen-only audit file (default: <out dir>/suppressed.json)")
    f.add_argument("--cooldown", type=int, default=None,
                   help="topic cooldown in days (default: settings.json repeat_topic_cooldown_days=%d)"
                        % DEFAULT_COOLDOWN_DAYS)
    f.set_defaults(func=cmd_filter)

    m = add_root(sub.add_parser("mark", help="record an edition (idempotent)"))
    m.add_argument("--edition", required=True, help="editions/<date>.json")
    m.add_argument("--date", default=None, help="override edition date (default: json date field)")
    m.set_defaults(func=cmd_mark)

    q = add_root(sub.add_parser("query", help="when/how often a topic was covered"))
    q.add_argument("--topic", required=True, help="topic name (slugged)")
    q.add_argument("--days", type=int, default=60,
                   help="window in days for the editions list (default: 60)")
    q.set_defaults(func=cmd_query)

    s = add_root(sub.add_parser("stats", help="counts, db size, last edition, top topics"))
    s.set_defaults(func=cmd_stats)

    pr = add_root(sub.add_parser("prune", help="drop rows older than N days not referenced by a kept edition"))
    pr.add_argument("--days", type=int, default=400,
                    help="age in days; older unreferenced rows are deleted (default: 400)")
    pr.set_defaults(func=cmd_prune)

    dg = add_root(sub.add_parser("digest", help="coverage analytics + the month-later resurface list"))
    dg.add_argument("--after", type=int, default=30,
                    help="a topic quiet this many days is ripe for a follow-up (default: 30)")
    dg.add_argument("--top", type=int, default=12, help="rows per list (default: 12)")
    dg.add_argument("--write", nargs="?", const=True, default=False, metavar="PATH",
                    help="also save the digest as markdown (default docs/coverage/<today>.md)")
    dg.add_argument("--cooldown", type=int, default=None,
                    help="cooldown window to report against (default: settings.json)")
    dg.set_defaults(func=cmd_digest)

    st = add_root(sub.add_parser("selftest", help="temp-db self test (prints SELFTEST PASS)"))
    st.set_defaults(func=None)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    root = project_root(args.root)
    if args.db:
        args.db = str(Path(args.db).resolve())
    else:
        args.db = str(root / "state" / "seen.sqlite")

    if args.cmd == "selftest" or (args.selftest and not args.cmd):
        return selftest()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args, root)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        print("memory.py error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())