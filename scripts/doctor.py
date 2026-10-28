#!/usr/bin/env python3
"""doctor.py - self-check for the Daily Beacon project.

    python scripts/doctor.py [--offline] [--quick] [--keep] [--root PATH] [--json]

Thirteen checks, one PASS/FAIL/WARN line each: settings keys and types; channels and feeds shape;
interests.md and AGENTS.md size; writable output dirs; Python plus requests/feedparser/bs4/PIL;
seen.sqlite tables; three network endpoints; static assets; a fixture build whose HTML is audited;
the summary line and exit code. Only `state/doctor-fixture` is written, removed unless --keep.
Exit 0 when nothing failed (warnings allowed), 1 on any FAIL, 2 on a usage error. ASCII only.
"""
from __future__ import annotations

import argparse, importlib, json, os, re, shutil, sqlite3, subprocess, sys, tempfile
import urllib.error, urllib.request
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
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
NET_TIMEOUT, FIXTURE_TIMEOUT, MAX_HTML_BYTES, FIXTURE_DIR = 15, 90, 3 << 20, "doctor-fixture"
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


class Doctor:
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
        self.failed(name, "%d problem(s): %s"
                    % (len(problems), "; ".join(str(part) for part in problems[:6])))

    def check_settings(self):
        name, path = "config/settings.json", self.root / "config" / "settings.json"
        if not path.is_file():
            return self.failed(name, "missing: %s" % path)
        data, error = load_json(path)
        if error or not isinstance(data, dict):
            return self.failed(name, error or "top level must be a JSON object")
        bad, extra = [], set(data) - set(key for key, _ in SETTINGS_TYPES)
        for key, want in SETTINGS_TYPES:
            if key not in data:
                bad.append("missing '%s'" % key)
            elif not ((isinstance(data[key], int) and not isinstance(data[key], bool))
                      if want is int else isinstance(data[key], want)):
                bad.append("'%s' must be %s" % (key, want.__name__))
        if bad:
            return self._fail_many(name, bad)
        return self.passed(name, "all %d spec keys present%s"
                           % (len(SETTINGS_TYPES), " (extra: %s)" % ", ".join(sorted(extra)[:4])
                              if extra else ""))

    def _check_list(self, name, rel, required, kind):
        path = self.root / rel
        if not path.is_file():
            return self.failed(name, "missing: %s" % path)
        data, error = load_json(path)
        if error:
            return self.failed(name, error)
        if not isinstance(data, list) or not data:
            return self.failed(name, "top level must be a non-empty JSON array")
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
            enabled += 1 if entry.get("enabled") is True else 0
            if kind == "channel":
                if not (isinstance(entry.get("id"), str) and CHANNEL_ID_RE.match(entry["id"])):
                    bad.append(where + " id is not a UC... channel id")
                tier = entry.get("tier")
                if isinstance(tier, int) and not isinstance(tier, bool) and tier in (1, 2, 3):
                    tiers[tier] += 1
                else:
                    bad.append(where + " tier must be 1, 2 or 3")
                continue
            url, tags = entry.get("url"), entry.get("tags")
            if not isinstance(url, str) or not url.startswith("https://"):
                bad.append("%s url is not https (%s)" % (where, ascii_text(url, 50)))
            if not (isinstance(tags, list) and all(isinstance(tag, str) for tag in tags)):
                bad.append(where + " tags must be an array of strings")
        if bad:
            return self._fail_many(name, bad)
        if kind == "channel":
            return self.passed(name, "%d channels, %d enabled, tier 1/2/3 = %d/%d/%d"
                               % (len(data), enabled, tiers[1], tiers[2], tiers[3]))
        return self.passed(name, "%d feeds, %d enabled, every url https" % (len(data), enabled))

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

    def check_dirs(self):
        bad = []
        for rel in ("editions", "site", "site/assets", "state"):
            folder = self.root / rel
            if not folder.is_dir():
                bad.append(rel + " missing")
            elif not self._writable(folder):
                bad.append(rel + " does not accept a temp file")
        if bad:
            return self._fail_many("writable directories", bad)
        return self.passed("writable directories", "4/4 exist and accept a temp file")

    @staticmethod
    def _writable(folder):
        """Create and remove one temp file, so a read-only location is caught."""
        probe = folder / (".doctor-%d.tmp" % os.getpid())
        try:
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink()
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
                rows = link.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = sorted(row[0] for row in rows.fetchall())
        except sqlite3.Error as exc:
            return self.failed(name, "cannot open read-only (%s)" % exc.__class__.__name__)
        missing = sorted(set(REQUIRED_TABLES) - set(tables))
        if missing:
            return self.failed(name, "missing table(s): %s (present: %s)"
                               % (", ".join(missing), ", ".join(tables) or "none"))
        return self.passed(name, "read-only open ok, tables: %s" % ", ".join(tables))

    def check_channel_policy(self):
        """The owner's brief, checked mechanically instead of trusted to the agent."""
        name = "channel policy"
        data, problem = load_json(self.root / "config" / "channels.json")
        if problem:
            return self.failed(name, problem)
        rows = data if isinstance(data, list) else data.get("channels") or []
        on = [c for c in rows if c.get("enabled") is True]
        notes_missing = [c.get("name", "?") for c in rows
                         if c.get("enabled") is not True and not (c.get("note") or "").strip()]
        # namings that are unambiguous violations of the brief if they are ever switched on
        banned = {"mrbeast", "jt music", "teminite", "skeler.", "asmongold clips",
                  "asmongold shorts", "viva la dirt league", "meatcanyon", "flashgitz"}
        leaked = sorted(c.get("name", "?") for c in on if c.get("name", "").lower() in banned)
        detail = "%d enabled of %d" % (len(on), len(rows))
        if leaked:
            return self.failed(name, detail + "; entertainment channels are enabled: " + ", ".join(leaked))
        if notes_missing:
            return self.warned(name, detail + "; disabled without a reason: " + ", ".join(notes_missing[:4]))
        return self.passed(name, detail + ", every disabled channel carries a reason")

    def _endpoints(self):
        """Exactly three probes: one feed, one channel RSS, github.com."""
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
                if kind == "channel" and isinstance(channel, str) and CHANNEL_ID_RE.match(channel):
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
        except Exception as exc:
            return False, "unreachable (%s)" % ascii_text(
                getattr(exc, "reason", exc.__class__.__name__), 60)

    def check_network(self):
        if self.offline:
            return
        name, endpoints = "network", self._endpoints()
        parts, failures = [], 0
        for label, url in endpoints:
            ok, detail = self._probe(url)
            parts.append("%s %s" % (label, "ok" if ok else detail))
            failures += 0 if ok else 1
        if failures == len(endpoints):
            return self.failed(name, "all %d endpoints failed: %s"
                               % (len(endpoints), "; ".join(parts)))
        summary = "%d/%d ok: %s" % (len(endpoints) - failures, len(endpoints), "; ".join(parts))
        return self.warned(name, summary) if failures else self.passed(name, summary)

    def check_static(self):
        name, bad, sizes = "site static assets", [], []
        for rel in ("site/style.css", "site/app.js"):
            path = self.root / rel
            ok = path.is_file() and path.stat().st_size > 0
            sizes.append(path.stat().st_size if ok else 0)
            if not ok:
                bad.append(rel + (" is empty" if path.is_file() else " missing"))
        if bad:
            return self._fail_many(name, bad)
        index = self.root / "site" / "index.html"
        base = "style.css %d B, app.js %d B" % tuple(sizes)
        if not index.is_file():
            return self.warned(name, base + "; index.html not built yet")
        return self.passed(name, "%s, index.html %d B" % (base, index.stat().st_size))

    def _run_fixture(self, script, out_dir):
        """--fixture under both spellings of the out flag; only a usage error (exit 2) falls
        through, because the builder changed that flag once."""
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
            if done.returncode != 2 or "unrecognized arguments" not in last[1] + last[2]:
                break
        return last

    def check_fixture(self):
        if self.quick:
            return
        name, script = "fixture build", self.root / "scripts" / "build_edition.py"
        if not script.is_file():
            return self.failed(name, "scripts/build_edition.py missing")
        out_dir = self.root / "state" / FIXTURE_DIR
        shutil.rmtree(out_dir, ignore_errors=True)
        try:
            code, stdout, stderr = self._run_fixture(script, out_dir)
            self.kept_fixture = out_dir.exists()
            if code != 0:
                tail = [ln.strip() for ln in (stderr or stdout or "").splitlines() if ln.strip()]
                return self.failed(name, "build_edition.py --fixture exited %d: %s"
                                   % (code, ascii_text(tail[-1] if tail else "no output", 180)))
            index = out_dir / "index.html"
            problems = ["exit 0 but index.html was not written"] if not index.is_file() \
                else check_html(index)
            if problems:
                return self._fail_many(name + ": HTML", problems)
            return self.passed(name, "built and valid: %.1f KB html, tags balanced, anchors "
                                     "resolve, every img has alt text"
                               % (index.stat().st_size / 1024.0))
        finally:
            if self.kept_fixture and not self.keep:
                shutil.rmtree(out_dir, ignore_errors=True)
                self.kept_fixture = False

    def check_business_events(self):
        """The detector that exists because the 2026-10-28 edition missed EA closing BioWare."""
        import subprocess
        script = self.root / "scripts" / "test_business_events.py"
        if not script.is_file():
            self.failed("business events", "scripts/test_business_events.py missing")
            return
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, timeout=120,
                cwd=str(self.root), encoding="utf-8", errors="replace",
            )
        except Exception as exc:
            self.failed("business events", "%s: %s" % (exc.__class__.__name__, ascii_text(exc, 90)))
            return
        if proc.returncode == 0:
            last = [ln for ln in (proc.stdout or "").splitlines() if "PASS" in ln or "FAIL" in ln]
            self.passed("business events", last[-1].strip() if last else "detector ok")
        else:
            tail = [ln.strip() for ln in (proc.stdout or "").splitlines() if "FAIL" in ln]
            self.failed("business events", (tail[0] if tail else "detector test failed"))

    def run(self):
        checks = (
            ("settings", self.check_settings),
            ("channels", lambda: self._check_list("config/channels.json", "config/channels.json",
                                                 ("id", "name", "tier", "enabled"), "channel")),
            ("feeds", lambda: self._check_list("config/feeds.json", "config/feeds.json",
                                              ("name", "url", "tags", "enabled"), "feed")),
            ("policy", self.check_channel_policy),
            ("business events", self.check_business_events),
            ("interests", lambda: self._text_file("config/interests.md",
                                                 "config/interests.md", 40)),
            ("agents.md", lambda: self._text_file("docs/AGENTS.md", "docs/AGENTS.md", 60)),
            ("dirs", self.check_dirs), ("runtime", self.check_runtime),
            ("memory", self.check_memory), ("network", self.check_network),
            ("static", self.check_static), ("fixture", self.check_fixture))
        for label, step in checks:
            try:
                step()
            except Exception as exc:
                self.failed("unexpected:" + label,
                            "%s: %s" % (exc.__class__.__name__, ascii_text(exc, 120)))
        tally = {key: sum(1 for item in self.results if item["status"] == key)
                 for key in (PASS, FAIL, WARN)}
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


def check_html(path):
    """Doctype, size, balanced tags, resolvable anchors, usable img alt. Empty list = good."""
    try:
        markup = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ["cannot read %s (%s)" % (path.name, exc.__class__.__name__)]
    problems = []
    if len(markup.encode("utf-8")) >= MAX_HTML_BYTES:
        problems.append("html is 3 MB or larger")
    if not markup.lstrip().startswith("<!DOCTYPE html>"):
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

    def attribute(tag_body, key):
        for found in ATTR_RE.finditer(tag_body):
            if found.group(1).lower() == key:
                return found.group(2)[1:-1]
        return None

    ids = set(filter(None, (attribute(m.group(0)[1:-1], "id")
                            for m in ANY_TAG_RE.finditer(cleaned))))
    missing = sorted({m.group(1) for m in ANCHOR_RE.finditer(cleaned)
                      if m.group(1) and m.group(1) not in ids})
    if missing:
        problems.append('href="#..." with no matching id: %s'
                        % ", ".join("#" + item for item in missing[:5]))
    for match in IMG_RE.finditer(cleaned):
        alt = attribute(match.group(1), "alt")
        if alt is None or not alt.strip():
            problems.append("<img> without usable alt text")
            break
    return problems


def build_parser():
    parser = argparse.ArgumentParser(
        prog="doctor.py",
        description="Self-check the Daily Beacon project: config, writable paths, memory DB, "
                    "network, static assets and a fixture build.",
        epilog="Checks 1-12 in order. Exit 0 when nothing FAILed (a WARN is fine), 1 on any "
               "FAIL, 2 on a usage error.")
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
