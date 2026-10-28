// test_scheduler_formats.mjs - proves every `when` format of the OpenCode scheduler plugin:
// accepted shapes, sharp rejection and catch-up maths. Plain node, no deps, ES module.
// Run: node scripts/test_scheduler_formats.mjs
//
// Imports the REAL plugin source (node 24 strips the TypeScript natively).

process.removeAllListeners("warning")

const PLUGIN = "file:///C:/Users/MarciNaro/.config/opencode/plugins/scheduler/index.ts"

let parseWhen
let computeDue
try {
  const mod = await import(PLUGIN)
  parseWhen = mod.parseWhen
  computeDue = mod.computeDue
} catch (e) {
  console.log("FAIL import plugin: " + (e && e.message ? e.message : String(e)))
  process.exitCode = 1
  console.log("FORMATS FAILED")
  process.exit(1)
}

let pass = 0
let fail = 0

function check(kind, what, cond, detail) {
  if (cond) {
    pass++
    console.log("PASS " + kind + " " + what)
  } else {
    fail++
    process.exitCode = 1
    console.log("FAIL " + kind + " " + what + (detail == null ? "" : " -- " + String(detail)))
  }
}

// Local-time constructors only, so nothing depends on the machine timezone.
const at = (y, mo, d, h, mi) => new Date(y, mo - 1, d, h, mi, 0, 0).getTime()
const show = (ms) => (ms == null || !Number.isFinite(ms) ? String(ms) : new Date(ms).toString().slice(0, 21))
const sameList = (a, b) => Array.isArray(a) && a.length === b.length && a.every((v, i) => v === b[i])
const spec = (when) => {
  const r = parseWhen(when)
  if (!r.ok) throw new Error("parse failed: " + when + " -> " + r.reason)
  return r.spec
}
const due = (when, created, lastFired, now) => computeDue(spec(when), created, lastFired, now)
const rejects = (kind, when) => {
  const r = parseWhen(when)
  check(kind, "rejects " + when, r.ok === false && typeof r.reason === "string" && r.reason.length > 0, JSON.stringify(r))
}

/* ------------------------------------------------------------------ once */
{
  const s = spec("once:2026-10-30T09:00")
  check("once", "spec kind + atMs", s.kind === "once" && s.atMs === at(2026, 10, 30, 9, 0), JSON.stringify(s))
  const s2 = spec("once:2026-01-01T00:00")
  check("once", "midnight atMs", s2.kind === "once" && s2.atMs === at(2026, 1, 1, 0, 0), JSON.stringify(s2))
  rejects("once", "once:2026-13-01T09:00")
  rejects("once", "once:2026-02-30T09:00")
  rejects("once", "once:tomorrow")
  const NOW = at(2026, 10, 28, 10, 0)
  check("once", "computeDue ignores refs", due("once:2026-10-30T09:00", NOW, NOW, NOW) === at(2026, 10, 30, 9, 0))
}

/* ----------------------------------------------------------------- every */
{
  const s = spec("every:30m")
  check("every", "30m -> 1800000ms", s.kind === "every" && s.ms === 1800000, JSON.stringify(s))
  const s2 = spec("every:2h")
  check("every", "2h -> 7200000ms", s2.kind === "every" && s2.ms === 7200000, JSON.stringify(s2))
  const s3 = spec("every:3d")
  check("every", "3d -> 259200000ms", s3.kind === "every" && s3.ms === 259200000, JSON.stringify(s3))
  rejects("every", "every:0m")
  rejects("every", "every:30s")
  rejects("every", "every:")
  const created = at(2026, 10, 28, 10, 0)
  const first = due("every:30m", created, 0, created)
  check("every", "arithmetic alignment from createdAt", first - created === 30 * 60000, (first - created) + "ms")
  const second = due("every:30m", created, first, created)
  check("every", "next slot is createdAt + 60m", second - created === 60 * 60000, (second - created) + "ms")
  const caught = due("every:2h", at(2026, 10, 1, 10, 0), at(2026, 10, 21, 10, 0), at(2026, 10, 28, 10, 0))
  check("every", "catch-up stays on the 2h grid", caught === at(2026, 10, 21, 12, 0), show(caught))
}

/* ----------------------------------------------------------------- daily */
{
  const s = spec("daily:09:00")
  check("daily", "09:00 -> h9 m0", s.kind === "daily" && s.h === 9 && s.m === 0, JSON.stringify(s))
  const s2 = spec("daily:23:59")
  check("daily", "23:59 -> h23 m59", s2.kind === "daily" && s2.h === 23 && s2.m === 59, JSON.stringify(s2))
  rejects("daily", "daily:24:00")
  rejects("daily", "daily:09:60")
  rejects("daily", "daily:9")
  const NOW = at(2026, 10, 28, 10, 0)
  check("daily", "past slot -> tomorrow", due("daily:09:00", NOW, 0, NOW) === at(2026, 10, 29, 9, 0), show(due("daily:09:00", NOW, 0, NOW)))
  check("daily", "future slot -> today", due("daily:23:00", NOW, 0, NOW) === at(2026, 10, 28, 23, 0), show(due("daily:23:00", NOW, 0, NOW)))
  const created = at(2026, 10, 27, 8, 0)
  const missed = due("daily:03:00", created, 0, NOW)
  check("daily", "missed slot returns a past timestamp", missed === at(2026, 10, 28, 3, 0) && missed < NOW, show(missed))
  const after = due("daily:03:00", created, missed, NOW)
  check("daily", "after that fire -> next future slot", after === at(2026, 10, 29, 3, 0) && after > NOW, show(after))
}
/* ---------------------------------------------------------------- hourly */
{
  const s = spec("hourly:30")
  check("hourly", "30 -> m30", s.kind === "hourly" && s.m === 30, JSON.stringify(s))
  const s2 = spec("hourly:05")
  check("hourly", "05 (2 digits) -> m5", s2.kind === "hourly" && s2.m === 5, JSON.stringify(s2))
  const s3 = spec("hourly:5")
  check("hourly", "5 (1 digit) -> m5", s3.kind === "hourly" && s3.m === 5, JSON.stringify(s3))
  rejects("hourly", "hourly:60")
  rejects("hourly", "hourly:")
  rejects("hourly", "hourly:9:30")
  const ref1 = at(2026, 10, 28, 10, 0)
  const d1 = due("hourly:30", ref1, 0, ref1)
  check("hourly", "next slot <= ref + 60m", Number.isFinite(d1) && d1 > ref1 && d1 - ref1 <= 60 * 60000, (d1 - ref1) + "ms")
  check("hourly", "minute is always 30", new Date(d1).getMinutes() === 30, new Date(d1).toString())
  const ref2 = at(2026, 10, 28, 10, 45)
  const d2 = due("hourly:30", ref2, 0, ref2)
  check("hourly", "past :30 -> next hour :30", d2 === at(2026, 10, 28, 11, 30), show(d2))
  const missed = due("hourly:15", at(2026, 10, 1, 0, 0), at(2026, 10, 21, 10, 15), at(2026, 10, 28, 10, 0))
  check("hourly", "catch-up -> exactly one hour later", missed === at(2026, 10, 21, 11, 15), show(missed))
}

/* ------------------------------------------------------------------ days */
{
  const s = spec("days:3@03:00")
  check("days", "spec kind + n3 h3 m0", s.kind === "days" && s.n === 3 && s.h === 3 && s.m === 0, JSON.stringify(s))
  const s2 = spec("days:1@23:30")
  check("days", "n1 h23 m30", s2.kind === "days" && s2.n === 1 && s2.h === 23 && s2.m === 30, JSON.stringify(s2))
  rejects("days", "days:0@03:00")
  rejects("days", "days:3@25:00")
  rejects("days", "days:3")
  rejects("days", "days:3@03:00 extra")
  const NOW = at(2026, 10, 28, 10, 0)
  const created = at(2026, 10, 1, 10, 0)
  const LF = at(2026, 10, 21, 10, 0)
  const first = due("days:3@03:00", created, LF, NOW)
  check("days", "7-day gap -> one slot, in the past", first > LF && first < NOW, show(first))
  check("days", "that slot is <= 3 days after the old fire", first - LF > 0 && first - LF <= 3 * 86400000, (first - LF) + "ms")
  check("days", "first slot after the fire is 22 Oct 03:00", first === at(2026, 10, 22, 3, 0), show(first))
  const second = due("days:3@03:00", created, first, NOW)
  check("days", "next fire jumps another 3 days", second === at(2026, 10, 25, 3, 0), show(second))
  const fresh = at(2026, 10, 28, 10, 0)
  check("days", "anchor 28 Oct 03:00 -> 31 Oct 03:00", due("days:3@03:00", fresh, 0, fresh) === at(2026, 10, 31, 3, 0), show(due("days:3@03:00", fresh, 0, fresh)))
  const noAnchor = due("days:3@03:00", 0, 0, NOW)
  check("days", "no createdAt -> finite and deterministic", Number.isFinite(noAnchor) && noAnchor === due("days:3@03:00", 0, 0, NOW) && noAnchor > NOW, show(noAnchor))
}

/* --------------------------------------------------------- weekly (single) */
{
  const s = spec("weekly:mon@09:00")
  check("weekly", "single: dow1 h9 m0", s.kind === "weekly" && s.dow === 1 && s.h === 9 && s.m === 0, JSON.stringify(s))
  check("weekly", "single: dows is [dow]", sameList(s.dows, [1]), JSON.stringify(s.dows))
  const s2 = spec("weekly:wed@18:30")
  check("weekly", "single: dow3 h18 m30", s2.kind === "weekly" && s2.dow === 3 && s2.h === 18 && s2.m === 30, JSON.stringify(s2))
  rejects("weekly", "weekly:xyz@09:00")
  rejects("weekly", "weekly:mon")
  rejects("weekly", "weekly:@09:00")
  rejects("weekly", "weekly:mon@9")
  const NOW = at(2026, 10, 28, 10, 0)
  check("weekly", "single from Wed -> next Monday", due("weekly:mon@09:00", NOW, 0, NOW) === at(2026, 11, 2, 9, 0), show(due("weekly:mon@09:00", NOW, 0, NOW)))
  const caught = due("weekly:wed@09:00", at(2026, 10, 1, 8, 0), at(2026, 10, 21, 9, 0), NOW)
  check("weekly", "single catch-up -> one slot only", caught === at(2026, 10, 28, 9, 0), show(caught))
}
/* ---------------------------------------------------------- weekly (multi) */
{
  const s = spec("weekly:mon,wed,fri@09:00")
  check("weekly", "multi: dow is first day (1)", s.kind === "weekly" && s.dow === 1, JSON.stringify(s))
  check("weekly", "multi: dows [1,3,5]", sameList(s.dows, [1, 3, 5]), JSON.stringify(s.dows))
  const s2 = spec("weekly:fri,mon@09:00")
  check("weekly", "multi: order as written, dow 5", s2.dow === 5 && sameList(s2.dows, [5, 1]), JSON.stringify(s2))
  const s3 = spec("weekly:mon,MON,wed@09:00")
  check("weekly", "multi: duplicates deduped", s3.dow === 1 && sameList(s3.dows, [1, 3]), JSON.stringify(s3.dows))
  rejects("weekly", "weekly:mon,tue,wed,thu,fri,sat,sun,mon@09:00")
  rejects("weekly", "weekly:funday@09:00")
  rejects("weekly", "weekly:,wed@09:00")
  const TUE = at(2026, 10, 27, 10, 0)
  check("weekly", "fixture Tuesday", new Date(TUE).getDay() === 2, new Date(TUE).toString())
  const nextFromTue = due("weekly:mon,wed,fri@09:00", TUE, 0, TUE)
  check("weekly", "multi from Tue -> Wednesday", nextFromTue === at(2026, 10, 28, 9, 0) && new Date(nextFromTue).getDay() === 3, show(nextFromTue))
  const afterWed = due("weekly:mon,wed,fri@09:00", TUE, nextFromTue, at(2026, 10, 28, 10, 0))
  check("weekly", "multi Wed -> Friday", afterWed === at(2026, 10, 30, 9, 0) && new Date(afterWed).getDay() === 5, show(afterWed))
  const caught = due("weekly:mon,wed,fri@09:00", at(2026, 10, 1, 8, 0), at(2026, 10, 23, 9, 0), at(2026, 10, 28, 10, 0))
  check("weekly", "multi catch-up -> one slot only", caught === at(2026, 10, 26, 9, 0), show(caught))
}

/* --------------------------------------------------------------- monthly */
{
  const s = spec("monthly:1@09:00")
  check("monthly", "spec kind + n1 h9 m0", s.kind === "monthly" && s.n === 1 && s.h === 9 && s.m === 0, JSON.stringify(s))
  const s2 = spec("monthly:31@03:00")
  check("monthly", "n31 h3 m0", s2.kind === "monthly" && s2.n === 31 && s2.h === 3 && s2.m === 0, JSON.stringify(s2))
  rejects("monthly", "monthly:0@09:00")
  rejects("monthly", "monthly:32@09:00")
  rejects("monthly", "monthly:1")
  const NOW = at(2026, 10, 28, 10, 0)
  check("monthly", "n1 -> 1 Nov", due("monthly:1@09:00", NOW, 0, NOW) === at(2026, 11, 1, 9, 0), show(due("monthly:1@09:00", NOW, 0, NOW)))
  const feb = due("monthly:31@03:00", at(2026, 1, 2, 0, 0), at(2026, 1, 31, 3, 0), at(2026, 2, 5, 0, 0))
  check("monthly", "31 clamps to 2026-02-28", feb === at(2026, 2, 28, 3, 0), show(feb))
  const apr = due("monthly:31@03:00", at(2026, 3, 1, 0, 0), at(2026, 3, 31, 3, 0), at(2026, 4, 2, 0, 0))
  check("monthly", "31 clamps to April 30", apr === at(2026, 4, 30, 3, 0), show(apr))
  let neverNull = true
  for (let i = 0; i < 24; i++) {
    const ref = new Date(2026, i % 12, 1 + (i % 27), 3, 0).getTime()
    const got = computeDue(spec("monthly:31@03:00"), at(2026, 1, 2, 0, 0), ref, ref)
    if (!Number.isFinite(got) || got <= ref) neverNull = false
  }
  check("monthly", "never returns null across 24 months", neverNull)
  const caught = due("monthly:25@09:00", at(2026, 6, 1, 0, 0), at(2026, 9, 25, 9, 0), NOW)
  check("monthly", "catch-up -> one slot only", caught === at(2026, 10, 25, 9, 0), show(caught))
}

/* ------------------------------------------------- all kinds: one-fire rule */
{
  const kinds = ["daily:03:00", "weekly:mon@09:00", "weekly:mon,wed,fri@09:00", "days:3@03:00", "hourly:15", "monthly:25@09:00"]
  const NOW = at(2026, 10, 28, 10, 0)
  const created = at(2026, 1, 2, 0, 0)
  for (const when of kinds) {
    const s = spec(when)
    const backdated = new Date(NOW - 9 * 86400000).getTime()
    const first = computeDue(s, created, backdated, NOW)
    const second = computeDue(s, created, first, NOW)
    check(String(s.kind), "catch-up-once invariant for " + when, Number.isFinite(first) && first > backdated && Number.isFinite(second) && second > first, "first " + show(first) + " second " + show(second))
  }
  check("every", "unknown kind -> null", computeDue({ kind: "nope" }, NOW, 0, NOW) === null)
}

/* ------------------------------------------------------------------ report */
if (fail === 0) {
  console.log("ALL FORMATS PASS")
} else {
  console.log("FORMATS FAILED: " + fail + " of " + (pass + fail) + " assertions")
}