"""Put the demo back to its opening state. Safe to run between rehearsals.

  python -m app.reset
"""
import shutil
from . import db
from .config import SHOTS, EXPORTS

KEEP_FILED = {"SS-2041": ("PMSG/MH/2026/118842", "disbursed", "4 Oct"),
              "SS-2042": ("PMSG/MH/2026/121907", "install", "22 Oct"),
              "SS-2043": ("PMSG/MH/2026/122416", "feasible", "23 Oct"),
              "SS-2046": ("PMSG/MH/2026/119533", "netmeter", "21 Oct"),
              "SS-2048": ("PMSG/MH/2026/120771", "claim", "24 Oct")}
UNFILED = {"SS-2044": ("docs", "25 Oct"), "SS-2045": ("docs", "26 Oct"),
           "SS-2047": ("register", "26 Oct")}


def reset(wipe_files=True):
    for t in ("runs", "run_steps", "run_events", "holds", "screenshots",
              "portal_applications", "portal_sessions", "sms"):
        db.ex(f"DELETE FROM {t}")
    for cid, (app_no, stage, last) in KEEP_FILED.items():
        db.ex("UPDATE customers SET application_no=?,stage=?,last_activity=? WHERE id=?",
              (app_no, stage, last, cid))
    for cid, (stage, last) in UNFILED.items():
        db.ex("UPDATE customers SET application_no=NULL,stage=?,last_activity=? WHERE id=?",
              (stage, last, cid))
    db.ex("DELETE FROM audit")
    for actor, role, action, target, detail in db.SEED_AUDIT:
        db.audit(actor, role, action, target, detail)
    if wipe_files:
        for d in (SHOTS, EXPORTS):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
    return {"customers_unfiled": list(UNFILED), "runs_cleared": True}


if __name__ == "__main__":
    db.seed()
    print("demo reset:", reset())
