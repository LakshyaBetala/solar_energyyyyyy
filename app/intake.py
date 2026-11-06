"""The customer sends their own documents: one link on WhatsApp, opened on the customer's phone.

The customer photographs the electricity bill and the Aadhaar (and later the bank passbook and
the roof), and types the email the portal will send its code to. Every file goes through the same
path as an upload in the dashboard: encrypted at rest, read by rules, Aadhaar reduced to its last
4 digits, anything unsure flagged for the owner. The page shows what was received, never the
contents, and nothing on it is filed anywhere: the owner still checks and registers.
"""
import html, secrets
from datetime import datetime, timedelta
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from . import db, closeout, valid
from .config import vendor
from .esign import CSS

router = APIRouter(prefix="/up")
VALID_DAYS = 7
MAX_UPLOADS = 30          # per link; a phone that keeps re-sending is stopped, the owner sends a new link
KINDS = {"bill": ("Electricity bill", "वीज बिल", "The latest bill: the PDF from the MSEDCL website, or a clear photo of the whole bill."),
         "aadhaar": ("Aadhaar card", "आधार कार्ड", "A photo of the side with the QR code. Only the last 4 digits are kept."),
         "passbook": ("Bank passbook or cheque", "बँक पासबुक किंवा चेक", "Needed later for the subsidy. You can send it now."),
         "roof": ("Photo of the roof", "छताचा फोटो", "Optional: one photo of where the panels will go.")}
ERRORS = {"type": "That kind of file cannot be used. Send a photo or a PDF.",
          "empty": "That file was empty. Choose the photo again.",
          "size": "That file is over 15 MB. Send a smaller photo.",
          "email": "That does not look like an email address. Check it and send it again.",
          "many": "Too many files on this link. Ask the installer for a new link."}
e = html.escape


def create(cid, user):
    token = secrets.token_urlsafe(18)
    db.ex("""INSERT INTO doc_requests(token,customer_id,created_by,created_at,expires_at)
             VALUES(?,?,?,?,?)""", (token, cid, user["username"], db.now(),
                                    (datetime.now() + timedelta(days=VALID_DAYS)).isoformat(timespec="seconds")))
    db.audit(user["username"], user["role"], "Asked the customer for documents", cid, f"link valid {VALID_DAYS} days")
    return token


def share_text(cid, url):
    c, _ = closeout.data(cid)
    first = (c["aadhaar_name"] or c["name"]).split()[0]
    return (f"Namaskar {first}, for your rooftop solar registration with {vendor()['name']}, please send a photo "
            f"of your electricity bill and your Aadhaar here: {url}\n"
            f"नमस्कार, सौर नोंदणीसाठी तुमचे वीज बिल आणि आधार कार्डचा फोटो या लिंकवर पाठवा. "
            f"The link is only for you and works for {VALID_DAYS} days.")


def whatsapp(cid, url):
    _, d = closeout.data(cid)
    num = "".join(ch for ch in d.get("mobile", "") if ch.isdigit())[-10:]
    return f"https://wa.me/91{num}?text={quote(share_text(cid, url))}" if len(num) == 10 else None


def page(body, status=200):
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Send your documents</title>
<style>{CSS}.item{{border-top:1px solid #EDF0F3;padding:14px 0}}.item:first-child{{border-top:0}}
.got{{color:#0B5133;font-weight:700}}.pick{{position:relative;display:block;margin-top:8px;padding:12px;border:2px dashed #7C8A97;
border-radius:8px;text-align:center;font-weight:700;color:#0B4F6C;cursor:pointer}}.pick input{{position:absolute;opacity:0;width:1px;height:1px}}.pick:focus-within{{outline:3px solid #0B6E4F;outline-offset:2px}}</style>
</head><body><div class="wrap"><div class="hd">{e(vendor()['name'])}</div>{body}</div></body></html>""", status_code=status)


def message(title, mr, text, status):
    return page(f'<div class="card"><h1>{title}<span class="mr">{mr}</span></h1><p>{text}</p></div>', status)


def load(token):
    r = db.one("SELECT * FROM doc_requests WHERE token=?", (token,))
    if not r:
        return None, message("This link is not valid", "ही लिंक वैध नाही", "Ask the installer to send you a new link.", 404)
    if datetime.fromisoformat(r["expires_at"]) < datetime.now():
        return r, message("This link has expired", "या लिंकची मुदत संपली आहे", "Ask the installer to send you a new link.", 410)
    return r, None


@router.get("/{token}", response_class=HTMLResponse)
def show(token: str, got: str = "", err: str = ""):
    r, stop = load(token)
    if stop:
        return stop
    cid = r["customer_id"]
    c, d = closeout.data(cid)
    have = {x["kind"] for x in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    first = e((c["aadhaar_name"] or c["name"]).split()[0])
    note = (f'<div class="err">{e(ERRORS[err])}</div>' if err in ERRORS else
            f'<div class="ok">Received: {e(KINDS[got][0])}. Thank you. / मिळाले, धन्यवाद.</div>' if got in KINDS else
            '<div class="ok">Email saved. Thank you. / ईमेल मिळाला.</div>' if got == "email" else "")
    items = "".join(f"""<div class="item"><b>{t}</b> <span class="mr" style="display:inline">/ {mr}</span>
<div class="small">{why}</div>{'<div class="got">&#10003; Received / मिळाले</div>' if k in have else ''}
<form method="post" action="/up/{e(token)}/file?kind={k}" enctype="multipart/form-data">
<label class="pick">{'Send it again' if k in have else 'Take a photo or choose a file'} / फोटो पाठवा
<input type="file" name="file" accept="image/*,application/pdf" onchange="this.form.submit()"></label>
<noscript><button type="submit">Send</button></noscript></form></div>""" for k, (t, mr, why) in KINDS.items())
    email = d.get("email")
    return page(f"""{note}<div class="card"><h1>Namaskar {first}<span class="mr">तुमची कागदपत्रे पाठवा</span></h1>
<p class="small">For your rooftop solar registration on PM Surya Ghar. Your installer checks everything before anything is filed.</p>
{items}</div>
<div class="card"><b>Your email</b> <span class="mr" style="display:inline">/ तुमचा ईमेल</span>
<div class="small">The PM Surya Ghar portal sends a code to this email while registering you.</div>
{'<div class="got">&#10003; Received / मिळाले</div>' if email else ''}
<form method="post" action="/up/{e(token)}/email"><input type="text" inputmode="email" name="email" autocomplete="email"
placeholder="name@example.com" aria-label="Email"><button type="submit">Save email / ईमेल पाठवा</button></form></div>""")


@router.post("/{token}/file")
async def take_file(token: str, kind: str = "", file: UploadFile = File(None)):
    r, stop = load(token)
    if stop:
        return stop
    if kind not in KINDS or file is None:
        return RedirectResponse(f"/up/{token}?err=type", 303)
    if r["uploads"] >= MAX_UPLOADS:
        return RedirectResponse(f"/up/{token}?err=many", 303)
    if (file.content_type or "").split("/")[0] not in ("image", "application"):
        return RedirectResponse(f"/up/{token}?err=type", 303)
    db.ex("UPDATE doc_requests SET uploads=uploads+1, last_at=? WHERE token=?", (db.now(), token))
    from .main import take_document  # the dashboard's own upload path (late import: main imports this module)
    from fastapi import HTTPException
    try:
        await take_document(r["customer_id"], kind, file, {"username": "customer", "role": "customer"})
    except HTTPException as ex:
        return RedirectResponse(f"/up/{token}?err={'size' if 'MB' in str(ex.detail) else 'empty' if 'empty' in str(ex.detail) else 'type'}", 303)
    return RedirectResponse(f"/up/{token}?got={kind}", 303)


@router.post("/{token}/email")
def take_email(token: str, email: str = Form("")):
    r, stop = load(token)
    if stop:
        return stop
    try:
        v = valid.email(email)
    except ValueError:
        v = ""
    if not v:
        return RedirectResponse(f"/up/{token}?err=email", 303)
    closeout.save(r["customer_id"], {"email": v}, "customer")
    db.audit("customer", "customer", "Customer gave their email", r["customer_id"], "through the document link")
    return RedirectResponse(f"/up/{token}?got=email", 303)


def link(request: Request, token):
    return str(request.base_url).rstrip("/") + f"/up/{token}"
