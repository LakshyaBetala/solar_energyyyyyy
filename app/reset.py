"""Put the demo back to its opening state. Safe to run between rehearsals.

  python -m app.reset

Customer and number state is restored from the seed in db.py, so there is one source of
truth for what the opening state looks like. Documents and extractions are kept; sessions
are kept so whoever is presenting stays signed in.
"""
import shutil
from datetime import datetime, timedelta
from . import db
from .config import SHOTS, EXPORTS


def reset(wipe_files=True):
    for t in ("runs", "run_steps", "run_events", "holds", "screenshots",
              "portal_applications", "portal_requests", "portal_sessions", "sms",
              "closeout", "sign_requests", "approvals", "msedcl_uploads"):
        db.ex(f"DELETE FROM {t}")
    # the company signature is one-time setup and survives a reset; customers' do not
    db.ex("DELETE FROM signatures WHERE role='consumer'")
    db.ex("DELETE FROM documents WHERE kind LIKE 'co_%'")
    db.seed_closeout()
    from . import closeout
    closeout.demo_assets()
    for c in db.CUSTOMERS:
        # seed tuple: 7 stage, 8 reference, 10 last activity, 11 blocked note, 15 workflow
        db.ex("""UPDATE customers SET stage=?,application_no=?,last_activity=?,blocked_note=?,
                 workflow=?,discom_ref=NULL WHERE id=?""", (c[7], c[8], c[10], c[11], c[15], c[0]))
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
