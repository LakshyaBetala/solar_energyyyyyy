"""Sandbox of the vendor side of the national rooftop portal, rebuilt from the screens the
client shared: Vendor Consent (approve a customer who picked you), My Application, and the
Upload Agreement dialog (total cost + agreement copy, JPG/JPEG/PDF up to 2 MB).

Applications come from the consumer-side sandbox in portal.py. Used to exercise the co-pilot
end to end without touching the real portal.
"""
import html
from fastapi import APIRouter, Form, UploadFile, File
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
    return db.q(f"""SELECT a.*, v.consented_at, v.agreement_at, v.cost, c.msisdn
                    FROM portal_applications a LEFT JOIN pmsg_vendor v ON v.application_no=a.application_no
                    LEFT JOIN portal_consumers c ON c.consumer_no=a.consumer_no
                    WHERE {where} ORDER BY a.submitted_at DESC""")


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
<td>{'Installation (Pending)' if a['agreement_at'] else 'Upload Agreement (Pending)'}</td>
<td><a class="btn" href="/pmsg/vendor/agreement?app={e(a['application_no'])}">Update Agreement</a></td></tr>"""
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
