"""Close-out test: details -> customer e-sign -> six MSEDCL PDFs -> co-pilot upload.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/closeout.py                       (in another)

Covers the consent rules (signature only on approved, unchanged documents), the 300 KB
limit, the GPS requirement, duplicate serials, the co-pilot API, the customer's signing
page in a phone-sized browser, and the extension attaching all six files on the MSEDCL
sandbox. Resets the demo first and again at the end.
"""
import asyncio, base64, io, json, re, sys, tempfile
from pathlib import Path
import httpx
from PIL import Image, ImageDraw
from pypdf import PdfReader
from playwright.async_api import async_playwright
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db  # noqa: E402

BASE = "http://127.0.0.1:8900"
EXT = Path(__file__).resolve().parent.parent / "extension"
CID, CONSUMER = "SS-2042", "170031277450"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def client(user=None):
    c = httpx.Client(base_url=BASE, timeout=90, follow_redirects=True)
    if user:
        c.post("/api/login", json={"username": user, "password": "demo"}).raise_for_status()
    return c


def drawn(blank=False):
    im = Image.new("RGBA", (420, 140), (0, 0, 0, 0))
    if not blank:
        ImageDraw.Draw(im).line([(20, 90), (80, 30), (130, 100), (190, 40), (260, 95), (390, 50)],
                                fill=(10, 20, 60, 255), width=4)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def fd(pairs):
    """Form fields with repeats (several 'approve' boxes), the way httpx wants them."""
    out = {}
    for k, v in pairs:
        out.setdefault(k, []).append(v)
    return out


def pdf_text(blob):
    return " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(blob)).pages)


def states(c, cid=CID):
    return {d["key"]: d["state"] for d in c.get(f"/api/closeout/{cid}").json()["docs"]}


def public_sign(url, digits, approve, signature=None, name="Asha Vinayak Deshpande"):
    """Walk the customer's link with a fresh browser-less session. Returns the final page text."""
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        pub.post(url + "/verify", data={"digits": digits})
        form = [("approve", k) for k in approve] + [("name", name), ("consent", "yes")]
        if signature:
            form.append(("signature", signature))
        return pub.post(url, data=fd(form)).text


def main_http():
    sup, op = client("r.deshmukh"), client("s.kale")
    print("  reset:", sup.post("/api/demo/reset").json()["runnable"])

    print("\n  -- details and checks")
    lst = {r["id"]: r for r in op.get("/api/closeout").json()}
    check("close-out list holds the installed customers", {CID, "SS-2048"} <= set(lst), ", ".join(lst))
    g = op.get(f"/api/closeout/{CID}").json()
    check("SS-2042 passes every check", not [x for x in g["checks"] if x["sev"] == "bad"], str(g["checks"]))
    check("capacity worked out from modules: 9 x 550 Wp = 4.95 kWp", g["capacity"] == 4.95, str(g["capacity"]))
    check("site photo GPS was read into the record", g["data"].get("lat", "").startswith("19.95"), g["data"].get("lat"))

    bad = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(bad, "JPEG")
    r = op.post(f"/api/closeout/{CID}/photo", files={"file": ("x.jpg", bad.getvalue(), "image/jpeg")})
    check("a photo without GPS is refused with a reason", r.status_code == 400 and "GPS" in r.text, r.text[:90])

    serial = g["data"]["module_serials"].split()[0]
    op.put("/api/closeout/SS-2048", json={"module_serials": serial})
    c48 = op.get("/api/closeout/SS-2048").json()
    check("a serial already used on another customer is blocked",
          any("already on SS-2042" in x["text"] for x in c48["checks"]), str(c48["checks"])[:120])
    op.put("/api/closeout/SS-2048", json={"module_serials": ""})

    print("\n  -- company signature")
    r = op.post("/api/signature/vendor", json={"image": drawn()})
    check("an operator cannot set the company signature", r.status_code == 403)
    r = sup.post("/api/signature/vendor", json={"image": drawn(blank=True)})
    check("an empty company signature is refused", r.status_code == 400, r.text[:80])
    r = sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"})
    check("the supervisor sets the company signature once", r.status_code == 200)

    st = states(op)
    check("before the customer signs, their documents wait for approval",
          all(st[k] == "needs_approval" for k in ("agreement", "wcr", "annexure1", "net_agreement")), str(st))
    check("vendor-only DCR declaration, datasheet and photo are ready",
          all(st[k] == "ready" for k in ("dcr_decl", "datasheet", "site_photo")), str(st))

    print("\n  -- customer e-sign")
    s = op.post(f"/api/closeout/{CID}/sign", json={}).json()
    url = s["url"]
    check("send-for-signature makes a link and a WhatsApp message to the customer's number",
          "/sign/" in url and (s["whatsapp"] or "").startswith("https://wa.me/919028144520"), s["whatsapp"])
    check("the request covers the four customer-signed documents",
          sorted(s["docs"]) == ["agreement", "annexure1", "net_agreement", "wcr"], str(s["docs"]))
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        first = pub.get(url).text
        check("the link asks for the bill digits before showing anything",
              "Confirm it is you" in first and "Deshpande" not in first)
        check("documents cannot be read before the check",
              pub.get(url + "/doc/wcr").status_code == 403)
        wrong = pub.post(url + "/verify", data={"digits": "0000"}).text
        check("wrong digits are refused", "do not match" in wrong)
        pub.post(url + "/verify", data={"digits": CONSUMER[-4:]})
        page = pub.get(url).text
        check("after the check the page lists the documents and a signature pad",
              "Work Completion Report" in page and 'id="pad"' in page)
        prev = pub.get(url + "/doc/wcr").text
        check("the customer can read the document they are approving",
              "Asha Vinayak Deshpande" in prev and "WORK COMPLETION REPORT" in prev.upper())
        check("the document shows only the masked Aadhaar", "XXXX XXXX 4471" in prev)
        no_ink = pub.post(url, data=fd([("approve", "wcr"), ("name", "Asha Deshpande"), ("consent", "yes"),
                                     ("signature", drawn(blank=True))])).text
        check("an empty signature is refused", "empty" in no_ink)
        no_consent = pub.post(url, data=fd([("approve", "wcr"), ("name", "Asha Deshpande"),
                                         ("signature", drawn())])).text
        check("signing without ticking consent is refused", "consent box" in no_consent)
        done = pub.post(url, data=fd([("approve", k) for k in s["docs"]] +
                        [("name", "Asha Vinayak Deshpande"), ("consent", "yes"), ("signature", drawn())])).text
        check("the customer signs once and approves all four", "Your documents are signed" in done)
        check("the same link cannot be used twice", "Already signed" in pub.get(url).text)

    st = states(op)
    check("every document is now ready", all(v == "ready" for v in st.values()), str(st))

    print("\n  -- the MSEDCL pack")
    out = {d["key"]: d for d in op.post(f"/api/closeout/{CID}/build").json()}
    sizes = {k: d["bytes"] for k, d in out.items()}
    check("all seven documents generated", all(sizes.values()), str(sizes))
    check("every file is at or under 300 KB", all(v <= 300 * 1024 for v in sizes.values()),
          ", ".join(f"{k} {v // 1024}KB" for k, v in sizes.items()))
    wcr = op.get(f"/files/closeout/{CID}/wcr.pdf").content
    check("the WCR is a real PDF carrying both signatures with the consent reference",
          wcr.startswith(b"%PDF") and "e-signed by Asha Vinayak Deshpande" in pdf_text(wcr)
          and "signed for" in pdf_text(wcr), pdf_text(wcr)[-160:].replace("\n", " "))
    dcr = pdf_text(op.get(f"/files/closeout/{CID}/dcr_decl.pdf").content)
    check("the DCR declaration lists all nine serial numbers", dcr.count("PE55026A") == 9)
    check("the vendor-only DCR declaration carries no customer signature", "e-signed by" not in dcr)

    print("\n  -- consent is bound to content")
    op.put(f"/api/closeout/{CID}", json={"inverter_serial": "PSIS5K26A09999"})
    st = states(op)
    check("changing the inverter serial puts the Annexure back to the customer",
          st["annexure1"] == "changed" and st["wcr"] == "ready", str(st))
    out = {d["key"]: d for d in op.post(f"/api/closeout/{CID}/build").json()}
    check("the changed Annexure is not generated with the old signature",
          out["annexure1"]["bytes"] is None and out["wcr"]["bytes"], str({k: v["bytes"] for k, v in out.items()}))
    s2 = op.post(f"/api/closeout/{CID}/sign", json={}).json()
    check("the next link asks only for the changed document", s2["docs"] == ["annexure1"], str(s2["docs"]))
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        pub.post(s2["url"] + "/verify", data={"digits": CONSUMER[-4:]})
        page = pub.get(s2["url"]).text
        check("a returning customer approves without drawing again",
              "saved signature" in page and 'id="pad"' not in page)
        op.put(f"/api/closeout/{CID}", json={"inverter_serial": "PSIS5K26A07777"})
        stale = pub.post(s2["url"], data=fd([("approve", "annexure1"), ("name", "Asha Vinayak Deshpande"),
                                          ("consent", "yes")]))
        check("approving a document that changed after the link was sent is refused",
              stale.status_code == 409 and "changed" in stale.text)
    s3 = op.post(f"/api/closeout/{CID}/sign", json={}).json()
    done = public_sign(s3["url"], CONSUMER[-4:], ["annexure1"])
    check("re-approval of the final version succeeds", "Your documents are signed" in done)
    check("everything is ready again", all(v == "ready" for v in states(op).values()), str(states(op)))

    s4 = op.post(f"/api/closeout/SS-2048/sign", json={"docs": ["wcr"]})
    check("a link cannot be sent for a document that is missing data", s4.status_code == 400, s4.text[:100])
    s4 = op.post(f"/api/closeout/SS-2048/sign", json={}).json()
    check("for a half-entered file, only the document that is complete goes out",
          s4["docs"] == ["agreement"], str(s4["docs"]))

    print("\n  -- lockout")
    sup.put(f"/api/closeout/{CID}", json={"rts_cost": "286000"})
    s5 = op.post(f"/api/closeout/{CID}/sign", json={}).json()
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        for _ in range(5):
            last = pub.post(s5["url"] + "/verify", data={"digits": "1111"})
        check("five wrong attempts lock the link", "locked" in pub.get(s5["url"]).text)
    s6 = op.post(f"/api/closeout/{CID}/sign", json={}).json()
    check("re-signing after a price change", "signed" in public_sign(s6["url"], CONSUMER[-4:], s6["docs"]))

    print("\n  -- co-pilot API")
    key = op.post("/api/copilot/key").json()["key"]
    with httpx.Client(base_url=BASE, timeout=90) as ext:
        r = ext.get("/api/copilot/lookup", params={"consumer_no": CONSUMER}, headers={"X-Solara-Key": "sk_wrong"})
        check("an unknown co-pilot key is refused", r.status_code == 401)
        look = ext.get("/api/copilot/lookup", params={"consumer_no": CONSUMER},
                       headers={"X-Solara-Key": key}).json()
        slots = sorted(f["slot"] for f in look["files"] if f["slot"])
        check("lookup by consumer number finds the customer and all six MSEDCL files",
              look["customer_id"] == CID and slots == [1, 2, 3, 4, 5, 6], str(slots))
        f = ext.get(f"/api/copilot/file/{CID}/site_photo", headers={"X-Solara-Key": key})
        check("the co-pilot downloads a file as PDF", f.content.startswith(b"%PDF"))
    return key


async def main_ui():
    """The dashboard the way the owner uses it: one next-action button per customer."""
    print("\n  -- close-out screen")
    print("  reset:", client("r.deshmukh").post("/api/demo/reset").json()["runnable"])
    db.ex("DELETE FROM signatures WHERE role='vendor'")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        pg.on("pageerror", lambda ex: errors.append(str(ex)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        await pg.goto(BASE)
        await pg.click('[data-as="r.deshmukh"]')
        await pg.wait_for_selector("#shell:not([hidden])")
        await pg.click('.navitem[data-view="closeout"]')
        await pg.wait_for_selector("#coNext")
        nxt = lambda: pg.inner_text("#coNext")
        check("first time, the next action is the company signature", "company signature" in await nxt(), await nxt())
        await pg.click("#coNext")
        box = await pg.locator("#vsPad").bounding_box()
        await pg.mouse.move(box["x"] + 20, box["y"] + 100)
        await pg.mouse.down()
        for i in range(20):
            await pg.mouse.move(box["x"] + 20 + i * 15, box["y"] + 70 + (30 if i % 2 else -20))
        await pg.mouse.up()
        await pg.click("#vsSave")
        await pg.wait_for_function("document.querySelector('#coNext').innerText.includes('Send to the customer')")
        check("after drawing it, the next action is sending to the customer", True)
        await pg.fill('[data-f="billing_unit"]', "4642 Nashik Road S/dn")
        await pg.click("#coSave")
        await pg.wait_for_timeout(700)
        saved = json.loads(db.one("SELECT data FROM closeout WHERE customer_id=?", (CID,))["data"])
        check("details typed on the screen are saved", saved.get("billing_unit") == "4642 Nashik Road S/dn")
        await pg.click("#coNext")
        await pg.wait_for_selector("a:has-text('Send on WhatsApp')")
        url = await pg.input_value("#signUrl")
        wa = await pg.get_attribute("a:has-text('Send on WhatsApp')", "href")
        check("send gives a link and a ready WhatsApp message", "/sign/" in url and wa.startswith("https://wa.me/91"))
        await pg.keyboard.press("Escape")
        public_sign(url, CONSUMER[-4:], ["agreement", "wcr", "annexure1", "net_agreement"], drawn())
        await pg.click('[data-co="SS-2048"]')
        await pg.wait_for_timeout(500)
        await pg.click(f'[data-co="{CID}"]')
        await pg.wait_for_function("document.querySelector('#coNext').innerText.includes('Generate')")
        check("once the customer signs, the next action is generating the documents", True)
        await pg.click("#coNext")
        await pg.wait_for_function("document.querySelector('#coNext').innerText.includes('Open MSEDCL')", timeout=60000)
        sizes = await pg.locator("td.mono:has-text('KB')").all_inner_texts()
        check("all seven documents show their size, every one under 300 KB",
              len(sizes) == 7 and all(int(s.split()[0]) <= 300 for s in sizes), ", ".join(sizes))
        await pg.click("#coKey")
        await pg.wait_for_selector("#mbody input[value^='sk_']")
        check("connect co-pilot shows a key once", True)
        await pg.keyboard.press("Escape")
        check("no JavaScript errors on the close-out screen", not errors, "; ".join(errors[:2]))
        await b.close()


async def main_browser(key):
    print("\n  -- signing page on a phone")
    op = client("s.kale")
    sup = client("r.deshmukh")
    sup.put(f"/api/closeout/{CID}", json={"rts_cost": "287500"})
    db.ex("DELETE FROM signatures WHERE role='consumer' AND customer_id=?", (CID,))
    s = op.post(f"/api/closeout/{CID}/sign", json={}).json()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        phone = await b.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        await phone.goto(s["url"])
        await phone.fill("#digits", CONSUMER[-4:])
        await phone.click("button[type=submit]")
        await phone.wait_for_selector("#pad")
        over = await phone.evaluate("document.documentElement.scrollWidth - innerWidth")
        check("the signing page fits a phone screen", over <= 1, f"{over}px")
        await phone.check("input[value=agreement]")
        await phone.check("#consent")
        box = await phone.locator("#pad").bounding_box()
        await phone.mouse.move(box["x"] + 30, box["y"] + 120)
        await phone.mouse.down()
        for i in range(24):
            await phone.mouse.move(box["x"] + 30 + i * 12, box["y"] + 60 + (35 if i % 2 else -25))
        await phone.mouse.up()
        await phone.click("button[type=submit]:has-text('Sign and approve')")
        await phone.wait_for_selector("text=Your documents are signed")
        check("signing with a finger on the pad works end to end", True)
        sig = db.one("SELECT * FROM signatures WHERE role='consumer' AND customer_id=?", (CID,))
        check("the drawn signature is stored encrypted", sig and open(sig["path"], "rb").read(15) == b"SOLARA-VAULT-1\n")
        await b.close()
    s = op.post(f"/api/closeout/{CID}/sign", json={}).json()
    if s.get("docs"):
        public_sign(s["url"], CONSUMER[-4:], s["docs"])

    print("\n  -- co-pilot extension on the MSEDCL sandbox")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{key}'}})")
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto(BASE + "/msedcl/")
        await pg.fill("#userIdField", "vendor01")                      # the person logs in
        await pg.fill("input[name=password]", "demo")
        await pg.click("button[type=submit]")
        await pg.click("a:has-text('79435901')")
        await pg.wait_for_selector("#solaraPanel button#solaraAttach", timeout=60000)
        panel = await pg.inner_text("#solaraPanel")
        check("the co-pilot recognises the customer from the page", "SS-2042" in panel, panel[:80])
        await pg.click("#solaraAttach")
        await pg.wait_for_function("document.querySelector('#solaraPanel').dataset.attached === '6'", timeout=30000)
        files = await pg.evaluate("[...document.querySelectorAll('input[type=file]')].map(i => i.files[0] && i.files[0].name)")
        check("one click attaches the right file to each of the six rows",
              files == [f"{CID}_{k}.pdf" for k in ("wcr", "annexure1", "dcr_decl", "net_agreement", "datasheet", "site_photo")], str(files))
        check("nothing is uploaded until the person presses Upload",
              db.one("SELECT COUNT(*) k FROM msedcl_uploads WHERE application_id='79435901'")["k"] == 0)
        await pg.click("#btnUpload")                                   # the person
        await pg.wait_for_selector("text=VERIFICATION PENDING")
        got = db.q("SELECT slot, bytes FROM msedcl_uploads WHERE application_id='79435901' ORDER BY slot")
        check("the portal accepted all six PDFs, each within 300 KB",
              [g["slot"] for g in got] == [1, 2, 3, 4, 5, 6] and all(g["bytes"] <= 300 * 1024 for g in got),
              ", ".join(f"{g['bytes'] // 1024}KB" for g in got))
        await pg.wait_for_timeout(1500)
        d = json.loads(db.one("SELECT data FROM closeout WHERE customer_id=?", (CID,))["data"])
        check("Solara marks the customer as uploaded", d.get("msedcl_uploaded") == "yes")
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main_ui())
    k = main_http()
    asyncio.run(main_browser(k))
    print("\n  reset:", client("r.deshmukh").post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("   failed:", f)
    sys.exit(1 if FAIL else 0)
