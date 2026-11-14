"""Milestone 1 acceptance test (KPI K1): a new customer's documents -> registered on the
national portal -> accepted in the vendor login -> vendor agreement e-signed and uploaded.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/milestone1.py                     (in another)

One browser with the co-pilot extension loaded plays the owner: they add the customer, drop in
the documents, confirm the one flagged detail, and on the portals they only press buttons, type
the OTP and the CAPTCHA, and tick the declaration. Everything else is filled by Solara. The
failure paths that matter (unreadable documents, wrong formats, steps out of order, the
co-pilot touching OTP fields or overwriting typing) are checked too. Resets the demo first
and again at the end. Synthetic data only.
"""
import asyncio, base64, io, json, os, re, sys, tempfile, time
from pathlib import Path
import httpx
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db  # noqa: E402
import fixtures as fx  # noqa: E402

BASE = "http://127.0.0.1:8900"
EXT = Path(__file__).resolve().parent.parent / "extension"
PASS, FAIL = [], []
SHOTS = Path(os.environ["SOLARA_SHOTS"]) if os.environ.get("SOLARA_SHOTS") else None  # set to save screenshots


async def shot(pg, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        await pg.wait_for_timeout(500)  # let the view's fade-in finish
        await pg.screenshot(path=str(SHOTS / f"m1-{name}.png"))


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def client(user):
    c = httpx.Client(base_url=BASE, timeout=120, follow_redirects=True)
    c.post("/api/login", json={"username": user, "password": "demo"}).raise_for_status()
    return c


def drawn():
    im = Image.new("RGBA", (420, 140), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(20, 90), (80, 30), (130, 100), (190, 40), (260, 95), (390, 50)],
                            fill=(10, 20, 60, 255), width=4)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def customer_signs(url, digits):
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        pub.post(url + "/verify", data={"digits": digits})
        return pub.post(url, data={"approve": ["agreement"], "name": fx.AADHAAR_NAME,
                                   "consent": "yes", "signature": drawn()}).text


async def panel_text(pg):
    await pg.wait_for_selector("#solaraPanel", timeout=20000)
    return await pg.inner_text("#solaraPanel")


async def main():
    sup = client("r.deshmukh")
    print("  reset:", sup.post("/api/demo/reset").json()["runnable"])
    if not db.one("SELECT 1 FROM signatures WHERE role='vendor'"):
        sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"}).raise_for_status()
    fx.register_consumer()
    key = sup.post("/api/copilot/key").json()["key"]
    tmp = Path(tempfile.mkdtemp())

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        (tmp / "bill.pdf").write_bytes(await fx.bill_pdf(pg))
        await b.close()
    (tmp / "image.jpg").write_bytes(fx.aadhaar_photo())
    (tmp / "passbook.jpg").write_bytes(fx.passbook_photo())
    (tmp / "roof.jpg").write_bytes(fx.passbook_photo())

    # ---------------- the API's guard rails ----------------
    print("\n  -- guard rails")
    viewer = client("a.more")
    check("a viewer cannot add a customer", viewer.post("/api/customers", json={"name": "X Y"}).status_code == 403)
    check("a customer needs a name", sup.post("/api/customers", json={"name": " "}).status_code == 400)
    t = sup.post("/api/customers", json={"name": "Edge Case Test"}).json()["customer"]["id"]
    r = sup.post(f"/api/registration/{t}/document", params={"kind": "aadhaar"},
                 files={"file": ("a.jpg", fx.aadhaar_photo(qr=False), "image/jpeg")}).json()
    un = next((f for f in r["fields"] if f["key"] == "aadhaar_unread"), None)
    check("an Aadhaar photo without a readable QR is flagged, not guessed",
          un and un["status"] == "review" and "QR" in un["note"], un and un["note"][:70])
    r = sup.post(f"/api/registration/{t}/confirm", json={"key": "aadhaar_unread", "value": ""})
    check("confirming a flag needs the value", r.status_code == 400)
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(200, 200); w.encrypt("KULK1981")
    buf = io.BytesIO(); w.write(buf)
    r = sup.post(f"/api/registration/{t}/document", params={"kind": "aadhaar"},
                 files={"file": ("eaadhaar.pdf", buf.getvalue(), "application/pdf")}).json()
    un = next((f for f in r["fields"] if f["key"] == "aadhaar_unread"), {})
    check("a password-protected e-Aadhaar PDF gets a clear instruction", "password" in un.get("note", ""), un.get("note", "")[:70])
    r = sup.post(f"/api/registration/{t}/document", params={"kind": "bill"},
                 files={"file": ("x.txt", b"hello", "text/plain")}).json()
    un = next((f for f in r["fields"] if f["key"] == "bill_unread"), {})
    check("a file that is not a PDF or photo is explained", "JPG, PNG or PDF" in un.get("note", ""), un.get("note", "")[:70])
    check("unknown document type refused",
          sup.post(f"/api/registration/{t}/document", params={"kind": "selfie"},
                   files={"file": ("a.jpg", b"x", "image/jpeg")}).status_code == 400)
    for body, why in [({"mobile": "12345"}, "short mobile"), ({"kw": "abc"}, "capacity not a number"),
                      ({"kw": "40"}, "capacity above residential"), ({"consumer_no": "123"}, "short consumer number")]:
        check(f"details refuse a {why}", sup.put(f"/api/registration/{t}", json=body).status_code == 400)
    check("accepted cannot be marked before registration",
          sup.post(f"/api/registration/{t}/mark", json={"step": "accepted"}).status_code == 400)
    check("an application number must look like NP-…",
          sup.post(f"/api/registration/{t}/mark", json={"step": "registered", "app_no": "12345"}).status_code == 400)
    check("agreement upload cannot be marked before it is signed",
          sup.post(f"/api/registration/{t}/mark", json={"step": "agreement_uploaded"}).status_code == 400)
    sup.post("/api/demo/reset")
    fx.register_consumer()
    if not db.one("SELECT 1 FROM signatures WHERE role='vendor'"):
        sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"})
    key = sup.post("/api/copilot/key").json()["key"]

    # ---------------- the owner's run ----------------
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", headless=True, viewport={"width": 1440, "height": 900},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{key}'}})")
        errors = []
        dash = ctx.pages[0] if ctx.pages else await ctx.new_page()
        dash.on("pageerror", lambda ex: errors.append(str(ex)))
        t0 = time.time()

        print("\n  -- 1. documents in Solara")
        await dash.goto(BASE)
        await dash.click('[data-as="r.deshmukh"]')
        await dash.wait_for_selector("#shell:not([hidden])")
        await dash.click('.navitem[data-view="reg"]')
        await dash.click("#regNew")
        await dash.fill("#nName", "Priya Kulkarni")
        await dash.click("#regCreate")
        await dash.wait_for_function("document.querySelector('#regNext') && document.querySelector('#regNext').innerText.includes('Upload the bill')")
        cid = db.one("SELECT id FROM customers ORDER BY rowid DESC")["id"]
        check("new customer added from one name; next step is the documents", True, cid)
        for kind, f in (("bill", "bill.pdf"), ("aadhaar", "image.jpg"), ("passbook", "passbook.jpg"), ("roof", "roof.jpg")):
            await dash.set_input_files(f'input[data-doc="{kind}"]', str(tmp / f))
            await dash.wait_for_function(f"""(r => r.innerText.includes(' KB') && !r.querySelector('.pill.live'))(
                document.querySelector('input[data-doc="{kind}"]').closest('.docrow'))""", timeout=60000)
        g = sup.get(f"/api/registration/{cid}").json()
        f = {x["key"]: x for x in g["fields"]}
        check("consumer number read from the bill", f["consumer_no"]["value"] == fx.NEW["consumer_no"])
        check("Aadhaar name read from the QR, offline", f["aadhaar_name"]["value"] == fx.AADHAAR_NAME
              and f["aadhaar_name"]["source"] == "Aadhaar QR")
        check("only the last 4 Aadhaar digits are kept", f["aadhaar_masked"]["value"] == "XXXX XXXX 4471")
        check("district and address come from the QR", f["aadhaar_district"]["value"] == "Pune")
        check("mobile and sanctioned load filled into the record",
              g["data"].get("mobile") == fx.NEW["msisdn"] and float(g["data"].get("sanctioned_load")) == 5)
        check("the bill-vs-Aadhaar name difference is the one thing flagged",
              [x["key"] for x in g["fields"] if x["status"] == "review" and x["key"] not in
               ("account_holder", "account_no", "ifsc", "passbook_unread")] == ["bill_name"])
        check("the unread bank page does not block registration (needed later)",
              "Check 1 highlighted" in await dash.inner_text("#regNext"))
        await shot(dash, "1-documents-read")
        await dash.click("#regNext")
        await dash.click('[data-confirm="bill_name"]')                       # owner confirms the bill spelling
        await dash.wait_for_function("!document.querySelector('[data-confirm]')")
        await dash.fill('[data-r="kw"]', "3")                                # from the customer's order
        await dash.fill('[data-r="rts_cost"]', "210000")
        await dash.fill('[data-r="email"]', "priya.k@example.com")                # the portal verifies it by OTP
        await dash.click("#regSave")
        await dash.wait_for_function("document.querySelector('#regNext').innerText.includes('Register')")
        check("after the check and the order details, the next step is registering", True)
        check("the name to file is the bill spelling",
              sup.get(f"/api/registration/{cid}").json()["values"]["name"] == fx.NEW["billed_name"])

        print("\n  -- 2. registration on the portal (co-pilot)")
        reg = await ctx.new_page()
        await reg.goto(BASE + "/portal/verify")
        await reg.wait_for_selector("#solaraPanel [data-pick]", timeout=20000)
        check("on a blank form the co-pilot offers the customers waiting to register",
              fx.NEW["billed_name"] in await reg.inner_text("#solaraPanel"))
        await reg.click(f'#solaraPanel [data-pick="{cid}"]')
        await reg.click("#solaraStart")   # picking names the customer; Start begins the run and fills by itself
        await reg.wait_for_selector("#solaraFilled")
        check("after Start the phone page filled by itself (no Fill click)", True)
        await sw.evaluate("chrome.storage.local.remove('run')")   # the rest of this test drives Fill by hand
        await shot(reg, "2-portal-filled")
        check("verify page: state, company, consumer number, mobile filled",
              await reg.input_value("#consumerNo") == fx.NEW["consumer_no"] and
              await reg.input_value("#mobile") == fx.NEW["msisdn"] and
              await reg.input_value("#state") == "Maharashtra", await reg.get_attribute("#solaraPanel", "data-filled"))
        await reg.click("#btnSendOtp")                                       # owner
        await reg.wait_for_url("**/portal/otp")
        await reg.wait_for_timeout(1200)
        check("the co-pilot leaves the OTP box alone", await reg.input_value("#otp") == "")
        otp = db.one("SELECT otp FROM portal_sessions ORDER BY rowid DESC")["otp"]
        await reg.fill("#otp", otp)                                          # owner types the OTP from the call
        await reg.click("#btnVerify")
        await reg.wait_for_url("**/portal/form")
        await reg.wait_for_selector("#solaraFill", timeout=20000)
        check("the co-pilot remembers the customer on the next page", fx.NEW["billed_name"] in await panel_text(reg))
        await reg.fill("#roofArea", "40")                                    # owner had typed this already
        await reg.click("#solaraFill")
        await reg.wait_for_selector("#solaraFilled")
        vals = {k: await reg.input_value(sel) for k, sel in (("name", "#applicantName"), ("addr", "#address"),
                ("pin", "#pin"), ("cap", "#capacity"), ("load", "#load"), ("cat", "#category"), ("roof", "#roofArea"))}
        check("application form filled from the record", vals["name"] == fx.NEW["billed_name"] and vals["pin"] == "410503"
              and vals["cap"] == "3" and float(vals["load"]) == 5 and vals["cat"] == "Residential", str(vals))
        check("what the owner typed is never overwritten", vals["roof"] == "40")
        check("the panel says what is left for the owner", "Module" in await reg.inner_text("#solaraFilled") or
              "module" in (await reg.inner_text("#solaraFilled")).lower())
        await reg.select_option("#moduleType", "Mono PERC (DCR)")            # owner (sandbox-only field)
        await reg.click("#btnSaveContinue")
        await reg.wait_for_url("**/portal/docs")
        await reg.wait_for_selector("#solaraFill", timeout=20000)
        await reg.click("#solaraFill")
        await reg.wait_for_selector("#solaraFilled")
        n = await reg.evaluate("[...document.querySelectorAll('input[type=file]')].filter(i => i.files.length).length")
        check("the customer's four documents attached to the portal's upload boxes", n == 4, str(n))
        await reg.click("#btnUpload")
        await reg.wait_for_url("**/portal/security")
        cap = db.one("SELECT captcha FROM portal_sessions ORDER BY rowid DESC")["captcha"]
        await reg.wait_for_timeout(800)
        await reg.fill("input[name=code]", cap)                              # owner types the CAPTCHA
        await reg.click("form button[type=submit]")
        await reg.wait_for_url("**/portal/review")
        await reg.check("#declaration")                                       # owner's own declaration
        await reg.click("#btnSubmit")
        await reg.wait_for_url("**/portal/ack")
        app_no = (await reg.inner_text("#applicationNo")).strip()
        await reg.wait_for_selector("#solaraPanel :text('saved in Solara')", timeout=20000)
        c = db.one("SELECT application_no, stage FROM customers WHERE id=?", (cid,))
        check("the application number is saved in Solara from the portal page, untyped",
              c["application_no"] == app_no and app_no.startswith("NP-MHSED"), app_no)
        filed = db.one("SELECT * FROM portal_applications WHERE application_no=?", (app_no,))
        check("the portal accepted the application under the bill name",
              filed and filed["applicant_name"] == fx.NEW["billed_name"])

        print("\n  -- 3. accepted in the vendor login")
        ven = await ctx.new_page()
        await ven.goto(BASE + "/pmsg/vendor/consent")
        await ven.click(f"form[action$='{app_no}'] button")                   # owner approves
        await dash.bring_to_front()
        await dash.click(f'[data-reg="{cid}"]')
        await dash.wait_for_function("document.querySelector('#regNext').innerText.includes('Vendor Consent')")
        await dash.click("#regNext")
        await dash.click("#regAcceptedModal")
        await dash.wait_for_function("document.querySelector('#regNext').innerText.includes('Send the agreement')")
        check("marked accepted; the next step is the agreement", True)
        elapsed = sup.get(f"/api/registration/{cid}").json()["elapsed_to_accepted"]
        check("documents to accepted is timed", elapsed is not None and elapsed < 300, f"{elapsed}s in this run")

        print("\n  -- 4. agreement e-signed and uploaded")
        await dash.click("#regNext")
        await dash.wait_for_selector("#signUrl")
        url = await dash.input_value("#signUrl")
        wa = await dash.get_attribute("a:has-text('Send on WhatsApp')", "href")
        check("the agreement link goes to the customer's own WhatsApp number", wa.startswith("https://wa.me/91" + fx.NEW["msisdn"]))
        await dash.keyboard.press("Escape")
        check("the customer signs the agreement on their phone", "signed" in customer_signs(url, fx.NEW["consumer_no"][-4:]))
        await dash.click(f'[data-reg="{cid}"]')
        await dash.wait_for_function("document.querySelector('#regNext').innerText.includes('Upload the agreement')")
        await ven.goto(BASE + f"/pmsg/vendor/agreement?app={app_no}")
        await ven.wait_for_selector("#solaraFill", timeout=30000)
        check("in the Upload Agreement dialog the co-pilot finds the right customer behind the list",
              fx.NEW["billed_name"] in await ven.inner_text("#solaraPanel"))
        await ven.click("#solaraFill")
        await ven.wait_for_selector("#solaraFilled")
        await shot(ven, "3-agreement-attached")
        check("cost filled and the signed agreement attached",
              await ven.input_value("#cost") == "210000" and
              await ven.evaluate("document.querySelector('#agreementCopy').files.length") == 1)
        await ven.click("#btnSubmitAgreement")                               # owner
        await ven.wait_for_selector("text=Agreement updated successfully")
        up = db.one("SELECT * FROM pmsg_vendor WHERE application_no=?", (app_no,))
        check("the portal received the agreement as a PDF under 2 MB with the cost",
              up["cost"] == "210000" and up["agreement_file"].endswith(".pdf") and up["agreement_bytes"] < 2 * 1024 * 1024,
              f"{up['agreement_file']} {up['agreement_bytes'] // 1024} KB")
        await ven.wait_for_selector("#solaraMarkUploaded", timeout=20000)
        await ven.click("#solaraMarkUploaded")
        await ven.wait_for_selector("#solaraPanel :text('Saved in Solara')")
        await dash.bring_to_front()
        await dash.click(f'[data-reg="{cid}"]')
        # the customer approves it in their own login; marked here from the dashboard
        await dash.wait_for_function("document.querySelector('#regNext').innerText.includes('Approve the agreement')")
        await dash.click("#regApproved")
        await dash.wait_for_function("document.querySelector('#regNext').innerText.includes('Milestone 1 done')")
        await shot(dash, "4-milestone-done")
        g = sup.get(f"/api/registration/{cid}").json()
        check("all seven steps done for this customer", all(s["done"] for s in g["steps"]),
              str([(s["key"], s["done"]) for s in g["steps"]]))
        check("no JavaScript errors in the dashboard", not errors, "; ".join(errors[:2]))
        print(f"  (whole run, automated: {time.time() - t0:.0f}s)")
        await ctx.close()

    audit = [a["action"] for a in db.q("SELECT action FROM audit WHERE target=?", (cid,))]
    check("the audit trail records each step", all(a in audit for a in (
        "Added customer", "Document extraction", "Confirmed extracted field", "Marked registered",
        "Marked accepted", "Sent documents for e-signature", "Customer e-signed documents",
        "Marked agreement uploaded", "Marked customer approved")), ", ".join(sorted(set(audit))))
    print("\n  reset:", client("r.deshmukh").post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("   failed:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
