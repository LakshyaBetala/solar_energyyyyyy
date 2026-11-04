"""The installation team's upload page: one link per customer, opened on a phone.

It can only add files to that one customer. It shows the customer's first name and the checklist of
what is still needed, nothing else: no address, no phone number, no other customer. The link
expires, can be switched off, and every upload is audited. The phone's location is requested only
when the person ticks the box, and only used when the photo carries no location of its own.
"""
from urllib.parse import quote
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from . import db, closeout, k2
from .esign import page, message, e

router = APIRouter(prefix="/field")
TOO_MANY = 80  # uploads one link accepts, so a leaked link cannot fill the disk


def _use(token):
    r, problem = k2.field_link_get(token)
    return r, (message("Link not available", "", e(problem), 403) if problem else None)


@router.get("/{token}", response_class=HTMLResponse)
def field_get(token: str, error: str = "", done: str = ""):
    r, stop = _use(token)
    if stop:
        return stop
    cid = r["customer_id"]
    c, d = closeout.data(cid)
    first = ((c["aadhaar_name"] or c["name"]) or "customer").split()[0]
    rows = ""
    for s in k2.field_checklist(cid):
        gps = s["gps"]
        rows += f"""<div class="card"><form method="post" action="/field/{e(token)}/upload" enctype="multipart/form-data"
 data-gps="{'1' if gps else ''}"><label style="margin-top:0">{e(s['label'])}
<span class="mr">{'done' if s['done'] else ('needed' if s['required'] else 'optional')}{f" ({s['count']})" if s['done'] and s['count'] > 1 else ''}</span></label>
<input type="hidden" name="slot" value="{e(s['key'])}">
<input type="file" name="file" required accept="{'.xlsx,.csv,.txt' if s['key'] == 'serial_sheet' else 'image/*,.pdf' if s['key'] in ('dcr_cert', 'invoice') else 'image/*'}">
{f'''<label style="font-weight:500"><input type="checkbox" name="consent" value="yes" class="consent" style="width:auto;display:inline"> Use this phone's location if the photo has none. It is used only for this photo.</label>
<input type="hidden" name="lat"><input type="hidden" name="lng"><input type="hidden" name="acc">''' if gps else ''}
<button type="submit">Upload</button></form></div>"""
    flash = (f'<div class="err">{e(error)}</div>' if error else "") + \
            (f'<div class="ok" style="margin-bottom:12px">{e(done)}</div>' if done else "")
    return page(f"""{flash}<div class="card"><h1>Installation uploads
<span class="mr">Consumer no. ending {e((c['consumer_no'] or '')[-4:])} &middot; {e(first)}</span></h1>
<p class="small">Add the photos and files for this installation. Each upload is checked; if something is
wrong you will be told what to fix.</p></div>{rows}
<script>
document.querySelectorAll('form[data-gps="1"]').forEach(f => f.addEventListener('submit', ev => {{
  const box = f.querySelector('.consent');
  if (!box.checked || f.dataset.sent) return;           // location is asked for only when ticked
  ev.preventDefault();
  navigator.geolocation.getCurrentPosition(p => {{
    f.lat.value = p.coords.latitude; f.lng.value = p.coords.longitude; f.acc.value = p.coords.accuracy;
    f.dataset.sent = '1'; f.submit();
  }}, () => {{ box.checked = false; alert('Location was not shared. Send the photo without it, or turn location on and try again.'); }},
  {{ enableHighAccuracy: true, timeout: 15000 }});
}}));
</script>""")


@router.post("/{token}/upload", response_class=HTMLResponse)
async def field_post(token: str, request: Request, slot: str = Form(""), file: UploadFile = File(...),
                     consent: str = Form(""), lat: str = Form(""), lng: str = Form(""), acc: str = Form("")):
    r, stop = _use(token)
    if stop:
        return stop
    cid = r["customer_id"]
    back = lambda **q: RedirectResponse(f"/field/{token}?" + "&".join(f"{k}={quote(v)}" for k, v in q.items()), 303)
    if slot not in {s[0] for s in k2.FIELD_SLOTS}:
        return back(error="Unknown upload type.")
    n = db.one("SELECT COUNT(*) n FROM audit WHERE action='Field upload' AND target=? AND detail LIKE ?",
               (cid, f"%{token[:6]}%"))["n"]
    if n >= TOO_MANY:
        return back(error="This link has reached its upload limit. Ask the office for a new one.")
    who = "field:" + token[:6]
    blob = await file.read()
    try:
        if slot == "site_photo":
            gps = None
            if lat and lng:
                try:
                    gps = (float(lat), float(lng), float(acc) if acc else None)
                except ValueError:
                    raise ValueError("the location sent by the phone was not understood; send the photo again")
            la, ln, src = k2.site_photo(cid, blob, who, gps, consent == "yes")
            note = f"{slot} at {la}, {ln} ({src})"
        elif slot == "serial_sheet":
            good, bad = k2.parse_serials(file.filename, blob)
            if bad:
                raise ValueError(f"{len(bad)} value(s) are not serial numbers (first: {bad[0][0]}). Nothing was saved")
            res = k2.set_serials(cid, good, who, "field sheet")
            note = f"{slot}: {res['count']} serials"
        else:
            k2.store_doc(cid, slot, file.filename, blob, who)
            note = slot
    except ValueError as ex:
        return back(error=str(ex))
    k2.track(cid, "field", "uploaded", who, None, note)
    db.audit("field", "field", "Field upload", cid, f"{note} via {token[:6]}")
    return back(done="Uploaded. Thank you.")
