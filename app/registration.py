"""Milestone 1: from a new customer's documents to registered, accepted by the vendor and the
vendor agreement uploaded on the national portal.

Six steps, each done or not, and the one thing to do next. The record itself lives in the
customers row and the close-out record (closeout.data), so every later document reuses it.
"""
import json, os, re
from datetime import datetime
import sqlite3
from . import db, closeout, extract, valid, vault
from .config import vendor, region

PRE_STAGES = ("lead", "docs", "register", "feasible")  # before installation
APP_NO = re.compile(r"^NP-[A-Z0-9]+-\d{6,}$")
LATER = {"account_holder", "account_no", "ifsc", "passbook_unread"}  # not needed to register
# what must be on file before the portal form can be filled
# the live portal's profile step asks for an email and verifies it by OTP, so it is needed too
REQUIRED = (("consumer_no", "consumer number"), ("name", "customer name"), ("mobile", "mobile"),
            ("kw", "proposed capacity (kW)"))
GENDER = {"M": "Male", "F": "Female", "T": "Other", "MALE": "Male", "FEMALE": "Female", "TRANSGENDER": "Other"}
# the bank's name as the portal's subsidy page lists it, from the IFSC's first four letters
BANKS = {"SBIN": "State Bank of India", "MAHB": "Bank of Maharashtra", "HDFC": "HDFC Bank", "ICIC": "ICICI Bank",
         "UTIB": "Axis Bank", "BKID": "Bank of India", "CNRB": "Canara Bank", "PUNB": "Punjab National Bank",
         "UBIN": "Union Bank of India", "BARB": "Bank of Baroda", "IDIB": "Indian Bank", "KKBK": "Kotak Mahindra Bank",
         "CBIN": "Central Bank of India", "IBKL": "IDBI Bank", "YESB": "Yes Bank", "IOBA": "Indian Overseas Bank",
         "UCBA": "UCO Bank", "PSIB": "Punjab & Sind Bank", "INDB": "IndusInd Bank", "FDRL": "Federal Bank"}


class Duplicate(ValueError):
    """The customer looks like one already on file. matches: [{id, name, why}]."""
    def __init__(self, matches):
        self.matches = matches
        super().__init__("This looks like " + "; ".join(f"{m['name']} ({m['id']}, {m['why']})" for m in matches))


MOBILE = re.compile(r"^[6-9]\d{9}$")
PIN = re.compile(r"^\d{6}$")


clean_mobile = valid.mobile


def duplicates(name, mobile=None, consumer_no=None, exclude=None):
    """Customers already on file with the same mobile, the same consumer number, or the same
    name once spelling, case and spaces are ignored."""
    out, nm = {}, extract.norm_name(name)
    for r in db.q("SELECT id, name, aadhaar_name, consumer_no FROM customers WHERE id<>?", (exclude or "",)):
        if consumer_no and r["consumer_no"] == consumer_no:
            out[r["id"]] = {"id": r["id"], "name": r["name"], "why": "same consumer number"}
        elif nm and nm in (extract.norm_name(r["name"]), extract.norm_name(r["aadhaar_name"])):
            out.setdefault(r["id"], {"id": r["id"], "name": r["name"], "why": "same name"})
    if mobile:
        for r in db.q("SELECT customer_id, data FROM closeout"):
            if r["customer_id"] != exclude and json.loads(r["data"]).get("mobile") == mobile:
                c = db.one("SELECT name FROM customers WHERE id=?", (r["customer_id"],))
                out[r["customer_id"]] = {"id": r["customer_id"], "name": c["name"] if c else "",
                                         "why": "same mobile number"}
    return list(out.values())


def create(name, mobile, user, allow_duplicate=False):
    name = valid.name(name, "the customer's name")
    mobile = clean_mobile(mobile)
    dup = duplicates(name, mobile)
    if dup and not allow_duplicate:
        raise Duplicate(dup)
    for _ in range(8):  # two people adding at once can pick the same number; the next try is free
        nums = [int(r["id"].split("-")[1]) for r in db.q("SELECT id FROM customers WHERE id LIKE 'SS-%'")]
        cid = f"SS-{max(nums, default=2000) + 1}"
        try:
            db.ex("""INSERT INTO customers(id,name,category,stage,workflow,last_activity,subsidy)
                     VALUES(?,?,?,?,?,?,0)""", (cid, name, "Residential", "docs", "rooftop_registration",
                                               datetime.now().strftime("%d %b").lstrip("0")))
            break
        except sqlite3.IntegrityError:
            continue
    else:
        raise ValueError("could not add the customer just now; please try again")
    if mobile:
        closeout.save(cid, {"mobile": mobile}, user["username"])
    db.audit(user["username"], user["role"], "Added customer", cid, name)
    return cid


UNITS_PER_KW_MONTH = 120  # a rooftop kW gives roughly 120 units a month in Maharashtra


def derived(cid):
    """Portal values Solara works out or defaults rather than reads from a document. The co-pilot
    fills them but tells the owner to check them."""
    _, d = closeout.data(cid)
    # roof area is measured on site, never guessed; the bank's name comes from the IFSC, the account type is assumed
    return [k for k in ("module_type",) if not d.get(k)] + ["bank_name", "account_type"]


def suggest(cid):
    """A proposed capacity from the bill, for the owner to accept with one click; never saved by itself."""
    rows = {extract.KEY_OF.get(r["field"]): r["value"] for r in extract.saved(cid)}
    def num(k):  # "3.5 kW approx." -> 3.5; nothing readable -> 0
        m = re.search(r"\d+(\.\d+)?", rows.get(k) or "")
        return float(m.group(0)) if m else 0
    avg, sanc = num("avg_units"), num("sanctioned_load")
    if not avg:
        return None
    kw = max(0.5, min(10, round(avg / UNITS_PER_KW_MONTH * 2) / 2))
    if sanc:
        kw = min(kw, sanc)
    return {"kw": kw, "why": f"about {avg:g} units a month on the bill"
            + (f", {sanc:g} kW sanctioned load" if sanc else "")}


def values(cid):
    """Everything the portal forms ask for, in one place. The name filed is the bill's spelling,
    because the portal checks it against the distribution company's register."""
    c, d = closeout.data(cid)
    rows = {r["field"]: r for r in extract.saved(cid)}
    bill = rows.get(extract.PRETTY["bill_name"])
    name = bill["value"] if bill and bill["status"] != "review" else (c["aadhaar_name"] or c["name"])
    read = lambda label: (rows.get(label) or {}).get("value") if (rows.get(label) or {}).get("status") != "review" else None
    ifsc = (read(extract.PRETTY["ifsc"]) or "").upper()
    return {**region(), "consumer_no": c["consumer_no"], "mobile": d.get("mobile"),
            "gender": GENDER.get((read(extract.PRETTY["aadhaar_gender"]) or "").strip().upper()),
            "ifsc": ifsc or None, "bank_name": BANKS.get(ifsc[:4]), "account_holder": read(extract.PRETTY["account_holder"]),
            "account_type": "Savings" if ifsc else None,
            "email": d.get("email"), "name": name, "address": c["address"], "pin": c["pin"],
            "district": d.get("district"), "sanctioned_load": d.get("sanctioned_load"),
            "capacity": f"{c['kw']:g}" if c["kw"] else None, "category": c["category"],
            "module_type": d.get("module_type") or os.environ.get("SOLARA_MODULE_TYPE", "Mono PERC (DCR)"),
            "rts_cost": d.get("rts_cost"), "vendor": vendor()["name"],
            "application_no": c["application_no"], "lat": d.get("lat"), "lng": d.get("lng")}


def missing(cid):
    c, d = closeout.data(cid)
    have = {"consumer_no": c["consumer_no"], "name": c["name"] or c["aadhaar_name"],
            "mobile": d.get("mobile"), "email": d.get("email"), "kw": c["kw"]}
    return [label for key, label in REQUIRED if not have[key]]


MISMATCH = {"bill_name", "pin", "aadhaar_pin", "bill_mobile", "consumer_no", "owner_name"}


def name_vs_aadhaar(c):
    """The Aadhaar name when the customer name on file does not match it, else None. First and last names must
    be the Aadhaar's; a middle name may be left out or given as an initial, nothing else may differ."""
    an = c["aadhaar_name"]
    t, a = extract.norm_name(c["name"]).split(), extract.norm_name(an).split()
    if not (t and a):
        return None
    ok = (t[0] == a[0] and t[-1] == a[-1] and len(t) <= len(a)
          and all(x in a[1:-1] or (len(x) == 1 and any(m.startswith(x) for m in a[1:-1])) for x in t[1:-1]))
    return None if ok else an


def validate(cid):
    """Everything wrong or doubtful with the record, before the portal form is filled.
    kinds: missing, invalid, uncertain (could not be read or is unsure), mismatch (two sources
    disagree). `blocking` is true while any remain; the co-pilot then says so, never silently."""
    c, d = closeout.data(cid)
    issues = [{"kind": "missing", "field": label, "message": f"{label} is not on file"}
              for label in missing(cid)]
    bad = lambda f, m: issues.append({"kind": "invalid", "field": f, "message": m})
    if d.get("mobile") and valid.mobile_masked(d["mobile"]):
        bad("mobile", ("the bill shows only part of the mobile" if d["mobile"].upper() != "N/A" else
                       "no mobile on the bill or the Aadhaar") + ": type the customer's full number, the portal sends the OTP to it")
    elif d.get("mobile") and not MOBILE.match(re.sub(r"\D", "", d["mobile"])):
        bad("mobile", "the mobile number must be 10 digits starting with 6-9")
    if c["pin"] and not PIN.match(c["pin"]):
        bad("PIN code", "the PIN code must be 6 digits")
    if an := name_vs_aadhaar(c):
        issues.append({"kind": "mismatch", "field": "name",
                       "message": f"The customer name “{c['name']}” does not match the Aadhaar, which reads “{an}”. "
                                  "Type the name as on the Aadhaar under Details"})
    if c["consumer_no"]:
        try:
            valid.consumer_no(c["consumer_no"])
        except ValueError as ex:
            bad("consumer number", str(ex))
    for r in extract.saved(cid):
        key = extract.KEY_OF.get(r["field"])
        if r["status"] != "review" or key in LATER:
            continue
        unread = r["value"] == "not read"
        issues.append({"kind": "uncertain" if unread or key not in MISMATCH else "mismatch",
                       "field": r["field"], "message": r["note"] or "check this against the document"})
    return {"issues": issues, "blocking": bool(issues)}


def status(cid):
    c, d = closeout.data(cid)
    kinds = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    rows = extract.saved(cid)
    # the bank page matters at the subsidy stage, not for registration
    flagged = [r for r in rows if r["status"] == "review" and extract.KEY_OF.get(r["field"]) not in LATER]
    miss = missing(cid)
    agreement = next(s for s in closeout.status(cid) if s["key"] == "agreement")
    signed = agreement["state"] in ("ready", "needs_vendor_sig")
    link_open = bool(db.one("""SELECT 1 FROM sign_requests WHERE customer_id=? AND status='sent'
                               AND expires_at>? AND docs LIKE '%agreement%'""", (cid, db.now())))
    steps = [
        ("documents", "Documents read", {"bill", "aadhaar"} <= kinds and bool(rows) and not flagged),
        ("details", "Details complete", not miss and not name_vs_aadhaar(c)),
        ("registered", "Registered on PM Surya Ghar", bool(c["application_no"])),
        ("accepted", "Accepted in vendor login", bool(d.get("accepted_at"))),
        ("signed", "Agreement e-signed", signed),
        ("uploaded", "Agreement uploaded", bool(d.get("agreement_uploaded_at"))),
        ("approved", "Customer approved it on the portal", bool(d.get("agreement_approved_at"))),
    ]
    done = {k for k, _, ok in steps if ok}
    if not {"bill", "aadhaar"} <= kinds:
        nxt = ("docs", "Upload the bill and Aadhaar")
    elif flagged:
        nxt = ("check", f"Check {len(flagged)} highlighted detail{'s' if len(flagged) > 1 else ''}")
    elif name_vs_aadhaar(c):
        nxt = ("details", "Fix the customer name to match the Aadhaar")
    elif miss:
        nxt = ("details", "Add: " + ", ".join(miss))
    elif "registered" not in done:
        nxt = ("register", "Register on PM Surya Ghar")
    elif "accepted" not in done:
        nxt = ("accept", "Approve in Vendor Consent, then mark it here")
    elif not d.get("rts_cost"):
        nxt = ("details", "Add the installation cost for the agreement")
    elif not closeout.signature("vendor"):
        nxt = ("vsig", "Add the company signature (once)")
    elif "signed" not in done:
        nxt = ("wait", "Waiting for the customer's e-sign") if link_open else \
              ("sign", "Send the agreement for e-sign")
    elif "uploaded" not in done:
        nxt = ("upload", "Upload the agreement on PM Surya Ghar")
    elif "approved" not in done:
        nxt = ("approve", "Approve the agreement in the customer's login")
    else:
        nxt = ("", "Milestone 1 done for this customer")
    t = lambda k: d.get(k)
    elapsed = None
    if t("docs_at") and t("accepted_at"):
        elapsed = int((datetime.fromisoformat(t("accepted_at")) -
                       datetime.fromisoformat(t("docs_at"))).total_seconds())
    return {"steps": [{"key": k, "label": lbl, "done": ok} for k, lbl, ok in steps],
            "next": {"act": nxt[0], "label": nxt[1]}, "flagged": len(flagged), "missing": miss,
            "link_open": link_open, "elapsed_to_accepted": elapsed, "validation": validate(cid),
            "times": {k: t(k) for k in ("docs_at", "registered_at", "accepted_at",
                                         "agreement_sent_at", "agreement_uploaded_at", "agreement_approved_at")}}


def save_details(cid, body, user):
    """Check every field first, then save. One bad value saves nothing and keeps what was there."""
    cols, rest = {}, {}
    if valid.text(body.get("name"), "name").strip():
        cols["name"] = valid.name(body["name"], "the customer's name")
    if "consumer_no" in body:
        no = valid.consumer_no(body["consumer_no"])
        other = duplicates("", None, no, exclude=cid) if no else []
        if other:
            raise ValueError(f"consumer number {no} is already on {other[0]['id']} ({other[0]['name']})")
        cols["consumer_no"] = no or None
    if "kw" in body:
        cols["kw"] = valid.kw(body["kw"])
    if "place" in body:   # "Dighi, Pune": printed under the customer's name on the quotation
        cols["place"] = valid.text(body["place"], "place").strip()[:80] or None
    if "mobile" in body:   # a part-hidden number as the bill prints it, or N/A, is kept as it is
        m = valid.text(body["mobile"], "mobile number").strip()
        rest["mobile"] = m.replace(" ", "") if valid.mobile_masked(m) else valid.mobile(m)
    if "email" in body:
        rest["email"] = valid.email(body["email"])
    if "district" in body:
        # shortcut: the district list is Maharashtra's; another state keeps free text until its list is added
        rest["district"] = (valid.district(body["district"]) if region()["state"] == "Maharashtra"
                            else valid.name(body["district"], "district", required=False))
    if "rts_cost" in body:
        rest["rts_cost"] = valid.cost(body["rts_cost"])
    sealed = None
    if valid.text(body.get("aadhaar"), "Aadhaar").strip():
        rest["aadhaar_last4"] = valid.aadhaar_any(body["aadhaar"])
        n = re.sub(r"\D", "", body["aadhaar"])
        if len(n) == 12:
            sealed = vault.seal(n)   # the full number, checked above, kept only encrypted
        elif rest["aadhaar_last4"] != closeout.data(cid)[1].get("aadhaar_last4"):
            sealed = ""              # a different last 4 typed: the stored full number no longer applies
    for col, v in cols.items():
        db.ex(f"UPDATE customers SET {col}=? WHERE id=?", (v, cid))
    if rest:
        closeout.save(cid, rest, user["username"])
    if sealed is not None:
        closeout.mark(cid, user["username"], aadhaar_enc=sealed)
    db.audit(user["username"], user["role"], "Updated registration details", cid,
             ", ".join(sorted(list(cols) + list(rest))))


DOC_CHECKS = {"bill": (("consumer_no", "consumer no."), ("bill_name", "name"), ("bill_mobile", "mobile"),
                        ("address", "address"), ("bill_district", "district")),
              "aadhaar": (("aadhaar_name", "name"), ("aadhaar_masked", "number"), ("aadhaar_dob", "date of birth"),
                          ("aadhaar_address", "address"))}


def doc_status(cid):
    """For the bill and the Aadhaar on file: how the read went (read / check / unread), what it gave, what it
    did not, and whether the model answered."""
    kinds = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    rows = {extract.KEY_OF.get(r["field"]): r for r in extract.saved(cid)}
    _, d = closeout.data(cid)
    out = {}
    for kind, keys in DOC_CHECKS.items():
        if kind not in kinds:
            continue
        got = [lbl for k, lbl in keys if k in rows and rows[k]["value"] != "not read"]
        if kind == "aadhaar" and "number" in got and not d.get("aadhaar_enc"):
            got[got.index("number")] = "number (last 4 only)"
        unsure = [lbl for k, lbl in keys if k in rows and rows[k]["status"] == "review"]
        out[kind] = {"state": "unread" if f"{kind}_unread" in rows else "check" if unsure else "read",
                     "got": got, "missing": [lbl for k, lbl in keys if not (k in rows and rows[k]["value"] != "not read")],
                     "unsure": unsure, "model_error": extract.MODEL_STATE.get((cid, kind)) or None}
    return out


_QUOTES = {}


def QUOTES_DIR():
    from pathlib import Path
    from .config import ROOT
    return Path(os.environ.get("SOLARA_QUOTES_DIR") or ROOT / "Quoatation (all range)")


def quotes():
    """The installation-cost choices: one per quotation in the client's quotation folder, named by its amount
    ("Bank Quotation - 125000.docx"). Read from disk, never written into the code: the repo is public.
    [{"amount": "125000", "inverter_kw": "3", "file": "..."}], cheapest first; [] when there is no folder."""
    folder = QUOTES_DIR()
    files = sorted(folder.glob("*.docx")) if folder.is_dir() else []
    key = tuple((p.name, p.stat().st_mtime) for p in files)
    if key not in _QUOTES:
        import zipfile
        out = []
        for p in files:
            m = re.search(r"(\d{5,7})", p.stem)
            if not m:
                continue
            try:
                xml = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8", "ignore")
                kw = re.search(r"Inverter[^<(]*\((\d+(?:\.\d+)?)\s*kW\)", re.sub(r"<[^>]+>", "", xml))
            except Exception:
                kw = None
            out.append({"amount": m.group(1), "inverter_kw": kw.group(1) if kw else None, "file": p.name})
        _QUOTES.clear()
        _QUOTES[key] = sorted(out, key=lambda q: int(q["amount"]))
    return _QUOTES[key]


def delete_customer(cid, user):
    """Remove a customer and everything kept for them (documents on disk, readings, record, links, runs).
    The audit trail keeps the fact that it happened."""
    import shutil
    from .config import DOCS
    c = db.one("SELECT name FROM customers WHERE id=?", (cid,))
    if not c:
        raise KeyError(cid)
    runs = [r["id"] for r in db.q("SELECT id FROM runs WHERE customer_id=?", (cid,))]
    for t in ("run_steps", "run_events", "holds", "screenshots") if runs else ():
        db.ex(f"DELETE FROM {t} WHERE run_id IN ({','.join('?' * len(runs))})", runs)
    for t in ("runs", "documents", "extractions", "calls", "closeout", "sign_requests", "doc_requests",
              "signatures", "approvals"):
        db.ex(f"DELETE FROM {t} WHERE customer_id=?", (cid,))
    db.ex("UPDATE numbers SET customer_id=NULL WHERE customer_id=?", (cid,))   # the number goes back to the pool
    db.ex("DELETE FROM customers WHERE id=?", (cid,))
    shutil.rmtree(DOCS / cid, ignore_errors=True)
    db.audit(user["username"], user["role"], "Deleted customer", cid, c["name"] or "")


def require_ready(cid, what):
    """A later step needs the earlier ones: documents read and checked, details complete."""
    st = status(cid)
    done = {s["key"] for s in st["steps"] if s["done"]}
    if "documents" not in done:
        raise ValueError(f"{what}: upload the bill and Aadhaar and check what was read first")
    if "details" not in done:
        raise ValueError(f"{what}: " + ("add " + ", ".join(st["missing"]) if st["missing"]
                                       else "make the customer name match the Aadhaar") + " first")
    if st["validation"]["blocking"]:
        raise ValueError(f"{what}: fix " + st["validation"]["issues"][0]["field"] + " first")


def mark(cid, step, user, app_no=None, replace=False, from_portal=False, note=""):
    """from_portal: the co-pilot read the number off the portal's own result page. The customer is
    then registered whatever Solara thought of the record, so the number is always kept."""
    c, d = closeout.data(cid)
    if step == "registered":
        app_no = valid.app_no(app_no)
        old = c["application_no"]
        if old and old != app_no and not (replace and user["role"] == "supervisor"):
            raise ValueError(f"already registered as {old}; a supervisor can replace it after checking the portal")
        if not (from_portal or (replace and old)):
            require_ready(cid, "cannot register")
        clash = db.one("SELECT id FROM customers WHERE application_no=? AND id<>?", (app_no, cid))
        if clash:
            raise ValueError(f"{app_no} is already on {clash['id']}")
        db.ex("UPDATE customers SET application_no=? WHERE id=?", (app_no, cid))
        if c["stage"] in ("lead", "docs", "register"):  # never moves a customer back
            db.ex("UPDATE customers SET stage='feasible' WHERE id=?", (cid,))
        if old and old != app_no:  # written only once the replacement has happened
            db.audit(user["username"], user["role"], "Replaced application number", cid, f"{old} -> {app_no}")
        closeout.save(cid, {"pmsg_app_no": app_no}, user["username"])
        closeout.mark(cid, user["username"], registered_at=db.now())
    elif step == "accepted":
        if not c["application_no"]:
            raise ValueError("register the customer first")
        if d.get("accepted_at"):
            return
        closeout.mark(cid, user["username"], accepted_at=db.now())
    elif step == "agreement_uploaded":
        agreement = next(s for s in closeout.status(cid) if s["key"] == "agreement")
        if agreement["state"] != "ready":
            raise ValueError("the agreement is not signed by both sides yet")
        check = closeout.verify_agreement(cid)
        if not check["ok"]:
            raise ValueError("the signed agreement does not verify: " + "; ".join(check["problems"]))
        closeout.mark(cid, user["username"], agreement_uploaded_at=db.now())
    elif step == "customer_approved":
        if not d.get("agreement_uploaded_at"):
            raise ValueError("upload the agreement on the portal first")
        if d.get("agreement_approved_at"):
            return
        closeout.mark(cid, user["username"], agreement_approved_at=db.now())
    else:
        raise ValueError("unknown step")
    db.audit(user["username"], user["role"], f"Marked {step.replace('_', ' ')}", cid, app_no or note)


def docs_uploaded(cid, user):
    c, d = closeout.data(cid)
    if not d.get("docs_at"):
        closeout.mark(cid, user, docs_at=db.now())


def summary(cid):
    c, _ = closeout.data(cid)
    st = status(cid)
    return {"id": cid, "name": c["name"], "consumer_no": c["consumer_no"], "kw": c["kw"],
            "application_no": c["application_no"], "next": st["next"],
            "done": sum(s["done"] for s in st["steps"]), "total": len(st["steps"])}


# What a status on the vendor's "My Application" list means for milestone 1. Read from the sandbox
# copy of the portal (built from the client's screen recording).
# shortcut: the live portal's status words are not seen yet; check them in the live session, and add
# them here. A status not listed changes nothing and is logged, so the live session shows what to add.
ACCEPTED = re.compile(r"upload agreement|agreement \(pending\)", re.I)
PAST_AGREEMENT = re.compile(r"installation|inspection|commission|subsidy|redeem", re.I)
next_of = lambda cid: status(cid)["next"]  # from_portal_list's own `status` is the row's text
# the vendor's part is filed and the customer still has to approve it in their login
UPLOADED = re.compile(r"acceptance|upload agreement \((completed|approved)\)", re.I)
# Installation opens only once the customer approved the agreement (customer login, 7 Nov 2026:
# Upload Agreement Completed, Installation In Progress); a later stage implies it too
APPROVED = re.compile(r"installation \((in progress|completed|approved)\)|inspection|commission|subsidy|redeem", re.I)


def from_portal_list(rows, page, user):
    """The co-pilot read the vendor's application list: bring each customer Solara knows up to date.
    Only moves a customer forward, and only for statuses Solara knows."""
    updated, unknown, problems, seen = [], set(), [], []
    for row in rows[:300]:
        try:
            app = valid.app_no(row.get("app_no"))
        except (ValueError, AttributeError):
            continue
        status = valid.text(row.get("status"), "status").strip()[:80]
        c = db.one("SELECT id, name FROM customers WHERE application_no=?", (app,))
        if not c or not status:
            continue
        _, d = closeout.data(c["id"])
        accepted, past = bool(ACCEPTED.search(status)), bool(PAST_AGREEMENT.search(status))
        uploaded, approved = past or bool(UPLOADED.search(status)), bool(APPROVED.search(status))
        if not (accepted or past):
            unknown.add(status)
            continue
        if not d.get("accepted_at"):
            mark(c["id"], "accepted", user, note=f"read from the portal list: {status}")
            updated.append({"id": c["id"], "name": c["name"], "what": "accepted in the vendor login"})
        for step, on, what in (("agreement_uploaded", uploaded, "agreement uploaded"),
                               ("customer_approved", approved, "customer approved the agreement")):
            if on and not d.get(step.replace("customer_", "agreement_") + "_at"):
                try:
                    mark(c["id"], step, user, note=f"read from the portal: {status}")
                    updated.append({"id": c["id"], "name": c["name"], "what": what})
                    _, d = closeout.data(c["id"])
                except ValueError as ex:  # the portal is ahead of Solara: say so, mark nothing
                    problems.append({"id": c["id"], "name": c["name"], "what": str(ex)})
                    break
        seen.append({"id": c["id"], "name": c["name"], "next": next_of(c["id"])})
    if unknown:
        db.audit(user["username"], user["role"], "Co-pilot saw portal statuses Solara does not know", None,
                 f"{page}: " + "; ".join(sorted(unknown))[:300])
    return {"ok": True, "updated": updated, "unknown": sorted(unknown), "problems": problems, "seen": seen}


def save_layout(body, user):
    """A real portal page's layout sent from the co-pilot in the live session: field names, types and
    list choices, never values. Kept as a file for the developer to turn into a test."""
    from .config import DATA
    clip = lambda v: valid.text(v, "layout")[:80] if not isinstance(v, (list, dict, bool)) else v
    fields = [{k: clip(v) if k != "options" else [clip(o) for o in (v or [])[:60]] for k, v in f.items()
               if k in ("tag", "type", "label", "all_labels", "rule", "id", "name", "placeholder", "required", "options")}
              for f in (body.get("fields") or [])[:200] if isinstance(f, dict)]
    page = clip(body.get("page", ""))
    out = DATA / "layouts" / f"{datetime.now():%Y%m%d-%H%M%S}_{re.sub(r'[^A-Za-z0-9]+', '-', page)[:60]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"page": page, "title": clip(body.get("title", "")), "fields": fields,
                               "buttons": [clip(b) for b in (body.get("buttons") or [])[:40]], "at": db.now()},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    db.audit(user["username"], user["role"], "Co-pilot saved a page layout", None, f"{page}: {len(fields)} fields")
    return {"ok": True, "fields": len(fields), "file": out.name}


def phone10(cid):
    _, d = closeout.data(cid)
    n = "".join(ch for ch in (d.get("mobile") or "") if ch.isdigit())[-10:]
    return n if len(n) == 10 else ""


def heads_up(cid, why="register"):
    """Before a call: tell the customer a code is coming, so they keep the phone close.
    The owner taps Send in WhatsApp; nothing is sent by Solara itself."""
    from urllib.parse import quote
    c, _ = closeout.data(cid)
    n = phone10(cid)
    if not n:
        return None
    first = (c["aadhaar_name"] or c["name"]).split()[0]
    if why == "approve":
        text = (f"Namaskar {first}, I am approving your solar agreement on PM Surya Ghar now. You will get one code by "
                f"SMS. Please tell me the code when I call.\nनमस्कार, मी आत्ता PM सूर्य घर वर तुमचा करार मंजूर करत आहे. "
                f"तुम्हाला SMS ने एक कोड येईल. मी फोन केल्यावर तो मला सांगा. - {vendor()['name']}")
    else:
        text = (f"Namaskar {first}, I am registering your rooftop solar on PM Surya Ghar now. In the next few minutes "
                f"you will get a code by SMS. Please keep your phone with you and tell me the code when I call.\n"
                f"नमस्कार, मी आत्ता तुमची सौर नोंदणी करत आहे. काही मिनिटांत तुम्हाला SMS ने एक कोड येईल. मी फोन केल्यावर तो मला "
                f"सांगा. - {vendor()['name']}")
    return {"phone": n, "tel": f"tel:+91{n}", "whatsapp": f"https://wa.me/91{n}?text={quote(text)}"}


def today(close_rows):
    """Everything to do now, across all customers, as one list in plain words. Each line is one action.
    close_rows: the close-out summaries (built in main, beside their screen)."""
    calls, todo, portal, waiting = [], [], [], []
    for r in db.q(f"""SELECT id FROM customers WHERE workflow='rooftop_registration' AND stage IN
                      ({",".join("?" * len(PRE_STAGES))}) ORDER BY id""", PRE_STAGES):
        cid = r["id"]
        c, d = closeout.data(cid)
        st = status(cid)
        act, first = st["next"]["act"], (c["aadhaar_name"] or c["name"] or "").split()[0]
        line = {"cid": cid, "name": c["name"], "screen": "reg", "act": act, "phone": phone10(cid)}
        if act == "docs":
            open_link = db.one("SELECT 1 FROM doc_requests WHERE customer_id=? AND expires_at>?", (cid, db.now()))
            (waiting if open_link else todo).append({**line, "text": f"{first} has the link for the bill and Aadhaar" if open_link
                                                     else f"Get the bill and Aadhaar from {first}"})
        elif act in ("check", "details"):
            todo.append({**line, "text": f"Check what Solara read for {first}" if act == "check" else f"Add {first}'s missing details"})
        elif act == "register":
            calls.append({**line, "text": f"Call {first} for the OTP and register", "otp": heads_up(cid)})
        elif act == "accept":
            portal.append({**line, "text": f"Approve {first} in Vendor Consent"})
        elif act == "vsig":
            todo.append({**line, "text": "Add the company signature (once)"})
        elif act == "sign":
            todo.append({**line, "text": f"Send {first} the agreement to sign"})
        elif act == "wait":
            waiting.append({**line, "text": f"{first} has the agreement to sign"})
        elif act == "upload":
            portal.append({**line, "text": f"Upload {first}'s signed agreement"})
        elif act == "approve":
            calls.append({**line, "text": f"Call {first} to approve the agreement in their login", "otp": heads_up(cid, "approve")})
    for x in close_rows:
        if x["uploaded"]:
            continue
        first = (x["name"] or "").split()[0]
        line = {"cid": x["id"], "name": x["name"], "screen": "closeout", "phone": phone10(x["id"])}
        if x["waiting_customer"] and x["link_open"]:
            waiting.append({**line, "act": "wait", "text": f"{first} has the installation papers to sign"})
        elif x["missing"]:
            todo.append({**line, "act": "fix", "text": f"Fill in {first}'s installation details"})
        elif x["waiting_customer"]:
            todo.append({**line, "act": "sign", "text": f"Send {first} the installation papers to sign"})
        elif x["built"] < x["total"]:
            todo.append({**line, "act": "build", "text": f"Make {first}'s MSEDCL documents"})
        else:
            portal.append({**line, "act": "upload", "text": f"Upload {first}'s six documents to MSEDCL"})
    return {"calls": calls, "todo": todo, "portal": portal, "waiting": waiting}
