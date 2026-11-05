"""The field team's phone page and the serial numbers read off label photos.

One link per customer, sent to the installer on WhatsApp. On site they take: the photo of the
installed system (GPS from the photo, or the phone's location at that moment), a photo of each
module's label and the inverter's label. Serials are read from the label's barcode or QR code
on this server (zxing-cpp, offline). Only when there is no readable code, and an AI key is set,
is the label photo sent to the model, and those values are marked as such.

Nothing read here reaches a document until a person confirms it beside its photo: the module
serial numbers then go into the record, where the repeat checks (closeout.checks) also apply.
"""
import html, io, json, re, secrets
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageOps
from . import db, closeout, vault, extract
from .config import DOCS, vendor

router = APIRouter(prefix="/field")
VALID_DAYS = 3
KINDS = {"module": "PV module label", "inverter": "Inverter label"}
e = html.escape


# ------------------------------- links -------------------------------
def create_link(cid, user):
    token = secrets.token_urlsafe(18)
    db.ex("INSERT INTO field_links(token,customer_id,created_by,created_at,expires_at) VALUES(?,?,?,?,?)",
          (token, cid, user["username"], db.now(),
           (datetime.now() + timedelta(days=VALID_DAYS)).isoformat(timespec="seconds")))
    db.audit(user["username"], user["role"], "Sent the field photo link", cid, f"valid {VALID_DAYS} days")
    return token


def share(cid, url):
    c, d = closeout.data(cid)
    text = (f"Site photos for {(c['name'] or '').split()[0]} (consumer no. ...{(c['consumer_no'] or '')[-4:]}): open {url} on site. "
            "1) photo of the installed panels with location on, 2) the label of every panel, "
            "3) the inverter label.")
    return {"text": text, "whatsapp": "https://wa.me/?text=" + quote(text)}


def link_customer(token):
    r = db.one("SELECT * FROM field_links WHERE token=?", (token,))
    if not r or r["expires_at"] < db.now():
        raise HTTPException(404, "this link has expired; ask the office for a new one")
    return r["customer_id"]


# ------------------------------- reading -------------------------------
def pick_serial(text):
    """The serial number in a barcode's text. Labels may encode just the serial, or several
    fields (serial, power, date); take the longest token with both letters and digits."""
    t = (text or "").strip().upper()
    if re.fullmatch(r"[A-Z0-9][A-Z0-9/-]{6,30}", t) and sum(ch.isdigit() for ch in t) >= 4:
        return t
    tokens = [x for x in re.findall(r"[A-Z0-9]{8,30}", t) if sum(ch.isdigit() for ch in x) >= 4]
    mixed = [x for x in tokens if re.search(r"[A-Z]", x)]
    return max(mixed or tokens, key=len) if (mixed or tokens) else None


def read_codes(img):
    import zxingcpp
    out = []
    for im in (img, ImageOps.grayscale(img), ImageOps.autocontrast(ImageOps.grayscale(img))):
        for b in zxingcpp.read_barcodes(im):
            s = pick_serial(b.text)
            if s and s not in out:
                out.append(s)
        if out:
            break
    return out


async def read_label(img):
    """[(serial, source)] from one label photo; empty when nothing could be read."""
    found = [(s, "barcode") for s in read_codes(img)]
    st = extract.llm_status()
    if not found and st["enabled"]:
        try:
            got = await extract.llm_read("serial", st, image=img)
            v = got.get("serial") or {}
            s = pick_serial(v.get("value") if isinstance(v, dict) else v)
            if s:
                found.append((s, "AI read the printed text"))
        except Exception:
            pass
    return found


def _owner(serial, cid):
    """Another customer this serial is already on (confirmed reads or their record)."""
    hit = db.one("SELECT customer_id FROM serial_reads WHERE serial=? AND customer_id<>? AND status='confirmed'",
                 (serial, cid))
    if hit:
        return hit["customer_id"]
    for r in db.q("SELECT customer_id, data FROM closeout WHERE customer_id<>?", (cid,)):
        if serial in closeout.serials(json.loads(r["data"])):
            return r["customer_id"]
    return None


def _photo_path(cid, rid):
    return DOCS / cid / "labels" / f"{rid}.jpg"


async def add_label(cid, kind, raw, who):
    if kind not in KINDS:
        raise ValueError("unknown label type")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        raise ValueError("that file is not a photo")
    found = await read_label(img)
    thumb = closeout.jpeg_under(img, 160)
    stamp_field(cid, who)
    if not found:
        rid = db.ex("""INSERT INTO serial_reads(customer_id,kind,serial,source,photo,status,note,ts)
                       VALUES(?,?,?,?,?,?,?,?)""", (cid, kind, None, None, "", "unread",
                                                    "no barcode or QR found; retake closer, or type the number", db.now()))
        _save_thumb(cid, rid, thumb)
        return [{"id": rid, "status": "unread"}]
    out = []
    for s, source in found:
        dup = db.one("SELECT id FROM serial_reads WHERE customer_id=? AND serial=? AND status<>'rejected'", (cid, s))
        if dup:
            out.append({"id": dup["id"], "serial": s, "status": "repeat", "note": "already read from another photo"})
            continue
        other = _owner(s, cid)
        status, note = ("clash", f"already on {other}; MNRE rejects a repeated serial") if other else ("read", "")
        rid = db.ex("""INSERT INTO serial_reads(customer_id,kind,serial,source,photo,status,note,ts)
                       VALUES(?,?,?,?,?,?,?,?)""", (cid, kind, s, source, "", status, note, db.now()))
        _save_thumb(cid, rid, thumb)
        out.append({"id": rid, "serial": s, "status": status, "note": note, "source": source})
    return out


def _save_thumb(cid, rid, blob):
    p = _photo_path(cid, rid)
    p.parent.mkdir(parents=True, exist_ok=True)
    vault.write(p, blob)
    db.ex("UPDATE serial_reads SET photo=? WHERE id=?", (str(p), rid))


def typed(serial):
    """A serial typed by a person: the label's spacing ("PE55026A 318500") is not part of it."""
    return pick_serial(re.sub(r"\s+", "", serial or ""))


def add_typed(cid, kind, serial, who):
    s = typed(serial)
    if not s:
        raise ValueError("a serial number has at least 8 letters and digits, with 4 or more digits")
    if db.one("SELECT 1 FROM serial_reads WHERE customer_id=? AND serial=? AND status<>'rejected'", (cid, s)):
        raise ValueError(f"{s} is already in the list")
    other = _owner(s, cid)
    stamp_field(cid, who)
    return db.ex("""INSERT INTO serial_reads(customer_id,kind,serial,source,photo,status,note,ts)
                    VALUES(?,?,?,?,?,?,?,?)""", (cid, kind, s, "typed", "", "clash" if other else "read",
                                                 f"already on {other}" if other else "typed on site", db.now()))


def stamp_field(cid, who):
    """The first thing the field team sends starts the post-installation clock."""
    c, d = closeout.data(cid)
    if not d.get("field_at"):
        closeout.mark(cid, who, field_at=db.now())
        if not d.get("install_date"):
            closeout.save(cid, {"install_date": datetime.now().date().isoformat()}, who)
        from .registration import PRE_STAGES
        if c["stage"] in PRE_STAGES:
            db.ex("UPDATE customers SET stage='install' WHERE id=?", (cid,))


def reads(cid):
    return db.q("""SELECT id, kind, serial, source, status, note, ts, confirmed_by FROM serial_reads
                   WHERE customer_id=? AND status<>'rejected' ORDER BY kind DESC, id""", (cid,))


def summary(cid):
    c, d = closeout.data(cid)
    rs = reads(cid)
    mods = [r for r in rs if r["kind"] == "module" and r["serial"]]
    try:
        want = int(d.get("module_count") or 0)
    except ValueError:
        want = 0
    return {"reads": rs, "modules_read": len(mods),
            "modules_confirmed": sum(r["status"] == "confirmed" for r in mods),
            "to_confirm": sum(r["status"] == "read" for r in rs), "clash": sum(r["status"] == "clash" for r in rs),
            "unread": sum(r["status"] == "unread" for r in rs), "module_count": want,
            "inverter": next((r["serial"] for r in rs if r["kind"] == "inverter" and r["status"] == "confirmed"), None),
            "site_photo": bool(d.get("lat")) and (DOCS / cid / "site_photo.jpg").exists(),
            "photo_source": d.get("photo_source"),
            "link_open": bool(db.one("SELECT 1 FROM field_links WHERE customer_id=? AND expires_at>?", (cid, db.now())))}


def decide(cid, rid, action, user, serial=None):
    """Confirm, reject or correct one read. Confirmed module serials go into the record."""
    r = db.one("SELECT * FROM serial_reads WHERE id=? AND customer_id=?", (rid, cid))
    if not r:
        raise KeyError("no such read")
    if action == "reject":
        db.ex("UPDATE serial_reads SET status='rejected' WHERE id=?", (rid,))
    elif action in ("confirm", "correct"):
        s = typed(serial) if action == "correct" else r["serial"]
        if not s:
            raise ValueError("type the serial number exactly as on the label")
        other = _owner(s, cid)
        if other:
            raise ValueError(f"{s} is already on {other}; MNRE rejects a repeated serial number")
        if db.one("SELECT 1 FROM serial_reads WHERE customer_id=? AND serial=? AND id<>? AND status<>'rejected'",
                  (cid, s, rid)):
            raise ValueError(f"{s} is already in this customer's list")
        db.ex("UPDATE serial_reads SET serial=?, status='confirmed', confirmed_by=?, note=? WHERE id=?",
              (s, user["username"], "corrected by hand" if action == "correct" and s != r["serial"] else r["note"], rid))
    else:
        raise ValueError("unknown action")
    db.audit(user["username"], user["role"], f"Serial {action}ed", cid, f"{r['kind']} {serial or r['serial']}")
    sync(cid, user["username"])


def sync(cid, who):
    """Write confirmed serials into the record once every module is confirmed."""
    s = summary(cid)
    c, d = closeout.data(cid)
    vals = {}
    mods = [r["serial"] for r in s["reads"] if r["kind"] == "module" and r["status"] == "confirmed"]
    pending = s["to_confirm"] + s["clash"] + s["unread"]
    # only with the panel count known can "all in" be told from "the first few in"
    if mods and not pending and len(mods) == s["module_count"] and mods != closeout.serials(d):
        vals["module_serials"] = "\n".join(mods)
    if s["inverter"] and s["inverter"] != d.get("inverter_serial"):
        vals["inverter_serial"] = s["inverter"]
    if vals:
        closeout.save(cid, vals, who)
    done = bool(mods) and not pending and len(mods) == s["module_count"] and closeout.serials({**d, **vals}) == mods
    closeout.mark(cid, who, serials_at=(d.get("serials_at") or db.now()) if done else None)


# ------------------------------- the phone page -------------------------------
CSS = """*{box-sizing:border-box}body{margin:0;font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
background:#F2F4F6;color:#172029}.wrap{max-width:560px;margin:0 auto;padding:14px}
.hd{font-weight:700;color:#0B4F6C;margin:2px 0 12px}.card{background:#fff;border:1px solid #D9DFE5;border-radius:10px;
padding:14px;margin-bottom:12px}h1{font-size:19px;margin:0 0 4px}h2{font-size:16px;margin:0 0 8px}
.btn{display:block;text-align:center;width:100%;font-size:17px;font-weight:700;padding:13px;border:0;border-radius:8px;
background:#0B6E4F;color:#fff;margin-top:8px;cursor:pointer}.ghost{background:#E6EAEE;color:#172029}
.row{display:flex;gap:10px;align-items:center;padding:8px 0;border-top:1px solid #EDF0F3}.row img{width:64px;height:48px;
object-fit:cover;border-radius:4px}.mono{font-family:ui-monospace,monospace;font-size:15px}.small{font-size:13px;color:#5B6875}
.ok{color:#0B5133}.bad{color:#8A1C12}.warn{color:#8A5A00}input[type=text]{width:100%;font-size:17px;padding:10px;
border:1px solid #9AA6B2;border-radius:8px}#msg{min-height:22px;margin-top:6px}"""


def page(cid, token):
    c, d = closeout.data(cid)
    s = summary(cid)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Site photos</title><style>{CSS}</style></head>
<body><div class="wrap"><div class="hd">{e(vendor()['name'])} &middot; site photos</div>
<div class="card"><h1>{e((c['name'] or '').split()[0] if c['name'] else '')}</h1><div class="small">consumer no. &hellip;{e((c['consumer_no'] or '')[-4:])} &middot; {e(d.get('module_count') or '?')} panels</div></div>
<div class="card"><h2>1. Photo of the installed panels</h2>
<div class="small">Stand where the panels and the roof are visible. Location must be on: the office needs the GPS.</div>
<div id="siteState" class="small {'ok' if s['site_photo'] else ''}">{'&#10003; Saved. ' + e(d.get('lat', '')) + ', ' + e(d.get('lng', '')) if s['site_photo'] else 'Not taken yet.'}</div>
<label class="btn">Take the site photo<input type="file" accept="image/*" capture="environment" data-kind="site" hidden></label></div>
<div class="card"><h2>2. Label of every panel</h2>
<div class="small">One photo per panel, close enough that the barcode fills the middle of the picture.</div>
<label class="btn">Photo of a panel label<input type="file" accept="image/*" capture="environment" data-kind="module" multiple hidden></label>
<div class="row" style="border:0"><input type="text" id="typed" placeholder="or type a serial number"><button class="btn ghost" style="width:auto;margin:0" id="addTyped">Add</button></div>
<div id="count" class="small"></div><div id="list"></div></div>
<div class="card"><h2>3. Inverter label</h2>
<label class="btn">Photo of the inverter label<input type="file" accept="image/*" capture="environment" data-kind="inverter" hidden></label>
<div id="inv"></div></div><div id="msg" class="small"></div></div>
<script>
const T = {json.dumps(token)}, $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
const say = (t, cls) => {{ $('#msg').className = 'small ' + (cls || ''); $('#msg').textContent = t; }};
const STATE = {{read: ['warn', 'read, the office checks it'], confirmed: ['ok', 'confirmed'], clash: ['bad', 'repeat'], unread: ['bad', 'not readable']}};
async function refresh() {{
  const r = await (await fetch(`/field/${{T}}/list`)).json();
  const row = x => `<div class="row"><img src="/field/${{T}}/photo/${{x.id}}.jpg" alt="" onerror="this.style.visibility='hidden'">
    <div style="flex:1"><div class="mono">${{esc(x.serial || '—')}}</div><div class="small ${{STATE[x.status][0]}}">${{STATE[x.status][1]}}${{x.note ? ' · ' + esc(x.note) : ''}}</div></div></div>`;
  $('#list').innerHTML = r.reads.filter(x => x.kind === 'module').map(row).join('');
  $('#inv').innerHTML = r.reads.filter(x => x.kind === 'inverter').map(row).join('');
  $('#count').textContent = `${{r.modules_read}} of ${{r.module_count || '?'}} panels read`;
  if (r.site_photo) {{ $('#siteState').className = 'small ok'; $('#siteState').textContent = '✓ Saved with location'; }}
}}
function where() {{
  return new Promise(res => {{
    if (!navigator.geolocation) return res(null);
    navigator.geolocation.getCurrentPosition(p => res(p.coords), () => res(null), {{enableHighAccuracy: true, timeout: 9000, maximumAge: 0}});
  }});
}}
async function send(kind, file) {{
  const fd = new FormData(); fd.append('file', file); fd.append('kind', kind);
  if (kind === 'site') {{ say('Getting the location…'); const c = await where();
    if (c) {{ fd.append('lat', c.latitude); fd.append('lng', c.longitude); fd.append('acc', c.accuracy); }} }}
  say('Sending…');
  const r = await fetch(`/field/${{T}}/photo`, {{method: 'POST', body: fd}});
  const j = await r.json().catch(() => ({{}}));
  if (!r.ok) {{ say(j.detail || 'Could not send. Try again.', 'bad'); return; }}
  say(kind === 'site' ? 'Site photo saved.' : (j.read || []).map(x => x.serial ? x.serial + ': ' + (STATE[x.status] || ['', x.status])[1] : 'No barcode found. Retake closer, or type it.').join(' · '),
      (j.read || []).some(x => x.status !== 'read') ? 'warn' : 'ok');
  refresh();
}}
document.addEventListener('change', async ev => {{
  const k = ev.target.dataset.kind; if (!k) return;
  for (const f of ev.target.files) await send(k, f);
  ev.target.value = '';
}});
$('#addTyped').onclick = async () => {{
  const fd = new FormData(); fd.append('serial', $('#typed').value); fd.append('kind', 'module');
  const r = await fetch(`/field/${{T}}/typed`, {{method: 'POST', body: fd}});
  const j = await r.json().catch(() => ({{}}));
  if (!r.ok) return say(j.detail || 'Could not add', 'bad');
  $('#typed').value = ''; say('Added.', 'ok'); refresh();
}};
refresh();
</script></body></html>"""


@router.get("/{token}", response_class=HTMLResponse)
def field_get(token: str):
    return HTMLResponse(page(link_customer(token), token))


@router.get("/{token}/list")
def field_list(token: str):
    return summary(link_customer(token))


@router.post("/{token}/photo")
async def field_photo(token: str, file: UploadFile = File(...), kind: str = Form("module"),
                      lat: str = Form(""), lng: str = Form(""), acc: str = Form("")):
    cid = link_customer(token)
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(400, "that photo is over 15 MB")
    who = f"field:{token[:6]}"
    try:
        if kind == "site":
            loc = (lat, lng, acc or "0") if lat and lng else None
            got = closeout.save_photo(cid, raw, who, loc)
            stamp_field(cid, who)
            db.audit("field team", "field", "Site photo from the field", cid, f"GPS {got[0]}, {got[1]}")
            return {"ok": True, "lat": got[0], "lng": got[1]}
        out = await add_label(cid, kind, raw, who)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except OSError:
        raise HTTPException(400, "that file is not a photo")
    db.audit("field team", "field", "Label photo from the field", cid,
             f"{kind}: " + ", ".join(x.get("serial") or x["status"] for x in out))
    return {"ok": True, "read": out}


@router.post("/{token}/typed")
def field_typed(token: str, serial: str = Form(""), kind: str = Form("module")):
    cid = link_customer(token)
    try:
        add_typed(cid, kind if kind in KINDS else "module", serial, f"field:{token[:6]}")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return {"ok": True}


@router.get("/{token}/photo/{rid}.jpg")
def field_thumb(token: str, rid: int):
    return thumb(link_customer(token), rid)


def thumb(cid, rid):
    r = db.one("SELECT photo FROM serial_reads WHERE id=? AND customer_id=?", (rid, cid))
    if not r or not r["photo"] or not Path(r["photo"]).exists():
        raise HTTPException(404)
    return Response(vault.read(Path(r["photo"])), media_type="image/jpeg", headers={"Cache-Control": "private"})

