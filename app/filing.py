"""Milestone 2: from "agreement uploaded" to "six documents on MSEDCL".

Eight steps, each done or not, and the one thing to do next. The owner files on four portals
through the co-pilot and presses every Submit; Solara knows what each form needs, which value
goes where, what is missing, and when each step was done. The customer's own acts (accepting
the installation, their loan's Aadhaar OTP) stay with the customer and show as waiting for them.

Per-customer controls promised in the terms, in the co-pilot model:
  Start   the next-action button: opens the right portal page, sends the right link
  Pause   hold a customer (reason kept); they leave Today until resumed
  Resume  carry on where it stopped
  Review  everything the co-pilot will put on the next portal form, with what is missing
  Approve the owner signs off that review; the co-pilot shows it, and says if values changed
  Retry   reopen a step the portal rejected, so it is filed again (reason kept)
"""
import hashlib, json
from datetime import datetime
from . import db, closeout, field, registration
from .config import vendor

SFR_NEEDS = ("location_type", "roof_load_ok", "shadow_free", "roof_area", "site_visited", "visitor_name",
             "visitor_phone", "rts_cost")
INSTALL_NEEDS = ("location_type", "phase", "inverter_kw", "inverter_make", "module_wp", "module_count",
                 "module_make", "dcr_cert_no", "protection_checks", "lightning_arrester")
DCR_NEEDS = ("invoice_no", "module_make", "module_wp", "module_count")
MSEDCL_KEYS = [s[0] for s in closeout.DOCS_SPEC if s[1]]
LABEL = {**closeout.LABEL, "lat": "site photo with GPS", "capacity": "Proposed capacity (kW)",
         "name": "Name as on the bill", "consumer_no": "Consumer number", "address": "Address",
         "pin": "PIN code", "state": "State", "discom": "DISCOM", "vendor": "Vendor",
         "application_no": "Application no.", "lng": "Longitude", "category": "Category",
         "aadhaar_name": "Name as on Aadhaar"}
# what the co-pilot puts on each portal form, for Review and Approve
FORMS = {
    "registration": ("consumer_no", "name", "mobile", "email", "state", "discom", "district", "address",
                     "pin", "capacity", "category"),
    "sfr": ("roof_load_ok", "shadow_free", "roof_area", "capacity", "site_visited", "rts_cost",
            "visitor_name", "visitor_phone"),
    "loan": ("name", "mobile", "email", "consumer_no", "address", "pin", "district", "state", "capacity",
             "rts_cost"),
    "dcr": ("application_no", "name", "mobile", "address", "state", "pin", "email", "invoice_no",
            "module_count", "module_serials"),
    "installation": ("location_type", "vendor", "lat", "lng", "phase", "inverter_kw", "inverter_qty",
                     "inverter_make", "inverter_serial", "module_wp", "module_count", "module_make",
                     "module_serials", "dcr_cert_no", "protection_checks", "lightning_arrester"),
}
FILES = {"sfr": ["quotation", "roof"], "installation": ["site_photo"], "dcr": [],  # the agreement is already on the portal by then
         "loan": [], "registration": ["bill", "aadhaar", "passbook", "roof"], "msedcl": MSEDCL_KEYS}
STEP_LABEL = {"sfr": "Site feasibility report", "loan": "Loan application", "field": "Photos and serials",
              "dcr": "DCR certificate", "installation": "Installation on PM Surya Ghar",
              "accepted": "Customer accepted the installation", "documents": "Six documents made",
              "msedcl": "On MSEDCL", "registration": "Registration", "agreement_uploaded": "Agreement uploaded"}


def _cust_filing():
    """Customers past milestone 1 (agreement uploaded, or already further on) whose subsidy is not paid."""
    out = []
    for r in db.q("""SELECT id, stage FROM customers WHERE workflow='rooftop_registration' AND application_no IS NOT NULL
                     AND stage<>'disbursed' ORDER BY id DESC"""):
        c, d = closeout.data(r["id"])
        if d.get("agreement_uploaded_at") or r["stage"] not in registration.PRE_STAGES or backlog(c, d):
            out.append(r)
    return out


def has(d, keys):
    return [LABEL.get(k, k) for k in keys if not d.get(k)]


def status(cid):
    c, d = closeout.data(cid)
    fs = field.summary(cid)
    st = {s["key"]: s for s in closeout.status(cid)}
    made = closeout.built(cid)
    loan = d.get("loan") == "Yes"
    kinds = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    docs_done = all(k in made for k in MSEDCL_KEYS)
    pre = backlog(c, d)
    ok = lambda k, v: pre or bool(v)
    steps = [("sfr", ok("sfr", d.get("sfr_at")))]
    if loan:
        steps.append(("loan", ok("loan", d.get("loan_at"))))
    steps += [("field", pre or bool(d.get("serials_at")) and fs["site_photo"]),
              ("dcr", ok("dcr", d.get("dcr_cert_no"))),
              ("installation", ok("installation", d.get("installation_at"))),
              ("accepted", ok("accepted", d.get("install_accepted_at"))),
              ("documents", docs_done),
              ("msedcl", bool(d.get("msedcl_uploaded")))]
    done = {k for k, v in steps if v}
    nxt = ("", "Milestone 2 done for this customer")
    if pre:
        pass  # filed on the portals before Solara: only the close-out is left
    elif not d.get("sfr_at"):
        miss = has(d, SFR_NEEDS)
        if miss:
            nxt = ("details", f"Add the site visit ({len(miss)} detail{'s' if len(miss) > 1 else ''})" if len(miss) > 2
                   else "Add the site visit: " + ", ".join(miss))
        elif not closeout.signature("vendor"):
            nxt = ("vsig", "Add the company signature (once)")
        elif "roof" not in kinds:
            nxt = ("roof", "Upload the pre-installation roof photo")
        else:
            nxt = ("sfr", "File the site feasibility report")
    elif loan and not d.get("loan_at"):
        nxt = ("loan", "Fill the customer's Jan Samarth loan form with them")
    elif "field" not in done:
        if not fs["link_open"] and not fs["reads"] and not fs["site_photo"]:
            nxt = ("field", "Send the field team the photo link")
        elif fs["to_confirm"] or fs["clash"]:
            nxt = ("serials", f"Confirm {fs['to_confirm'] + fs['clash']} serial number(s) against the photos")
        elif fs["unread"]:
            nxt = ("serials", f"Type {fs['unread']} unreadable label(s) from the photo, or remove them")
        elif not fs["site_photo"]:
            nxt = ("wait_field", "Waiting for the site photo from the field")
        elif not fs["module_count"]:
            nxt = ("details", "Add the number of panels installed")
        elif fs["modules_confirmed"] < fs["module_count"]:
            nxt = ("wait_field", f"{fs['modules_confirmed']} of {fs['module_count']} panel labels in; waiting for the rest")
        else:
            nxt = ("serials", "Confirm the serial numbers")
    elif not d.get("dcr_cert_no"):
        miss = has(d, DCR_NEEDS)
        if d.get("dcr_dealer_wait"):
            nxt = ("dealer", "Waiting for the dealer to transfer the panels on the DCR portal")
        elif miss:
            nxt = ("details", "Add for the DCR certificate: " + ", ".join(miss[:2]) + (f" and {len(miss) - 2} more" if len(miss) > 2 else ""))
        else:
            nxt = ("dcr", "Apply for the DCR certificate")
    elif not d.get("installation_at"):
        miss = has(d, INSTALL_NEEDS) + ([] if fs["site_photo"] else ["site photo with GPS"])
        nxt = ("details", "Add for the installation: " + ", ".join(miss[:2]) + (f" and {len(miss) - 2} more" if len(miss) > 2 else "")) if miss else \
              ("installation", "Submit the installation on PM Surya Ghar")
    elif not d.get("install_accepted_at"):
        nxt = ("ask_accept", "Customer to accept the installation on their phone")
    if nxt[0]:
        pass
    elif not docs_done:
        bad = [s for s in st.values() if s["slot"] and s["state"] != "ready"]
        missing = sum(len(x["note"].split(",")) for x in bad if x["state"] == "missing" and x["note"].startswith("Missing"))
        if any(x["state"] in ("needs_approval", "changed") for x in bad):
            nxt = ("closeout", "Send the documents to the customer for e-sign")
        elif missing or any(x["state"] in ("missing", "blocked") for x in bad):
            nxt = ("closeout", f"Close-out: complete {missing} detail{'s' if missing != 1 else ''}" if missing
                   else "Close-out: " + next(x["note"] for x in bad if x["state"] in ("missing", "blocked")))
        else:
            nxt = ("closeout", "Generate the six documents")
    elif not d.get("msedcl_uploaded"):
        nxt = ("msedcl", "Upload the six documents on MSEDCL")
    t = lambda k: d.get(k)
    post = None
    if t("field_at") and t("msedcl_uploaded_at"):
        post = int((datetime.fromisoformat(t("msedcl_uploaded_at")) - datetime.fromisoformat(t("field_at"))).total_seconds())
    return {"steps": [{"key": k, "label": STEP_LABEL[k], "done": v} for k, v in steps],
            "next": {"act": nxt[0], "label": nxt[1]}, "loan": loan, "field": fs, "backlog": pre,
            "paused": {"at": t("paused_at"), "by": t("paused_by"), "reason": t("paused_reason")} if t("paused_at") else None,
            "post_install_seconds": post,
            "times": {k: t(k) for k in ("agreement_uploaded_at", "sfr_at", "loan_at", "field_at", "serials_at",
                                         "dcr_at", "installation_at", "install_accepted_at", "msedcl_uploaded_at")},
            "receipts": receipts(cid)}


def backlog(c, d):
    """Installed before Solara: the portal steps were filed by hand and only the MSEDCL close-out is
    left (the client's list shows documents pending for months). Nothing filed through Solara yet."""
    return (c["stage"] in ("netmeter", "claim", "disbursed") or bool(d.get("msedcl_app_id"))) and         not any(d.get(k) for k in ("sfr_at", "field_at", "installation_at", "dcr_at"))


def summary(cid):
    c, d = closeout.data(cid)
    s = status(cid)
    return {"id": cid, "name": c["name"], "kw": c["kw"], "stage": c["stage"], "application_no": c["application_no"],
            "next": s["next"], "paused": bool(s["paused"]), "done": sum(x["done"] for x in s["steps"]),
            "total": len(s["steps"])}


def listing():
    return [summary(r["id"]) for r in _cust_filing()]


# ------------------------------- marks -------------------------------
def mark(cid, step, user, ref=None):
    c, d = closeout.data(cid)
    who = user["username"]
    if step == "sfr":
        if not c["application_no"]:
            raise ValueError("register the customer first")
        miss = has(d, SFR_NEEDS)
        if miss:
            raise ValueError("the site feasibility report needs: " + ", ".join(miss))
        closeout.mark(cid, who, sfr_at=db.now())
    elif step == "loan":
        if d.get("loan") != "Yes":
            raise ValueError("this customer is not taking a loan")
        if not d.get("sfr_at"):
            raise ValueError("Jan Samarth opens only after the site feasibility report")
        if ref:
            closeout.save(cid, {"loan_ref": ref.strip()[:40]}, who)
        closeout.mark(cid, who, loan_at=db.now())
    elif step == "dcr":
        cert = (ref or "").strip().upper()
        if len([ch for ch in cert if ch.isalnum()]) < 6:
            raise ValueError("enter the DCR certificate number as shown on the portal")
        other = next((r["customer_id"] for r in db.q("SELECT customer_id, data FROM closeout WHERE customer_id<>?", (cid,))
                      if json.loads(r["data"]).get("dcr_cert_no", "").upper() == cert), None)
        if other:
            raise ValueError(f"DCR certificate {cert} is already on {other}; one certificate covers one customer's panels")
        closeout.save(cid, {"dcr_cert_no": cert}, who)
        closeout.mark(cid, who, dcr_at=db.now(), dcr_dealer_wait=None)
    elif step == "dealer":
        closeout.mark(cid, who, dcr_dealer_wait=None if d.get("dcr_dealer_wait") else db.now())
    elif step == "installation":
        miss = has(d, INSTALL_NEEDS) + ([] if d.get("lat") else ["site photo with GPS"])
        if miss:
            raise ValueError("the installation form needs: " + ", ".join(miss))
        closeout.mark(cid, who, installation_at=db.now())
        if c["stage"] in registration.PRE_STAGES:
            db.ex("UPDATE customers SET stage='install' WHERE id=?", (cid,))
    elif step == "accepted":
        if not d.get("installation_at"):
            raise ValueError("submit the installation first")
        closeout.mark(cid, who, install_accepted_at=db.now())
    else:
        raise ValueError("unknown step")
    db.audit(who, user["role"], f"Filed: {STEP_LABEL.get(step, step)}", cid, ref or "")


REOPEN = {"sfr": ("sfr_at",), "loan": ("loan_at",), "dcr": ("dcr_at",),
          "installation": ("installation_at", "install_accepted_at"),  # re-filed: the customer accepts again
          "accepted": ("install_accepted_at",), "msedcl": ("msedcl_uploaded", "msedcl_uploaded_at"),
          "agreement_uploaded": ("agreement_uploaded_at",)}


def retry(cid, step, user, reason):
    """Reopen a step the portal rejected, so it shows as to do and is filed again."""
    if step not in REOPEN:
        raise ValueError("that step cannot be reopened")
    reason = " ".join((reason or "").split())
    if len(reason) < 4:
        raise ValueError("say why it is filed again (what the portal said)")
    closeout.mark(cid, user["username"], **{k: None for k in REOPEN[step]})
    if step == "dcr":
        closeout.save(cid, {"dcr_cert_no": ""}, user["username"])
    db.audit(user["username"], user["role"], f"Reopened: {STEP_LABEL[step]}", cid, reason[:200])


def pause(cid, user, reason):
    reason = " ".join((reason or "").split())
    if len(reason) < 3:
        raise ValueError("say why it is paused, e.g. customer away until 12 Nov")
    closeout.mark(cid, user["username"], paused_at=db.now(), paused_by=user["name"], paused_reason=reason[:200])
    db.audit(user["username"], user["role"], "Paused customer", cid, reason[:200])


def resume(cid, user):
    closeout.mark(cid, user["username"], paused_at=None, paused_by=None, paused_reason=None)
    db.audit(user["username"], user["role"], "Resumed customer", cid)


# ------------------------------- review and approve -------------------------------
def review(cid, step):
    if step not in FORMS and step != "msedcl":
        raise ValueError("nothing to review for that step")
    v = registration.values(cid)
    c, d = closeout.data(cid)
    v["lat"], v["lng"] = d.get("lat"), d.get("lng")
    rows = [{"key": k, "label": LABEL.get(k, k), "value": v.get(k)} for k in FORMS.get(step, ())]
    kinds = {r["kind"] for r in db.q("SELECT kind FROM documents WHERE customer_id=?", (cid,))}
    made = closeout.built(cid)
    ready = {s["key"] for s in closeout.status(cid) if s["state"] == "ready"}  # the co-pilot makes these on demand
    have = lambda f: f in made or f in ready or f in kinds or (f == "site_photo" and bool(d.get("lat")))
    files = [{"key": f, "title": closeout.SPEC[f][2] if f in closeout.SPEC else f, "ready": have(f)}
             for f in FILES.get(step, [])]
    digest = hashlib.sha256(json.dumps([rows, [f["key"] for f in files if f["ready"]]], sort_keys=True,
                                       default=str).encode()).hexdigest()[:16]
    ap = d.get(f"approved_{step}")
    state = None
    if ap:
        h, at, by = (ap.split("|") + ["", ""])[:3]
        state = {"at": at, "by": by, "current": h == digest}
    return {"step": step, "title": STEP_LABEL.get(step, step), "rows": rows, "files": files,
            "missing": [r["label"] for r in rows if r["value"] in (None, "")] + [f["title"] for f in files if not f["ready"]],
            "hash": digest, "approval": state}


def approve(cid, step, user):
    r = review(cid, step)
    if r["missing"]:
        raise ValueError("cannot approve with blanks: " + ", ".join(r["missing"]))
    closeout.mark(cid, user["username"], **{f"approved_{step}": f"{r['hash']}|{db.now()}|{user['name']}"})
    db.audit(user["username"], user["role"], f"Approved what will be filed: {r['title']}", cid, r["hash"])
    return review(cid, step)


# ------------------------------- receipts -------------------------------
def receipts(cid):
    return [{"step": r["kind"][3:], "title": STEP_LABEL.get(r["kind"][3:], r["kind"][3:]), "at": r["uploaded_at"],
             "bytes": r["bytes"]}
            for r in db.q("SELECT kind, uploaded_at, bytes FROM documents WHERE customer_id=? AND kind LIKE 'rc_%' "
                          "ORDER BY id", (cid,))]


def accept_text(cid):
    """A 3-line how-to the customer gets on WhatsApp for their own approval steps."""
    c, d = closeout.data(cid)
    first = (c["aadhaar_name"] or c["name"]).split()[0]
    return (f"Namaskar {first}, your rooftop solar is installed by {vendor()['name']}. Please approve it: "
            "1) open pmsuryaghar.gov.in and log in with your consumer number and mobile OTP, "
            "2) open your application, 3) press Accept on the installation details. "
            "तुमच्या मोबाईलवर पोर्टल उघडून इन्स्टॉलेशन मंजूर करा.")
