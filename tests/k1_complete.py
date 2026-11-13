"""K1 completion tests: the things the happy-path run in milestone1.py does not cover.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/k1_complete.py                    (in another)

API: duplicate customers, validation, uploads, extraction conflicts, uncertain fields, manual
corrections that survive a re-read, Aadhaar privacy, the agreement's kept copy, verification and
refusal paths. Extension (real Chrome, extension loaded, on a synthetic portal page): connection
failures, human typing kept, OTP/CAPTCHA/password/declaration untouched, nothing submitted.
Synthetic data only. Resets the demo first and again at the end.
"""
import asyncio, base64, io, json, re, sys, tempfile
from pathlib import Path
import httpx
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, closeout, extract, registration, vault  # noqa: E402
import fixtures as fx  # noqa: E402

BASE = "http://127.0.0.1:8900"
EXT = Path(__file__).resolve().parent.parent / "extension"
PASS, FAIL = [], []


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


def sign(url, digits, name=fx.AADHAAR_NAME):
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        pub.post(url + "/verify", data={"digits": digits})
        return pub.post(url, data={"approve": ["agreement"], "name": name, "consent": "yes",
                                   "signature": drawn()}).text


def everything_in_db():
    c = db.conn()
    out = []
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        out += [str(tuple(r)) for r in c.execute(f"SELECT * FROM {t}")]
    return "\n".join(out)


def upload(sup, cid, kind, name, blob, mime):
    return sup.post(f"/api/registration/{cid}/document", params={"kind": kind}, files={"file": (name, blob, mime)})


async def main():
    sup, viewer = client("r.deshmukh"), client("a.more")
    sup.post("/api/demo/reset")
    sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"}).raise_for_status()
    fx.register_consumer()
    key = sup.post("/api/copilot/key").json()["key"]
    async with async_playwright() as p:
        b = await p.chromium.launch()
        bill = await fx.bill_pdf(await b.new_page())
        await b.close()
    aadhaar = fx.aadhaar_photo()

    # ---------------- A. customer creation and duplicates ----------------
    print("\n  -- A. creation and duplicates")
    mk = lambda **kw: sup.post("/api/customers", json=kw)
    r = mk(name="Zubin Karandikar", mobile="9876501234")
    zid = r.json()["customer"]["id"]
    check("a customer is created from a name and a valid mobile", r.status_code == 200 and zid.startswith("SS-"))
    check("the mobile is saved with the record", r.json()["data"].get("mobile") == "9876501234")
    check("a mobile that cannot exist is refused", mk(name="Other Person", mobile="1234567890").status_code == 400)
    check("a +91 number is accepted and stored as 10 digits",
          mk(name="Plus Ninety One", mobile="+91 98765 43210").json()["data"]["mobile"] == "9876543210")
    d = mk(name="zubin  KARANDIKAR")
    check("the same name (case and spacing ignored) is stopped as a duplicate",
          d.status_code == 409 and d.json()["duplicates"][0]["id"] == zid, d.json().get("detail", "")[:70])
    d = mk(name="Someone Else Entirely", mobile="9876501234")
    check("the same mobile number is stopped as a duplicate",
          d.status_code == 409 and d.json()["duplicates"][0]["why"] == "same mobile number")
    check("a duplicate can still be added on purpose",
          mk(name="Zubin Karandikar", allow_duplicate=True).status_code == 200)
    check("a duplicate warning created nothing", len([x for x in db.q("SELECT id FROM customers WHERE name LIKE 'Someone Else%'")]) == 0)
    check("a viewer cannot add a customer", viewer.post("/api/customers", json={"name": "View Er"}).status_code == 403)
    other = mk(name="Consumer Clash Test").json()["customer"]["id"]
    sup.put(f"/api/registration/{zid}", json={"consumer_no": "555000111222"}).raise_for_status()
    check("a consumer number already on another customer is refused",
          sup.put(f"/api/registration/{other}", json={"consumer_no": "555000111222"}).status_code == 400)
    check("a bad email is refused", sup.put(f"/api/registration/{zid}", json={"email": "not-an-email"}).status_code == 400)

    # ---------------- B. uploads ----------------
    print("\n  -- B. document uploads")
    check("an unknown document type is refused on the general upload route too",
          sup.post(f"/api/documents/{zid}/upload", params={"kind": "../../x"},
                   files={"file": ("a.pdf", b"%PDF-1", "application/pdf")}).status_code == 400)
    check("an empty file is refused with a reason",
          upload(sup, zid, "bill", "bill.pdf", b"", "application/pdf").status_code == 400)
    check("a missing customer is refused", upload(sup, "SS-999999", "bill", "b.pdf", b"%PDF", "application/pdf").status_code in (404, 400))
    check("a viewer cannot upload", viewer.post(f"/api/registration/{zid}/document", params={"kind": "bill"},
          files={"file": ("b.pdf", b"x", "application/pdf")}).status_code == 403)
    r = upload(sup, zid, "bill", "corrupt.pdf", b"%PDF-1.4 this is not really a pdf", "application/pdf")
    g = r.json()
    check("a corrupt PDF is kept, explained and does not crash the upload",
          r.status_code == 200 and any(f["key"] == "bill_unread" and f["status"] == "review" for f in g["fields"])
          and g.get("extract_error") is None)

    # ---------------- C. extraction, flags, mismatches, corrections ----------------
    print("\n  -- C. extraction, uncertain fields, manual corrections")
    cid = mk(name="Priya Kulkarni", mobile="9876543211").json()["customer"]["id"]
    upload(sup, cid, "bill", "bill.pdf", bill, "application/pdf")
    g = upload(sup, cid, "aadhaar", "image.jpg", aadhaar, "image/jpeg").json()
    f = {x["key"]: x for x in g["fields"]}
    check("each field carries its source", f["consumer_no"]["source"] == "bill" and f["aadhaar_name"]["source"] == "Aadhaar QR")
    kinds = {i["field"]: i["kind"] for i in g["validation"]["issues"]}
    check("a name that differs between bill and Aadhaar is a flagged mismatch", kinds.get("Consumer name (bill)") == "mismatch", str(kinds))
    check("the bill mobile disagreeing with the mobile typed by hand is flagged, and the typed one is kept",
          f["bill_mobile"]["status"] == "review" and g["data"]["mobile"] == "9876543211"
          and kinds.get("Registered mobile") == "mismatch")
    check("a missing required item is listed as missing", kinds.get("proposed capacity (kW)") == "missing")
    db.ex("UPDATE customers SET pin='41' WHERE id=?", (cid,))
    check("a malformed PIN shows as invalid", any(i["kind"] == "invalid" for i in registration.validate(cid)["issues"]))
    db.ex("UPDATE customers SET pin='410503' WHERE id=?", (cid,))
    check("incomplete or conflicting data is blocking, never silently accepted", g["validation"]["blocking"])
    check("flagged values did not reach the record", g["customer"]["aadhaar_name"] == fx.AADHAAR_NAME  # clean QR value, not the flagged bill name
          and f["bill_name"]["status"] == "review")

    g = sup.post(f"/api/registration/{cid}/confirm", json={"key": "bill_name", "value": fx.NEW["billed_name"]}).json()
    f = {x["key"]: x for x in g["fields"]}
    check("a correction is saved, with what was read kept in the note",
          f["bill_name"]["status"] == "ok" and f["bill_name"]["note"].startswith("Checked by"), f["bill_name"]["note"])
    check("the filed name follows the correction", g["values"]["name"] == fx.NEW["billed_name"])
    g = upload(sup, cid, "passbook", "pb.jpg", fx.passbook_photo(), "image/jpeg").json()
    f = {x["key"]: x for x in g["fields"]}
    check("a correction survives uploading another document", f["bill_name"]["status"] == "ok" and f["bill_name"]["note"].startswith("Checked by"))
    g = upload(sup, cid, "bill", "bill.pdf", bill, "application/pdf").json()
    f = {x["key"]: x for x in g["fields"]}
    check("replacing the corrected document asks for the check again", f["bill_name"]["status"] == "review")
    sup.post(f"/api/registration/{cid}/confirm", json={"key": "bill_name", "value": fx.NEW["billed_name"]})
    sup.post(f"/api/registration/{cid}/confirm", json={"key": "bill_mobile", "value": "9876543211"})
    sup.put(f"/api/registration/{cid}", json={"kw": "3", "rts_cost": "210000", "email": "k1.customer@example.test"}).raise_for_status()
    g = sup.get(f"/api/registration/{cid}").json()
    check("once corrected and complete, nothing blocks the portal fill",
          not g["validation"]["blocking"] and g["next"]["act"] == "register", str(g["validation"]["issues"]))

    t = mk(name="Unread Aadhaar Case").json()["customer"]["id"]
    g = upload(sup, t, "aadhaar", "a.jpg", fx.aadhaar_photo(qr=False), "image/jpeg").json()
    check("an Aadhaar without a readable QR is uncertain, with the reason",
          any(i["kind"] == "uncertain" and i["field"] == "Aadhaar" for i in g["validation"]["issues"]))
    r = sup.post(f"/api/registration/{t}/confirm", json={"key": "aadhaar_unread", "value": "4471 2019 0101"})
    check("a full Aadhaar number typed by a person is refused", r.status_code == 400 and "last 4" in r.text)
    g = sup.post(f"/api/registration/{t}/confirm", json={"key": "aadhaar_unread", "value": "Unread Aadhaar Case"}).json()
    check("typing the name for an unread Aadhaar reaches the customer record",
          g["customer"]["aadhaar_name"] == "Unread Aadhaar Case" and not any(x["key"] == "aadhaar_unread" for x in g["fields"]))
    upload(sup, t, "bill", "x.pdf", b"%PDF-1.4 broken", "application/pdf")
    r = sup.post(f"/api/registration/{t}/confirm", json={"key": "bill_unread", "value": "12"})
    check("an unread bill needs a real consumer number to be corrected", r.status_code == 400)
    g = sup.post(f"/api/registration/{t}/confirm", json={"key": "bill_unread", "value": "170 099 900 123"}).json()
    check("a typed consumer number lands in the record", g["customer"]["consumer_no"] == "170099900123")

    # ---------------- D. Aadhaar privacy ----------------
    print("\n  -- D. Aadhaar privacy")
    dump = everything_in_db()
    check("no more than the last 4 digits of the Aadhaar number are in the database or audit trail",
          "44712019" not in dump and "XXXX XXXX 4471" in dump)
    xml = '<PrintLetterBarcodeData uid="999911112222" name="Test Person" gender="M" yob="1980" pc="410503" dist="Pune"/>'
    parsed = extract.parse_xml_qr(xml)
    check("the older XML QR keeps only the last 4 digits", parsed["last4"] == "2222" and "99991111" not in json.dumps(parsed))
    check("the Aadhaar number is never sent to a model (no model call path for it)",
          "aadhaar" not in extract.PROMPTS and not re.search(r"llm_read\(\s*['\"]aadhaar", Path("app/extract.py").read_text(encoding="utf-8")))

    # ---------------- E. agreement: kept copy, e-sign, verification ----------------
    print("\n  -- E. agreement")
    g = sup.get(f"/api/registration/{cid}").json()
    check("the agreement is flagged as a draft until the client's wording is in", g["agreement"]["draft"] is True)
    check("agreement refuses to go out to a customer before the application number exists",
          sup.post(f"/api/registration/{cid}/agreement").status_code == 400)
    check("a failed upload mark is refused and not recorded",
          sup.post(f"/api/registration/{cid}/mark", json={"step": "agreement_uploaded"}).status_code == 400)
    app_no = "NP-K1TEST26-12345678"
    sup.post(f"/api/registration/{cid}/mark", json={"step": "registered", "app_no": app_no}).raise_for_status()
    clash = mk(name="Application Clash Test").json()["customer"]["id"]
    check("an application number already on another customer is refused",
          sup.post(f"/api/registration/{clash}/mark", json={"step": "registered", "app_no": app_no}).status_code == 400)
    sup.post(f"/api/registration/{cid}/mark", json={"step": "accepted"}).raise_for_status()
    nm = db.one("SELECT aadhaar_name FROM customers WHERE id=?", (cid,))["aadhaar_name"]
    db.ex("UPDATE customers SET aadhaar_name=NULL, address=NULL WHERE id=?", (cid,))
    r = sup.post(f"/api/registration/{cid}/agreement")
    check("an agreement with a blank address is not generated or sent", r.status_code == 400 and "address" in r.text, r.text[:80])
    db.ex("UPDATE customers SET aadhaar_name=NULL, address=? WHERE id=?", (fx.NEW["address"], cid))
    html_ = closeout.unsigned_html("agreement", cid)
    check("without an Aadhaar name the agreement uses the customer name, never 'None'",
          "None" not in html_ and "Priya Kulkarni" in html_)
    db.ex("UPDATE customers SET aadhaar_name=? WHERE id=?", (nm, cid))
    s1 = sup.post(f"/api/registration/{cid}/agreement").json()
    tok1 = s1["url"].rsplit("/", 1)[1]
    snap = closeout.snapshot_html(tok1, "agreement", cid)
    check("the exact version sent is kept, encrypted", snap is not None and snap == closeout.unsigned_html("agreement", cid)
          and snap.encode() not in Path(closeout.snapshot_path(tok1, "agreement", cid)).read_bytes())
    sup.put(f"/api/registration/{cid}", json={"rts_cost": "230000"})
    out = sign(s1["url"], fx.NEW["consumer_no"][-4:])
    check("a change after sending stops the signature; nothing is signed", "changed after this link" in out)
    check("no approval was recorded for the changed document", not db.one("SELECT 1 FROM approvals WHERE customer_id=?", (cid,)))
    s2 = sup.post(f"/api/registration/{cid}/agreement").json()
    tok2 = s2["url"].rsplit("/", 1)[1]
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        pub.post(s2["url"] + "/verify", data={"digits": "0000"})
        check("wrong digits do not open the documents", pub.get(s2["url"] + "/doc/agreement").status_code == 403)
        pub.post(s2["url"] + "/verify", data={"digits": fx.NEW["consumer_no"][-4:]})
        shown = pub.get(s2["url"] + "/doc/agreement").text
    # a phone viewport is prepended to the response only; the kept copy itself follows byte for byte
    check("the customer is shown the kept copy", shown.endswith(closeout.snapshot_html(tok2, "agreement", cid)) and "Rs 230000" in shown)
    check("the customer e-signs the current version", "signed" in sign(s2["url"], fx.NEW["consumer_no"][-4:]))
    ap = db.one("SELECT * FROM approvals WHERE customer_id=?", (cid,))
    rq = db.one("SELECT * FROM sign_requests WHERE token=?", (tok2,))
    check("signature evidence is tied to this customer, this request and this document hash",
          ap["request_token"] == tok2 and ap["doc_hash"] == closeout.doc_hash("agreement", cid)
          and rq["customer_id"] == cid and rq["signer_name"] and rq["signed_at"] and rq["ip"] is not None)
    sg = db.one("SELECT * FROM signatures WHERE role='consumer' AND customer_id=?", (cid,))
    check("the signature image is stored encrypted under the customer", sg and b"\x89PNG" not in Path(sg["path"]).read_bytes())
    v = sup.get(f"/api/registration/{cid}/agreement/check").json()
    check("the signed agreement verifies end to end (approval, kept copy, signatures, stored PDF)", v["ok"], str(v["problems"]))
    check("the signed agreement PDF is stored securely and opens",
          "agreement" in closeout.built(cid) and vault.read(closeout.path_for(cid, "agreement")).startswith(b"%PDF"))
    dr = closeout.snapshot_path(tok2, "agreement", cid)
    original = vault.read(dr)
    vault.write(dr, original + b"<!-- tampered -->")
    v = sup.get(f"/api/registration/{cid}/agreement/check").json()
    check("a copy that no longer matches what was approved fails verification", not v["ok"] and any("does not match" in x for x in v["problems"]))
    check("an unverified agreement cannot be marked uploaded",
          sup.post(f"/api/registration/{cid}/mark", json={"step": "agreement_uploaded"}).status_code == 400)
    vault.write(dr, original)
    r = httpx.post(f"{BASE}/api/copilot/report", headers={"X-Solara-Key": key},
                   json={"customer_id": cid, "event": "agreement_uploaded"})
    check("once the copy is restored the co-pilot's upload report verifies and is accepted", r.status_code == 200, r.text[:80])
    check("the audit trail names each agreement step",
          all(a in [x["action"] for x in db.q("SELECT action FROM audit WHERE target=?", (cid,))]
              for a in ("Sent documents for e-signature", "Customer e-signed documents", "Marked agreement uploaded")))

    # ---------------- F. co-pilot API ----------------
    print("\n  -- F. co-pilot API")
    pil = httpx.Client(base_url=BASE, headers={"X-Solara-Key": key}, timeout=60)
    lk = pil.get("/api/copilot/lookup", params={"cid": zid}).json()
    check("lookup tells the co-pilot what is missing or doubtful", lk["issues"] and lk["agreement_draft"] is True)
    check("a wrong co-pilot key is refused", httpx.get(f"{BASE}/api/copilot/pending", headers={"X-Solara-Key": "nope"}).status_code == 401)
    check("an unknown customer gets a clear answer", pil.get("/api/copilot/lookup", params={"consumer_no": "000000000000"}).status_code == 404)
    check("an application number that clashes is refused by the report route",
          pil.post("/api/copilot/report", json={"customer_id": clash, "event": "app_no", "app_no": app_no}).status_code == 400)

    # ---------------- G. the extension on a synthetic portal page ----------------
    print("\n  -- G. extension")
    ext_cid = mk(name="Ext Field Tester", mobile="9811122233").json()["customer"]["id"]
    sup.put(f"/api/registration/{ext_cid}", json={"consumer_no": "170077700555", "email": "ext@example.test", "district": "Pune"})
    FORM = """<!doctype html><title>Synthetic portal</title><form id=f onsubmit="window.submitted=(window.submitted||0)+1;return false">
    <label for=nm>Applicant name</label><input id=nm>
    <label for=mb>Mobile number</label><input id=mb>
    <label for=em>Email</label><input id=em>
    <label for=st>State</label><select id=st><option value="">Select</option><option>Maharashtra</option><option>Gujarat</option></select>
    <label for=ct>Category</label><select id=ct><option value="">Select</option><option>Residential</option><option>Commercial</option></select>
    <label for=otp>Enter OTP</label><input id=otp>
    <label for=cap>Captcha code</label><input id=cap>
    <label for=pw>Password</label><input id=pw type=password>
    <label for=vo>Verification code</label><input id=vo>
    <div role=combobox aria-label="District" id=dd style="border:1px solid #888;padding:4px">Select district</div>
    <label><input type=checkbox id=decl> I declare the details are correct</label>
    <button type=submit id=sub>Submit</button><button type=button id=up onclick="window.uploaded=1">Upload</button></form>"""
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", headless=True, viewport={"width": 1300, "height": 900},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await ctx.route("**/portal/k1-fake", lambda route: route.fulfill(body=FORM, content_type="text/html"))
        setcfg = lambda url, k: sw.evaluate(f"chrome.storage.local.set({{url: '{url}', key: '{k}', current: {{cid: '{ext_cid}', at: Date.now()}}}})")

        # disconnected: the server address is wrong
        await setcfg("http://127.0.0.1:9", key)
        pg = await ctx.new_page()
        await pg.goto(BASE + "/portal/k1-fake")
        await pg.wait_for_selector("#solaraRetry", timeout=20000)
        txt = await pg.inner_text("#solaraPanel")
        check("a disconnected co-pilot says Solara is not reachable and offers Try again", "not reachable" in txt, txt[:90])
        check("nothing was filled while disconnected", await pg.input_value("#nm") == "")
        await setcfg(BASE, "sk_wrong_key")
        await pg.click("#solaraRetry")
        await pg.wait_for_function("document.querySelector('#solaraPanel').innerText.includes('not recognised')", timeout=20000)
        check("a wrong key is explained", True)

        # connected: the person has already typed and chosen things
        await setcfg(BASE, key)
        await pg.reload()
        await pg.wait_for_selector("#solaraFill", timeout=20000)
        txt = await pg.inner_text("#solaraPanel")
        check("the panel lists what is missing or doubtful before filling",
              "to sort out in Solara first" in txt and "missing" in txt, txt[:160].replace("\n", " "))
        check("with open issues the fill button says so", "Fill anyway" in await pg.inner_text("#solaraFill"))
        await pg.focus("#mb"); await pg.keyboard.type("9000000001")              # the person types a mobile
        await pg.focus("#st"); await pg.keyboard.press("ArrowDown"); await pg.keyboard.press("ArrowDown")  # chooses Gujarat
        chosen = await pg.input_value("#st")
        await pg.click("#solaraFill")
        await pg.wait_for_selector("#solaraFilled")
        panel = await pg.inner_text("#solaraFilled")
        check("a field the person typed is kept", await pg.input_value("#mb") == "9000000001")
        check("a dropdown the person chose is kept", await pg.input_value("#st") == chosen == "Gujarat", chosen)
        check("an untouched field is filled", await pg.input_value("#nm") != "" and await pg.input_value("#em") == "ext@example.test")
        check("an untouched native dropdown is filled", await pg.input_value("#ct") == "Residential",
              f"{await pg.input_value('#ct')!r} / {panel.replace(chr(10), ' ')[:200]}")
        check("OTP, CAPTCHA, verification code and password are left empty",
              [await pg.input_value(s_) for s_ in ("#otp", "#cap", "#vo", "#pw")] == ["", "", "", ""])
        check("the declaration is not ticked", not await pg.is_checked("#decl"))
        check("nothing was submitted or uploaded", await pg.evaluate("(window.submitted||0) + (window.uploaded||0)") == 0)
        check("a custom dropdown is not clicked open; the panel says what to pick",
              "district" in panel.lower() and "yourself" in panel and await pg.inner_text("#dd") == "Select district", panel.replace("\n", " ")[:160])
        check("the panel says what was kept", "Kept 2" in panel, panel.replace("\n", " ")[:120])

        # the page refuses a value (a script clears it), and Solara does not claim success
        await pg.reload()
        await pg.evaluate("""document.querySelector('#em').addEventListener('input', e => { e.target.value = ''; })""")
        await pg.wait_for_selector("#solaraFill")
        await pg.click("#solaraFill")
        await pg.wait_for_selector("#solaraFilled")
        panel = await pg.inner_text("#solaraFilled")
        check("a value the page rejects is reported, not counted as filled", "did not accept" in panel and "mail" in panel.lower(), panel.replace("\n", " ")[:160])

        # an application number Solara refuses must not be shown as saved
        await ctx.route("**/portal/k1-ack", lambda route: route.fulfill(content_type="text/html", body=f"""<!doctype html>
          <table><tr><td>Consumer Number</td><td>170077700555</td></tr><tr><td>Application Number</td><td>{app_no}</td></tr></table>"""))
        pg2 = await ctx.new_page()
        await pg2.goto(BASE + "/portal/k1-ack")
        await pg2.wait_for_selector("#solaraPanel :text('NOT saved')", timeout=20000)
        check("a refused application number is shown as NOT saved", True)
        check("the customer record did not take it", db.one("SELECT application_no FROM customers WHERE id=?", (ext_cid,))["application_no"] in (None, ""))
        await ctx.close()

    # ---------------- I. dashboard ----------------
    print("\n  -- I. dashboard")
    async with async_playwright() as p:
        br = await p.chromium.launch()
        dash = await br.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        dash.on("pageerror", lambda ex: errs.append(str(ex)))
        await dash.goto(BASE)
        await dash.click('[data-as="r.deshmukh"]')
        await dash.wait_for_selector("#shell:not([hidden])")
        await dash.click('.navitem[data-view="reg"]')
        await dash.click("#regNew")
        await dash.fill("#nName", "Zubin Karandikar")
        await dash.click("#regCreate")
        await dash.wait_for_selector("#regDupe", timeout=15000)
        check("adding a duplicate shows who it matches and offers to open them",
              "Open SS-" in await dash.inner_text("#regDupe") and "Add as a new customer anyway" in await dash.inner_text("#regCreate"))
        await dash.fill("#nName", "Zubin Karandikar Junior")
        await dash.click("#regCreate")
        await dash.wait_for_selector("#regDupe", timeout=15000)
        check("changing the name takes back the override", "anyway" in await dash.inner_text("#regCreate")
              and await dash.get_attribute("#regCreate", "data-force") != "Zubin Karandikar Junior|")
        await dash.keyboard.press("Escape")
        await dash.click(f'[data-reg="{zid}"]')
        await dash.wait_for_selector("#regIssues", timeout=15000)
        check("the registration screen lists what to sort out before registering",
              "missing" in (await dash.inner_text("#regIssues")).lower())
        await dash.click(f'[data-reg="{cid}"]')
        await dash.wait_for_selector("#regAgrCheck", timeout=15000)
        txt = await dash.inner_text("#regAgrCheck")
        check("a signed agreement shows whether it verified, and the draft warning is on screen",
              "verified" in txt and "DRAFT" in await dash.inner_text("body"), txt[:90])
        check("no JavaScript errors in the dashboard", not errs, "; ".join(errs[:2]))
        await br.close()

    # ---------------- H. human-in-the-loop, by inspection of the code itself ----------------
    print("\n  -- H. human-in-the-loop rules in the extension source")
    src = (EXT / "panel.js").read_text(encoding="utf-8") + (EXT / "background.js").read_text(encoding="utf-8")
    code = re.sub(r"//.*", "", src)
    # the one place a click is sent: opening a dropdown and choosing its option (a field value, like typing)
    pick = re.search(r"async function pickCustom\(.*?\n  \}\n", code, re.S)
    rest = code.replace(pick.group(0), "") if pick else code
    card = re.search(r"function openApplyCard\(\w*\) \{.*?\n  \}\n", rest, re.S)   # opens one page; never submits
    rest = rest.replace(card.group(0), "") if card else rest
    PRESS_BLOCK = code[code.index("const PRESS = {"):code.index("function openApplyCard")]
    presses = set(re.findall(r"^    (\w+): \{ find:", code, re.M))   # the only buttons ever pressed for the owner
    check("the extension presses only three non-submitting buttons: the card, the vendor Yes, Fetch Details",
          presses == {"card", "vendor", "fetch"} and "submit" not in PRESS_BLOCK.lower(), str(presses))
    clicks = re.findall(r"(\w+(?:\[0\])?)\.dispatchEvent\(new MouseEvent", pick.group(0)) if pick else []
    sels = re.search(r"const boxOf = .*?\n", code).group(0) + re.search(r"const OPTS = .*?\n", code).group(0)
    check("the extension never clicks, submits or ticks anything on a portal (only a dropdown and its option)",
          not re.search(r"\.click\(|\.submit\(|requestSubmit|\.checked\s*=|dispatchEvent\(new (Mouse|Pointer)Event", rest)
          and pick is not None and set(clicks) <= {"box", "hit[0]"} and not re.search(r"(?i)button|checkbox|submit|input", sels),
          f"clicks in pickCustom on: {sorted(set(clicks))}")
    check("OTP, CAPTCHA and password fields are excluded by rule and by guard",
          "otp|captcha" in code and "humanOnly" in code and "'password'" in code)
    check("it asks for no powers beyond Solara and the listed portals",
          json.loads((EXT / "manifest.json").read_text())["permissions"] == ["storage"])
    check("no CAPTCHA solver, stealth or automation library is referenced",
          not re.search(r"(?i)2captcha|anticaptcha|puppeteer-extra|stealth|webdriver", code))

    print("\n  reset:", client("r.deshmukh").post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for f_ in FAIL:
        print("   failed:", f_)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
