"""Sandbox of the vendor side of the national rooftop portal, rebuilt from the screens the
client shared: Vendor Consent (approve a customer who picked you), My Application, and the
Upload Agreement dialog (total cost + agreement copy, JPG/JPEG/PDF up to 2 MB).

Milestone 2 adds the Site Feasibility Report dialog and the 5-step Submit Installation (labels
from the client's screens and MNRE's vendor manual), and a sandbox-only control standing in for the
customer accepting the installation and the DISCOM moving the application on, so the status list
the co-pilot reads changes the way the real one does.

Applications come from the consumer-side sandbox in portal.py. Used to exercise the co-pilot
end to end without touching the real portal.
"""
import html, json, re
from fastapi import APIRouter, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from . import db
from .config import vendor

router = APIRouter(prefix="/pmsg/vendor")
e = html.escape
MAX_AGREEMENT = 2 * 1024 * 1024

CSS = """body{margin:0;font:13px Poppins,Arial,sans-serif;color:#1E2A39;background:#EEF2F7}
.top{background:#fff;display:flex;align-items:center;gap:14px;padding:10px 18px;border-bottom:1px solid #DDE3EA}
.top b{color:#1B4F8C}.who{margin-left:auto;background:#1B4F8C;color:#fff;border-radius:16px;padding:5px 14px}
.side{position:fixed;left:0;top:52px;bottom:0;width:170px;background:#fff;border-right:1px solid #DDE3EA;padding:10px}
.side a{display:block;padding:8px 10px;color:#1E2A39;text-decoration:none;border-radius:6px}
.side a.on{background:#1B4F8C;color:#fff}.main{margin-left:190px;padding:18px}
h2{font-size:17px;color:#1B4F8C;margin:0 0 12px}table{width:100%;border-collapse:collapse;background:#fff}
th,td{padding:8px 10px;border-bottom:1px solid #E5EAF0;text-align:left;font-size:12px}th{color:#5A6B7E}
.btn{background:#1B4F8C;color:#fff;border:0;border-radius:6px;padding:6px 14px;cursor:pointer;text-decoration:none}
.scrim{position:fixed;inset:0;background:rgba(10,20,35,.45);display:flex;align-items:flex-start;justify-content:center;padding-top:60px}
.dlg{background:#fff;border-radius:8px;width:640px;padding:18px 20px}.dlg h3{margin:0 0 14px;font-size:15px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 18px}.fg label{display:block;font-size:11.5px;margin-bottom:4px}
.fg input{width:100%;box-sizing:border-box;padding:7px;border:1px solid #CBD5E1;border-radius:5px}
.fg input[readonly]{background:#F3F6FA}.hint{font-size:10.5px;color:#1B4F8C;margin-top:3px}
.ok{background:#E6F6EE;color:#13603B;padding:9px 12px;border-radius:6px;margin-bottom:10px}
.err{background:#FDECEA;color:#8A1C12;padding:9px 12px;border-radius:6px;margin-bottom:10px}
.sandbox{background:#8E231B;color:#fff;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;padding:3px;text-align:center}"""


def shell(active, body):
    nav = "".join(f'<a href="/pmsg/vendor/{k}" class="{"on" if k == active else ""}">{t}</a>'
                  for k, t in (("applications", "My Application"), ("consent", "Vendor Consent")))
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>Vendor</title>
<style>{CSS}</style></head><body><div class="sandbox">Demo sandbox &mdash; not the government portal</div>
<div class="top"><b>PM Surya Ghar: Muft Bijli Yojana</b> &middot; vendor &middot; sandbox
<span class="who">{e(vendor()['name'])}</span></div><div class="side">{nav}</div>
<div class="main">{body}</div></body></html>""")


def apps(where="1=1"):
    return db.q(f"""SELECT a.*, v.consented_at, v.agreement_at, v.cost, c.msisdn, i.sfr_at, i.install_at,
                    i.stage AS istage FROM portal_applications a
                    LEFT JOIN pmsg_vendor v ON v.application_no=a.application_no
                    LEFT JOIN portal_consumers c ON c.consumer_no=a.consumer_no
                    LEFT JOIN pmsg_install i ON i.application_no=a.application_no
                    WHERE {where} ORDER BY a.submitted_at DESC""")


# after installation the application moves on in this order (customer, then DISCOM, then REC)
LATER = ["Installation (Consumer Acceptance Pending)", "Inspection (Pending)", "Project Commissioning (Pending)",
         "Subsidy Request (Pending)", "Subsidy Disbursal (Pending)", "Subsidy Disbursal (Completed)"]


def status_of(a):
    if a["istage"]:
        return a["istage"]
    return "Installation (Pending)" if a["agreement_at"] else "Upload Agreement (Pending)"


@router.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/pmsg/vendor/applications")


@router.get("/consent", response_class=HTMLResponse)
def consent():
    rows = "".join(f"""<tr><td>{e(a['application_no'])}</td><td>{e(a['consumer_no'])}</td>
<td>{e(a['applicant_name'])}</td><td>{a['capacity']:.2f}</td>
<td><form method="post" action="/pmsg/vendor/consent/{e(a['application_no'])}">
<button class="btn" type="submit">Approve</button></form></td></tr>""" for a in apps("v.consented_at IS NULL"))
    return shell("consent", f"""<h2>Vendor Consent</h2><table><tr><th>Application Number</th>
<th>Consumer Number</th><th>Consumer Name</th><th>Proposed Capacity (kW)</th><th>Action</th></tr>
{rows or '<tr><td colspan=5>No data found.</td></tr>'}</table>""")


@router.post("/consent/{app_no}")
def consent_post(app_no: str):
    if db.one("SELECT 1 FROM portal_applications WHERE application_no=?", (app_no,)):
        db.ex("""INSERT INTO pmsg_vendor(application_no,consented_at) VALUES(?,?)
                 ON CONFLICT(application_no) DO UPDATE SET consented_at=excluded.consented_at""",
              (app_no, db.now()))
    return RedirectResponse("/pmsg/vendor/consent", 303)


def table():
    rows = "".join(f"""<tr><td>{e(a['application_no'])}</td><td>{e(a['consumer_no'])}</td>
<td>{e(a['applicant_name'])}</td><td>{e(a['msisdn'] or '')}</td><td>{a['capacity']:.3f}</td>
<td>{e(status_of(a))}</td>
<td><a class="btn" href="/pmsg/vendor/agreement?app={e(a['application_no'])}">Update Agreement</a>
<a class="btn" href="/pmsg/vendor/sfr?app={e(a['application_no'])}">Site Feasibility Report</a>
<a class="btn" href="/pmsg/vendor/install?app={e(a['application_no'])}">Submit Installation</a></td></tr>"""
                   for a in apps("v.consented_at IS NOT NULL"))
    return f"""<h2>My Application</h2><table><tr><th>Application Number</th><th>Consumer Number</th>
<th>Consumer Name</th><th>Mobile No.</th><th>Proposed Capacity (kWp)</th><th>Status</th><th>Action</th></tr>
{rows or '<tr><td colspan=7>No data found.</td></tr>'}</table>"""


@router.get("/applications", response_class=HTMLResponse)
def applications():
    return shell("applications", table())


@router.get("/agreement", response_class=HTMLResponse)
def agreement(app: str, error: str = "", done: int = 0):
    a = next((x for x in apps() if x["application_no"] == app), None)
    if not a or not a["consented_at"]:
        return shell("applications", table() + '<div class="err">Approve this customer in Vendor Consent first.</div>')
    msg = ('<div class="ok">Agreement updated successfully.</div>' if done else
           f'<div class="err">{e(error)}</div>' if error else "")
    locked = " disabled" if a["agreement_at"] else ""
    ro = lambda v: f'<input type="text" readonly value="{e(v)}">'
    return shell("applications", table() + f"""<div class="scrim"><div class="dlg" role="dialog" aria-label="Upload Agreement">
<h3>Upload Agreement</h3>{msg}<form method="post" action="/pmsg/vendor/agreement?app={e(app)}" enctype="multipart/form-data">
<div class="grid"><div class="fg"><label>Customer Name:</label>{ro(a['applicant_name'])}</div>
<div class="fg"><label>Consumer Number:</label>{ro(a['consumer_no'])}</div>
<div class="fg"><label>Application Number:</label>{ro(a['application_no'])}</div>
<div class="fg"><label for="cost">Total Cost of RTS Installation:*</label>
<input type="text" id="cost" name="cost" value="{e(a['cost'] or '')}"{locked}>
<div class="hint">(Inclusive of Taxes and all other charges as indicated in Agreement)</div></div>
<div class="fg"><label for="agreementCopy">Agreement Copy:*</label>
<input type="file" id="agreementCopy" name="agreement" accept=".jpg,.jpeg,.pdf"{locked}>
<div class="hint">File Formats only accepts JPG,JPEG or PDF. Maximum Size 2MB</div></div></div>
<p style="text-align:right"><button class="btn" type="submit" id="btnSubmitAgreement"{locked}>Submit</button></p>
</form></div></div>""")


@router.post("/agreement")
async def agreement_post(app: str, cost: str = Form(""), agreement: UploadFile = File(None)):
    back = lambda m: RedirectResponse(f"/pmsg/vendor/agreement?app={app}&error={m}", 303)
    if not cost.replace(",", "").strip().isdigit():
        return back("Enter the total cost in rupees")
    if agreement is None or not agreement.filename:
        return back("Agreement copy is required")
    blob = await agreement.read()
    if not (blob.startswith(b"%PDF") or blob[:3] == b"\xff\xd8\xff"):
        return back("File Formats only accepts JPG,JPEG or PDF")
    if len(blob) > MAX_AGREEMENT:
        return back("Maximum Size 2MB")
    db.ex("""UPDATE pmsg_vendor SET cost=?, agreement_file=?, agreement_bytes=?, agreement_at=?
             WHERE application_no=?""", (cost.replace(",", "").strip(), agreement.filename, len(blob),
                                          db.now(), app))
    return RedirectResponse(f"/pmsg/vendor/agreement?app={app}&done=1", 303)


# ------------------------------- site feasibility report -------------------------------
def _app(app):
    return next((x for x in apps() if x["application_no"] == app), None)


def _ins(app):
    r = db.one("SELECT * FROM pmsg_install WHERE application_no=?", (app,))
    return r or {"application_no": app, "sfr": None, "sfr_at": None, "install": None, "install_at": None, "stage": None}


def _save_ins(app, **kw):
    cur = _ins(app)
    cur.update(kw)
    db.ex("""INSERT INTO pmsg_install(application_no,sfr,sfr_at,install,install_at,stage) VALUES(?,?,?,?,?,?)
             ON CONFLICT(application_no) DO UPDATE SET sfr=excluded.sfr,sfr_at=excluded.sfr_at,
             install=excluded.install,install_at=excluded.install_at,stage=excluded.stage""",
          (app, cur["sfr"], cur["sfr_at"], cur["install"], cur["install_at"], cur["stage"]))


def yesno(name, label):
    return (f'<div class="fg"><label>{label}<span style="color:#C00">*</span></label>'
            f'<label style="display:inline"><input type="radio" name="{name}" value="Y"> Yes</label> '
            f'<label style="display:inline"><input type="radio" name="{name}" value="N"> No</label></div>')


@router.get("/sfr", response_class=HTMLResponse)
def sfr(app: str, error: str = "", done: int = 0):
    a = _app(app)
    if not a or not a["consented_at"]:
        return shell("applications", table() + '<div class="err">Approve this customer in Vendor Consent first.</div>')
    msg = ('<div class="ok">Site Feasibility Report submitted successfully.</div>' if done else
           f'<div class="err">{e(error)}</div>' if error else "")
    lock = " disabled" if _ins(app)["sfr_at"] else ""
    return shell("applications", table() + f"""<div class="scrim"><div class="dlg" role="dialog" aria-label="Site Feasibility Report">
<h3>Site Feasibility Report</h3>{msg}<form method="post" action="/pmsg/vendor/sfr?app={e(app)}" enctype="multipart/form-data">
<fieldset style="border:0;padding:0;margin:0"{lock}><div class="grid">
{yesno('roofLoad', 'Roof has enough load bearing capacity:')}
{yesno('shadowFree', 'Availability of shadow free roof for the RTS installation:')}
<div class="fg"><label for="roofArea">Available shadow free roof area [Meter Square]:*</label><input type="text" id="roofArea" name="area"></div>
<div class="fg"><label for="permCap">Permissible RTS Installation Capacity By Vendor(kW):*</label><input type="text" id="permCap" name="capacity"></div>
{yesno('visited', 'Vendor has visited the installation site and carried out the assessment:')}<div></div>
<div class="fg"><label for="qAmt">Quotation Amount(Rs.):*</label><input type="text" id="qAmt" name="amount"></div>
<div class="fg"><label for="qDoc">Quotation Document:*</label><input type="file" id="qDoc" name="quotation" accept=".pdf"></div>
<div class="fg"><label for="emp">Name of vendor employee visited the project site:*</label><input type="text" id="emp" name="employee"></div>
<div class="fg"><label for="empNo">Contact Number:*</label><input type="text" id="empNo" name="employee_phone"></div></div>
<p><label><input type="checkbox" name="certify" value="1"> This is to certify that the proposed equipment specifications and
equipment to be installed for the said project shall be aligned with the technical standards and specifications set
forth in the PM Surya Ghar: Muft Bijli Yojana scheme guidelines. *</label></p>
<div class="fg"><label for="preImg">Upload photo (Pre Installation):*</label><input type="file" id="preImg" name="photo" accept=".jpg,.jpeg,.png"></div>
<p style="text-align:right"><button class="btn" type="submit" id="btnSubmitSfr">Submit</button></p></fieldset>
</form></div></div>""")


@router.post("/sfr")
async def sfr_post(app: str, roofLoad: str = Form(""), shadowFree: str = Form(""), area: str = Form(""),
                   capacity: str = Form(""), visited: str = Form(""), amount: str = Form(""),
                   employee: str = Form(""), employee_phone: str = Form(""), certify: str = Form(""),
                   quotation: UploadFile = File(None), photo: UploadFile = File(None)):
    back = lambda m: RedirectResponse(f"/pmsg/vendor/sfr?app={app}&error={m}", 303)
    if not all(x in ("Y", "N") for x in (roofLoad, shadowFree, visited)):
        return back("Answer every Yes/No question")
    try:
        if float(area) <= 0 or float(capacity) <= 0:
            raise ValueError
    except ValueError:
        return back("Enter the roof area and permissible capacity as numbers")
    if not amount.replace(",", "").strip().isdigit():
        return back("Enter the quotation amount in rupees")
    if not employee.strip() or not re.fullmatch(r"[6-9]\d{9}", employee_phone.strip()):
        return back("Enter the employee's name and 10-digit contact number")
    if certify != "1":
        return back("Tick the certification")
    files = {}
    for f, kind in ((quotation, "quotation"), (photo, "photo")):
        if f is None or not f.filename:
            return back(f"Upload the {kind}")
        b = await f.read()
        if len(b) > 2 * 1024 * 1024:
            return back(f"The {kind} is over 2 MB")
        if kind == "quotation" and not b.startswith(b"%PDF"):
            return back("The quotation must be a PDF")
        if kind == "photo" and not (b[:3] == b"\xff\xd8\xff" or b.startswith(b"\x89PNG")):
            return back("The photo must be JPG or PNG")
        files[kind] = [f.filename, len(b)]
    _save_ins(app, sfr=json.dumps({"roof_load": roofLoad, "shadow_free": shadowFree, "area": area, "capacity": capacity,
                                   "visited": visited, "amount": amount, "employee": employee,
                                   "employee_phone": employee_phone, "files": files}), sfr_at=db.now())
    return RedirectResponse(f"/pmsg/vendor/sfr?app={app}&done=1", 303)


# ------------------------------- submit installation (5 steps) -------------------------------
STEPS = ["Vendor Details", "Inverter & PV Module Details", "Plant Photo & Documents", "Protection Checklist",
         "Final Submission"]
CHECKS = [("spd", "Surge Protection Device (SPD) installed"), ("mcb", "MCB / circuit breaker provided"),
          ("earth", "Earthing done as per the standards"), ("la", "Lightning Arrester installed")]


def _steps_bar(n):
    return '<div style="display:flex;gap:10px;margin:10px 0">' + "".join(
        f'<div style="flex:1;text-align:center;padding:6px;border-radius:14px;background:{"#F29B1D" if i == n else "#D4DAE2" if i > n else "#2E9E5B"};color:#fff">'
        f'Step 0{i}<br><small>{t}</small></div>' for i, t in enumerate(STEPS, 1)) + "</div>"


def _install_head(a):
    return f"""<h2>Installation Details</h2><table><tr><td>Application Number:</td><td>{e(a['application_no'])}</td>
<td>Consumer Number:</td><td>{e(a['consumer_no'])}</td><td>State:</td><td>MAHARASHTRA</td></tr>
<tr><td>Discom:</td><td>Maharashtra State Electricity Distribution Co. Ltd</td><td>Proposed Capacity (kWp):</td>
<td>{a['capacity']:g}</td><td></td><td></td></tr></table>"""


def _rows(prefix, n, cols):
    head = "".join(f"<th>{c}</th>" for c in ["S.No."] + [c for c, _ in cols] + ["Action"])
    body = "".join("<tr><td>" + str(i + 1) + "</td>" + "".join(
        f'<td><input type="text" name="{prefix}_{k}_{i}"></td>' for _, k in cols) +
        f'<td><button type="button" class="btn" onclick="this.nextElementSibling.hidden=false">+ Add Serial Number</button>'
        f'<textarea name="{prefix}_serial_{i}" aria-label="Serial Numbers" rows="3" hidden></textarea></td></tr>'
        for i in range(n))
    return f"<table><tr>{head}</tr>{body}</table>"


@router.get("/install", response_class=HTMLResponse)
def install(app: str, step: int = 1, error: str = "", done: int = 0):
    a = _app(app)
    if not a or not a["agreement_at"]:
        return shell("applications", table() + '<div class="err">Upload the agreement first.</div>')
    ins = _ins(app)
    if not ins["sfr_at"]:
        return shell("applications", table() + '<div class="err">Submit the Site Feasibility Report first.</div>')
    if ins["install_at"] or done:
        return shell("applications", _install_head(a) + '<div class="ok">Installation details submitted successfully. '
                     'The consumer has to accept them from the consumer login.</div>')
    data = json.loads(ins["install"] or "{}")
    msg = f'<div class="err">{e(error)}</div>' if error else ""
    loc = data.get("location", "")
    head = _install_head(a) + f"""<div class="fg" style="max-width:300px"><label for="locType">Type of Location*</label>
<select id="locType" name="location" form="stepForm"><option value="">Select Location type</option>
{''.join(f'<option{" selected" if loc == o else ""}>{o}</option>' for o in ("Rural", "Urban"))}</select></div>
<h3>Submit Solar Rooftop Installation Details</h3>{_steps_bar(step)}{msg}"""
    if step == 1:
        body = f"""<h3>Project Developer/Vendor Details</h3><div class="grid">
<div class="fg"><label for="vName">Name of Vendor:*</label><input type="text" id="vName" name="vendor" value="{e(data.get('vendor', ''))}"></div>
<div class="fg"><label>View/upload signed copy of the agreement between Vendor and Customer:*</label>
<a href="#">{e(app)}_Agreement.pdf</a></div>
<div class="fg"><label for="lat">Latitude:*</label><input type="text" id="lat" name="lat" value="{e(data.get('lat', '0.00'))}"></div>
<div class="fg"><label for="lng">Enter longitude:*</label><input type="text" id="lng" name="lng" value="{e(data.get('lng', '0.00'))}"></div></div>"""
    elif step == 2:
        body = f"""<div class="fg" style="max-width:300px"><label for="phase">Phase of Solar Inverter*</label>
<select id="phase" name="phase"><option value="">Select</option><option>Single Phase</option><option>Three Phase</option></select></div>
<h3>Solar Inverter Details</h3>{_rows('inv', 3, [('Capacity/Rating(in kW) of each inverter', 'kw'), ('Quantity of Inverter', 'qty'), ('Manufacturer of Inverter', 'make')])}
<h3>Solar PV Modules Details</h3>{_rows('mod', 3, [('Capacity/Rating(in Wp) of each Solar PV Module', 'wp'), ('Quantity of Solar PV Module', 'qty'), ('Manufacturer of Solar PV Module', 'make')])}
<div class="fg" style="max-width:340px"><label for="dcrNo">DCR Certificate Number:*</label><input type="text" id="dcrNo" name="dcr"></div>"""
    elif step == 3:
        body = """<h3>Plant Photo &amp; Documents</h3><div class="fg"><label for="plant">Upload Plant Photo with Geo Coordinates:* (JPG, max 500 KB)</label>
<input type="file" id="plant" name="plant" accept=".jpg,.jpeg"></div>"""
    elif step == 4:
        body = "<h3>Protection Checklist</h3><div class='grid'>" + "".join(yesno(k, t) for k, t in CHECKS) + "</div>"
    else:
        rows = "".join(f"<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>" for k, v in data.items() if k != "serials")
        body = f"""<h3>Final Submission</h3><table>{rows}</table>
<p><label><input type="checkbox" name="declare" value="1"> I hereby declare that the information furnished above is true
and the installation conforms to the technical specifications of the scheme.</label></p>"""
    btn = "Final Submit" if step == 5 else "Save &amp; Next"
    return shell("applications", head + f"""<form id="stepForm" method="post" action="/pmsg/vendor/install?app={e(app)}&step={step}"
enctype="multipart/form-data">{body}<p style="text-align:right"><button class="btn" type="submit" id="btnStep">{btn}</button></p></form>""")


@router.post("/install")
async def install_post(request: Request, app: str, step: int = 1):
    a = _app(app)
    ins = _ins(app)
    if not a or not ins["sfr_at"] or ins["install_at"]:
        return RedirectResponse(f"/pmsg/vendor/install?app={app}", 303)
    form = await request.form()
    data = json.loads(ins["install"] or "{}")
    back = lambda m: RedirectResponse(f"/pmsg/vendor/install?app={app}&step={step}&error={m}", 303)
    if form.get("location") not in ("Rural", "Urban"):
        return back("Select the type of location")
    data["location"] = form.get("location")
    if step == 1:
        try:
            lat, lng = float(form.get("lat") or 0), float(form.get("lng") or 0)
        except ValueError:
            return back("Latitude and longitude must be numbers")
        if not (6 <= lat <= 37.5 and 68 <= lng <= 97.5):
            return back("Enter the latitude and longitude of the site")
        if not (form.get("vendor") or "").strip():
            return back("Enter the name of the vendor")
        data.update(vendor=form.get("vendor").strip(), lat=lat, lng=lng)
    elif step == 2:
        if form.get("phase") not in ("Single Phase", "Three Phase"):
            return back("Select the phase of the solar inverter")
        try:
            inv = float(form.get("inv_kw_0") or 0) * int(form.get("inv_qty_0") or 0)
            wp, qty = float(form.get("mod_wp_0") or 0), int(form.get("mod_qty_0") or 0)
        except ValueError:
            return back("Ratings and quantities must be numbers")
        if inv <= 0 or not (form.get("inv_make_0") or "").strip():
            return back("Enter the inverter rating, quantity and manufacturer")
        if wp <= 0 or qty <= 0 or not (form.get("mod_make_0") or "").strip():
            return back("Enter the module rating, quantity and manufacturer")
        sn = [x for x in re.split(r"[\s,;]+", form.get("mod_serial_0") or "") if x]
        if len(sn) != qty:
            return back(f"Add {qty} serial numbers for the PV modules ({len(sn)} entered)")
        cert = db.one("SELECT * FROM dcr_certs WHERE cert_no=?", ((form.get("dcr") or "").strip().upper(),))
        if not cert:
            return back("DCR certificate number not found on the DCR portal")
        if set(sn) - set(json.loads(cert["serials"])):
            return back("Module serial numbers do not match the DCR certificate")
        data.update(phase=form.get("phase"), inverter_kw=inv, inverter_make=form.get("inv_make_0").strip(),
                    module_wp=wp, module_qty=qty, module_make=form.get("mod_make_0").strip(),
                    dcr=cert["cert_no"], serials=sn, capacity_kw=round(wp * qty / 1000, 2))
    elif step == 3:
        f = form.get("plant")
        b = await f.read() if f is not None and getattr(f, "filename", "") else b""
        if not b:
            return back("Upload the plant photo")
        if b[:3] != b"\xff\xd8\xff" or len(b) > 500 * 1024:
            return back("The plant photo must be a JPG up to 500 KB")
        data["plant_photo"] = f"{f.filename} ({len(b) // 1024} KB)"
    elif step == 4:
        ans = {k: form.get(k) for k, _ in CHECKS}
        if any(v not in ("Y", "N") for v in ans.values()):
            return back("Answer every item of the protection checklist")
        if any(v != "Y" for v in ans.values()):
            return back("All protection items must be in place before submission")
        data["checklist"] = "all Yes"
    else:
        if form.get("declare") != "1":
            return back("Tick the declaration")
        missing = [k for k in ("vendor", "lat", "inverter_make", "module_make", "dcr", "plant_photo", "checklist") if k not in data]
        if missing:
            return back("Complete every step first: " + ", ".join(missing))
        _save_ins(app, install=json.dumps(data), install_at=db.now(), stage=LATER[0])
        return RedirectResponse(f"/pmsg/vendor/install?app={app}&done=1", 303)
    _save_ins(app, install=json.dumps(data))
    return RedirectResponse(f"/pmsg/vendor/install?app={app}&step={step + 1}", 303)


# ------------------------------- later stages, sandbox only -------------------------------
@router.post("/sandbox/advance")
def advance(app: str = Form(...)):
    """Stands in for the customer accepting and the DISCOM working through the application."""
    ins = _ins(app)
    if ins["stage"] in LATER and LATER.index(ins["stage"]) < len(LATER) - 1:
        _save_ins(app, stage=LATER[LATER.index(ins["stage"]) + 1])
    return {"stage": _ins(app)["stage"]}
