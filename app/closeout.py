"""Close-out: from "installation done" to the six MSEDCL documents and the vendor-consumer
agreement, signed with the customer's consent.

What was installed is entered once and feeds every document. Each document is rendered as
HTML and hashed without signatures; that hash is exactly what the customer approves. The
customer's signature is only ever placed on a document whose current hash they approved, so
a document that changed after approval goes back to them. Every output fits MSEDCL's
300 KB per-file limit.
"""
import base64, hashlib, html, io, json, re
from datetime import datetime
import fitz  # PyMuPDF: shrinks manufacturer datasheets to fit the upload limit
from PIL import Image, ExifTags
from playwright.async_api import async_playwright
from . import db, vault
from .config import DOCS, DATA, MAX_UPLOAD_KB, vendor

LIBRARY = DATA / "library"  # datasheets, uploaded once per module + inverter pair
LIBRARY.mkdir(parents=True, exist_ok=True)
# shortcut: formats rebuilt from the screens on the client call; swap in the client's own
# template wording, then set this False so the "draft format" footer disappears
TEMPLATE_DRAFT = True

FIELDS = [  # key, label, group
    ("pmsg_app_no", "PM Surya Ghar application no.", "References"),
    ("msedcl_app_id", "MSEDCL application ID", "References"),
    ("dcr_cert_no", "DCR certificate no.", "References"),
    ("invoice_no", "Invoice / e-way bill no.", "References"),
    ("agreement_date", "Agreement date", "References"),
    ("install_date", "Installation date", "References"),
    ("rts_cost", "Total cost of installation, incl. taxes (Rs)", "References"),
    ("mobile", "Customer mobile", "Connection"),
    ("aadhaar_last4", "Aadhaar, last 4 digits only", "Connection"),
    ("billing_unit", "Name of billing unit", "Connection"),
    ("sanctioned_load", "Sanctioned / connected load (kW)", "Connection"),
    ("phase", "Type of connection", "Connection"),
    ("tariff", "Consumer tariff category", "Connection"),
    ("module_make", "PV module make", "Modules"),
    ("almm_model", "ALMM model no.", "Modules"),
    ("module_wp", "Wattage per module (Wp)", "Modules"),
    ("module_count", "No. of modules", "Modules"),
    ("module_serials", "Module serial numbers, one per line", "Modules"),
    ("cell_maker", "Cell manufacturer", "Modules"),
    ("cell_invoice", "Cell GST invoice no.", "Modules"),
    ("warranty", "Warranty, product + performance (years)", "Modules"),
    ("inverter_make", "Inverter make and model", "Inverter and meter"),
    ("inverter_kw", "Inverter rating (kW)", "Inverter and meter"),
    ("inverter_serial", "Inverter serial no.", "Inverter and meter"),
    ("inverter_year", "Inverter year of manufacture", "Inverter and meter"),
    ("meter_serial", "Generation meter serial no.", "Inverter and meter"),
    ("earthing_count", "No. of separate earthings", "Earthing and protection"),
    ("earth_ohm", "Earth resistance (ohm)", "Earthing and protection"),
    ("lightning_arrester", "Lightning arrester installed", "Earthing and protection"),
    ("protection_checks", "All earthing and protection checks done", "Earthing and protection"),
]
LABEL = {k: lbl for k, lbl, _ in FIELDS}
SYSTEM = ("lat", "lng", "photo_taken", "msedcl_uploaded", "msedcl_uploaded_at")

PLANT = ("module_make", "almm_model", "module_wp", "module_count", "inverter_make", "inverter_kw")
DOCS_SPEC = [  # key, MSEDCL upload slot (None: not an MSEDCL upload), title, signed by,
    # needs: every field the document prints, so nothing goes out with a blank in it
    ("agreement", None, "Vendor-consumer agreement", ("consumer", "vendor"),
     ("agreement_date", "rts_cost", "pmsg_app_no")),
    ("wcr", 1, "Work Completion Report", ("consumer", "vendor"),
     PLANT + ("install_date", "billing_unit", "sanctioned_load", "phase", "tariff", "warranty",
              "inverter_year", "earthing_count", "earth_ohm", "lightning_arrester",
              "protection_checks")),
    ("annexure1", 2, "Annexure-I Installation Report of RE Gen. System", ("consumer", "vendor"),
     PLANT + ("install_date", "module_serials", "inverter_serial", "meter_serial", "lat",
              "pmsg_app_no", "msedcl_app_id")),
    ("dcr_decl", 3, "Declaration of DCR", ("vendor",),
     ("module_make", "module_wp", "module_count", "module_serials", "cell_maker",
      "cell_invoice", "dcr_cert_no", "pmsg_app_no")),
    ("net_agreement", 4, "Net Agreement Bond", ("consumer",),
     ("install_date", "tariff", "module_wp", "module_count", "inverter_kw", "meter_serial")),
    ("datasheet", 5, "Brochure/Datasheet of PV modules and inverter", (),
     ("module_make", "inverter_make")),
    ("site_photo", 6, "Photo of installed PV system with Geo Co-ordinates", (), ("lat",)),
]
SPEC = {s[0]: s for s in DOCS_SPEC}


# ------------------------------- the record -------------------------------
def data(cid):
    """The customer row, and the close-out record laid over what the system already knows."""
    c = db.one("SELECT * FROM customers WHERE id=?", (cid,))
    if not c:
        raise KeyError(f"unknown customer {cid}")
    pc = db.one("SELECT * FROM portal_consumers WHERE consumer_no=?",
                (c["consumer_no"],)) if c["consumer_no"] else None
    base = {"sanctioned_load": f"{pc['sanctioned_load']:g}", "tariff": pc["tariff"],
            "mobile": pc["msisdn"]} if pc else {}
    if c["application_no"]:
        base["pmsg_app_no"] = c["application_no"]
    row = db.one("SELECT data FROM closeout WHERE customer_id=?", (cid,))
    return c, {**base, **json.loads(row["data"] if row else "{}")}


def _store(cid, d, user):
    db.ex("""INSERT INTO closeout(customer_id,data,updated_at,updated_by) VALUES(?,?,?,?)
             ON CONFLICT(customer_id) DO UPDATE SET data=excluded.data,
             updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
          (cid, json.dumps(d, ensure_ascii=False), db.now(), user))


def invalidate(cid):
    """Generated files go stale the moment their inputs change; drop them so nothing old
    can be uploaded."""
    db.ex("DELETE FROM documents WHERE customer_id=? AND kind LIKE 'co_%'", (cid,))


def save(cid, values, user):
    c, d = data(cid)
    d.update({k: str(v).strip() for k, v in values.items() if k in LABEL})
    _store(cid, d, user)
    invalidate(cid)
    return d


def mark(cid, user, **system):
    c, d = data(cid)
    d.update({k: v for k, v in system.items() if k in SYSTEM})
    _store(cid, d, user)


def serials(d):
    return [s for s in re.split(r"[\s,;]+", d.get("module_serials", "")) if s]


def capacity(d):
    try:
        return round(float(d["module_wp"]) * int(d["module_count"]) / 1000, 2)
    except (KeyError, ValueError):
        return None


def checks(cid, d):
    """Problems that would get a filing rejected. 'bad' blocks the documents, 'warn' does not."""
    out, sn = [], serials(d)
    try:
        n = int(d.get("module_count") or 0)
    except ValueError:
        n = 0
    if sn and n and len(sn) != n:
        out.append(("bad", f"{n} modules but {len(sn)} serial numbers"))
    dup = sorted({s for s in sn if sn.count(s) > 1})
    if dup:
        out.append(("bad", "Serial number listed twice: " + ", ".join(dup)))
    for row in db.q("SELECT customer_id, data FROM closeout WHERE customer_id<>?", (cid,)):
        clash = set(sn) & set(serials(json.loads(row["data"])))
        if clash:
            out.append(("bad", f"Serial {sorted(clash)[0]} is already on {row['customer_id']}; "
                               "MNRE rejects repeated serial numbers"))
    try:
        if d.get("earth_ohm") and float(d["earth_ohm"]) >= 5:
            out.append(("bad", "Earth resistance must be below 5 ohm"))
    except ValueError:
        out.append(("bad", "Earth resistance is not a number"))
    if d.get("protection_checks") and d["protection_checks"] != "Yes":
        out.append(("bad", "Earthing and protection checks are not all done"))
    cap = capacity(d)
    try:
        if cap and d.get("sanctioned_load") and cap > float(d["sanctioned_load"]):
            out.append(("warn", f"Plant {cap} kWp is above the sanctioned load "
                                f"{d['sanctioned_load']} kW"))
    except ValueError:
        pass
    return out


# ------------------------------- templates -------------------------------
e = lambda v: html.escape(str(v if v not in (None, "") else "—"))

CSS = """
@page{size:A4;margin:14mm 15mm}
body{font:10.5px/1.45 Arial,sans-serif;color:#111;margin:0}
h1{font-size:13.5px;text-align:center;margin:0 0 3px;text-transform:uppercase;letter-spacing:.02em}
.sub{text-align:center;font-size:10px;margin-bottom:10px;color:#333}
table{width:100%;border-collapse:collapse;margin:6px 0}
td,th{border:1px solid #444;padding:3px 6px;vertical-align:top;text-align:left}
th{background:#eee;font-weight:700}
td.n{width:26px;text-align:center}
td.k{width:46%}
p{margin:6px 0;text-align:justify}
.sigs{display:flex;gap:28px;margin-top:22px}
.sig{flex:1;font-size:10px}
.sig .ln{height:52px;border-bottom:1px solid #222;display:flex;align-items:flex-end}
.sig .ln img{max-height:50px;max-width:200px}
.sig .cap{font-size:7.5px;color:#555;margin-top:2px}
.ft{margin-top:14px;font-size:7.5px;color:#777;border-top:1px dashed #aaa;padding-top:4px}
ol{margin:4px 0 4px 18px;padding:0}
"""


def _page(title, sub, body, d):
    draft = ('<div class="ft">Draft format generated by Solara. Replace with the installer\'s '
             'own template text before filing.</div>') if TEMPLATE_DRAFT else ""
    return (f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><h1>{e(title)}</h1>'
            f'<div class="sub">{sub}</div>{body}{draft}')


def _rows(rows):
    return "<table>" + "".join(f'<tr><td class="k">{e(k)}</td><td>{e(v)}</td></tr>'
                               for k, v in rows) + "</table>"


def _sig(label, who, sig):
    s = sig.get(who)
    img = f'<img src="{s["img"]}" alt="">' if s else ""
    cap = f'<div class="cap">{e(s["caption"])}</div>' if s else ""
    return f'<div class="sig"><div class="ln">{img}</div><div>{label}</div>{cap}</div>'


def _date(v):
    try:
        return datetime.fromisoformat(v).strftime("%d-%m-%Y")
    except (TypeError, ValueError):
        return v


def _below5(v):
    try:
        return float(v) < 5
    except (TypeError, ValueError):
        return False


def _masked(d):
    return f"XXXX XXXX {d['aadhaar_last4']}" if d.get("aadhaar_last4") else "—"


def t_agreement(c, d, sig, V):
    body = f"""<p>This agreement is executed on <b>{e(_date(d.get('agreement_date')))}</b> for design,
supply, installation, commissioning and 5-year comprehensive maintenance of a rooftop solar (RTS)
project/system along with warranty under PM Surya Ghar: Muft Bijli Yojana</p>
<p style="text-align:center"><b>Between</b></p>
<p><b>{e(c['aadhaar_name'])}</b>, having address {e(c['address'])}, {e(c['pin'])}, electricity
consumer number {e(c['consumer_no'])} (hereinafter referred to as the first party, i.e.
consumer / purchaser / owner of the system)</p>
<p style="text-align:center"><b>And</b></p>
<p><b>{e(V['name'])}</b> (hereinafter referred to as the second party, i.e. vendor)</p>
{_rows([("RTS capacity", f"{c['kw']} kW"),
        ("Total cost of RTS installation (inclusive of taxes and all other charges)",
         f"Rs {d.get('rts_cost')}"),
        ("PM Surya Ghar application no.", d.get("pmsg_app_no"))])}
<p><b>Vendor responsibilities.</b></p><ol>
<li>Solar modules, including the cells, and inverters shall be manufactured in India and conform to
the standards and specifications prescribed by MNRE.</li>
<li>Procurement and supply of the complete system as per BIS/IS/IEC standards and the safety
guidelines for rooftop solar plants.</li>
<li>Complete installation, civil and electrical work following all safety and relevant BIS
standards.</li>
<li>Documentation (technical catalogues, warranty certificates, BIS certificates and test reports)
provided to the consumer.</li>
<li>Presence at testing and commissioning by the DISCOM.</li>
<li>Five years of comprehensive operation and maintenance, and guidance to the consumer on cleaning
and upkeep.</li></ol>
<p><b>Consumer responsibilities.</b></p><ol>
<li>Allow submission of the online application on the National Portal, the net-metering and
inspection applications, and upload of the relevant documents.</li>
<li>Secure storage of the material delivered at the premises until handover.</li>
<li>Access to the roof for installation, operation, maintenance, testing and meter reading.</li>
<li>Electricity and water during installation and for cleaning of the panels.</li>
<li>Report any malfunction to the vendor during the warranty period.</li>
<li>Pay the amount as per the payment schedule agreed with the vendor.</li></ol>
<div class="sigs">{_sig("First party (consumer)", "consumer", sig)}
{_sig(f"Second party (vendor) &middot; {e(V['name'])}", "vendor", sig)}</div>"""
    return _page("Agreement between consumer and vendor",
                 "Installation of grid-connected rooftop solar (RTS) project under "
                 "PM Surya Ghar: Muft Bijli Yojana", body, d)


def t_wcr(c, d, sig, V):
    ok = d.get("protection_checks") or "—"
    checks_ = ["Separate earthing provided for lightning arrester",
               "Separate earthing provided for solar panel structure",
               "Earthing provided for DCDB", "Earthing provided for ACDB",
               "Separate earthing for grid inverter (AC side)",
               "All metallic body parts earthed", "DC fuses provided"]
    rows = [("Name of consumer", c["aadhaar_name"]), ("Consumer number", c["consumer_no"]),
            ("Aadhaar (masked)", _masked(d)), ("Installation address", f"{c['address']}, {c['pin']}"),
            ("Name of billing unit", d.get("billing_unit")),
            ("MSEDCL sanctioned and connected load", f"{d.get('sanctioned_load')} kW"),
            ("Type of connection", d.get("phase")), ("Consumer tariff category", d.get("tariff")),
            ("Installed rooftop solar capacity (AC)", f"{d.get('inverter_kw')} kW"),
            ("Date of installation", _date(d.get("install_date")))]
    body = f"""{_rows(rows)}
<table><tr><th colspan="2">Checking of earthing system</th></tr>
{"".join(f'<tr><td class="k">{e(x)}</td><td>{e(ok)}</td></tr>' for x in checks_)}</table>
<table><tr><th colspan="2">Solar PV modules</th></tr>
{"".join(f'<tr><td class="k">{e(k)}</td><td>{e(v)}</td></tr>' for k, v in [
        ("Make of module", d.get("module_make")), ("ALMM model number", d.get("almm_model")),
        ("Wattage per module", f"{d.get('module_wp')} Wp"), ("No. of modules", d.get("module_count")),
        ("Total capacity", f"{capacity(d)} kWp"),
        ("Warranty (product + performance)", d.get("warranty"))])}</table>
<table><tr><th colspan="2">Power conditioning unit (inverter)</th></tr>
{"".join(f'<tr><td class="k">{e(k)}</td><td>{e(v)}</td></tr>' for k, v in [
        ("Make and model", d.get("inverter_make")), ("Rating", f"{d.get('inverter_kw')} kW"),
        ("Type of charge controller", "MPPT"), ("Year of manufacturing", d.get("inverter_year"))])}</table>
<table><tr><th colspan="2">Earthing and protection</th></tr>
<tr><td class="k">No. of separate earthings with earth resistance</td>
<td>{e(d.get('earthing_count'))} earthings, {e(d.get('earth_ohm'))} ohm</td></tr>
<tr><td class="k">Earth resistance measured in the presence of a licensed electrical
contractor/supervisor and found below 5 ohm as per MNRE OM dated 07.06.2024</td>
<td>{"Yes" if _below5(d.get("earth_ohm")) else "—"}</td></tr>
<tr><td class="k">Lightning arrester</td><td>{e(d.get('lightning_arrester'))}</td></tr></table>
<p>We, {e(V['name'])} (vendor) and {e(c['aadhaar_name'])} (consumer), bearing consumer number
{e(c['consumer_no'])}, have ensured the structural stability of the installed solar power plant
and obtained the requisite permissions from the concerned authority. If in future the installed
solar plant collapses or is damaged by any means, MSEDCL will not be held responsible for any loss
to property or human life.</p>
<div class="sigs">{_sig("Consumer", "consumer", sig)}
{_sig(f"Vendor &middot; {e(V['name'])}", "vendor", sig)}</div>"""
    return _page("Work completion report", "Grid-connected rooftop solar PV system", body, d)


def t_annexure1(c, d, sig, V):
    sn = serials(d)
    body = f"""{_rows([("Name of consumer", c["aadhaar_name"]), ("Consumer number", c["consumer_no"]),
                   ("Address", f"{c['address']}, {c['pin']}"),
                   ("PM Surya Ghar application no.", d.get("pmsg_app_no")),
                   ("MSEDCL application ID", d.get("msedcl_app_id")),
                   ("Installed capacity (DC)", f"{capacity(d)} kWp"),
                   ("Inverter capacity (AC)", f"{d.get('inverter_kw')} kW"),
                   ("Module make, model and wattage",
                    f"{d.get('module_make')}, {d.get('almm_model')}, {d.get('module_wp')} Wp"),
                   ("No. of modules", d.get("module_count")),
                   ("Inverter make, model and serial no.",
                    f"{d.get('inverter_make')}, {d.get('inverter_serial')}"),
                   ("Generation meter serial no.", d.get("meter_serial")),
                   ("Date of installation", _date(d.get("install_date"))),
                   ("Location (GPS)", f"{d.get('lat')}, {d.get('lng')}"),
                   ("Installer", V["name"])])}
<table><tr><th colspan="4">PV module serial numbers</th></tr>
{"".join("<tr>" + "".join(f'<td>{e(x)}</td>' for x in sn[i:i + 4]) + "</tr>"
         for i in range(0, len(sn), 4))}</table>
<p>Certified that the above rooftop solar system has been installed as per the approved
capacity and the applicable technical standards, and is ready for inspection and
commissioning.</p>
<div class="sigs">{_sig("Consumer", "consumer", sig)}
{_sig(f"Installer &middot; {e(V['name'])}", "vendor", sig)}</div>"""
    return _page("Annexure-I", "Installation report of renewable energy generating system", body, d)


def t_dcr_decl(c, d, sig, V):
    sn = serials(d)
    body = f"""<p>Consumer: <b>{e(c['aadhaar_name'])}</b>, consumer number {e(c['consumer_no'])},
PM Surya Ghar application no. {e(d.get('pmsg_app_no'))}</p>
<p>1. We confirm that the following PV modules, made with domestically manufactured cells, have
been supplied and installed at the above site.</p>
{_rows([("PV module capacity", f"{d.get('module_wp')} W"), ("Number of PV modules", len(sn)),
        ("Sr. no. of PV modules", ", ".join(sn)), ("PV module make", d.get("module_make")),
        ("Cell manufacturer's name", d.get("cell_maker")),
        ("Cell GST invoice no.", d.get("cell_invoice")),
        ("DCR certificate no. (NISE portal)", d.get("dcr_cert_no"))])}
<p>2. The above undertaking is based on the certificate issued by the PV module
manufacturer/supplier while supplying the above order.</p>
<p>3. I, {e(V['signatory'])}, on behalf of M/s {e(V['name'])}, further declare that the
information given above is true and correct and nothing has been concealed therein. If anything
is found incorrect at any stage, the due Central Financial Assistance (CFA) may be withheld and
appropriate action may be taken against me and my company for wrong declaration. Supporting
documents and proof of the above will be provided as and when requested by MNRE.</p>
<div class="sigs">{_sig(f"{e(V['signatory'])}, for {e(V['name'])}", "vendor", sig)}
<div class="sig"></div></div>"""
    return _page("Declaration of domestic content (DCR)",
                 "Undertaking / self-declaration for domestic content requirement fulfilment",
                 body, d)


def t_net_agreement(c, d, sig, V):
    body = f"""<p>This agreement is entered into on {e(_date(d.get('install_date')))} between
<b>{e(c['aadhaar_name'])}</b>, consumer number {e(c['consumer_no'])}, residing at
{e(c['address'])}, {e(c['pin'])} (the eligible consumer), and the Maharashtra State Electricity
Distribution Co. Ltd. (the distribution licensee), for net metering of the consumer's rooftop
solar system.</p>
{_rows([("Tariff category", d.get("tariff")), ("Solar system capacity (DC)", f"{capacity(d)} kWp"),
        ("Inverter capacity (AC)", f"{d.get('inverter_kw')} kW"),
        ("Generation meter serial no.", d.get("meter_serial")), ("Installer", V["name"])])}
<ol><li>The consumer shall keep the system in line with the technical and safety standards
notified by the Central Electricity Authority and the distribution licensee.</li>
<li>The consumer shall provide the distribution licensee access to the metering and the system
for inspection and testing.</li>
<li>Energy exported and imported shall be measured by the net meter and billed as per the
applicable regulations of the Maharashtra Electricity Regulatory Commission.</li>
<li>The consumer shall not make changes to the system capacity without prior approval.</li>
<li>Either party may terminate this agreement as provided in the applicable regulations.</li></ol>
<div class="sigs">{_sig("Eligible consumer", "consumer", sig)}
<div class="sig"><div class="ln"></div><div>For the distribution licensee</div></div></div>"""
    return _page("Net metering connection agreement", "Rooftop solar system", body, d)


TEMPLATES = {"agreement": t_agreement, "wcr": t_wcr, "annexure1": t_annexure1,
             "dcr_decl": t_dcr_decl, "net_agreement": t_net_agreement}


def unsigned_html(key, cid):
    c, d = data(cid)
    return TEMPLATES[key](c, d, {}, vendor())


def doc_hash(key, cid):
    return hashlib.sha256(unsigned_html(key, cid).encode()).hexdigest()


# ------------------------------- signatures -------------------------------
def signature(role, cid=None):
    if role == "vendor":
        return db.one("SELECT * FROM signatures WHERE role='vendor' ORDER BY id DESC")
    return db.one("SELECT * FROM signatures WHERE role='consumer' AND customer_id=? "
                  "ORDER BY id DESC", (cid,))


def png_from_data_url(url):
    """Validate a drawn signature: a real PNG with enough ink to be a signature."""
    m = re.match(r"data:image/png;base64,([A-Za-z0-9+/=]+)$", url or "")
    if not m:
        raise ValueError("signature must be a PNG image")
    raw = base64.b64decode(m.group(1))
    if len(raw) > 400_000:
        raise ValueError("signature image too large")
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    ink = sum(1 for px in im.getdata() if px[3] > 40)
    if ink < 150:
        raise ValueError("the signature is empty; draw it in the box")
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def save_signature(role, png, name, cid=None, token=None):
    who = cid or "vendor"
    path = DOCS / who / f"signature_{role}_{datetime.now():%Y%m%d%H%M%S}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    vault.write(path, png)
    db.ex("""INSERT INTO signatures(customer_id,role,name,path,created_at,request_token)
             VALUES(?,?,?,?,?,?)""", (cid, role, name, str(path), db.now(), token))


def _sig_img(row):
    from pathlib import Path
    return "data:image/png;base64," + base64.b64encode(vault.read(Path(row["path"]))).decode()


def approval(cid, key):
    """The approval covering this document's current content, if any."""
    return db.one("SELECT * FROM approvals WHERE customer_id=? AND doc_key=? AND doc_hash=? "
                  "ORDER BY id DESC", (cid, key, doc_hash(key, cid)))


def signed_html(key, cid):
    c, d = data(cid)
    sig = {}
    roles = SPEC[key][3]
    if "consumer" in roles:
        a, s = approval(cid, key), signature("consumer", cid)
        if not (a and s):
            raise PermissionError("the customer has not approved this version of the document")
        sig["consumer"] = {"img": _sig_img(s), "caption": f"e-signed by {s['name']} on "
                           f"{a['ts'][:10]} with consent, approval #{a['id']}"}
    if "vendor" in roles:
        s = signature("vendor")
        if not s:
            raise PermissionError("the company signature has not been added")
        sig["vendor"] = {"img": _sig_img(s), "caption": f"signed for {vendor()['name']}"}
    return TEMPLATES[key](c, d, sig, vendor())


# ------------------------------- status -------------------------------
def datasheet_key(d):
    slug = lambda s: re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return f"{slug(d.get('module_make'))}__{slug(d.get('inverter_make'))}"


def status(cid):
    c, d = data(cid)
    blocked = any(sev == "bad" for sev, _ in checks(cid, d))
    vsig = bool(signature("vendor"))
    out = []
    for key, slot, title, roles, need in DOCS_SPEC:
        miss = [LABEL.get(k, "site photo with GPS" if k == "lat" else k) for k in need if not d.get(k)]
        st, note = "ready", ""
        if miss:
            st, note = "missing", "Missing: " + ", ".join(miss)
        elif key == "datasheet" and not (LIBRARY / f"{datasheet_key(d)}.pdf").exists():
            st, note = "missing", f"Upload the datasheet for {d['module_make']} + {d['inverter_make']} once"
        elif key in TEMPLATES and blocked:
            st, note = "blocked", "Fix the checks above first"
        elif "consumer" in roles and not approval(cid, key):
            had = db.one("SELECT 1 FROM approvals WHERE customer_id=? AND doc_key=?", (cid, key))
            st = "changed" if had else "needs_approval"
            note = ("Changed after the customer approved it; needs their approval again" if had
                    else "Needs the customer's e-sign")
        elif "vendor" in roles and not vsig:
            st, note = "needs_vendor_sig", "Add the company signature once"
        out.append({"key": key, "slot": slot, "title": title, "signers": list(roles),
                    "state": st, "note": note})
    return out


# ------------------------------- files -------------------------------
def fit(pdf, limit_kb=MAX_UPLOAD_KB):
    """Return the PDF as is if it fits; otherwise re-render its pages as JPEG until it does."""
    if len(pdf) <= limit_kb * 1024:
        return pdf
    src = fitz.open(stream=pdf, filetype="pdf")
    for dpi, q in ((110, 70), (90, 60), (72, 50), (60, 40), (48, 35)):
        out = fitz.open()
        for page in src:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=q, optimize=True)
            pg = out.new_page(width=page.rect.width, height=page.rect.height)
            pg.insert_image(pg.rect, stream=buf.getvalue())
        blob = out.tobytes(garbage=4, deflate=True)
        if len(blob) <= limit_kb * 1024:
            return blob
    raise ValueError(f"could not bring the file under {limit_kb} KB")


def gps(img):
    """Latitude and longitude from a photo's EXIF, or None."""
    g = img.getexif().get_ifd(ExifTags.IFD.GPSInfo)
    if not g or 2 not in g or 4 not in g:
        return None
    deg = lambda v, ref: (-1 if ref in ("S", "W") else 1) * (
        float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600)
    return round(deg(g[2], g.get(1, "N")), 6), round(deg(g[4], g.get(3, "E")), 6)


def save_photo(cid, raw, user):
    img = Image.open(io.BytesIO(raw))
    loc = gps(img)
    if not loc:
        raise ValueError("this photo has no GPS location. Take it with location turned on in "
                         "the phone camera, and send the original file, not a WhatsApp copy")
    taken = img.getexif().get(306) or ""  # DateTime
    img = img.convert("RGB")
    img.thumbnail((1400, 1400))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=72, optimize=True)
    path = DOCS / cid / "site_photo.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    vault.write(path, buf.getvalue())
    mark(cid, user, lat=f"{loc[0]}", lng=f"{loc[1]}", photo_taken=str(taken))
    invalidate(cid)
    return loc


def save_datasheet(cid, raw):
    if not raw.startswith(b"%PDF"):
        raise ValueError("the datasheet must be a PDF")
    c, d = data(cid)
    if not (d.get("module_make") and d.get("inverter_make")):
        raise ValueError("enter the module make and inverter make first")
    blob = fit(raw)
    vault.write(LIBRARY / f"{datasheet_key(d)}.pdf", blob)
    invalidate(cid)
    return len(blob)


def _photo_html(c, d, jpeg):
    src = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    return _page("Photo of installed PV system", "with geo co-ordinates", f"""
<img src="{src}" style="width:100%;max-height:200mm;object-fit:contain;border:1px solid #444">
{_rows([("Consumer", f"{c['aadhaar_name']}, consumer no. {c['consumer_no']}"),
        ("Location", f"Latitude {d.get('lat')}, Longitude {d.get('lng')}"),
        ("Photo taken", d.get("photo_taken")), ("Installed capacity", f"{capacity(d)} kWp")])}""", d)


def path_for(cid, key):
    slot = SPEC[key][1]
    return DOCS / cid / "closeout" / f"{slot or 0}_{key}.pdf"


async def build(cid, user):
    """Generate every document that is ready. Returns one row per document."""
    c, d = data(cid)
    st = {s["key"]: s for s in status(cid)}
    ready = [k for k, s in st.items() if s["state"] == "ready"]
    htmls = {k: signed_html(k, cid) for k in ready if k in TEMPLATES}
    if "site_photo" in ready:
        htmls["site_photo"] = _photo_html(c, d, vault.read(DOCS / cid / "site_photo.jpg"))
    blobs = {}
    if htmls:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page()
            for k, h in htmls.items():
                await pg.set_content(h, wait_until="load")
                blobs[k] = await pg.pdf(format="A4", print_background=True)
            await b.close()
    if "datasheet" in ready:
        blobs["datasheet"] = vault.read(LIBRARY / f"{datasheet_key(d)}.pdf")
    out = []
    for k, s in st.items():
        row = {**s, "bytes": None}
        if k in blobs:
            pdf = fit(blobs[k])
            p = path_for(cid, k)
            p.parent.mkdir(parents=True, exist_ok=True)
            vault.write(p, pdf)
            db.ex("DELETE FROM documents WHERE customer_id=? AND kind=?", (cid, "co_" + k))
            db.ex("""INSERT INTO documents(customer_id,kind,filename,path,bytes,uploaded_at)
                     VALUES(?,?,?,?,?,?)""", (cid, "co_" + k, p.name, str(p), len(pdf), db.now()))
            row["bytes"] = len(pdf)
        out.append(row)
    db.audit(user["username"], user["role"], "Generated close-out documents", cid,
             f"{len(blobs)} of {len(st)} ready, largest "
             f"{max((len(v) for v in blobs.values()), default=0) // 1024} KB")
    return out


def demo_assets(cid="SS-2042"):
    """Sandbox only: a geotagged rooftop photo and a manufacturer datasheet for one seeded
    customer, so the close-out screen can be walked end to end."""
    if not db.one("SELECT 1 FROM closeout WHERE customer_id=?", (cid,)):
        return
    c, d = data(cid)
    if not d.get("lat"):
        save_photo(cid, _demo_photo(19.953214, 73.837105), "system")
    if not (LIBRARY / f"{datasheet_key(d)}.pdf").exists():
        save_datasheet(cid, _demo_datasheet(d))


def _demo_photo(lat, lng, with_gps=True):
    from PIL import ImageDraw
    im = Image.new("RGB", (1280, 960), "#9CC3E6")
    dr = ImageDraw.Draw(im)
    dr.polygon([(0, 520), (1280, 430), (1280, 960), (0, 960)], fill="#A0694B")
    for r in range(3):
        for k in range(3):
            x, y = 230 + k * 280, 470 + r * 150 - k * 18
            dr.rectangle([x, y, x + 250, y + 132], fill="#1D2F55", outline="#C9D3E0", width=4)
    dms = lambda v: (float(int(v)), float(int(v * 60 % 60)), round(v * 3600 % 60, 2))
    exif = Image.Exif()
    exif[306] = "2026:10:21 15:42:10"
    if with_gps:
        exif[ExifTags.IFD.GPSInfo] = {1: "N", 2: dms(lat), 3: "E", 4: dms(lng)}
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, exif=exif)
    return buf.getvalue()


def _demo_datasheet(d):
    """A deliberately heavy two-page PDF, like a real manufacturer brochure."""
    import os
    doc = fitz.open()
    for i in range(2):
        pg = doc.new_page()
        pg.insert_text((50, 60), f"{d['module_make']} / {d['inverter_make']} datasheet "
                                 f"(sandbox) page {i + 1}", fontsize=13)
        noise = Image.frombytes("RGB", (900, 600), os.urandom(900 * 600 * 3))
        buf = io.BytesIO()
        noise.save(buf, "PNG")
        pg.insert_image(fitz.Rect(50, 90, 545, 420), stream=buf.getvalue())
    return doc.tobytes()


def built(cid):
    """Documents already generated, by key, with their size."""
    return {r["kind"][3:]: r["bytes"] for r in
            db.q("SELECT kind, bytes FROM documents WHERE customer_id=? AND kind LIKE 'co_%'", (cid,))}
