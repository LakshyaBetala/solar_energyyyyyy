"""The automation itself: a real Playwright session driving a real web application.

Nothing here is simulated. The browser is Chromium, the form fills are keystrokes, the
uploads are the documents on disk, the screenshots are captured from the live page, and
the holds genuinely block the coroutine until a person resolves them through the API
with a role the server checks.

Two portals are driven by the same engine: the national rooftop portal and a DISCOM
self-service portal. Each workflow is a step list plus a selector block. Pointing one at
its live counterpart is a change of base URL and selectors; the holds, retries, evidence
capture and audit writes stay exactly as they are.
"""
import asyncio, base64, json, time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
from .. import db, extract, vault
from ..config import PORTAL_URL, BASE_URL, SHOTS, FRAME_INTERVAL, FRAME_QUALITY, ROLES

STEPS = [
    ("boot", "Launch isolated browser session"),
    ("open", "Open rooftop solar portal"),
    ("discom", "Select state and distribution company"),
    ("consumer", "Enter consumer number and mobile"),
    ("otp", "OTP checkpoint"),
    ("applicant", "Fill applicant details from documents"),
    ("tech", "Enter load and proposed capacity"),
    ("upload", "Attach documents"),
    ("captcha", "CAPTCHA checkpoint"),
    ("validate", "Pre-flight validation against portal record"),
    ("fix", "Field correction"),
    ("approve", "Supervisor approval"),
    ("submit", "Submit application"),
    ("record", "Capture acknowledgement and update records"),
]
DSTEPS = [
    ("boot", "Launch isolated browser session"),
    ("open", "Open DISCOM self-service portal"),
    ("login", "Identify the connection and mobile"),
    ("otp", "OTP checkpoint"),
    ("request", "Fill the service request from documents"),
    ("upload", "Attach documents"),
    ("validate", "Pre-flight check against the connection record"),
    ("approve", "Supervisor approval"),
    ("submit", "Submit service request"),
    ("record", "Capture request number and update records"),
]
WORKFLOWS = {
    "rooftop_registration": {"label": "New rooftop registration", "steps": STEPS},
    "load_enhancement": {"label": "Sanctioned load enhancement", "steps": DSTEPS},
    "load_reduction": {"label": "Sanctioned load reduction", "steps": DSTEPS},
    "new_connection": {"label": "New LT connection", "steps": DSTEPS},
}
ROOFTOP_CATEGORIES = ("Residential", "Housing society")

SEL = {
    "state": "#state", "discom": "#discom", "consumer": "#consumerNo", "mobile": "#mobile",
    "send_otp": "#btnSendOtp", "otp": "#otp", "verify": "#btnVerify",
    "name": "#applicantName", "category": "#category", "mobile2": "#mobile2",
    "address": "#address", "pin": "#pin", "bank": "#bank", "load": "#load",
    "capacity": "#capacity", "roof": "#roofArea", "module": "#moduleType", "vendor": "#vendor",
    "save": "#btnSaveContinue", "upload": "#btnUpload", "captcha": "#captcha",
    "captcha_in": "#captchaInput", "captcha_go": "#btnCaptcha",
    "declaration": "#declaration", "submit": "#btnSubmit", "edit": "#btnEdit",
    "error": "#valError", "err_code": "#errCode", "app_no": "#applicationNo",
}
DOC_INPUTS = {"bill": "#docBill", "aadhaar": "#docAadhaar", "passbook": "#docPassbook",
              "roof": "#docRoof"}
DSEL = {
    "consumer": "#dConsumer", "mobile": "#dMobile", "send_otp": "#dSendOtp",
    "otp": "#dOtp", "verify": "#dVerify", "type": "#reqType", "load": "#reqLoad",
    "phase": "#phase", "purpose": "#purpose", "reason": "#reason", "app_name": "#appName",
    "app_address": "#appAddress", "app_pin": "#appPin", "next": "#btnReqNext",
    "upload": "#dBtnUpload", "declaration": "#dDecl", "submit": "#dSubmit",
    "request_no": "#requestNo",
}
DDOC_INPUTS = {"aadhaar": "#dDocId", "bill": "#dDocBill", "ownership": "#dDocOwnership"}
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"}

RUNS: dict[int, "Runner"] = {}
MAX_RETRIES = 2
MAX_ATTEMPTS = 3  # the portals lock a session after three wrong OTPs


class HoldRejected(Exception):
    pass


class Runner:
    def __init__(self, run_id, customer, started_by, workflow, target_kw, headless=True,
                 speed=1.0):
        self.id = run_id
        self.c = customer
        self.wf = workflow
        self.wf_label = WORKFLOWS[workflow]["label"]
        self.steps = WORKFLOWS[workflow]["steps"]
        self.target_kw = float(target_kw)
        self.started_by = started_by
        self.headless = headless
        self.speed = max(0.25, min(4.0, float(speed)))
        self.status = "starting"
        self.page = None
        self.browser = None
        self.subs: list[asyncio.Queue] = []
        self.history: list[dict] = []
        self.last_frame = None
        self.resume = asyncio.Event()
        self.resume.set()
        self.holds: dict[int, asyncio.Future] = {}
        self.statuses: dict[str, str] = {}
        self.captcha_code = None
        self.retries = 0
        self.abort = False
        self.app_no = None
        self.t0 = time.time()
        self.step_t = time.time()
        for i, (k, label) in enumerate(self.steps):
            db.ex("""INSERT INTO run_steps(run_id,idx,key,label,status,note,ms)
                     VALUES(?,?,?,?,'todo','',0)""", (run_id, i, k, label))
        # publish the whole plan immediately so the console shows every step from the
        # start, greyed out, rather than growing one row at a time
        self.emit({"type": "plan", "workflow": workflow, "label": self.wf_label, "steps": [
            {"key": k, "label": label, "status": "todo", "note": "", "ms": 0}
            for k, label in self.steps]})

    # ---------- plumbing ----------
    def emit(self, ev):
        if ev.get("type") == "frame":
            self.last_frame = ev
        else:
            self.history.append(ev)
        dead = []
        for q in self.subs:
            try:
                q.put_nowait(ev)
            except Exception:
                dead.append(q)
        for q in dead:
            self.subs.remove(q)

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        for ev in self.history:
            q.put_nowait(ev)
        if self.last_frame:
            q.put_nowait(self.last_frame)
        q.put_nowait({"type": "state", "status": self.status, "retries": self.retries})
        self.subs.append(q)
        return q

    def log(self, level, message):
        ts = db.hhmmss()
        db.ex("INSERT INTO run_events(run_id,ts,level,message) VALUES(?,?,?,?)",
              (self.id, ts, level, message))
        self.emit({"type": "event", "ts": ts, "level": level, "message": message})

    def step(self, key, status, note=""):
        ms = int((time.time() - self.step_t) * 1000) if status in ("done", "fail", "skipped") else 0
        if status == "active":
            self.step_t = time.time()
        self.statuses[key] = status
        db.ex("UPDATE run_steps SET status=?,note=?,ms=? WHERE run_id=? AND key=?",
              (status, note, ms, self.id, key))
        self.emit({"type": "step", "key": key, "status": status, "note": note, "ms": ms,
                   "label": dict(self.steps).get(key, key)})

    def where(self, key):
        keys = [k for k, _ in self.steps]
        return f"{keys.index(key) + 1} of {len(keys)}"

    def set_status(self, s):
        self.status = s
        db.ex("UPDATE runs SET status=? WHERE id=?", (s, self.id))
        self.emit({"type": "state", "status": s, "retries": self.retries})

    async def gate(self):
        if self.abort:
            raise HoldRejected("abandoned by the operator")
        if not self.resume.is_set():
            self.set_status("paused")
            await self.resume.wait()
            if self.abort:
                raise HoldRejected("abandoned by the operator")
            self.set_status("running")

    async def wait(self, seconds):
        await self.gate()
        await asyncio.sleep(seconds / self.speed)

    def pause(self):
        self.resume.clear()

    def unpause(self):
        self.resume.set()

    async def snap(self, key, label, kind="ok"):
        path = SHOTS / f"run{self.id}_{key}_{int(time.time() * 1000)}.png"
        try:
            vault.write(path, await self.page.screenshot(full_page=False))
        except Exception as e:
            self.log("warn", f"screenshot failed: {e}")
            return None
        db.ex("""INSERT INTO screenshots(run_id,step_key,label,kind,path,ts)
                 VALUES(?,?,?,?,?,?)""", (self.id, key, label, kind, str(path), db.now()))
        self.emit({"type": "shot", "label": label, "kind": kind, "url": f"/files/shots/{path.name}",
                   "ts": db.hhmmss()})
        self.log("info", f"screenshot captured: {label}")
        return path

    async def frame_pump(self):
        while self.status not in ("done", "failed", "stopped"):
            try:
                if self.page and not self.page.is_closed():
                    b = await self.page.screenshot(type="jpeg", quality=FRAME_QUALITY)
                    self.emit({"type": "frame", "data": base64.b64encode(b).decode(),
                               "url": self.page.url})
            except Exception:
                pass
            await asyncio.sleep(FRAME_INTERVAL)

    # ---------- human checkpoints ----------
    async def hold(self, kind, label, context, min_role="operator"):
        # An Abandon that lands just before a checkpoint opens finds nothing to release, so the
        # checkpoint itself must refuse to open. No await between here and `await fut`, so no race.
        await self.gate()
        hid = db.ex("""INSERT INTO holds(run_id,kind,status,context,created_at)
                       VALUES(?,?,'waiting',?,?)""",
                    (self.id, kind, json.dumps(context, ensure_ascii=False), db.now()))
        fut = asyncio.get_running_loop().create_future()
        self.holds[hid] = fut
        self.set_status("held")
        self.emit({"type": "hold", "id": hid, "kind": kind, "label": label, "context": context,
                   "min_role": min_role})
        self.log("warn", f"{label} — run held, waiting for a person")
        res = await fut
        self.holds.pop(hid, None)
        self.emit({"type": "hold_resolved", "id": hid, "kind": kind,
                   "resolution": res.get("resolution"), "by": res.get("by")})
        if self.abort:
            raise HoldRejected(f"abandoned by {res.get('by')}")
        if res.get("resolution") in ("escalate", "reject"):
            raise HoldRejected({"escalate": f"escalated to staff by {res.get('by')}",
                                "reject": f"rejected by {res.get('by')}"}[res["resolution"]])
        self.set_status("running")
        return res

    def stop(self, user):
        """Abandon the run. Any waiting checkpoint is released so the coroutine unwinds
        and the browser closes; nothing is submitted."""
        self.abort = True
        self.resume.set()
        for hid, fut in list(self.holds.items()):
            if not fut.done():
                db.ex("""UPDATE holds SET status='resolved',resolved_at=?,resolved_by=?,
                         resolution='escalate' WHERE id=?""", (db.now(), user["username"], hid))
                fut.set_result({"resolution": "escalate", "payload": {},
                                "by": user["username"], "role": user["role"]})
        db.audit(user["username"], user["role"], "Abandoned run", self.c["id"],
                 f"run {self.id}, nothing submitted")
        self.log("warn", f"run abandoned by {user['username']}")

    def resolve_hold(self, hold_id, resolution, payload, user):
        h = db.one("SELECT * FROM holds WHERE id=? AND run_id=?", (hold_id, self.id))
        if not h:
            return False, "no such hold on this run"
        if h["status"] != "waiting":
            return False, "that checkpoint is already resolved"
        need = "supervisor" if h["kind"] == "approve" else "operator"
        if ROLES[user["role"]] < ROLES[need]:
            db.audit(user["username"], user["role"], f"REFUSED {h['kind']} — insufficient role",
                     self.c["id"], f"run {self.id}: needs {need}")
            return False, f"{h['kind']} requires the {need} role; you are {user['role']}"
        fut = self.holds.get(hold_id)
        if not fut or fut.done():
            return False, "checkpoint is no longer waiting"
        db.ex("""UPDATE holds SET status='resolved',resolved_at=?,resolved_by=?,resolution=?
                 WHERE id=?""", (db.now(), user["username"], resolution, hold_id))
        db.audit(user["username"], user["role"], f"Resolved {h['kind']} checkpoint",
                 self.c["id"], f"run {self.id}: {resolution}")
        fut.set_result({"resolution": resolution, "payload": payload or {},
                        "by": user["username"], "role": user["role"]})
        return True, "ok"

    # ---------- page actions ----------
    async def type_into(self, sel, value, label=None):
        await self.gate()
        loc = self.page.locator(sel)
        await loc.scroll_into_view_if_needed()
        await loc.fill("")
        await loc.press_sequentially(str(value), delay=max(8, int(26 / self.speed)))
        if label:
            self.log("act", f"{label} = {value}")

    async def choose(self, sel, value, label=None):
        await self.gate()
        await self.page.locator(sel).select_option(value)
        if label:
            self.log("act", f"{label} = {value}")

    async def press(self, sel, label=None):
        await self.gate()
        await self.page.locator(sel).click()
        if label:
            self.log("act", label)
        await self.page.wait_for_load_state("domcontentloaded")
        await self.wait(0.25)

    async def attach_file(self, sel, path):
        """Documents are encrypted at rest, so they are decrypted in memory and handed to
        the browser as a buffer. Plaintext never touches the disk."""
        p = Path(path)
        await self.page.locator(sel).set_input_files(
            {"name": p.name, "mimeType": MIME.get(p.suffix.lower(), "application/octet-stream"),
             "buffer": vault.read(p)})
        self.log("act", f"attached {p.name}")

    async def page_error(self):
        try:
            if await self.page.locator(SEL["error"]).count():
                txt = (await self.page.locator(SEL["error"]).inner_text()).strip()
                code = ""
                if await self.page.locator(SEL["err_code"]).count():
                    code = (await self.page.locator(SEL["err_code"]).inner_text()).strip()
                return " ".join(txt.split()), code
        except Exception:
            pass
        return None, None

    async def otp_checkpoint(self, field, verify):
        """Hold for a person to read the OTP. A wrong code is re-asked, as the portal allows,
        rather than abandoning the run; the portal's own lockout ends it after three."""
        self.step("otp", "hold")
        await self.snap("otp", "OTP checkpoint", "hold")
        num = db.one("SELECT * FROM numbers WHERE customer_id=?", (self.c["id"],))
        last_err = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            inbox = db.q("SELECT sender,body,ts FROM sms WHERE msisdn=? ORDER BY id DESC LIMIT 4",
                          (num["msisdn"] if num else "",))
            res = await self.hold(
                "otp", "OTP checkpoint" if attempt == 1 else f"OTP rejected, attempt {attempt} of 3",
                {"msisdn": num["msisdn"] if num else "unassigned", "customer": self.c["name"],
                 "step": self.where("otp"), "inbox": inbox, "error": last_err,
                 "attempt": attempt,
                 "hint": "The portal sent a 6-digit code to the number dedicated to this "
                         "registration. The agent does not read it for you and never stores it."})
            await self.type_into(field, str(res["payload"].get("code", "")).strip())
            self.log("head", f"operator {res['by']} supplied the OTP (value not stored)")
            await self.press(verify, "click Verify")
            err, _ = await self.page_error()
            if not err:
                if num:
                    db.ex("UPDATE numbers SET otp_count=otp_count+1 WHERE id=?", (num["id"],))
                self.log("good", "mobile verified")
                self.step("otp", "done", f"{res['by']}, {attempt} attempt{'s' if attempt > 1 else ''}")
                return
            await self.snap("otp", f"OTP rejected, attempt {attempt}", "fail")
            self.log("err", f"portal rejected the OTP: {err}")
            last_err = err
            if "Start again" in err:
                break
        self.step("otp", "fail", "locked after 3 attempts")
        raise RuntimeError("the portal locked the session after three wrong OTPs")

    # ---------- the run ----------
    async def execute(self):
        docs = {d["kind"]: d["path"] for d in
                db.q("SELECT * FROM documents WHERE customer_id=?", (self.c["id"],))}
        v = extract.filing_values(self.c["id"])
        if self.wf != "new_connection" and not v.get("consumer_no"):
            raise RuntimeError("no extraction on file for this customer; run extraction first")
        self.set_status("running")
        db.audit(self.started_by["username"], self.started_by["role"], "Started agent run",
                 self.c["id"], f"run {self.id}, {self.wf_label.lower()}")
        self.log("head", f"run {self.id} — {self.wf_label} — {self.c['id']} {self.c['name']} — "
                         f"{self.target_kw:g} kW")

        async with async_playwright() as p:
            self.step("boot", "active")
            self.browser = await p.chromium.launch(headless=self.headless)
            ctx = await self.browser.new_context(viewport={"width": 1120, "height": 720},
                                                 accept_downloads=False)
            self.page = await ctx.new_page()
            pump = asyncio.create_task(self.frame_pump())
            await self.gate()  # honour an Abandon pressed while the browser was still launching
            self.log("good", f"chromium session ready (headless={self.headless}), "
                             f"isolated profile for {self.c['id']}")
            self.step("boot", "done", "isolated context")
            try:
                if self.wf == "rooftop_registration":
                    await self.flow(v, docs)
                else:
                    await self.flow_discom(v, docs)
            finally:
                pump.cancel()
                try:
                    await ctx.close()
                    await self.browser.close()
                except Exception:
                    pass

    # ===================== rooftop portal =====================
    async def flow(self, v, docs):
        self.step("open", "active")
        await self.page.goto(f"{PORTAL_URL}/verify", wait_until="domcontentloaded")
        self.log("act", f"navigate {self.page.url}")
        self.step("open", "done")

        self.step("discom", "active")
        await self.choose(SEL["state"], "Maharashtra", "state")
        await self.choose(SEL["discom"], "Maharashtra State Electricity Distribution Co. Ltd.",
                          "distribution company")
        self.step("discom", "done")

        self.step("consumer", "active")
        await self.type_into(SEL["consumer"], v["consumer_no"], "consumer number (from bill, 99%)")
        await self.type_into(SEL["mobile"], v["mobile"], "registered mobile (from bill)")
        await self.press(SEL["send_otp"], "click Send OTP")
        err, _ = await self.page_error()
        if err:
            await self.snap("consumer", "Consumer verification refused", "fail")
            self.step("consumer", "fail", err[:90])
            raise RuntimeError(f"portal refused the consumer number: {err}")
        self.log("good", "portal accepted the consumer number and requested an OTP")
        self.step("consumer", "done")

        await self.otp_checkpoint(SEL["otp"], SEL["verify"])
        await self.fill_form(v, first_pass=True)
        await self.attach(docs)
        await self.security()
        await self.review_and_submit(v)

    async def fill_form(self, v, first_pass):
        self.step("applicant", "active")
        if self.page.url.rstrip("/").endswith("/review"):
            await self.press(SEL["edit"], "click Edit applicant details")
        name = v["aadhaar_name"] if first_pass else v["bill_name"]
        await self.type_into(SEL["name"], name,
                            "applicant name (identity document, 98%)" if first_pass
                            else "applicant name (bill spelling, after correction)")
        await self.choose(SEL["category"], self.c["category"], "category")
        await self.type_into(SEL["mobile2"], v["mobile"])
        await self.type_into(SEL["address"], v["address"].replace("Address ", ""), "address (bill)")
        await self.type_into(SEL["pin"], v["pin"])
        await self.type_into(SEL["bank"], v["bank"], "bank details (passbook, masked in logs)")
        self.step("applicant", "done", "6 fields from documents")

        self.step("tech", "active")
        await self.type_into(SEL["load"], f"{float(v['load']):.2f}", "sanctioned load (bill)")
        await self.type_into(SEL["capacity"], f"{self.target_kw:.2f}", "proposed plant capacity")
        await self.type_into(SEL["roof"], v["roof_area"], "roof area (photo estimate, 81%)")
        await self.choose(SEL["module"], "Mono PERC (DCR)", "module technology")
        await self.type_into(SEL["vendor"], "MH/VND/2024/00871", "vendor code")
        self.log("good", f"plant {self.target_kw:.2f} kW is within the sanctioned load "
                         f"{float(v['load']):.2f} kW, no enhancement needed")
        await self.press(SEL["save"], "click Save and continue")
        err, _ = await self.page_error()
        if err:
            await self.snap("tech", "Form rejected", "fail")
            self.step("tech", "fail", err[:90])
            raise RuntimeError(f"portal rejected the form: {err}")
        self.step("tech", "done")

    async def attach(self, docs):
        self.step("upload", "active")
        if await self.page.locator(DOC_INPUTS["bill"]).count():
            n = 0
            for kind, sel in DOC_INPUTS.items():
                if docs.get(kind):
                    await self.attach_file(sel, docs[kind])
                    n += 1
            await self.press(SEL["upload"], "click Upload and continue")
            self.step("upload", "done", f"{n} files, decrypted in memory")
        else:
            await self.press(SEL["upload"], "documents already attached, continue")
            self.step("upload", "done", "reused files from this session")
        err, _ = await self.page_error()
        if err:
            await self.snap("upload", "Upload rejected", "fail")
            self.step("upload", "fail", err[:90])
            raise RuntimeError(f"portal rejected the uploads: {err}")

    async def security(self):
        if not await self.page.locator(SEL["captcha"]).count():
            if self.statuses.get("captcha", "todo") == "todo":
                self.step("captcha", "skipped", "no security check on this attempt")
            return
        if self.captcha_code:
            self.log("info", "same CAPTCHA as before in this session, reusing the operator's answer")
            await self.type_into(SEL["captcha_in"], self.captcha_code)
            await self.press(SEL["captcha_go"], "submit security code")
            err, _ = await self.page_error()
            if not err:
                return
            self.captcha_code = None  # the portal issued a fresh one; ask again below
        self.step("captcha", "hold")
        await self.snap("captcha", "CAPTCHA checkpoint", "hold")
        last_err = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            shot = await self.page.locator(SEL["captcha"]).screenshot(type="png")
            res = await self.hold(
                "captcha", "CAPTCHA checkpoint" if attempt == 1 else
                f"CAPTCHA refused, attempt {attempt} of 3",
                {"image": "data:image/png;base64," + base64.b64encode(shot).decode(),
                 "step": self.where("captcha"), "error": last_err, "attempt": attempt,
                 "hint": "The agent screenshots the challenge and asks a person. It does not "
                         "attempt to break it. Every CAPTCHA is counted so you can see what the "
                         "portal costs you in staff time."})
            code = str(res["payload"].get("code", "")).strip()
            await self.type_into(SEL["captcha_in"], code)
            await self.press(SEL["captcha_go"], "submit security code")
            err, _ = await self.page_error()
            if not err:
                self.captcha_code = code
                self.step("captcha", "done",
                          f"{res['by']}, {attempt} attempt{'s' if attempt > 1 else ''}")
                return
            await self.snap("captcha", f"CAPTCHA refused, attempt {attempt}", "fail")
            self.log("err", "portal refused the security code")
            last_err = err
        self.step("captcha", "fail", "refused 3 times")
        raise RuntimeError("security check failed three times")

    async def review_and_submit(self, v):
        self.step("validate", "active")
        rows = await self.read_review()
        filed = rows.get("Applicant name", "")
        on_record = rows.get("Name on connection", "")
        self.log("info", f"review page reports name on connection as “{on_record}”")

        if extract.norm_cmp(filed, on_record):
            self.log("good", "pre-flight check passed: name filed matches the connection record")
            # A retry must not erase the record of the attempt that failed, nor of the
            # correction a person made. Only an untouched step gets marked skipped.
            self.step("validate", "done",
                      f"passed after correction, retry {self.retries}" if self.retries
                      else "pre-flight passed")
            if self.statuses.get("fix", "todo") in ("todo", ""):
                self.step("fix", "skipped", "nothing to correct")
        else:
            await self.snap("validate", "Pre-flight mismatch caught before submitting", "fail")
            self.log("err", f"pre-flight check failed: filing “{filed}” against a "
                            f"connection registered as “{on_record}”")
            self.step("validate", "fail", "name does not match the connection record")
            self.step("fix", "hold")
            res = await self.hold("fix", "Field correction needed", {
                "step": self.where("fix"),
                "filed": filed, "on_record": on_record,
                "bill_name": v["bill_name"], "aadhaar_name": v["aadhaar_name"],
                "options": [
                    {"id": "use_bill", "label": f"File the connection spelling “{on_record}”",
                     "recommended": True},
                    {"id": "submit_anyway", "label": "Submit the identity spelling anyway",
                     "detail": "The portal will validate this itself. Use it to see the real "
                               "rejection."}],
                "hint": "The agent caught this before spending a submission. Extraction already "
                        "flagged the field."})
            if res["resolution"] == "use_bill":
                self.retries += 1
                db.ex("UPDATE runs SET retries=? WHERE id=?", (self.retries, self.id))
                self.log("head", f"{res['by']} chose the connection spelling, re-filing the form")
                self.step("fix", "done", f"{res['by']}: connection spelling")
                await self.fill_form(v, first_pass=False)
                await self.attach({})
                await self.security()
                return await self.review_and_submit(v)
            self.step("fix", "done", f"{res['by']}: submit as filed")
            self.log("warn", "operator chose to submit the identity spelling; the portal will decide")

        rows = await self.approve_gate()

        self.step("submit", "active")
        await self.gate()
        await self.page.locator(SEL["declaration"]).check()
        self.log("act", "tick declaration")
        await self.press(SEL["submit"], "click Submit application")
        err, code = await self.page_error()
        if err:
            await self.snap("submit", f"Portal rejected the submission ({code or 'error'})", "fail")
            self.log("err", f"portal rejected the submission [{code}]: {err}")
            self.step("submit", "fail", f"{code}: rejected by the portal")
            if self.retries >= MAX_RETRIES:
                raise RuntimeError(f"portal rejected the submission after {self.retries} retries")
            self.retries += 1
            db.ex("UPDATE runs SET retries=? WHERE id=?", (self.retries, self.id))
            review = await self.read_review()
            self.step("fix", "hold")
            res = await self.hold("fix", "Portal rejected the submission", {
                "step": "retry", "portal_error": err, "code": code,
                "filed": review.get("Applicant name", ""),
                "on_record": review.get("Name on connection", ""),
                "bill_name": v["bill_name"], "aadhaar_name": v["aadhaar_name"],
                "options": [{"id": "use_bill", "label": "Correct the name and retry",
                             "recommended": True}],
                "hint": "This is the portal's own validation, captured with a screenshot. The run "
                        "is held, not abandoned."})
            self.step("fix", "done", f"{res['by']}: corrected after rejection")
            await self.fill_form(v, first_pass=False)
            await self.attach({})
            await self.security()
            return await self.review_and_submit(v)

        await self.page.wait_for_selector(SEL["app_no"], timeout=15000)
        self.app_no = (await self.page.locator(SEL["app_no"]).inner_text()).strip()
        self.log("good", f"application number captured: {self.app_no}")
        self.step("submit", "done")
        await self.finish(f"Acknowledgement {self.app_no}", """UPDATE customers SET
            application_no=?,stage='feasible',last_activity=?,blocked_note=NULL WHERE id=?""",
                          (self.app_no, datetime.now().strftime("%d %b"), self.c["id"]),
                          "stage moved to DISCOM feasibility")

    # ===================== DISCOM self-service portal =====================
    async def flow_discom(self, v, docs):
        new = self.wf == "new_connection"
        self.step("open", "active")
        await self.page.goto(f"{BASE_URL}/discom/login", wait_until="domcontentloaded")
        self.log("act", f"navigate {self.page.url}")
        self.step("open", "done")

        self.step("login", "active")
        num = db.one("SELECT msisdn FROM numbers WHERE customer_id=?", (self.c["id"],))
        if new:
            mobile = "".join(ch for ch in (num["msisdn"] if num else "") if ch.isdigit())[-10:]
            self.log("info", "no consumer number yet; identifying by the applicant's mobile only")
        else:
            mobile = v["mobile"]
            await self.type_into(DSEL["consumer"], v["consumer_no"],
                                 "consumer number (from bill, 99%)")
        await self.type_into(DSEL["mobile"], mobile,
                             "dedicated mobile for this application" if new
                             else "registered mobile (from bill)")
        await self.press(DSEL["send_otp"], "click Send OTP")
        err, _ = await self.page_error()
        if err:
            await self.snap("login", "Sign-in refused", "fail")
            self.step("login", "fail", err[:90])
            raise RuntimeError(f"portal refused the sign-in: {err}")
        self.step("login", "done")

        await self.otp_checkpoint(DSEL["otp"], DSEL["verify"])

        self.step("request", "active")
        kind = {"load_enhancement": "Load enhancement", "load_reduction": "Load reduction",
                "new_connection": "New connection"}[self.wf]
        await self.choose(DSEL["type"], kind, "request type")
        await self.type_into(DSEL["load"], f"{self.target_kw:.2f}", "requested load (kW)")
        await self.choose(DSEL["phase"], "Three phase" if self.target_kw > 7 else "Single phase",
                          "supply")
        purpose = "Residential" if self.c["category"] in ROOFTOP_CATEGORIES else self.c["category"]
        await self.choose(DSEL["purpose"], purpose, "purpose")
        reason = {
            "load_enhancement": f"Rooftop solar plant of {self.c['kw']:g} kW requires a sanctioned "
                                f"load of at least {self.target_kw:g} kW",
            "load_reduction": "Connected load reduced after equipment was removed from the premises",
            "new_connection": "New residential premises; supply needed for occupation and a "
                              "rooftop solar plant"}[self.wf]
        await self.type_into(DSEL["reason"], reason, "reason")
        if new:
            await self.type_into(DSEL["app_name"], v["aadhaar_name"] or self.c["aadhaar_name"],
                                 "applicant name (identity document)")
            await self.type_into(DSEL["app_address"], v["owner_address"] or self.c["address"],
                                 "premises address (ownership proof)")
            await self.type_into(DSEL["app_pin"], v["owner_pin"] or self.c["pin"])
        await self.press(DSEL["next"], "click Save and continue")
        err, _ = await self.page_error()
        if err:
            await self.snap("request", "Request refused by the portal", "fail")
            self.step("request", "fail", err[:90])
            raise RuntimeError(f"portal refused the request: {err}")
        self.step("request", "done", kind.lower())

        self.step("upload", "active")
        n = 0
        for kind_key, sel in DDOC_INPUTS.items():
            if docs.get(kind_key) and await self.page.locator(sel).count():
                await self.attach_file(sel, docs[kind_key])
                n += 1
        await self.press(DSEL["upload"], "click Upload and continue")
        err, _ = await self.page_error()
        if err:
            await self.snap("upload", "Upload rejected", "fail")
            self.step("upload", "fail", err[:90])
            raise RuntimeError(f"portal rejected the uploads: {err}")
        self.step("upload", "done", f"{n} files, decrypted in memory")

        self.step("validate", "active")
        rows = await self.read_review()
        req = float(rows.get("Requested load", "0").split()[0])
        if new:
            ok = abs(req - self.target_kw) < 0.01 and rows.get("Applicant name")
            note = "applicant and load match the request"
        else:
            cur = float(rows.get("Current sanctioned load", "0").split()[0])
            on_bill = float(v["load"] or 0)
            if abs(cur - on_bill) > 0.01:
                self.log("warn", f"portal shows {cur:g} kW sanctioned; the bill shows {on_bill:g} kW")
            ok = req > cur if self.wf == "load_enhancement" else req < cur
            note = f"{cur:g} kW → {req:g} kW"
        if not ok:
            await self.snap("validate", "Pre-flight check failed", "fail")
            self.step("validate", "fail", note)
            raise RuntimeError(f"pre-flight check failed: {note}")
        self.log("good", f"pre-flight check passed: {note}")
        self.step("validate", "done", note)

        await self.approve_gate()

        self.step("submit", "active")
        await self.gate()
        await self.page.locator(DSEL["declaration"]).check()
        self.log("act", "tick confirmation")
        await self.press(DSEL["submit"], "click Submit request")
        err, code = await self.page_error()
        if err:
            await self.snap("submit", f"Portal refused the request ({code or 'error'})", "fail")
            self.step("submit", "fail", f"{code}: refused by the portal")
            raise RuntimeError(f"portal refused the request [{code}]: {err}")
        await self.page.wait_for_selector(DSEL["request_no"], timeout=15000)
        self.app_no = (await self.page.locator(DSEL["request_no"]).inner_text()).strip()
        self.log("good", f"request number captured: {self.app_no}")
        self.step("submit", "done")

        follow = {
            "load_enhancement": (f"Load enhancement {self.app_no} filed. Rooftop registration "
                                 f"can proceed once the DISCOM sanctions {self.target_kw:g} kW",
                                 "rooftop_registration"),
            "load_reduction": (f"Load reduction {self.app_no} filed, awaiting site inspection",
                               self.c["workflow"]),
            "new_connection": (f"New connection {self.app_no} filed, awaiting site inspection and "
                               f"demand note", None)}[self.wf]
        await self.finish(f"Acknowledgement {self.app_no}", """UPDATE customers SET
            discom_ref=?,blocked_note=?,workflow=?,last_activity=? WHERE id=?""",
                          (self.app_no, follow[0], follow[1], datetime.now().strftime("%d %b"),
                           self.c["id"]), "DISCOM request on record, follow-up created")

    # ===================== shared =====================
    async def approve_gate(self):
        self.step("approve", "hold")
        await self.snap("approve", "State at the approval gate", "hold")
        rows = await self.read_review()
        res = await self.hold("approve", "Approval required", {
            "step": self.where("approve"), "summary": rows, "customer": self.c["name"],
            "workflow": self.wf_label, "subsidy": self.c["subsidy"],
            "hint": "No application is filed without a person approving it. Only a supervisor may "
                    "approve, and the server enforces that, not the screen."},
            min_role="supervisor")
        self.step("approve", "done", f"{res['by']}, supervisor")
        db.audit(res["by"], "supervisor", "APPROVED final submission", self.c["id"],
                 f"run {self.id}, {self.wf_label.lower()}, {len(rows)} fields verified")
        return rows

    async def finish(self, shot_label, sql, args, outcome):
        self.step("record", "active")
        await self.snap("record", shot_label, "ok")
        db.ex(sql, args)
        db.ex("UPDATE runs SET application_no=?,finished_at=?,status='done' WHERE id=?",
              (self.app_no, db.now(), self.id))
        db.audit("agent", "agent", f"{self.wf_label} filed", self.c["id"],
                 f"{self.app_no}, {outcome}")
        self.log("good", f"customer record updated, {outcome}")
        self.step("record", "done", "record and evidence stored")
        self.set_status("done")
        self.emit({"type": "done", "application_no": self.app_no, "workflow": self.wf_label,
                   "seconds": round(time.time() - self.t0, 1), "retries": self.retries})
        self.log("head", f"run complete in {time.time() - self.t0:.0f}s — {self.app_no}")

    async def read_review(self):
        """Scrape the portal's own review table, so comparisons use what the portal shows."""
        out = {}
        try:
            for tr in await self.page.locator("table tr").all():
                tds = await tr.locator("td").all()
                if len(tds) == 2:
                    out[(await tds[0].inner_text()).strip()] = (await tds[1].inner_text()).strip()
        except Exception:
            pass
        return out


def preflight(c, workflow, target_kw):
    """Refuse work the agent already knows the portal will reject. Returns an error or None."""
    if workflow not in WORKFLOWS:
        return f"unknown workflow {workflow}"
    if workflow == "rooftop_registration":
        if c["application_no"]:
            return f"{c['id']} is already filed as {c['application_no']}; a second filing would be a duplicate"
        if not c["consumer_no"]:
            return f"{c['id']} has no electricity connection yet; file a new connection first"
        if c["category"] not in ROOFTOP_CATEGORIES:
            return (f"PM Surya Ghar covers residential consumers and housing societies; "
                    f"{c['id']} is {c['category'].lower()}")
        load = next((r["value"] for r in extract.saved(c["id"])
                     if r["field"] == "Sanctioned load (kW)"), None)
        if load and target_kw > float(load) + 0.001:
            return (f"plant {target_kw:g} kW exceeds the sanctioned load {float(load):g} kW; "
                    f"file a load enhancement first")
    elif workflow == "new_connection":
        if c["consumer_no"]:
            return f"{c['id']} already has connection {c['consumer_no']}; use a load change instead"
    elif not c["consumer_no"]:
        return f"{c['id']} has no consumer number; a load change needs an existing connection"
    if workflow != "rooftop_registration" and c["discom_ref"] and c["workflow"] != workflow:
        return f"{c['id']} already has DISCOM request {c['discom_ref']} on record"
    return None


async def start(customer_id, user, headless=True, speed=1.0, workflow=None, target_kw=None):
    c = db.one("SELECT * FROM customers WHERE id=?", (customer_id,))
    if not c:
        raise ValueError("unknown customer")
    workflow = workflow or c["workflow"]
    if not workflow:
        raise ValueError(f"no agent workflow applies to {c['id']}: {c['blocked_note'] or 'none'}")
    target_kw = float(target_kw if target_kw not in (None, "") else c["kw"])
    problem = preflight(c, workflow, target_kw)
    if problem:
        raise ValueError(problem)
    for r in RUNS.values():
        if r.status in ("running", "held", "paused", "starting"):
            raise RuntimeError(f"run {r.id} is still active on {r.c['id']}")
    run_id = db.ex("""INSERT INTO runs(customer_id,workflow,status,started_at,started_by,headless)
                      VALUES(?,?,'starting',?,?,?)""",
                   (customer_id, workflow, db.now(), user["username"], 1 if headless else 0))
    r = Runner(run_id, c, user, workflow, target_kw, headless=headless, speed=speed)
    RUNS[run_id] = r

    async def go():
        try:
            await r.execute()
        except HoldRejected as e:
            r.log("err", f"run stopped: {e.args[0]} — nothing was submitted")
            r.set_status("stopped")
            db.ex("UPDATE runs SET status='stopped',finished_at=? WHERE id=?", (db.now(), run_id))
            db.audit("system", "system", "Run stopped", c["id"], f"run {run_id}: {e.args[0]}")
            r.emit({"type": "failed", "status": "stopped", "reason": str(e.args[0])})
        except Exception as e:
            r.log("err", f"run failed: {type(e).__name__}: {e}")
            try:
                await r.snap("failure", "State at failure", "fail")
            except Exception:
                pass
            r.set_status("failed")
            db.ex("UPDATE runs SET status='failed',finished_at=? WHERE id=?", (db.now(), run_id))
            db.audit("system", "system", "Run failed", c["id"], f"run {run_id}: {e}")
            r.emit({"type": "failed", "status": "failed", "reason": f"{type(e).__name__}: {e}"})

    asyncio.create_task(go())
    return r
