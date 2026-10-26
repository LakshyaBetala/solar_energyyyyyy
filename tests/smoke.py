"""End-to-end test. Drives the real HTTP API the way an operator would, through a real
agent run against the real sandbox portal, and asserts on what ended up in the database.

Run the server first:  python -m uvicorn app.main:app --port 8900
Then:                  python tests/smoke.py
"""
import asyncio, json, sys, httpx
sys.path.insert(0, ".")
from app import db  # noqa: E402

BASE = "http://127.0.0.1:8900"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main():
    cid = "SS-2045"
    db.ex("DELETE FROM portal_applications")
    db.ex("DELETE FROM portal_sessions")
    db.ex("UPDATE customers SET application_no=NULL, stage='docs' WHERE id=?", (cid,))

    async with httpx.AsyncClient(base_url=BASE, timeout=90, follow_redirects=True) as c:
        # ---------- auth + RBAC ----------
        r = await c.post("/api/login", json={"username": "r.deshmukh", "password": "nope"})
        check("bad password rejected", r.status_code == 401, f"got {r.status_code}")

        r = await c.post("/api/login", json={"username": "a.more", "password": "demo"})
        check("viewer can sign in", r.status_code == 200 and r.json()["role"] == "viewer")
        r = await c.post("/api/runs", json={"customer_id": cid})
        check("viewer CANNOT start a run (server-side)", r.status_code == 403, r.text[:70])

        r = await c.post("/api/login", json={"username": "s.kale", "password": "demo"})
        check("operator can sign in", r.status_code == 200 and r.json()["role"] == "operator")

        r = await c.get("/api/bootstrap")
        boot = r.json()
        check("bootstrap returns data", r.status_code == 200 and len(boot["customers"]) == 8,
              f"{len(boot.get('customers', []))} customers")
        check("LLM status reported", "llm" in boot, json.dumps(boot.get("llm")))

        # ---------- extraction on the real PDFs ----------
        r = await c.post(f"/api/extract/{cid}?use_llm=false")
        ex = r.json()
        flagged = [f for f in ex["fields"] if f["status"] == "review"]
        check("extraction parsed the PDF", r.status_code == 200 and ex["chars_parsed"] > 300,
              f"{ex.get('chars_parsed')} chars, {len(ex.get('fields', []))} fields")
        check("name mismatch flagged by rules", len(flagged) == 1 and
              flagged[0]["field"] == "Consumer name (bill)",
              f"{[f['field'] for f in flagged]}")

        # ---------- the agent run ----------
        r = await c.post("/api/runs", json={"customer_id": cid, "headless": True, "speed": 4})
        check("operator started the run", r.status_code == 200, r.text[:90])
        rid = r.json()["run_id"]

        holds_seen, done, failure = [], None, None
        async with c.stream("GET", f"/api/runs/{rid}/stream") as s:
            async for line in s.aiter_lines():
                if not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                if ev["type"] == "event":
                    print(f"      {ev['ts']} [{ev['level']:<4}] {ev['message'][:88]}")
                if ev["type"] == "hold":
                    holds_seen.append(ev["kind"])
                    await resolve(c, rid, ev)
                if ev["type"] == "done":
                    done = ev
                    break
                if ev["type"] == "failed":
                    failure = ev
                    break

        check("run reached a conclusion", done is not None,
              failure["reason"] if failure else "")
        if not done:
            summarise()
            return
        check("all four human checkpoints fired in order",
              holds_seen == ["otp", "captcha", "fix", "approve"], str(holds_seen))
        check("application number came from the portal page",
              done["application_no"].startswith("PMSG/MH/"), done["application_no"])
        check("retry was needed and recorded", done["retries"] == 1, str(done["retries"]))

        # ---------- the portal really persisted it ----------
        row = db.one("SELECT * FROM portal_applications WHERE application_no=?",
                     (done["application_no"],))
        check("portal stored the application server-side", row is not None)
        check("portal stored the BILL spelling of the name",
              row and row["applicant_name"] == "VAISHALI D PAWAR", row and row["applicant_name"])

        steps = {s["key"]: s for s in
                 db.q("SELECT * FROM run_steps WHERE run_id=?", (rid,))}
        check("the correction step keeps the operator's decision after the retry",
              steps["fix"]["status"] == "done" and "s.kale" in (steps["fix"]["note"] or ""),
              f"{steps['fix']['status']}: {steps['fix']['note']}")
        check("the validation step records that it passed only after a correction",
              "retry" in (steps["validate"]["note"] or ""), steps["validate"]["note"])

        cust = db.one("SELECT * FROM customers WHERE id=?", (cid,))
        check("customer record advanced to feasibility",
              cust["stage"] == "feasible" and cust["application_no"] == done["application_no"])

        shots = db.q("SELECT * FROM screenshots WHERE run_id=?", (rid,))
        from pathlib import Path
        real = [s for s in shots if Path(s["path"]).exists() and Path(s["path"]).stat().st_size > 900]
        check("screenshots exist on disk", len(real) >= 5, f"{len(real)} PNG files")
        check("a failure screenshot was captured",
              any(s["kind"] == "fail" for s in shots))

        hd = db.q("SELECT * FROM holds WHERE run_id=?", (rid,))
        check("every hold is resolved and attributed",
              all(h["status"] == "resolved" and h["resolved_by"] for h in hd),
              str([(h["kind"], h["resolved_by"]) for h in hd]))
        appr = next((h for h in hd if h["kind"] == "approve"), None)
        check("approval was attributed to the supervisor",
              appr and appr["resolved_by"] == "r.deshmukh", appr and appr["resolved_by"])

        sms_rows = db.q("SELECT * FROM sms WHERE code IS NOT NULL")
        check("OTP was issued to the dedicated number", len(sms_rows) >= 1,
              f"{len(sms_rows)} messages")
        ev_text = " ".join(e["message"] for e in
                           db.q("SELECT message FROM run_events WHERE run_id=?", (rid,)))
        check("OTP value never written into the run log",
              not any(s["code"] and s["code"] in ev_text for s in sms_rows))

        # ---------- exports ----------
        r = await c.get("/api/exports/pipeline.xlsx")
        check("Excel export is a real xlsx", r.status_code == 200 and
              r.content[:2] == b"PK" and len(r.content) > 5000, f"{len(r.content)} bytes")
        r = await c.get(f"/api/exports/run/{rid}.pdf")
        check("PDF run report is a real pdf", r.status_code == 200 and
              r.content[:5] == b"%PDF-" and len(r.content) > 20000, f"{len(r.content)} bytes")

        # ---------- duplicate guard ----------
        r = await c.post("/api/runs", json={"customer_id": cid, "headless": True, "speed": 4})
        rid2 = r.json().get("run_id")
        if rid2:
            dup = None
            async with c.stream("GET", f"/api/runs/{rid2}/stream") as s:
                async for line in s.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    ev = json.loads(line[6:])
                    if ev["type"] == "hold":
                        await resolve(c, rid2, ev)
                    if ev["type"] in ("done", "failed"):
                        dup = ev
                        break
            blocked = db.q("SELECT * FROM holds WHERE run_id=? AND kind='fix'", (rid2,))
            check("second application on the same connection is refused by the portal",
                  dup is not None and (dup["type"] == "failed" or any(
                      "VAL-0901" in (h["context"] or "") for h in blocked)),
                  json.dumps(dup)[:110])

    summarise()


async def resolve(c, rid, ev):
    """Act as the operator/supervisor would, reading only what a person could see."""
    kind, hid = ev["kind"], ev["id"]
    if kind == "otp":
        # a person reads the code out of the dedicated number's inbox
        code = db.one("SELECT code FROM sms WHERE msisdn=? AND code IS NOT NULL ORDER BY id DESC",
                      (ev["context"]["msisdn"],))["code"]
        body = {"resolution": "ok", "payload": {"code": code}}
    elif kind == "captcha":
        code = db.one("SELECT captcha FROM portal_sessions ORDER BY rowid DESC")["captcha"]
        body = {"resolution": "ok", "payload": {"code": code}}
    elif kind == "fix":
        body = {"resolution": "use_bill", "payload": {}}
    elif kind == "approve":
        # operator must be refused, supervisor must succeed
        r = await c.post(f"/api/runs/{rid}/holds/{hid}", json={"resolution": "approve"})
        check("operator CANNOT approve a submission (server-side)", r.status_code == 403,
              r.text[:70])
        await c.post("/api/login", json={"username": "r.deshmukh", "password": "demo"})
        body = {"resolution": "approve", "payload": {}}
    else:
        body = {"resolution": "ok", "payload": {}}
    r = await c.post(f"/api/runs/{rid}/holds/{hid}", json=body)
    if r.status_code != 200:
        print(f"      !! could not resolve {kind}: {r.status_code} {r.text[:90]}")
    if kind == "approve":
        await c.post("/api/login", json={"username": "s.kale", "password": "demo"})


def summarise():
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("   failed:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
