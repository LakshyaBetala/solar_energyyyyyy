"""Milestone 3: where every customer stands, and what needs doing today.

Stages are the national portal's own ten (as on the client's My Application screen). Solara knows
the steps it filed; the portal knows the DISCOM's (feasibility, inspection, commissioning,
subsidy). When the owner opens a portal list, the co-pilot reads each row's status (read-only,
no clicks) and posts it here, so both sides meet on one screen and any disagreement is shown.
"""
import json, re
from datetime import datetime, timedelta
from . import db, closeout, registration, filing, field

STAGES = [("registration", "Registration", "Consumer"), ("application", "Application", "Consumer"),
          ("feasibility", "Feasibility", "DISCOM"), ("vendor_selection", "Vendor selection", "Consumer"),
          ("agreement", "Upload agreement", "Vendor"), ("installation", "Installation", "Vendor"),
          ("inspection", "Inspection", "DISCOM"), ("commissioning", "Project commissioning", "DISCOM"),
          ("subsidy_request", "Subsidy request", "Consumer"), ("subsidy_disbursal", "Subsidy disbursal", "REC")]
KEYS = [s[0] for s in STAGES]
NAME = {s[0]: s[1] for s in STAGES}
# portal wording (2024 manual and the 2026 screens) to our stage keys; first match wins
WORDS = [(r"disburs", "subsidy_disbursal"), (r"subsidy|claim", "subsidy_request"), (r"commission", "commissioning"),
         (r"inspection", "inspection"), (r"installation|work start", "installation"),
         (r"agreement", "agreement"), (r"vendor selection|vendor consent", "vendor_selection"),
         (r"feasib", "feasibility"), (r"application", "application"), (r"regist", "registration")]
LEGACY = {"registration": "register", "application": "register", "feasibility": "feasible",
          "vendor_selection": "feasible", "agreement": "feasible", "installation": "install",
          "inspection": "netmeter", "commissioning": "netmeter", "subsidy_request": "claim",
          "subsidy_disbursal": "claim"}  # "disbursed" only once the portal shows it Completed
ORDER = ["lead", "docs", "register", "feasible", "install", "netmeter", "claim", "disbursed"]


def parse(text):
    """'Installation (Pending)' -> ('installation', 'pending'). Unknown wording -> (None, ...)."""
    t = " ".join((text or "").lower().split())
    state = "rejected" if re.search(r"reject|return|revert", t) else "done" if re.search(r"complet|approved|disbursed$", t) \
        else "accepting" if re.search(r"(consumer|customer) acceptance", t) else "pending"  # accepting: vendor's part filed
    for rx, key in WORDS:
        if re.search(rx, t):
            return key, state
    return None, state


def capture(portal, rows, user):
    """Rows the co-pilot read off a portal list. Returns which matched a Solara customer."""
    matched, unknown = [], []
    for r in rows[:500]:
        ref, status = str(r.get("ref") or "").strip().upper()[:40], " ".join(str(r.get("status") or "").split())[:80]
        cons = re.sub(r"\D", "", str(r.get("consumer_no") or ""))
        c = None
        if portal == "pmsg" and ref:
            c = db.one("SELECT id, stage FROM customers WHERE application_no=?", (ref,))
        if not c and portal == "msedcl" and ref:
            c = next(({"id": x["customer_id"]} for x in db.q("SELECT customer_id, data FROM closeout")
                      if json.loads(x["data"]).get("msedcl_app_id") == ref), None)
        if not c and cons:  # an old application of the same consumer must not overwrite their current one
            c = db.one("SELECT id, stage FROM customers WHERE consumer_no=? AND (application_no IS NULL OR ?='')",
                       (cons, ref if portal == "pmsg" else ""))
        if not c:
            unknown.append(ref or cons)
            continue
        cid = c["id"]
        stage, state = parse(status) if portal == "pmsg" else (None, None)
        db.ex("""INSERT INTO portal_status(customer_id,portal,ref,status,stage,seen_at,seen_by) VALUES(?,?,?,?,?,?,?)
                 ON CONFLICT(customer_id,portal) DO UPDATE SET ref=excluded.ref,status=excluded.status,
                 stage=excluded.stage,seen_at=excluded.seen_at,seen_by=excluded.seen_by""",
              (cid, portal, ref, status, f"{stage}:{state}" if stage else None, db.now(), user["username"]))
        if portal == "pmsg" and stage:
            _advance(cid, stage, state, user)
        if portal == "msedcl" and re.search(r"verification pending|approved", status, re.I):
            c2, d = closeout.data(cid)
            if not d.get("msedcl_uploaded"):
                closeout.mark(cid, user["username"], msedcl_uploaded="yes", msedcl_uploaded_at=db.now())
        matched.append(cid)
    if matched or unknown:
        db.audit(user["username"], user["role"], "Read portal statuses", portal,
                 f"{len(matched)} matched, {len(unknown)} not in Solara")
    return {"matched": sorted(set(matched)), "unknown": unknown}


def _advance(cid, stage, state, user):
    """The portal is the record for the DISCOM's steps: move the customer forward to it, never back."""
    i = KEYS.index(stage)
    reached = i + (1 if state == "done" else 0)  # stages fully behind the customer
    legacy = LEGACY[KEYS[min(i, len(KEYS) - 1)]]
    if state == "done" and stage == "subsidy_disbursal":
        legacy = "disbursed"
    c = db.one("SELECT stage FROM customers WHERE id=?", (cid,))
    if c and c["stage"] in ORDER and ORDER.index(legacy) > ORDER.index(c["stage"]):
        db.ex("UPDATE customers SET stage=? WHERE id=?", (legacy, cid))
    c2, d = closeout.data(cid)
    # the portal moving past installation means the customer accepted it on their phone
    if reached > KEYS.index("installation") and d.get("installation_at") and not d.get("install_accepted_at"):
        closeout.mark(cid, user["username"], install_accepted_at=db.now())


def portal_row(cid, portal="pmsg"):
    return db.one("SELECT * FROM portal_status WHERE customer_id=? AND portal=?", (cid, portal))


def solara_done(cid):
    """Stages Solara itself knows are done, with when."""
    c, d = closeout.data(cid)
    out = {}
    # the stage on record when the customer came in (or was moved on by hand) counts too
    base = {"feasible": "feasibility", "install": "installation", "netmeter": "inspection",
            "claim": "subsidy_request"}.get(c["stage"])
    if c["stage"] == "disbursed":
        base = None
        out.update({k: "on record" for k in KEYS})
    if base and c["application_no"]:
        out.update({k: "on record" for k in KEYS[:KEYS.index(base)]})
    if c["application_no"]:
        out["registration"] = out["application"] = d.get("registered_at") or "before Solara"
    if d.get("accepted_at"):
        out["vendor_selection"] = d["accepted_at"]
    if d.get("agreement_uploaded_at"):
        out["agreement"] = d["agreement_uploaded_at"]
    if d.get("install_accepted_at"):  # the stage ends when the customer accepts what the vendor filed
        out["installation"] = d["install_accepted_at"]
    return out


def timeline(cid):
    mine = solara_done(cid)
    p = portal_row(cid)
    p_stage, p_state = (p["stage"].split(":") if p and p["stage"] else (None, None))
    pi = KEYS.index(p_stage) if p_stage else -1
    rows, problems = [], []
    for i, (k, name, who) in enumerate(STAGES):
        by_portal = pi > i or (pi == i and p_state == "done")
        here = pi == i and p_state != "done"
        if here and p_state == "accepting":
            name = f"{name} (customer to accept)"
        # where the portal says the application sits wins; Solara being ahead is flagged below
        state = ("rejected" if p_state == "rejected" else "current") if here else \
            "done" if (k in mine or by_portal) else "pending"
        rows.append({"key": k, "name": name, "who": who, "state": state, "at": mine.get(k),
                     "source": "Solara" if k in mine else ("portal" if by_portal or here else "")})
        if k in mine and p_stage and pi <= i and not by_portal and not (pi == i and p_state == "accepting"):
            problems.append(f"Solara has {name.lower()} done, the portal still shows {p['status']}")
    if p_state == "rejected":
        problems.append(f"The portal shows {p['status']}: open it and file again (Retry)")
    d = closeout.data(cid)[1]
    if d.get("installation_at") and p_stage == "installation" and p_state == "pending":
        problems.append(f"Solara has the installation filed, the portal still shows {p['status']}: check it went through")
    if p and not p_stage:
        problems.append(f"The portal shows a status Solara does not know: {p['status']}")
    cur = next((r for r in rows if r["state"] != "done"), None)
    return {"stages": rows, "current": cur["key"] if cur else "subsidy_disbursal",
            "current_name": cur["name"] if cur else "Subsidy paid", "portal": p, "problems": problems}


# ------------------------------- today -------------------------------
# next action -> (group on Today, severity)
K1_GROUP = {"check": ("checks", "warn"), "docs": ("checks", "info"), "details": ("checks", "info"),
            "accept": ("uploads", "warn"), "sign": ("esign", "warn"), "vsig": ("esign", "warn"),
            "wait": ("esign", "info"), "upload": ("uploads", "warn")}
K1_TITLE = {"accept": "Approve in Vendor Consent, then mark it",
            "wait": "Agreement link is with the customer: remind them",
            "upload": "Upload the signed agreement on PM Surya Ghar"}
K2_GROUP = {"loan": ("calls", "warn"), "ask_accept": ("calls", "warn"), "dealer": ("dealer", "info"),
            "serials": ("checks", "warn"), "details": ("checks", "info"), "roof": ("checks", "info"),
            "wait_field": ("field", "info"), "field": ("field", "warn"), "vsig": ("esign", "warn")}


def _m(cid):
    return closeout.data(cid)


def today():
    """Everything a person has to do, grouped, each with the screen to open. Derived live."""
    items = []
    add = lambda group, sev, cid, name, title, view, act="", detail="": items.append(
        {"group": group, "sev": sev, "cid": cid, "name": name, "title": title, "view": view, "act": act,
         "detail": detail})
    paused = []
    since = (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")
    otp_seen = {r["target"]: (r["ts"], r["detail"]) for r in db.q(
        "SELECT target, ts, detail FROM audit WHERE action='Co-pilot waiting for OTP' AND ts>? ORDER BY id", (since,))}
    for r in db.q("SELECT id FROM customers WHERE workflow='rooftop_registration' AND stage<>'disbursed' ORDER BY id"):
        cid = r["id"]
        c, d = _m(cid)
        if d.get("paused_at"):
            paused.append({"cid": cid, "name": c["name"], "reason": d.get("paused_reason"), "by": d.get("paused_by"),
                           "at": d.get("paused_at")})
            continue
        mob = d.get("mobile") or ""
        # resolved once anything was filed for them after the co-pilot saw the OTP box
        if cid in otp_seen and any(str(v) > otp_seen[cid][0] for k, v in d.items() if k.endswith("_at")):
            del otp_seen[cid]
        if cid in otp_seen:
            add("calls", "bad", cid, c["name"], f"The portal is waiting for {c['name']}'s OTP: call {mob}", "reg",
                "", otp_seen[cid][1])
        if c["stage"] in registration.PRE_STAGES and not d.get("agreement_uploaded_at"):
            st = registration.status(cid)  # still in milestone 1
            a, label = st["next"]["act"], st["next"]["label"]
            if a == "register":
                if cid not in otp_seen:
                    add("calls", "warn", cid, c["name"], f"Register {c['name']}: call them for the portal OTP ({mob})", "reg", a)
            elif a in K1_GROUP:
                g, sv = K1_GROUP[a]
                add(g, sv, cid, c["name"], K1_TITLE.get(a, label), "reg", a)
            continue
        if not c["application_no"]:
            continue
        s = filing.status(cid)
        a, label = s["next"]["act"], s["next"]["label"]
        if a:
            g, sv = K2_GROUP.get(a, ("uploads", "warn"))
            if a == "closeout" and "e-sign" in label:
                g = "esign"
            if a == "closeout" and label.startswith("Close-out: complete"):
                g, sv = "checks", "info"
            add(g, sv, cid, c["name"], label, "closeout" if a in ("closeout", "msedcl") else "inst", a)
        for prob in timeline(cid)["problems"]:
            add("checks", "bad", cid, c["name"], prob, "inst", "portal")
    order = {"calls": 0, "esign": 1, "uploads": 2, "dealer": 3, "field": 4, "checks": 5}
    sev = {"bad": 0, "warn": 1, "info": 2}
    items.sort(key=lambda x: (order[x["group"]], sev[x["sev"]], x["cid"]))
    return {"items": items, "paused": paused,
            "counts": {g: sum(1 for x in items if x["group"] == g) for g in order}}


def board():
    """One row per live customer: current stage, Solara's next step, what the portal said."""
    out = []
    for r in db.q("SELECT id FROM customers WHERE workflow='rooftop_registration' ORDER BY id DESC"):
        cid = r["id"]
        c, d = closeout.data(cid)
        t = timeline(cid)
        in_k1 = c["stage"] in registration.PRE_STAGES and not d.get("agreement_uploaded_at")
        nxt = registration.status(cid)["next"] if in_k1 or not c["application_no"] else filing.status(cid)["next"]
        p = t["portal"]
        out.append({"id": cid, "name": c["name"], "kw": c["kw"], "application_no": c["application_no"],
                    "stage": t["current"], "stage_name": t["current_name"],
                    "index": KEYS.index(t["current"]) if t["current"] in KEYS else len(KEYS),
                    "next": nxt, "paused": bool(d.get("paused_at")),
                    "portal_status": p["status"] if p else None, "portal_seen": p["seen_at"] if p else None,
                    "problems": t["problems"], "serials": field.summary(cid)["modules_confirmed"],
                    "others": others(cid, c, d)})
    return out


def others(cid, c, d):
    """The other three portals in a word each: the loan, the DCR certificate, MSEDCL."""
    ms = portal_row(cid, "msedcl")
    loan = None
    if d.get("loan") == "Yes":
        loan = f"applied {d['loan_ref']}" if d.get("loan_at") and d.get("loan_ref") else "applied" if d.get("loan_at") \
            else "to apply"
    dcr = d.get("dcr_cert_no") or ("waiting for the dealer" if d.get("dcr_dealer_wait") else None)
    msedcl = "all six on MSEDCL" if d.get("msedcl_uploaded") else (ms["status"] if ms else None)
    return {"loan": loan, "dcr": dcr, "msedcl": msedcl}
