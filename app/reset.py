"""Put the demo back to its opening state. Safe to run between rehearsals.

  python -m app.reset

Customer and number state is restored from the seed in db.py, so there is one source of
truth for what the opening state looks like. Documents and extractions are kept; sessions
are kept so whoever is presenting stays signed in.
"""
import shutil
from datetime import datetime, timedelta
from . import db
from .config import SHOTS, EXPORTS, DOCS


def reset(wipe_files=True):
    for t in ("runs", "run_steps", "run_events", "holds", "screenshots",
              "portal_applications", "portal_requests", "portal_sessions", "sms",
              "closeout", "sign_requests", "approvals", "msedcl_uploads", "pmsg_vendor",
              "filings", "serials", "field_links"):
        db.ex(f"DELETE FROM {t}")
    # the company signature is one-time setup and survives a reset; customers' do not
    db.ex("DELETE FROM signatures WHERE role='consumer'")
    db.ex("DELETE FROM documents WHERE kind LIKE 'co_%' OR kind LIKE 'rc_%'")
    db.ex("DELETE FROM documents WHERE kind IN ('dcr_cert','invoice','serial_sheet','serial_label',"
          "'preinstall','install_photo')")
    db.seed_closeout()
    from . import closeout
    closeout.demo_assets()
    # customers added during a rehearsal go; seeded ones come back exactly as seeded
    ids = [c[0] for c in db.CUSTOMERS]
    nos = [p[0] for p in db.PORTAL_CONSUMERS]
    for t in ("documents", "extractions"):
        db.ex(f"DELETE FROM {t} WHERE customer_id NOT IN ({','.join('?' * len(ids))})", ids)
    db.ex(f"DELETE FROM customers WHERE id NOT IN ({','.join('?' * len(ids))})", ids)
    db.ex(f"DELETE FROM portal_consumers WHERE consumer_no NOT IN ({','.join('?' * len(nos))})", nos)
    for d in DOCS.iterdir():
        if d.is_dir() and d.name not in ids and d.name != "vendor":
            shutil.rmtree(d, ignore_errors=True)
    for c in db.CUSTOMERS:
        db.ex("""INSERT OR REPLACE INTO customers(id,name,aadhaar_name,place,consumer_no,kw,category,
                 stage,application_no,subsidy,last_activity,blocked_note,pin,address,bank,workflow)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", c)
    for msisdn, cid, days, otps, st in db.NUMBERS:
        db.ex("""UPDATE numbers SET customer_id=?,otp_count=?,status=?,expires_at=?
                 WHERE msisdn=?""",
              (cid, otps, st, (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds"),
               msisdn))
    db.ex("DELETE FROM audit")
    for actor, role, action, target, detail in db.SEED_AUDIT:
        db.audit(actor, role, action, target, detail)
    if wipe_files:
        for d in (SHOTS, EXPORTS):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
    return {"runnable": [c[0] for c in db.CUSTOMERS if c[15] and not c[8]], "runs_cleared": True}


if __name__ == "__main__":
    db.seed()
    print("demo reset:", reset())
