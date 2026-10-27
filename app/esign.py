"""The customer's signing page: one link, opened on the customer's own phone (or on the
installer's phone at the site).

The customer proves they hold the bill (last 4 digits of the consumer number), reads each
document, ticks the ones they approve, and draws their signature once. Later documents only
need their approval; the saved signature is placed on nothing they have not approved. Every
approval is tied to the exact content they were shown (closeout.doc_hash).
"""
import html, json, secrets
from datetime import datetime, timedelta
from urllib.parse import quote
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from . import db, closeout
from .config import vendor

router = APIRouter(prefix="/sign")
MAX_ATTEMPTS = 5
VALID_DAYS = 7
e = html.escape


def create(cid, keys, user):
    st = {s["key"]: s for s in closeout.status(cid)}
    keys = keys or [k for k, s in st.items() if s["state"] in ("needs_approval", "changed")]
    if not keys:
        raise ValueError("nothing is waiting for the customer's approval")
    bad = [k for k in keys if k not in st or "consumer" not in st[k]["signers"]
           or st[k]["state"] in ("missing", "blocked")]
    if bad:
        raise ValueError("not ready to send: " + ", ".join(st[k]["title"] if k in st else k for k in bad))
    token = secrets.token_urlsafe(18)
    db.ex("""INSERT INTO sign_requests(token,customer_id,docs,created_by,created_at,expires_at,status)
             VALUES(?,?,?,?,?,?,'sent')""",
          (token, cid, json.dumps({k: closeout.doc_hash(k, cid) for k in keys}), user["username"],
           db.now(), (datetime.now() + timedelta(days=VALID_DAYS)).isoformat(timespec="seconds")))
    db.audit(user["username"], user["role"], "Sent documents for e-signature", cid,
             ", ".join(st[k]["title"] for k in keys))
    return token, keys


def share_text(cid, url):
    c, d = closeout.data(cid)
    first = (c["aadhaar_name"] or c["name"]).split()[0]
    return (f"Namaskar {first}, please read and sign your rooftop solar documents from "
            f"{vendor()['name']}: {url}\n"
            f"नमस्कार, तुमच्या छतावरील सौर प्रकल्पाची कागदपत्रे वाचून सही करण्यासाठी ही लिंक उघडा. "
            f"The link is only for you and works for {VALID_DAYS} days.")


def whatsapp(cid, url):
    c, d = closeout.data(cid)
    num = "".join(ch for ch in d.get("mobile", "") if ch.isdigit())[-10:]
    return f"https://wa.me/91{num}?text={quote(share_text(cid, url))}" if len(num) == 10 else None


# ------------------------------- page chrome -------------------------------
CSS = """
*{box-sizing:border-box}body{margin:0;font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,
Arial,sans-serif;background:#F2F4F6;color:#172029}
.wrap{max-width:560px;margin:0 auto;padding:16px}
.hd{font-weight:700;font-size:15px;color:#0B4F6C;margin:4px 0 14px}
.card{background:#fff;border:1px solid #D9DFE5;border-radius:10px;padding:16px;margin-bottom:12px}
h1{font-size:20px;margin:0 0 6px}.mr{display:block;color:#5B6875;font-size:14px}
label{display:block;font-weight:600;margin:12px 0 5px}
input[type=text],input[inputmode]{width:100%;font-size:18px;padding:11px;border:1px solid #9AA6B2;
border-radius:8px}
button{width:100%;font-size:17px;font-weight:700;padding:13px;border:0;border-radius:8px;
background:#0B6E4F;color:#fff;margin-top:14px}button.ghost{background:#E6EAEE;color:#172029;
width:auto;padding:8px 14px;font-size:14px;margin:6px 0 0}
.doc{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid #EDF0F3}
.doc:first-child{border-top:0}.doc input{width:22px;height:22px;margin-top:2px;flex:none}
.doc a{color:#0B5C8C;font-weight:600;white-space:nowrap}.doc .t{flex:1}
canvas{width:100%;height:190px;border:2px dashed #7C8A97;border-radius:8px;background:#fff;
touch-action:none}
.err{background:#FDECEA;color:#8A1C12;border-radius:8px;padding:10px 12px;margin-bottom:12px}
.ok{background:#E7F5EE;color:#0B5133;border-radius:8px;padding:12px}
.small{font-size:13px;color:#5B6875}.saved{max-width:220px;border-bottom:1px solid #333}
"""


def page(body, status=200):
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign documents</title>
<style>{CSS}</style></head><body><div class="wrap"><div class="hd">{e(vendor()['name'])}</div>
{body}</div></body></html>""", status_code=status)


def message(title, mr, text, status=200):
    return page(f'<div class="card"><h1>{title}<span class="mr">{mr}</span></h1>'
                f'<p>{text}</p></div>', status)


def load(token):
    r = db.one("SELECT * FROM sign_requests WHERE token=?", (token,))
    if not r:
        return None, message("This link is not valid", "ही लिंक वैध नाही",
                             "Ask the installer to send you a new link.", 404)
    if r["status"] == "signed":
        return r, message("Already signed. Thank you.", "सही झाली आहे. धन्यवाद.",
                          "Nothing more is needed from you on this link.")
    if r["status"] == "locked":
        return r, message("This link is locked", "ही लिंक बंद झाली आहे",
                          "Too many wrong attempts. Ask the installer for a new link.", 403)
    if datetime.fromisoformat(r["expires_at"]) < datetime.now():
        return r, message("This link has expired", "या लिंकची मुदत संपली आहे",
                          "Ask the installer to send you a new link.", 410)
    return r, None


def expected_digits(cid):
    c, d = closeout.data(cid)
    src = c["consumer_no"] or d.get("mobile", "")
    return "".join(ch for ch in src if ch.isdigit())[-4:]


def verified(request, r):
    return bool(r["verify_secret"]) and secrets.compare_digest(
        request.cookies.get("sg_" + r["token"][:12], ""), r["verify_secret"])


# ------------------------------- routes -------------------------------
@router.get("/{token}", response_class=HTMLResponse)
def sign_get(token: str, request: Request, error: str = ""):
    r, stop = load(token)
    if stop:
        return stop
    err = f'<div class="err">{e(error)}</div>' if error else ""
    if not verified(request, r):
        return page(f"""{err}<div class="card"><h1>Confirm it is you
<span class="mr">तुमची ओळख निश्चित करा</span></h1>
<form method="post" action="/sign/{e(token)}/verify">
<label for="digits">Last 4 digits of the consumer number on your electricity bill
<span class="mr">तुमच्या वीज बिलावरील ग्राहक क्रमांकाचे शेवटचे ४ अंक</span></label>
<input id="digits" name="digits" inputmode="numeric" maxlength="4" autocomplete="off" required>
<button type="submit">Continue / पुढे</button></form></div>""")
    cid = r["customer_id"]
    c, d = closeout.data(cid)
    docs = json.loads(r["docs"])
    titles = {s[0]: s[2] for s in closeout.DOCS_SPEC}
    saved = closeout.signature("consumer", cid)
    rows = "".join(f"""<div class="doc"><input type="checkbox" name="approve" value="{e(k)}" id="a_{e(k)}">
<label class="t" for="a_{e(k)}" style="margin:0;font-weight:500">{e(titles[k])}</label>
<a href="/sign/{e(token)}/doc/{e(k)}" target="_blank" rel="noopener">Read / वाचा</a></div>""" for k in docs)
    if saved:
        pad = f"""<div class="card"><label style="margin-top:0">Your saved signature
<span class="mr">तुमची जतन केलेली सही</span></label>
<img class="saved" src="{closeout._sig_img(saved)}" alt="Your saved signature">
<p class="small">It will be placed only on the documents you tick above.</p></div>"""
        consent = ("I approve the documents I ticked. The installer may place my saved signature on "
                   "these documents only.",
                   "मी निवडलेली कागदपत्रे मला मान्य आहेत. माझी जतन केलेली सही फक्त याच कागदपत्रांवर वापरता येईल.")
    else:
        pad = """<div class="card"><label style="margin-top:0">Sign here with your finger
<span class="mr">येथे बोटाने सही करा</span></label><canvas id="pad"></canvas>
<button type="button" class="ghost" id="clear">Clear / पुसा</button>
<input type="hidden" name="signature" id="signature"></div>"""
        consent = ("I have read the documents I ticked. The installer may place this signature on "
                   "those documents only, and submit them to MSEDCL and the PM Surya Ghar portal "
                   "for my rooftop solar system. Any other document must be shown to me and "
                   "approved by me first.",
                   "मी निवडलेली कागदपत्रे वाचली आहेत. ही सही फक्त याच कागदपत्रांवर वापरून ती महावितरण व "
                   "पीएम सूर्य घर पोर्टलवर सादर करण्यास माझी संमती आहे. इतर कोणतेही कागदपत्र आधी मला "
                   "दाखवून माझी परवानगी घ्यावी.")
    return page(f"""{err}<form method="post" action="/sign/{e(token)}" id="f">
<div class="card"><h1>Namaskar, {e((c['aadhaar_name'] or c['name']).split()[0])}
<span class="mr">कृपया कागदपत्रे वाचा आणि मान्य असलेली निवडा</span></h1>
<p class="small">Rooftop solar system, consumer no. ending {e(expected_digits(cid))}.
Read each document, then tick the ones you approve.</p>{rows}</div>
{pad}
<div class="card"><label for="name" style="margin-top:0">Your full name
<span class="mr">तुमचे पूर्ण नाव</span></label>
<input type="text" id="name" name="name" value="{e(c['aadhaar_name'] or '')}" required>
<div class="doc" style="margin-top:10px"><input type="checkbox" name="consent" value="yes" id="consent" required>
<label class="t" for="consent" style="margin:0;font-weight:500">{e(consent[0])}
<span class="mr">{e(consent[1])}</span></label></div>
<button type="submit">Sign and approve / सही करून मान्यता द्या</button></div></form>
<script>
const pad = document.getElementById('pad');
if (pad) {{
  const ctx = pad.getContext('2d'); let ink = 0, last = null;
  const size = () => {{ const r = pad.getBoundingClientRect(), k = devicePixelRatio || 1;
    pad.width = r.width * k; pad.height = r.height * k; ctx.scale(k, k);
    ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#0A1A3A'; ink = 0; }};
  size();
  const at = ev => {{ const r = pad.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; }};
  pad.addEventListener('pointerdown', ev => {{ pad.setPointerCapture(ev.pointerId); last = at(ev); }});
  pad.addEventListener('pointermove', ev => {{ if (!last) return; const p = at(ev);
    ctx.beginPath(); ctx.moveTo(...last); ctx.lineTo(...p); ctx.stroke(); ink += 1; last = p; }});
  ['pointerup', 'pointercancel'].forEach(t => pad.addEventListener(t, () => {{ last = null; }}));
  document.getElementById('clear').onclick = () => {{ ctx.clearRect(0, 0, pad.width, pad.height); ink = 0; }};
  document.getElementById('f').addEventListener('submit', ev => {{
    if (ink < 12) {{ ev.preventDefault(); alert('Please sign in the box. / कृपया चौकटीत सही करा.'); return; }}
    document.getElementById('signature').value = pad.toDataURL('image/png'); }});
}}
document.getElementById('f').addEventListener('submit', ev => {{
  if (!document.querySelector('input[name=approve]:checked')) {{
    ev.preventDefault(); alert('Tick at least one document. / किमान एक कागदपत्र निवडा.'); }} }});
</script>""")


@router.post("/{token}/verify")
def sign_verify(token: str, digits: str = Form("")):
    r, stop = load(token)
    if stop:
        return stop
    if digits.strip() != expected_digits(r["customer_id"]):
        n = r["attempts"] + 1
        db.ex("UPDATE sign_requests SET attempts=?, status=? WHERE token=?",
              (n, "locked" if n >= MAX_ATTEMPTS else r["status"], token))
        db.audit("customer", "customer", "E-sign check failed", r["customer_id"],
                 f"attempt {n} of {MAX_ATTEMPTS}")
        return RedirectResponse(f"/sign/{token}?error=" + quote(
            "Those digits do not match. Check the consumer number on your bill."), 303)
    secret = secrets.token_urlsafe(16)
    db.ex("UPDATE sign_requests SET verify_secret=? WHERE token=?", (secret, token))
    resp = RedirectResponse(f"/sign/{token}", 303)
    resp.set_cookie("sg_" + token[:12], secret, httponly=True, samesite="lax",
                    path=f"/sign/{token}", max_age=3600)
    return resp


@router.get("/{token}/doc/{key}", response_class=HTMLResponse)
def sign_doc(token: str, key: str, request: Request):
    r, stop = load(token)
    if stop:
        return stop
    if not verified(request, r) or key not in json.loads(r["docs"]):
        return message("Not available", "उपलब्ध नाही", "Open the link from the start.", 403)
    return HTMLResponse(closeout.unsigned_html(key, r["customer_id"]))


@router.post("/{token}", response_class=HTMLResponse)
async def sign_post(token: str, request: Request):
    r, stop = load(token)
    if stop:
        return stop
    if not verified(request, r):
        return RedirectResponse(f"/sign/{token}", 303)
    form = await request.form()
    cid, docs = r["customer_id"], json.loads(r["docs"])
    approve = [k for k in form.getlist("approve") if k in docs]
    name = (form.get("name") or "").strip()
    back = lambda msg: RedirectResponse(f"/sign/{token}?error=" + quote(msg), 303)
    if not approve:
        return back("Tick at least one document.")
    if form.get("consent") != "yes" or len(name) < 3:
        return back("Enter your full name and tick the consent box.")
    changed = [k for k in approve if closeout.doc_hash(k, cid) != docs[k]]
    if changed:
        titles = {s[0]: s[2] for s in closeout.DOCS_SPEC}
        return message("A document changed after this link was sent", "कागदपत्र बदलले आहे",
                       "Changed: " + ", ".join(titles[k] for k in changed) +
                       ". Nothing was signed. Ask the installer to send a fresh link.", 409)
    if not closeout.signature("consumer", cid):
        try:
            png = closeout.png_from_data_url(form.get("signature"))
        except ValueError as ex:
            return back(str(ex))
        closeout.save_signature("consumer", png, name, cid, token)
    ts = db.now()
    for k in approve:
        db.ex("""INSERT INTO approvals(customer_id,doc_key,doc_hash,request_token,ts)
                 VALUES(?,?,?,?,?)""", (cid, k, docs[k], token, ts))
    ip = request.client.host if request.client else ""
    db.ex("""UPDATE sign_requests SET status='signed',signed_at=?,signer_name=?,ip=?,ua=?
             WHERE token=?""", (ts, name, ip, request.headers.get("user-agent", "")[:300], token))
    closeout.invalidate(cid)
    db.audit("customer", "customer", "Customer e-signed documents", cid,
             f"{name}; approved {len(approve)} of {len(docs)}; from {ip}")
    return message("Thank you. Your documents are signed.", "धन्यवाद. तुमची सही झाली आहे.",
                   f"You approved {len(approve)} document(s). The installer will file them for you.")
