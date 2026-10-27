"""A second sandbox: a distribution company's self-service portal.

It covers the three DISCOM service requests in the brief — new connection, sanctioned
load enhancement and load reduction — with the same honesty as the rooftop portal:
a real session, a real OTP written to the SMS table, server-side validation of the
request against the connection register, document uploads, and a duplicate guard.

Two portals, one agent engine: the runner drives this with a different step list and
selector block, which is exactly what pointing it at the live portals will look like.
"""
import json, random, secrets
from datetime import datetime
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from . import db
from .config import DATA
from .portal import shell as _shell, sess as _sess, set_sess

router = APIRouter(prefix="/discom")
COOKIE = "dsid"
DSTEPS = ["Identify", "Mobile OTP", "Service request", "Documents", "Review and submit"]
KINDS = {"Load enhancement": "load_enhancement", "Load reduction": "load_reduction",
         "New connection": "new_connection"}
LT_MAX_KW = 49  # sandbox ceiling for a low-tension request
UPLOADS = {"load": [("dDocId", "Identity proof"), ("dDocBill", "Latest electricity bill")],
           "new": [("dDocId", "Identity proof"), ("dDocOwnership", "Ownership or occupancy proof")]}


def shell(title, inner, step=None):
    return _shell(title, inner, step, steps=DSTEPS, brand="Distribution Company Self-Service",
                  sub="Maharashtra &middot; sandbox",
                  nav=("Home", "Services", "Track request", "Pay bill", "Help"), mark="&#9889;")


def sess(request: Request):
    return _sess(request, COOKIE)


def banner(error, code=""):
    if not error:
        return ""
    ref = (f'<br><span style="opacity:.75">Error reference: <span id="errCode">{code}</span>'
           f'</span>') if code else ""
    return f'<div class="pbanner err" id="valError"><b>&#9888;</b><div>{error}{ref}</div></div>'


def data_of(s):
    return json.loads(s["data"] or "{}")


@router.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/discom/login")


@router.get("/login", response_class=HTMLResponse)
def login_get(error: str = ""):
    return shell("Identify", banner(error) + """
<div class="pcard"><h4>Identify yourself</h4>
<div class="pd">Existing consumers enter their consumer number and registered mobile. For a new
connection, leave the consumer number blank and enter the applicant's mobile.</div>
<form method="post" action="/discom/login"><div class="pf">
<div class="f"><label for="dConsumer">Consumer number (existing connections)</label>
<input type="text" id="dConsumer" name="consumer_no" maxlength="12" autocomplete="off"></div>
<div class="f"><label for="dMobile">Mobile number</label>
<input type="text" id="dMobile" name="mobile" maxlength="10" autocomplete="off"></div>
<div class="f wide"><button type="submit" id="dSendOtp">Send OTP</button></div>
</div></form></div>""", 0)


@router.post("/login")
def login_post(consumer_no: str = Form(""), mobile: str = Form("")):
    consumer_no, mobile = consumer_no.strip(), mobile.strip()
    if not (mobile.isdigit() and len(mobile) == 10):
        return login_get("Enter a 10-digit mobile number.")
    if consumer_no:
        pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (consumer_no,))
        if not pc:
            return login_get(f"Consumer number {consumer_no} was not found in the register.")
        if pc["msisdn"] != mobile:
            return login_get("This mobile is not the one registered against the consumer number.")
    sid = secrets.token_hex(12)
    otp = f"{random.randint(0, 999999):06d}"
    set_sess(sid, consumer_no=consumer_no or None, stage="otp", otp=otp, otp_tries=0,
             data={"portal": "discom", "mobile": mobile})
    num = db.one("SELECT msisdn FROM numbers WHERE REPLACE(REPLACE(msisdn,' ',''),'+91','')=?",
                 (mobile,))
    db.ex("INSERT INTO sms(msisdn,sender,body,code,ts) VALUES(?,?,?,?,?)",
          (num["msisdn"] if num else "+91 " + mobile, "VM-DISCOM",
           f"{otp} is your OTP for the DISCOM self-service portal. Valid for 10 minutes.",
           otp, db.now()))
    r = RedirectResponse("/discom/otp", status_code=303)
    r.set_cookie(COOKIE, sid, httponly=True, samesite="lax")
    return r


@router.get("/otp", response_class=HTMLResponse)
def otp_get(request: Request, error: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    mob = data_of(s).get("mobile", "")
    return shell("Mobile OTP", banner(error) + f"""
<div class="pcard"><h4>Enter the one-time password</h4>
<div class="pd">Sent to the mobile ending {mob[-4:]}. Valid for 10 minutes.</div>
<form method="post" action="/discom/otp" class="otpwrap">
<label for="dOtp">One-time password</label>
<input type="text" id="dOtp" name="otp" maxlength="6" autocomplete="off" inputmode="numeric">
<div style="margin-top:14px"><button type="submit" id="dVerify">Verify</button></div></form>
<div class="pnote">Attempts used: {s['otp_tries']} of 3.</div></div>""", 1)


@router.post("/otp")
def otp_post(request: Request, otp: str = Form("")):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    if otp.strip() != s["otp"]:
        tries = s["otp_tries"] + 1
        set_sess(s["sid"], otp_tries=tries)
        if tries >= 3:
            set_sess(s["sid"], stage="login")
            return login_get("Too many incorrect OTP attempts. Start again.")
        return otp_get(request, f"Incorrect OTP. {3 - tries} attempt(s) left.")
    set_sess(s["sid"], stage="request")
    db.ex("UPDATE sms SET read_at=? WHERE code=? AND read_at IS NULL", (db.now(), s["otp"]))
    return RedirectResponse("/discom/request", status_code=303)


@router.get("/request", response_class=HTMLResponse)
def request_get(request: Request, error: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (s["consumer_no"],)) \
        if s["consumer_no"] else None
    conn = (f"""<table style="margin-bottom:14px">
<tr><td>Consumer number</td><td>{pc['consumer_no']}</td></tr>
<tr><td>Name on connection</td><td>{pc['billed_name']}</td></tr>
<tr><td>Current sanctioned load</td><td>{pc['sanctioned_load']:.2f} kW</td></tr>
<tr><td>Tariff</td><td>{pc['tariff']}</td></tr></table>""" if pc else
            '<div class="pd" id="noConnection">No existing connection. Only a new connection '
            'can be requested from this sign-in.</div>')
    opts = "".join(f"<option>{k}</option>" for k in KINDS)
    return shell("Service request", banner(error) + f"""
<div class="pcard"><h4>Raise a service request</h4>{conn}
<form method="post" action="/discom/request"><div class="pf">
<div class="f"><label for="reqType">Request type</label>
<select id="reqType" name="kind"><option value="">Select</option>{opts}</select></div>
<div class="f"><label for="reqLoad">Requested load (kW)</label>
<input type="text" id="reqLoad" name="requested" autocomplete="off"></div>
<div class="f"><label for="phase">Supply</label><select id="phase" name="phase">
<option value="">Select</option><option>Single phase</option><option>Three phase</option></select></div>
<div class="f"><label for="purpose">Purpose</label><select id="purpose" name="purpose">
<option value="">Select</option><option>Residential</option><option>Commercial</option>
<option>Industrial</option></select></div>
<div class="f wide"><label for="reason">Reason for the request</label>
<input type="text" id="reason" name="reason" autocomplete="off"></div>
<div class="f wide" style="border-top:1px dashed #D6DEE7;padding-top:10px">
<span class="pnote" style="margin:0">New connection only</span></div>
<div class="f wide"><label for="appName">Applicant name</label>
<input type="text" id="appName" name="app_name" autocomplete="off"></div>
<div class="f"><label for="appAddress">Premises address</label>
<input type="text" id="appAddress" name="app_address" autocomplete="off"></div>
<div class="f"><label for="appPin">PIN code</label>
<input type="text" id="appPin" name="app_pin" maxlength="6" autocomplete="off"></div>
<div class="f wide"><button type="submit" id="btnReqNext">Save and continue</button></div>
</div></form></div>""", 2)


@router.post("/request")
def request_post(request: Request, kind: str = Form(""), requested: str = Form(""),
                 phase: str = Form(""), purpose: str = Form(""), reason: str = Form(""),
                 app_name: str = Form(""), app_address: str = Form(""), app_pin: str = Form("")):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    k = KINDS.get(kind)
    if not k:
        return request_get(request, "Select a request type.")
    try:
        req = float(requested)
    except ValueError:
        return request_get(request, "Requested load must be a number in kW.")
    if not phase or not purpose or len(reason.strip()) < 10:
        return request_get(request, "Supply, purpose and a reason of at least 10 characters are "
                                    "required.")
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (s["consumer_no"],)) \
        if s["consumer_no"] else None
    cur = float(pc["sanctioned_load"]) if pc else 0.0
    if k == "new_connection":
        if pc:
            return request_get(request, "This sign-in is linked to an existing connection. A new "
                                        "connection is requested without a consumer number.")
        if not app_name.strip() or not app_address.strip() or not (app_pin.isdigit() and
                                                                    len(app_pin) == 6):
            return request_get(request, "Applicant name, premises address and a 6-digit PIN are "
                                        "required for a new connection.")
        if not 1 <= req <= LT_MAX_KW:
            return request_get(request, f"A new LT connection must be between 1 and {LT_MAX_KW} kW.")
    else:
        if not pc:
            return request_get(request, "A load change needs an existing consumer number. Sign in "
                                        "again with it.")
        if k == "load_enhancement" and req <= cur:
            return request_get(request, f"Requested load {req:.2f} kW must be above the current "
                                        f"sanctioned load {cur:.2f} kW for an enhancement.")
        if k == "load_reduction" and not 1 <= req < cur:
            return request_get(request, f"Requested load must be below {cur:.2f} kW and at least "
                                        f"1 kW for a reduction.")
        # the HT ceiling limits going up; a reduction is always allowed to bring a load down
        if k == "load_enhancement" and req > LT_MAX_KW:
            return request_get(request, f"Loads above {LT_MAX_KW} kW need an HT application.")
    set_sess(s["sid"], stage="docs", data={
        "kind": k, "kind_label": kind, "requested": req, "current": cur, "phase": phase,
        "purpose": purpose, "reason": reason.strip(), "app_name": app_name.strip(),
        "app_address": app_address.strip(), "app_pin": app_pin.strip()})
    return RedirectResponse("/discom/docs", status_code=303)


@router.get("/docs", response_class=HTMLResponse)
def docs_get(request: Request, error: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    d = data_of(s)
    fields = UPLOADS["new" if d.get("kind") == "new_connection" else "load"]
    rows = "".join(f"""<div class="upr"><label for="{i}">{lbl}</label>
<input type="file" id="{i}" name="{i}" accept=".pdf,.jpg,.jpeg,.png"></div>""" for i, lbl in fields)
    return shell("Documents", banner(error) + f"""
<div class="pcard"><h4>Attach documents</h4><div class="pd">PDF, JPG or PNG. Both are required.</div>
<form method="post" action="/discom/docs" enctype="multipart/form-data">{rows}
<div style="margin-top:13px"><button type="submit" id="dBtnUpload">Upload and continue</button></div>
</form></div>""", 3)


@router.post("/docs")
async def docs_post(request: Request, dDocId: UploadFile = File(None),
                    dDocBill: UploadFile = File(None), dDocOwnership: UploadFile = File(None)):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    d = data_of(s)
    files = {"dDocId": dDocId}
    files.update({"dDocOwnership": dDocOwnership} if d.get("kind") == "new_connection"
                 else {"dDocBill": dDocBill})
    missing = [k for k, f in files.items() if f is None or not f.filename]
    if missing:
        return docs_get(request, "Missing: " + ", ".join(missing) + ".")
    out = DATA / "portal_uploads" / s["sid"]
    out.mkdir(parents=True, exist_ok=True)
    saved = {}
    for k, f in files.items():
        blob = await f.read()
        (out / f"{k}_{f.filename}").write_bytes(blob)
        saved[k] = {"name": f.filename, "bytes": len(blob)}
    set_sess(s["sid"], stage="review", data={"uploads": saved})
    return RedirectResponse("/discom/review", status_code=303)


@router.get("/review", response_class=HTMLResponse)
def review_get(request: Request, error: str = "", code: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    d = data_of(s)
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (s["consumer_no"],)) \
        if s["consumer_no"] else None
    rows = [("Request type", d.get("kind_label", "")),
            ("Consumer number", s["consumer_no"] or "Not yet allotted")]
    if pc:
        rows += [("Name on connection", pc["billed_name"]),
                 ("Current sanctioned load", f"{d.get('current', 0):.2f} kW")]
    else:
        rows += [("Applicant name", d.get("app_name", "")),
                 ("Premises address", f"{d.get('app_address', '')} {d.get('app_pin', '')}")]
    rows += [("Requested load", f"{d.get('requested', 0):.2f} kW"), ("Supply", d.get("phase", "")),
             ("Purpose", d.get("purpose", "")), ("Reason", d.get("reason", "")),
             ("Documents attached", f"{len(d.get('uploads', {}))} files")]
    tbl = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return shell("Review", banner(error, code) + f"""
<div class="pcard"><h4>Review your request</h4>
<div class="pd">After submission the request is assigned to the sub-division for site inspection.</div>
<table>{tbl}</table>
<form method="post" action="/discom/review" style="margin-top:12px">
<label style="display:flex;gap:9px;align-items:flex-start;font-weight:400;font-size:11.5px;
color:#4A5663"><input type="checkbox" id="dDecl" name="declaration" value="1"
style="width:auto;margin-top:2px"><span>I confirm the details are correct and agree to pay the
applicable charges.</span></label>
<div style="margin-top:13px"><button type="submit" id="dSubmit">Submit request</button></div>
</form></div>""", 4)


@router.post("/review")
def review_post(request: Request, declaration: str = Form("")):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    d = data_of(s)
    if not declaration:
        return review_get(request, "The confirmation must be ticked before submitting.", "SR-0004")
    who = s["consumer_no"] or d.get("app_name", "").upper()
    dup = db.one("SELECT request_no FROM portal_requests WHERE kind=? AND "
                 "(consumer_no=? OR applicant=?)", (d.get("kind"), s["consumer_no"] or "", who))
    if dup:
        return review_get(request, f"A {d.get('kind_label', '').lower()} request "
                                   f"{dup['request_no']} is already open for this "
                                   f"{'connection' if s['consumer_no'] else 'applicant'}.",
                          "SR-0902")
    req_no = f"SR/MH/{datetime.now().year}/{random.randint(400000, 499999)}"
    db.ex("""INSERT INTO portal_requests(request_no,kind,consumer_no,applicant,current_load,
             requested_load,submitted_at,payload) VALUES(?,?,?,?,?,?,?,?)""",
          (req_no, d.get("kind"), s["consumer_no"] or "", who, d.get("current"),
           d.get("requested"), db.now(), json.dumps(d, ensure_ascii=False)))
    set_sess(s["sid"], stage="done", data={"request_no": req_no})
    return RedirectResponse("/discom/ack", status_code=303)


@router.get("/ack", response_class=HTMLResponse)
def ack(request: Request):
    s = sess(request)
    if not s:
        return RedirectResponse("/discom/login")
    d = data_of(s)
    row = db.one("SELECT * FROM portal_requests WHERE request_no=?", (d.get("request_no", ""),))
    if not row:
        return RedirectResponse("/discom/login")
    return shell("Acknowledgement", f"""
<div class="pbanner ok"><b>&#10003;</b><div><b>Request registered.</b> It has been assigned to the
sub-division for site inspection.</div></div>
<div class="pcard"><h4>Acknowledgement</h4><table>
<tr><td>Request number</td><td><b id="requestNo">{row['request_no']}</b></td></tr>
<tr><td>Request type</td><td>{d.get('kind_label', '')}</td></tr>
<tr><td>Consumer / applicant</td><td>{row['consumer_no'] or row['applicant']}</td></tr>
<tr><td>Requested load</td><td>{row['requested_load']:.2f} kW</td></tr>
<tr><td>Submitted on</td><td>{row['submitted_at'].replace('T', ' ')}</td></tr>
<tr><td>Next step</td><td>Site inspection and demand note</td></tr></table></div>""")
