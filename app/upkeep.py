"""Looking after Solara without anyone remembering to: the daily backup, a copy of it somewhere
else, old backups pruned, the restore drill, and the document-retention period.

Runs once at startup and then every hour in the server (main.startup); every action is in the
audit trail. Settings (solara.env or the environment):
  SOLARA_BACKUP_COPY=D:\\Solara backups   a second folder (USB disk, OneDrive) that gets each backup too
  SOLARA_KEEP_BACKUPS=14                  how many daily backups to keep in each folder
  SOLARA_KEEP_MONTHS=0                    months after the subsidy is disbursed before a customer's
                                          documents are deleted (0 = never). The record, the audit
                                          trail and the receipts stay.
"""
import os, shutil, sqlite3, tempfile, threading, time, zipfile
from datetime import datetime, timedelta
from pathlib import Path
from . import db, backup, vault
from .config import DOCS

DAY = 22 * 3600  # "daily" with slack, so a backup made a little later each day still counts


def setting(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def latest():
    zips = sorted(backup.BACKUPS.glob("solara_*.zip"), key=lambda p: p.stat().st_mtime) if backup.BACKUPS.exists() else []
    return zips[-1] if zips else None


def prune(folder, keep):
    zips = sorted(Path(folder).glob("solara_*.zip"), key=lambda p: p.stat().st_mtime)
    for p in zips[:-keep] if keep > 0 else []:
        p.unlink(missing_ok=True)


def daily_backup(now=None):
    """A backup when the last one is a day old; copied to SOLARA_BACKUP_COPY; old ones pruned."""
    now = now or time.time()
    last = latest()
    if last and now - last.stat().st_mtime < DAY:
        return None
    p = backup.create()
    keep = setting("SOLARA_KEEP_BACKUPS", 14)
    prune(backup.BACKUPS, keep)
    copy = os.environ.get("SOLARA_BACKUP_COPY", "").strip()
    where = ""
    if copy:
        try:
            Path(copy).mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, Path(copy) / p.name)
            prune(copy, keep)
            where = f", copied to {copy}"
        except OSError as ex:
            where = f", NOT copied to {copy}: {ex.strerror or ex}"
    db.audit("system", "system", "Daily backup", "", f"{p.name} ({p.stat().st_size // 1024} KB){where}")
    return p


def verify(zip_path):
    """The restore drill: open the backup somewhere else and prove it would work.
    The database must pass SQLite's integrity check, and one document must open with this vault key."""
    out = {"file": Path(zip_path).name, "ok": False}
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
        con = sqlite3.connect(Path(tmp) / "solara.db")
        try:
            out["integrity"] = con.execute("PRAGMA integrity_check").fetchone()[0]
            out["customers"] = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
            row = con.execute("SELECT path FROM documents ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            con.close()
        out["document"] = "none in this backup"
        if row:
            rel = Path(row[0])
            parts = rel.parts
            # stored paths are absolute on the old computer; in the archive they sit under documents/
            inner = Path(tmp, *parts[parts.index("documents"):]) if "documents" in parts else None
            try:
                vault.read(inner)
                out["document"] = "opens with this computer's vault key"
            except Exception as ex:
                out["document"] = f"does NOT open with this vault key ({type(ex).__name__})"
                return out
    out["ok"] = out["integrity"] == "ok"
    return out


def disbursed_at(cid):
    """When the portal showed the subsidy as disbursed (the co-pilot read it), if it did."""
    r = db.one("SELECT seen_at FROM portal_status WHERE customer_id=? AND portal='pmsg' AND stage='subsidy_disbursal:done'", (cid,))
    return r["seen_at"] if r else None


def retention(now=None):
    """Delete the documents of customers whose subsidy was disbursed more than N months ago."""
    months = setting("SOLARA_KEEP_MONTHS", 0)
    if months <= 0:
        return []
    cutoff = ((now or datetime.now()) - timedelta(days=30 * months)).isoformat(timespec="seconds")
    gone = []
    for r in db.q("SELECT id FROM customers WHERE stage='disbursed'"):
        at = disbursed_at(r["id"])
        docs = db.q("SELECT id, path FROM documents WHERE customer_id=?", (r["id"],))
        if not at or at > cutoff or not docs:
            continue
        for d in docs:
            Path(d["path"]).unlink(missing_ok=True)
        db.ex("DELETE FROM documents WHERE customer_id=?", (r["id"],))
        shutil.rmtree(DOCS / r["id"], ignore_errors=True)
        db.audit("system", "system", "Retention: documents deleted", r["id"],
                 f"{len(docs)} document(s); subsidy disbursed {at[:10]}, kept {months} month(s)")
        gone.append(r["id"])
    return gone


def run_once():
    out = {}
    for name, job in (("backup", daily_backup), ("retention", retention)):
        try:
            out[name] = job()
        except Exception as ex:  # one failing job must not stop the other, and is never silent
            db.audit("system", "system", f"Upkeep failed: {name}", "", f"{type(ex).__name__}: {ex}"[:300])
            out[name] = None
    return out


def start():
    """Hourly, in a background thread of the server."""
    def loop():
        while True:
            run_once()
            time.sleep(3600)
    threading.Thread(target=loop, name="solara-upkeep", daemon=True).start()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "verify":
        r = verify(sys.argv[2])
        print(("RESTORE DRILL PASSED" if r["ok"] else "RESTORE DRILL FAILED") + f": {r}")
        sys.exit(0 if r["ok"] else 1)
    print(run_once())
