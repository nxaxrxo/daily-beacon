"""Detached, windowless runner: python _run_detached.py <log> <done> -- <cmd...>"""
import subprocess, sys, os
DETACHED = 0x00000008
CREATE_NO_WINDOW = 0x08000000
log_path, done_path = sys.argv[1], sys.argv[2]
cmd = sys.argv[sys.argv.index("--") + 1:]
with open(log_path, "wb") as lf:
    p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT,
                         creationflags=DETACHED | CREATE_NO_WINDOW, close_fds=True)
with open(done_path, "w", encoding="ascii") as f:
    f.write("pid=%d\n" % p.pid)
print("launched pid", p.pid)
