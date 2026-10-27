"""Sandbox of the MSEDCL rooftop-solar vendor portal (v3.0.0), rebuilt from the screens the
client shared: password login, the 'Vendor Subsidies Consumer's List' with days pending,
and the six-document upload page (PDF only, 300 KB each, all mandatory).

It exists so the co-pilot extension can be exercised end to end without touching MSEDCL.
"""
import html, secrets
from datetime import datetime
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from . import db
from .config import MAX_UPLOAD_KB, vendor

router = APIRouter(prefix="/msedcl")
e = html.escape
SLOTS = ["Work Completion Report", "Annexure-I Installation Report of RE Gen. System",
         "Declaration of DCR", "Net Agreement Bond", "Brochure/Datasheet of PV modules and Inverter",
         "Photo of installed PV system with Geo Co-ordinates"]
# application id, consumer number, days the documents have been pending (as on the client's list)
APPS = [("79435901", "170031277450", 24), ("79436117", "170036002985", 48),
        ("79434410", "170024518893", 134)]
SESSIONS = set()

CSS = """body{margin:0;font:12px Tahoma,Arial,sans-serif;color:#222}
.top{display:flex;align-items:center;gap:14px;padding:6px 14px;border-bottom:3px solid #1A5DA8}
.top b{color:#1A3E73;font-size:14px}.top .v{font-size:11px;color:#1A3E73;text-align:center;flex:1}
h2{color:#C0392B;font-weight:400;font-size:17px;text-align:center;margin:16px 0}
table{border-collapse:collapse;margin:8px auto;width:94%}th{background:#5B9BD5;color:#fff;
font-weight:400;padding:5px;border:1px solid #fff;text-align:left}td{padding:5px;border:1px solid #DCE6F1}
.bar{background:#5B9BD5;color:#fff;padding:5px 10px;width:300px;margin:12px 3%}
.note{text-align:center;font-size:11px}.red{color:#C00}input[readonly]{background:#eee;border:1px solid #aaa}
.btn{border-radius:12px;padding:3px 26px;border:1px solid #555;background:#f4f4f4;cursor:pointer}
.login{width:330px;margin:60px auto;border:1px solid #5B9BD5;padding:18px}"""


def shell(body):
    v = vendor()
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>Rooftop Solar</title>
<style>{CSS}</style></head><body><div class="top"><b>MAHAVITARAN</b><div class="v">
<b>Maharashtra State Electricity Distribution Co. Ltd.</b><br>Rooftop Solar Portal for Vendor,
Employee And AMISP - Version : 3.0.0 &middot; SANDBOX<br>Vendor Name : {e(v['name'])}</div>
<a href="/msedcl/">Logout</a></div>{body}</body></html>""")


def authed(request):
    return request.cookies.get("msid") in SESSIONS


@router.get("/", response_class=HTMLResponse)
def login_get(error: str = ""):
    return shell(f"""<form class="login" method="post" action="/msedcl/login">
{f'<div class="red">{e(error)}</div>' if error else ''}
<label><input type="radio" name="userType" value="employee"> Employee</label>
<label><input type="radio" name="userType" value="vendor" checked> Vendor</label>
<label><input type="radio" name="userType" value="amisp"> AMISP</label>
<p>User Id <input type="text" id="userIdField" name="username"></p>
<p>Password <input type="password" name="password"></p>
<button class="btn" type="submit">Submit</button></form>""")


@router.post("/login")
def login_post(username: str = Form(""), password: str = Form("")):
    if not (username.strip() and password == "demo"):
        return RedirectResponse("/msedcl/?error=Invalid+user+id+or+password", 303)
    sid = secrets.token_hex(12)
    SESSIONS.add(sid)
    r = RedirectResponse("/msedcl/list", 303)
    r.set_cookie("msid", sid, httponly=True, samesite="lax")
    return r


def consumer(no):
    return db.one("SELECT * FROM portal_consumers WHERE consumer_no=?", (no,))


@router.get("/list", response_class=HTMLResponse)
def listing(request: Request):
    if not authed(request):
        return RedirectResponse("/msedcl/", 303)
    rows = ""
    for app_id, no, days in APPS:
        pc = consumer(no)
        n = db.one("SELECT COUNT(DISTINCT slot) k FROM msedcl_uploads WHERE application_id=?",
                   (app_id,))["k"]
        rows += f"""<tr><td><a href="/msedcl/upload?app={app_id}">{app_id}</a></td><td>{no}</td>
<td>{e(pc['billed_name'])}</td><td>{e(pc['address'])}</td><td>Status Receipt Approved</td><td>{n}</td>
<td>{'Verification Pending' if n == 6 else 'Pending For Upload'}</td>
<td class="red" style="font-size:16px">{0 if n == 6 else days}</td></tr>"""
    return shell(f"""<h2>Rooftop Solar Vendor Subsidies Consumer's List</h2><table><tr>
<th>Application ID</th><th>Consumer Number</th><th>Consumer Full Name</th><th>Consumer Address</th>
<th>Current Workflow Status</th><th>Total Files Uploaded</th><th>Document Status</th>
<th>Document Pending Since (days)</th></tr>{rows}</table>""")


@router.get("/upload", response_class=HTMLResponse)
def upload_get(request: Request, app: str, error: str = ""):
    if not authed(request):
        return RedirectResponse("/msedcl/", 303)
    hit = next((a for a in APPS if a[0] == app), None)
    if not hit:
        return shell('<h2>Application not found</h2>')
    pc = consumer(hit[1])
    got = {r["slot"]: r for r in db.q("SELECT * FROM msedcl_uploads WHERE application_id=?", (app,))}
    ro = lambda v: f'<input type="text" readonly value="{e(v)}">'
    rows = "".join(f"""<tr><td>{i}. {e(name)}</td><td>{
        f'{e(got[i]["filename"])}' if i in got else f'<input type="file" name="doc{i}" accept=".pdf">'}</td>
<td>{'VERIFICATION PENDING' if i in got else ''}</td><td></td></tr>""" for i, name in enumerate(SLOTS, 1))
    return shell(f"""<h2>Rooftop Solar Installation Documents Upload for Vendor</h2>
{f'<div class="note red">{e(error)}</div>' if error else ''}
<div class="bar">Consumer Details</div><table>
<tr><td>Application ID :</td><td>{ro(app)}</td><td>Consumer Number :</td><td>{ro(hit[1])}</td></tr>
<tr><td>Consumer Name :</td><td>{ro(pc['billed_name'])}</td><td>Consumer Contact No :</td><td>{ro(pc['msisdn'])}</td></tr>
<tr><td>Agency Name :</td><td>{ro(vendor()['name'])}</td><td>AMISP Contact Name :</td><td>{ro('—')}</td></tr></table>
<div class="bar">List of Documents To Upload <span class="red">*</span></div>
<form method="post" action="/msedcl/upload?app={app}" enctype="multipart/form-data">
<div class="note">All files are mandatory ( File size limit {MAX_UPLOAD_KB} KB each )
<span class="red">Select file type pdf Only</span></div>
<table><tr><th>Document Name</th><th>File Upload</th><th>Document Status</th><th>Remark</th></tr>{rows}</table>
<p style="text-align:center"><button class="btn" type="submit" id="btnUpload">Upload</button>
<a class="btn" href="/msedcl/list">Back To List</a></p></form>""")


@router.post("/upload")
async def upload_post(request: Request, app: str, doc1: UploadFile = File(None),
                      doc2: UploadFile = File(None), doc3: UploadFile = File(None),
                      doc4: UploadFile = File(None), doc5: UploadFile = File(None),
                      doc6: UploadFile = File(None)):
    if not authed(request):
        return RedirectResponse("/msedcl/", 303)
    have = {r["slot"] for r in db.q("SELECT slot FROM msedcl_uploads WHERE application_id=?", (app,))}
    files = {i: f for i, f in enumerate([doc1, doc2, doc3, doc4, doc5, doc6], 1)
             if f is not None and f.filename}
    if have | set(files) != set(range(1, 7)):
        return RedirectResponse(f"/msedcl/upload?app={app}&error=All+files+are+mandatory", 303)
    blobs = {i: await f.read() for i, f in files.items()}
    for i, b in blobs.items():
        if not b.startswith(b"%PDF") or not files[i].filename.lower().endswith(".pdf"):
            return RedirectResponse(f"/msedcl/upload?app={app}&error=Select+file+type+pdf+only", 303)
        if len(b) > MAX_UPLOAD_KB * 1024:
            return RedirectResponse(f"/msedcl/upload?app={app}&error=File+size+limit+{MAX_UPLOAD_KB}+KB", 303)
    for i, b in blobs.items():
        db.ex("INSERT INTO msedcl_uploads(application_id,slot,filename,bytes,ts) VALUES(?,?,?,?,?)",
              (app, i, files[i].filename, len(b), datetime.now().isoformat(timespec="seconds")))
    return RedirectResponse(f"/msedcl/upload?app={app}", 303)
