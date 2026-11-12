"""Run every suite in order against the server on port 8900 and print one summary.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/run_all.py                        (in another)
"""
import re, subprocess, sys

SUITES = ["smoke", "ui", "closeout", "milestone1", "k1_complete", "real_labels", "validation", "k1_audit", "longevity", "live_mode"]
total, failed = 0, []
for s in SUITES:
    out = subprocess.run([sys.executable, f"tests/{s}.py"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    m = re.search(r"(\d+) passed, (\d+) failed", out.stdout)
    p, f = (int(m.group(1)), int(m.group(2))) if m else (0, 1)
    total += p
    status = "ok" if out.returncode == 0 and m and f == 0 else "FAILED"
    print(f"  {s:12s} {p:4d} passed  {f:3d} failed   {status}")
    if status != "ok":
        failed.append(s)
        lines = (out.stdout + out.stderr).splitlines()
        hits = [ln for ln in lines if "FAIL" in ln or "Error" in ln]
        # a process that died mid-run prints no FAIL line: show how it ended instead
        print("\n".join("     " + ln for ln in (hits or [f"exit code {out.returncode}; last lines:"] + lines[-6:]))[-2000:])
print(f"\n  {total} checks passed" + (f"; failing suites: {', '.join(failed)}" if failed else "; all suites green"))
sys.exit(1 if failed else 0)
