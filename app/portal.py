"""A real, server-side mock of a rooftop-solar portal.

This is a working web application, not a prop: it holds a session, issues a real OTP
to a real SMS table, generates a real CAPTCHA, validates uploads, and rejects a
submission server-side when the applicant name does not match the distribution
company's consumer register. The agent has to get through all of it honestly.

Swapping this for the live government portal means changing selectors and the base
URL in app/agent/runner.py. Nothing else about the agent changes.
"""
import secrets, json, random, string, re
from datetime import datetime
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import db
from .config import DOCS

router = APIRouter(prefix="/portal")

CSS = """
*{box-sizing:border-box}
body{margin:0;font:13px/1.5 "Segoe UI",Arial,sans-serif;color:#17202A;background:#F2F4F7}
.phead{background:#123A6B;color:#fff;padding:10px 16px;display:flex;align-items:center;gap:11px}
.pm{width:26px;height:26px;border-radius:5px;background:#F2A63B;color:#123A6B;display:grid;
place-items:center;font-weight:700;font-size:13px}
.pt{font-weight:600;font-size:13.5px}
.ps{font-size:9.5px;opacity:.78;letter-spacing:.11em;text-transform:uppercase}
.pnav{background:#0E2E55;color:#C6D7EC;font-size:10.5px;padding:6px 16px;display:flex;gap:16px;
letter-spacing:.07em;text-transform:uppercase}
.pbody{padding:16px}
.pcard{background:#fff;border:1px solid #D6DEE7;border-radius:7px;padding:16px;max-width:640px}
h4{margin:0 0 4px;font-size:15px;color:#123A6B}
.pd{font-size:11.5px;color:#5E6B78;margin-bottom:14px}
.pf{display:grid;grid-template-columns:1fr 1fr;gap:11px 16px}
.f{min-width:0}.wide{grid-column:1/-1}
label{display:block;font-size:10.5px;color:#4A5663;margin-bottom:4px;font-weight:600}
input[type=text],select,input[type=file]{width:100%;background:#fff;border:1px solid #BFCAD6;
border-radius:5px;padding:7px 9px;font-size:12.5px;font-family:inherit;color:#17202A}
input:focus,select:focus{outline:none;border-color:#F2A63B;box-shadow:0 0 0 3px rgba(242,166,59,.25)}
button{background:#123A6B;color:#fff;border:1px solid #123A6B;border-radius:5px;padding:8px 17px;
font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit}
button:hover{background:#0E2E55}
.pnote{font-size:10.5px;color:#6A7684;margin-top:12px}
.pbanner{border-radius:6px;padding:10px 12px;font-size:11.5px;margin-bottom:14px;max-width:640px;
display:flex;gap:9px;align-items:flex-start}
.err{background:#FDECEA;border:1px solid #F3B5AF;color:#8E231B}
.ok{background:#E8F7EE;border:1px solid #A9DDBE;color:#146332}
table{width:100%;border-collapse:collapse;font-size:12px}
td{padding:6px 8px;border-bottom:1px solid #E6EBF1}
td:first-child{color:#5E6B78;width:44%}
.otpwrap input{width:150px;text-align:center;letter-spacing:.5em;font-family:ui-monospace,monospace;
font-size:17px}
.capimg{font-family:ui-monospace,monospace;font-size:23px;letter-spacing:.24em;padding:9px 15px;
border-radius:5px;color:#123A6B;background:repeating-linear-gradient(45deg,#E9EEF4 0 6px,#DFE6EE 6px 12px);
border:1px solid #BFCAD6;transform:skewY(-3deg);display:inline-block;text-decoration:line-through;
text-decoration-color:rgba(18,58,107,.35)}
.steps{font-size:10.5px;color:#6A7684;margin-bottom:12px;letter-spacing:.04em}
.steps b{color:#123A6B}
.upr{display:flex;align-items:center;gap:11px;border:1px solid #D6DEE7;border-radius:6px;
padding:9px 11px;margin-bottom:8px;background:#fff}
.upr label{flex:0 0 190px;margin:0}
.sandbox{background:#8E231B;color:#fff;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
padding:3px 16px;text-align:center}
"""

STEPS = ["Verify connection", "Mobile OTP", "Applicant details", "Documents", "Security check",
         "Review and submit"]

UPLOAD_FIELDS = [("docBill", "Latest electricity bill"),
                 ("docAadhaar", "Aadhaar (front and back)"),
                 ("docPassbook", "Bank passbook first page"),
                 ("docRoof", "Roof photographs")]


def shell(title, inner, step=None):
    bar = ""
    if step is not None:
        bar = '<div class="steps">' + " &rsaquo; ".join(
            (f"<b>{s}</b>" if i == step else s) for i, s in enumerate(STEPS)) + "</div>"
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>{CSS}</style></head><body>
<div class="sandbox">Demo sandbox &mdash; this is not a government service</div>
<div class="phead"><div class="pm">&#9728;</div><div><div class="pt">Rooftop Solar Portal</div>
<div class="ps">National programme &middot; sandbox</div></div></div>
<div class="pnav"><span>Home</span><span>Apply</span><span>Track status</span><span>Vendors</span>
<span>Help</span></div>
<div class="pbody">{bar}{inner}</div></body></html>""")


def sid_of(request: Request):
    return request.cookies.get("psid")


def sess(request: Request):
    s = sid_of(request)
    return db.one("SELECT * FROM portal_sessions WHERE sid=?", (s,)) if s else None


def set_sess(sid, **kw):
    cur = db.one("SELECT * FROM portal_sessions WHERE sid=?", (sid,))
    data = json.loads(cur["data"] or "{}") if cur else {}
    data.update(kw.pop("data", {}) or {})
    fields = {"stage": kw.get("stage", cur["stage"] if cur else "verify"),
              "otp": kw.get("otp", cur["otp"] if cur else None),
              "otp_tries": kw.get("otp_tries", cur["otp_tries"] if cur else 0),
              "captcha": kw.get("captcha", cur["captcha"] if cur else None),
              "consumer_no": kw.get("consumer_no", cur["consumer_no"] if cur else None)}
    if cur:
        db.ex("""UPDATE portal_sessions SET consumer_no=?,stage=?,otp=?,otp_tries=?,captcha=?,data=?
                 WHERE sid=?""", (fields["consumer_no"], fields["stage"], fields["otp"],
                                  fields["otp_tries"], fields["captcha"],
                                  json.dumps(data, ensure_ascii=False), sid))
    else:
        db.ex("""INSERT INTO portal_sessions(sid,consumer_no,stage,otp,otp_tries,captcha,data,created_at)
                 VALUES(?,?,?,?,?,?,?,?)""", (sid, fields["consumer_no"], fields["stage"], fields["otp"],
                                              fields["otp_tries"], fields["captcha"],
                                              json.dumps(data, ensure_ascii=False), db.now()))
    return data


def norm(n):
    return re.sub(r"[^A-Z ]", "", (n or "").upper()).replace("  ", " ").strip()


@router.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/portal/verify")


@router.get("/verify", response_class=HTMLResponse)
def verify_get(request: Request, error: str = ""):
    banner = f'<div class="pbanner err" id="valError"><b>&#9888;</b><div>{error}</div></div>' if error else ""
    return shell("Verify connection", banner + """
<div class="pcard"><h4>Verify your electricity connection</h4>
<div class="pd">Enter the consumer number printed on your bill. A one-time password will be sent to
the mobile number registered with the distribution company.</div>
<form method="post" action="/portal/verify"><div class="pf">
<div class="f"><label for="state">State</label><select id="state" name="state">
<option value="">Select state</option><option>Maharashtra</option><option>Gujarat</option>
<option>Goa</option></select></div>
<div class="f"><label for="discom">Distribution company</label><select id="discom" name="discom">
<option value="">Select company</option>
<option>Maharashtra State Electricity Distribution Co. Ltd.</option>
<option>Torrent Power</option><option>Adani Electricity</option></select></div>
<div class="f"><label for="consumerNo">Consumer number</label>
<input type="text" id="consumerNo" name="consumer_no" maxlength="12" autocomplete="off"></div>
<div class="f"><label for="mobile">Registered mobile</label>
<input type="text" id="mobile" name="mobile" maxlength="10" autocomplete="off"></div>
<div class="f wide"><button type="submit" id="btnSendOtp">Send OTP</button></div>
</div></form>
<div class="pnote">The consumer number is 12 digits and appears at the top of your bill.</div></div>""", 0)


@router.post("/verify")
def verify_post(request: Request, state: str = Form(""), discom: str = Form(""),
                consumer_no: str = Form(""), mobile: str = Form("")):
    if not state or not discom:
        return verify_get(request, "Select both the state and the distribution company.")
    consumer_no = consumer_no.strip()
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (consumer_no,))
    if not pc:
        return verify_get(request, f"Consumer number {consumer_no or '(blank)'} was not found in the "
                                   "register. Check the number on your bill.")
    if mobile.strip() != pc["msisdn"]:
        return verify_get(request, "The mobile number does not match the one registered against this "
                                   "consumer number.")
    sid = secrets.token_hex(12)
    otp = f"{random.randint(0, 999999):06d}"
    set_sess(sid, consumer_no=consumer_no, stage="otp", otp=otp, otp_tries=0,
             data={"state": state, "discom": discom, "mobile": mobile})
    msisdn = db.one("SELECT msisdn FROM numbers WHERE REPLACE(REPLACE(msisdn,' ',''),'+91','')=?",
                    (mobile.strip(),))
    db.ex("INSERT INTO sms(msisdn,sender,body,code,ts) VALUES(?,?,?,?,?)",
          (msisdn["msisdn"] if msisdn else "+91 " + mobile, "VM-NRSOLR",
           f"OTP for rooftop solar registration is {otp}. Valid for 10 minutes. Do not share it.",
           otp, db.now()))
    r = RedirectResponse("/portal/otp", status_code=303)
    r.set_cookie("psid", sid, httponly=True, samesite="lax")
    return r


@router.get("/otp", response_class=HTMLResponse)
def otp_get(request: Request, error: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    mob = json.loads(s["data"] or "{}").get("mobile", "")
    banner = f'<div class="pbanner err" id="valError"><b>&#9888;</b><div>{error}</div></div>' if error else ""
    return shell("Mobile verification", banner + f"""
<div class="pcard"><h4>Enter the one-time password</h4>
<div class="pd">A 6-digit code was sent to the mobile number ending {mob[-4:] if mob else '____'}.
It is valid for 10 minutes.</div>
<form method="post" action="/portal/otp" class="otpwrap">
<label for="otp">One-time password</label>
<input type="text" id="otp" name="otp" maxlength="6" autocomplete="off" inputmode="numeric">
<div style="margin-top:14px"><button type="submit" id="btnVerify">Verify</button></div></form>
<div class="pnote">Attempts used: {s['otp_tries']} of 3.</div></div>""", 1)


@router.post("/otp")
def otp_post(request: Request, otp: str = Form("")):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    if otp.strip() != s["otp"]:
        tries = s["otp_tries"] + 1
        set_sess(s["sid"], otp_tries=tries)
        if tries >= 3:
            set_sess(s["sid"], stage="verify")
            return verify_get(request, "Too many incorrect OTP attempts. Start again.")
        return otp_get(request, f"Incorrect OTP. {3 - tries} attempt(s) left.")
    set_sess(s["sid"], stage="form")
    db.ex("UPDATE sms SET read_at=? WHERE code=? AND read_at IS NULL", (db.now(), s["otp"]))
    return RedirectResponse("/portal/form", status_code=303)


@router.get("/form", response_class=HTMLResponse)
def form_get(request: Request, error: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (s["consumer_no"],))
    banner = f'<div class="pbanner err" id="valError"><b>&#9888;</b><div>{error}</div></div>' if error else ""
    return shell("Application form", banner + f"""
<div class="pcard"><h4>Applicant and plant details</h4>
<div class="pd">Details must match your electricity bill and your Aadhaar. Sanctioned load on record
for this connection is {pc['sanctioned_load']:.2f} kW.</div>
<form method="post" action="/portal/form"><div class="pf">
<div class="f wide"><label for="applicantName">Applicant name</label>
<input type="text" id="applicantName" name="applicant_name" autocomplete="off"></div>
<div class="f"><label for="category">Category</label><select id="category" name="category">
<option value="">Select</option><option>Residential</option><option>Commercial</option>
<option>Industrial</option><option>Housing society</option></select></div>
<div class="f"><label for="mobile2">Mobile</label>
<input type="text" id="mobile2" name="mobile" maxlength="10" autocomplete="off"></div>
<div class="f wide"><label for="address">Installation address</label>
<input type="text" id="address" name="address" autocomplete="off"></div>
<div class="f"><label for="pin">PIN code</label>
<input type="text" id="pin" name="pin" maxlength="6" autocomplete="off"></div>
<div class="f"><label for="bank">Bank account for subsidy</label>
<input type="text" id="bank" name="bank" autocomplete="off"></div>
<div class="f"><label for="load">Sanctioned load (kW)</label>
<input type="text" id="load" name="load" autocomplete="off"></div>
<div class="f"><label for="capacity">Proposed capacity (kW)</label>
<input type="text" id="capacity" name="capacity" autocomplete="off"></div>
<div class="f"><label for="roofArea">Roof area (sq.m)</label>
<input type="text" id="roofArea" name="roof_area" autocomplete="off"></div>
<div class="f"><label for="moduleType">Module technology</label>
<select id="moduleType" name="module_type"><option value="">Select</option>
<option>Mono PERC (DCR)</option><option>Bifacial (DCR)</option><option>Polycrystalline</option>
</select></div>
<div class="f wide"><label for="vendor">Registered vendor code</label>
<input type="text" id="vendor" name="vendor" autocomplete="off"></div>
<div class="f wide"><button type="submit" id="btnSaveContinue">Save and continue</button></div>
</div></form></div>""", 2)


@router.post("/form")
def form_post(request: Request, applicant_name: str = Form(""), category: str = Form(""),
              mobile: str = Form(""), address: str = Form(""), pin: str = Form(""),
              bank: str = Form(""), load: str = Form(""), capacity: str = Form(""),
              roof_area: str = Form(""), module_type: str = Form(""), vendor: str = Form("")):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    missing = [k for k, v in {"applicant name": applicant_name, "category": category,
                              "address": address, "PIN code": pin, "sanctioned load": load,
                              "proposed capacity": capacity, "module technology": module_type,
                              "vendor code": vendor}.items() if not str(v).strip()]
    if missing:
        return form_get(request, "These fields are required: " + ", ".join(missing) + ".")
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (s["consumer_no"],))
    try:
        cap = float(capacity)
    except ValueError:
        return form_get(request, "Proposed capacity must be a number in kW.")
    if cap > float(pc["sanctioned_load"]) + 0.001:
        return form_get(request, f"Proposed capacity {cap:.2f} kW exceeds the sanctioned load "
                                 f"{pc['sanctioned_load']:.2f} kW. Apply for a load enhancement first.")
    set_sess(s["sid"], stage="docs", data={"applicant_name": applicant_name, "category": category,
                                           "mobile": mobile, "address": address, "pin": pin,
                                           "bank": bank, "load": load, "capacity": capacity,
                                           "roof_area": roof_area, "module_type": module_type,
                                           "vendor": vendor})
    return RedirectResponse("/portal/docs", status_code=303)


@router.get("/docs", response_class=HTMLResponse)
def docs_get(request: Request, error: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    banner = f'<div class="pbanner err" id="valError"><b>&#9888;</b><div>{error}</div></div>' if error else ""
    held = json.loads(s["data"] or "{}").get("uploads") or {}
    if held:
        # Files already attached earlier in this session, as a real portal would remember.
        lst = "".join(f"""<div class="upr"><label>{lbl}</label><span style="font-size:11.5px">
{held[i]['name']} &middot; {held[i]['bytes'] // 1024} KB &middot; <b style="color:#146332">
attached</b></span></div>""" for i, lbl in UPLOAD_FIELDS if i in held)
        return shell("Documents", banner + f"""
<div class="pcard"><h4>Supporting documents</h4>
<div class="pd">These files are already attached to this application.</div>{lst}
<form method="post" action="/portal/docs">
<div style="margin-top:13px"><button type="submit" id="btnUpload">Continue</button></div>
</form></div>""", 3)
    rows = "".join(f"""<div class="upr"><label for="{i}">{lbl}</label>
<input type="file" id="{i}" name="{i}" accept=".pdf,.jpg,.jpeg,.png"></div>"""
                   for i, lbl in UPLOAD_FIELDS)
    return shell("Documents", banner + f"""
<div class="pcard"><h4>Attach supporting documents</h4>
<div class="pd">PDF, JPG or PNG. All four are required.</div>
<form method="post" action="/portal/docs" enctype="multipart/form-data">{rows}
<div style="margin-top:13px"><button type="submit" id="btnUpload">Upload and continue</button></div>
</form></div>""", 3)


@router.post("/docs")
async def docs_post(request: Request, docBill: UploadFile = File(None),
                    docAadhaar: UploadFile = File(None), docPassbook: UploadFile = File(None),
                    docRoof: UploadFile = File(None)):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    files = {"docBill": docBill, "docAadhaar": docAadhaar, "docPassbook": docPassbook,
             "docRoof": docRoof}
    missing = [k for k, f in files.items() if f is None or not f.filename]
    if missing and (json.loads(s["data"] or "{}").get("uploads")):
        set_sess(s["sid"], stage="security")
        return RedirectResponse("/portal/security", status_code=303)
    if missing:
        return docs_get(request, "All four documents are required. Missing: " + ", ".join(missing) + ".")
    out = DOCS / "portal" / s["sid"]
    out.mkdir(parents=True, exist_ok=True)
    saved = {}
    for k, f in files.items():
        blob = await f.read()
        p = out / f"{k}_{f.filename}"
        p.write_bytes(blob)
        saved[k] = {"name": f.filename, "bytes": len(blob)}
    set_sess(s["sid"], stage="security", data={"uploads": saved})
    return RedirectResponse("/portal/security", status_code=303)


@router.get("/security", response_class=HTMLResponse)
def security_get(request: Request, error: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    cap = s["captcha"]
    if not cap:
        cap = "".join(random.choice(string.ascii_uppercase.replace("O", "").replace("I", "") +
                                    "23456789") for _ in range(5))
        set_sess(s["sid"], captcha=cap)
    banner = f'<div class="pbanner err" id="valError"><b>&#9888;</b><div>{error}</div></div>' if error else ""
    return shell("Security check", banner + f"""
<div class="pcard"><h4>Security check</h4>
<div class="pd">Type the characters shown below. This step confirms a person is present.</div>
<form method="post" action="/portal/security">
<div style="display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap">
<span class="capimg" id="captcha">{cap}</span>
<div style="flex:1;min-width:150px"><label for="captchaInput">Enter the code</label>
<input type="text" id="captchaInput" name="code" maxlength="5" autocomplete="off"></div></div>
<div style="margin-top:14px"><button type="submit" id="btnCaptcha">Continue</button></div>
</form></div>""", 4)


@router.post("/security")
def security_post(request: Request, code: str = Form("")):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    if code.strip().upper() != (s["captcha"] or ""):
        return security_get(request, "The code did not match. Try again.")
    set_sess(s["sid"], stage="review")
    return RedirectResponse("/portal/review", status_code=303)


@router.get("/review", response_class=HTMLResponse)
def review_get(request: Request, error: str = "", code: str = ""):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    d = json.loads(s["data"] or "{}")
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (s["consumer_no"],))
    banner = ""
    if error:
        banner = (f'<div class="pbanner err" id="valError"><b>&#9888;</b><div><b>Submission '
                  f'rejected.</b> {error}<br><span style="opacity:.75">Error reference: '
                  f'<span id="errCode">{code}</span></span></div></div>')
    rows = [("Applicant name", d.get("applicant_name", "")),
            ("Consumer number", s["consumer_no"]),
            ("Name on connection", pc["billed_name"]),
            ("Category", d.get("category", "")),
            ("Installation address", d.get("address", "")),
            ("PIN code", d.get("pin", "")),
            ("Sanctioned load", f"{float(d.get('load') or 0):.2f} kW"),
            ("Proposed capacity", f"{float(d.get('capacity') or 0):.2f} kW"),
            ("Module technology", d.get("module_type", "")),
            ("Registered vendor", d.get("vendor", "")),
            ("Documents attached", f"{len(d.get('uploads', {}))} files")]
    tbl = "".join(f"<tr><td>{k}</td><td id=rv_{i}>{v}</td></tr>" for i, (k, v) in enumerate(rows))
    return shell("Review and submit", banner + f"""
<div class="pcard"><h4>Review your application</h4>
<div class="pd">Check every field. After submission, changes require a correction request.</div>
<table>{tbl}</table>
<div style="margin-top:12px"><a href="/portal/form" id="btnEdit"
style="font-size:11.5px;color:#123A6B">Edit applicant details</a></div>
<form method="post" action="/portal/review" style="margin-top:10px">
<label style="display:flex;gap:9px;align-items:flex-start;font-weight:400;font-size:11.5px;
color:#4A5663"><input type="checkbox" id="declaration" name="declaration" value="1"
style="width:auto;margin-top:2px">
<span>I declare that the information above is true and that I have not availed this subsidy
before.</span></label>
<div style="margin-top:14px"><button type="submit" id="btnSubmit">Submit application</button></div>
</form></div>""", 5)


@router.post("/review")
def review_post(request: Request, declaration: str = Form("")):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    d = json.loads(s["data"] or "{}")
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (s["consumer_no"],))
    if not declaration:
        return review_get(request, "The declaration must be accepted before submitting.", "VAL-0004")
    if norm(d.get("applicant_name")) != norm(pc["billed_name"]):
        return review_get(
            request,
            f"Applicant name does not match the name on the electricity bill for consumer "
            f"{s['consumer_no']}. The register holds &ldquo;{pc['billed_name']}&rdquo;. Correct the "
            f"name or upload a name-change certificate.", "VAL-0712")
    if db.one("SELECT 1 FROM portal_applications WHERE consumer_no=?", (s["consumer_no"],)):
        return review_get(request, "An application already exists against this consumer number.",
                          "VAL-0901")
    app_no = f"PMSG/MH/{datetime.now().year}/1{random.randint(22500, 23400)}"
    db.ex("""INSERT INTO portal_applications(application_no,consumer_no,applicant_name,capacity,
             submitted_at,payload) VALUES(?,?,?,?,?,?)""",
          (app_no, s["consumer_no"], d.get("applicant_name"), float(d.get("capacity") or 0),
           db.now(), json.dumps(d, ensure_ascii=False)))
    set_sess(s["sid"], stage="done", data={"application_no": app_no})
    return RedirectResponse("/portal/ack", status_code=303)


@router.get("/ack", response_class=HTMLResponse)
def ack(request: Request):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/verify")
    d = json.loads(s["data"] or "{}")
    app_no = d.get("application_no", "")
    row = db.one("SELECT * FROM portal_applications WHERE application_no=?", (app_no,))
    if not row:
        return RedirectResponse("/portal/verify")
    return shell("Acknowledgement", f"""
<div class="pbanner ok"><b>&#10003;</b><div><b>Application submitted.</b> It has been registered and
forwarded to the distribution company for technical feasibility.</div></div>
<div class="pcard"><h4>Acknowledgement</h4>
<div class="pd">Save this reference. An SMS confirmation has been sent to the registered mobile.</div>
<table>
<tr><td>Application number</td><td><b id="applicationNo">{app_no}</b></td></tr>
<tr><td>Applicant</td><td>{row['applicant_name']}</td></tr>
<tr><td>Consumer number</td><td>{row['consumer_no']}</td></tr>
<tr><td>Capacity applied</td><td>{row['capacity']:.2f} kW</td></tr>
<tr><td>Submitted on</td><td>{row['submitted_at'].replace('T', ' ')}</td></tr>
<tr><td>Next step</td><td>Technical feasibility by the distribution company (7 to 15 days)</td></tr>
</table></div>""")


@router.get("/reset")
def reset(request: Request):
    """Clears sandbox applications so the demo can be run again from a clean state."""
    db.ex("DELETE FROM portal_applications")
    db.ex("DELETE FROM portal_sessions")
    return Response("portal sandbox reset", media_type="text/plain")
