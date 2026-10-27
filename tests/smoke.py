"""End-to-end test of everything the demo relies on. Drives the real HTTP API the way an
operator would, through real agent runs against both sandbox portals, and asserts on
what actually ended up in the database and on disk.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/smoke.py                          (in another)

It resets the demo first and again at the end, so it leaves a clean opening state.
"""
import asyncio, io, json, sys, zipfile, httpx
from pathlib import Path
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, vault  # noqa: E402

BASE = "http://127.0.0.1:8900"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def login(c, who):
    r = await c.post("/api/login", json={"username": who, "password": "demo"})
    assert r.status_code == 200, r.text


async def act(c, rid, ev, plan):
    """Answer a checkpoint the way a person would, reading only what a person could see."""
    kind, hid = ev["kind"], ev["id"]
    if kind == "otp":
        code = db.one("SELECT code FROM sms WHERE msisdn=? AND code IS NOT NULL ORDER BY id DESC",
                      (ev["context"]["msisdn"],))["code"]
        if plan.pop("resend_otp", False):
            plan["stale_code"] = code
            body = {"resolution": "resend", "payload": {}}
        else:
            if plan.pop("wrong_otp", False):
                # the code from before a resend, which the portal must now refuse; else a typo
                code = plan.pop("stale_code", None) or f"{(int(code) + 1) % 1000000:06d}"
            body = {"resolution": "ok", "payload": {"code": code}}
    elif kind == "captcha":
        code = db.one("SELECT captcha FROM portal_sessions ORDER BY rowid DESC")["captcha"]
        body = {"resolution": "ok", "payload": {"code": code}}
    elif kind == "fix":
        body = {"resolution": (plan.get("fix") or ["use_bill"]).pop(0), "payload": {}}
    elif kind == "approve":
        if plan.pop("operator_tries_approve", False):
            r = await c.post(f"/api/runs/{rid}/holds/{hid}", json={"resolution": "approve"})
            check("operator CANNOT approve a filing (server returns 403)", r.status_code == 403,
                  r.json().get("detail", ""))
        await login(c, "r.deshmukh")
        body = {"resolution": "approve", "payload": {}}
    else:
        body = {"resolution": "ok", "payload": {}}
    r = await c.post(f"/api/runs/{rid}/holds/{hid}", json=body)
    if r.status_code != 200:
        print(f"      !! could not resolve {kind}: {r.status_code} {r.text[:90]}")
    if kind == "approve":
        await login(c, "s.kale")


async def run(c, body, plan=None, quiet=True):
    """Start a run, answer its checkpoints, return (run_id, holds seen, final event)."""
    plan = dict(plan or {})
    r = await c.post("/api/runs", json={"headless": True, "speed": 4, **body})
    if r.status_code != 200:
        return None, [], {"type": "refused", "reason": r.json().get("detail", r.text)}
    rid = r.json()["run_id"]
    holds, end = [], None
    async with c.stream("GET", f"/api/runs/{rid}/stream") as s:
        async for line in s.aiter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev["type"] == "event" and not quiet:
                print(f"      {ev['ts']} [{ev['level']:<4}] {ev['message'][:88]}")
            if ev["type"] == "hold":
                holds.append(ev)
                await act(c, rid, ev, plan)
            if ev["type"] in ("done", "failed"):
                end = ev
                break
    return rid, holds, end


def kinds(holds):
    return [h["kind"] for h in holds]


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120, follow_redirects=True) as c:
        await login(c, "r.deshmukh")
        r = await c.post("/api/demo/reset")
        check("demo resets to its opening state", r.status_code == 200, json.dumps(r.json()))

        # ================= auth and access control =================
        print("\n  -- access control")
        r = await c.post("/api/login", json={"username": "r.deshmukh", "password": "nope"})
        check("wrong password refused", r.status_code == 401)
        check("passwords are salted scrypt, not plain hashes",
              all(u["pw"].startswith("scrypt$") for u in db.q("SELECT pw FROM users")))
        await login(c, "a.more")
        r = await c.post("/api/runs", json={"customer_id": "SS-2045"})
        check("viewer CANNOT start a run", r.status_code == 403, r.json()["detail"])
        await login(c, "s.kale")
        check("sessions persist in the database, so a restart keeps people signed in",
              db.one("SELECT COUNT(*) k FROM sessions")["k"] >= 1)
        async with httpx.AsyncClient(base_url=BASE) as anon:
            r = await anon.get("/files/docs/SS-2045/bill_sep2026.pdf")
            check("documents are NOT served without signing in", r.status_code == 401)
        r = await c.get("/files/docs/SS-2045/bill_sep2026.pdf")
        check("signed-in users get the decrypted document", r.content[:5] == b"%PDF-")

        # ================= data at rest =================
        print("\n  -- data at rest")
        docs = db.q("SELECT path FROM documents")
        sealed = [d for d in docs if vault.is_sealed(Path(d["path"]))]
        check("every customer document is encrypted on disk", len(sealed) == len(docs),
              f"{len(sealed)}/{len(docs)}")
        raw = Path(docs[0]["path"]).read_bytes()
        check("raw file bytes are not a readable PDF", b"%PDF" not in raw[:200])

        # ================= extraction =================
        print("\n  -- extraction")
        r = await c.post("/api/extract/SS-2045?use_llm=false")
        ex = r.json()
        flagged = [f["field"] for f in ex["fields"] if f["status"] == "review"]
        check("extraction parses the encrypted PDF", ex["chars_parsed"] > 300,
              f"{ex['chars_parsed']} chars, {len(ex['fields'])} fields")
        check("bill / identity name mismatch is flagged", flagged == ["Consumer name (bill)"],
              str(flagged))
        r = await c.post("/api/extract/SS-2050?use_llm=false")
        names = {f["field"]: f["value"] for f in r.json()["fields"]}
        check("new-connection applicant parses without a bill (ownership proof instead)",
              "Property owner" in names and "Consumer number" not in names,
              names.get("Property address", ""))

        # ================= guards: work the agent refuses to start =================
        print("\n  -- refusal guards")
        for cid, wf, needle, why in [
            ("SS-2044", "rooftop_registration", "PM Surya Ghar", "commercial is not eligible"),
            ("SS-2049", "rooftop_registration", "exceeds the sanctioned load", "load too low"),
            ("SS-2050", "rooftop_registration", "no electricity connection", "no connection yet"),
            ("SS-2041", "rooftop_registration", "already filed", "duplicate filing"),
            ("SS-2045", "new_connection", "already has connection", "wrong workflow"),
        ]:
            _, _, end = await run(c, {"customer_id": cid, "workflow": wf})
            check(f"refused: {cid} {why}", end["type"] == "refused" and needle in end["reason"],
                  end["reason"][:90])

        # ================= rooftop: wrong OTP, then the full path =================
        print("\n  -- rooftop registration: resend the OTP, then type the old code")
        sms_before = db.one("SELECT COUNT(*) n FROM sms WHERE sender='VM-NRSOLR'")["n"]
        rid, holds, end = await run(c, {"customer_id": "SS-2045"},
                                    {"resend_otp": True, "wrong_otp": True,
                                     "operator_tries_approve": True})
        check("run completed after a resend and a stale code", end and end["type"] == "done",
              (end or {}).get("reason", ""))
        check("checkpoints: OTP, OTP after resend, OTP after rejection, CAPTCHA, correction, approval",
              kinds(holds) == ["otp", "otp", "otp", "captcha", "fix", "approve"], str(kinds(holds)))
        check("Resend OTP made the portal text a second code",
              db.one("SELECT COUNT(*) n FROM sms WHERE sender='VM-NRSOLR'")["n"] - sms_before == 2)
        check("the prompt after a resend says a new code was sent",
              "new code" in (holds[1]["context"].get("notice") or ""))
        check("the code from before the resend is refused by the portal",
              "Incorrect OTP" in (holds[2]["context"].get("error") or ""))
        if end and end["type"] == "done":
            app_no = end["application_no"]
            check("application number read off the portal page", app_no.startswith("PMSG/MH/"),
                  app_no)
            row = db.one("SELECT * FROM portal_applications WHERE application_no=?", (app_no,))
            check("portal stored the bill spelling of the name",
                  row and row["applicant_name"] == "VAISHALI D PAWAR")
            steps = {s["key"]: s for s in db.q("SELECT * FROM run_steps WHERE run_id=?", (rid,))}
            check("OTP step records two attempts and the resend",
                  "2 attempts, 1 resend" in steps["otp"]["note"], steps["otp"]["note"])
            check("correction step keeps the operator's decision",
                  steps["fix"]["status"] == "done" and "s.kale" in steps["fix"]["note"])
            check("validation step records it passed only after a correction",
                  "retry" in steps["validate"]["note"], steps["validate"]["note"])
            appr = db.one("SELECT * FROM holds WHERE run_id=? AND kind='approve'", (rid,))
            check("approval attributed to the supervisor", appr["resolved_by"] == "r.deshmukh")
            check("refused approval attempt is in the audit trail", db.one(
                "SELECT 1 FROM audit WHERE action LIKE 'REFUSED approve%'") is not None)
            shots = db.q("SELECT * FROM screenshots WHERE run_id=?", (rid,))
            check("screenshots captured, including the failures",
                  len(shots) >= 6 and any(s["kind"] == "fail" for s in shots), f"{len(shots)}")
            check("screenshots are encrypted on disk",
                  all(vault.is_sealed(Path(s["path"])) for s in shots))
            r = await c.get(f"/files/shots/{Path(shots[0]['path']).name}")
            check("screenshots decrypt for signed-in users", r.content[:4] == b"\x89PNG")
            log = " ".join(e["message"] for e in
                           db.q("SELECT message FROM run_events WHERE run_id=?", (rid,)))
            codes = [s["code"] for s in db.q("SELECT code FROM sms WHERE code IS NOT NULL")]
            check("no OTP value ever reaches the run log", not any(k in log for k in codes))

        # ================= rooftop: operator insists, portal rejects for real =================
        print("\n  -- rooftop registration, 'submit anyway' and the portal's own rejection")
        rid, holds, end = await run(c, {"customer_id": "SS-2047"},
                                    {"fix": ["submit_anyway", "use_bill"]})
        check("run recovered from a real portal rejection", end and end["type"] == "done",
              (end or {}).get("reason", ""))
        check("checkpoints include the portal's rejection and a second approval",
              kinds(holds) == ["otp", "captcha", "fix", "approve", "fix", "approve"],
              str(kinds(holds)))
        rej = [h for h in holds if h["kind"] == "fix" and h["context"].get("portal_error")]
        check("the rejection carried the portal's error code VAL-0712",
              bool(rej) and rej[0]["context"].get("code") == "VAL-0712")

        # ================= portal: the resend cap =================
        print("\n  -- portal: resend works three times, then stops")
        pc = db.one("SELECT consumer_no, msisdn FROM portal_consumers ORDER BY rowid LIMIT 1")
        async with httpx.AsyncClient(base_url=BASE, timeout=30, follow_redirects=True) as pp:
            await pp.post("/portal/verify", data={"state": "Maharashtra", "discom": "MSEDCL",
                                                  "consumer_no": pc["consumer_no"],
                                                  "mobile": pc["msisdn"]})
            pages = [(await pp.post("/portal/otp/resend")).text for _ in range(4)]
        check("three resends each confirm a new code",
              all("new code has been sent" in t for t in pages[:3]))
        check("the fourth resend is refused", "Resend limit reached" in pages[3])

        # ================= DISCOM: the three service requests =================
        print("\n  -- DISCOM: load enhancement, load reduction, new connection")
        rid, holds, end = await run(c, {"customer_id": "SS-2049"}, {"resend_otp": True})
        check("load enhancement filed", end and end["type"] == "done",
              (end or {}).get("application_no") or (end or {}).get("reason", ""))
        check("load enhancement checkpoints: OTP, OTP after resend, approval",
              kinds(holds) == ["otp", "otp", "approve"], str(kinds(holds)))
        check("DISCOM resend texted a second DISCOM code",
              db.one("SELECT COUNT(*) n FROM sms WHERE sender='VM-DISCOM'")["n"] >= 2)
        req = db.one("SELECT * FROM portal_requests WHERE kind='load_enhancement'")
        check("DISCOM stored 3 kW → 5 kW", req and req["current_load"] == 3.0 and
              req["requested_load"] == 5.0)
        cust = db.one("SELECT * FROM customers WHERE id='SS-2049'")
        check("customer now waits on the DISCOM, next step is rooftop registration",
              cust["discom_ref"] and cust["workflow"] == "rooftop_registration")
        _, _, end = await run(c, {"customer_id": "SS-2049", "workflow": "load_enhancement"})
        check("refused: second load enhancement on the same connection",
              end["type"] == "refused", end["reason"][:90])

        _, _, end = await run(c, {"customer_id": "SS-2046", "workflow": "load_reduction",
                                  "target_kw": 120})
        check("portal validation rejects a 'reduction' to a higher load",
              end and end["type"] == "failed" and "below" in end["reason"], end["reason"][:90])
        rid, holds, end = await run(c, {"customer_id": "SS-2046", "workflow": "load_reduction",
                                        "target_kw": 80})
        check("load reduction filed (100 kW → 80 kW)", end and end["type"] == "done",
              (end or {}).get("reason", ""))
        rid, holds, end = await run(c, {"customer_id": "SS-2050"})
        check("new connection filed without a consumer number", end and end["type"] == "done",
              (end or {}).get("reason", ""))
        req = db.one("SELECT * FROM portal_requests WHERE kind='new_connection'")
        check("DISCOM stored the applicant from the identity document",
              req and req["applicant"] == "SUNITA RAMESH PATIL", req and req["applicant"])
        cust = db.one("SELECT * FROM customers WHERE id='SS-2050'")
        check("new-connection customer has its request number and no further agent work",
              cust["discom_ref"] and cust["workflow"] is None)

        # ================= follow-ups, exports, backups =================
        print("\n  -- follow-ups, exports, backups")
        fu = (await c.get("/api/followups")).json()
        check("follow-ups list the number about to expire as urgent",
              any(f["sev"] == "bad" and "44526" in f["title"] for f in fu), f"{len(fu)} items")
        check("follow-ups show DISCOM requests awaiting a decision",
              any(f["cid"] == "SS-2049" and f["sev"] == "info" for f in fu))
        r = await c.get("/api/exports/pipeline.xlsx")
        check("Excel export is a real workbook", r.content[:2] == b"PK", f"{len(r.content)} bytes")
        r = await c.get(f"/api/exports/run/{rid}.pdf")
        check("PDF run report is a real PDF with screenshots embedded",
              r.content[:5] == b"%PDF-" and len(r.content) > 40000, f"{len(r.content)} bytes")
        r = await c.post("/api/backup")
        check("operator CANNOT create a backup", r.status_code == 403)
        await login(c, "r.deshmukh")
        r = await c.post("/api/backup")
        name = r.json()["file"]
        z = zipfile.ZipFile(io.BytesIO((await c.get(f"/api/backups/{name}")).content))
        files = z.namelist()
        check("backup holds the database and the encrypted documents",
              "solara.db" in files and any(f.startswith("documents/") for f in files),
              f"{len(files)} files")
        check("backup does NOT contain the vault key", not any("vault.key" in f for f in files))

        # ================= controls: pause and abandon =================
        print("\n  -- run controls")
        # Abandon arriving just before a checkpoint opens: deterministic, no timing involved
        from app.agent.runner import Runner, HoldRejected
        probe = Runner(-1, db.one("SELECT * FROM customers WHERE id='SS-2045'"),
                       {"username": "probe", "role": "operator"}, "rooftop_registration", 3)
        probe.stop({"username": "probe", "role": "operator"})
        try:
            await asyncio.wait_for(probe.hold("otp", "probe", {}), timeout=3)
            outcome = "opened"
        except HoldRejected:
            outcome = "refused"
        except asyncio.TimeoutError:
            outcome = "hung"
        check("a checkpoint refuses to open after Abandon (no hang)", outcome == "refused", outcome)
        for t in ("run_steps", "run_events", "holds"):
            db.ex(f"DELETE FROM {t} WHERE run_id=-1")
        db.ex("DELETE FROM audit WHERE actor='probe'")

        await c.post("/api/demo/reset")
        await login(c, "s.kale")
        r = await c.post("/api/runs", json={"customer_id": "SS-2045", "headless": True, "speed": 1})
        rid = r.json()["run_id"]
        await c.post(f"/api/runs/{rid}/pause")
        paused = False
        async with c.stream("GET", f"/api/runs/{rid}/stream") as s:
            async for line in s.aiter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev["type"] == "state" and ev["status"] == "paused":
                        paused = True
                        break
        check("pause takes effect between steps", paused)
        r = await c.post(f"/api/runs/{rid}/stop")
        await asyncio.sleep(2)
        st = db.one("SELECT status FROM runs WHERE id=?", (rid,))["status"]
        check("abandon stops the run and nothing is filed",
              st == "stopped" and db.one("SELECT COUNT(*) k FROM portal_applications")["k"] == 0, st)

        await login(c, "r.deshmukh")
        r = await c.post("/api/demo/reset")
        check("demo left in its opening state", r.status_code == 200 and
              set(r.json()["runnable"]) == {"SS-2045", "SS-2047", "SS-2049", "SS-2050"},
              json.dumps(r.json()["runnable"]))

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("   failed:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
