import asyncio, hashlib, json, secrets, random
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends, Body, UploadFile, File
from fastapi.responses import (JSONResponse, StreamingResponse, FileResponse, HTMLResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from . import (db, extract, exports, docs_gen, portal, discom, vault, backup, closeout, esign, valid,
               msedcl, pmsg, registration, intake, reset as resetmod)
from .agent import runner
from .config import WEB, SHOTS, DOCS, ROLES, HEADLESS_DEFAULT, PORTAL_URL, portals, live, region, is_local
from .config import public_url as config_public_url

app = FastAPI(title="Solara", docs_url="/api/docs")
app.include_router(portal.router)
app.include_router(discom.router)
app.include_router(esign.router)
app.include_router(msedcl.router)
app.include_router(pmsg.router)
app.include_router(intake.router)


@app.on_event("startup")
async def startup():
    fresh = db.seed()
    # Runs owned by a previous process cannot be resumed: their browser is gone and their
    # holds can never be answered. Close them out so the dashboard is not stuck on a
    # checkpoint nobody can resolve.
    orphans = db.q("SELECT id FROM runs WHERE status IN ('running','held','paused','starting')")
    for o in orphans:
        db.ex("UPDATE runs SET status='stopped',finished_at=? WHERE id=?", (db.now(), o["id"]))
        db.ex("""UPDATE holds SET status='cancelled',resolved_at=?,resolution='server restarted'
                 WHERE run_id=? AND status='waiting'""", (db.now(), o["id"]))
        db.audit("system", "system", "Run closed on restart", "", f"run {o['id']}, nothing submitted")
    if orphans:
        print(f"  closed {len(orphans)} run(s) orphaned by a restart")
    if live():
        print(f"\n  Solara LIVE -> http://127.0.0.1:8900   ({len(db.q('SELECT 1 FROM users'))} user(s))")
        if not db.q("SELECT 1 FROM users"):
            print('  no users yet: python -m app.users add <username> "<Full Name>" supervisor\n')
        return
    if fresh or not db.q("SELECT 1 FROM documents LIMIT 1"):
        await docs_gen.generate([c[0] for c in db.CUSTOMERS])  # sample files are for the demo's own customers only
        for c in db.q("SELECT id FROM customers"):
            try:
                await extract.run(c["id"], use_llm=False)
            except Exception:
                pass
    if not db.q("SELECT 1 FROM closeout LIMIT 1"):
        db.seed_closeout()
    closeout.demo_assets()
    print(f"\n  Solara ready -> http://127.0.0.1:8900   (portal sandbox at {PORTAL_URL})")
    print("  sign in: r.deshmukh / s.kale / a.more   password: demo\n")


# ------------------------------- auth -------------------------------
def session_user(request: Request):
    tok = request.cookies.get("solara") or ""
    row = db.one("SELECT username FROM sessions WHERE token=?", (tok,)) if tok else None
    return row["username"] if row else None


def current(request: Request):
    u = session_user(request)
    if not u:
        raise HTTPException(401, "sign in first")
    row = db.one("SELECT username,name,role FROM users WHERE username=?", (u,))
    if not row:
        raise HTTPException(401, "unknown user")
    return row


def need(role):
    def dep(user=Depends(current)):
        if ROLES[user["role"]] < ROLES[role]:
            raise HTTPException(403, f"this action needs the {role} role; you are {user['role']}")
        return user
    return dep


@app.exception_handler(TypeError)
@app.exception_handler(AttributeError)
async def wrong_type(request: Request, exc):
    """A value of the wrong kind (a list where text belongs) is the sender's mistake, not a crash."""
    if request.url.path.startswith("/api/"):
        db.audit("system", "system", "Rejected wrong-typed request", "", f"{request.url.path}: {type(exc).__name__}")
        return JSONResponse({"detail": "one of the values has the wrong type; send plain text or numbers"}, status_code=400)
    raise exc


@app.post("/api/login")
def login(body: dict = Body(...)):
    try:
        user, pw = valid.text(body.get("username"), "username").strip(), valid.text(body.get("password"), "password")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    row = db.one("SELECT * FROM users WHERE username=?", (user,))
    if not row or not db.pwcheck(pw, row["pw"]):
        raise HTTPException(401, "wrong username or password")
    tok = secrets.token_urlsafe(32)
    db.ex("INSERT INTO sessions(token,username,created_at) VALUES(?,?,?)",
          (tok, row["username"], db.now()))
    db.audit(row["username"], row["role"], "Signed in")
    r = JSONResponse({"username": row["username"], "name": row["name"], "role": row["role"]})
    r.set_cookie("solara", tok, httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return r


@app.post("/api/logout")
def logout(request: Request):
    db.ex("DELETE FROM sessions WHERE token=?", (request.cookies.get("solara", ""),))
    r = JSONResponse({"ok": True})
    r.delete_cookie("solara")
    return r


@app.get("/api/me")
def me(request: Request):
    """Session probe. Not being signed in is an answer, not an error, so this stays 200."""
    u = session_user(request)
    return {"user": db.one("SELECT username,name,role FROM users WHERE username=?", (u,)) if u else None,
            "live": live()}


# ------------------------------- reads -------------------------------
def days_left(iso):
    try:
        left = (datetime.fromisoformat(iso) - datetime.now()).total_seconds()
        return max(0, int(-(-left // 86400)))
    except Exception:
        return 0


@app.get("/api/bootstrap")
def bootstrap(user=Depends(current)):
    active = next((r for r in runner.RUNS.values()
                   if r.status in ("running", "held", "paused", "starting")), None)
    return {
        "user": user,
        "customers": customers(),
        "numbers": numbers(),
        "calls": calls(),
        "audit": db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 200"),
        "llm": extract.llm_status(),
        "active_run": active.id if active else None,
        "runs": db.q("SELECT * FROM runs ORDER BY id DESC LIMIT 20"),
        "portal_url": PORTAL_URL,
        "workflows": [{"id": k, "label": v["label"]} for k, v in runner.WORKFLOWS.items()],
    }


@app.get("/api/customers")
def customers(user=Depends(current)):
    out = db.q("SELECT * FROM customers ORDER BY id")
    for c in out:
        n = db.one("SELECT msisdn FROM numbers WHERE customer_id=?", (c["id"],))
        c["number"] = n["msisdn"] if n else None
        c["docs"] = db.one("SELECT COUNT(*) k FROM documents WHERE customer_id=?", (c["id"],))["k"]
        c["flagged"] = 0 if c["application_no"] else db.one(
            "SELECT COUNT(*) k FROM extractions WHERE customer_id=? AND status='review'",
            (c["id"],))["k"]
    return out


@app.get("/api/numbers")
def numbers(user=Depends(current)):
    out = db.q("SELECT * FROM numbers ORDER BY id")
    for n in out:
        n["days_left"] = days_left(n["expires_at"])
        n["unread"] = db.one("SELECT COUNT(*) k FROM sms WHERE msisdn=? AND read_at IS NULL",
                             (n["msisdn"],))["k"]
    return out


@app.get("/api/calls")
def calls(user=Depends(current)):
    out = db.q("SELECT * FROM calls ORDER BY id DESC")
    for c in out:
        c["transcript"] = json.loads(c["transcript"])
    return out


@app.get("/api/audit")
def audit(user=Depends(current)):
    return db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 400")


@app.get("/api/reports")
def reports(user=Depends(current)):
    done = db.q("SELECT * FROM runs WHERE status='done'")
    allr = db.q("SELECT * FROM runs")
    holds = db.q("SELECT kind, COUNT(*) k FROM holds GROUP BY kind")
    secs = []
    for r in done:
        try:
            secs.append((datetime.fromisoformat(r["finished_at"]) -
                         datetime.fromisoformat(r["started_at"])).total_seconds())
        except Exception:
            pass
    return {
        "runs_total": len(allr),
        "runs_done": len(done),
        "runs_failed": len([r for r in allr if r["status"] in ("failed", "stopped")]),
        "retries": sum(r["retries"] for r in allr),
        "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None,
        "holds": {h["kind"]: h["k"] for h in holds},
        "applications": db.one("SELECT COUNT(*) k FROM portal_applications")["k"],
        "service_requests": db.one("SELECT COUNT(*) k FROM portal_requests")["k"],
        "by_workflow": {r["workflow"]: r["k"] for r in db.q(
            "SELECT workflow, COUNT(*) k FROM runs WHERE status='done' GROUP BY workflow")},
        "stages": {s["stage"]: s["k"] for s in
                   db.q("SELECT stage, COUNT(*) k FROM customers GROUP BY stage")},
        "documents": db.one("SELECT COUNT(*) k FROM documents")["k"],
        "extractions": db.one("SELECT COUNT(*) k FROM extractions")["k"],
        "flagged": db.one("SELECT COUNT(*) k FROM extractions WHERE status='review'")["k"],
    }


# ------------------------------- documents -------------------------------
@app.get("/api/extract/{customer_id}")
def extract_get(customer_id: str, user=Depends(current)):
    return {"customer_id": customer_id, "fields": extract.saved(customer_id),
            "documents": db.q("SELECT kind,filename,bytes FROM documents WHERE customer_id=?",
                              (customer_id,)),
            "llm": extract.llm_status()}


@app.post("/api/extract/{customer_id}")
async def extract_post(customer_id: str, use_llm: bool = True, user=Depends(need("operator"))):
    try:
        return await extract.run(customer_id, use_llm=use_llm)
    except Exception as e:
        raise HTTPException(400, str(e))


UPLOAD_KINDS = {"bill", "aadhaar", "passbook", "roof", "ownership"}


@app.post("/api/documents/{customer_id}/upload")
async def upload_doc(customer_id: str, kind: str = "bill", file: UploadFile = File(...),
                     user=Depends(need("operator"))):
    if not db.one("SELECT 1 FROM customers WHERE id=?", (customer_id,)):
        raise HTTPException(404, "unknown customer")
    if kind not in UPLOAD_KINDS:
        raise HTTPException(400, "unknown document type")
    out = DOCS / customer_id
    out.mkdir(parents=True, exist_ok=True)
    # phones name every photo image.jpg; keep the bill and the Aadhaar from overwriting each other
    name = f"{kind}_{Path(file.filename or 'upload.pdf').name}"
    p = out / name
    blob = await file.read()
    if not blob:
        raise HTTPException(400, "that file is empty; choose the document again")
    if len(blob) > 15 * 1024 * 1024:
        raise HTTPException(400, "that file is over 15 MB; send a smaller photo")
    size = vault.write(p, blob)
    db.ex("DELETE FROM documents WHERE customer_id=? AND kind=?", (customer_id, kind))
    db.ex("""INSERT INTO documents(customer_id,kind,filename,path,bytes,uploaded_at)
             VALUES(?,?,?,?,?,?)""", (customer_id, kind, name, str(p), size, db.now()))
    db.audit(user["username"], user["role"], "Uploaded document", customer_id,
             f"{kind}: {name} ({size // 1024} KB, encrypted at rest)")
    return {"ok": True, "kind": kind, "filename": name, "bytes": size}


@app.post("/api/documents/regenerate")
async def regen(user=Depends(need("operator"))):
    made = await docs_gen.generate()
    return {"ok": True, "files": len(made)}


# ------------------------------- numbers -------------------------------
@app.get("/api/numbers/{nid}/inbox")
def inbox(nid: int, user=Depends(current)):
    n = db.one("SELECT * FROM numbers WHERE id=?", (nid,))
    if not n:
        raise HTTPException(404)
    return db.q("SELECT sender,body,ts,read_at FROM sms WHERE msisdn=? ORDER BY id DESC LIMIT 10",
                (n["msisdn"],))


@app.post("/api/numbers/{nid}/test-otp")
def test_otp(nid: int, user=Depends(need("operator"))):
    n = db.one("SELECT * FROM numbers WHERE id=?", (nid,))
    if not n:
        raise HTTPException(404)
    code = f"{random.randint(0, 999999):06d}"
    db.ex("INSERT INTO sms(msisdn,sender,body,code,ts) VALUES(?,?,?,?,?)",
          (n["msisdn"], "VM-SOLARA", f"Solara delivery test. Code {code}.", code, db.now()))
    db.audit(user["username"], user["role"], "OTP delivery test", n["msisdn"], "delivered")
    return {"ok": True, "msisdn": n["msisdn"], "code_visible_in_inbox": True}


@app.post("/api/numbers/{nid}/release")
def release(nid: int, user=Depends(need("operator"))):
    n = db.one("SELECT * FROM numbers WHERE id=?", (nid,))
    if not n:
        raise HTTPException(404)
    db.ex("UPDATE numbers SET customer_id=NULL,status='free',expires_at=? WHERE id=?",
          ((datetime.now() + timedelta(days=90)).isoformat(timespec="seconds"), nid))
    db.audit(user["username"], user["role"], "Released number", n["msisdn"],
             f"was assigned to {n['customer_id']}")
    return {"ok": True}


@app.post("/api/numbers/{nid}/assign")
def assign(nid: int, body: dict = Body(default={}), user=Depends(need("operator"))):
    n = db.one("SELECT * FROM numbers WHERE id=?", (nid,))
    if not n:
        raise HTTPException(404)
    cid = body.get("customer_id")
    if not cid:
        free = db.one("""SELECT id FROM customers WHERE id NOT IN
                         (SELECT customer_id FROM numbers WHERE customer_id IS NOT NULL)""")
        if not free:
            raise HTTPException(400, "every application already holds a number")
        cid = free["id"]
    db.ex("UPDATE numbers SET customer_id=?,status='active',assigned_at=?,expires_at=? WHERE id=?",
          (cid, db.now(), (datetime.now() + timedelta(days=90)).isoformat(timespec="seconds"), nid))
    db.audit(user["username"], user["role"], "Assigned number", n["msisdn"],
             f"to {cid}, 90-day exclusive hold")
    return {"ok": True, "customer_id": cid}


# ------------------------------- runs -------------------------------
@app.post("/api/runs")
async def start_run(body: dict = Body(...), user=Depends(need("operator"))):
    try:
        r = await runner.start(body["customer_id"], user,
                               headless=bool(body.get("headless", HEADLESS_DEFAULT)),
                               speed=float(body.get("speed", 1)),
                               workflow=body.get("workflow"), target_kw=body.get("target_kw"))
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"run_id": r.id, "status": r.status}


@app.get("/api/runs")
def run_list(user=Depends(current)):
    return db.q("SELECT * FROM runs ORDER BY id DESC LIMIT 50")


@app.get("/api/runs/{rid}")
def run_detail(rid: int, user=Depends(current)):
    r = db.one("SELECT * FROM runs WHERE id=?", (rid,))
    if not r:
        raise HTTPException(404)
    live = runner.RUNS.get(rid)
    return {
        "run": r,
        "live_status": live.status if live else r["status"],
        "steps": db.q("SELECT * FROM run_steps WHERE run_id=? ORDER BY idx", (rid,)),
        "events": db.q("SELECT * FROM run_events WHERE run_id=? ORDER BY id", (rid,)),
        "shots": [{**s, "url": f"/files/shots/{Path(s['path']).name}"}
                  for s in db.q("SELECT * FROM screenshots WHERE run_id=? ORDER BY id", (rid,))],
        "holds": db.q("SELECT * FROM holds WHERE run_id=? ORDER BY id", (rid,)),
    }


@app.get("/api/runs/{rid}/stream")
async def stream(rid: int, user=Depends(current)):
    r = runner.RUNS.get(rid)
    if not r:
        raise HTTPException(404, "that run is not live in this process")
    q = r.subscribe()

    async def gen():
        yield "retry: 2000\n\n"
        try:
            while True:
                ev = await q.get()
                yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in r.subs:
                r.subs.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/runs/{rid}/pause")
def pause(rid: int, user=Depends(need("operator"))):
    r = runner.RUNS.get(rid)
    if not r:
        raise HTTPException(404)
    r.pause()
    db.audit(user["username"], user["role"], "Paused run", r.c["id"], f"run {rid}")
    return {"ok": True, "status": "pausing"}


@app.post("/api/runs/{rid}/resume")
def resume(rid: int, user=Depends(need("operator"))):
    r = runner.RUNS.get(rid)
    if not r:
        raise HTTPException(404)
    r.unpause()
    db.audit(user["username"], user["role"], "Resumed run", r.c["id"], f"run {rid}")
    return {"ok": True}


@app.post("/api/runs/{rid}/stop")
def stop_run(rid: int, user=Depends(need("operator"))):
    r = runner.RUNS.get(rid)
    if not r:
        raise HTTPException(404)
    if r.status in ("done", "failed", "stopped"):
        return {"ok": True, "status": r.status}
    r.stop(user)
    return {"ok": True}


@app.post("/api/runs/{rid}/speed")
def speed(rid: int, body: dict = Body(...), user=Depends(need("operator"))):
    r = runner.RUNS.get(rid)
    if not r:
        raise HTTPException(404)
    r.speed = max(0.25, min(4.0, float(body.get("speed", 1))))
    return {"ok": True, "speed": r.speed}


@app.post("/api/runs/{rid}/holds/{hid}")
def resolve(rid: int, hid: int, body: dict = Body(...), user=Depends(current)):
    r = runner.RUNS.get(rid)
    if not r:
        raise HTTPException(404, "run not live")
    ok, msg = r.resolve_hold(hid, body.get("resolution", "ok"), body.get("payload"), user)
    if not ok:
        raise HTTPException(403 if "role" in msg else 409, msg)
    return {"ok": True}


# ------------------------------- exports / files -------------------------------
@app.get("/api/exports/pipeline.xlsx")
def xlsx(user=Depends(current)):
    p = exports.pipeline_xlsx()
    db.audit(user["username"], user["role"], "Exported pipeline workbook", "", p.name)
    return FileResponse(p, filename=p.name,
                        media_type="application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet")


@app.get("/api/exports/run/{rid}.pdf")
async def runpdf(rid: int, user=Depends(current)):
    if not db.one("SELECT 1 FROM runs WHERE id=?", (rid,)):
        raise HTTPException(404)
    p = await exports.run_report_pdf(rid)
    db.audit(user["username"], user["role"], "Exported run report", f"run {rid}", p.name)
    return FileResponse(p, filename=p.name, media_type="application/pdf")


MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg"}


@app.get("/files/shots/{name}")
def shot(name: str, user=Depends(current)):
    p = SHOTS / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return Response(vault.read(p), media_type="image/png", headers={"Cache-Control": "private"})


@app.get("/files/docs/{cid}/{name}")
def doc(cid: str, name: str, user=Depends(current)):
    p = DOCS / Path(cid).name / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    db.audit(user["username"], user["role"], "Viewed document", Path(cid).name, p.name)
    disposition = 'inline; filename="' + p.name + '"'
    return Response(vault.read(p), media_type=MEDIA.get(p.suffix.lower(), "application/octet-stream"),
                    headers={"Cache-Control": "private", "Content-Disposition": disposition})


# ------------------------------- follow-ups -------------------------------
@app.get("/api/followups")
def followups(user=Depends(current)):
    """Everything that needs a person, worst first. Derived from live data, so it is always
    current and never needs to be maintained by hand."""
    out = []
    for n in numbers():
        if n["customer_id"] and n["days_left"] <= 14:
            out.append({"sev": "bad" if n["days_left"] <= 7 else "warn", "cid": n["customer_id"],
                        "title": f"Number {n['msisdn']} expires in {n['days_left']} days",
                        "action": "Renew before the subsidy cycle closes, or release it"})
    for c in db.q("SELECT * FROM customers WHERE blocked_note IS NOT NULL ORDER BY id"):
        out.append({"sev": "info" if c["discom_ref"] else "warn", "cid": c["id"],
                    "title": c["blocked_note"],
                    "action": "Awaiting the DISCOM" if c["discom_ref"] else
                              (runner.WORKFLOWS[c["workflow"]]["label"] if c["workflow"]
                               else "Handled by staff")})
    for r in db.q("""SELECT e.customer_id, COUNT(*) k FROM extractions e
                     JOIN customers c ON c.id = e.customer_id
                     WHERE e.status='review' AND c.application_no IS NULL AND c.workflow IS NOT NULL
                     GROUP BY e.customer_id"""):
        out.append({"sev": "warn", "cid": r["customer_id"],
                    "title": f"{r['k']} extracted field{'s' if r['k'] > 1 else ''} need review",
                    "action": "Open Document Intake"})
    for r in db.q("""SELECT * FROM runs WHERE status IN ('failed','stopped')
                     ORDER BY id DESC LIMIT 3"""):
        out.append({"sev": "info", "cid": r["customer_id"],
                    "title": f"Run {r['id']} {r['status']}; nothing was submitted",
                    "action": "Review the run report"})
    order = {"bad": 0, "warn": 1, "info": 2}
    return sorted(out, key=lambda f: order[f["sev"]])


# ------------------------------- close-out -------------------------------
CLOSE_STAGES = ("install", "netmeter", "claim")  # installed, subsidy not yet paid


def closeout_summary(cid):
    c, d = closeout.data(cid)
    st, made = closeout.status(cid), closeout.built(cid)
    ms = [s for s in st if s["slot"]]
    return {"id": cid, "name": c["name"], "kw": c["kw"], "stage": c["stage"],
            "ready": sum(s["state"] == "ready" for s in ms), "total": len(ms),
            "built": sum(s["key"] in made for s in ms),
            "missing": sum(s["state"] in ("missing", "blocked") for s in st),
            "waiting_customer": any(s["state"] in ("needs_approval", "changed") for s in st),
            "link_open": bool(db.one("""SELECT 1 FROM sign_requests WHERE customer_id=? AND
                                       status='sent' AND expires_at>?""", (cid, db.now()))),
            "uploaded": bool(d.get("msedcl_uploaded")), "msedcl_app_id": d.get("msedcl_app_id")}


def _cid(cid):
    if not db.one("SELECT 1 FROM customers WHERE id=?", (cid,)):
        raise HTTPException(404, "unknown customer")
    return cid


@app.get("/api/closeout")
def closeout_list(user=Depends(current)):
    rows = db.q(f"""SELECT id FROM customers WHERE stage IN ({",".join("?" * len(CLOSE_STAGES))})
                    ORDER BY id""", CLOSE_STAGES)
    return [closeout_summary(r["id"]) for r in rows]


@app.get("/api/closeout/{cid}")
def closeout_get(cid: str, user=Depends(current)):
    c, d = closeout.data(_cid(cid))
    made = closeout.built(cid)
    reqs = db.q("""SELECT token,status,created_at,signed_at,signer_name,docs,expires_at
                   FROM sign_requests WHERE customer_id=? ORDER BY created_at DESC LIMIT 5""", (cid,))
    for r in reqs:
        r["docs"] = list(json.loads(r["docs"]))
    return {"customer": c, "data": d,
            "fields": [{"key": k, "label": lbl, "group": g} for k, lbl, g in closeout.FIELDS],
            "checks": [{"sev": s, "text": t} for s, t in closeout.checks(cid, d)],
            "docs": [{**s, "bytes": made.get(s["key"])} for s in closeout.status(cid)],
            "capacity": closeout.capacity(d), "serial_count": len(closeout.serials(d)),
            "consumer_signature": bool(closeout.signature("consumer", cid)),
            "vendor_signature": bool(closeout.signature("vendor")), "requests": reqs}


CLOSEOUT_RULES = {"aadhaar_last4": valid.aadhaar_any, "mobile": valid.mobile, "rts_cost": valid.cost,
                  "email": valid.email}


def closeout_checked(body):
    """The close-out page follows the same rules as Registration: a full Aadhaar number is cut to its
    last 4 here, and a bad cost or mobile is refused instead of saved."""
    out = dict(body)
    for k, rule in CLOSEOUT_RULES.items():
        try:
            if k in out and valid.text(out[k], k).strip():
                out[k] = rule(out[k])
        except ValueError as ex:
            raise HTTPException(400, str(ex))
    return out


@app.put("/api/closeout/{cid}")
def closeout_put(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    body = closeout_checked(body)
    closeout.save(_cid(cid), body, user["username"])
    db.audit(user["username"], user["role"], "Updated close-out details", cid,
             ", ".join(sorted(k for k in body if k in closeout.LABEL))[:200])
    return closeout_get(cid, user)


@app.post("/api/closeout/{cid}/photo")
async def closeout_photo(cid: str, file: UploadFile = File(...), user=Depends(need("operator"))):
    try:
        lat, lng = closeout.save_photo(_cid(cid), await file.read(), user["username"])
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except OSError:
        raise HTTPException(400, "that file is not a photo")
    db.audit(user["username"], user["role"], "Added site photo", cid, f"GPS {lat}, {lng}")
    return {"ok": True, "lat": lat, "lng": lng}


@app.get("/api/closeout/{cid}/photo.jpg")
def closeout_photo_get(cid: str, user=Depends(current)):
    p = DOCS / Path(cid).name / "site_photo.jpg"
    if not p.exists():
        raise HTTPException(404)
    return Response(vault.read(p), media_type="image/jpeg", headers={"Cache-Control": "private"})


@app.post("/api/closeout/{cid}/datasheet")
async def closeout_datasheet(cid: str, file: UploadFile = File(...), user=Depends(need("operator"))):
    try:
        size = closeout.save_datasheet(_cid(cid), await file.read())
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    db.audit(user["username"], user["role"], "Added datasheet to the library", cid, f"{size // 1024} KB")
    return {"ok": True, "bytes": size}


@app.post("/api/closeout/{cid}/sign")
def closeout_sign(cid: str, request: Request, body: dict = Body(default={}),
                  user=Depends(need("operator"))):
    try:
        token, keys = esign.create(_cid(cid), body.get("docs"), user)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    url = config_public_url(request, f"/sign/{token}")
    return {"url": url, "whatsapp": esign.whatsapp(cid, url), "text": esign.share_text(cid, url), "local": is_local(url),
            "docs": keys}


@app.post("/api/closeout/{cid}/build")
async def closeout_build(cid: str, user=Depends(need("operator"))):
    return await closeout.build(_cid(cid), user)


@app.get("/files/closeout/{cid}/{key}.pdf")
def closeout_file(cid: str, key: str, user=Depends(current)):
    if key not in closeout.SPEC or key not in closeout.built(_cid(cid)):
        raise HTTPException(404, "not generated yet")
    p = closeout.path_for(cid, key)
    db.audit(user["username"], user["role"], "Viewed close-out document", cid, key)
    return Response(vault.read(p), media_type="application/pdf",
                    headers={"Cache-Control": "private", "Content-Disposition": f'inline; filename="{p.name}"'})


@app.post("/api/signature/vendor")
def vendor_signature(body: dict = Body(...), user=Depends(need("supervisor"))):
    try:
        png = closeout.png_from_data_url(body.get("image"))
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    name = (body.get("name") or "").strip() or user["name"]
    closeout.save_signature("vendor", png, name)
    for r in db.q("SELECT customer_id FROM closeout"):
        closeout.invalidate(r["customer_id"])
    db.audit(user["username"], user["role"], "Set the company signature", "", name)
    return {"ok": True}


# ------------------------------- registration (milestone 1) -------------------------------
DOC_KINDS = {"bill": "Electricity bill", "aadhaar": "Aadhaar", "passbook": "Bank passbook or cheque",
             "roof": "Roof photo"}


def _pre_install():
    return db.q(f"""SELECT id FROM customers WHERE workflow='rooftop_registration' AND stage IN
                    ({",".join("?" * len(registration.PRE_STAGES))}) ORDER BY id DESC""",
                registration.PRE_STAGES)


@app.get("/api/today")
def today_list(user=Depends(current)):
    """One list of what to do now, for every customer: calls, things to do here, things on the portals."""
    rows = db.q(f"""SELECT id FROM customers WHERE stage IN ({",".join("?" * len(CLOSE_STAGES))}) ORDER BY id""", CLOSE_STAGES)
    return registration.today([closeout_summary(r["id"]) for r in rows])


@app.get("/api/registration")
def registration_list(user=Depends(current)):
    return [registration.summary(r["id"]) for r in _pre_install()]


@app.post("/api/customers")
def customer_create(body: dict = Body(...), user=Depends(need("operator"))):
    try:
        cid = registration.create(body.get("name"), body.get("mobile"), user,
                                  allow_duplicate=bool(body.get("allow_duplicate")))
    except registration.Duplicate as ex:
        return JSONResponse({"detail": str(ex), "duplicates": ex.matches}, status_code=409)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return registration_get(cid, user)


@app.get("/api/registration/{cid}")
def registration_get(cid: str, user=Depends(current)):
    c, d = closeout.data(_cid(cid))
    reqs = db.q("""SELECT status,created_at,signed_at,signer_name FROM sign_requests WHERE customer_id=?
                   AND docs LIKE '%agreement%' ORDER BY created_at DESC LIMIT 3""", (cid,))
    return {"customer": c, "data": d, **registration.status(cid),
            "fields": [{**r, "key": extract.KEY_OF.get(r["field"])} for r in extract.saved(cid)],
            "documents": db.q("""SELECT kind, filename, bytes, uploaded_at FROM documents WHERE
                                 customer_id=? AND kind NOT LIKE 'co_%'""", (cid,)),
            "doc_kinds": DOC_KINDS, "values": registration.values(cid), "portals": portals(),
            "vendor_signature": bool(closeout.signature("vendor")), "requests": reqs,
            "agreement": {"draft": closeout.TEMPLATE_DRAFT, "check": closeout.verify_agreement(cid)},
            "suggest": registration.suggest(cid), "llm": extract.llm_status(), "otp": registration.heads_up(cid),
            "districts": valid.MH_DISTRICTS if region()["state"] == "Maharashtra" else []}


async def take_document(cid, kind, file, user):
    """Store one registration document and read it. Used by the dashboard and by the customer's own link."""
    if kind not in DOC_KINDS:
        raise HTTPException(400, "unknown document type")
    await upload_doc(cid, kind, file, user)
    registration.docs_uploaded(cid, user["username"])
    kinds = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    if kinds & {"bill", "aadhaar"}:
        try:
            await extract.run(cid, fresh=kind)
        except Exception as ex:  # the upload is kept; the person can retry or type the details
            db.audit("agent", "agent", "Document extraction failed", cid, f"{kind}: {type(ex).__name__}")
            return f"The file is saved but could not be read ({type(ex).__name__}). Try Read again or type the details."
    return None


@app.post("/api/registration/{cid}/document")
async def registration_document(cid: str, kind: str, file: UploadFile = File(...),
                                user=Depends(need("operator"))):
    problem = await take_document(_cid(cid), kind, file, user)
    out = registration_get(cid, user)
    out["extract_error"] = problem
    return out


@app.post("/api/registration/{cid}/ask-docs")
def registration_ask_docs(cid: str, request: Request, user=Depends(need("operator"))):
    """A link for the customer to send their own bill, Aadhaar and email from their phone."""
    url = intake.link(request, intake.create(_cid(cid), user))
    return {"url": url, "whatsapp": intake.whatsapp(cid, url), "text": intake.share_text(cid, url), "local": is_local(url)}


@app.put("/api/registration/{cid}")
def registration_put(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    try:
        registration.save_details(_cid(cid), body, user)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return registration_get(cid, user)


@app.post("/api/registration/{cid}/confirm")
def registration_confirm(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    try:
        extract.confirm(_cid(cid), valid.text(body.get("key"), "key"), body.get("value"), user)
    except KeyError:
        raise HTTPException(404, "no such extracted field")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return registration_get(cid, user)


@app.post("/api/registration/{cid}/mark")
def registration_mark(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    try:
        registration.mark(_cid(cid), valid.text(body.get("step"), "step"), user, body.get("app_no"),
                          replace=body.get("replace") is True)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return registration_get(cid, user)


@app.get("/api/registration/{cid}/agreement/check")
async def registration_agreement_check(cid: str, user=Depends(current)):
    """Verify the signed agreement: the approval, the kept copy, both signatures, and that the
    stored PDF opens and names this customer."""
    cid = _cid(cid)
    res = closeout.verify_agreement(cid)
    st = next(s for s in closeout.status(cid) if s["key"] == "agreement")
    if st["state"] == "ready" and "agreement" not in closeout.built(cid):
        try:
            await closeout.build(cid, user)
        except Exception as ex:
            res["problems"].append(f"the agreement PDF could not be generated ({type(ex).__name__})")
    if "agreement" in closeout.built(cid):
        try:
            from pypdf import PdfReader
            import io
            text = " ".join(p.extract_text() or "" for p in
                            PdfReader(io.BytesIO(vault.read(closeout.path_for(cid, "agreement")))).pages)
            if (closeout.data(cid)[0]["consumer_no"] or "x") not in text:
                res["problems"].append("the stored PDF does not show this customer's consumer number")
        except Exception as ex:
            res["problems"].append(f"the stored PDF could not be opened ({type(ex).__name__})")
    elif st["state"] == "ready":
        res["problems"].append("the signed agreement PDF is not stored")
    res["ok"] = not res["problems"]
    return {**res, "draft": closeout.TEMPLATE_DRAFT}


@app.post("/api/registration/{cid}/agreement")
def registration_agreement(cid: str, request: Request, user=Depends(need("operator"))):
    c, d = closeout.data(_cid(cid))
    try:
        registration.require_ready(cid, "cannot send the agreement")
        if not d.get("accepted_at"):
            raise ValueError("cannot send the agreement: accept the customer in the vendor login first")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    if not d.get("agreement_date"):
        closeout.save(cid, {"agreement_date": datetime.now().date().isoformat()}, user["username"])
    try:
        token, keys = esign.create(cid, ["agreement"], user)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    closeout.mark(cid, user["username"], agreement_sent_at=db.now())
    url = config_public_url(request, f"/sign/{token}")
    return {"url": url, "whatsapp": esign.whatsapp(cid, url), "text": esign.share_text(cid, url), "local": is_local(url)}


# ------------------------------- co-pilot extension -------------------------------
def copilot_user(request: Request):
    key = request.headers.get("X-Solara-Key", "")
    row = db.one("SELECT username FROM copilot_keys WHERE key_hash=?",
                 (hashlib.sha256(key.encode()).hexdigest(),)) if key else None
    if not row:
        raise HTTPException(401, "co-pilot key not recognised; create a new one in Solara")
    return db.one("SELECT username,name,role FROM users WHERE username=?", (row["username"],))


@app.post("/api/copilot/key")
def copilot_key(user=Depends(need("operator"))):
    key = "sk_" + secrets.token_urlsafe(24)
    db.ex("INSERT INTO copilot_keys(key_hash,username,created_at) VALUES(?,?,?)",
          (hashlib.sha256(key.encode()).hexdigest(), user["username"], db.now()))
    db.audit(user["username"], user["role"], "Created a co-pilot key")
    return {"key": key}


@app.get("/api/copilot/pending")
def copilot_pending(user=Depends(copilot_user)):
    """Customers ready to be registered: the co-pilot offers these on a blank portal form."""
    out = []
    for r in _pre_install():
        c = db.one("SELECT id, name, consumer_no, application_no FROM customers WHERE id=?", (r["id"],))
        if c["consumer_no"] and not c["application_no"]:
            out.append({"id": c["id"], "name": c["name"], "consumer_no": c["consumer_no"]})
    return out


@app.get("/api/copilot/lookup")
async def copilot_lookup(consumer_no: str = "", app_no: str = "", cid: str = "",
                         user=Depends(copilot_user)):
    """Which customer is on the portal page the operator has open, and what Solara has for it."""
    c = db.one("SELECT id FROM customers WHERE id=?", (cid,)) if cid else None
    if not c and consumer_no:
        c = db.one("SELECT id FROM customers WHERE consumer_no=?", (consumer_no.strip(),))
    if not c and app_no:
        c = db.one("SELECT id FROM customers WHERE application_no=?", (app_no.strip(),))
        if not c:
            c = next(({"id": r["customer_id"]} for r in db.q("SELECT customer_id, data FROM closeout")
                      if json.loads(r["data"]).get("pmsg_app_no") == app_no.strip()), None)
    if not c:
        raise HTTPException(404, "this customer is not in Solara")
    cid = c["id"]
    st = closeout.status(cid)
    build_error = None
    if any(s["state"] == "ready" and s["key"] not in closeout.built(cid) for s in st):
        try:
            await closeout.build(cid, user)
        except Exception as ex:  # report it; the fields still fill and the person is told
            build_error = f"Could not generate the signed documents ({type(ex).__name__}). Try again."
            db.audit(user["username"], user["role"], "Document generation failed", cid, type(ex).__name__)
    cust, d = closeout.data(cid)
    made = closeout.built(cid)
    fields = [("Consumer name", cust["aadhaar_name"] or cust["name"]), ("Consumer number", cust["consumer_no"]),
              ("Address", cust["address"]), ("PIN code", cust["pin"]),
              ("Capacity (kWp)", closeout.capacity(d))]
    fields += [(lbl, d.get(k)) for k, lbl, _ in closeout.FIELDS if d.get(k)]
    return {"customer_id": cid, "name": cust["name"], "application_no": cust["application_no"],
            "files": [{"key": s["key"], "slot": s["slot"], "title": s["title"], "bytes": made[s["key"]]}
                      for s in st if s["key"] in made],
            "not_ready": [{"title": s["title"], "note": s["note"]} for s in st
                          if s["slot"] and s["key"] not in made],
            "fields": [{"label": k, "value": str(v)} for k, v in fields if v not in (None, "")],
            "values": {k: v for k, v in registration.values(cid).items() if v},
            "issues": registration.validate(cid)["issues"], "build_error": build_error,
            "derived": registration.derived(cid),
            "agreement_draft": closeout.TEMPLATE_DRAFT,
            "docs": [r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=? AND "
                                             "kind IN ('bill','aadhaar','passbook','roof')", (cid,))]}


@app.get("/api/copilot/doc/{cid}/{kind}")
def copilot_doc(cid: str, kind: str, user=Depends(copilot_user)):
    """A customer's own document (bill, Aadhaar...), for a portal's upload box."""
    d = db.one("SELECT * FROM documents WHERE customer_id=? AND kind=?", (_cid(cid), kind))
    if not d or kind not in DOC_KINDS:
        raise HTTPException(404, "no such document on file")
    blob = vault.read(Path(d["path"]))
    db.audit(user["username"], user["role"], "Co-pilot fetched document", cid, kind)
    kind_type = "application/pdf" if blob.startswith(b"%PDF") else \
        "image/png" if blob.startswith(b"\x89PNG") else "image/jpeg"
    return Response(blob, media_type=kind_type,
                    headers={"Content-Disposition": f'attachment; filename="{d["filename"]}"'})


@app.get("/api/copilot/file/{cid}/{key}")
def copilot_file(cid: str, key: str, user=Depends(copilot_user)):
    if key not in closeout.SPEC or key not in closeout.built(_cid(cid)):
        raise HTTPException(404, "not generated yet")
    p = closeout.path_for(cid, key)
    db.audit(user["username"], user["role"], "Co-pilot fetched document", cid, key)
    return Response(vault.read(p), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{cid}_{key}.pdf"'})


@app.post("/api/copilot/report")
def copilot_report(body: dict = Body(...), user=Depends(copilot_user)):
    if body.get("event") == "page_layout":
        return registration.save_layout(body, user)
    if body.get("event") == "portal_list":
        return registration.from_portal_list(body.get("rows") or [], str(body.get("page", ""))[:80], user)
    cid = _cid(body.get("customer_id", ""))
    uploaded = set(body.get("uploaded") or [])
    msedcl_keys = {s[0] for s in closeout.DOCS_SPEC if s[1]}
    if body.get("event") in ("app_no", "agreement_uploaded"):
        c = db.one("SELECT application_no FROM customers WHERE id=?", (cid,))
        if body["event"] == "app_no" and c["application_no"] == (body.get("app_no") or "").upper():
            return {"ok": True, "already": True}
        try:
            registration.mark(cid, "registered" if body["event"] == "app_no" else "agreement_uploaded",
                              user, body.get("app_no"), from_portal=body["event"] == "app_no")
        except ValueError as ex:
            raise HTTPException(400, str(ex))
        return {"ok": True}
    if body.get("portal") == "msedcl" and msedcl_keys <= uploaded:
        closeout.mark(cid, user["username"], msedcl_uploaded="yes", msedcl_uploaded_at=db.now())
        db.audit(user["username"], user["role"], "MSEDCL documents uploaded", cid,
                 "all 6 show Verification Pending on the portal")
    if body.get("left"):
        # portal drift: a field the co-pilot used to fill is now unknown; /api/health shows it
        labels = sorted({str(x)[:60] for x in body["left"]})[:12]
        db.audit(user["username"], user["role"], "Co-pilot left fields", cid,
                 f"{str(body.get('page', ''))[:80]}: {', '.join(labels)}")
    if body.get("attached"):
        db.audit(user["username"], user["role"], "Co-pilot attached files", cid,
                 f"{body['attached']} file(s) on {body.get('portal')}; operator presses Upload")
    return {"ok": True}


# ------------------------------- health -------------------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)  # no icon; answering keeps the browser console free of a 404


@app.get("/api/health")
def health(user=Depends(current)):
    """Everything that breaks slowly, checked in one place: the database, the key, backups, disk,
    and portal drift (fields the co-pilot could no longer fill)."""
    import shutil
    from .config import DATA
    out = []
    add = lambda key, ok, text, warn=False: out.append(
        {"key": key, "state": "ok" if ok else ("warn" if warn else "bad"), "text": text})
    qc = db.one("PRAGMA quick_check")
    ver = db.conn().execute("PRAGMA user_version").fetchone()[0]
    add("database", list(qc.values())[0] == "ok" and ver == len(db.MIGRATIONS),
        f"integrity {list(qc.values())[0]}, schema {ver}/{len(db.MIGRATIONS)}")
    doc = db.one("SELECT path FROM documents ORDER BY id DESC")
    try:
        if doc:
            vault.read(Path(doc["path"]))
        add("key", True, "the vault key opens the documents" if doc else "no documents yet")
    except Exception as e:
        add("key", False, f"the vault key does not open the documents ({type(e).__name__})")
    zips = sorted(backup.BACKUPS.glob("*.zip"), key=lambda p: p.stat().st_mtime) if backup.BACKUPS.exists() else []
    age = (datetime.now().timestamp() - zips[-1].stat().st_mtime) / 3600 if zips else None
    add("backups", age is not None and age < 36,
        f"last backup {age:.0f} h ago" if age is not None else "no backup yet", warn=not live())
    free = shutil.disk_usage(DATA).free / 1e9
    add("disk", free > 2, f"{free:.1f} GB free")
    since = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    drift = db.q("""SELECT detail, COUNT(*) k FROM audit WHERE action='Co-pilot left fields' AND ts>?
                    GROUP BY detail ORDER BY k DESC LIMIT 5""", (since,))
    add("portals", not drift, "no unfilled fields in 7 days" if not drift else
        "fields left unfilled: " + "; ".join(f"{d['detail']} ({d['k']}x)" for d in drift), warn=True)
    llm = extract.llm_status()
    add("ai", llm["enabled"], f"{llm['provider']} for photos" if llm["enabled"] else
        "AI is off (by design): the rules read bills and Aadhaar; photos of bills are flagged for typing", warn=True)
    return {"ok": all(c["state"] == "ok" for c in out if c["key"] in ("database", "key", "disk")),
            "checks": out}


# ------------------------------- backups -------------------------------
@app.post("/api/backup")
def make_backup(user=Depends(need("supervisor"))):
    p = backup.create()
    db.audit(user["username"], user["role"], "Created backup", "", p.name)
    return {"ok": True, "file": p.name, "bytes": p.stat().st_size}


@app.get("/api/backups/{name}")
def get_backup(name: str, user=Depends(need("supervisor"))):
    p = backup.BACKUPS / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name, media_type="application/zip")


@app.post("/api/demo/reset")
async def demo_reset(user=Depends(need("supervisor"))):
    if live():  # reset deletes every customer that is not demo data
        raise HTTPException(403, "reset is for the demo only and is switched off on a live install")
    for r in list(runner.RUNS.values()):
        if r.status in ("running", "held", "paused", "starting"):
            r.stop(user)
    runner.RUNS.clear()
    corrected = [r["customer_id"] for r in db.q("SELECT DISTINCT customer_id FROM extractions WHERE note LIKE 'Checked by%'")]
    out = resetmod.reset()
    # a value someone corrected during a rehearsal is not demo data: read those customers' documents afresh
    for cid in corrected:
        if db.one("SELECT 1 FROM customers WHERE id=?", (cid,)):
            db.ex("DELETE FROM extractions WHERE customer_id=?", (cid,))
            try:
                await extract.run(cid, use_llm=False)
            except Exception:
                pass
    db.audit(user["username"], user["role"], "Reset demo environment", "", "runs and evidence cleared")
    return out


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})  # updates are seen on the next load


class FreshStatic(StaticFiles):
    """The browser asks each time whether the dashboard's files changed (a cheap 304 when not), so an
    update is seen on the next page load instead of an old copy running from the cache. Set here, on the
    static files only: a global HTTP middleware would wrap the live run stream too."""
    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", FreshStatic(directory=WEB), name="static")
