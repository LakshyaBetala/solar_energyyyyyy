"""Sandbox of the NISE DCR verification portal (v6.2), B2C certificate, rebuilt from the client's
screens: the 'DCR DETAILS (B2C)' form with its exact labels, the application-number format check,
panel numbers typed or uploaded as Excel (column A from row 2), and the dealer's panel credit:
a panel the dealer has not transferred to the vendor's stock is refused, as on the real portal.

It exists so the co-pilot can be exercised end to end without touching the real portal.
"""
import html, io, json, re, secrets
from datetime import datetime
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import db
from .config import vendor

router = APIRouter(prefix="/dcr")
e = html.escape
SESSIONS = set()
APP_FORMAT = re.compile(r"^NP-[A-Z0-9]{4,}-\d{5,}$")
STATES = ["Andaman and Nicobar Islands (35)", "Andhra Pradesh (28)", "Gujarat (24)", "Karnataka (29)",
          "Madhya Pradesh (23)", "Maharashtra (27)", "Rajasthan (08)", "Telangana (36)"]
CSS = """body{margin:0;font:13px Arial,sans-serif;color:#222;background:#F4F6F8}.top{background:#fff;display:flex;
align-items:center;gap:16px;padding:10px 18px;border-bottom:3px solid #6CB33F}.top b{font-size:16px}
.side{position:fixed;top:56px;bottom:0;left:0;width:190px;background:#1F2D3D;color:#cfd8e3;padding:10px}
.side a{display:block;color:#cfd8e3;padding:6px;text-decoration:none}.main{margin-left:210px;padding:18px}
h2{border-left:4px solid #6CB33F;padding-left:10px;font-size:17px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.fg label{display:block;margin-bottom:4px}.fg input,.fg select,.fg textarea{width:100%;box-sizing:border-box;padding:7px;
border:1px solid #ccc;border-radius:3px}.hint{background:#D9EDF7;color:#245;padding:6px;margin-top:4px;font-size:12px}
.btn{background:#6CB33F;color:#fff;border:0;padding:8px 22px;border-radius:3px;cursor:pointer}
.err{background:#FDECEA;color:#8A1C12;padding:10px;margin:10px 0}.ok{background:#E6F6EE;color:#13603B;padding:12px;margin:10px 0}
.login{width:340px;margin:70px auto;background:#fff;padding:20px;border:1px solid #ddd}
.sandbox{background:#8E231B;color:#fff;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;padding:3px;text-align:center}"""


def shell(body):
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>DCR Verification Portal</title>
<style>{CSS}</style></head><body><div class="sandbox">Demo sandbox &mdash; not the NISE portal</div>
<div class="top"><b>NISE</b> DCR Verification Portal <span style="margin-left:auto">{e(vendor()['name'])}</span>
<span id="timer">Session: 45:00</span></div><div class="side"><a href="/dcr/b2c">DCR &rsaquo; Sell (B2C - Consumer)</a>
<a href="/dcr/">Logout</a></div><div class="main">{body}</div>
<div style="margin-left:210px;padding:10px;color:#888">2024 - 2026 &copy; DCR Verification Portal &middot; Version : 6.2</div></body></html>""")


def seed_stock():
    """The dealer's transfer of panels into the vendor's stock, for the demo and the tests."""
    for i in range(318500, 318540):
        db.ex("INSERT OR IGNORE INTO dcr_stock(serial,credited_at) VALUES(?,?)", (f"PE55026A{i:06d}", db.now()))


def authed(request):
    return request.cookies.get("dcrid") in SESSIONS


@router.get("/", response_class=HTMLResponse)
def login_get(error: str = ""):
    return shell(f"""<form class="login" method="post" action="/dcr/login">{f'<div class="err">{e(error)}</div>' if error else ''}
<div class="fg"><label for="u">User Name</label><input id="u" name="username"></div>
<div class="fg"><label for="p">Password</label><input id="p" type="password" name="password"></div>
<div class="fg"><label for="c">Enter Captcha <b style="letter-spacing:.3em">7 K 2 Q</b></label><input id="c" name="captcha"></div>
<p><button class="btn">Login</button></p></form>""")


@router.post("/login")
async def login_post(request: Request):
    f = await request.form()
    if not (f.get("username") and f.get("password") == "demo" and (f.get("captcha") or "").replace(" ", "").upper() == "7K2Q"):
        return RedirectResponse("/dcr/?error=Invalid+login+or+captcha", 303)
    sid = secrets.token_hex(10)
    SESSIONS.add(sid)
    r = RedirectResponse("/dcr/b2c", 303)
    r.set_cookie("dcrid", sid, httponly=True, samesite="lax")
    return r


def field(i, label, ctl):
    return f'<div class="fg"><label for="{i}">{label}</label>{ctl}</div>'


@router.get("/b2c", response_class=HTMLResponse)
def b2c(request: Request, error: str = "", cert: str = ""):
    if not authed(request):
        return RedirectResponse("/dcr/", 303)
    if cert:
        c = db.one("SELECT * FROM dcr_certs WHERE cert_no=?", (cert,))
        if c:
            n = len(json.loads(c["serials"]))
            return shell(f"""<h2>DCR DETAILS (B2C)</h2><div class="ok">DCR Certificate generated successfully.</div>
<table><tr><td>Certificate Number</td><td><b id="certNo">{e(c['cert_no'])}</b></td></tr>
<tr><td>Consumer Application Number</td><td>{e(c['application_no'])}</td></tr>
<tr><td>Customer Name</td><td>{e(c['customer_name'])}</td></tr><tr><td>Quantity</td><td>{n}</td></tr></table>
<p><a href="/dcr/cert/{e(c['cert_no'])}.pdf" class="btn">Download Certificate</a></p>""")
    opt = lambda opts: '<option value="">Select an option</option>' + "".join(f"<option>{e(o)}</option>" for o in opts)
    return shell(f"""<h2>DCR DETAILS (B2C)</h2>{f'<div class="err" id="dcrError">{e(error)}</div>' if error else ''}
<form method="post" action="/dcr/b2c" enctype="multipart/form-data"><div class="grid">
{field('br', 'Branch', f'<select id="br" name="branch">{opt(["Maharashtra - Flat No. 203, Sai Plaza"])}</select>')}
{field('it', 'Item Type', f'<select id="it" name="item">{opt(["Solar Panels"])}</select>')}
{field('po', 'Purchase Order Ref', '<input id="po" name="po" placeholder="Enter Customer PO Ref">')}
{field('pn', 'Project Name', '<input id="pn" name="project" placeholder="Enter Customer Project Ref (Optional)">')}
{field('ss', 'Subsidy Scheme', f'<select id="ss" name="scheme">{opt(["PM Surya Ghar: Muft Bijli Yojana"])}</select>')}
<div class="fg"><label for="can">Consumer Application Number</label><input id="can" name="app_no" placeholder="e.g. NP-RJJOV25-5119272">
<div class="hint">Only Enter Application Number in format: NP-XXXXXNN-NNNNNNN (e.g. NP-RJJOV25-5119272)</div></div>
{field('cn', 'Customer Name', '<input id="cn" name="name" placeholder="Enter Customer Name">')}
{field('cm', 'Consumer Mobile', '<input id="cm" name="mobile" placeholder="Enter Customer Mobile #">')}
{field('ca', 'Customer Address', '<textarea id="ca" name="address" placeholder="Enter Customer Address (Optional)"></textarea>')}
{field('cs', 'Customer State', f'<select id="cs" name="state">{opt(STATES)}</select>')}
{field('cp', 'Customer Pin Code', '<input id="cp" name="pin" placeholder="Enter Pin Code (Optional)">')}
{field('ccp', 'Customer Contact Person', '<input id="ccp" name="contact" placeholder="Enter Contact Person (Optional)">')}
{field('ce', 'Customer Contact Email', '<input id="ce" name="email" placeholder="Enter Contact Person Email">')}
{field('inv', 'Invoice Number / E-Way Bill', '<input id="inv" name="invoice" placeholder="Enter Invoice / E-Way Bill Number">')}
{field('dt', 'Date', '<input id="dt" type="date" name="date">')}
{field('pan', 'Panel Numbers (Enter Or Upload Via Excel)', '<textarea id="pan" name="panels" rows="4"></textarea>')}
{field('xl', 'Upload Excel (Column A Row 2 Onwards Data Will Read)', '<input id="xl" type="file" name="excel" accept=".xlsx">')}
{field('qty', 'Quantity', '<input id="qty" name="qty">')}
{field('rm', 'Remarks', '<input id="rm" name="remarks">')}</div>
<p><button class="btn" id="btnDcr">Submit</button></p></form>""")


@router.post("/b2c")
async def b2c_post(request: Request, excel: UploadFile = File(None)):
    if not authed(request):
        return RedirectResponse("/dcr/", 303)
    f = await request.form()
    back = lambda m: RedirectResponse(f"/dcr/b2c?error={m}", 303)
    app_no = (f.get("app_no") or "").strip().upper()
    if not APP_FORMAT.match(app_no):
        return back("Only Enter Application Number in format: NP-XXXXXNN-NNNNNNN")
    for k, lbl in (("branch", "Branch"), ("item", "Item Type"), ("scheme", "Subsidy Scheme"), ("name", "Customer Name"),
                   ("state", "Customer State"), ("invoice", "Invoice Number / E-Way Bill")):
        if not (f.get(k) or "").strip():
            return back(f"{lbl} is required")
    if not re.fullmatch(r"[6-9]\d{9}", (f.get("mobile") or "").strip()):
        return back("Enter a valid 10 digit Consumer Mobile")
    serials = [x.strip().upper() for x in re.split(r"[\s,;]+", f.get("panels") or "") if x.strip()]
    if excel is not None and excel.filename:
        from openpyxl import load_workbook
        try:
            ws = load_workbook(io.BytesIO(await excel.read()), read_only=True).active
            serials += [str(r[0]).strip().upper() for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
        except Exception:
            return back("The Excel file could not be read")
    if not serials:
        return back("Enter the panel numbers or upload the Excel")
    if len(set(serials)) != len(serials):
        return back("Duplicate panel numbers entered")
    if (f.get("qty") or "").strip() != str(len(serials)):
        return back(f"Quantity does not match the number of panels ({len(serials)})")
    stock = {r["serial"]: r for r in db.q(f"SELECT * FROM dcr_stock WHERE serial IN ({','.join('?' * len(serials))})", serials)}
    missing = [s for s in serials if s not in stock]
    if missing:
        return back("Panel Numbers not available in your stock (not transferred by the dealer): " + ", ".join(missing[:5]))
    used = [s for s in serials if stock[s]["used_by"]]
    if used:
        return back("Panel Numbers already used in another certificate: " + ", ".join(used[:5]))
    n = (db.one("SELECT COUNT(*) k FROM dcr_certs")["k"] or 0) + 4512
    cert = f"NISE-B2C-{datetime.now():%y}-{n:06d}"
    db.ex("INSERT INTO dcr_certs(cert_no,application_no,customer_name,serials,invoice,issued_at) VALUES(?,?,?,?,?,?)",
          (cert, app_no, f.get("name").strip(), json.dumps(serials), f.get("invoice").strip(), db.now()))
    for s in serials:
        db.ex("UPDATE dcr_stock SET used_by=? WHERE serial=?", (cert, s))
    return RedirectResponse(f"/dcr/b2c?cert={cert}", 303)


@router.get("/cert/{cert}.pdf")
def cert_pdf(cert: str, request: Request):
    if not authed(request):
        return RedirectResponse("/dcr/", 303)
    c = db.one("SELECT * FROM dcr_certs WHERE cert_no=?", (cert,))
    if not c:
        return Response(status_code=404)
    import fitz
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((50, 70), f"DCR Certificate {c['cert_no']} (sandbox)", fontsize=14)
    pg.insert_text((50, 100), f"{c['customer_name']} - {c['application_no']}", fontsize=11)
    for i, s in enumerate(json.loads(c["serials"])):
        pg.insert_text((50, 130 + 14 * i), s, fontsize=9)
    return Response(doc.tobytes(), media_type="application/pdf")
