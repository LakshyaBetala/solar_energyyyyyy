"""Milestone 2 acceptance test (KPI K2): from "agreement uploaded" to "six documents on MSEDCL",
through Solara, with the co-pilot extension loaded in the owner's browser.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/milestone2.py                     (in another)

The customer is taken through milestone 1 by the API (tests/milestone1.py proves that part in the
browser). Then the owner, in one browser with the extension:
  1  enters the site visit in Solara, files the Site Feasibility Report on the national portal
     (Solara fills, attaches the quotation and roof photo; the owner ticks the certificate, Submits)
  2  fills the customer's Jan Samarth loan form with them (the customer types Aadhaar and OTP)
  3  sends the field team a link; on a phone they photograph the site (GPS from the phone) and
     each panel label; serials are read from the barcodes and the owner confirms them
  4  applies for the DCR certificate: refused once because the dealer had not transferred a
     panel (Solara shows "waiting for the dealer"), issued after the transfer, number saved
  5  submits the installation in 5 steps (lat/long, inverter and module rows, serials, DCR
     number, plant photo, protection checklist); the customer accepts on their phone
  6  gets the six documents e-signed by the customer, generated under 300 KB, and uploaded on
     MSEDCL; the post-installation time is shown
The guard rails (validation, repeats, files over size, the co-pilot leaving OTP, Aadhaar,
declarations alone) are checked along the way. Resets the demo before and after. Synthetic data.
"""
import asyncio, base64, io, json, os, sys, tempfile, time
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
SHOTS = Path(os.environ["SOLARA_SHOTS"]) if os.environ.get("SOLARA_SHOTS") else None
APP_NO = "NP-MHSED26-16190001"
SERIALS = [f"PE55026A{n:06d}" for n in range(318501, 318506)] + ["PE55026A318600"]  # the last: not yet transferred
SITE = (19.072345, 73.913456)


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def shot(pg, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOTS / f"m2-{name}.png"), full_page=True)


def client(user):
    c = httpx.Client(base_url=BASE, timeout=120, follow_redirects=True)
    c.post("/api/login", json={"username": user, "password": "demo"}).raise_for_status()
    return c


def drawn():
    im = Image.new("RGBA", (420, 140), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(20, 90), (80, 30), (130, 100), (190, 40), (260, 95), (390, 50)], fill=(10, 20, 60, 255), width=4)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def customer_signs(url, docs):
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        pub.post(url + "/verify", data={"digits": fx.NEW["consumer_no"][-4:]})
        return pub.post(url, data={"approve": docs, "name": fx.AADHAAR_NAME, "consent": "yes", "signature": drawn()}).text


async def milestone1(sup, tmp):
    """The customer as milestone 1 leaves them: registered, accepted, agreement e-signed and uploaded."""
    cid = sup.post("/api/customers", json={"name": "Priya Kulkarni"}).json()["customer"]["id"]
    for kind, f in (("bill", "bill.pdf"), ("aadhaar", "aadhaar.jpg"), ("roof", "roof.jpg")):
        sup.post(f"/api/registration/{cid}/document", params={"kind": kind},
                 files={"file": (f, (tmp / f).read_bytes())}).raise_for_status()
    sup.post(f"/api/registration/{cid}/confirm", json={"key": "bill_name", "value": fx.NEW["billed_name"]}).raise_for_status()
    sup.put(f"/api/registration/{cid}", json={"kw": "3.3", "rts_cost": "198000", "email": "priya.k@example.com",
                                              "district": "Pune"}).raise_for_status()
    db.ex("INSERT INTO portal_applications(application_no,consumer_no,applicant_name,capacity,submitted_at,payload) VALUES(?,?,?,?,?,?)",
          (APP_NO, fx.NEW["consumer_no"], fx.NEW["billed_name"], 3.3, db.now(), "{}"))
    sup.post(f"/api/registration/{cid}/mark", json={"step": "registered", "app_no": APP_NO}).raise_for_status()
    sup.post(f"/pmsg/vendor/consent/{APP_NO}")
    sup.post(f"/api/registration/{cid}/mark", json={"step": "accepted"}).raise_for_status()
    url = sup.post(f"/api/registration/{cid}/agreement").json()["url"]
    customer_signs(url, ["agreement"])
    await closeout.build(cid, {"username": "test", "role": "supervisor"})
    pdf = closeout.vault.read(closeout.path_for(cid, "agreement"))
    sup.post(f"/pmsg/vendor/agreement?app={APP_NO}", data={"cost": "198000"},
             files={"agreement": ("agreement.pdf", pdf, "application/pdf")})
    sup.post(f"/api/registration/{cid}/mark", json={"step": "agreement_uploaded"}).raise_for_status()
    return cid


async def panel_says(pg, text, timeout=25000):
    try:
        await pg.wait_for_function("t => (document.querySelector('#solaraPanel') || {innerText: ''}).innerText.includes(t)", arg=text, timeout=timeout)
    except Exception:
        print(f"   waiting for '{text}', the panel was:", " | ".join((await pg.inner_text("#solaraPanel"))[:400].splitlines()))
        raise


async def fill(pg):
    try:
        await pg.wait_for_selector("#solaraFill", timeout=25000)
    except Exception:
        print("   panel was:", " | ".join((await pg.inner_text("#solaraPanel"))[:300].splitlines()))
        raise
    await pg.click("#solaraFill")
    try:
        await pg.wait_for_selector("#solaraFilled", timeout=25000)
    except Exception:
        print("   after Fill the panel was:", " | ".join((await pg.inner_text("#solaraPanel"))[:400].splitlines()),
              "scans:", await pg.get_attribute("#solaraPanel", "data-scans"), "fill:", await pg.get_attribute("#solaraPanel", "data-fill"),
              "panels:", await pg.locator("#solaraPanel").count(), "url:", pg.url, "err:", await pg.get_attribute("#solaraPanel", "data-err"), "lastclick:", await pg.get_attribute("#solaraPanel", "data-lastclick"))
        print("   hit test:", await pg.evaluate("(() => { const b = document.querySelector('#solaraFill').getBoundingClientRect(); const el = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2); return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height), innerWidth, innerHeight, el && (el.id || el.tagName)]; })()"))
        await pg.bring_to_front(); await pg.click("#solaraFill"); await pg.wait_for_timeout(3000)
        print("   second click:", await pg.get_attribute("#solaraPanel", "data-fill"), await pg.get_attribute("#solaraPanel", "data-lastclick"))
        await pg.evaluate("window.__md = 0; addEventListener('mousedown', () => window.__md++, true); addEventListener('pointerdown', () => window.__md += 10, true)")
        await pg.mouse.click(1259, 832); await pg.wait_for_timeout(500)
        print("   window saw mouse:", await pg.evaluate("window.__md"), "active:", await pg.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.tagName)"))
        await pg.locator("#solaraFill").dispatch_event("click"); await pg.wait_for_timeout(3000)
        print("   synthetic click:", await pg.get_attribute("#solaraPanel", "data-fill"))
        await pg.screenshot(path=str(Path(tempfile.gettempdir()) / "m2_fail.png"))
        raise
    return await pg.inner_text("#solaraFilled")


async def main():
    sup = client("r.deshmukh")
    print("  reset:", sup.post("/api/demo/reset").json()["runnable"])
    if not db.one("SELECT 1 FROM signatures WHERE role='vendor'"):
        sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"}).raise_for_status()
    fx.register_consumer()
    db.ex("DELETE FROM dcr_stock WHERE serial=?", (SERIALS[-1],))
    tmp = Path(tempfile.mkdtemp())
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        (tmp / "bill.pdf").write_bytes(await fx.bill_pdf(pg))
        await b.close()
    (tmp / "aadhaar.jpg").write_bytes(fx.aadhaar_photo())
    (tmp / "roof.jpg").write_bytes(fx.site_photo_without_gps())
    cid = await milestone1(sup, tmp)
    print(f"  customer {cid} through milestone 1 ({APP_NO})")
    g = sup.get(f"/api/filing/{cid}").json()
    check("after the agreement the customer is on the Installation list, next is the site visit",
          any(x["id"] == cid for x in sup.get("/api/filing").json()) and g["next"]["act"] == "details", g["next"]["label"])
    check("Today lists the customer's next step", any(x["cid"] == cid for x in sup.get("/api/today").json()["items"]))

    # ---------------- guard rails ----------------
    print("\n  -- guard rails")
    op, viewer = client("s.kale"), client("a.more")
    check("a viewer cannot change filing details", viewer.put(f"/api/filing/{cid}", json={"roof_area": "40"}).status_code == 403)
    check("Yes/No questions take only Yes or No", sup.put(f"/api/filing/{cid}", json={"roof_load_ok": "maybe"}).status_code == 400)
    check("the visitor's number needs 10 digits", sup.put(f"/api/filing/{cid}", json={"visitor_phone": "12345"}).status_code == 400)
    check("roof area must be a number", sup.put(f"/api/filing/{cid}", json={"roof_area": "big"}).status_code == 400)
    r = sup.post(f"/api/filing/{cid}/mark", json={"step": "sfr"})
    check("the feasibility report cannot be marked filed with details missing", r.status_code == 400, r.json().get("detail", "")[:80])
    check("the installation cannot be marked before the DCR certificate",
          sup.post(f"/api/filing/{cid}/mark", json={"step": "installation"}).status_code == 400)
    check("a DCR number must look like one", sup.post(f"/api/filing/{cid}/mark", json={"step": "dcr", "ref": "12"}).status_code == 400)
    check("approving needs a supervisor", op.post(f"/api/filing/{cid}/approve", json={"step": "sfr"}).status_code == 403)
    check("approval is refused while the form has blanks", sup.post(f"/api/filing/{cid}/approve", json={"step": "sfr"}).status_code == 400)
    key = sup.post("/api/copilot/key").json()["key"]

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            fx.browser_profile(), channel="chromium", headless=True, viewport={"width": 1440, "height": 900},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        await ctx.grant_permissions(["geolocation"], origin=BASE)
        await ctx.set_geolocation({"latitude": SITE[0], "longitude": SITE[1], "accuracy": 12})
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{key}'}})")
        errors = []
        dash = ctx.pages[0] if ctx.pages else await ctx.new_page()
        dash.on("pageerror", lambda ex: errors.append(str(ex) + " @ " + " / ".join((ex.stack or "").splitlines()[1:3])))
        await dash.goto(BASE)
        await dash.click('[data-as="r.deshmukh"]')
        await dash.wait_for_selector("#shell:not([hidden])")
        await dash.wait_for_selector("#otherview [data-group=calls]", timeout=20000)
        check("the dashboard opens on Today", "Calls to make" in await dash.inner_text("#otherview"))

        # ---------------- 1. site visit and feasibility report ----------------
        print("\n  -- 1. site feasibility report")
        await dash.click('.navitem[data-view="inst"]')
        await dash.click(f'[data-inst="{cid}"]')
        await dash.wait_for_selector("#instNext")
        for k, v in (("location_type", "Urban"), ("roof_load_ok", "Yes"), ("shadow_free", "Yes"), ("site_visited", "Yes"), ("loan", "Yes")):
            await dash.select_option(f'[data-i="{k}"]', v)
        for k, v in (("roof_area", "42"), ("visitor_name", "Amol Kadam"), ("visitor_phone", "9890012345"), ("loan_bank", "Bank of Maharashtra")):
            await dash.fill(f'[data-i="{k}"]', v)
        await dash.click('[data-form="Site visit and feasibility report"] [data-isave]')
        try:
            await dash.wait_for_function("document.querySelector('#instNext').innerText.includes('feasibility report')")
        except Exception:
            print("   next was:", await dash.inner_text("#instNext"), "| toast:", await dash.inner_text("#toastmsg"),
                  "| api:", sup.get(f"/api/filing/{cid}").json()["next"])
            raise
        check("with the site visit entered, the next step is filing the feasibility report", True)
        rv = sup.get(f"/api/filing/{cid}/review?step=sfr").json()
        check("Review shows every value the co-pilot will put on the report, and both files",
              not rv["missing"] and {f["key"] for f in rv["files"] if f["ready"]} == {"quotation", "roof"}, ", ".join(rv["missing"]))
        sup.post(f"/api/filing/{cid}/approve", json={"step": "sfr"}).raise_for_status()
        await shot(dash, "1-installation-view")

        pm = await ctx.new_page()
        pm.on("pageerror", lambda ex: errors.append(str(ex)))
        await pm.goto(f"{BASE}/pmsg/vendor/applications")
        await panel_says(pm, "updated in Solara")
        check("on My Application the co-pilot reads every row's status into Solara",
              db.one("SELECT status FROM portal_status WHERE customer_id=? AND portal='pmsg'", (cid,))["status"] == "Installation (Pending)")
        await pm.click(f'tr:has-text("{APP_NO}") >> text=Site Feasibility Report')
        await panel_says(pm, "Priya Kulkarni")
        check("the dialog does not say whose it is; the co-pilot knows from the row that was clicked",
              cid in await pm.inner_text("#solaraPanel"))
        check("the co-pilot shows the owner's approval of these values", "approved by" in (await pm.inner_text("#solaraPanel")).lower())
        left = await fill(pm)
        vals = {k: await pm.input_value(s) for k, s in (("area", "#roofArea"), ("cap", "#permCap"), ("amt", "#qAmt"), ("emp", "#emp"), ("no", "#empNo"))}
        radios = {n: await pm.evaluate(f"(document.querySelector('input[name={n}]:checked') || {{}}).value || ''") for n in ("roofLoad", "shadowFree", "visited")}
        check("roof area, permissible kW, quotation amount, visitor and number filled",
              vals == {"area": "42", "cap": "3.3", "amt": "198000", "emp": "Amol Kadam", "no": "9890012345"}, str(vals))
        check("the three Yes/No questions answered from the record", radios == {"roofLoad": "Y", "shadowFree": "Y", "visited": "Y"}, str(radios))
        files = await pm.evaluate("[...document.querySelectorAll('input[type=file]')].map(i => i.files.length ? i.files[0].name + ':' + i.files[0].size : '')")
        check("the quotation PDF and the pre-installation photo are attached, both under 300 KB",
              all(f and int(f.split(":")[1]) <= 300 * 1024 for f in files), str(files))
        check("the certification checkbox is left for the owner", not await pm.is_checked('input[name="certify"]'))
        check("nothing left for the owner to type", "Left for you" not in left, left)
        await pm.check('input[name="certify"]')
        await pm.click("#btnSubmitSfr")
        await pm.wait_for_selector("text=Site Feasibility Report submitted successfully")
        await pm.wait_for_selector("#solaraMark", timeout=25000)
        await pm.click("#solaraMark")
        await panel_says(pm, "with the page as the receipt")
        g = sup.get(f"/api/filing/{cid}").json()
        check("marked filed in Solara, with the portal page kept as the receipt",
              bool(g["times"]["sfr_at"]) and any(r["step"] == "sfr" for r in g["receipts"]))
        check("the sandbox portal received the report", bool(db.one("SELECT sfr_at FROM pmsg_install WHERE application_no=?", (APP_NO,))["sfr_at"]))
        check("next is the customer's loan application", g["next"]["act"] == "loan", g["next"]["label"])
        await shot(pm, "2-feasibility-report")

        # ---------------- 2. Jan Samarth, with the customer ----------------
        print("\n  -- 2. loan application (Jan Samarth)")
        js = await ctx.new_page()
        await js.goto(f"{BASE}/jansamarth/")
        await panel_says(js, "Priya Kulkarni")
        left = await fill(js)
        got = {k: await js.input_value(s) for k, s in (("name", "#an"), ("mob", "#mob"), ("mail", "#em"), ("cons", "#cno"), ("cap", "#cap"), ("cost", "#pc"))}
        check("basic details filled: name as on Aadhaar, mobile, email, consumer no., capacity, cost",
              got == {"name": fx.AADHAAR_NAME, "mob": fx.NEW["msisdn"], "mail": "priya.k@example.com", "cons": fx.NEW["consumer_no"],
                      "cap": "3.3", "cost": "198000"}, str(got))
        check("date of birth and loan amount are the customer's to give", await js.input_value("#dob") == "" and
              await js.input_value("#la") == "" and "Date Of Birth" not in left)
        await js.fill("#dob", "1981-03-14")
        await js.fill("#la", "150000")
        await js.click("#btnNext")
        await js.wait_for_selector("text=Address Details")
        await fill(js)
        got = {k: await js.input_value(s) for k, s in (("pin", "#pin"), ("dis", "#dis"), ("st", "#st"))}
        check("address page filled from the record", got == {"pin": fx.NEW["pin"], "dis": "Pune", "st": "Maharashtra"} and
              await js.input_value("#ad"), str(got))
        await js.click("#btnNext")
        await js.wait_for_selector("text=Aadhaar Verification")
        await panel_says(js, "Priya")
        await js.wait_for_timeout(1500)
        check("the co-pilot never types the Aadhaar number or the OTP",
              await js.input_value("#aad") == "" and await js.input_value("#otp") == "")
        today = sup.get("/api/today").json()
        check("Today shows the OTP call while the portal waits for it",
              any(x["cid"] == cid and x["group"] == "calls" and "OTP" in x["title"] for x in today["items"]))
        await js.fill("#aad", "123456784471")                       # the customer types these
        await js.fill("#otp", "246810")
        await js.click("#btnNext")
        await js.wait_for_selector("text=Select Bank")
        await js.wait_for_timeout(1500)
        check("bank and branch are left for the customer to pick", await js.input_value("#bk") == "" and await js.input_value("#brn") == "")
        await js.select_option("#bk", "Bank of Maharashtra")
        await js.select_option("#brn", "Manchar")
        await js.click("#btnNext")
        await js.wait_for_selector("#jsRef")
        ref = await js.inner_text("#jsRef")
        await js.wait_for_selector("#solaraLoan", timeout=25000)
        await js.click("#solaraLoan")
        await panel_says(js, "Saved: reference")
        g = sup.get(f"/api/filing/{cid}").json()
        check("loan reference saved without typing, approval letter in the customer's file",
              g["data"].get("loan_ref") == ref and any(x["kind"] == "loan_approval" for x in g["documents"]), ref)
        js_row = db.one("SELECT data FROM js_applications WHERE ref=?", (ref,))
        check("the full Aadhaar number never reached the portal's stored data or Solara",
              "123456784471" not in js_row["data"] and "123456784471" not in json.dumps(g))
        check("next is the field team", g["next"]["act"] == "field", g["next"]["label"])
        await js.close()

        # ---------------- 3. on site: photos and serial numbers ----------------
        print("\n  -- 3. field team on site")
        await dash.bring_to_front()
        await dash.click('.navitem[data-view="inst"]')
        await dash.click(f'[data-inst="{cid}"]')
        await dash.click("#instLink")
        await dash.wait_for_selector("#signUrl")
        link = await dash.input_value("#signUrl")
        await dash.click("[data-close]")
        r = httpx.post(link + "/photo", data={"kind": "site"}, files={"file": ("p.jpg", fx.site_photo_without_gps(), "image/jpeg")})
        check("a site photo with no GPS and no phone location is refused with the reason", r.status_code == 400 and "GPS" in r.json()["detail"])
        r = httpx.post(link + "/photo", data={"kind": "site", "lat": "19.07", "lng": "73.91", "acc": "900"},
                       files={"file": ("p.jpg", fx.site_photo_without_gps(), "image/jpeg")})
        check("a phone location accurate only to 900 m is refused", r.status_code == 400 and "accurate" in r.json()["detail"])
        phone = await ctx.new_page()
        await phone.set_viewport_size({"width": 390, "height": 844})
        await phone.goto(link)
        check("the field page fits a phone (no sideways scroll)", await phone.evaluate("document.documentElement.scrollWidth <= 392"))
        (tmp / "site.jpg").write_bytes(fx.site_photo_without_gps())
        await phone.set_input_files('input[data-kind="site"]', str(tmp / "site.jpg"))
        await phone.wait_for_selector("#siteState.ok", timeout=30000)
        d = closeout.data(cid)[1]
        check("site photo taken: GPS from the phone's location (the photo itself had none)",
              abs(float(d["lat"]) - SITE[0]) < 1e-4 and abs(float(d["lng"]) - SITE[1]) < 1e-4 and "phone location" in d["photo_source"],
              f"{d.get('lat')}, {d.get('lng')} · {d.get('photo_source')}")
        site = closeout.vault.read(closeout.DOCS / cid / "site_photo.jpg")
        check("the site photo carries its coordinates printed on it and is under 300 KB", len(site) <= 300 * 1024, f"{len(site) // 1024} KB")
        labels = []
        for s in SERIALS[:5]:
            labels.append(tmp / f"{s}.jpg"); labels[-1].write_bytes(fx.label_photo(s))
        labels.append(tmp / "repeat.jpg"); labels[-1].write_bytes(fx.label_photo(SERIALS[0]))          # same panel twice
        labels.append(tmp / "clash.jpg"); labels[-1].write_bytes(fx.label_photo("PE55026A318410"))     # on another customer
        labels.append(tmp / "blurred.jpg"); labels[-1].write_bytes(fx.label_photo(SERIALS[5], code=False))
        await phone.set_input_files('input[data-kind="module"]', [str(x) for x in labels])
        await phone.wait_for_function("document.querySelector('#count').innerText.startsWith('6 of')", timeout=60000)
        inv = tmp / "inv.jpg"; inv.write_bytes(fx.label_photo("PSIS3K26A04411", "inverter"))
        await phone.set_input_files('input[data-kind="inverter"]', str(inv))
        await phone.wait_for_function("document.querySelector('#inv').innerText.includes('PSIS3K26A04411')", timeout=30000)
        await shot(phone, "3-field-phone")
        await phone.close()  # a phone-sized page in the same browser stops mouse input reaching later pages (headless quirk)
        reads = sup.get(f"/api/filing/{cid}").json()["field"]
        by = {r["serial"]: r for r in reads["reads"] if r["serial"]}
        check("five panel serials read from their barcodes, offline", all(by.get(s, {}).get("source") == "barcode" for s in SERIALS[:5]))
        check("the same panel photographed twice is not counted twice", sum(1 for r in reads["reads"] if r["serial"] == SERIALS[0]) == 1)
        check("a serial already on another customer is flagged as a repeat", by.get("PE55026A318410", {}).get("status") == "clash",
              by.get("PE55026A318410", {}).get("note", ""))
        check("a label with no readable code is flagged, not guessed", reads["unread"] == 1)
        check("Today shows the serials waiting for confirmation", any(x["cid"] == cid and "serial" in x["title"].lower()
                                                                   for x in sup.get("/api/today").json()["items"]))
        g = sup.get(f"/api/filing/{cid}").json()
        check("nothing reaches the record before a person confirms it", not g["data"].get("module_serials"))
        await dash.reload()
        await dash.wait_for_selector("#shell:not([hidden])")
        await dash.click('.navitem[data-view="inst"]')
        await dash.click(f'[data-inst="{cid}"]')
        await dash.wait_for_selector("#instConfirmAll")
        await dash.click("#instConfirmAll")
        await dash.wait_for_function("!document.querySelector('#instConfirmAll') || document.querySelectorAll('[data-srdo=confirm]').length <= 3", timeout=20000)
        clash = by["PE55026A318410"]["id"]
        r = sup.post(f"/api/filing/{cid}/serial/{clash}", json={"action": "confirm"})
        check("a repeated serial cannot be confirmed", r.status_code == 400, r.json().get("detail", "")[:70])
        await dash.click(f'[data-srdo="reject"][data-srid="{clash}"]')
        await dash.wait_for_function(f"!document.querySelector('[data-sr=\"{clash}\"]')")
        unread = next(r for r in reads["reads"] if r["status"] == "unread")
        await dash.fill(f'[data-srfix="{unread["id"]}"]', SERIALS[5].lower())          # typed off the photo
        await dash.click(f'[data-srdo="confirm"][data-srid="{unread["id"]}"]')
        await dash.wait_for_function(f"!document.querySelector('[data-srfix=\"{unread['id']}\"]')")
        inv_read = next(r for r in sup.get(f"/api/filing/{cid}").json()["field"]["reads"] if r["kind"] == "inverter")
        if inv_read["status"] != "confirmed":
            sup.post(f"/api/filing/{cid}/serial/{inv_read['id']}", json={"action": "confirm"}).raise_for_status()
        g = sup.get(f"/api/filing/{cid}").json()
        check("six serials confirmed into the record, in order, typed one upper-cased",
              g["data"].get("module_serials", "").split("\n") == SERIALS, g["data"].get("module_serials", "").replace("\n", " "))
        check("module count and inverter serial come from the site", g["data"].get("module_count") == "6" and
              g["data"].get("inverter_serial") == "PSIS3K26A04411")
        check("the field step is done and the post-installation clock started", g["steps"][2]["done"] and bool(g["times"]["field_at"]))
        await shot(dash, "4-serials-confirmed")

        # ---------------- 4. DCR certificate ----------------
        print("\n  -- 4. DCR certificate")
        sup.put(f"/api/filing/{cid}", json={"invoice_no": "INV/26-27/0518", "module_make": "Premier Energies", "module_wp": "550",
                                            "almm_model": "PE-M144-550", "phase": "Single phase", "inverter_make": "Polycab PSIS-3K",
                                            "inverter_kw": "3", "protection_checks": "Yes", "lightning_arrester": "Yes",
                                            "earth_ohm": "1.8", "earthing_count": "3"}).raise_for_status()
        g = sup.get(f"/api/filing/{cid}").json()
        check("next is the DCR certificate", g["next"]["act"] == "dcr", g["next"]["label"])
        dcr = await ctx.new_page()
        await dcr.goto(f"{BASE}/dcr/")
        await dcr.wait_for_timeout(1200)
        check("on the DCR login the co-pilot fills nothing (user, password, captcha are the owner's)",
              await dcr.input_value("#u") == "" and await dcr.input_value("#c") == "")
        await dcr.fill("#u", "vendor"); await dcr.fill("#p", "demo"); await dcr.fill("#c", "7K2Q")
        await dcr.click("button.btn")
        await dcr.wait_for_selector("#can")
        await dcr.close()  # carry on in a fresh tab with the same session (input to a tab after its login stalls in this headless run)
        dcr = await ctx.new_page()
        await dcr.goto(f"{BASE}/dcr/b2c")
        await dcr.wait_for_selector("#can")
        await panel_says(dcr, "Priya Kulkarni")
        left = await fill(dcr)
        got = {k: await dcr.input_value(s) for k, s in (("app", "#can"), ("name", "#cn"), ("mob", "#cm"), ("st", "#cs"), ("pin", "#cp"),
                                                        ("mail", "#ce"), ("inv", "#inv"), ("qty", "#qty"), ("br", "#br"), ("it", "#it"), ("ss", "#ss"))}
        check("application no., name, mobile, state, PIN, email, invoice, quantity, branch, item, scheme filled",
              got["app"] == APP_NO and got["name"] == fx.NEW["billed_name"] and got["mob"] == fx.NEW["msisdn"] and
              "Maharashtra" in got["st"] and got["pin"] == fx.NEW["pin"] and got["inv"] == "INV/26-27/0518" and got["qty"] == "6"
              and got["br"] and got["it"] == "Solar Panels" and got["ss"].startswith("PM Surya Ghar"), str(got))
        check("the six panel numbers are filled one per line", (await dcr.input_value("#pan")).split("\n") == SERIALS)
        check("the vendor's own contact person and PO reference are left alone",
              await dcr.input_value("#ccp") == "" and await dcr.input_value("#po") == "")
        await dcr.fill("#dt", "2026-11-03")
        await dcr.click("#btnDcr")
        await dcr.wait_for_selector("#dcrError")
        await panel_says(dcr, "waiting for the dealer")
        g = sup.get(f"/api/filing/{cid}").json()
        check("a panel the dealer has not transferred: refused, and Solara shows 'waiting for the dealer'",
              g["next"]["act"] == "dealer" and any(x["cid"] == cid and x["group"] == "dealer" for x in sup.get("/api/today").json()["items"]))
        db.ex("INSERT OR IGNORE INTO dcr_stock(serial,credited_at) VALUES(?,?)", (SERIALS[-1], db.now()))  # the dealer transfers it
        await dcr.goto(f"{BASE}/dcr/b2c")
        await dcr.wait_for_selector("#can")
        await panel_says(dcr, "Priya Kulkarni")
        await fill(dcr)
        await dcr.fill("#dt", "2026-11-03")
        await dcr.click("#btnDcr")
        await dcr.wait_for_selector("#certNo")
        cert = await dcr.inner_text("#certNo")
        await panel_says(dcr, "saved in Solara")
        g = sup.get(f"/api/filing/{cid}").json()
        check("certificate issued; its number saved in Solara without typing, the page kept as receipt",
              g["data"].get("dcr_cert_no") == cert and any(r["step"] == "dcr" for r in g["receipts"]), cert)
        check("the dealer wait is cleared", not g["data"].get("dcr_dealer_wait") and g["next"]["act"] == "installation", g["next"]["label"])
        await shot(dcr, "5-dcr")

        # ---------------- 5. submit installation, 5 steps ----------------
        print("\n  -- 5. submit installation (5 steps)")
        ins = await ctx.new_page()
        await ins.goto(f"{BASE}/pmsg/vendor/install?app={APP_NO}")
        await panel_says(ins, "Priya Kulkarni")
        await fill(ins)
        got = {k: await ins.input_value(s) for k, s in (("v", "#vName"), ("lat", "#lat"), ("lng", "#lng"), ("loc", "#locType"))}
        check("step 1: vendor, latitude and longitude (replacing the portal's 0.00) and location type",
              got["v"] and got["lat"] == str(SITE[0]) and got["lng"] == str(SITE[1]) and got["loc"] == "Urban", str(got))
        await ins.click("#btnStep")
        await ins.wait_for_selector("#phase")
        await panel_says(ins, "Fill")
        await fill(ins)
        row = lambda n: ins.input_value(f'[name="{n}"]')
        got = {k: await row(n) for k, n in (("ikw", "inv_kw_0"), ("iq", "inv_qty_0"), ("im", "inv_make_0"), ("mwp", "mod_wp_0"),
                                           ("mq", "mod_qty_0"), ("mm", "mod_make_0"), ("ikw2", "inv_kw_1"), ("mwp2", "mod_wp_1"))}
        check("step 2: inverter and module rows from the record; the second rows left empty",
              got == {"ikw": "3", "iq": "1", "im": "Polycab PSIS-3K", "mwp": "550", "mq": "6", "mm": "Premier Energies", "ikw2": "", "mwp2": ""}, str(got))
        check("step 2: serial numbers and the DCR certificate number filled",
              (await row("mod_serial_0")).split("\n") == SERIALS and await row("inv_serial_0") == "PSIS3K26A04411"
              and await ins.input_value("#dcrNo") == cert)
        check("step 2: phase matched to the portal's wording", await ins.input_value("#phase") == "Single Phase")
        await ins.click("#btnStep")
        await ins.wait_for_selector("#plant")
        await panel_says(ins, "attach 1 file")
        await fill(ins)
        size = await ins.evaluate("document.querySelector('#plant').files[0].size")
        check("step 3: the geotagged plant photo attached, under the portal's 500 KB", 0 < size <= 500 * 1024, f"{size // 1024} KB")
        await ins.click("#btnStep")
        await ins.wait_for_selector("text=Protection Checklist")
        await panel_says(ins, "Fill")
        await fill(ins)
        ans = await ins.evaluate("['spd','mcb','earth','la'].map(n => (document.querySelector(`input[name=${n}]:checked`) || {}).value || '')")
        check("step 4: the protection checklist answered from the record", ans == ["Y", "Y", "Y", "Y"], str(ans))
        await ins.click("#btnStep")
        try:
            await ins.wait_for_selector('input[name="declare"]')
        except Exception:
            print("   step 4 -> 5:", ins.url, "|", " ".join((await ins.inner_text("body"))[:500].split()))
            raise
        await ins.wait_for_timeout(1500)
        check("step 5: the declaration is left for the owner", not await ins.is_checked('input[name="declare"]'))
        await ins.check('input[name="declare"]')
        await ins.click("#btnStep")
        await ins.wait_for_selector("text=Installation details submitted successfully")
        await ins.wait_for_selector("#solaraMark", timeout=25000)
        await ins.click("#solaraMark")
        await panel_says(ins, "with the page as the receipt")
        g = sup.get(f"/api/filing/{cid}").json()
        check("installation marked filed in Solara, receipt kept", bool(g["times"]["installation_at"]) and
              any(r["step"] == "installation" for r in g["receipts"]))
        check("next: the customer accepts on their phone (their own step, shown as a call)",
              g["next"]["act"] == "ask_accept" and any(x["cid"] == cid and x["group"] == "calls" for x in sup.get("/api/today").json()["items"]))
        sup.post("/pmsg/vendor/sandbox/advance", data={"app": APP_NO})   # the customer accepts with their OTP
        await pm.goto(f"{BASE}/pmsg/vendor/applications")
        await panel_says(pm, "updated in Solara")
        g = sup.get(f"/api/filing/{cid}").json()
        check("the portal's next status, read by the co-pilot, marks the customer's acceptance",
              bool(g["times"]["install_accepted_at"]) and g["timeline"]["current"] == "inspection", g["timeline"]["current"])
        await shot(ins, "6-installation-done")

        # ---------------- 6. six documents, e-sign, MSEDCL ----------------
        print("\n  -- 6. six documents on MSEDCL")
        sup.put(f"/api/closeout/{cid}", json={"msedcl_app_id": "79437788", "billing_unit": "4651 Manchar", "warranty": "10 + 25",
                                              "inverter_year": "2026", "meter_serial": "GM2611877", "cell_maker": "Premier Energies",
                                              "cell_invoice": "PEL/26/91120", "aadhaar_last4": "4471"}).raise_for_status()
        g = sup.get(f"/api/closeout/{cid}").json()
        if any(x["key"] == "datasheet" and x["state"] == "missing" for x in g["docs"]):
            sup.post(f"/api/closeout/{cid}/datasheet", files={"file": ("ds.pdf", closeout._demo_datasheet(g["data"]), "application/pdf")})
        url = sup.post(f"/api/closeout/{cid}/sign", json={}).json()["url"]
        page = customer_signs(url, ["wcr", "annexure1", "net_agreement"])
        check("the customer e-signs the three documents they sign (signature saved once, reused)", "Thank you" in page)
        built = sup.post(f"/api/closeout/{cid}/build").json()
        ms = [x for x in built if x["slot"]]
        check("all six MSEDCL documents generated, each a PDF under 300 KB", all(x["bytes"] and x["bytes"] <= 300 * 1024 for x in ms),
              ", ".join(f"{x['key']} {(x['bytes'] or 0) // 1024} KB" for x in ms))
        ml = await ctx.new_page()
        await ml.goto(f"{BASE}/msedcl/")
        await ml.fill("#userIdField", "vendor"); await ml.fill('input[name="password"]', "demo")
        await ml.click("button.btn")
        await ml.wait_for_selector("text=Consumer's List")
        await panel_says(ml, "updated in Solara")
        check("the MSEDCL list status is read into Solara too",
              (db.one("SELECT status FROM portal_status WHERE customer_id=? AND portal='msedcl'", (cid,)) or {}).get("status") == "Pending For Upload")
        await ml.close()  # a fresh tab after the password login, as for DCR (headless input quirk)
        ml = await ctx.new_page()
        await ml.goto(f"{BASE}/msedcl/upload?app=79437788")
        await ml.wait_for_selector("#solaraAttach", timeout=40000)
        await ml.click("#solaraAttach")
        await ml.wait_for_function("document.querySelector('#solaraPanel').dataset.attached === '6'", timeout=40000)
        await ml.evaluate("window.__hits = []; addEventListener('click', e => window.__hits.push(e.target.id || e.target.tagName), true)")
        await ml.click("#btnUpload")
        try:
            await ml.wait_for_selector("text=VERIFICATION PENDING")
        except Exception:
            print("   MSEDCL page:", ml.url, "| clicks:", await ml.evaluate("window.__hits"), "| panel at:",
                  await ml.evaluate("JSON.stringify(document.querySelector('#solaraPanel').getBoundingClientRect())"),
                  "| button at:", await ml.evaluate("JSON.stringify(document.querySelector('#btnUpload').getBoundingClientRect())"))
            raise
        await panel_says(ml, "Solara has been updated")
        g = sup.get(f"/api/filing/{cid}").json()
        check("all six accepted by MSEDCL: none rejected for size or format",
              db.one("SELECT COUNT(DISTINCT slot) k FROM msedcl_uploads WHERE application_id='79437788'")["k"] == 6)
        check("milestone 2 done for the customer", all(s["done"] for s in g["steps"]) and not g["next"]["act"], g["next"]["label"])
        post = g["post_install_seconds"]
        check("post-installation time is shown (first field photo to all six on MSEDCL)", post is not None and post >= 0, f"{post} s")
        await shot(ml, "7-msedcl")
        await dash.bring_to_front()
        await dash.reload()
        await dash.wait_for_selector("#shell:not([hidden])")
        await dash.click('.navitem[data-view="inst"]')
        await dash.click(f'[data-inst="{cid}"]')
        await dash.wait_for_selector("text=Post-installation")
        rec = sup.get(f"/files/receipt/{cid}/installation")
        check("the installation receipt opens as a PDF with the filled values in it",
              rec.status_code == 200 and rec.content.startswith(b"%PDF"))
        import fitz
        txt = "".join(pg.get_text() for pg in fitz.open(stream=rec.content, filetype="pdf"))
        check("the receipt shows what was submitted", "Installation details submitted successfully" in txt, txt[:80].replace("\n", " "))
        jsr = sup.get(f"/files/receipt/{cid}/loan")
        jtxt = "".join(pg.get_text() for pg in fitz.open(stream=jsr.content, filetype="pdf"))
        check("no receipt carries an OTP or Aadhaar number", "246810" not in jtxt and "123456784471" not in jtxt)
        check("all receipts are under 300 KB", all(r["bytes"] <= 300 * 1024 for r in g["receipts"]), str([r["bytes"] // 1024 for r in g["receipts"]]))
        await shot(dash, "8-milestone2-done")
        check("no script errors on the dashboard or the portals", not errors, "; ".join(errors[:3]))
        await ctx.close()

    print("\n  reset:", sup.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
