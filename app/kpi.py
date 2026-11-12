"""The client's six milestones, measured from what Solara already records: the audit trail, each
step's time, the portal statuses the co-pilot read, the backups. A KPI run needs no stopwatch
sheet; Reports shows this page and the monthly workbook carries it.

Owner time is worked out from the people's own actions on a customer: two actions less than
GAP apart are one sitting, a longer gap is a wait (an OTP, the customer, the field) and counts
as TOUCH. shortcut: an OTP read out inside a sitting is counted as owner time (it is under GAP);
the KPI excludes it, so these figures are slightly high, never flattering.
"""
from datetime import datetime
from . import db, closeout, tracker, upkeep

PEOPLE = ("viewer", "operator", "supervisor")
GAP, TOUCH = 240, 30
# what each problem case leaves in the audit trail when Solara handles it (K4)
CASES = [("wrong OTP", "Co-pilot: wrong OTP"), ("OTP not received, resent", "Co-pilot: OTP resend"),
         ("portal session timed out", "Co-pilot: portal session ended"), ("internet cut mid-form", "Co-pilot: internet off"),
         ("file over the portal's limit", "File made smaller for the portal"), ("repeated serial number", "Serial repeat refused"),
         ("photo without GPS", "Photo without GPS refused"), ("dealer panels not transferred", "DCR: waiting for the dealer")]


def owner_seconds(cid, since=None, until=None):
    ts = [datetime.fromisoformat(r["ts"]) for r in db.q(
        "SELECT ts FROM audit WHERE target=? AND role IN (?,?,?) ORDER BY ts", (cid, *PEOPLE))
        if (not since or r["ts"] >= since) and (not until or r["ts"] <= until)]
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    return int(sum(g if g <= GAP else TOUCH for g in gaps) + (TOUCH if ts else 0))


def count(action, cid=None, like=False):
    op = "LIKE" if like else "="
    if cid:
        return db.one(f"SELECT COUNT(*) k FROM audit WHERE action {op} ? AND target=?", (action, cid))["k"]
    return db.one(f"SELECT COUNT(*) k FROM audit WHERE action {op} ?", (action,))["k"]


def customers():
    out = []
    for r in db.q("SELECT id, name FROM customers WHERE workflow='rooftop_registration' ORDER BY id"):
        cid = r["id"]
        _, d = closeout.data(cid)
        k1_end = d.get("agreement_approved_at") or d.get("agreement_uploaded_at")
        post = d.get("field_at"), d.get("msedcl_uploaded_at")
        out.append({"id": cid, "name": r["name"],
                    "k1_seconds": owner_seconds(cid, until=k1_end) if k1_end else None,
                    "k2_seconds": owner_seconds(cid, *post) if all(post) else None,
                    "total_seconds": owner_seconds(cid), "done": bool(post[1]),
                    "left_fields": count("Co-pilot left fields", cid), "refiled": count("Reopened:%", cid, like=True)})
    return out


def summary():
    rows = customers()
    k1 = [r["k1_seconds"] for r in rows if r["k1_seconds"] is not None]
    k2 = [r["k2_seconds"] for r in rows if r["k2_seconds"] is not None]
    full = [r["total_seconds"] for r in rows if r["done"]]
    board = tracker.board()
    seen = [b for b in board if b["portal_status"]]
    match = [b for b in seen if not b["problems"]]
    avg = lambda xs: round(sum(xs) / len(xs) / 60, 1) if xs else None
    last = upkeep.latest()
    drill = db.one("SELECT ts, action, detail FROM audit WHERE action LIKE 'Restore drill%' ORDER BY id DESC")
    ms = [
        {"key": "K1", "name": "Documents to the customer's approved agreement", "target": "3 customers, each 5 min or less",
         "value": f"{sum(x <= 300 for x in k1)} of {len(k1)} within 5 min" + (f", average {avg(k1)} min" if k1 else ""),
         "met": len(k1) >= 3 and sum(x <= 300 for x in k1) >= 3},
        {"key": "K2", "name": "Post-installation paperwork closed", "target": "3 customers, each 5 min or less; 0 files rejected",
         "value": f"{sum(x <= 300 for x in k2)} of {len(k2)} within 5 min; {sum(r['refiled'] for r in rows)} re-filed",
         "met": len(k2) >= 3 and sum(x <= 300 for x in k2) >= 3},
        {"key": "K3", "name": "Stage on screen matches the portal", "target": "10 of 10 live customers",
         "value": f"{len(match)} of {len(seen)} read from the portal agree", "met": len(seen) >= 10 and len(match) == len(seen)},
        {"key": "K4", "name": "Problem cases handled", "target": "8 of 8",
         "value": f"{sum(1 for _, a in CASES if count(a))} of 8 seen and handled", "met": all(count(a) for _, a in CASES),
         "cases": [{"case": n, "times": count(a)} for n, a in CASES]},
        {"key": "K5", "name": "Live customers order to MSEDCL", "target": "10 customers, average 15 min or less, 0 wrong submissions",
         "value": f"{len(full)} through MSEDCL" + (f", average {avg(full)} min" if full else "") + f", {sum(r['refiled'] for r in rows)} re-filed",
         "met": len(full) >= 10 and (avg(full) or 99) <= 15 and not sum(r["refiled"] for r in rows)},
        {"key": "K6", "name": "Runs and looks after itself", "target": "daily backup, restore drill passed, retention set",
         "value": (f"last backup {datetime.fromtimestamp(last.stat().st_mtime):%d %b %H:%M}" if last else "no backup yet") +
                  (f"; restore drill {drill['action'][14:].lower()} on {drill['ts'][:10]}" if drill else "; no restore drill yet"),
         "met": bool(last and drill and drill["action"] == "Restore drill PASSED")},
    ]
    return {"milestones": ms, "customers": rows}
