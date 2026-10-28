# U1 - scheduler recurring formats

DONE. `node scripts/test_scheduler_formats.mjs` exits 0 and ends `ALL FORMATS PASS` (83 PASS lines + the final ALL FORMATS PASS, re-run after every edit).
Backup left in place: `~\.config\opencode\plugins\scheduler\index.ts.bak-20261028-104050`
(39749 bytes, matched the original before the first edit).

Changed: `index.ts` header format list + `USAGE`; `parseWhen` adds days/hourly/monthly and a
comma-list weekly (days deduped, order as written, 8+ rejected, single day still yields `dow`;
once/every/daily/weekly-single shapes byte-identical); `computeDue` adds days (createdAt anchor,
k*N in one step), hourly (minute fixed, <= +60m), monthly (clamp min(N,monthLen), re-clamp next
month, never null), weekly (scans <=8 days over `dows`, fallback `[dow]`). Untouched: tick, fire,
logging, error ownership, setup(). `tools/schedule.py`: `ACCEPTED` only. New test imports the REAL
plugin by dynamic import of index.ts and covers >=2 valid + >=2 rejects per kind plus catch-up
maths on fixed local-time constants.

## node scripts/test_scheduler_formats.mjs (exit 0)```
PASS once spec kind + atMs
PASS once midnight atMs
PASS once rejects once:2026-13-01T09:00
PASS once rejects once:2026-02-30T09:00
PASS once rejects once:tomorrow
PASS once computeDue ignores refs
PASS every 30m -> 1800000ms
PASS every 2h -> 7200000ms
PASS every 3d -> 259200000ms
PASS every rejects every:0m
PASS every rejects every:30s
PASS every rejects every:
PASS every arithmetic alignment from createdAt
PASS every next slot is createdAt + 60m
PASS every catch-up stays on the 2h grid
PASS daily 09:00 -> h9 m0
PASS daily 23:59 -> h23 m59
PASS daily rejects daily:24:00
PASS daily rejects daily:09:60
PASS daily rejects daily:9
PASS daily past slot -> tomorrow
PASS daily future slot -> today
PASS daily missed slot returns a past timestamp
PASS daily after that fire -> next future slot
PASS hourly 30 -> m30
PASS hourly 05 (2 digits) -> m5
PASS hourly 5 (1 digit) -> m5
PASS hourly rejects hourly:60
PASS hourly rejects hourly:
PASS hourly rejects hourly:9:30
PASS hourly next slot <= ref + 60m
PASS hourly minute is always 30
PASS hourly past :30 -> next hour :30
PASS hourly catch-up -> exactly one hour later
PASS days spec kind + n3 h3 m0
PASS days n1 h23 m30
PASS days rejects days:0@03:00
PASS days rejects days:3@25:00
PASS days rejects days:3
PASS days rejects days:3@03:00 extra
PASS days 7-day gap -> one slot, in the past
PASS days that slot is <= 3 days after the old fire
PASS days first slot after the fire is 22 Oct 03:00
PASS days next fire jumps another 3 days
PASS days anchor 28 Oct 03:00 -> 31 Oct 03:00
PASS days no createdAt -> finite and deterministic
PASS weekly single: dow1 h9 m0
PASS weekly single: dows is [dow]
PASS weekly single: dow3 h18 m30
PASS weekly rejects weekly:xyz@09:00
PASS weekly rejects weekly:mon
PASS weekly rejects weekly:@09:00
PASS weekly rejects weekly:mon@9
PASS weekly single from Wed -> next Monday
PASS weekly single catch-up -> one slot only
PASS weekly multi: dow is first day (1)
PASS weekly multi: dows [1,3,5]
PASS weekly multi: order as written, dow 5
PASS weekly multi: duplicates deduped
PASS weekly rejects weekly:mon,tue,wed,thu,fri,sat,sun,mon@09:00
PASS weekly rejects weekly:funday@09:00
PASS weekly rejects weekly:,wed@09:00
PASS weekly fixture Tuesday
PASS weekly multi from Tue -> Wednesday
PASS weekly multi Wed -> Friday
PASS weekly multi catch-up -> one slot only
PASS monthly spec kind + n1 h9 m0
PASS monthly n31 h3 m0
PASS monthly rejects monthly:0@09:00
PASS monthly rejects monthly:32@09:00
PASS monthly rejects monthly:1
PASS monthly n1 -> 1 Nov
PASS monthly 31 clamps to 2026-02-28
PASS monthly 31 clamps to April 30
PASS monthly never returns null across 24 months
PASS monthly catch-up -> one slot only
PASS daily catch-up-once invariant for daily:03:00
PASS weekly catch-up-once invariant for weekly:mon@09:00
PASS weekly catch-up-once invariant for weekly:mon,wed,fri@09:00
PASS days catch-up-once invariant for days:3@03:00
PASS hourly catch-up-once invariant for hourly:15
PASS monthly catch-up-once invariant for monthly:25@09:00
PASS every unknown kind -> null
ALL FORMATS PASS
```

## python tools\schedule.py --help (exit 0)
```
usage: schedule.py [-h] {add,list,rm,pause,resume} ...

Agent-facing scheduler client
```

`schedule.py add --help` prints the full ACCEPTED line (once | every | daily | hourly:MM |
days:N@HH:MM | weekly:mon@HH:MM or weekly:mon,wed,fri@HH:MM | monthly:N@HH:MM).

Decisions where the spec was silent: weekly keeps written order (dedupe first, so `dow` is the
first day as typed, `dows` always present); days uses key `n`, capped 365; monthly cannot loop
forever or return null (fallback is a real future stamp); hourly accepts 1-2 digits. Overlap:
wave unit u3 had already written overlapping versions of these files - I kept the shared
structure, corrected spec field names to the brief (`days.n`, `monthly.n`), restored written-order
weekdays, and replaced the test with the required real-import version. No other files touched.