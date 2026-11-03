import asyncio, hashlib, json, secrets, random
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends, Body, UploadFile, File
from fastapi.responses import (JSONResponse, StreamingResponse, FileResponse, HTMLResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from . import (db, extract, exports, docs_gen, portal, discom, vault, backup, closeout, esign,
               msedcl, pmsg, registration, filing, field, tracker, dcr, jansamarth, reset as resetmod)
from .agent import runner
from .config import WEB, SHOTS, DOCS, ROLES, HEADLESS_DEFAULT, PORTAL_URL, portals, live

app = FastAPI(title="Solara", docs_url="/api/docs")
app.include_router(portal.router)
app.include_router(discom.router)
app.include_router(esign.router)
app.include_router(msedcl.router)
app.include_router(pmsg.router)
app.include_router(field.router)
app.include_router(dcr.router)
app.include_router(jansamarth.router)


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
        await docs_gen.generate()
        for c in db.q("SELECT id FROM customers"):
            try:
                await extract.run(c["id"], use_llm=False)
            except Exception:
                pass
    if not db.q("SELECT 1 FROM closeout LIMIT 1"):
        db.seed_closeout()
    closeout.demo_assets()
    dcr.seed_stock()
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


@app.post("/api/login")
def login(body: dict = Body(...)):
    row = db.one("SELECT * FROM users WHERE username=?", (body.get("username", "").strip(),))
    if not row or not db.pwcheck(body.get("password", ""), row["pw"]):
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


@app.post("/api/documents/{customer_id}/upload")
async def upload_doc(customer_id: str, kind: str = "bill", file: UploadFile = File(...),
                     user=Depends(need("operator"))):
    if not db.one("SELECT 1 FROM customers WHERE id=?", (customer_id,)):
        raise HTTPException(404, "unknown customer")
    out = DOCS / customer_id
    out.mkdir(parents=True, exist_ok=True)
    # phones name every photo image.jpg; keep the bill and the Aadhaar from overwriting each other
    name = f"{kind}_{Path(file.filename or 'upload.pdf').name}"
    p = out / name
    blob = await file.read()
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
            "vendor_signature": bool(closeout.signature("vendor")), "requests": reqs, "portals": portals(),
            "choices": closeout.CHOICES}


@app.put("/api/closeout/{cid}")
def closeout_put(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    try:
        closeout.save(_cid(cid), body, user["username"])
    except ValueError as ex:
        raise HTTPException(400, str(ex))
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
    url = str(request.base_url).rstrip("/") + f"/sign/{token}"
    return {"url": url, "whatsapp": esign.whatsapp(cid, url), "text": esign.share_text(cid, url),
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


@app.get("/api/registration")
def registration_list(user=Depends(current)):
    return [registration.summary(r["id"]) for r in _pre_install()]


@app.post("/api/customers")
def customer_create(body: dict = Body(...), user=Depends(need("operator"))):
    try:
        cid = registration.create(body.get("name"), body.get("mobile"), user)
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
            "llm": extract.llm_status()}


@app.post("/api/registration/{cid}/document")
async def registration_document(cid: str, kind: str, file: UploadFile = File(...),
                                user=Depends(need("operator"))):
    if kind not in DOC_KINDS:
        raise HTTPException(400, "unknown document type")
    await upload_doc(_cid(cid), kind, file, user)
    registration.docs_uploaded(cid, user["username"])
    kinds = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    if kinds & {"bill", "aadhaar"}:
        await extract.run(cid)
    return registration_get(cid, user)


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
        extract.confirm(_cid(cid), body.get("key"), body.get("value"), user)
    except KeyError:
        raise HTTPException(404, "no such extracted field")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return registration_get(cid, user)


@app.post("/api/registration/{cid}/mark")
def registration_mark(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    try:
        registration.mark(_cid(cid), body.get("step"), user, body.get("app_no"))
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return registration_get(cid, user)


@app.post("/api/registration/{cid}/agreement")
def registration_agreement(cid: str, request: Request, user=Depends(need("operator"))):
    c, d = closeout.data(_cid(cid))
    if not d.get("agreement_date"):
        closeout.save(cid, {"agreement_date": datetime.now().date().isoformat()}, user["username"])
    try:
        token, keys = esign.create(cid, ["agreement"], user)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    closeout.mark(cid, user["username"], agreement_sent_at=db.now())
    url = str(request.base_url).rstrip("/") + f"/sign/{token}"
    return {"url": url, "whatsapp": esign.whatsapp(cid, url), "text": esign.share_text(cid, url)}


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


PICK = {"sfr": ("sfr",), "loan": ("loan",), "dcr": ("dcr", "dealer"), "installation": ("installation", "details")}


@app.get("/api/copilot/pending")
def copilot_pending(step: str = "", user=Depends(copilot_user)):
    """Customers the co-pilot offers on a form that does not say whose it is: for a registration
    form, those ready to register; for a milestone 2 form, those whose next step it is."""
    out = []
    if step in PICK:
        for r in filing.listing():
            if r["next"]["act"] in PICK[step] and not r["paused"]:
                c = db.one("SELECT consumer_no FROM customers WHERE id=?", (r["id"],))
                out.append({"id": r["id"], "name": r["name"], "consumer_no": c["consumer_no"], "next": r["next"]["label"]})
        return out
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
    if any(s["state"] == "ready" and s["key"] not in closeout.built(cid) for s in st):
        await closeout.build(cid, user)
    cust, d = closeout.data(cid)
    made = closeout.built(cid)
    fields = [("Consumer name", cust["aadhaar_name"]), ("Consumer number", cust["consumer_no"]),
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
            "docs": [r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=? AND "
                                             "kind IN ('bill','aadhaar','passbook','roof')", (cid,))]
                    + (["site_photo"] if (DOCS / cid / "site_photo.jpg").exists() else []),
            "paused": {"by": d.get("paused_by"), "reason": d.get("paused_reason")} if d.get("paused_at") else None,
            "approvals": {k: filing.review(cid, k)["approval"] for k in filing.FORMS},
            "done": {k: bool(d.get(v)) for k, v in (("sfr", "sfr_at"), ("loan", "loan_at"), ("installation", "installation_at"),
                                                  ("dcr", "dcr_cert_no"), ("agreement_uploaded", "agreement_uploaded_at"))}}


@app.get("/api/copilot/doc/{cid}/{kind}")
def copilot_doc(cid: str, kind: str, user=Depends(copilot_user)):
    """A customer's own document (bill, Aadhaar...), for a portal's upload box."""
    if kind == "site_photo":
        p = DOCS / _cid(cid) / "site_photo.jpg"
        if not p.exists():
            raise HTTPException(404, "no site photo yet")
        d = {"path": str(p), "filename": f"{cid}_plant_photo_geotagged.jpg"}
    else:
        d = db.one("SELECT * FROM documents WHERE customer_id=? AND kind=?", (_cid(cid), kind))
    if not d or (kind not in DOC_KINDS and kind != "site_photo"):
        raise HTTPException(404, "no such document on file")
    blob = portal_sized(vault.read(Path(d["path"])))
    db.audit(user["username"], user["role"], "Co-pilot fetched document", cid, kind)
    pdf = blob.startswith(b"%PDF")
    name = Path(d["filename"]).stem + (".pdf" if pdf else ".jpg")
    return Response(blob, media_type="application/pdf" if pdf else "image/jpeg",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def portal_sized(blob):
    """Every file the co-pilot hands a portal fits the strictest upload box seen (300 KB): photos
    are re-encoded as JPEG, PDFs re-rendered only if they are over."""
    if blob.startswith(b"%PDF"):
        try:
            return closeout.fit(blob)
        except ValueError:
            return blob
    import io
    from PIL import Image
    try:
        return closeout.jpeg_under(Image.open(io.BytesIO(blob)))
    except Exception:
        return blob


@app.get("/api/copilot/file/{cid}/{key}")
def copilot_file(cid: str, key: str, user=Depends(copilot_user)):
    if key not in closeout.SPEC or key not in closeout.built(_cid(cid)):
        raise HTTPException(404, "not generated yet")
    p = closeout.path_for(cid, key)
    db.audit(user["username"], user["role"], "Co-pilot fetched document", cid, key)
    return Response(vault.read(p), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{cid}_{key}.pdf"'})


async def save_receipt(cid, step, snapshot, url, user):
    """Keep what the portal showed when the owner marked a filing done, as a PDF in the customer's file."""
    if not snapshot:
        return None
    pdf = closeout.fit(await exports.html_pdf(exports.receipt_html(snapshot, filing.STEP_LABEL.get(step, step), cid, url)))
    p = DOCS / cid / "receipts" / f"{step}_{datetime.now():%Y%m%d%H%M%S}.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    vault.write(p, pdf)
    save_doc(cid, "rc_" + step, p, len(pdf))
    db.audit(user["username"], user["role"], "Saved portal receipt", cid, f"{step}, {len(pdf) // 1024} KB")
    return len(pdf)


def save_doc(cid, kind, p, size):
    db.ex("DELETE FROM documents WHERE customer_id=? AND kind=?", (cid, kind))
    db.ex("INSERT INTO documents(customer_id,kind,filename,path,bytes,uploaded_at) VALUES(?,?,?,?,?,?)",
          (cid, kind, p.name, str(p), size, db.now()))


@app.post("/api/copilot/report")
async def copilot_report(body: dict = Body(...), user=Depends(copilot_user)):
    cid = _cid(body.get("customer_id", ""))
    uploaded = set(body.get("uploaded") or [])
    msedcl_keys = {s[0] for s in closeout.DOCS_SPEC if s[1]}
    ev = body.get("event")
    if ev in ("app_no", "agreement_uploaded"):
        c = db.one("SELECT application_no FROM customers WHERE id=?", (cid,))
        if ev == "app_no" and c["application_no"] == (body.get("app_no") or "").upper():
            return {"ok": True, "already": True}
        try:
            registration.mark(cid, "registered" if ev == "app_no" else "agreement_uploaded",
                              user, body.get("app_no"))
        except ValueError as ex:
            raise HTTPException(400, str(ex))
        if ev == "agreement_uploaded":
            await save_receipt(cid, "agreement_uploaded", body.get("receipt"), body.get("page"), user)
        return {"ok": True}
    if ev in ("filed", "dcr_cert", "loan_ref"):
        step = {"dcr_cert": "dcr", "loan_ref": "loan"}.get(ev, body.get("step"))
        if step not in ("sfr", "installation", "loan", "dcr"):
            raise HTTPException(400, "unknown step")
        c, d = closeout.data(cid)
        ref = (body.get("ref") or "").strip() or None
        already = (step == "dcr" and d.get("dcr_cert_no") == (ref or "").upper()) or \
                  (step == "loan" and d.get("loan_at") and d.get("loan_ref") == ref) or \
                  (step in ("sfr", "installation") and d.get(f"{step}_at"))
        if not already:
            try:
                filing.mark(cid, step, user, ref)
            except ValueError as ex:
                raise HTTPException(400, str(ex))
        size = await save_receipt(cid, step, body.get("receipt"), body.get("page"), user)
        if body.get("letter"):  # the bank's in-principle approval letter, fetched from the page by the co-pilot
            import base64
            blob = base64.b64decode(body["letter"])[:5 * 1024 * 1024]
            if blob.startswith(b"%PDF"):
                p = DOCS / cid / "loan_approval.pdf"
                vault.write(p, blob)
                save_doc(cid, "loan_approval", p, len(blob))
                db.audit(user["username"], user["role"], "Saved loan approval letter", cid, ref or "")
        return {"ok": True, "already": bool(already), "receipt_bytes": size}
    if ev == "dealer_wait":
        c, d = closeout.data(cid)
        if not d.get("dcr_dealer_wait"):
            closeout.mark(cid, user["username"], dcr_dealer_wait=db.now())
            db.audit(user["username"], user["role"], "DCR: waiting for the dealer", cid, str(body.get("message", ""))[:200])
        return {"ok": True}
    if ev == "otp_waiting":
        recent = db.one("SELECT 1 FROM audit WHERE action='Co-pilot waiting for OTP' AND target=? AND ts>?",
                        (cid, (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")))
        if not recent:
            db.audit(user["username"], user["role"], "Co-pilot waiting for OTP", cid, str(body.get("page", ""))[:80])
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


@app.post("/api/copilot/status")
def copilot_status(body: dict = Body(...), user=Depends(copilot_user)):
    """Rows the co-pilot read off a portal list the owner opened (read-only, no clicks)."""
    portal = body.get("portal")
    if portal not in ("pmsg", "msedcl"):
        raise HTTPException(400, "unknown portal")
    return tracker.capture(portal, body.get("rows") or [], user)


@app.get("/api/copilot/xlsx/{cid}")
def copilot_xlsx(cid: str, user=Depends(copilot_user)):
    """The DCR portal's Excel of panel numbers, for its upload box."""
    c, d = closeout.data(_cid(cid))
    sn = closeout.serials(d)
    if not sn:
        raise HTTPException(404, "no confirmed serial numbers yet")
    p = exports.serials_xlsx(cid, sn)
    return Response(p.read_bytes(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{p.name}"'})


# ------------------------------- milestone 2: filing -------------------------------
FILING_GROUPS = ("Site visit", "Loan", "References", "Modules", "Inverter and meter", "Earthing and protection")
FILING_EXTRA = ("phase",)  # from the Connection group, asked on the installation form


@app.get("/api/filing")
def filing_list(user=Depends(current)):
    return filing.listing()


@app.get("/api/filing/{cid}")
def filing_get(cid: str, user=Depends(current)):
    c, d = closeout.data(_cid(cid))
    return {"customer": c, "data": d, **filing.status(cid), "timeline": tracker.timeline(cid),
            "fields": [{"key": k, "label": lbl, "group": g} for k, lbl, g in closeout.FIELDS if g in FILING_GROUPS or k in FILING_EXTRA],
            "choices": closeout.CHOICES, "portals": portals(), "accept_text": filing.accept_text(cid),
            "checks": [{"sev": s, "text": t} for s, t in closeout.checks(cid, d)],
            "documents": db.q("SELECT kind, filename, bytes FROM documents WHERE customer_id=? AND kind IN "
                              "('roof','loan_approval')", (cid,)),
            "vendor_signature": bool(closeout.signature("vendor"))}


@app.put("/api/filing/{cid}")
def filing_put(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    keys = {k for k, _, g in closeout.FIELDS if g in FILING_GROUPS or k in FILING_EXTRA}
    vals = {k: v for k, v in body.items() if k in keys}
    if "visitor_phone" in vals and vals["visitor_phone"]:
        import re
        vals["visitor_phone"] = re.sub(r"\D", "", vals["visitor_phone"])[-10:]
        if len(vals["visitor_phone"]) != 10:
            raise HTTPException(400, "the contact number has 10 digits")
    if vals.get("roof_area"):
        try:
            if float(vals["roof_area"]) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "roof area is a number of square metres, e.g. 42")
    try:
        closeout.save(_cid(cid), vals, user["username"])
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    db.audit(user["username"], user["role"], "Updated filing details", cid, ", ".join(sorted(vals))[:200])
    return filing_get(cid, user)


def _act(fn):
    try:
        return fn()
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except KeyError as ex:
        raise HTTPException(404, str(ex))


@app.post("/api/filing/{cid}/mark")
def filing_mark(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    _act(lambda: filing.mark(_cid(cid), body.get("step"), user, body.get("ref")))
    return filing_get(cid, user)


@app.post("/api/filing/{cid}/retry")
def filing_retry(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    _act(lambda: filing.retry(_cid(cid), body.get("step"), user, body.get("reason")))
    return filing_get(cid, user)


@app.post("/api/filing/{cid}/pause")
def filing_pause(cid: str, body: dict = Body(default={}), user=Depends(need("operator"))):
    _act(lambda: filing.pause(_cid(cid), user, body.get("reason")))
    return filing_get(cid, user)


@app.post("/api/filing/{cid}/resume")
def filing_resume(cid: str, user=Depends(need("operator"))):
    filing.resume(_cid(cid), user)
    return filing_get(cid, user)


@app.get("/api/filing/{cid}/review")
def filing_review(cid: str, step: str, user=Depends(current)):
    return _act(lambda: filing.review(_cid(cid), step))


@app.post("/api/filing/{cid}/approve")
def filing_approve(cid: str, body: dict = Body(...), user=Depends(need("supervisor"))):
    return _act(lambda: filing.approve(_cid(cid), body.get("step"), user))


@app.post("/api/filing/{cid}/field-link")
def filing_field_link(cid: str, request: Request, user=Depends(need("operator"))):
    token = field.create_link(_cid(cid), user)
    url = str(request.base_url).rstrip("/") + f"/field/{token}"
    return {"url": url, **field.share(cid, url)}


@app.post("/api/filing/{cid}/serial/{rid}")
def filing_serial(cid: str, rid: int, body: dict = Body(...), user=Depends(need("operator"))):
    _act(lambda: field.decide(_cid(cid), rid, body.get("action"), user, body.get("serial")))
    return filing_get(cid, user)


@app.post("/api/filing/{cid}/serials/confirm-all")
def filing_serials_all(cid: str, user=Depends(need("operator"))):
    """One tap for every barcode read that has no problem; repeats and unreadable ones stay."""
    for r in field.reads(_cid(cid)):
        if r["status"] == "read" and r["source"] == "barcode":
            _act(lambda: field.decide(cid, r["id"], "confirm", user))
    return filing_get(cid, user)


@app.get("/api/field/{cid}/photo/{rid}.jpg")
def field_photo_dash(cid: str, rid: int, user=Depends(current)):
    return field.thumb(_cid(cid), rid)


@app.post("/api/filing/{cid}/receipt")
async def filing_receipt(cid: str, step: str, file: UploadFile = File(...), user=Depends(need("operator"))):
    """Fallback: the owner saves a portal acknowledgement by hand (PDF or screenshot)."""
    if step not in filing.STEP_LABEL:
        raise HTTPException(400, "unknown step")
    blob = await file.read()
    if blob.startswith(b"%PDF"):
        pdf = closeout.fit(blob)
    else:
        import io
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(blob)).convert("RGB")
        except Exception:
            raise HTTPException(400, "upload a PDF or a screenshot")
        buf = io.BytesIO()
        im.save(buf, "PDF", resolution=110)
        pdf = closeout.fit(buf.getvalue())
    p = DOCS / _cid(cid) / "receipts" / f"{step}_{datetime.now():%Y%m%d%H%M%S}.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    vault.write(p, pdf)
    save_doc(cid, "rc_" + step, p, len(pdf))
    db.audit(user["username"], user["role"], "Saved portal receipt", cid, f"{step}, uploaded by hand")
    return filing_get(cid, user)


@app.get("/files/receipt/{cid}/{kind}")
def receipt_file(cid: str, kind: str, user=Depends(current)):
    k = kind if kind == "loan_approval" else "rc_" + kind
    d = db.one("SELECT * FROM documents WHERE customer_id=? AND kind=?", (_cid(cid), k))
    if not d:
        raise HTTPException(404, "no receipt")
    db.audit(user["username"], user["role"], "Viewed receipt", cid, kind)
    return Response(vault.read(Path(d["path"])), media_type="application/pdf",
                    headers={"Cache-Control": "private", "Content-Disposition": f'inline; filename="{d["filename"]}"'})


@app.get("/api/filing/{cid}/dcr.xlsx")
def filing_xlsx(cid: str, user=Depends(current)):
    c, d = closeout.data(_cid(cid))
    sn = closeout.serials(d)
    if not sn:
        raise HTTPException(404, "no confirmed serial numbers yet")
    p = exports.serials_xlsx(cid, sn)
    return FileResponse(p, filename=p.name)


# ------------------------------- milestone 3: dashboard -------------------------------
@app.get("/api/today")
def today_list(user=Depends(current)):
    return tracker.today()


@app.get("/api/board")
def board(user=Depends(current)):
    return {"rows": tracker.board(), "stages": [{"key": k, "name": n, "who": w} for k, n, w in tracker.STAGES]}


@app.get("/api/tracker/{cid}")
def tracker_get(cid: str, user=Depends(current)):
    return tracker.timeline(_cid(cid))


def _month(month):
    import re
    month = month or datetime.now().strftime("%Y-%m")
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", month):
        raise HTTPException(400, "month looks like 2026-11")
    return month


@app.get("/api/exports/month.xlsx")
def month_xlsx(month: str = "", user=Depends(current)):
    p = exports.month_xlsx(_month(month))
    db.audit(user["username"], user["role"], "Exported monthly workbook", "", p.name)
    return FileResponse(p, filename=p.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/exports/month.pdf")
async def month_pdf(month: str = "", user=Depends(current)):
    p = await exports.month_pdf(_month(month))
    db.audit(user["username"], user["role"], "Exported monthly report", "", p.name)
    return FileResponse(p, filename=p.name, media_type="application/pdf")


# ------------------------------- health -------------------------------
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
        "no AI key: photos of bills are flagged for typing", warn=True)
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
def demo_reset(user=Depends(need("supervisor"))):
    if live():  # reset deletes every customer that is not demo data
        raise HTTPException(403, "reset is for the demo only and is switched off on a live install")
    for r in list(runner.RUNS.values()):
        if r.status in ("running", "held", "paused", "starting"):
            r.stop(user)
    runner.RUNS.clear()
    out = resetmod.reset()
    db.audit(user["username"], user["role"], "Reset demo environment", "", "runs and evidence cleared")
    return out


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
