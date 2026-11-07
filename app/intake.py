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
from .config import vendor, public_url
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


REQUIRED = ("bill", "aadhaar")      # with the email, what the portal needs to register them; the rest can come later
OPTIONAL = ("passbook", "roof")

# Big phone photos (3-8 MB) are slow on mobile data. Shrink only those, keep plenty of pixels for the
# Aadhaar QR, and send the original if anything goes wrong. A PDF is never touched.
UPLOAD_JS = """<script>
async function shrink(f) {
  if (!/^image\\//.test(f.type) || f.size < 3e6 || !window.createImageBitmap) return f;
  const img = await createImageBitmap(f), s = Math.min(1, 3000 / Math.max(img.width, img.height));
  const c = document.createElement('canvas'); c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
  const b = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.9));
  return b && b.size < f.size ? new File([b], (f.name || 'photo').replace(/\\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' }) : f;
}
document.querySelectorAll('input[data-up]').forEach(inp => inp.addEventListener('change', async () => {
  const f = inp.files[0]; if (!f) return;
  const form = inp.form, msg = form.querySelector('.sending');
  msg.hidden = false; document.querySelectorAll('input[data-up]').forEach(x => { if (x !== inp) x.disabled = true; });
  let file = f; try { file = await shrink(f); } catch (e) { file = f; }
  const fd = new FormData(); fd.append('file', file, file.name || f.name);
  try { const r = await fetch(form.action, { method: 'POST', body: fd }); location.href = r.url; }
  catch (e) { msg.textContent = 'Could not send. Check the internet and try again. / पाठवता आले नाही, पुन्हा प्रयत्न करा.';
              document.querySelectorAll('input[data-up]').forEach(x => { x.disabled = false; }); }
}));
</script>"""


def page(body, status=200):
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Send your documents</title>
<style>{CSS}.item{{border-top:1px solid #EDF0F3;padding:14px 0}}.item:first-child{{border-top:0;padding-top:4px}}
.ih{{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}}.got{{color:#0B5133;font-weight:700;white-space:nowrap}}
.pick{{position:relative;display:block;margin-top:10px;padding:13px;border:2px dashed #7C8A97;border-radius:8px;text-align:center;
font-weight:700;color:#0B4F6C;cursor:pointer}}.again{{position:relative;display:inline-block;margin-top:6px;color:#0B5C8C;
text-decoration:underline;font-size:14px;cursor:pointer}}.pick input,.again input{{position:absolute;opacity:0;width:1px;height:1px}}
.pick:focus-within,.again:focus-within{{outline:3px solid #0B6E4F;outline-offset:2px}}
.sending{{margin-top:8px;font-weight:700;color:#0B4F6C}}.todo{{background:#FFF4DE;color:#5C3D00;border-radius:8px;padding:12px 14px;margin-bottom:12px}}
.done-all{{background:#E7F5EE;color:#0B5133;border-radius:10px;padding:16px;margin-bottom:12px}}.done-all b{{font-size:18px}}
h2{{font-size:16px;margin:0 0 4px}}details summary{{cursor:pointer;color:#0B5C8C;font-size:14px;margin-top:6px}}.pick.big{{padding:22px 12px;font-size:19px;border-style:solid;background:#EEF6F3;margin-top:14px}}.pick.big .mr{{font-size:14px;font-weight:600}}.dots{{display:flex;gap:6px;align-items:center}}.dots .dot{{width:28px;height:6px;border-radius:3px;background:#D9DFE5}}.dots .dot.on{{background:#0B6E4F}}.dots .dot.now{{background:#7FB8A3}}.dots .small{{margin-left:6px}}.check{{list-style:none;margin:0 0 12px;padding:0 4px;display:grid;gap:6px;color:#5B6875}}.check li.done{{color:#0B5133;font-weight:600}}.check li.now{{color:#172029;font-weight:700}}.check form{{display:inline;margin-left:8px}}.opt summary{{color:#172029;font-size:15px}}</style>
</head><body><div class="wrap"><div class="hd">{e(vendor()['name'])}</div>{body}</div>{UPLOAD_JS}</body></html>""", status_code=status)


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
    """One thing at a time: the next item is big, with one button; a short list shows what is done."""
    r, stop = load(token)
    if stop:
        return stop
    cid = r["customer_id"]
    c, d = closeout.data(cid)
    have = {x["kind"] for x in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    email = d.get("email")
    first = e((c["aadhaar_name"] or c["name"]).split()[0])
    steps = [("bill", "Electricity bill", "वीज बिल", "bill" in have), ("aadhaar", "Aadhaar card", "आधार कार्ड", "aadhaar" in have),
             ("email", "Your email", "तुमचा ईमेल", bool(email))]
    left = [s for s in steps if not s[3]]
    phone = vendor().get("phone")
    help_line = (f'<p class="small" style="text-align:center;margin-top:14px">Need help? Call your installer: '
                 f'<a href="tel:{e(phone.replace(" ", ""))}"><b>{e(phone)}</b></a></p>') if phone else ""
    note = (f'<div class="err">{e(ERRORS[err])}</div>' if err in ERRORS else
            f'<div class="ok">&#10003; Got it: {e(KINDS[got][0])}. / मिळाले.</div>' if got in KINDS and left else
            '<div class="ok">&#10003; Email saved. / ईमेल मिळाला.</div>' if got == "email" and left else "")

    def upload(k, label, cls):
        return (f'<form method="post" action="/up/{e(token)}/file?kind={k}" enctype="multipart/form-data">'
                f'<label class="{cls}">{label}<input type="file" name="file" accept="image/*,application/pdf" data-up></label>'
                f'<div class="sending" hidden>Sending… keep this page open / पाठवत आहे…</div>'
                f'<noscript><button type="submit">Send</button></noscript></form>')

    email_form = (f'<form method="post" action="/up/{e(token)}/email"><input type="text" inputmode="email" name="email" '
                  f'autocomplete="email" placeholder="name@example.com" aria-label="Email">'
                  f'<button type="submit">Save email / ईमेल पाठवा</button></form>')
    optional = (f'<details class="card opt"><summary><b>Optional:</b> bank passbook or a roof photo '
                f'<span class="mr" style="display:inline">/ ऐच्छिक</span></summary>'
                + "".join(f'<div class="item"><b>{KINDS[k][0]}</b> <span class="mr" style="display:inline">/ {KINDS[k][1]}</span>'
                          f'{" <span class=got>&#10003; Received</span>" if k in have else ""}<div class="small">{KINDS[k][2]}</div>'
                          f'{upload(k, "Send a different photo" if k in have else "Take a photo / फोटो पाठवा", "again" if k in have else "pick")}</div>'
                          for k in OPTIONAL) + '</details>')

    if not left:
        return page(f"""<div class="done-all"><b>All done. Thank you, {first}.</b><span class="mr">सर्व मिळाले. धन्यवाद.</span>
<p style="margin:6px 0 0">You can close this page. Your installer will call you when the portal sends you a code.</p></div>
{optional}{help_line}""")

    k, title, mr, _ = left[0]
    n = steps.index(left[0]) + 1
    why = KINDS[k][2] if k in KINDS else "The PM Surya Ghar portal sends a code to this email while registering you."
    big = email_form if k == "email" else upload(k, "Take a photo or choose a file<span class=\"mr\">फोटो काढा किंवा फाइल निवडा</span>", "pick big")
    dots = "".join(f'<span class="dot{" on" if s[3] else " now" if s is left[0] else ""}"></span>' for s in steps)
    checklist = "".join(
        f'<li class="{"done" if s[3] else "now" if s is left[0] else ""}">'
        f'{"&#10003;" if s[3] else "&#9679;" if s is left[0] else "&#9675;"} {s[1]}'
        + (upload(s[0], "Send a different photo", "again") if s[3] and s[0] != "email" else "") + "</li>"
        for s in steps)
    return page(f"""{note}<div class="card"><p class="small" style="margin:0 0 8px">Namaskar {first} · for your rooftop solar registration</p>
<div class="dots" aria-label="Step {n} of 3">{dots}<span class="small">Step {n} of 3</span></div>
<h1 style="margin-top:10px">{title}<span class="mr">{mr}</span></h1><p class="small">{why}</p>{big}</div>
<ul class="check">{checklist}</ul>{optional}{help_line}""")


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
    return public_url(request, f"/up/{token}")
