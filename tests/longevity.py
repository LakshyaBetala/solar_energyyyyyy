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
print("\n  reset:", c.post("/api/demo/reset").json()["runnable"])
print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
