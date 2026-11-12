"""Guards against slow breakage: old databases upgrade, the health check sees problems, the
co-pilot's unfilled fields reach the health check, and the dependency versions are pinned.

  python tests/longevity.py        (server on 8900 for the API part)
"""
import re, sqlite3, sys, tempfile
from pathlib import Path
import httpx
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db  # noqa: E402

BASE, PASS, FAIL = "http://127.0.0.1:8900", [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def cols(c):
    return {r[1] for r in c.execute("PRAGMA table_info(customers)")}


# ---- migrations ----
print("\n  -- database upgrades")
old = sqlite3.connect(Path(tempfile.mkdtemp()) / "old.db")
old.execute("CREATE TABLE customers(id TEXT PRIMARY KEY, name TEXT)")  # a database from before
old.execute("INSERT INTO customers VALUES('SS-1','Kept Customer')")
old.commit()
old.executescript(db.SCHEMA)
db.migrate(old)
check("an old database gains the missing columns", {"workflow", "discom_ref"} <= cols(old))
check("its data is kept", old.execute("SELECT name FROM customers").fetchone()[0] == "Kept Customer")
check("its version is recorded", old.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS))
db.migrate(old)
check("upgrading twice is harmless", old.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS))
pre = sqlite3.connect(Path(tempfile.mkdtemp()) / "pre.db")
pre.executescript(db.SCHEMA)  # columns already there, version 0: an install from before versioning
db.migrate(pre)
check("a database that already has the columns upgrades without error",
      pre.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS))

# ---- pinned dependencies ----
print("\n  -- dependencies")
reqs = [ln.strip() for ln in Path("requirements.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
loose = [r for r in reqs if not re.match(r"^[A-Za-z0-9_.\-]+==[0-9][\w.]*$", r)]
check("every dependency is pinned to one exact version", not loose, ", ".join(loose))

# ---- health and drift ----
print("\n  -- health check")
c = httpx.Client(base_url=BASE, timeout=60)
c.post("/api/login", json={"username": "r.deshmukh", "password": "demo"}).raise_for_status()
h = c.get("/api/health").json()
st = {x["key"]: x for x in h["checks"]}
check("health covers database, key, backups, disk, portals, AI",
      set(st) == {"database", "key", "backups", "disk", "portals", "ai"}, ", ".join(st))
check("the database and key are healthy", st["database"]["state"] == "ok" and st["key"]["state"] == "ok",
      st["database"]["text"] + " · " + st["key"]["text"])
key = c.post("/api/copilot/key").json()["key"]
r = httpx.post(BASE + "/api/copilot/report", headers={"X-Solara-Key": key},
               json={"customer_id": "SS-2045", "portal": "pmsuryaghar.gov.in", "attached": 3,
                     "page": "pmsuryaghar.gov.in/consumer/apply", "left": ["Name of Scheme", "Roof Type"]})
check("the co-pilot's report of unfilled fields is accepted", r.status_code == 200)
p = {x["key"]: x for x in c.get("/api/health").json()["checks"]}["portals"]
check("health shows the drift: which page and which fields",
      p["state"] == "warn" and "consumer/apply" in p["text"] and "Roof Type" in p["text"], p["text"])
c.post("/api/backup")
b = {x["key"]: x for x in c.get("/api/health").json()["checks"]}["backups"]
check("a fresh backup turns the backup check green", b["state"] == "ok", b["text"])

# ---- upkeep: daily backup, pruning, retention (K6) ----
print("\n  -- upkeep")
import os, time  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from app import upkeep, backup as _backup, closeout as _co  # noqa: E402
same_day = upkeep.daily_backup()               # the backup just made above is today's
for z in _backup.BACKUPS.glob("solara_*.zip"):  # as if the last one were two days old
    os.utime(z, (time.time() - 2 * 86400,) * 2)
fresh = upkeep.daily_backup()
check("a daily backup is made when the last is a day old, and not twice the same day",
      same_day is None and fresh is not None and time.time() - fresh.stat().st_mtime < 120)
check("...and it is in the audit trail", bool(db.one("SELECT 1 FROM audit WHERE action='Daily backup'")))
fake = []
for i in range(4):  # older backups, oldest first
    f = _backup.BACKUPS / f"solara_2020010{i + 1}_000000.zip"
    f.write_bytes(b"x")
    os.utime(f, (time.time() - 86400 * (10 - i),) * 2)
    fake.append(f)
upkeep.prune(_backup.BACKUPS, 2)
check("only the newest backups are kept", not fake[0].exists() and upkeep.latest() is not None and
      len(list(_backup.BACKUPS.glob("solara_*.zip"))) == 2)
v = upkeep.verify(upkeep.latest())
check("the restore drill passes on the newest backup", v["ok"], str(v))
# retention: a disbursed customer's documents go after the set months; nobody else's
cid = "SS-9901"  # a customer of this check only; the demo reset removes it
db.ex("INSERT OR REPLACE INTO customers(id,name,category,stage,workflow,subsidy) VALUES(?,?,?,?,?,0)",
      (cid, "Retention Check", "Residential", "disbursed", "rooftop_registration"))
doc = _co.DOCS / cid / "bill.pdf"
doc.parent.mkdir(parents=True, exist_ok=True)
_co.vault.write(doc, b"%PDF-1.4 test")
db.ex("INSERT INTO documents(customer_id,kind,filename,path,bytes,uploaded_at) VALUES(?,?,?,?,?,?)",
      (cid, "bill", "bill.pdf", str(doc), 13, db.now()))
receipt = _co.DOCS / cid / "receipts" / "sfr.pdf"
receipt.parent.mkdir(parents=True, exist_ok=True)
_co.vault.write(receipt, b"%PDF-1.4 receipt")
db.ex("INSERT INTO documents(customer_id,kind,filename,path,bytes,uploaded_at) VALUES(?,?,?,?,?,?)",
      (cid, "rc_sfr", "sfr.pdf", str(receipt), 16, db.now()))
old = (datetime.now() - timedelta(days=400)).isoformat(timespec="seconds")
db.ex("""INSERT INTO portal_status(customer_id,portal,ref,status,stage,seen_at,seen_by) VALUES(?,?,?,?,?,?,?)
         ON CONFLICT(customer_id,portal) DO UPDATE SET stage=excluded.stage, seen_at=excluded.seen_at""",
      (cid, "pmsg", "NP-TEST-000001", "Subsidy Disbursal (Disbursed)", "subsidy_disbursal:done", old, "test"))
others = db.one("SELECT COUNT(*) k FROM documents WHERE customer_id<>?", (cid,))["k"]
os.environ.pop("SOLARA_KEEP_MONTHS", None)
check("retention is off unless set", upkeep.retention() == [])
os.environ["SOLARA_KEEP_MONTHS"] = "24"
check("24 months: a subsidy disbursed 13 months ago keeps its documents", upkeep.retention() == [])
os.environ["SOLARA_KEEP_MONTHS"] = "12"
gone = upkeep.retention()
os.environ.pop("SOLARA_KEEP_MONTHS", None)
check("12 months: that customer's documents are deleted, the record and others' documents stay",
      gone == [cid] and not db.q("SELECT 1 FROM documents WHERE customer_id=? AND kind='bill'", (cid,))
      and db.one("SELECT 1 FROM customers WHERE id=?", (cid,)) is not None
      and db.one("SELECT COUNT(*) k FROM documents WHERE customer_id<>?", (cid,))["k"] == others and not doc.exists())
check("...the portal receipts stay", receipt.exists() and db.one("SELECT 1 FROM documents WHERE customer_id=? AND kind='rc_sfr'", (cid,)))
check("...and the deletion is in the audit trail", bool(db.one("SELECT 1 FROM audit WHERE action='Retention: documents deleted' AND target=?", (cid,))))
print("\n  reset:", c.post("/api/demo/reset").json()["runnable"])
print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
