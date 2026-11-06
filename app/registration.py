"""Milestone 1: from a new customer's documents to registered, accepted by the vendor and the
vendor agreement uploaded on the national portal.

Six steps, each done or not, and the one thing to do next. The record itself lives in the
customers row and the close-out record (closeout.data), so every later document reuses it.
"""
import json, os, re
from datetime import datetime
import sqlite3
from . import db, closeout, extract, valid
from .config import vendor, region

PRE_STAGES = ("lead", "docs", "register", "feasible")  # before installation
APP_NO = re.compile(r"^NP-[A-Z0-9]+-\d{6,}$")
LATER = {"account_holder", "account_no", "ifsc", "passbook_unread"}  # not needed to register
# what must be on file before the portal form can be filled
# the live portal's profile step asks for an email and verifies it by OTP, so it is needed too
REQUIRED = (("consumer_no", "consumer number"), ("name", "customer name"), ("mobile", "mobile"),
            ("email", "email (the portal sends it an OTP)"), ("kw", "proposed capacity (kW)"))


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
    return [k for k in ("module_type",) if not d.get(k)]  # roof area is measured on site, never guessed


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
    return {**region(), "consumer_no": c["consumer_no"], "mobile": d.get("mobile"),
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


def validate(cid):
    """Everything wrong or doubtful with the record, before the portal form is filled.
    kinds: missing, invalid, uncertain (could not be read or is unsure), mismatch (two sources
    disagree). `blocking` is true while any remain; the co-pilot then says so, never silently."""
    c, d = closeout.data(cid)
    issues = [{"kind": "missing", "field": label, "message": f"{label} is not on file"}
              for label in missing(cid)]
    bad = lambda f, m: issues.append({"kind": "invalid", "field": f, "message": m})
    if d.get("mobile") and not MOBILE.match(re.sub(r"\D", "", d["mobile"])):
        bad("mobile", "the mobile number must be 10 digits starting with 6-9")
    if c["pin"] and not PIN.match(c["pin"]):
        bad("PIN code", "the PIN code must be 6 digits")
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
            "link_open": link_open, "elapsed_to_accepted": elapsed, "validation": validate(cid),
            "times": {k: t(k) for k in ("docs_at", "registered_at", "accepted_at",
                                         "agreement_sent_at", "agreement_uploaded_at")}}


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
    if "mobile" in body:
        rest["mobile"] = valid.mobile(body["mobile"])
    if "email" in body:
        rest["email"] = valid.email(body["email"])
    if "district" in body:
        # shortcut: the district list is Maharashtra's; another state keeps free text until its list is added
        rest["district"] = (valid.district(body["district"]) if region()["state"] == "Maharashtra"
                            else valid.name(body["district"], "district", required=False))
    if "rts_cost" in body:
        rest["rts_cost"] = valid.cost(body["rts_cost"])
    if valid.text(body.get("aadhaar"), "Aadhaar").strip():
        rest["aadhaar_last4"] = valid.aadhaar_any(body["aadhaar"])  # the full number is dropped here
    for col, v in cols.items():
        db.ex(f"UPDATE customers SET {col}=? WHERE id=?", (v, cid))
    if rest:
        closeout.save(cid, rest, user["username"])
    db.audit(user["username"], user["role"], "Updated registration details", cid,
             ", ".join(sorted(list(cols) + list(rest))))


def require_ready(cid, what):
    """A later step needs the earlier ones: documents read and checked, details complete."""
    st = status(cid)
    done = {s["key"] for s in st["steps"] if s["done"]}
    if "documents" not in done:
        raise ValueError(f"{what}: upload the bill and Aadhaar and check what was read first")
    if "details" not in done:
        raise ValueError(f"{what}: add " + ", ".join(st["missing"]) + " first")
    if st["validation"]["blocking"]:
        raise ValueError(f"{what}: fix " + st["validation"]["issues"][0]["field"] + " first")


def mark(cid, step, user, app_no=None, replace=False, from_portal=False):
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


# What a status on the vendor's "My Application" list means for milestone 1. Read from the sandbox
# copy of the portal (built from the client's screen recording).
# shortcut: the live portal's status words are not seen yet; check them in the live session, and add
# them here. A status not listed changes nothing and is logged, so the live session shows what to add.
ACCEPTED = re.compile(r"upload agreement|agreement \(pending\)", re.I)
PAST_AGREEMENT = re.compile(r"installation|inspection|commission|subsidy|redeem", re.I)


def from_portal_list(rows, page, user):
    """The co-pilot read the vendor's application list: bring each customer Solara knows up to date.
    Only moves a customer forward, and only for statuses Solara knows."""
    updated, unknown, problems = [], set(), []
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
        if not (accepted or past):
            unknown.add(status)
            continue
        if not d.get("accepted_at"):
            mark(c["id"], "accepted", user)
            updated.append({"id": c["id"], "name": c["name"], "what": "accepted in the vendor login"})
        if past and not d.get("agreement_uploaded_at"):
            try:
                mark(c["id"], "agreement_uploaded", user)
                updated.append({"id": c["id"], "name": c["name"], "what": "agreement uploaded"})
            except ValueError as ex:  # the portal is ahead of Solara: say so, mark nothing
                problems.append({"id": c["id"], "name": c["name"], "what": str(ex)})
    if unknown:
        db.audit(user["username"], user["role"], "Co-pilot saw portal statuses Solara does not know", None,
                 f"{page}: " + "; ".join(sorted(unknown))[:300])
    return {"ok": True, "updated": updated, "unknown": sorted(unknown), "problems": problems}
