"""Sandbox of the rooftop-solar loan journey on Jan Samarth, in the steps the client described
(basic details, address, Aadhaar OTP, bank and branch, then an in-principle approval letter).
The real portal was not shown on the call and sits behind bot protection, so this is a
stand-in, built so the co-pilot's split of work can be tested: it fills the basic details and
the address; the customer types their own Aadhaar number and OTP and picks the bank.

It exists so the co-pilot can be exercised end to end without touching Jan Samarth.
"""
import html, json, re, secrets
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import db

router = APIRouter(prefix="/jansamarth")
e = html.escape
BANKS = {"Bank of Maharashtra": ["Nashik Road", "Panchavati", "Manchar"], "State Bank of India": ["Nashik Main", "Pune Camp"]}
CSS = """body{margin:0;font:14px Arial,sans-serif;background:#F5F7FB;color:#1d2733}.top{background:#0E3C78;color:#fff;
padding:12px 18px;font-weight:700}.main{max-width:760px;margin:18px auto;background:#fff;padding:20px;border-radius:8px}
.steps{display:flex;gap:6px;margin-bottom:14px}.steps div{flex:1;padding:6px;text-align:center;background:#E3E8F0;border-radius:4px;font-size:12px}
.steps .on{background:#0E3C78;color:#fff}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.fg label{display:block;margin-bottom:4px}
.fg input,.fg select,.fg textarea{width:100%;box-sizing:border-box;padding:8px;border:1px solid #bbb;border-radius:4px}
.btn{background:#0E3C78;color:#fff;border:0;padding:9px 22px;border-radius:4px;cursor:pointer}.err{background:#FDECEA;color:#8A1C12;padding:10px;margin-bottom:10px}
.ok{background:#E6F6EE;color:#13603B;padding:12px}.sandbox{background:#8E231B;color:#fff;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;padding:3px;text-align:center}"""
STEPS = ["Basic Details", "Address Details", "Aadhaar Verification", "Select Bank"]


# the real portal carries a "Support / Grievance" form on every page; the helper must leave it alone
HELP = """<div class="help" style="margin-top:28px;padding:12px;border-top:1px solid #ddd"><b>Need help?</b>
<label><input type="radio" name="sg" value="s"> Support</label> <label><input type="radio" name="sg" value="g"> Grievance</label>
<form id="helpForm" onsubmit="return false"><input name="name" placeholder="Enter your full name"> <input name="mobileNumber" placeholder="10 digit mobile number">
<input type="email" name="email" placeholder="Enter your email address"> <input name="applicationId" placeholder="If application is completed">
<input name="stageOfApplication" placeholder="Stage of application"> <input name="subject" placeholder="Subject of Query">
<textarea name="description" placeholder="Write in brief"></textarea></form></div>"""


def shell(step, body):
    bar = "".join(f'<div class="{"on" if i == step else ""}">{i}. {t}</div>' for i, t in enumerate(STEPS, 1))
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>JanSamarth - Rooftop Solar Loan</title>
<style>{CSS}</style></head><body><div class="sandbox">Demo sandbox &mdash; not Jan Samarth</div>
<div class="top">JanSamarth &middot; Loan application for Rooftop Solar</div><div class="main">
{f'<div class="steps">{bar}</div>' if step else ''}{body}{HELP}</div></body></html>""")


def _sess(request):
    sid = request.cookies.get("jsid") or ""
    r = db.one("SELECT * FROM js_applications WHERE ref=?", ("S-" + sid,)) if sid else None
    return sid, (json.loads(r["data"]) if r else {})


def _save(sid, data):
    db.ex("""INSERT INTO js_applications(ref,data) VALUES(?,?) ON CONFLICT(ref) DO UPDATE SET data=excluded.data""",
          ("S-" + sid, json.dumps(data)))


def fg(i, label, ctl):
    return f'<div class="fg"><label for="{i}">{label}</label>{ctl}</div>'


@router.get("/", response_class=HTMLResponse)
def start(request: Request, step: int = 1, error: str = ""):
    sid, data = _sess(request)
    msg = f'<div class="err">{e(error)}</div>' if error else ""
    if step == 1:
        body = f"""<h3>Basic Details</h3>{msg}<div class="grid">
{fg('an', 'Applicant Name (as per Aadhaar)', '<input id="an" name="name">')}
{fg('mob', 'Mobile Number', '<input id="mob" name="mobile">')}
{fg('em', 'Email ID', '<input id="em" name="email">')}
{fg('cno', 'Electricity Consumer Number', '<input id="cno" name="consumer_no">')}
{fg('dob', 'Date of Birth', '<input id="dob" type="date" name="dob">')}
{fg('cap', 'Proposed Rooftop Solar Capacity (kW)', '<input id="cap" name="capacity">')}
{fg('pc', 'Project Cost (Rs.)', '<input id="pc" name="cost">')}
{fg('la', 'Loan Amount Required (Rs.)', '<input id="la" name="loan">')}</div>"""
    elif step == 2:
        body = f"""<h3>Address Details</h3>{msg}<div class="grid">
{fg('ad', 'Address', '<textarea id="ad" name="address"></textarea>')}
{fg('pin', 'Pin Code', '<input id="pin" name="pin">')}
{fg('dis', 'District', '<input id="dis" name="district">')}
{fg('st', 'State', '<select id="st" name="state"><option value="">Select</option><option>Gujarat</option><option>Maharashtra</option></select>')}</div>"""
    elif step == 3:
        # as on the live portal: two ways to verify, the number in three boxes of four (the first two hidden like a
        # password), a consent box, and focus that jumps to the next box after four digits
        body = f"""<h3>Aadhaar Verification</h3>{msg}<p>Verify identity with Aadhaar. A six digit OTP will be sent to the mobile
registered with it.</p>
<p><label><input type="radio" id="mat-radio-2-input" name="mat-radio-group-0" value="aadhaar" checked> Aadhaar number</label>
&nbsp; <label><input type="radio" id="mat-radio-3-input" name="mat-radio-group-0" value="vid"> Aadhaar Virtual ID</label></p>
<div style="margin:10px 0"><div style="margin-bottom:4px">Aadhaar number *</div>
<input type="password" id="aadharNoFirst" name="aadharNoFirst" maxlength="4" inputmode="numeric" style="width:90px;padding:8px">
<input type="password" id="aadharNoSecond" name="aadharNoSecond" maxlength="4" inputmode="numeric" style="width:90px;padding:8px">
<input type="text" id="aadharNoThird" name="aadharNoThird" maxlength="4" inputmode="numeric" style="width:90px;padding:8px"></div>
<p><label><input type="checkbox" id="consent" name="consent" value="yes"> I provide my consent to share my details with the issuer for
the purpose of fetching my details.</label></p>
<div class="grid">{fg('otp', 'Enter OTP', '<input id="otp" name="otp" inputmode="numeric">')}</div><p style="font-size:12px;color:#777">Sandbox OTP: 246810</p>
<script>['aadharNoFirst', 'aadharNoSecond', 'aadharNoThird'].forEach(function (id, i, all) {{ var el = document.getElementById(id);
  el.addEventListener('input', function () {{ if (el.value.length >= 4 && all[i + 1]) document.getElementById(all[i + 1]).focus(); }}); }});</script>"""
    else:
        banks = "".join(f"<option>{b}</option>" for b in BANKS)
        branches = "".join(f"<option>{x}</option>" for v in BANKS.values() for x in v)
        body = f"""<h3>Select Bank</h3>{msg}<div class="grid">{fg('bk', 'Bank Name', f'<select id="bk" name="bank"><option value="">Select</option>{banks}</select>')}
{fg('brn', 'Branch', f'<select id="brn" name="branch"><option value="">Select</option>{branches}</select>')}</div>"""
    r = shell(step, f"""<form method="post" action="/jansamarth/?step={step}">{body}
<p style="text-align:right"><button class="btn" id="btnNext">{'Submit Application' if step == 4 else 'Next'}</button></p></form>""")
    if not sid:
        r.set_cookie("jsid", secrets.token_hex(8), samesite="lax")
    return r


@router.post("/")
async def step_post(request: Request, step: int = 1):
    sid, data = _sess(request)
    if not sid:
        return RedirectResponse("/jansamarth/", 303)
    f = {k: str(v).strip() for k, v in (await request.form()).items()}
    back = lambda m: RedirectResponse(f"/jansamarth/?step={step}&error={m}", 303)
    if step == 1:
        if not f.get("name") or not re.fullmatch(r"[6-9]\d{9}", f.get("mobile", "")) or not re.fullmatch(r"\d{9,14}", f.get("consumer_no", "")):
            return back("Enter the applicant name, a 10-digit mobile and the consumer number")
        if not f.get("dob") or not f.get("loan", "").isdigit():
            return back("Enter the date of birth and the loan amount")
    elif step == 2:
        if not f.get("address") or not re.fullmatch(r"\d{6}", f.get("pin", "")) or not f.get("state"):
            return back("Enter the address, a 6-digit pin code and the state")
    elif step == 3:
        aad = f.get("aadharNoFirst", "") + f.get("aadharNoSecond", "") + f.get("aadharNoThird", "")
        if f.get("mat-radio-group-0") != "aadhaar" or not re.fullmatch(r"\d{12}", aad) or f.get("otp") != "246810" or f.get("consent") != "yes":
            return back("Aadhaar number, consent or OTP is not correct")
        f = {"aadhaar_verified": "yes", "aadhaar_last4": aad[-4:]}
    else:
        if f.get("bank") not in BANKS or f.get("branch") not in BANKS[f.get("bank")]:
            return back("Select the bank and a branch of that bank")
        data.update(f)
        if data.get("aadhaar_verified") != "yes":
            return RedirectResponse("/jansamarth/?step=3&error=Verify+Aadhaar+first", 303)
        ref = f"JS-RTS-{secrets.randbelow(10 ** 7):07d}"
        db.ex("INSERT INTO js_applications(ref,consumer_no,applicant,data,bank,branch,submitted_at) VALUES(?,?,?,?,?,?,?)",
              (ref, data.get("consumer_no"), data.get("name"), json.dumps(data), data["bank"], data["branch"], db.now()))
        db.ex("DELETE FROM js_applications WHERE ref=?", ("S-" + sid,))
        r = RedirectResponse(f"/jansamarth/done?ref={ref}", 303)
        r.delete_cookie("jsid")
        return r
    data.update(f)
    _save(sid, data)
    return RedirectResponse(f"/jansamarth/?step={step + 1}", 303)


@router.get("/done", response_class=HTMLResponse)
def done(ref: str):
    a = db.one("SELECT * FROM js_applications WHERE ref=?", (ref,))
    if not a:
        return shell(0, "<p>Not found</p>")
    return shell(0, f"""<div class="ok">Your loan application has been submitted to {e(a['bank'])}, {e(a['branch'])} branch.
In-principle approval is generated.</div><p>Reference No: <b id="jsRef">{e(a['ref'])}</b></p>
<p><a class="btn" href="/jansamarth/letter/{e(a['ref'])}.pdf">Download In-principle Approval Letter</a></p>""")


@router.get("/letter/{ref}.pdf")
def letter(ref: str):
    a = db.one("SELECT * FROM js_applications WHERE ref=?", (ref,))
    if not a:
        return Response(status_code=404)
    import fitz
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((50, 70), "In-principle approval (sandbox)", fontsize=15)
    for i, line in enumerate([f"Reference: {a['ref']}", f"Applicant: {a['applicant']}", f"Consumer no.: {a['consumer_no']}",
                              f"Bank: {a['bank']}, {a['branch']} branch"]):
        pg.insert_text((50, 110 + 18 * i), line, fontsize=11)
    return Response(doc.tobytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{ref}_in_principle.pdf"'})
