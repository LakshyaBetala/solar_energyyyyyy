"""Milestone 1: from a new customer's documents to registered, accepted by the vendor and the
vendor agreement uploaded on the national portal.

Six steps, each done or not, and the one thing to do next. The record itself lives in the
customers row and the close-out record (closeout.data), so every later document reuses it.
"""
import re
from datetime import datetime
from . import db, closeout, extract
from .config import vendor, region

PRE_STAGES = ("lead", "docs", "register", "feasible")  # before installation
APP_NO = re.compile(r"^NP-[A-Z0-9]+-\d{6,}$")
LATER = {"account_holder", "account_no", "ifsc", "passbook_unread"}  # not needed to register
# what must be on file before the portal form can be filled
REQUIRED = (("consumer_no", "consumer number"), ("name", "customer name"), ("mobile", "mobile"),
            ("kw", "proposed capacity (kW)"))


def create(name, mobile, user):
    name = " ".join((name or "").split())
    if len(name) < 3:
        raise ValueError("enter the customer's name")
    nums = [int(r["id"].split("-")[1]) for r in db.q("SELECT id FROM customers WHERE id LIKE 'SS-%'")]
    cid = f"SS-{max(nums, default=2000) + 1}"
    db.ex("""INSERT INTO customers(id,name,category,stage,workflow,last_activity,subsidy)
             VALUES(?,?,?,?,?,?,0)""", (cid, name, "Residential", "docs", "rooftop_registration",
                                       datetime.now().strftime("%d %b").lstrip("0")))
    if mobile:
        closeout.save(cid, {"mobile": mobile}, user["username"])
    db.audit(user["username"], user["role"], "Added customer", cid, name)
    return cid


def values(cid):
    """Everything the portal forms ask for, in one place. The name filed is the bill's spelling,
    because the portal checks it against the distribution company's register."""
    c, d = closeout.data(cid)
    rows = {r["field"]: r for r in extract.saved(cid)}
    bill = rows.get(extract.PRETTY["bill_name"])
    name = bill["value"] if bill and bill["status"] != "review" else (c["aadhaar_name"] or c["name"])
    return {**region(), "consumer_no": c["consumer_no"], "mobile": d.get("mobile"),
            "email": d.get("email"), "name": name, "address": c["address"], "pin": c["pin"],
            "district": d.get("district"), "sanctioned_load": d.get("sanctioned_load"),
            "capacity": f"{c['kw']:g}" if c["kw"] else None, "category": c["category"],
            "rts_cost": d.get("rts_cost"), "vendor": vendor()["name"],
            "application_no": c["application_no"], "lat": d.get("lat"), "lng": d.get("lng")}


def missing(cid):
    c, d = closeout.data(cid)
    have = {"consumer_no": c["consumer_no"], "name": c["name"] or c["aadhaar_name"],
            "mobile": d.get("mobile"), "kw": c["kw"]}
    return [label for key, label in REQUIRED if not have[key]]


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
        ("details", "Details complete", not miss),
        ("registered", "Registered on PM Surya Ghar", bool(c["application_no"])),
        ("accepted", "Accepted in vendor login", bool(d.get("accepted_at"))),
        ("signed", "Agreement e-signed", signed),
        ("uploaded", "Agreement uploaded", bool(d.get("agreement_uploaded_at"))),
    ]
    done = {k for k, _, ok in steps if ok}
    if not {"bill", "aadhaar"} <= kinds:
        nxt = ("docs", "Upload the bill and Aadhaar")
    elif flagged:
        nxt = ("check", f"Check {len(flagged)} highlighted detail{'s' if len(flagged) > 1 else ''}")
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
    else:
        nxt = ("", "Milestone 1 done for this customer")
    t = lambda k: d.get(k)
    elapsed = None
    if t("docs_at") and t("accepted_at"):
        elapsed = int((datetime.fromisoformat(t("accepted_at")) -
                       datetime.fromisoformat(t("docs_at"))).total_seconds())
    return {"steps": [{"key": k, "label": lbl, "done": ok} for k, lbl, ok in steps],
            "next": {"act": nxt[0], "label": nxt[1]}, "flagged": len(flagged), "missing": miss,
            "link_open": link_open, "elapsed_to_accepted": elapsed,
            "times": {k: t(k) for k in ("docs_at", "registered_at", "accepted_at",
                                         "agreement_sent_at", "agreement_uploaded_at")}}


def save_details(cid, body, user):
    cols = {}
    if "name" in body and body["name"].strip():
        cols["name"] = " ".join(body["name"].split())
    if "consumer_no" in body:
        no = re.sub(r"\D", "", body["consumer_no"] or "")
        if no and not 9 <= len(no) <= 14:
            raise ValueError("the consumer number on an MSEDCL bill has 12 digits")
        cols["consumer_no"] = no or None
    if "kw" in body:
        try:
            kw = float(body["kw"]) if str(body["kw"]).strip() else None
        except ValueError:
            raise ValueError("capacity must be a number of kW, e.g. 3 or 3.3")
        if kw is not None and not 0.5 <= kw <= 10:
            raise ValueError("residential rooftop capacity is between 0.5 and 10 kW")
        cols["kw"] = kw
    for col, v in cols.items():
        db.ex(f"UPDATE customers SET {col}=? WHERE id=?", (v, cid))
    rest = {k: body[k] for k in ("mobile", "email", "district", "rts_cost") if k in body}
    if "mobile" in rest:
        rest["mobile"] = re.sub(r"\D", "", rest["mobile"] or "")[-10:]
        if rest["mobile"] and len(rest["mobile"]) != 10:
            raise ValueError("the mobile number has 10 digits")
    if rest.get("rts_cost"):
        rest["rts_cost"] = re.sub(r"[^\d]", "", rest["rts_cost"])
    if rest:
        closeout.save(cid, rest, user["username"])
    db.audit(user["username"], user["role"], "Updated registration details", cid,
             ", ".join(sorted(list(cols) + list(rest))))


def mark(cid, step, user, app_no=None):
    c, d = closeout.data(cid)
    if step == "registered":
        app_no = (app_no or "").strip().upper()
        if not APP_NO.match(app_no):
            raise ValueError("the application number looks like NP-MHSED26-16165074")
        clash = db.one("SELECT id FROM customers WHERE application_no=? AND id<>?", (app_no, cid))
        if clash:
            raise ValueError(f"{app_no} is already on {clash['id']}")
        db.ex("UPDATE customers SET application_no=?, stage='feasible' WHERE id=?", (app_no, cid))
        closeout.save(cid, {"pmsg_app_no": app_no}, user["username"])
        closeout.mark(cid, user["username"], registered_at=db.now())
    elif step == "accepted":
        if not c["application_no"]:
            raise ValueError("register the customer first")
        closeout.mark(cid, user["username"], accepted_at=db.now())
    elif step == "agreement_uploaded":
        agreement = next(s for s in closeout.status(cid) if s["key"] == "agreement")
        if agreement["state"] != "ready":
            raise ValueError("the agreement is not signed by both sides yet")
        closeout.mark(cid, user["username"], agreement_uploaded_at=db.now())
    else:
        raise ValueError("unknown step")
    db.audit(user["username"], user["role"], f"Marked {step.replace('_', ' ')}", cid, app_no or "")


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
