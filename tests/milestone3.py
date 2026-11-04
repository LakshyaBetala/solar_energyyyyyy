"""Milestone 3 acceptance test (KPI K3): one screen with every customer's stage, matching the
portal, and today's list of everything that needs a person; the monthly Excel in one click; and
the per-customer controls the terms promise (Start, Pause, Resume, Review, Approve, Retry).

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/milestone3.py                     (in another)

Ten customers sit at ten different points on the national portal's sandbox. The owner opens My
Application once with the co-pilot loaded; it reads every row's status (read only). Then:
  - the stage Solara shows matches the portal for 10 of 10, and the two that disagree with Solara
    (a filing the portal rejected, a step Solara has done that the portal does not) are flagged
  - Today lists the OTP calls, e-signs, uploads, dealer waits, field work and checks, and each
    item's button opens the right screen for that customer
  - the controls work on a live customer and leave an audit trail; a viewer cannot use them
  - the monthly workbook and PDF come out in one click with every customer's dates
Resets the demo before and after. Synthetic data only.
"""
import asyncio, base64, io, json, sys, time
from datetime import datetime
from pathlib import Path
import httpx
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, closeout  # noqa: E402
import fixtures as fx  # noqa: E402

BASE = "http://127.0.0.1:8900"
EXT = Path(__file__).resolve().parent.parent / "extension"
PASS, FAIL = [], []
MONTH = datetime.now().strftime("%Y-%m")


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def client(user):
    c = httpx.Client(base_url=BASE, timeout=120, follow_redirects=True)
    c.post("/api/login", json={"username": user, "password": "demo"}).raise_for_status()
    return c


def drawn():
    im = Image.new("RGBA", (420, 140), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(20, 90), (80, 30), (130, 100), (190, 40), (260, 95), (390, 50)], fill=(10, 20, 60, 255), width=4)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


INSTALLED = {"location_type": "Urban", "roof_load_ok": "Yes", "shadow_free": "Yes", "roof_area": "30", "site_visited": "Yes",
             "visitor_name": "Amol Kadam", "visitor_phone": "9890012345", "rts_cost": "180000", "phase": "Single phase",
             "inverter_kw": "3", "inverter_make": "Polycab PSIS-3K", "module_wp": "550", "module_count": "2",
             "module_make": "Premier Energies", "protection_checks": "Yes", "lightning_arrester": "Yes",
             "invoice_no": "INV/26-27/0700", "inverter_serial": "PSIS3K26A07001"}


def put_on_portal(app_no, consumer_no, name, kw, status, agreement=True):
    """The application as the portal holds it: consented by the vendor, at this status."""
    db.ex("INSERT OR REPLACE INTO portal_applications(application_no,consumer_no,applicant_name,capacity,submitted_at,payload) "
          "VALUES(?,?,?,?,?,?)", (app_no, consumer_no, name.upper(), kw, db.now(), "{}"))
    db.ex("INSERT OR REPLACE INTO pmsg_vendor(application_no,consented_at,agreement_at) VALUES(?,?,?)",
          (app_no, db.now(), db.now() if agreement else None))
    db.ex("INSERT OR REPLACE INTO pmsg_install(application_no,stage) VALUES(?,?)", (app_no, status))


def new_customer(sup, name, n, stage="feasible"):
    cid = sup.post("/api/customers", json={"name": name}).json()["customer"]["id"]
    app_no = f"NP-MHSED26-1619{n:04d}"
    cons = f"17009{n:07d}"
    db.ex("UPDATE customers SET consumer_no=?, kw=3, address='Plot 1, Test Nagar, Pune', pin='411001' WHERE id=?", (cons, cid))
    sup.post(f"/api/registration/{cid}/mark", json={"step": "registered", "app_no": app_no}).raise_for_status()
    db.ex("UPDATE customers SET stage=? WHERE id=?", (stage, cid))
    closeout.mark(cid, "test", accepted_at=db.now(), agreement_uploaded_at=db.now())
    return cid, app_no, cons


def through_field(cid, n):
    """The site visit and field work done, as milestone 2 leaves them."""
    closeout.save(cid, {**INSTALLED, "module_serials": f"K3T{n:03d}A0000001\nK3T{n:03d}A0000002"}, "test")
    closeout.mark(cid, "test", sfr_at=db.now(), field_at=db.now(), serials_at=db.now())
    closeout.save_photo(cid, closeout._demo_photo(18.52 + n / 1000, 73.85), "test")


async def main():
    sup = client("r.deshmukh")
    print("  reset:", sup.post("/api/demo/reset").json()["runnable"])
    if not db.one("SELECT 1 FROM signatures WHERE role='vendor'"):
        sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"}).raise_for_status()

    # ---------------- ten customers, ten points on the portal ----------------
    seeded = {r["id"]: r for r in db.q("SELECT id, application_no, consumer_no, name, kw FROM customers WHERE id IN "
                                         "('SS-2041','SS-2042','SS-2043','SS-2048')")}
    want = {}  # cid -> the stage Solara must show after reading the portal
    for cid, status, stage in (("SS-2041", "Subsidy Disbursal (Completed)", "Subsidy paid"),
                               ("SS-2042", "Inspection (Pending)", "Inspection"),
                               ("SS-2043", "Upload Agreement (Pending)", "Upload agreement"),
                               ("SS-2048", "Subsidy Request (Pending)", "Subsidy request")):
        c = seeded[cid]
        put_on_portal(c["application_no"], c["consumer_no"], c["name"], c["kw"], status, agreement=cid != "SS-2043")
        want[cid] = stage
    made = {}
    plan = [("Anil Patil", "Installation (Pending)", "Installation", "install"),
            ("Bhavna Joshi", "Installation (Consumer Acceptance Pending)", "Installation (customer to accept)", "install"),
            ("Chetan More", "Project Commissioning (Pending)", "Project commissioning", "netmeter"),
            ("Deepa Rao", "Installation (Rejected)", "Installation", "install"),
            ("Eknath Pawar", "Upload Agreement (Pending)", "Upload agreement", "feasible"),
            ("Farida Shaikh", "Subsidy Disbursal (Pending)", "Subsidy disbursal", "claim")]
    for i, (name, status, stage, legacy) in enumerate(plan, 1):
        cid, app_no, cons = new_customer(sup, name, i, legacy)
        put_on_portal(app_no, cons, name, 3, status)
        made[name.split()[0]] = cid
        want[cid] = stage
    A, B, C, D, E, F = (made[k] for k in ("Anil", "Bhavna", "Chetan", "Deepa", "Eknath", "Farida"))
    for cid in (A, B, D):
        through_field(cid, int(cid[-2:]))
    closeout.save(A, {"dcr_cert_no": "NISE-B2C-26-009901"}, "test")      # A: ready to submit the installation
    for cid in (B, D):
        closeout.save(cid, {"dcr_cert_no": f"NISE-B2C-26-0099{cid[-2:]}"}, "test")
        closeout.mark(cid, "test", dcr_at=db.now(), installation_at=db.now())  # B and D: filed; D was then rejected
    closeout.mark(E, "test", sfr_at=db.now())                               # E: next is the field team
    db.ex("UPDATE customers SET stage='feasible' WHERE id=?", (E,))
    put_on_portal("NP-MHSED26-16199999", "170099999999", "Not In Solara", 3, "Installation (Pending)")
    print(f"  ten customers on the sandbox portal: {', '.join(want)}")
    key = sup.post("/api/copilot/key").json()["key"]
    before = json.dumps([db.q("SELECT * FROM pmsg_install ORDER BY application_no"),
                         db.q("SELECT application_no, consented_at, agreement_at FROM pmsg_vendor ORDER BY application_no")])

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            fx.browser_profile(), channel="chromium", headless=True, viewport={"width": 1440, "height": 900},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{key}'}})")
        errors = []

        # ---------------- the co-pilot reads My Application ----------------
        print("\n  -- statuses from the portal")
        pm = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pm.goto(f"{BASE}/pmsg/vendor/applications")
        await pm.wait_for_function("(document.querySelector('#solaraPanel') || {innerText: ''}).innerText.includes('updated in Solara')", timeout=30000)
        panel = await pm.inner_text("#solaraPanel")
        check("the co-pilot reads all 11 rows; 10 updated in Solara, 1 not in Solara",
              "Read 11 statuses" in panel and "10" in panel and "1 not in Solara" in panel, " ".join(panel.split())[:120])
        after = json.dumps([db.q("SELECT * FROM pmsg_install ORDER BY application_no"),
                            db.q("SELECT application_no, consented_at, agreement_at FROM pmsg_vendor ORDER BY application_no")])
        check("reading the list changed nothing on the portal (read only, no clicks)", before == after)
        board = {r["id"]: r for r in sup.get("/api/board").json()["rows"]}
        got = {cid: board[cid]["stage_name"] for cid in want}
        right = [cid for cid in want if got[cid] == want[cid]]
        check(f"stage on Solara's screen matches the portal for {len(right)} of 10", len(right) == 10,
              "; ".join(f"{c}: {got[c]} vs {want[c]}" for c in want if c not in right))
        probs = {cid for cid, r in board.items() if r["problems"]}
        check("the rejected filing and the step the portal has not taken are flagged, nothing else",
              probs == {D, E}, str({c: board[c]["problems"] for c in probs}))
        check("the customer accepting the installation is shown as their step, not a mismatch",
              board[B]["stage_name"] == "Installation (customer to accept)" and not board[B]["problems"])
        legacy = {r["id"]: r["stage"] for r in db.q("SELECT id, stage FROM customers")}
        check("customers move forward with the portal (inspection → net metering stage)", legacy["SS-2042"] == "netmeter")
        check("and never backwards", legacy["SS-2048"] == "claim")
        check("a customer still to accept is not marked accepted", not closeout.data(B)[1].get("install_accepted_at"))

        # ---------------- the dashboard ----------------
        print("\n  -- one screen")
        dash = await ctx.new_page()
        dash.on("pageerror", lambda ex: errors.append(str(ex)))
        await dash.goto(BASE)
        await dash.click('[data-as="r.deshmukh"]')
        await dash.wait_for_selector("#otherview [data-group=calls]")
        await dash.click('.navitem[data-view="pipeline"]')
        await dash.wait_for_selector("#board")
        txt = await dash.inner_text("#board")
        shown = [cid for cid in want if cid in txt]
        check("every live customer is on the board, with the portal's status beside Solara's stage",
              len(shown) == 10 and "Inspection (Pending)" in txt and "seen" in txt, f"{len(shown)} of 10")
        rows = await dash.evaluate("""[...document.querySelectorAll('#board tbody tr')].map(r => [r.cells[0].innerText.trim(),
            r.cells[3].innerText.trim(), r.querySelectorAll('.dots i.done').length])""")
        ui = {r[0]: r[1] for r in rows}
        check("the screen shows the same stage for all ten", all(ui.get(c) == want[c] for c in want),
              "; ".join(f"{c}: {ui.get(c)}" for c in want if ui.get(c) != want[c]))
        await fx_shot(dash, "m3-board")

        print("\n  -- today")
        sup.post("/api/copilot/report", headers={"X-Solara-Key": key},
                 json={"customer_id": C, "event": "otp_waiting", "page": "pmsg/consumer"})  # the portal waits for C's OTP
        closeout.mark(D, "test", dcr_dealer_wait=None)
        t = sup.get("/api/today").json()
        groups = {}
        for x in t["items"]:
            groups.setdefault(x["group"], set()).add(x["cid"])
        check("calls: the customer the portal is waiting on for an OTP", C in groups.get("calls", set()))
        check("calls: the customer who has to accept their installation", B in groups.get("calls", set()))
        check("e-signs: the documents waiting for the customer's signature", "SS-2042" in groups.get("esign", set()))
        check("uploads: the installation ready to submit", A in groups.get("uploads", set()))
        check("field: the customer whose site photos are next", E in groups.get("field", set()))
        check("checks: the rejected filing and the portal mismatch", {D, E} <= groups.get("checks", set()))
        closeout.save(F, {**INSTALLED}, "test")
        closeout.mark(F, "test", sfr_at=db.now(), field_at=db.now(), serials_at=db.now(), dcr_dealer_wait=db.now())
        closeout.save(F, {"module_serials": "K3TF0A0000001\nK3TF0A0000002"}, "test")
        closeout.save_photo(F, closeout._demo_photo(18.6, 73.9), "test")
        t = sup.get("/api/today").json()
        check("waiting for the dealer: the customer whose panels are not transferred",
              any(x["cid"] == F and x["group"] == "dealer" for x in t["items"]))
        await dash.click('.navitem[data-view="today"]')
        await dash.wait_for_selector(f'[data-group=dealer] [data-cid="{F}"]')
        await dash.click(f'[data-group=dealer] [data-cid="{F}"]')
        await dash.wait_for_selector("#instDealerClear")
        sel = await dash.inner_text('[data-inst][aria-current="true"]')
        check("an item's button opens that customer's screen at the right step", F in sel and "dealer" in (await dash.inner_text("#mbody")).lower())
        await dash.click("[data-close]")
        await dash.click('.navitem[data-view="today"]')
        await dash.wait_for_selector(f'[data-group=calls] [data-cid="{B}"]')
        await dash.click(f'[data-group=calls] [data-cid="{B}"]')
        await dash.wait_for_selector("#acceptText")
        check("the acceptance call opens the 3-line message for the customer", "Accept" in await dash.input_value("#acceptText"))
        await dash.click("[data-close]")
        await fx_shot(dash, "m3-today")

        # ---------------- controls ----------------
        print("\n  -- per-customer controls")
        op, viewer = client("s.kale"), client("a.more")
        check("a viewer cannot pause, approve or retry",
              viewer.post(f"/api/filing/{A}/pause", json={"reason": "x y z"}).status_code == 403 and
              viewer.post(f"/api/filing/{A}/approve", json={"step": "installation"}).status_code == 403 and
              viewer.post(f"/api/filing/{A}/retry", json={"step": "installation", "reason": "test"}).status_code == 403)
        check("an operator cannot approve (a supervisor signs off)", op.post(f"/api/filing/{A}/approve", json={"step": "installation"}).status_code == 403)
        check("pause needs a reason", sup.post(f"/api/filing/{A}/pause", json={"reason": ""}).status_code == 400)
        await dash.click('.navitem[data-view="inst"]')
        await dash.click(f'[data-inst="{A}"]')
        await dash.wait_for_selector("#instPause")
        async with dash.expect_popup() as pop:
            await dash.click("#instNext")                                                  # Start
        page = await pop.value
        check("Start opens the portal page for the next step", "/pmsg/vendor/applications" in page.url, page.url)
        await page.close()
        await dash.click("#instReview")                                                      # Review
        await dash.wait_for_selector("#revApprove")
        body = await dash.inner_text("#mbody")
        check("Review lists every value for the installation form, with the files", "Polycab PSIS-3K" in body and
              "Files" in body and "blank" not in body, " ".join(body.split())[:100])
        await dash.click("#revApprove")                                                      # Approve
        await dash.wait_for_selector("#scrim[hidden]", state="attached")
        look = httpx.get(f"{BASE}/api/copilot/lookup", params={"cid": A}, headers={"X-Solara-Key": key}).json()
        check("the co-pilot sees the approval for that form", (look["approvals"]["installation"] or {}).get("current") is True)
        sup.put(f"/api/filing/{A}", json={"inverter_kw": "3.3"}).raise_for_status()
        look = httpx.get(f"{BASE}/api/copilot/lookup", params={"cid": A}, headers={"X-Solara-Key": key}).json()
        check("a value changed after approval shows as changed", look["approvals"]["installation"]["current"] is False)
        await dash.click("#instPause")                                                       # Pause
        await dash.fill("#pauseWhy", "customer away until 12 Nov")
        await dash.click("#instPauseGo")
        await dash.wait_for_selector("#instResume")
        t = sup.get("/api/today").json()
        check("a paused customer leaves Today's lists and shows under Paused, with the reason",
              not any(x["cid"] == A for x in t["items"]) and any(x["cid"] == A and "12 Nov" in x["reason"] for x in t["paused"]))
        check("the co-pilot shows the pause on the portal", (httpx.get(f"{BASE}/api/copilot/lookup", params={"cid": A},
              headers={"X-Solara-Key": key}).json()["paused"] or {}).get("reason") == "customer away until 12 Nov")
        await dash.click("#instResume")                                                      # Resume
        await dash.wait_for_selector("#instPause")
        check("resumed: back on Today where it stopped", any(x["cid"] == A for x in sup.get("/api/today").json()["items"]))
        await dash.click(f'[data-inst="{D}"]')
        await dash.wait_for_selector("#instRetry")
        await dash.click("#instRetry")                                                       # Retry
        await dash.select_option("#retryStep", "installation")
        await dash.fill("#retryWhy", "plant photo rejected: no coordinates visible")
        await dash.click("#instRetryGo")
        await dash.wait_for_function("document.querySelector('#instNext').innerText.includes('Submit the installation')")
        g = sup.get(f"/api/filing/{D}").json()
        check("Retry reopens the rejected step: next is submitting the installation again", g["next"]["act"] == "installation")
        sup.post(f"/api/filing/{A}/mark", json={"step": "installation"}).raise_for_status()
        check("an installation Solara has filed but the portal still shows pending is flagged",
              any("went through" in x for x in sup.get(f"/api/tracker/{A}").json()["problems"]))
        audit = {(a["action"], a["target"]) for a in sup.get("/api/audit").json()}
        check("every control is in the audit trail", {("Paused customer", A), ("Resumed customer", A),
              ("Reopened: Installation on PM Surya Ghar", D), ("Approved what will be filed: Installation on PM Surya Ghar", A)} <= audit)
        await fx_shot(dash, "m3-controls")

        # ---------------- monthly report ----------------
        print("\n  -- monthly report")
        await dash.click('.navitem[data-view="today"]')
        await dash.wait_for_selector("#monthXlsx")
        async with ctx.expect_event("request", lambda r: "/api/exports/month.xlsx" in r.url) as req:
            await dash.click("#monthXlsx")
        check("one click on Today asks for the month's workbook", MONTH in (await req.value).url)
        x = sup.get("/api/exports/month.xlsx", params={"month": MONTH})
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(x.content))
        cust = [r for r in wb["Customers"].iter_rows(min_row=2, values_only=True)]
        check("the workbook has every customer with stage and portal status", {c for c in want} <= {r[0] for r in cust} and
              all(r[5] for r in cust), f"{len(cust)} rows")
        filed = list(wb[f"Filed {MONTH}"].iter_rows(min_row=2, values_only=True))
        check("and every step filed this month, with its time", any(r[1] == B and r[3] == "Installation filed" for r in filed), f"{len(filed)} rows")
        check("and the month's audit trail", wb["Audit"].max_row > 5)
        pdf = sup.get("/api/exports/month.pdf", params={"month": MONTH})
        check("the PDF summary comes out too", pdf.status_code == 200 and pdf.content.startswith(b"%PDF"))
        check("a month that is not a month is refused", sup.get("/api/exports/month.xlsx", params={"month": "2026-13"}).status_code == 400)
        check("no script errors on the dashboard", not errors, "; ".join(errors[:3]))
        await ctx.close()

    print("\n  reset:", sup.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


async def fx_shot(pg, name):
    import os
    from pathlib import Path
    if os.environ.get("SOLARA_SHOTS"):
        d = Path(os.environ["SOLARA_SHOTS"]); d.mkdir(parents=True, exist_ok=True)
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(d / f"{name}.png"), full_page=True)


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
