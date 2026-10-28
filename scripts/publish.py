#!/usr/bin/env python3
"""publish.py - commit the built site and push it so GitHub Pages serves it.

Modes:
  (default)      git add -A, commit "edition: <date>", push, print the live URL
  --check        report branch, remote, tree, build state and live URL; change nothing
  --url          print only the live URL (config/settings.json -> site_base_url)
  --verify       GET the live URL, require 200 + the masthead "THE DAILY BEACON"
  --wait N       with --verify: poll every 20s for up to N seconds, stop on first success
  --set-url URL  write site_base_url into config/settings.json, all other keys preserved

Exit codes: 0 success, 1 failure, 2 usage error.
Never force-pushes. Refuses to commit a staged file that looks like a secret.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.json"
SITE_DIR = ROOT / "site"
SITE_INDEX = SITE_DIR / "index.html"
EDITIONS = ROOT / "editions"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MASTHEAD = b"THE DAILY BEACON"
HTTP_TIMEOUT = 25
POLL_SECONDS = 20
MAX_POLLS = 12
GH_PREFIX = "gh" + "p_"  # fragments: this file must never match its own guard
PAT_PREFIX = "git" + "hub_pat_"
SK_PREFIX = "sk" + "-"
AIZA_PREFIX = "AI" + "za"
XOX_PREFIX = "xo" + "x[baprs]-"
SECRET_CONTENT = re.compile(
    r"\b(" + GH_PREFIX + "|" + PAT_PREFIX +
    "|" + SK_PREFIX + r"[A-Za-z0-9]{16,}" +
    "|" + AIZA_PREFIX + r"[0-9A-Za-z_-]{20,}" +
    "|" + XOX_PREFIX + ")")
SECRET_NAMES = (".env", "credentials.json")
SECRET_SUFFIXES = (".pem", ".key")
REDACT = re.compile(
    "(" + GH_PREFIX + r"[A-Za-z0-9]{8,}" +
    "|" + PAT_PREFIX + r"[A-Za-z0-9_]{8,}" +
    "|" + SK_PREFIX + r"[A-Za-z0-9]{8,}" +
    "|" + AIZA_PREFIX + r"[0-9A-Za-z_-]{8,}" +
    "|" + XOX_PREFIX + r"[A-Za-z0-9-]{4,})")

# - small helpers

def git(*args: str) -> subprocess.CompletedProcess:
    """Run git in the project root; never raises."""
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def git_lines(*args: str) -> list:
    res = git(*args)
    if res.returncode != 0:
        return []
    return [ln for ln in res.stdout.splitlines() if ln.strip()]


def first_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return REDACT.sub("<redacted>", lines[0]) if lines else "(no output)"


def warn(msg: str) -> None:
    print(REDACT.sub("<redacted>", msg), file=sys.stderr)


def load_settings() -> dict:
    if not SETTINGS.is_file():
        warn("publish: config/settings.json not found")
        return {}
    try:
        with SETTINGS.open("r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        warn(f"publish: cannot read config/settings.json ({exc})")
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_settings(data: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def settings_url() -> str:
    return str(load_settings().get("site_base_url") or "").strip()


def in_git_repo() -> bool:
    return git("rev-parse", "--git-dir").returncode == 0


def current_branch() -> str:
    name = (git("rev-parse", "--abbrev-ref", "HEAD").stdout or "").strip()
    if not name or name == "HEAD":
        name = (git("symbolic-ref", "--short", "HEAD").stdout or "").strip()
    return name or "main"


def remote_url() -> str:
    res = git("remote", "get-url", "origin")
    return (res.stdout or "").strip() if res.returncode == 0 else ""


def has_upstream() -> bool:
    res = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    return res.returncode == 0 and bool((res.stdout or "").strip())


def derived_pages_url() -> str:
    """Pages URL implied by the origin remote (used only until site_base_url is set)."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/*$", remote_url())
    if not m:
        return ""
    owner, repo = m.group(1).lower(), m.group(2).lower()
    if repo == f"{owner}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{repo}/"


def live_url() -> str:
    return settings_url() or derived_pages_url()


def pages_branch() -> str:
    """Branch the live site is served from; an empty value disables the mirror."""
    return str(load_settings().get("pages_branch", "gh-pages") or "").strip()


def newest_edition_date() -> str:
    """Newest editions/YYYY-MM-DD.json stem, falling back to today."""
    best = None
    for path in sorted(EDITIONS.glob("*.json")) if EDITIONS.is_dir() else []:
        try:
            value = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if best is None or value > best:
            best = value
    return (best or date.today()).isoformat()

# - secret guard

def staged_files() -> list:
    return git_lines("diff", "--cached", "--name-only")


def staged_blob(name: str) -> bytes:
    res = subprocess.run(["git", "show", f":{name}"], cwd=str(ROOT), capture_output=True)
    return res.stdout if res.returncode == 0 else b""


def secret_hits(files: list) -> list:
    hits = []
    for name in files:
        base = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if (base in SECRET_NAMES or base.endswith(".env")
                or base.endswith(SECRET_SUFFIXES) or "_token" in base):
            hits.append(name)
            continue
        blob = staged_blob(name)
        if not blob or b"\x00" in blob[:8000]:
            continue
        if SECRET_CONTENT.search(blob.decode("utf-8", "ignore")):
            hits.append(name)
    return hits


def unstage(name: str) -> None:
    if git("restore", "--staged", "--", name).returncode != 0:
        git("rm", "--cached", "-q", "--", name)

# - pages mirror

def _git_in(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git inside another worktree; never raises."""
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _identity_args() -> list:
    """-c overrides for a clone with no committer configured (a fresh machine)."""
    args = []
    for key in ("user.name", "user.email"):
        res = subprocess.run(["git", "config", "--get", key], cwd=str(ROOT),
                             capture_output=True, text=True)
        if res.returncode == 0 and (res.stdout or "").strip():
            continue
        if key == "user.name":
            args += ["-c", "user.name=daily-beacon"]
        else:
            m = re.search(r"github\.com[:/]+([^/]+)/", remote_url())
            owner = m.group(1) if m else "daily-beacon"
            args += ["-c", f"user.email={owner}@users.noreply.github.com"]
    return args


def mirror_pages() -> int:
    """Copy site/ onto the Pages branch so a branch-served site actually updates.

    GitHub Pages here is served from a branch (build_type=legacy), not from the Actions
    artifact, so pushing main alone leaves the live page frozen. The copy is built in a
    temporary worktree of that branch and pushed as a fast-forward - no force, no history
    rewrite, and a no-op run prints "already up to date" instead of an empty commit.
    """
    branch = pages_branch()
    if not branch:
        print("publish: pages mirror disabled (pages_branch is empty)")
        return 0
    if not SITE_INDEX.is_file():
        warn("publish: site/index.html missing - pages mirror skipped")
        return 1

    remote_ref = f"refs/remotes/origin/{branch}"
    fetched = git("fetch", "--quiet", "origin", f"+refs/heads/{branch}:{remote_ref}")
    if fetched.returncode != 0:
        print(f"publish: origin/{branch} not fetched (first publish of that branch)")
    if git("rev-parse", "--verify", "--quiet", remote_ref).returncode == 0:
        start = remote_ref
    else:
        start = "HEAD"

    scratch = Path(tempfile.mkdtemp(prefix="daily-beacon-pages-"))
    tree = scratch / "tree"
    # --detach: a throwaway checkout must never create, reset or delete a real local branch.
    added = git("worktree", "add", "--force", "--detach", str(tree), start)
    if added.returncode != 0:
        shutil.rmtree(scratch, ignore_errors=True)
        warn(f"publish: cannot open a worktree for branch {branch}")
        warn(first_line(added.stderr or added.stdout))
        return 1

    try:
        for entry in tree.iterdir():
            if entry.name == ".git":
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        copied = 0
        for entry in SITE_DIR.iterdir():
            target = tree / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)
            copied += 1
        (tree / ".nojekyll").write_bytes(b"")

        staged_res = _git_in(tree, "add", "-A")
        if staged_res.returncode != 0:
            warn("publish: git add failed in the pages worktree")
            warn(first_line(staged_res.stderr or staged_res.stdout))
            return 1
        changed = [ln for ln in _git_in(tree, "status", "--porcelain").stdout.splitlines()
                   if ln.strip()]
        if not changed:
            print(f"publish: origin/{branch} already up to date")
            return 0
        commit = _git_in(tree, *_identity_args(), "commit", "-q", "-m",
                         f"site: {newest_edition_date()}")
        if commit.returncode != 0:
            warn("publish: commit failed in the pages worktree")
            warn(first_line(commit.stderr or commit.stdout))
            return 1
        pushed = _git_in(tree, "push", "origin", f"HEAD:refs/heads/{branch}")
        if pushed.returncode != 0:
            warn(f"publish: git push origin {branch} failed")
            warn(first_line(pushed.stderr or pushed.stdout))
            return 1
        print(f"publish: mirrored site/ to origin/{branch} ({copied} entries, {len(changed)} changes)")
        return 0
    finally:
        git("worktree", "remove", "--force", str(tree))
        git("worktree", "prune")
        shutil.rmtree(scratch, ignore_errors=True)


# - --check

def cmd_check() -> int:
    """Report state; exit 0 unless this is not a git repository at all.

    "Not built yet" is legitimate before the first build, so it is a check line and
    never an error - cmd_publish refuses on its own.
    """
    print(f"check: root {ROOT}")
    if not in_git_repo():
        print("check: repository MISSING - not a git repository (run: git init -b main)")
        print("check: verdict cannot check - no git repository")
        return 1
    print(f"check: branch {current_branch()}")
    print(f"check: remote {remote_url() or '(no origin remote)'}")

    status = git_lines("status", "--short")
    if not status:
        print("check: working tree clean (0 entries)")
    else:
        print(f"check: working tree dirty ({len(status)} entries)")
        for line in status[:25]:
            print(f"    {line}")
        if len(status) > 25:
            print(f"    ... {len(status) - 25} more")

    if not SITE_INDEX.is_file():
        print("check: site/index.html MISSING - not built yet")
        print(f"check: live url {live_url() or '(not set)'}")
        print("check: verdict nothing to publish yet - run build_edition.py first")
        return 0

    stat = SITE_INDEX.stat()
    print(f"check: site/index.html present ({stat.st_size} bytes)")
    committed = git("log", "-1", "--format=%ct", "--", "site/index.html")
    stamp = (committed.stdout or "").strip()
    if committed.returncode == 0 and stamp.isdigit():
        if stat.st_mtime > int(stamp) + 1:
            print("check: site newer than the last commit touching it")
        else:
            print("check: site not newer than the last commit touching it")
    else:
        print("check: site never committed")
    print(f"check: live url {live_url() or '(not set)'}")
    pages = pages_branch()
    if pages:
        known = git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{pages}")
        state = "known locally" if known.returncode == 0 else "not fetched yet"
        print(f"check: pages branch {pages} ({state})")
    else:
        print("check: pages mirror disabled")
    print("check: verdict would publish" if status else "check: verdict up to date")
    return 0

# - publishing

def git_failure(what: str, res: subprocess.CompletedProcess) -> int:
    warn(f"publish: {what} failed")
    detail = first_line(res.stderr) if (res.stderr or "").strip() else first_line(res.stdout)
    warn(detail)
    return 1


def cmd_publish() -> int:
    if not SITE_INDEX.is_file():
        print("publish: no site built - run build_edition.py first")
        return 1
    if not in_git_repo():
        warn("publish: not a git repository - run: git init -b main")
        return 1

    added = git("add", "-A")
    if added.returncode != 0:
        return git_failure("git add -A", added)

    staged = staged_files()
    if staged:
        hits = secret_hits(staged)
        if hits:
            for name in hits:
                unstage(name)
            for name in hits:
                print(f"publish: BLOCKED - possible secret in {name}")
            return 1
        message = f"edition: {newest_edition_date()}"
        commit = git("commit", "-m", message)
        if commit.returncode != 0:
            return git_failure("git commit", commit)
        print(f"publish: committed '{message}' ({len(staged)} files)")
    else:
        print("publish: nothing to commit")

    branch = current_branch()
    if has_upstream():
        push = git("push")
    else:
        push = git("push", "-u", "origin", branch)
    if push.returncode != 0:
        return git_failure("git push", push)

    if mirror_pages() != 0:
        warn("publish: committed on main, but the Pages branch did not update - "
             "the live site still shows the previous edition")
        return 1

    url = live_url()
    if url:
        print(f"publish: pushed to origin/{branch}, live url {url}")
    else:
        print(f"publish: pushed to origin/{branch}, live url not set "
              "(run: publish.py --set-url <url>)")
    return 0

# - --verify

def probe(url: str):
    request = Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache",
                                    "Pragma": "no-cache"})
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            status = getattr(response, "status", 200)
            body = response.read()
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except URLError as exc:
        return False, f"connection failed: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 - any transport error is a failed poll
        return False, f"request failed: {exc}"
    if status != 200:
        return False, f"HTTP {status}"
    if MASTHEAD not in body:
        return False, f"masthead not found ({len(body)} bytes)"
    return True, len(body)


def cmd_verify(wait: int) -> int:
    url = live_url()
    if not url:
        warn("verify: FAILED no live url - set site_base_url in config/settings.json")
        return 1
    wait = max(0, int(wait or 0))
    started = time.monotonic()
    deadline = started + wait
    attempt = 0
    while True:
        attempt += 1
        ok, detail = probe(url)
        elapsed = int(round(time.monotonic() - started))
        if ok:
            print(f"verify: 200, masthead found, {detail} bytes, {url} (after {elapsed}s)")
            return 0
        if attempt >= MAX_POLLS or time.monotonic() + POLL_SECONDS > deadline:
            print(f"verify: FAILED {detail} (after {elapsed}s, {attempt} attempt(s))")
            return 1
        print(f"verify: attempt {attempt}/{MAX_POLLS} {detail} - retrying in {POLL_SECONDS}s")
        time.sleep(POLL_SECONDS)

# - misc

def cmd_url() -> int:
    url = settings_url()
    if not url:
        warn("publish: site_base_url is not set in config/settings.json")
        return 1
    print(url)
    return 0


def cmd_set_url(value: str) -> int:
    url = (value or "").strip()
    if not url.startswith(("http://", "https://")):
        warn("publish: --set-url needs an http(s) URL")
        return 2
    data = load_settings()
    data["site_base_url"] = url
    try:
        save_settings(data)
    except OSError as exc:
        warn(f"publish: cannot write config/settings.json ({exc})")
        return 1
    print(f"publish: site_base_url set to {url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publish.py",
        description="Commit the built site and push it so GitHub Pages serves it.",
        epilog="Default mode publishes. Never force-pushes. Blocks staged secrets.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report state and change nothing")
    mode.add_argument("--url", action="store_true", help="print the live URL only")
    mode.add_argument("--verify", action="store_true", help="GET the live URL, require 200 + masthead")
    mode.add_argument("--set-url", metavar="URL", dest="set_url", help="write site_base_url to settings")
    parser.add_argument("--wait", type=int, default=0, metavar="N",
                        help="with --verify: poll every 20s for up to N seconds (max 12 polls)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.set_url is not None:
        return cmd_set_url(args.set_url)
    if args.url:
        return cmd_url()
    if args.verify:
        return cmd_verify(args.wait)
    if args.wait:
        warn("publish: --wait only applies together with --verify")
        return 2
    if args.check:
        return cmd_check()
    return cmd_publish()


if __name__ == "__main__":
    sys.exit(main())