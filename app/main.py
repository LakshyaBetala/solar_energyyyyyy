import asyncio, hashlib, io, json, os, secrets, random
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends, Body, UploadFile, File, Form
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi.responses import (JSONResponse, StreamingResponse, FileResponse, HTMLResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from . import (db, drafts, extract, exports, docs_gen, portal, discom, vault, backup, closeout, esign, valid,
               msedcl, pmsg, registration, intake, filing, field, tracker, dcr, jansamarth, upkeep, kpi,
               reset as resetmod)
from .agent import runner
from .config import clean, single_owner, HELPER_DIR, DATA, WEB, SHOTS, DOCS, ROLES, HEADLESS_DEFAULT, PORTAL_URL, portals, live, region, is_local
from .config import public_url as config_public_url

app = FastAPI(title="Solara", docs_url="/api/docs")
app.include_router(portal.router)
app.include_router(discom.router)
app.include_router(esign.router)
app.include_router(msedcl.router)
app.include_router(pmsg.router)
app.include_router(intake.router)
app.include_router(field.router)
app.include_router(dcr.router)
app.include_router(jansamarth.router)


@app.on_event("startup")
async def startup():
    fresh = db.seed()
    if not os.environ.get("SOLARA_NO_UPKEEP"):  # tests that time backups turn it off
        upkeep.start()
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
    if not clean() and (fresh or not db.q("SELECT 1 FROM documents LIMIT 1")):
        await docs_gen.generate([c[0] for c in db.CUSTOMERS])  # sample files are for the demo's own customers only
        for c in db.q("SELECT id FROM customers"):
            try:
                await extract.run(c["id"], use_llm=False)
            except Exception:
                pass
    if not clean():
        if not db.q("SELECT 1 FROM closeout LIMIT 1"):
            db.seed_closeout()
        closeout.demo_assets()
    dcr.seed_stock()
    print(f"\n  Solara ready -> http://127.0.0.1:8900   (portal sandbox at {PORTAL_URL})")
    print("  sign in: r.deshmukh / s.kale / a.more   password: demo\n")


# ------------------------------- auth -------------------------------
SESSION_HOURS = 12
FAILS, LOCK_MIN = 5, 15  # five wrong passwords lock that username for fifteen minutes


def session_user(request: Request):
    tok = request.cookies.get("solara") or ""
    row = db.one("SELECT username, created_at FROM sessions WHERE token=?", (tok,)) if tok else None
    # the cookie's own expiry is the browser's word; the server keeps its own
    if row and row["created_at"] < (datetime.now() - timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds"):
        db.ex("DELETE FROM sessions WHERE token=?", (tok,))
        row = None
    return row["username"] if row else owner_here(request)


OWNER = "owner"


def owner_here(request: Request):
    """A single-owner install: a request made on this computer, by Solara's own page, is the owner's, with no
    sign-in. A page of another site open in the same browser cannot use this (its Origin is not Solara's, and
    the browser marks its requests cross-site), nor can a web address pointed at this computer (the Host)."""
    if not single_owner() or not from_this_computer(request):
        return None
    host = request.headers.get("host", "")
    if host.split(":")[0] not in ("127.0.0.1", "localhost"):
        return None
    origin = request.headers.get("origin")
    if (origin and origin != f"http://{host}") or request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return None
    if not db.one("SELECT 1 FROM users WHERE username=?", (OWNER,)):
        # a password nobody knows: this account is only ever reached this way
        db.ex("INSERT INTO users(username,name,role,pw) VALUES(?,?,?,?)",
              (OWNER, os.environ.get("SOLARA_OWNER_NAME", "Owner"), "supervisor", db.pwhash(secrets.token_urlsafe(24))))
    return OWNER


def from_this_computer(request: Request):
    """Directly from this computer, not through the HTTPS proxy (which adds X-Forwarded-For)."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost") and not request.headers.get("x-forwarded-for")


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
def login(request: Request, body: dict = Body(...)):
    try:
        user, pw = valid.text(body.get("username"), "username").strip().lower(), valid.text(body.get("password"), "password")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    since = (datetime.now() - timedelta(minutes=LOCK_MIN)).isoformat(timespec="seconds")
    host = request.client.host if request.client else ""
    last_ok = db.one("SELECT MAX(id) i FROM audit WHERE action='Signed in' AND actor=?", (user[:40],))["i"] or 0
    fails = db.one("""SELECT COUNT(*) k FROM audit WHERE action='Failed sign-in' AND target=? AND detail=? AND ts>? AND id>?""",
                   (user[:40], host, since, last_ok))["k"]
    if fails >= FAILS:
        raise HTTPException(429, f"too many wrong passwords for {user}; try again in {LOCK_MIN} minutes")
    row = db.one("SELECT * FROM users WHERE username=?", (user,))
    if not row or not db.pwcheck(pw, row["pw"]):
        db.audit("anonymous", "none", "Failed sign-in", user[:40], host)
        raise HTTPException(401, "wrong username or password")
    tok = secrets.token_urlsafe(32)
    db.ex("INSERT INTO sessions(token,username,created_at) VALUES(?,?,?)",
          (tok, row["username"], db.now()))
    db.audit(row["username"], row["role"], "Signed in")
    r = JSONResponse({"username": row["username"], "name": row["name"], "role": row["role"]})
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie("solara", tok, httponly=True, samesite="lax", max_age=60 * 60 * SESSION_HOURS, secure=https)
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
            "live": live(), "single": single_owner(),
            "setup": not single_owner() and not db.q("SELECT 1 FROM users") and from_this_computer(request)}


@app.get("/api/helper")
def helper_get(request: Request, user=Depends(current)):
    """Where the Chrome helper's folder is on this computer, for Chrome's "Load unpacked"."""
    return {"folder": str(HELPER_DIR), "here": from_this_computer(request)}


@app.post("/api/helper/open")
def helper_open(request: Request, body: dict = Body(...), user=Depends(need("operator"))):
    """Open the helper's folder in Explorer, or Solara in the computer's browser. Only on the computer Solara runs on."""
    if not from_this_computer(request):
        raise HTTPException(403, "this works on the computer Solara runs on")
    what = body.get("what")
    if what == "folder":
        os.startfile(str(HELPER_DIR)) if hasattr(os, "startfile") else None
    elif what == "solara":
        import webbrowser
        webbrowser.open(f"http://{request.headers.get('host', '127.0.0.1:8900')}/")
    else:
        raise HTTPException(400, "unknown")
    return {"ok": True}


def new_user(body):
    """A person who signs in: lower-case username, a name, a role, a password of 10+ characters."""
    from .users import MIN_PASSWORD
    try:
        username = valid.text(body.get("username"), "username").strip().lower()
        name = " ".join(valid.text(body.get("name"), "name").split())
        pw = valid.text(body.get("password"), "password")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    role = body.get("role", "operator")
    import re as _re
    if not _re.fullmatch(r"[a-z][a-z0-9._-]{1,29}", username):
        raise HTTPException(400, "username: 2-30 letters, digits, dot, dash or underscore, starting with a letter")
    if role not in ROLES or len(name) < 2:
        raise HTTPException(400, "give the person's name and a role (viewer, operator or supervisor)")
    if len(pw) < MIN_PASSWORD:
        raise HTTPException(400, f"the password needs {MIN_PASSWORD} or more characters")
    return username, name, role, pw


@app.post("/api/setup")
def first_user(request: Request, body: dict = Body(...)):
    """The very first supervisor, created on the computer Solara runs on and only while there is nobody."""
    if db.q("SELECT 1 FROM users") or not from_this_computer(request):
        raise HTTPException(403, "people are added by a supervisor in Solara")
    username, name, _, pw = new_user({**body, "role": "supervisor"})
    db.ex("INSERT INTO users(username,name,role,pw) VALUES(?,?,?,?)", (username, name, "supervisor", db.pwhash(pw)))
    db.audit(username, "supervisor", "Created the first supervisor", username, name)
    return login(request, {"username": username, "password": pw})


@app.get("/api/users")
def users_list(user=Depends(need("supervisor"))):
    return db.q("SELECT username, name, role FROM users ORDER BY role DESC, username")


@app.post("/api/users")
def users_save(body: dict = Body(...), user=Depends(need("supervisor"))):
    """Add a person, or give an existing one a new role or password."""
    username = str(body.get("username", "")).strip().lower()
    old = db.one("SELECT username FROM users WHERE username=?", (username,))
    if old and not body.get("password"):  # role change only
        if body.get("role") not in ROLES:
            raise HTTPException(400, "unknown role")
        if username == user["username"] and body["role"] != "supervisor":
            raise HTTPException(400, "you cannot take away your own supervisor role")
        db.ex("UPDATE users SET role=? WHERE username=?", (body["role"], username))
        db.audit(user["username"], user["role"], "Changed role", username, body["role"])
        return users_list(user)
    username, name, role, pw = new_user({**body, "name": body.get("name") or (old and username) or ""})
    if old:
        db.ex("UPDATE users SET pw=? WHERE username=?", (db.pwhash(pw), username))
        db.ex("DELETE FROM sessions WHERE username=?", (username,))  # the old password's sessions end
        db.ex("DELETE FROM copilot_keys WHERE username=?", (username,))  # and its Chrome helper keys
        db.audit(user["username"], user["role"], "Reset password", username)
    else:
        db.ex("INSERT INTO users(username,name,role,pw) VALUES(?,?,?,?)", (username, name, role, db.pwhash(pw)))
        db.audit(user["username"], user["role"], "Added person", username, f"{name}, {role}")
    return users_list(user)


@app.delete("/api/users/{username}")
def users_remove(username: str, user=Depends(need("supervisor"))):
    if username == user["username"]:
        raise HTTPException(400, "you cannot remove yourself")
    db.ex("DELETE FROM sessions WHERE username=?", (username,))
    db.ex("DELETE FROM copilot_keys WHERE username=?", (username,))
    db.ex("DELETE FROM users WHERE username=?", (username,))
    db.audit(user["username"], user["role"], "Removed person", username)
    return users_list(user)


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
async def extract_post(customer_id: str, use_llm: bool = True, kind: str = "", user=Depends(need("operator"))):
    try:   # kind: read that document again as if just uploaded, so what it gives refreshes the details
        return await extract.run(customer_id, use_llm=use_llm, fresh=kind if kind in ("bill", "aadhaar") else None)
    except Exception as e:
        raise HTTPException(400, str(e))


UPLOAD_KINDS = {"bill", "aadhaar", "passbook", "roof", "ownership", "pan"}


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
    # plain letters and digits: the name goes into a download header, which takes no Hindi or quote marks
    raw = Path(file.filename or "upload.pdf").name
    ext = (Path(raw).suffix.lstrip(".").lower() or "pdf")
    name = f"{kind}_{portal_name(raw, ext if ext.isalnum() and ext.isascii() else 'bin')}"
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
            "vendor_signature": bool(closeout.signature("vendor")), "requests": reqs, "portals": portals(),
            "choices": closeout.CHOICES}


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
    try:
        closeout.save(_cid(cid), body, user["username"])
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    if "module_count" in body:
        field.sync(cid, user["username"])
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
    try:   # drawn on the pad, or a photo cropped in the browser (stored as ink on a see-through background)
        png = drafts.ink_only(closeout.png_from_upload(body["image"])) if body.get("photo") \
            else closeout.png_from_data_url(body.get("image"))
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
             "roof": "Roof photo", "pan": "PAN card (optional)"}


# ------------------------------- AI reading: the key, set in the app -------------------------------
def _setting(name, value):
    """One line of the settings file kept with the data; '' removes it. Takes effect at once."""
    import re as _re
    f = DATA / "solara.env"
    lines = [x for x in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []) if not _re.match(rf"\s*{name}\s*=", x)]
    if value:
        lines.append(f"{name}={value}")
        os.environ[name] = value
    else:
        os.environ.pop(name, None)
    f.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def ai_settings():
    st, keys = extract.llm_status(), extract.gemini_keys()
    return {"on": st["enabled"], "provider": st["provider"], "model": st["model"], "has_key": bool(keys),
            "tail": keys[0][-4:] if keys else "", "aadhaar": extract.aadhaar_to_model()}   # the key itself is never sent back


@app.get("/api/settings/ai")
def ai_get(user=Depends(current)):
    return ai_settings()


@app.post("/api/settings/ai")
async def ai_set(body: dict = Body(...), user=Depends(need("supervisor"))):
    import re as _re, httpx
    key = valid.text(body.get("key"), "key").strip()
    if not _re.fullmatch(r"[A-Za-z0-9_.\-]{20,200}", key):
        raise HTTPException(400, "that does not look like a Gemini API key; copy it again from Google AI Studio")
    if not body.get("unchecked"):   # asked of Google once, so a wrong key is known now and not on a customer's day
        try:
            async with httpx.AsyncClient(timeout=15) as cl:
                r = await cl.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", headers={"x-goog-api-key": key})
        except httpx.HTTPError:
            raise HTTPException(502, "Google could not be reached to check the key. Check the internet and try again")
        if r.status_code != 200:
            raise HTTPException(400, "Google did not accept this key. Copy it again from Google AI Studio")
    _setting("GEMINI_API_KEY", key)
    db.audit(user["username"], user["role"], "AI key set", None, f"Gemini, key ending {key[-4:]}")
    return ai_settings()


@app.delete("/api/settings/ai")
def ai_remove(user=Depends(need("supervisor"))):
    _setting("GEMINI_API_KEY", "")
    db.audit(user["username"], user["role"], "AI key removed", None, "")
    return ai_settings()


def _pre_install():
    return db.q(f"""SELECT id FROM customers WHERE workflow='rooftop_registration' AND stage IN
                    ({",".join("?" * len(registration.PRE_STAGES))}) ORDER BY id DESC""",
                registration.PRE_STAGES)


@app.get("/api/today")
def today_list(user=Depends(current)):
    """One list of what to do now, for every customer: calls, things to do here, things on the portals."""
    rows = db.q(f"""SELECT id FROM customers WHERE stage IN ({",".join("?" * len(CLOSE_STAGES))}) ORDER BY id""", CLOSE_STAGES)
    return {**tracker.today([closeout_summary(r["id"]) for r in rows]), "portals": portals()}


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


@app.get("/api/registration/{cid}/draft/{kind}")
def registration_draft(cid: str, kind: str, fmt: str = "", user=Depends(need("operator"))):
    """The agreement (PDF) or the quotation (Word, or PDF with fmt=pdf), filled into the client's templates."""
    res = _draft(cid, kind, user)
    return _quotation_pdf(res) if kind == "quotation" and fmt == "pdf" else res


def _quotation_pdf(res):
    """The quotation's Word file as a PDF, under the same file name."""
    if res.media_type == "application/pdf":   # this customer's own quotation: a PDF already
        return res
    try:
        blob = drafts.docx_to_pdf(res.body)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    name = (res.headers.get("content-disposition") or "").replace(".docx", ".pdf")
    return Response(blob, media_type="application/pdf", headers={"Content-Disposition": name})


def _draft(cid, kind, user):
    c, d = closeout.data(_cid(cid))
    if not (c["name"] and c["address"]):
        raise HTTPException(400, "the customer's name and address are needed first: upload the bill")
    try:
        if kind == "agreement":
            if not d.get("rts_cost"):
                raise HTTPException(400, "pick the installation cost under Details first: the agreement prints it")
            sig = closeout.signature("consumer_upload", c["id"])
            vsig = closeout.signature("vendor")
            blob = drafts.agreement_pdf(c["name"], c["address"], cost=d["rts_cost"],
                                        sign=vault.read(Path(sig["path"])) if sig else None,
                                        vendor_sign=vault.read(Path(vsig["path"])) if vsig else None)
            ext, mime = "pdf", "application/pdf"
        elif kind == "quotation" and (own := own_quotation(cid)):
            blob, ext, mime = vault.read(Path(own["path"])), "pdf", "application/pdf"   # the one uploaded for this customer
        elif kind == "quotation":
            q = next((q for q in registration.quotes() if d.get("rts_cost") and float(q["amount"]) == float(d["rts_cost"])), None)
            if not q or not q["file"]:
                raise HTTPException(400, "pick the installation cost (one of the quotations) under Details first" if not q else
                                    f"there is no quotation template for Rs {drafts.inr(q['amount'])}: add one in Reports, "
                                    "or upload this customer's own quotation")
            blob = drafts.quotation_docx(registration.quote_file(q), c["name"], c["place"] or d.get("district") or "")
            ext, mime = "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            raise HTTPException(404, "unknown document")
    except (FileNotFoundError, ValueError) as ex:
        raise HTTPException(400, str(ex))
    db.audit(user["username"], user["role"], f"Made the {kind}", cid, "")
    name = f"{kind}_{cid}_{(c['name'] or '').replace(' ', '_')}.{ext}"
    return Response(blob, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------- quotations -------------------------------
# The price list is the quotation templates on file. The owner adds one for a new price (a Word file with the
# "Date :" and "To," lines Solara fills) and it is offered everywhere at once. One customer's own quotation,
# uploaded as a PDF or a Word file, goes to the portal as it is instead. The portal always gets a PDF.
MAX_TEMPLATE = 5 * 1024 * 1024


def own_quotation(cid):
    return db.one("SELECT * FROM documents WHERE customer_id=? AND kind='quotation_own'", (cid,))


def quote_list():
    try:
        agreement = "own" if drafts.own_agreement().exists() else "folder" if drafts.agreement_template() else ""
    except FileNotFoundError:
        agreement = ""
    return {"quotes": registration.quotes(), "can_pdf": drafts.can_pdf(), "agreement": agreement}


@app.post("/api/templates/agreement")
async def agreement_template_upload(file: UploadFile = File(...), user=Depends(need("supervisor"))):
    """The vendor-consumer agreement draft (the MNRE format, a PDF with its blanks) that Solara fills for each customer."""
    blob = await file.read()
    if not blob.startswith(b"%PDF") or len(blob) > MAX_TEMPLATE:
        raise HTTPException(400, "the agreement draft is a PDF of at most 5 MB")
    try:   # filled once with a made-up customer: a draft Solara cannot fill is refused here, with the reason
        drafts.agreement_pdf("Sample Customer", "1 Sample Road, Pune 411001", cost="200000", template=blob)
    except Exception as ex:
        raise HTTPException(400, "Solara could not fill this PDF. It needs the standard draft's blanks: the date after \"executed on\", "
                                 f"the First and Second Party lines, and the Name / Address / Sign / Date table ({type(ex).__name__})")
    p = drafts.own_agreement()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(blob)
    db.audit(user["username"], user["role"], "Agreement draft uploaded", None, f"{len(blob) // 1024} KB")
    return quote_list()


@app.get("/api/quotes")
def quotes_get(user=Depends(current)):
    return quote_list()


@app.post("/api/quotes")
async def quotes_add(amount: str = Form(""), file: UploadFile = File(...), user=Depends(need("supervisor"))):
    import zipfile
    blob = await file.read()
    try:
        amt = valid.amount(amount)
        if not blob.startswith(b"PK"):
            raise ValueError("the template is a Word file (.docx): Solara puts each customer's name, place and the date into it")
        if len(blob) > MAX_TEMPLATE:
            raise ValueError("that file is over 5 MB; save the letterhead picture smaller in Word and send it again")
        drafts.quotation_docx(io.BytesIO(blob), "Sample Customer", "Pune")   # refused here, not on a customer's day
    except (zipfile.BadZipFile, KeyError):
        raise HTTPException(400, "that file could not be opened as a Word document; save it as .docx and send it again")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    have = next((q for q in registration.quotes() if q["amount"] == amt and q["file"]), None)
    if have and not have["own"]:   # the quotations that came with Solara stay as they are: this is for a new price
        raise HTTPException(400, f"Rs {drafts.inr(amt)} already has its quotation. Add a quotation here only for a price that is not in the list")
    replaced = bool(have)
    (registration.OWN_QUOTES() / f"{amt}.docx").write_bytes(blob)
    db.audit(user["username"], user["role"], "Quotation template " + ("replaced" if replaced else "added"), None, f"Rs {drafts.inr(amt)}")
    return quote_list()


@app.delete("/api/quotes/{amount}")
def quotes_remove(amount: str, user=Depends(need("supervisor"))):
    q = next((q for q in registration.quotes() if q["amount"] == amount and q["own"]), None)
    if not q:
        raise HTTPException(404, "that quotation was not added in Solara, so it is not removed here")
    using = [r["customer_id"] for r in db.q("SELECT customer_id, data FROM closeout")
             if json.loads(r["data"]).get("rts_cost") == amount and not json.loads(r["data"]).get("sfr_at")]
    registration.quote_file(q).unlink()
    db.audit(user["username"], user["role"], "Quotation template removed", None, f"Rs {drafts.inr(amount)}")
    return {**quote_list(), "using": using}   # customers still at this price: they need another price or their own file


@app.post("/api/registration/{cid}/quotation")
async def registration_quotation(cid: str, file: UploadFile = File(...), user=Depends(need("operator"))):
    """This customer's own quotation, a PDF or a Word file; kept as the PDF that goes to the portal."""
    cid = _cid(cid)
    blob = await file.read()
    if blob.startswith(b"PK"):
        if len(blob) > MAX_TEMPLATE:
            raise HTTPException(400, "that Word file is over 5 MB")
        try:
            blob = drafts.docx_to_pdf(blob)
        except ValueError as ex:
            raise HTTPException(400, str(ex) + "; or save the quotation as a PDF and upload that")
    if not blob.startswith(b"%PDF"):
        raise HTTPException(400, "send the quotation as a PDF or a Word file (.docx)")
    if len(blob) > PORTAL_MAX:
        try:
            blob = closeout.fit(blob, limit_kb=PORTAL_MAX // 1024)
        except ValueError:
            raise HTTPException(400, f"the quotation is {len(blob) // 1024} KB as a PDF; the portal takes 2 MB at most")
    p = DOCS / cid / "quotation_own.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    size = vault.write(p, blob)
    db.ex("DELETE FROM documents WHERE customer_id=? AND kind='quotation_own'", (cid,))
    db.ex("INSERT INTO documents(customer_id,kind,filename,path,bytes,uploaded_at) VALUES(?,?,?,?,?,?)",
          (cid, "quotation_own", p.name, str(p), size, db.now()))
    db.audit(user["username"], user["role"], "Uploaded the customer's own quotation", cid, f"{size // 1024} KB PDF")
    return registration_get(cid, user)


@app.delete("/api/registration/{cid}/quotation")
def registration_quotation_remove(cid: str, user=Depends(need("operator"))):
    d = own_quotation(_cid(cid))
    if not d:
        raise HTTPException(404, "this customer has no quotation of their own")
    Path(d["path"]).unlink(missing_ok=True)
    db.ex("DELETE FROM documents WHERE customer_id=? AND kind='quotation_own'", (cid,))
    db.audit(user["username"], user["role"], "Removed the customer's own quotation", cid, "")
    return registration_get(cid, user)


@app.post("/api/registration/{cid}/signature")
def registration_signature(cid: str, body: dict = Body(...), user=Depends(need("operator"))):
    """The customer's signature, from a photo cropped in the browser; it goes on the agreement's Sign line."""
    c, _ = closeout.data(_cid(cid))
    try:
        png = drafts.ink_only(closeout.png_from_upload(body.get("image")))   # stored as it will print: ink only
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    closeout.save_signature("consumer_upload", png, c["name"] or "", cid)
    db.audit(user["username"], user["role"], "Added the customer's signature", cid, "photo, cropped")
    return registration_get(cid, user)


@app.delete("/api/customers/{cid}")
def customer_delete(cid: str, user=Depends(need("supervisor"))):
    try:
        registration.delete_customer(_cid(cid), user)
    except KeyError:
        raise HTTPException(404, "unknown customer")
    return {"ok": True}


@app.get("/api/registration/{cid}")
def registration_get(cid: str, user=Depends(current)):
    c, d = closeout.data(_cid(cid))
    sealed = d.pop("aadhaar_enc", None)
    if sealed and ROLES[user["role"]] >= ROLES["operator"]:   # the full Aadhaar number, for the people who file it
        try:
            d["aadhaar_full"] = vault.unseal(sealed)
        except Exception:
            pass
    reqs = db.q("""SELECT status,created_at,signed_at,signer_name FROM sign_requests WHERE customer_id=?
                   AND docs LIKE '%agreement%' ORDER BY created_at DESC LIMIT 3""", (cid,))
    return {"customer": c, "data": d, **registration.status(cid),
            "fields": [{**r, "key": extract.KEY_OF.get(r["field"])} for r in extract.saved(cid)],
            "documents": db.q("""SELECT kind, filename, bytes, uploaded_at FROM documents WHERE
                                 customer_id=? AND kind NOT LIKE 'co_%'""", (cid,)),
            "doc_kinds": DOC_KINDS, "values": registration.values(cid), "portals": portals(),
            "vendor_signature": bool(closeout.signature("vendor")), "requests": reqs,
            "customer_sign": (lambda s: closeout._sig_img(s) if s else None)(closeout.signature("consumer_upload", cid)),
            "vendor_sign": (lambda s: closeout._sig_img(s) if s else None)(closeout.signature("vendor")),
            "agreement": {"draft": closeout.TEMPLATE_DRAFT, "check": closeout.verify_agreement(cid)},
            "suggest": registration.suggest(cid), "llm": extract.llm_status(), "quotes": registration.quotes(),
            "quotation_own": bool(own_quotation(cid)), "can_pdf": drafts.can_pdf(),
            "doc_status": registration.doc_status(cid),
            "otp": registration.heads_up(cid, "approve" if registration.status(cid)["next"]["act"] == "approve" else "register"),
            "districts": valid.MH_DISTRICTS if region()["state"] == "Maharashtra" else []}


async def take_document(cid, kind, file, user):
    """Store one registration document and read it. Used by the dashboard and by the customer's own link."""
    if kind not in DOC_KINDS:
        raise HTTPException(400, "unknown document type")
    await upload_doc(cid, kind, file, user)
    registration.docs_uploaded(cid, user["username"])
    kinds = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    if kinds & {"bill", "aadhaar", "pan"}:
        try:
            await extract.run(cid, fresh=kind)
        except Exception as ex:  # the upload is kept; the person can retry or type the details
            db.audit("agent", "agent", "Document extraction failed", cid, f"{kind}: {type(ex).__name__}")
            return f"The file is saved but could not be read ({type(ex).__name__}). Try Read again or type the details."
    return None


def front_and_back(blobs):
    """The two photos of an Aadhaar (front and back) as one two-page PDF, so the QR and the address on the
    back are read with the name and number on the front."""
    import fitz
    from PIL import Image
    out = fitz.open()
    try:   # each side as it came: a PDF's pages are taken as they are, a photo becomes a page
        for b in blobs:
            if not b.startswith(b"%PDF"):
                buf = io.BytesIO()
                Image.open(io.BytesIO(b)).convert("RGB").save(buf, "PDF", resolution=200)
                b = buf.getvalue()
            with fitz.open(stream=b, filetype="pdf") as side:
                out.insert_pdf(side)
        return out.tobytes(garbage=3, deflate=True)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "send the front and the back as two PDFs, two photos (JPG or PNG), or one PDF with both")


@app.post("/api/registration/{cid}/document")
async def registration_document(cid: str, kind: str, file: list[UploadFile] = File(...),
                                user=Depends(need("operator"))):
    if len(file) > 2 or (len(file) == 2 and kind != "aadhaar"):
        raise HTTPException(400, "one file per document; the Aadhaar takes two photos (front and back)")
    if len(file) == 2:
        pdf = front_and_back([await f.read() for f in file])
        file = [StarletteUploadFile(io.BytesIO(pdf), filename="front_back.pdf", size=len(pdf))]
    problem = await take_document(_cid(cid), kind, file[0], user)
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


@app.post("/api/registration/{cid}/locate")
def registration_locate(cid: str, force: bool = False, user=Depends(need("operator"))):
    """Latitude, longitude and urban/rural from the address, through OpenStreetMap."""
    hit = registration.locate(_cid(cid), user, force)
    if not hit:
        raise HTTPException(404, "the map service found no place for this address; type the latitude and longitude")
    db.audit(user["username"], user["role"], "Found the premises on the map", cid, hit["accuracy"])
    return {**hit, "registration": registration_get(cid, user)}


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
    user = db.one("SELECT username,name,role FROM users WHERE username=?", (row["username"],))
    if not user:  # the person was removed: their key goes with them
        raise HTTPException(401, "co-pilot key not recognised; create a new one in Solara")
    if ROLES[user["role"]] < ROLES["operator"]:
        raise HTTPException(403, "the Chrome helper needs the operator role")
    return user


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
    """Who the helper offers under "who are you filling for": every customer, on every portal. The owner fills
    the customer's own login and loan forms on their behalf, so anyone may be picked at any time. The ones this
    page is the next step for come first ("here")."""
    first = []
    if step in PICK:
        for r in filing.listing():
            if r["next"]["act"] in PICK[step] and not r["paused"]:
                first.append(r["id"])
    else:
        for r in _pre_install():
            c = db.one("SELECT consumer_no, application_no FROM customers WHERE id=?", (r["id"],))
            if c["consumer_no"] and not c["application_no"]:
                first.append(r["id"])
    rows = {r["id"]: r for r in db.q("SELECT id, name, consumer_no, application_no FROM customers")}
    rest = sorted((i for i in rows if i not in first), reverse=True)   # the newest first
    return [{"id": i, "name": rows[i]["name"], "consumer_no": rows[i]["consumer_no"] or "", "here": i in first,
             "application_no": rows[i]["application_no"] or ""}
            for i in [x for x in first if x in rows] + rest]


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
    if not closeout.data(cid)[1].get("lat"):   # the portal asks for the position: find it once, keep it
        try:
            registration.locate(cid, {"username": user["username"]})
        except Exception:
            pass   # no map answer: the co-pilot asks the operator instead
    cust, d = closeout.data(cid)
    made = closeout.built(cid)
    fields = [("Consumer name", cust["aadhaar_name"] or cust["name"]), ("Consumer number", cust["consumer_no"]),
              ("Address", cust["address"]), ("PIN code", cust["pin"]),
              ("Capacity (kWp)", closeout.capacity(d))]
    fields += [(lbl, d.get(k)) for k, lbl, _ in closeout.FIELDS if d.get(k)]
    issues = registration.validate(cid)["issues"]
    # A value Solara itself knows is wrong (a mobile of which the bill shows only part, a PIN that is not six digits) is
    # not handed to the helper: it would be typed into the portal. The helper asks the owner for the right one instead.
    wrong = {{"mobile": "mobile", "PIN code": "pin"}.get(i["field"]) for i in issues if i["kind"] == "invalid"}
    return {"customer_id": cid, "name": cust["name"], "application_no": cust["application_no"],
            "files": [{"key": s["key"], "slot": s["slot"], "title": s["title"], "bytes": made[s["key"]]}
                      for s in st if s["key"] in made],
            "not_ready": [{"title": s["title"], "note": s["note"]} for s in st
                          if s["slot"] and s["key"] not in made],
            "fields": [{"label": k, "value": str(v)} for k, v in fields if v not in (None, "")],
            "values": {k: v for k, v in {**registration.values(cid), "place": cust["place"],
                                         "aadhaar": _aadhaar_full(d)}.items() if v and k not in wrong},
            "issues": issues, "build_error": build_error,
            "derived": registration.derived(cid),
            "cost_options": [q["amount"] for q in registration.quotes()],
            "agreement_draft": closeout.TEMPLATE_DRAFT,
            "docs": [r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=? AND "
                                             "kind IN ('bill','aadhaar','passbook','roof','pan')", (cid,))]
                    + (["site_photo"] if (DOCS / cid / "site_photo.jpg").exists() else []),
            "paused": {"by": d.get("paused_by"), "reason": d.get("paused_reason")} if d.get("paused_at") else None,
            "approvals": {k: filing.review(cid, k)["approval"] for k in filing.FORMS},
            "done": {k: bool(d.get(v)) for k, v in (("sfr", "sfr_at"), ("loan", "loan_at"), ("installation", "installation_at"),
                                                  ("dcr", "dcr_cert_no"), ("agreement_uploaded", "agreement_uploaded_at"),
                                                  ("customer_approved", "agreement_approved_at"))}}


def _aadhaar_full(d):
    """The customer's Aadhaar number as Solara keeps it (encrypted), for the helper to type on the portal."""
    try:
        n = vault.unseal(d["aadhaar_enc"]) if d.get("aadhaar_enc") else None
    except Exception:
        return None
    return n if n and n[-4:] == str(d.get("aadhaar_last4") or "") else None   # a replaced card: its old number is not filed


def portal_name(name, ext):
    """Letters, digits and underscores, one extension: what the national portal accepts as a file name."""
    import re as _re
    stem = _re.sub(r"[^A-Za-z0-9]+", "_", name.rsplit(".", 1)[0]).strip("_")[:60] or "document"
    return f"{stem}.{ext}"


def fit_box(blob, as_pdf, max_kb):
    """A file as one portal box takes it: PDF or JPEG, within that box's size (KB, 0 = the usual limits)."""
    import io
    from PIL import Image
    if blob.startswith(b"%PDF"):
        limit = max_kb * 1024 if max_kb else PORTAL_MAX
        if len(blob) > limit:  # re-rendered smaller first; refused only if it still does not fit
            try:
                blob = closeout.fit(blob, limit_kb=limit // 1024)
            except ValueError:
                pass
        if len(blob) > limit:
            raise HTTPException(413, f"the PDF is {len(blob) // 1024} KB; this box takes {limit // 1024} KB at most. Upload a smaller copy in Solara")
        return blob, "application/pdf", "pdf"
    # JPEG under 300 KB unless the box says less: the strictest photo box seen (MSEDCL, the feasibility report's photo)
    kb = min(max_kb or 300, 300) if not as_pdf else max(40, (max_kb or 300) - 20)
    jpg = closeout.jpeg_under(Image.open(io.BytesIO(blob)), kb=kb)
    if not as_pdf:
        return jpg, "image/jpeg", "jpg"
    for k in (kb, kb * 3 // 4, kb // 2, kb // 3):  # a box that takes PDF only (the 2024 plant photo box): one page
        out = io.BytesIO()
        Image.open(io.BytesIO(jpg)).save(out, "PDF", resolution=150)
        if not max_kb or out.tell() <= max_kb * 1024:
            return out.getvalue(), "application/pdf", "pdf"
        jpg = closeout.jpeg_under(Image.open(io.BytesIO(blob)), kb=max(30, k))
    raise HTTPException(413, f"the photo does not fit this box's {max_kb} KB as a PDF; attach it by hand")


@app.get("/api/copilot/doc/{cid}/{kind}")
def copilot_doc(cid: str, kind: str, user=Depends(copilot_user), to: str = "", max_kb: int = 0):
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
    blob, name = vault.read(Path(d["path"])), d["filename"]
    before = len(blob)
    try:
        blob, kind_type, ext = fit_box(blob, to == "pdf", max(0, min(max_kb, 5120)))
    except HTTPException as ex:
        raise HTTPException(ex.status_code, f"{kind}: {ex.detail}")
    except Exception:
        raise HTTPException(415, f"the {kind} file is neither a PDF nor a photo Solara can read; upload it again in Solara")
    name = portal_name(name, ext)
    db.audit(user["username"], user["role"], "Co-pilot fetched document", cid, kind)
    if len(blob) != before:
        db.audit(user["username"], user["role"], "File made smaller for the portal", cid, f"{kind}: {before // 1024} KB to {len(blob) // 1024} KB")
    return Response(blob, media_type=kind_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


PORTAL_MAX = 2 * 1024 * 1024  # the portal's limit on the bill, passbook and agreement boxes (seen 7 Nov 2026)


def portal_jpeg(blob, name, limit):
    """A photo as the portal accepts it: JPEG (it refuses PNG on some boxes), within the size limit."""
    import io
    from PIL import Image
    if blob.startswith(b"\xff\xd8") and len(blob) <= limit:
        return blob, name, "image/jpeg"
    im = Image.open(io.BytesIO(blob)).convert("RGB")
    for side, q in ((3000, 85), (2400, 80), (1800, 75), (1400, 70), (1000, 65)):
        im.thumbnail((side, side))
        out = io.BytesIO(); im.save(out, "JPEG", quality=q, optimize=True)
        if out.tell() <= limit:
            break
    stem = name.rsplit(".", 1)[0]
    return out.getvalue(), stem + ".jpg", "image/jpeg"


@app.get("/api/copilot/draft/{cid}/{kind}")
def copilot_draft(cid: str, kind: str, fmt: str = "", user=Depends(copilot_user)):
    """The same two documents, for the portal's upload boxes. fmt=pdf turns the quotation into a PDF (the site
    feasibility form takes PDF only, 2 MB at most)."""
    res = _draft(cid, kind, user)
    if kind == "quotation" and fmt == "pdf":
        res = _quotation_pdf(res)
        if len(res.body) > PORTAL_MAX:
            raise HTTPException(413, f"the quotation PDF is {len(res.body) // 1024} KB; the portal takes 2 MB at most")
    return res


@app.get("/api/copilot/file/{cid}/{key}")
def copilot_file(cid: str, key: str, user=Depends(copilot_user), max_kb: int = 0):
    if key not in closeout.SPEC or key not in closeout.built(_cid(cid)):
        raise HTTPException(404, "not generated yet")
    blob = vault.read(closeout.path_for(cid, key))
    before = len(blob)
    blob, _, _ = fit_box(blob, True, max(0, min(max_kb, 5120)))
    db.audit(user["username"], user["role"], "Co-pilot fetched document", cid, key)
    if len(blob) != before:
        db.audit(user["username"], user["role"], "File made smaller for the portal", cid, f"{key}: {before // 1024} KB to {len(blob) // 1024} KB")
    return Response(blob, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{portal_name(cid + "_" + key, "pdf")}"'})


def receipt_sized(pdf):
    """Small when it can be; a receipt is never uploaded anywhere, so a long one is kept whole."""
    try:
        return closeout.fit(pdf)
    except ValueError:
        return pdf


async def save_receipt(cid, step, snapshot, url, user):
    """Keep what the portal showed when the owner marked a filing done, as a PDF in the customer's file."""
    if not snapshot:
        return None
    pdf = receipt_sized(await exports.html_pdf(exports.receipt_html(snapshot, filing.STEP_LABEL.get(step, step), cid, url)))
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


PROBLEMS = {"otp_wrong": "Co-pilot: wrong OTP", "otp_resend": "Co-pilot: OTP resend",
            "session": "Co-pilot: portal session ended", "offline": "Co-pilot: internet off"}


@app.post("/api/copilot/report")
async def copilot_report(body: dict = Body(...), user=Depends(copilot_user)):
    if body.get("event") == "page_layout":
        return registration.save_layout(body, user)
    if body.get("event") == "portal_list":
        rows = body.get("rows") or []
        out = registration.from_portal_list(rows, str(body.get("page", ""))[:80], user)
        # the same rows place each customer on the board's ten stages
        tracker.capture("pmsg", [{"ref": r.get("app_no"), "status": r.get("status")} for r in rows if isinstance(r, dict) and r.get("status")], user)
        return out
    if body.get("event") == "problem" and not body.get("customer_id"):
        what = PROBLEMS.get(body.get("kind"))
        if not what:
            raise HTTPException(400, "unknown problem")
        db.audit(user["username"], user["role"], what, "", str(body.get("page", ""))[:80])
        return {"ok": True}
    cid = _cid(body.get("customer_id", ""))
    uploaded = set(body.get("uploaded") or [])
    msedcl_keys = {s[0] for s in closeout.DOCS_SPEC if s[1]}
    if body.get("event") == "detail":   # a value the owner typed in the co-pilot because Solara had none
        col = {"capacity": "kw", "rts_cost": "rts_cost", "mobile": "mobile", "email": "email",
               "consumer_no": "consumer_no", "district": "district", "name": "name"}.get(valid.text(body.get("key"), "key"))
        if not col:
            return {"ok": True, "saved": False}   # filled on the page only (a state, a PIN... the record keeps its own)
        try:
            registration.save_details(cid, {col: body.get("value")}, user)
        except ValueError as ex:
            raise HTTPException(400, str(ex))
        return {"ok": True, "saved": True}
    ev = body.get("event")
    if ev in ("app_no", "agreement_uploaded", "customer_approved"):
        c = db.one("SELECT application_no FROM customers WHERE id=?", (cid,))
        if ev == "app_no" and c["application_no"] == (body.get("app_no") or "").upper():
            return {"ok": True, "already": True}
        step = {"app_no": "registered"}.get(body["event"], body["event"])
        try:
            registration.mark(cid, step, user, body.get("app_no"), from_portal=ev == "app_no")
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
    if ev == "problem":
        # the co-pilot met one of the problem cases on a portal page and told the owner what to do
        what = PROBLEMS.get(body.get("kind"))
        if not what:
            raise HTTPException(400, "unknown problem")
        page = str(body.get("page", ""))[:80]
        recent = db.one("SELECT 1 FROM audit WHERE action=? AND target=? AND detail=? AND ts>?",
                        (what, cid, page, (datetime.now() - timedelta(minutes=2)).isoformat(timespec="seconds")))
        if not recent:
            db.audit(user["username"], user["role"], what, cid, page)
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
    rows = body.get("rows") or []
    out = tracker.capture(portal, rows, user)
    if portal == "pmsg":  # the same list moves registration on: agreement uploaded, customer approved
        out["steps"] = registration.from_portal_list([{"app_no": r.get("ref"), "status": r.get("status")} for r in rows if isinstance(r, dict)],
                                                     str(body.get("page", ""))[:80], user)
    return out


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
    if "module_count" in vals:  # serials already confirmed may now be all of them
        field.sync(cid, user["username"])
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
    url = config_public_url(request, f"/field/{token}")
    return {"url": url, "local": is_local(url), **field.share(cid, url)}


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
        pdf = receipt_sized(blob)
    else:
        import io
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(blob)).convert("RGB")
        except Exception:
            raise HTTPException(400, "upload a PDF or a screenshot")
        buf = io.BytesIO()
        im.save(buf, "PDF", resolution=110)
        pdf = receipt_sized(buf.getvalue())
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


@app.get("/api/exports/everything.zip")
def export_everything(user=Depends(need("supervisor"))):
    from starlette.background import BackgroundTask
    p = exports.everything_zip()
    db.audit(user["username"], user["role"], "Exported all data", "", p.name)
    return FileResponse(p, filename=p.name, media_type="application/zip", background=BackgroundTask(p.unlink, missing_ok=True))


@app.get("/api/exports/month.pdf")
async def month_pdf(month: str = "", user=Depends(current)):
    p = await exports.month_pdf(_month(month))
    db.audit(user["username"], user["role"], "Exported monthly report", "", p.name)
    return FileResponse(p, filename=p.name, media_type="application/pdf")


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
@app.post("/api/backup/verify")
def backup_verify(user=Depends(need("supervisor"))):
    """The restore drill on the newest backup (made now if there is none): opened on the side, checked, thrown away."""
    p = upkeep.latest() or backup.create()
    r = upkeep.verify(p)
    db.audit(user["username"], user["role"], "Restore drill " + ("PASSED" if r["ok"] else "FAILED"), "",
             f"{r['file']}: database {r.get('integrity')}, {r.get('customers')} customers, document {r.get('document')}")
    return r


@app.get("/api/kpi")
def kpi_report(user=Depends(current)):
    return kpi.summary()


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
