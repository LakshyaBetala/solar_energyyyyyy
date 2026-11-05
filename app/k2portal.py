"""Sandbox of the K2 portal screens, so the co-pilot and the tracking can be exercised end to end
without touching a government portal.

Labels marked REAL are copied from screens the client showed (tests/real_labels.py). Labels marked
GUESS follow Solara's own field names because those screens have not been seen yet; they are here to
test the flow, and say nothing about what the real portal calls them (handover task A8).

Like the real portals, a page refuses a submission with required fields empty, and Submit is
pressed by a person. Nothing here is stored beyond a reference number per submission.
"""
import html, itertools
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from .config import vendor

router = APIRouter(prefix="/k2portal")
e = html.escape
_ref = itertools.count(41001)
DONE = {}  # (page, submitted reference) -> fields, in memory

# key: (title, [(id, label, kind, required, source)], needs_declaration)
PAGES = {
    "sfr": ("Site Feasibility Report", [
        ("area", "Available shadow free roof area [Meter Square]:*", "text", 1, "REAL"),
        ("perm", "Permissible RTS Installation Capacity By Vendor(kW):*", "text", 1, "REAL"),
        ("qa", "Quotation Amount(Rs.):*", "text", 1, "REAL"),
        ("qd", "Quotation Document:*", "file", 1, "REAL"),
        ("emp", "Name of vendor employee visited the project site:*", "text", 1, "REAL"),
        ("cnum", "Contact Number:*", "text", 1, "REAL"),
        ("pre", "Pre-installation photo", "file", 0, "GUESS")], True),
    "install/1": ("Submit Installation: step 1", [
        ("vn", "Name of Vendor:*", "text", 1, "REAL"), ("lat", "Latitude:*", "text", 1, "REAL"),
        ("lng", "Enter longitude:*", "text", 1, "REAL")], False),
    "install/2": ("Submit Installation: step 2", [
        ("mk", "PV module make", "text", 1, "GUESS"), ("al", "ALMM model no.", "text", 1, "GUESS"),
        ("wp", "Wattage per module (Wp)", "text", 1, "GUESS"), ("nm", "No. of modules", "text", 1, "GUESS"),
        ("sn", "Module serial numbers, one per line", "textarea", 1, "GUESS")], False),
    "install/3": ("Submit Installation: step 3", [
        ("im", "Inverter make and model", "text", 1, "GUESS"), ("ik", "Inverter rating (kW)", "text", 1, "GUESS"),
        ("is", "Inverter serial no.", "text", 1, "GUESS"), ("iy", "Inverter year of manufacture", "text", 1, "GUESS"),
        ("ms", "Generation meter serial no.", "text", 1, "GUESS")], False),
    "install/4": ("Submit Installation: step 4", [
        ("dc", "DCR certificate no.", "text", 1, "GUESS"), ("iv", "Invoice / e-way bill no.", "text", 1, "GUESS"),
        ("cm", "Cell manufacturer", "text", 1, "GUESS"), ("ci", "Cell GST invoice no.", "text", 1, "GUESS"),
        ("dt", "Installation date", "text", 1, "GUESS"), ("df", "DCR certificate file", "file", 1, "GUESS")], False),
    "install/5": ("Submit Installation: step 5", [
        ("ec", "No. of separate earthings", "text", 1, "GUESS"), ("eo", "Earth resistance (ohm)", "text", 1, "GUESS"),
        ("la", "Lightning arrester installed", "text", 1, "GUESS"),
        ("pc", "All earthing and protection checks done", "text", 1, "GUESS"),
        ("ph", "Installation photo", "file", 1, "GUESS")], True),
    "dcr": ("NISE DCR Details (B2C)", [
        ("can", "Consumer Application Number", "text", 1, "REAL"), ("cname", "Customer Name", "text", 1, "REAL"),
        ("cmob", "Consumer Mobile", "text", 1, "REAL"), ("caddr", "Customer Address", "textarea", 1, "REAL"),
        ("cpin", "Customer Pin Code", "text", 1, "REAL"), ("inv", "Invoice Number / E-Way Bill", "text", 1, "REAL"),
        ("pan", "Panel Numbers (Enter Or Upload Via Excel)", "textarea", 1, "REAL"),
        ("cert", "Certificate file", "file", 1, "REAL"),
        ("xl", "Upload Excel of panel numbers", "file", 0, "GUESS")], True),
    # The loan portal's labels are not known. The customer's own Aadhaar number and OTP, and the bank
    # and branch they pick, are here so the test can prove the co-pilot leaves them alone.
    "jansamarth": ("Jan Samarth loan application", [
        ("jn", "Applicant Name", "text", 1, "GUESS"), ("jm", "Mobile Number", "text", 1, "GUESS"),
        ("je", "Email ID", "text", 0, "GUESS"), ("ja", "Address", "textarea", 1, "GUESS"),
        ("jp", "Pin Code", "text", 1, "GUESS"), ("jd", "District", "text", 1, "GUESS"),
        ("jl", "Loan Amount Required (Rs)", "text", 1, "GUESS"),
        ("jaa", "Aadhaar Number", "text", 1, "GUESS"), ("jo", "Aadhaar OTP", "text", 1, "GUESS"),
        ("sb", "Select Bank", "select", 1, "GUESS"), ("sbr", "Select Branch", "select", 1, "GUESS")], True),
}
CSS = """body{font:14px system-ui,Arial;margin:0;color:#222}.top{background:#1A3E73;color:#fff;padding:10px 16px}
.wrap{max-width:640px;margin:16px auto;padding:0 14px}.fg{margin:10px 0}label{display:block;font-weight:600}
input[type=text],textarea{width:100%;padding:6px;box-sizing:border-box}.src{font-size:10px;color:#888}
.alert{background:#fdecea;color:#8a1c12;padding:10px;border-radius:6px;margin:10px 0}button{padding:8px 22px}"""


def shell(title, body):
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(title)}</title>
<style>{CSS}</style></head><body><div class="top"><b>Sandbox portal</b> &middot; {e(vendor()['name'])}</div>
<div class="wrap"><h2>{e(title)}</h2>{body}</div></body></html>""")


def form(key, errors=()):
    title, fields, decl = PAGES[key]
    rows = ""
    for i, label, kind, req, src in fields:
        ctl = (f'<input type="file" id="{i}" name="{i}">' if kind == "file" else
               f'<select id="{i}" name="{i}"><option value="">Select</option><option>Bank of Maharashtra</option>'
               f'<option>Manchar branch</option></select>' if kind == "select" else
               f'<textarea id="{i}" name="{i}" rows="3"></textarea>' if kind == "textarea" else
               f'<input type="text" id="{i}" name="{i}">')
        rows += f'<div class="fg"><label for="{i}">{e(label)}</label>{ctl}<span class="src">{src}</span></div>'
    if decl:
        rows += '<div class="fg"><label><input type="checkbox" id="declaration" name="declaration"> I declare the details are correct</label></div>'
    err = f'<div class="alert" role="alert">{"<br>".join(e(m) for m in errors)}</div>' if errors else ""
    return shell(title, f'{err}<form method="post" enctype="multipart/form-data" action="/k2portal/{key}">{rows}'
                        f'<button type="submit" id="btnSubmit">Submit</button></form>')


async def _read(request):
    """Required text from a multipart/urlencoded form without a dependency on python-multipart for
    anything but parsing."""
    f = await request.form()
    return {k: (v if isinstance(v, str) else (v.filename or "")) for k, v in f.items()}


def _handle(key):
    async def get():
        return form(key)

    async def post(request: Request):
        data = await _read(request)
        title, fields, decl = PAGES[key]
        miss = [label.rstrip(":*") + " is required" for i, label, kind, req, src in fields if req and not data.get(i, "").strip()]
        if decl and not data.get("declaration"):
            miss.append("Please accept the declaration")
        if miss:
            return form(key, miss)
        ref = f"SBX-{key.replace('/', '').upper()}-{next(_ref)}"
        DONE[ref] = data
        return shell("Submitted", f'<p>Your submission was received.</p><table><tr><td>Reference Number</td><td id="refNo">{e(ref)}</td></tr></table>'
                                  f'<p><a href="/k2portal/{key}">Back</a></p>')
    router.add_api_route(f"/{key}", get, methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(f"/{key}", post, methods=["POST"], response_class=HTMLResponse)


for _k in PAGES:
    _handle(_k)
