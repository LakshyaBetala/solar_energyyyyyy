"""Milestone 2: after registration, everything the installer files and uploads.

Five filing steps, each with its own readiness check, history and receipt:

  sfr           the site feasibility report on PM Surya Ghar
  installation  the five installation screens, in order (installation:1 ... installation:5)
  dcr           the NISE DCR certificate, with the panel serial numbers
  msedcl        the six MSEDCL documents (PDF, 300 KB each)
  loan          the Jan Samarth loan application, when the customer takes a loan

Rules that hold everywhere in this module:
- Solara prepares and checks; a person presses every Submit. "filed" is only ever written after a
  person says they pressed it (or, for MSEDCL, after the MSEDCL page itself showed the documents).
- Nothing is reported as done without that evidence. A failure is recorded and can be retried.
- Passwords, OTPs and Aadhaar numbers are never held here.
"""
import io, re
from datetime import datetime, date
from . import db, closeout, vault
from .config import DOCS, vendor

STEPS = [("sfr", "Site feasibility report"), ("installation", "Installation, 5 screens"),
         ("dcr", "DCR certificate"), ("msedcl", "MSEDCL documents"), ("loan", "Jan Samarth loan")]
SCREENS = {1: "Location and vendor", 2: "Modules and serial numbers", 3: "Inverter and meter",
           4: "Certificate and invoice", 5: "Protection and photos"}
# Only screen 1's labels have been seen on the real portal (tests/real_labels.py). The grouping of
# the rest follows the fields the client's documents ask for and must be checked on the portal.
SCREENS_VERIFIED = {1}
# every filing that gets an acknowledgement: the two K1 filings and the five K2 steps
RECEIPT_STEPS = ("registration", "sfr", "installation", "dcr", "msedcl", "loan", "agreement")
RECEIPT_LABEL = {"registration": "Registration (application)", "sfr": "Site feasibility report",
                 "installation": "Installation", "dcr": "DCR certificate", "msedcl": "MSEDCL documents",
                 "loan": "Jan Samarth loan", "agreement": "Agreement upload"}
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_\-]{3,39}$")
SERIAL = re.compile(r"^[A-Z0-9][A-Z0-9\-/.]{5,31}$")
MOBILE = re.compile(r"^[6-9]\d{9}$")
INDIA = (6.0, 37.5, 68.0, 97.5)  # lat min/max, lng min/max
# documents the installation team and the office add per customer (K1's are in main.DOC_KINDS)
DOC_KINDS = {"dcr_cert": "DCR certificate for the panels", "invoice": "Invoice / e-way bill",
             "serial_sheet": "Panel serial numbers (sheet)", "serial_label": "Serial label photo",
             "preinstall": "Photo before installation", "install_photo": "Installation photo",
             "loan_approval": "Jan Samarth approval letter"}
MULTI = {"serial_label", "preinstall", "install_photo"}  # kinds that can hold several files


# ------------------------------- history -------------------------------
def track(cid, step, status, user, ref=None, note=None):
    db.ex("INSERT INTO filings(customer_id,step,status,ref_no,note,by,ts) VALUES(?,?,?,?,?,?,?)",
          (cid, step, status, ref, (note or "")[:300], user, db.now()))


def history(cid):
    return db.q("SELECT id,step,status,ref_no,note,by,ts FROM filings WHERE customer_id=? ORDER BY id", (cid,))


def latest(cid, step):
    return db.one("SELECT * FROM filings WHERE customer_id=? AND step=? AND status NOT IN "
                  "('generated','note') ORDER BY id DESC", (cid, step))


# ------------------------------- helpers -------------------------------
def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _issue(kind, field, message):
    return {"kind": kind, "field": field, "message": message}


def _need(d, c, keys):
    out = []
    for k in keys:
        v = d.get(k) if k in closeout.LABEL or k in d else c.get(k)
        if v in (None, ""):
            out.append(_issue("missing", closeout.LABEL.get(k, k), f"{closeout.LABEL.get(k, k)} is not on file"))
    return out


def in_india(lat, lng):
    return INDIA[0] <= lat <= INDIA[1] and INDIA[2] <= lng <= INDIA[3]


def _date_ok(v, field, out, future_ok=False):
    if not v:
        return
    try:
        dt = date.fromisoformat(str(v)[:10])
    except ValueError:
        out.append(_issue("invalid", field, f"{field} must be a date (YYYY-MM-DD)"))
        return
    if dt > date.today() and not future_ok:
        out.append(_issue("invalid", field, f"{field} is in the future"))


def has_doc(cid, kind):
    return bool(db.one("SELECT 1 FROM documents WHERE customer_id=? AND kind=?", (cid, kind)))


# ------------------------------- serial numbers -------------------------------
def sync_registry(cid, d, user):
    """Keep the serial register in step with what is saved. First holder keeps a serial."""
    db.ex("DELETE FROM serials WHERE customer_id=?", (cid,))
    for s in closeout.serials(d):
        db.ex("INSERT OR IGNORE INTO serials(serial,customer_id,source,added_by,added_at) VALUES(?,?,?,?,?)",
              (s, cid, "entered", user, db.now()))


def parse_serials(filename, blob):
    """Serial numbers from an Excel sheet (column A; a header row is skipped), a CSV or a text file.
    Returns (serials, rejected) where rejected is [(value, reason)]. Nothing is guessed."""
    name = (filename or "").lower()
    if len(blob) > 2 * 1024 * 1024:
        raise ValueError("that file is over 2 MB; a serial-number sheet is tiny. Send the right file")
    cells = []
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        try:
            ws = load_workbook(io.BytesIO(blob), read_only=True, data_only=True).worksheets[0]
        except Exception:
            raise ValueError("the Excel file could not be opened; save it as .xlsx and try again")
        rows = [r[0] for r in ws.iter_rows(max_col=1, values_only=True)]
        cells = ["" if v is None else str(v).strip() for v in rows]
        if cells and re.search(r"serial|panel|module|number|sr\.?\s*no", cells[0], re.I) and " " in cells[0]:
            cells = cells[1:]
    elif name.endswith((".csv", ".txt", ".tsv")) or not name:
        try:
            text = blob.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = blob.decode("latin-1")
        cells = [p.strip() for p in re.split(r"[\r\n,;\t]+", text)]
        if cells and re.search(r"serial", cells[0], re.I):
            cells = cells[1:]
    else:
        raise ValueError("send the serial numbers as an Excel (.xlsx), CSV or text file")
    good, bad = [], []
    for c in cells:
        c = re.sub(r"\s+", "", c).upper()
        if not c:
            continue
        (good if SERIAL.match(c) else bad).append(c if SERIAL.match(c) else (c, "not a serial number: 6-32 letters, digits, - / ."))
    return good, bad


def set_serials(cid, serials, user, source="entered"):
    """Replace this customer's serial numbers, all or nothing. Refuses a list with an invalid
    serial, a serial listed twice, or a serial another customer already holds."""
    c, d = closeout.data(cid)
    serials = [re.sub(r"\s+", "", s).upper() for s in serials if str(s).strip()]
    if not serials:
        raise ValueError("no serial numbers found")
    bad = [s for s in serials if not SERIAL.match(s)]
    if bad:
        raise ValueError(f"{len(bad)} value(s) are not serial numbers, e.g. {bad[0]}")
    dup = sorted({s for s in serials if serials.count(s) > 1})
    if dup:
        raise ValueError(f"serial number listed twice: {', '.join(dup[:5])}. Nothing was saved")
    other = db.q(f"SELECT serial, customer_id FROM serials WHERE customer_id<>? AND serial IN "
                 f"({','.join('?' * len(serials))})", (cid, *serials))
    if other:
        raise ValueError(f"serial {other[0]['serial']} is already on {other[0]['customer_id']}; "
                         "MNRE rejects repeated serial numbers. Nothing was saved")
    closeout.save(cid, {"module_serials": "\n".join(serials)}, user)
    db.ex("UPDATE serials SET source=? WHERE customer_id=?", (source, cid))
    n = _num(d.get("module_count"))
    db.audit(user, "user", "Serial numbers saved", cid, f"{len(serials)} from {source}"
             + (f"; the plant has {int(n)} modules" if n and int(n) != len(serials) else ""))
    return {"count": len(serials), "expected": int(n) if n else None,
            "matches": bool(n) and int(n) == len(serials)}


def add_serials(cid, new, user, source="photo, confirmed"):
    """Add confirmed serials to what is already saved. The same all-or-nothing rules apply."""
    c, d = closeout.data(cid)
    return set_serials(cid, closeout.serials(d) + [re.sub(r"\s+", "", str(s)).upper() for s in new if str(s).strip()],
                       user, source)


async def read_serial_photos(cid, user, reader=None):
    """Suggest serial numbers from the customer's serial-label photos, each with checks, for a
    person to confirm one by one. Nothing is saved here. Only photos of kind serial_label are
    ever sent to the model; identity documents never are. `reader` is for tests."""
    from pathlib import Path
    from PIL import Image
    from . import extract
    st = extract.llm_status()
    if reader is None:
        if not st["enabled"]:
            raise ValueError("reading photos needs the AI key (ANTHROPIC_API_KEY in .env). "
                             "Type the serial numbers or upload the sheet instead")
        reader = extract.llm_read
    docs = db.q("SELECT id, filename, path FROM documents WHERE customer_id=? AND kind='serial_label' ORDER BY id", (cid,))
    if not docs:
        raise ValueError("no serial label photos on file yet; add them first")
    c, d = closeout.data(cid)
    held, seen, out = set(closeout.serials(d)), set(), []
    for doc in docs:
        row = {"doc_id": doc["id"], "filename": doc["filename"], "serials": []}
        out.append(row)
        try:
            im = Image.open(io.BytesIO(vault.read(Path(doc["path"])))).convert("RGB")
        except Exception:
            row["error"] = "this photo could not be opened"
            continue
        try:
            got = await reader("serial_label", st, image=im)
        except Exception as ex:
            row["error"] = f"the model could not read this photo ({type(ex).__name__})"
            continue
        v = (got or {}).get("serial_numbers")
        val, sure = (v.get("value"), bool(v.get("sure"))) if isinstance(v, dict) else (v, False)
        for raw in (val if isinstance(val, list) else re.split(r"[\s,;]+", str(val or ""))):
            s = re.sub(r"\s+", "", str(raw)).upper()
            if not s:
                continue
            notes = []
            if not SERIAL.match(s):
                notes.append("does not look like a serial number")
            if s in held:
                notes.append("already saved for this customer")
            if s in seen:
                notes.append("read twice")
            other = db.one("SELECT customer_id FROM serials WHERE serial=? AND customer_id<>?", (s, cid))
            if other:
                notes.append(f"already on {other['customer_id']}")
            if not sure:
                notes.append("the model was not sure; check it on the photo")
            seen.add(s)
            row["serials"].append({"value": s, "ok": not notes, "notes": notes})
    db.audit(user, "user", "Serial label photos read", cid, f"{len(docs)} photo(s), {sum(len(r['serials']) for r in out)} suggested")
    n = _num(d.get("module_count"))
    return {"photos": out, "expected": int(n) if n else None, "saved": len(held)}


def serials_xlsx(cid):
    """The sheet the DCR portal accepts: serial numbers in column A from row 2."""
    from openpyxl import Workbook
    c, d = closeout.data(cid)
    wb = Workbook()
    ws = wb.active
    ws.title = "Panels"
    ws["A1"] = "Panel Serial Number"
    for i, s in enumerate(closeout.serials(d), start=2):
        ws.cell(row=i, column=1, value=s)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------- the checks, step by step -------------------------------
def registered(cid):
    c, d = closeout.data(cid)
    return bool(c["application_no"])


def sfr_issues(cid):
    c, d = closeout.data(cid)
    out = []
    if not c["application_no"]:
        out.append(_issue("missing", "PM Surya Ghar application", "register the customer on PM Surya Ghar first"))
    out += _need(d, c, ("roof_free_area", "roof_type", "roof_load_ok", "sfr_visitor", "sfr_visitor_phone", "sfr_date"))
    out += [] if c["kw"] else [_issue("missing", "proposed capacity (kW)", "proposed capacity is not on file")]
    area = _num(d.get("roof_free_area"))
    if d.get("roof_free_area") and (area is None or area <= 0):
        out.append(_issue("invalid", closeout.LABEL["roof_free_area"], "enter the area as a number of square metres"))
    elif area and c["kw"] and area < c["kw"] * 8:
        out.append(_issue("warning", closeout.LABEL["roof_free_area"],
                          f"{area:g} m2 is small for {c['kw']:g} kW (about 10 m2 per kW is usual)"))
    if d.get("roof_load_ok") and d["roof_load_ok"].lower() != "yes":
        out.append(_issue("invalid", closeout.LABEL["roof_load_ok"], "the roof load must be confirmed before filing"))
    perm = _num(d.get("permissible_kw"))
    if d.get("permissible_kw") and perm is None:
        out.append(_issue("invalid", closeout.LABEL["permissible_kw"], "enter the capacity in kW"))
    elif perm is not None and c["kw"] and perm < c["kw"]:
        out.append(_issue("invalid", closeout.LABEL["permissible_kw"],
                          f"the site allows {perm:g} kW but {c['kw']:g} kW is proposed"))
    if d.get("sfr_visitor_phone") and not MOBILE.match(re.sub(r"\D", "", d["sfr_visitor_phone"])[-10:]):
        out.append(_issue("invalid", closeout.LABEL["sfr_visitor_phone"], "the contact number must be 10 digits starting 6-9"))
    _date_ok(d.get("sfr_date"), closeout.LABEL["sfr_date"], out)
    if not d.get("rts_cost"):
        out.append(_issue("missing", "quotation amount", "the installation cost (quotation amount) is not on file"))
    return out


def screen_issues(cid, n):
    c, d = closeout.data(cid)
    out = []
    if n == 1:
        if not vendor()["name"]:
            out.append(_issue("missing", "vendor name", "set SOLARA_VENDOR_NAME"))
        lat, lng = _num(d.get("lat")), _num(d.get("lng"))
        if lat is None or lng is None:
            out.append(_issue("missing", "latitude / longitude", "add the geotagged site photo; its coordinates are used"))
        elif not in_india(lat, lng):
            out.append(_issue("invalid", "latitude / longitude", f"{lat}, {lng} is outside India; check the photo's location"))
    elif n == 2:
        out += _need(d, c, ("module_make", "almm_model", "module_wp", "module_count", "module_serials"))
        cnt, wp, sn = _num(d.get("module_count")), _num(d.get("module_wp")), closeout.serials(d)
        if d.get("module_count") and (cnt is None or cnt < 1 or cnt != int(cnt)):
            out.append(_issue("invalid", closeout.LABEL["module_count"], "enter a whole number of modules"))
        if sn and cnt and len(sn) != int(cnt):
            out.append(_issue("invalid", "serial numbers", f"{int(cnt)} modules but {len(sn)} serial numbers"))
        bad = [s for s in sn if not SERIAL.match(s.upper())]
        if bad:
            out.append(_issue("invalid", "serial numbers", f"{len(bad)} are not valid serial numbers, e.g. {bad[0]}"))
        dup = sorted({s for s in sn if sn.count(s) > 1})
        if dup:
            out.append(_issue("invalid", "serial numbers", "listed twice: " + ", ".join(dup[:3])))
        clash = db.q("SELECT serial, customer_id FROM serials WHERE customer_id<>?", (cid,)) if sn else []
        clash = [r for r in clash if r["serial"] in set(sn)]
        if clash:
            out.append(_issue("invalid", "serial numbers", f"{clash[0]['serial']} is already on {clash[0]['customer_id']}"))
        if cnt and wp and c["kw"]:
            kwp = cnt * wp / 1000
            if abs(kwp - c["kw"]) > 0.1 * c["kw"]:
                out.append(_issue("warning", "capacity", f"{kwp:g} kWp installed against {c['kw']:g} kW approved"))
    elif n == 3:
        out += _need(d, c, ("inverter_make", "inverter_kw", "inverter_serial", "inverter_year", "meter_serial"))
        if d.get("inverter_kw") and _num(d["inverter_kw"]) is None:
            out.append(_issue("invalid", closeout.LABEL["inverter_kw"], "enter the rating as a number"))
    elif n == 4:
        out += _need(d, c, ("dcr_cert_no", "invoice_no", "cell_maker", "cell_invoice", "install_date"))
        _date_ok(d.get("install_date"), closeout.LABEL["install_date"], out)
        if not has_doc(cid, "dcr_cert"):
            out.append(_issue("missing", "DCR certificate", "upload the DCR certificate for the panels"))
    elif n == 5:
        out += _need(d, c, ("earthing_count", "earth_ohm", "lightning_arrester", "protection_checks"))
        oh = _num(d.get("earth_ohm"))
        if d.get("earth_ohm") and (oh is None or oh >= 5):
            out.append(_issue("invalid", closeout.LABEL["earth_ohm"], "earth resistance must be a number below 5 ohm"))
        if d.get("protection_checks") and d["protection_checks"] != "Yes":
            out.append(_issue("invalid", closeout.LABEL["protection_checks"], "all earthing and protection checks must be done"))
        if not (DOCS / cid / "site_photo.jpg").exists():
            out.append(_issue("missing", "site photo", "add the geotagged photo of the installed system"))
    return out


def installation_issues(cid):
    return [i for n in SCREENS for i in screen_issues(cid, n)]


def dcr_issues(cid):
    c, d = closeout.data(cid)
    out = []
    if not c["application_no"]:
        out.append(_issue("missing", "consumer application number", "register the customer first"))
    for lbl, v in (("customer name", c["aadhaar_name"] or c["name"]), ("customer address", c["address"]),
                   ("PIN code", c["pin"]), ("customer mobile", d.get("mobile"))):
        if not v:
            out.append(_issue("missing", lbl, f"{lbl} is not on file"))
    out += _need(d, c, ("invoice_no", "module_serials", "module_count"))
    sn = closeout.serials(d)
    cnt = _num(d.get("module_count"))
    if sn and cnt and len(sn) != int(cnt):
        out.append(_issue("invalid", "serial numbers", f"{int(cnt)} modules but {len(sn)} serial numbers"))
    out += [i for i in screen_issues(cid, 2) if i["field"] == "serial numbers" and i not in out]
    if not has_doc(cid, "dcr_cert"):
        out.append(_issue("missing", "DCR certificate", "upload the DCR certificate for the panels"))
    if not d.get("dcr_credit"):
        out.append(_issue("missing", closeout.LABEL["dcr_credit"], "say whether the panels are credited to this dealer"))
    return out


def loan_wanted(cid):
    return (closeout.data(cid)[1].get("loan_needed") or "").lower() == "yes"


def loan_issues(cid):
    c, d = closeout.data(cid)
    out = []
    for lbl, v in (("customer name", c["aadhaar_name"] or c["name"]), ("mobile", d.get("mobile")),
                   ("address", c["address"]), ("PIN code", c["pin"]), ("district", d.get("district")),
                   ("bank", d.get("loan_bank")), ("branch", d.get("loan_branch")),
                   ("loan amount", d.get("loan_amount"))):
        if not v:
            out.append(_issue("missing", lbl, f"{lbl} is not on file"))
    amt, cost = _num(d.get("loan_amount")), _num(d.get("rts_cost"))
    if d.get("loan_amount") and (amt is None or amt <= 0):
        out.append(_issue("invalid", "loan amount", "enter the amount in rupees"))
    elif amt and cost and amt > cost:
        out.append(_issue("invalid", "loan amount", f"Rs {amt:,.0f} is more than the project cost Rs {cost:,.0f}"))
    if d.get("mobile") and not MOBILE.match(re.sub(r"\D", "", d["mobile"])[-10:]):
        out.append(_issue("invalid", "mobile", "the mobile number must be 10 digits starting 6-9"))
    docs = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    for kind, lbl in (("bill", "electricity bill"), ("aadhaar", "Aadhaar (the customer enters their own on the portal)"),
                      ("passbook", "bank passbook or cheque page")):
        if kind not in docs:
            out.append(_issue("missing", lbl, f"{lbl} is not on file"))
    return out


def loan_pack(cid):
    """What the Jan Samarth form needs, ready for the person to copy or the co-pilot to fill. The
    customer's Aadhaar OTP and any bank login are the customer's own; Solara never holds them."""
    c, d = closeout.data(cid)
    return {"issues": loan_issues(cid), "wanted": loan_wanted(cid),
            "values": {k: v for k, v in {
                "name": c["aadhaar_name"] or c["name"], "mobile": d.get("mobile"), "email": d.get("email"),
                "address": c["address"], "pin": c["pin"], "district": d.get("district"),
                "loan_amount": d.get("loan_amount"), "loan_bank": d.get("loan_bank"),
                "loan_branch": d.get("loan_branch"), "project_cost": d.get("rts_cost"),
                "capacity": f"{c['kw']:g}" if c["kw"] else None}.items() if v},
            "documents": [r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=? AND kind IN "
                                                   "('bill','aadhaar','passbook','loan_approval')", (cid,))]}


def msedcl_state(cid):
    """Evidence-based: 'filed' only when the MSEDCL page itself showed the documents."""
    c, d = closeout.data(cid)
    slots = [s for s in closeout.status(cid) if s["slot"]]
    made = closeout.built(cid)
    up = set(filter(None, (d.get("msedcl_slots_uploaded") or "").split(",")))
    rej = set(filter(None, (d.get("msedcl_slots_rejected") or "").split(",")))
    rows = []
    for s in slots:
        bad = []
        if s["key"] in made:
            try:
                blob = vault.read(closeout.path_for(cid, s["key"]))
                bad = closeout.validate_pdf(blob)
            except OSError:
                bad = ["the stored file is missing"]
        rows.append({"key": s["key"], "slot": s["slot"], "title": s["title"], "state": s["state"],
                     "note": s["note"], "bytes": made.get(s["key"]), "problems": bad,
                     "on_portal": s["key"] in up or bool(d.get("msedcl_uploaded")),
                     "rejected": s["key"] in rej})
    return {"documents": rows, "uploaded": bool(d.get("msedcl_uploaded")),
            "uploaded_at": d.get("msedcl_uploaded_at"), "rejected": sorted(rej)}


def msedcl_issues(cid):
    out = []
    for r in msedcl_state(cid)["documents"]:
        if r["state"] in ("missing", "blocked", "needs_approval", "changed", "needs_vendor_sig"):
            out.append(_issue("missing", r["title"], r["note"] or r["state"]))
        elif r["problems"]:
            out.append(_issue("invalid", r["title"], "; ".join(r["problems"])))
    return out


ISSUES = {"sfr": sfr_issues, "installation": installation_issues, "dcr": dcr_issues,
          "msedcl": msedcl_issues, "loan": loan_issues}
BLOCKING = ("missing", "invalid")


def blocking(issues):
    return [i for i in issues if i["kind"] in BLOCKING]


# ------------------------------- progress -------------------------------
def _minutes(a, b):
    if not (a and b):
        return None
    return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60, 1)


def _step(cid, key, label):
    c, d = closeout.data(cid)
    issues = ISSUES[key](cid)
    block = blocking(issues)
    evs = [h for h in history(cid) if h["step"] == key or h["step"].startswith(key + ":")]
    evs = [h for h in evs if h["status"] not in ("generated", "note")]
    last = latest(cid, key)
    ref, receipt = None, None
    parts = None
    if key == "installation":
        parts = []
        for n, t in SCREENS.items():
            lt = latest(cid, f"installation:{n}")
            parts.append({"n": n, "title": t, "verified_labels": n in SCREENS_VERIFIED,
                          "filed": bool(lt and lt["status"] == "filed"),
                          "failed": bool(lt and lt["status"] == "failed"),
                          "issues": screen_issues(cid, n), "ref": lt and lt["ref_no"]})
        done = all(p["filed"] for p in parts)
        failed = any(p["failed"] for p in parts)
    elif key == "msedcl":
        done = bool(d.get("msedcl_uploaded"))
        failed = bool(d.get("msedcl_slots_rejected"))
    else:
        done = bool(last and last["status"] in ("filed", "receipt", "sanctioned"))
        failed = bool(last and last["status"] in ("failed", "rejected"))
    rc = db.one("SELECT ref_no, ts FROM filings WHERE customer_id=? AND step=? AND status='receipt' "
                "ORDER BY id DESC", (cid, key))
    if rc:
        ref = rc["ref_no"]
        receipt = has_doc(cid, f"rc_{key}")
    if key == "dcr" and d.get("dcr_cert_no"):
        ref = ref or d["dcr_cert_no"]
    if key == "msedcl" and d.get("msedcl_app_id"):
        ref = ref or d["msedcl_app_id"]
    if key == "loan":
        ref = ref or d.get("loan_ref")
    if key == "loan" and not loan_wanted(cid):
        state = "n/a"
    elif done:
        state = "filed"
    elif failed:
        state = "failed"
    elif key == "dcr" and (d.get("dcr_credit") or "").lower() == "no" and not [i for i in block if i["field"] != closeout.LABEL["dcr_credit"]]:
        state = "waiting"
    elif block:
        state = "not_ready"
    else:
        state = "ready"
    filed = next((h for h in reversed(evs) if h["status"] in ("filed", "receipt", "sanctioned")), None)
    first = evs[0]["ts"] if evs else None
    return {"key": key, "label": label, "state": state, "issues": issues, "blocking": len(block),
            "ref": ref, "receipt": receipt, "screens": parts, "started": first,
            "filed_at": filed["ts"] if filed and state == "filed" else None,
            "minutes": _minutes(first, filed["ts"]) if filed and state == "filed" else None,
            "last": last and {"status": last["status"], "note": last["note"], "ts": last["ts"]}}


NEXT = {"not_ready": "Fix {n} item(s) for the {label}", "ready": "File the {label}: it is ready",
        "failed": "Retry the {label}: the last attempt failed", "waiting": "Wait for the dealer to credit the panels"}


def progress(cid):
    steps = [_step(cid, k, lbl) for k, lbl in STEPS]
    nxt = next(({"step": s["key"], "label": NEXT[s["state"]].format(n=s["blocking"], label=s["label"].lower())}
                for s in steps if s["state"] in NEXT), {"step": "", "label": "K2 filings are complete for this customer"})
    if not registered(cid):
        nxt = {"step": "registration", "label": "Register the customer on PM Surya Ghar first (Registration)"}
    c, d = closeout.data(cid)
    pending_docs = [{"step": s["key"], "field": i["field"], "message": i["message"]}
                    for s in steps if s["state"] not in ("filed", "n/a") for i in s["issues"]
                    if i["kind"] == "missing" and ("upload" in i["message"] or "photo" in i["message"]
                                                    or "document" in i["field"].lower() or "certificate" in i["field"].lower())]
    return {"customer_id": cid, "steps": steps, "next": nxt, "registered": registered(cid),
            "application_no": c["application_no"], "pending_docs": pending_docs,
            "pending_portal": [s["key"] for s in steps if s["state"] == "ready"],
            "failed": [s["key"] for s in steps if s["state"] == "failed"],
            "missing": sum(s["blocking"] for s in steps if s["state"] not in ("filed", "n/a")),
            "refs": {s["key"]: s["ref"] for s in steps if s["ref"]},
            "durations": durations(cid), "post_install": post_install(cid),
            "receipts": (rc := receipts(cid, steps)),
            "missing_receipts": [k for k, v in rc.items() if v["filed"] and not v["file"]]}


def post_install(cid):
    """From the installation team's first upload to the six documents showing on MSEDCL. This is
    elapsed time, not the owner's effort; the 5-minute KPI is measured with a stopwatch."""
    c, d = closeout.data(cid)
    first = db.one("SELECT ts FROM filings WHERE customer_id=? AND step='field' AND status='uploaded' "
                   "ORDER BY id LIMIT 1", (cid,))
    if not first:
        return None
    end = d.get("msedcl_uploaded_at") if d.get("msedcl_uploaded") else None
    ag = d.get("agreement_uploaded_at")
    return {"started": first["ts"], "finished": end, "done": bool(end),
            "minutes": _minutes(first["ts"], end or db.now()),
            "since_agreement_minutes": _minutes(ag, end) if ag and end else None}


def receipts(cid, steps):
    """For each filing: is it filed, what reference, and is the acknowledgement kept in the file."""
    c, d = closeout.data(cid)
    filed = {"registration": bool(c["application_no"]), "agreement": bool(d.get("agreement_uploaded_at")),
             **{s["key"]: s["state"] == "filed" for s in steps}}
    refs = {"registration": c["application_no"], **{s["key"]: s["ref"] for s in steps}}
    out = {}
    for k in RECEIPT_STEPS:
        row = db.one("SELECT ref_no FROM filings WHERE customer_id=? AND step=? AND status='receipt' "
                     "ORDER BY id DESC", (cid, k))
        out[k] = {"label": RECEIPT_LABEL[k], "filed": filed.get(k, False), "ref": (row and row["ref_no"]) or refs.get(k),
                  "file": has_doc(cid, f"rc_{k}"), "saved": bool(row)}
    return out


def durations(cid):
    """Minutes between the milestones that have timestamps, K1 and K2 together."""
    c, d = closeout.data(cid)
    marks = [("Documents in", d.get("docs_at")), ("Registered", d.get("registered_at")),
             ("Accepted by vendor login", d.get("accepted_at")),
             ("Agreement sent", d.get("agreement_sent_at")), ("Agreement uploaded", d.get("agreement_uploaded_at"))]
    for k, lbl in STEPS:
        f = next((h for h in reversed(history(cid)) if h["step"] == k and h["status"] in ("filed", "receipt", "sanctioned")), None)
        marks.append((f"{lbl} filed", f["ts"] if f else d.get("msedcl_uploaded_at") if k == "msedcl" else None))
    marks = [(n, t) for n, t in marks if t]
    marks.sort(key=lambda x: x[1])
    return [{"stage": b[0], "at": b[1], "minutes_since_previous": _minutes(a[1], b[1])}
            for a, b in zip(marks, marks[1:])] if len(marks) > 1 else []


def summary(cid):
    p = progress(cid)
    c, d = closeout.data(cid)
    return {"id": cid, "name": c["name"], "stage": c["stage"], "application_no": c["application_no"],
            "next": p["next"], "missing": p["missing"], "failed": p["failed"],
            "pending_portal": p["pending_portal"], "refs": p["refs"],
            "steps": {s["key"]: s["state"] for s in p["steps"]},
            "done": sum(s["state"] in ("filed", "n/a") for s in p["steps"]), "total": len(p["steps"])}


# ------------------------------- the person's actions -------------------------------
def _ref_ok(cid, step, ref):
    ref = (ref or "").strip()
    if not REF.match(ref):
        raise ValueError("the reference should be 4-40 letters, digits, / _ or - exactly as the portal shows it")
    clash = db.one("SELECT customer_id FROM filings WHERE step=? AND ref_no=? AND customer_id<>? "
                   "AND status IN ('receipt','filed')", (step, ref, cid))
    if clash:
        raise ValueError(f"{ref} is already recorded on {clash['customer_id']}")
    return ref


def _screen(step):
    m = re.match(r"^installation:([1-5])$", step)
    return int(m.group(1)) if m else None


def mark_filed(cid, step, user, ref=None, note=None):
    """A person says they pressed Submit on the portal. Refused if the step is not ready, or if an
    installation screen is filed out of order. MSEDCL cannot be marked by hand: only the page's
    own list is evidence."""
    base = step.split(":")[0]
    if base not in dict(STEPS) or (":" in step and not _screen(step)):
        raise ValueError("unknown step")
    if step == "installation":
        raise ValueError("file the five installation screens one at a time (installation:1 to installation:5)")
    if base == "msedcl":
        raise ValueError("MSEDCL is marked only when its own page shows the six documents; "
                         "open the MSEDCL list with the co-pilot on")
    if base == "loan" and not loan_wanted(cid):
        raise ValueError("this customer is not taking a loan")
    if not registered(cid):
        raise ValueError("register the customer on PM Surya Ghar first")
    n = _screen(step)
    if n:
        block = blocking(screen_issues(cid, n))
        for earlier in range(1, n):
            lt = latest(cid, f"installation:{earlier}")
            if not (lt and lt["status"] == "filed"):
                raise ValueError(f"file screen {earlier} ({SCREENS[earlier]}) first")
    else:
        block = blocking(ISSUES[base](cid))
    if block:
        raise ValueError("not ready: " + "; ".join(i["message"] for i in block[:4]))
    if ref:
        ref = _ref_ok(cid, step, ref)
    track(cid, step, "filed", user["username"], ref, note)
    if ref and base in ("sfr", "dcr", "loan"):
        track(cid, step, "receipt", user["username"], ref, "reference noted when filed")
    if ref and base == "dcr":
        closeout.save(cid, {"dcr_cert_no": ref}, user["username"])
    if ref and base == "loan":
        closeout.save(cid, {"loan_ref": ref}, user["username"])
    db.audit(user["username"], user["role"], f"Marked {step} filed", cid, ref or "")


def mark_failed(cid, step, user, note):
    if step.split(":")[0] not in dict(STEPS):
        raise ValueError("unknown step")
    note = (note or "").strip()
    if not note:
        raise ValueError("say what went wrong, so it can be fixed and retried")
    track(cid, step, "failed", user["username"], None, note)
    db.audit(user["username"], user["role"], f"Marked {step} failed", cid, note[:120])


def retry(cid, step, user):
    last = latest(cid, step)
    if not (last and last["status"] == "failed"):
        raise ValueError("only a failed step can be retried")
    track(cid, step, "retry", user["username"], None, "retry started")
    db.audit(user["username"], user["role"], f"Retry {step}", cid)


LOAN_STATUS = {"submitted": "filed", "sanctioned": "sanctioned", "rejected": "rejected",
               "withdrawn": "withdrawn"}


def loan_status(cid, status, user, ref=None, note=None):
    if status not in LOAN_STATUS:
        raise ValueError("status must be one of: " + ", ".join(LOAN_STATUS))
    if not loan_wanted(cid):
        raise ValueError("this customer is not taking a loan")
    if status == "submitted":
        return mark_filed(cid, "loan", user, ref, note)
    if not latest(cid, "loan") or latest(cid, "loan")["status"] == "retry":
        raise ValueError("record that the application was submitted first")
    if ref:
        ref = _ref_ok(cid, "loan", ref)
        closeout.save(cid, {"loan_ref": ref}, user["username"])
    track(cid, "loan", LOAN_STATUS[status], user["username"], ref, note)
    db.audit(user["username"], user["role"], f"Loan {status}", cid, ref or "")


def record_receipt(cid, step, ref_no, user, filename=None, blob=None):
    """Save the reference the portal gave, and optionally its acknowledgement page or PDF."""
    if step not in RECEIPT_STEPS:
        raise ValueError("unknown step; a receipt belongs to a whole step, not one installation screen")
    ref = _ref_ok(cid, step, ref_no)
    if step == "registration":
        on_file = closeout.data(cid)[0]["application_no"]
        if not on_file:
            raise ValueError("register the customer first; there is no application number yet")
        if ref.upper() != on_file:
            raise ValueError(f"{ref} is not the application number on file ({on_file}); check the acknowledgement")
    if blob is not None:
        store_doc(cid, f"rc_{step.replace(':', '_')}", filename, blob, user["username"])
    track(cid, step, "receipt", user["username"], ref, "receipt saved" + (" with file" if blob else ""))
    base = step.split(":")[0]
    if base == "dcr":
        closeout.save(cid, {"dcr_cert_no": ref}, user["username"])
    db.audit(user["username"], user["role"], f"Receipt saved for {step}", cid, ref)
    return ref


# ------------------------------- files -------------------------------
def kind_of_file(blob):
    if blob.startswith(b"%PDF"):
        return "pdf"
    if blob.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if blob.startswith(b"\x89PNG"):
        return "png"
    return None


def store_doc(cid, kind, filename, blob, who):
    """Validate and keep a customer's document, encrypted. PDFs must open; photos must decode."""
    if not kind.startswith("rc_") and kind not in DOC_KINDS:
        raise ValueError("unknown document type")
    if kind == "loan_approval" and not loan_wanted(cid):
        raise ValueError("this customer is not taking a loan")
    if not blob:
        raise ValueError("that file is empty; choose it again")
    if len(blob) > 15 * 1024 * 1024:
        raise ValueError("that file is over 15 MB; send a smaller one")
    ft = kind_of_file(blob)
    if not ft:
        raise ValueError("send a PDF, JPG or PNG file")
    if ft == "pdf":
        probs = closeout.validate_pdf(blob, 15 * 1024)
        if probs:
            raise ValueError("this PDF cannot be used: " + "; ".join(probs))
    else:
        from PIL import Image
        try:
            Image.open(io.BytesIO(blob)).verify()
        except Exception:
            raise ValueError("this photo is damaged and cannot be opened; take it again")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", (filename or "upload").rsplit("/", 1)[-1].rsplit("\\", 1)[-1])[:60]
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    name = f"{kind}_{stamp}_{safe}" if kind in MULTI else f"{kind}_{safe}"
    p = DOCS / cid / name
    p.parent.mkdir(parents=True, exist_ok=True)
    size = vault.write(p, blob)
    if kind not in MULTI:
        db.ex("DELETE FROM documents WHERE customer_id=? AND kind=?", (cid, kind))
    db.ex("INSERT INTO documents(customer_id,kind,filename,path,bytes,uploaded_at) VALUES(?,?,?,?,?,?)",
          (cid, kind, name, str(p), size, db.now()))
    db.audit(who, "user", "Uploaded document", cid, f"{kind}: {safe} ({size // 1024} KB, encrypted at rest)")
    if kind == "loan_approval":
        track(cid, "loan", "note", who, None, "approval letter saved")
    return {"kind": kind, "filename": name, "bytes": size}


def site_photo(cid, raw, who, browser_gps=None, consent=False):
    """The geotagged photo of the installed system. Location comes from the photo itself; if it
    has none, the phone's location is used ONLY when the person agreed to share it, and only if
    it is a plausible place in India with a usable accuracy."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(raw))
    except Exception:
        raise ValueError("that file is not a photo")
    if closeout.gps(im):
        return closeout.save_photo(cid, raw, who) + ("photo",)
    if not browser_gps:
        raise ValueError("this photo has no GPS location. Allow location on the page and send it again, "
                         "or take the photo with location turned on in the camera")
    if not consent:
        raise ValueError("location was not shared; tick the box to allow the page to use this phone's location")
    lat, lng, acc = browser_gps
    if not in_india(lat, lng):
        raise ValueError(f"the location {lat:.4f}, {lng:.4f} is not in India")
    if acc is not None and acc > 100:
        raise ValueError(f"the phone's location is only accurate to {acc:.0f} m; step outside and try again")
    return closeout.save_photo(cid, raw, who, fallback=(round(lat, 6), round(lng, 6))) + ("phone",)


# ------------------------------- field-team links -------------------------------
FIELD_SLOTS = [  # key, label, what it is, needs GPS
    ("site_photo", "Photo of the installed system", "photo with location", True),
    ("preinstall", "Photo before installation", "photo", False),
    ("install_photo", "Other installation photos", "photos", False),
    ("serial_label", "Panel serial label photos", "photos", False),
    ("serial_sheet", "Panel serial numbers (Excel / CSV)", "sheet", False),
    ("dcr_cert", "DCR certificate", "pdf or photo", False),
    ("invoice", "Invoice / e-way bill", "pdf or photo", False)]


def field_link(cid, user, days=3):
    import secrets
    from datetime import timedelta
    tok = secrets.token_urlsafe(24)
    db.ex("INSERT INTO field_links(token,customer_id,created_by,created_at,expires_at,status,label) VALUES(?,?,?,?,?,?,?)",
          (tok, cid, user["username"], db.now(), (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds"),
           "open", ""))
    db.audit(user["username"], user["role"], "Created a field-upload link", cid, f"{days} days")
    return tok


def field_link_get(token):
    """(row, problem). The row only for a link that is open and in date."""
    r = db.one("SELECT * FROM field_links WHERE token=?", (token,)) if token else None
    if not r:
        return None, "This link is not valid."
    if r["status"] != "open":
        return None, "This link was switched off. Ask the office for a new one."
    if datetime.fromisoformat(r["expires_at"]) < datetime.now():
        return None, "This link has expired. Ask the office for a new one."
    return r, None


def field_checklist(cid):
    c, d = closeout.data(cid)
    have = {r["kind"]: r["n"] for r in db.q("SELECT kind, COUNT(*) n FROM documents WHERE customer_id=? GROUP BY kind", (cid,))}
    sn = closeout.serials(d)
    out = []
    for key, label, what, gps in FIELD_SLOTS:
        if key == "site_photo":
            n = 1 if (DOCS / cid / "site_photo.jpg").exists() else 0
        elif key == "serial_sheet":
            n = 1 if sn else 0
        else:
            n = have.get(key, 0)
        out.append({"key": key, "label": label, "what": what, "gps": gps, "count": n,
                    "required": key in ("site_photo", "serial_sheet", "dcr_cert"), "done": n > 0})
    return out


# ------------------------------- values for the co-pilot -------------------------------
def portal_values(cid):
    c, d = closeout.data(cid)
    sn = closeout.serials(d)
    v = {k: d.get(k) for k in ("roof_free_area", "permissible_kw", "module_make", "almm_model", "module_wp",
                               "module_count", "inverter_make", "inverter_kw", "inverter_serial", "inverter_year",
                               "meter_serial", "dcr_cert_no", "invoice_no", "cell_maker", "cell_invoice",
                               "install_date", "earth_ohm", "earthing_count", "lightning_arrester",
                               "loan_amount", "loan_bank", "loan_branch")}
    v["permissible_kw"] = v["permissible_kw"] or (f"{c['kw']:g}" if c["kw"] else None)
    v["module_serials"] = "\n".join(sn) if sn else None
    return {k: x for k, x in v.items() if x}
