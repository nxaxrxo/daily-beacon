#!/usr/bin/env python3
"""doctor.py - self-check for the Daily Beacon project.

    python scripts/doctor.py [--offline] [--quick] [--keep] [--root PATH] [--json]

Twelve checks, one PASS/FAIL/WARN line each, in order: settings.json keys and types; channels.json
shape (id/name/tier/enabled, tier 1..3, UC ids); feeds.json shape (https urls); interests.md size;
AGENTS.md size; writable editions/site/site/assets/state; Python >= 3.11 plus
requests/feedparser/bs4/PIL; state/seen.sqlite tables (items, topics, editions); three network
endpoints (one feed, one channel RSS, github.com); site/style.css + app.js + index.html; a fixture
build whose HTML is structurally audited; the summary line and exit code.

Only `state/doctor-fixture` is written, and it is deleted again unless --keep.
Exit codes: 0 nothing failed (warnings allowed), 1 at least one FAIL, 2 usage error.
Console output is ASCII only. No token or credential is read or printed.
"""

from __future__ import annotations

import argparse, importlib, json, re, shutil, sqlite3, subprocess, sys, tempfile
import urllib.error, urllib.request
from pathlib import Path

try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
SETTINGS_TYPES = (
    ("timezone_note", str), ("lookback_hours", int), ("max_videos_per_channel", int),
    ("max_videos_total", int), ("max_news_items", int), ("short_max_seconds", int),
    ("transcript_max_chars", int), ("edition_max_stories", int), ("edition_min_stories", int),
    ("repeat_topic_cooldown_days", int), ("keep_editions", int), ("site_base_url", str),
    ("publish", bool))
REQUIRED_TABLES = ("items", "topics", "editions")
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,}$")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
NET_TIMEOUT, FIXTURE_TIMEOUT, MAX_HTML_BYTES = 15, 90, 3 * 1024 * 1024
FIXTURE_DIR = "doctor-fixture"
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
SCRIPT_RE = re.compile(r"(<script\b[^<>]*>)(.*?)(</script\s*>)", re.S | re.I)
STYLE_RE = re.compile(r"(<style\b[^<>]*>)(.*?)(</style\s*>)", re.S | re.I)
TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9:-]*)((?:[^<>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>")
ATTR_RE = re.compile(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*("[^"]*"|'[^']*')""")
IMG_RE = re.compile(r"<img\b((?:[^<>\"']|\"[^\"]*\"|'[^']*')*)>", re.I)
ANCHOR_RE = re.compile(r"""href\s*=\s*["']#([^"']*)["']""")
ANY_TAG_RE = re.compile(r"<[A-Za-z][^<>]*>")

def ascii_text(value, limit=320):
    """One console-safe line: ASCII, no newlines, truncated."""
    text = " ".join(str(value if value is not None else "").split())
    text = text.encode("ascii", "replace").decode("ascii")
    return text[: max(limit - 3, 0)] + "..." if limit and len(text) > limit else text

def load_json(path):
    """(data, error) - never raises, always UTF-8."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except FileNotFoundError:
        return None, "file not found"
    except json.JSONDecodeError as exc:
        return None, "invalid JSON at line %d column %d" % (exc.lineno, exc.colno)
    except (UnicodeDecodeError, OSError) as exc:
        return None, "cannot read (%s)" % exc.__class__.__name__

def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)

class Doctor:
    """Runs every check, records one result each, decides the exit code."""

    def __init__(self, root, offline, quick, keep, as_json):
        self.root, self.offline, self.quick = root, offline, quick
        self.keep, self.as_json = keep, as_json
        self.results, self.kept_fixture = [], False

    def _record(self, status, name, detail):
        detail = ascii_text(detail)
        self.results.append({"check": name, "status": status, "detail": detail})
        if not self.as_json:
            print("[%s] %s - %s" % (status, name, detail))

    def passed(self, name, detail):
        self._record(PASS, name, detail)

    def warned(self, name, detail):
        self._record(WARN, name, detail)

    def failed(self, name, detail):
        self._record(FAIL, name, detail)

    def _fail_many(self, name, problems):
        return self.failed(name, "%d problem(s): %s" % (len(problems),
                           "; ".join(str(part) for part in problems[:6])))

    def check_settings(self):
        """1. Every SPEC section 3 key, present and correctly typed."""
        name, path = "config/settings.json", self.root / "config" / "settings.json"
        if not path.is_file():
            return self.failed(name, "missing: %s" % path)
        data, error = load_json(path)
        if error:
            return self.failed(name, error)
        if not isinstance(data, dict):
            return self.failed(name, "top level must be a JSON object")
        bad, extra = [], set(data) - set(key for key, _ in SETTINGS_TYPES)
        for key, want in SETTINGS_TYPES:
            if key not in data:
                bad.append("missing '%s'" % key)
            elif not (is_int(data[key]) if want is int else isinstance(data[key], want)):
                bad.append("'%s' must be %s" % (key, want.__name__))
        if bad:
            return self._fail_many(name, bad)
        return self.passed(name, "all %d spec keys present with the right type%s"
                           % (len(SETTINGS_TYPES),
                              " (extra: %s)" % ", ".join(sorted(extra)[:4]) if extra else ""))

    def _check_list(self, name, rel, required, kind):
        """2/3. Shape plus per-entry validation, shared by channels and feeds."""
        path = self.root / rel
        if not path.is_file():
            return self.failed(name, "missing: %s" % path)
        data, error = load_json(path)
        if error:
            return self.failed(name, error)
        if not isinstance(data, list):
            return self.failed(name, "top level must be a JSON array")
        if not data:
            return self.failed(name, "array is empty")
        bad, enabled, tiers = [], 0, {1: 0, 2: 0, 3: 0}
        for index, entry in enumerate(data):
            where = "entry[%d]" % index
            if not isinstance(entry, dict):
                bad.append(where + " is not an object")
                continue
            bad.extend("%s missing '%s'" % (where, key) for key in required if key not in entry)
            if not str(entry.get("name") or "").strip():
                bad.append(where + " name is empty")
            if not isinstance(entry.get("enabled"), bool):
                bad.append(where + " enabled must be a boolean")
            else:
                enabled += 1 if entry["enabled"] else 0
            if kind == "channel":
                if not (isinstance(entry.get("id"), str)
                        and CHANNEL_ID_RE.match(entry["id"])):
                    bad.append(where + " id is not a UC... channel id")
                if is_int(entry.get("tier")) and entry["tier"] in (1, 2, 3):
                    tiers[entry["tier"]] += 1
                else:
                    bad.append(where + " tier must be 1, 2 or 3")
                continue
            url = entry.get("url")
            if not isinstance(url, str) or not url.strip():
                bad.append(where + " url is empty")
            elif not url.startswith("https://"):
                bad.append("%s url is not https (%s)" % (where, ascii_text(url, 50)))
            tags = entry.get("tags")
            if not (isinstance(tags, list) and all(isinstance(tag, str) for tag in tags)):
                bad.append(where + " tags must be an array of strings")
        if bad:
            return self._fail_many(name, bad)
        if kind == "channel":
            return self.passed(name, "%d channels, %d enabled, tier 1/2/3 = %d/%d/%d"
                               % (len(data), enabled, tiers[1], tiers[2], tiers[3]))
        return self.passed(name, "%d feeds, %d enabled, every url https" % (len(data), enabled))

    def check_channels(self):
        return self._check_list("config/channels.json", "config/channels.json",
                                ("id", "name", "tier", "enabled"), "channel")

    def check_feeds(self):
        return self._check_list("config/feeds.json", "config/feeds.json",
                                ("name", "url", "tags", "enabled"), "feed")

    def _text_file(self, name, rel, min_lines):
        path = self.root / rel
        if not path.is_file():
            return self.warned(name, "missing: %s" % path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return self.failed(name, "cannot read (%s)" % exc.__class__.__name__)
        count = len(text.splitlines())
        if count < min_lines:
            return self.warned(name, "%d lines, expected more than %d" % (count, min_lines))
        return self.passed(name, "%d lines, %d bytes" % (count, len(text.encode("utf-8"))))

    def check_interests(self):
        return self._text_file("config/interests.md", "config/interests.md", 40)

    def check_agents_md(self):
        return self._text_file("docs/AGENTS.md", "docs/AGENTS.md", 60)

    def check_dirs(self):
        """6. The four output directories exist and accept a temp file."""
        name, bad = "writable directories", []
        for rel in ("editions", "site", "site/assets", "state"):
            folder = self.root / rel
            if not folder.is_dir():
                bad.append(rel + " missing")
            elif not self._writable(folder):
                bad.append(rel + " does not accept a temp file")
        if bad:
            return self._fail_many(name, bad)
        return self.passed(name, "4/4 directories exist and accept a temp file")

    @staticmethod
    def _writable(folder):
        """Create and remove one temp file, so a read-only mount is caught."""
        try:
            handle, temp_path = tempfile.mkstemp(prefix=".doctor-", suffix=".tmp",
                                                 dir=str(folder))
            with open(handle, "w", encoding="utf-8") as stream:
                stream.write("ok\n")
            Path(temp_path).unlink()
            return True
        except OSError:
            return False

    def check_runtime(self):
        name, version = "runtime", "%d.%d.%d" % sys.version_info[:3]
        if sys.version_info < (3, 11):
            return self.failed(name, "Python %s, need 3.11 or newer" % version)
        missing = []
        for module in ("requests", "feedparser", "bs4", "PIL"):
            try:
                importlib.import_module(module)
            except Exception as exc:
                missing.append("%s (%s)" % (module, exc.__class__.__name__))
        if missing:
            return self.failed(name, "Python %s, cannot import: %s"
                               % (version, ", ".join(missing)))
        return self.passed(name, "Python %s, requests/feedparser/bs4/PIL all import" % version)

    def check_memory(self):
        name, path = "state/seen.sqlite", self.root / "state" / "seen.sqlite"
        if not path.is_file():
            return self.warned(name, "absent - no edition has been marked yet")
        try:
            with sqlite3.connect("file:%s?mode=ro" % path.as_posix(), uri=True, timeout=5) as link:
                rows = link.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        except sqlite3.Error as exc:
            return self.failed(name, "cannot open read-only (%s)" % exc.__class__.__name__)
        tables = set(row[0] for row in rows)
        missing = [table for table in REQUIRED_TABLES if table not in tables]
        if missing:
            return self.failed(name, "missing table(s): %s (present: %s)"
                               % (", ".join(missing), ", ".join(sorted(tables)) or "none"))
        return self.passed(name, "read-only open ok, tables: %s" % ", ".join(sorted(tables)))

    def _endpoints(self):
        found = []
        for rel, kind in (("config/feeds.json", "feed"), ("config/channels.json", "channel")):
            data, _ = load_json(self.root / rel)
            for entry in data if isinstance(data, list) else []:
                if not (isinstance(entry, dict) and entry.get("enabled") is True):
                    continue
                url, channel = entry.get("url"), entry.get("id")
                if kind == "feed" and isinstance(url, str) and url.startswith("https://"):
                    found.append(("feed %s" % ascii_text(entry.get("name"), 30), url))
                    break
                if kind == "channel" and isinstance(channel, str) \
                        and CHANNEL_ID_RE.match(channel):
                    found.append(("youtube rss", "https://www.youtube.com/feeds/videos.xml"
                                                 "?channel_id=" + channel))
                    break
        return found + [("github.com", "https://github.com")]

    def _probe(self, url):
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(request, timeout=NET_TIMEOUT) as response:
                code = getattr(response, "status", None) or response.getcode()
                return 200 <= int(code) < 400, "http %s" % code
        except urllib.error.HTTPError as exc:
            return False, "http %s" % exc.code
        except urllib.error.URLError as exc:
            return False, "unreachable (%s)" % ascii_text(exc.reason, 60)
        except Exception as exc:
            return False, "unreachable (%s)" % exc.__class__.__name__

    def check_network(self):
        if self.offline:
            return
        name, endpoints = "network", self._endpoints()
        parts, failures = [], 0
        for label, url in endpoints:
            ok, detail = self._probe(url)
            parts.append("%s %s" % (label, "ok" if ok else detail))
            failures += 0 if ok else 1
        summary = "%d/%d ok: %s" % (len(endpoints) - failures, len(endpoints), "; ".join(parts))
        if failures == len(endpoints):
            return self.failed(name, "all %d endpoints failed: %s"
                               % (len(endpoints), "; ".join(parts)))
        return self.warned(name, summary) if failures else self.passed(name, summary)

    def check_static(self):
        name, bad, sizes = "site static assets", [], []
        for rel in ("site/style.css", "site/app.js"):
            path = self.root / rel
            if not path.is_file():
                bad.append(rel + " missing")
            elif path.stat().st_size == 0:
                bad.append(rel + " is empty")
            else:
                sizes.append(path.stat().st_size)
        if bad:
            return self._fail_many(name, bad)
        base = "style.css %d B, app.js %d B" % (sizes[0], sizes[1])
        index = self.root / "site" / "index.html"
        if not index.is_file():
            return self.warned(name, base + "; site/index.html not built yet")
        return self.passed(name, "%s, index.html %d B" % (base, index.stat().st_size))

    def _run_fixture(self, script, out_dir):
        last = (1, "", "not run")
        for flag in ("--out", "--out-dir"):
            try:
                done = subprocess.run([sys.executable, str(script), "--fixture", flag,
                                       str(out_dir)], cwd=str(self.root), capture_output=True,
                                      text=True, encoding="utf-8", errors="replace",
                                      timeout=FIXTURE_TIMEOUT)
            except subprocess.TimeoutExpired:
                return 124, "", "timed out after %d s" % FIXTURE_TIMEOUT
            except OSError as exc:
                return 126, "", "cannot start build_edition.py (%s)" % exc.__class__.__name__
            last = (done.returncode, done.stdout or "", done.stderr or "")
            if done.returncode == 0 or done.returncode != 2 \
                    or "unrecognized arguments" not in last[1] + last[2]:
                break
        return last

    def check_fixture(self):
        """11. Build the fixture and audit the HTML it produced."""
        if self.quick:
            return
        name, script = "fixture build", self.root / "scripts" / "build_edition.py"
        if not script.is_file():
            return self.failed(name, "scripts/build_edition.py is missing")
        out_dir = self.root / "state" / FIXTURE_DIR
        shutil.rmtree(out_dir, ignore_errors=True)
        try:
            code, stdout, stderr = self._run_fixture(script, out_dir)
            self.kept_fixture = out_dir.exists()
            if code != 0:
                lines = [ln.strip() for ln in (stderr or stdout or "").splitlines() if ln.strip()]
                return self.failed(name, "build_edition.py --fixture exited %d: %s"
                                   % (code, ascii_text(lines[-1] if lines else "no output", 180)))
            index = out_dir / "index.html"
            if not index.is_file():
                return self.failed(name, "exit 0 but %s was not written" % index)
            problems = check_html(index)
            if problems:
                return self._fail_many(name + ": HTML", problems)
            return self.passed(name, "built and valid: %.1f KB html, tags balanced, anchors "
                                     "resolve, every img has alt text"
                               % (index.stat().st_size / 1024.0))
        finally:
            if self.kept_fixture and not self.keep:
                shutil.rmtree(out_dir, ignore_errors=True)
                self.kept_fixture = False

    def run(self):
        """12. Every check once, then the summary line and the exit code."""
        for step in (self.check_settings, self.check_channels, self.check_feeds,
                     self.check_interests, self.check_agents_md, self.check_dirs,
                     self.check_runtime, self.check_memory, self.check_network,
                     self.check_static, self.check_fixture):
            try:
                step()
            except Exception as exc:
                self.failed("unexpected:" + step.__name__,
                            "%s: %s" % (exc.__class__.__name__, ascii_text(exc, 120)))
        tally = {PASS: 0, FAIL: 0, WARN: 0}
        for item in self.results:
            tally[item["status"]] = tally.get(item["status"], 0) + 1
        if self.as_json:
            print(json.dumps({"root": str(self.root), "offline": self.offline,
                              "quick": self.quick, "passed": tally[PASS],
                              "failed": tally[FAIL], "warnings": tally[WARN],
                              "ok": tally[FAIL] == 0, "checks": self.results},
                             indent=2, ensure_ascii=True))
        else:
            print("doctor: %d passed, %d failed, %d warnings"
                  % (tally[PASS], tally[FAIL], tally[WARN]))
            if self.kept_fixture:
                print("doctor: fixture kept at %s" % (self.root / "state" / FIXTURE_DIR))
        return 1 if tally[FAIL] else 0

def attribute(tag_body, key):
    """Value of one attribute inside a tag body, or None."""
    for match in ATTR_RE.finditer(tag_body):
        if match.group(1).lower() == key:
            return match.group(2)[1:-1]
    return None

def check_html(path):
    """Doctype, size, balanced tags, resolvable anchors, non-empty img alt. Empty = good."""
    try:
        markup = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ["cannot read %s (%s)" % (path.name, exc.__class__.__name__)]
    size, problems = len(markup.encode("utf-8")), []
    if size >= MAX_HTML_BYTES:
        problems.append("html is %.1f MB, the limit is 3 MB" % (size / (1024.0 * 1024.0)))
    if "<!DOCTYPE html>" not in markup[:200]:
        problems.append("missing <!DOCTYPE html> at the top")
    cleaned = COMMENT_RE.sub("", markup)
    cleaned = SCRIPT_RE.sub(lambda mo: mo.group(1) + mo.group(3), cleaned)
    cleaned = STYLE_RE.sub(lambda mo: mo.group(1) + mo.group(3), cleaned)
    stack = []
    for match in TAG_RE.finditer(cleaned):
        closing, raw_name, _attrs, selfclose = match.groups()
        tag = raw_name.lower()
        if tag in VOID or selfclose:
            continue
        if not closing:
            stack.append(tag)
        elif not stack:
            problems.append("stray closing tag </%s>" % tag)
            break
        elif stack[-1] == tag:
            stack.pop()
        else:
            problems.append("</%s> closes <%s>" % (tag, stack[-1]))
            if tag in stack:
                while stack and stack.pop() != tag:
                    pass
    if stack:
        problems.append("unclosed tag(s): %s" % ", ".join("<%s>" % tag for tag in stack[-4:]))
    ids = set(filter(None, (attribute(m.group(0)[1:-1], "id")
                            for m in ANY_TAG_RE.finditer(cleaned))))
    missing = []
    for match in ANCHOR_RE.finditer(cleaned):
        if match.group(1) and match.group(1) not in ids and match.group(1) not in missing:
            missing.append(match.group(1))
    if missing:
        problems.append('href="#..." with no matching id: %s'
                        % ", ".join("#" + item for item in missing[:5]))
    for index, match in enumerate(IMG_RE.finditer(cleaned)):
        alt = attribute(match.group(1), "alt")
        if alt is None or not alt.strip():
            problems.append("img[%d] has no usable alt attribute" % index)
        if len(problems) >= 8:
            break
    return problems

def build_parser():
    parser = argparse.ArgumentParser(
        prog="doctor.py",
        description="Self-check the Daily Beacon project: config, writable paths, memory DB, "
                    "network, static assets and a fixture build.",
        epilog="Checks 1-12 run in order: exit 0 when nothing FAILed (WARN is fine), 1 when at "
               "least one check failed, 2 on a usage error.")
    parser.add_argument("--offline", action="store_true", help="skip the network check (9)")
    parser.add_argument("--quick", action="store_true",
                        help="skip the fixture build (11); writes nothing to state/")
    parser.add_argument("--keep", action="store_true",
                        help="keep state/doctor-fixture after the fixture build")
    parser.add_argument("--root", metavar="PATH", default=None,
                        help="project root (default: parent of scripts/)")
    parser.add_argument("--json", action="store_true",
                        help="emit the same results as one JSON object on stdout")
    return parser

def main(argv=None):
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve() if args.root \
        else Path(__file__).resolve().parents[1]
    if not root.is_dir():
        print("doctor: root is not a directory: %s" % root, file=sys.stderr)
        return 2
    return Doctor(root, args.offline, args.quick, args.keep, args.json).run()

if __name__ == "__main__":
    raise SystemExit(main())
