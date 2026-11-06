"""KPI 1 audit: every defect ever registered against milestone 1, every finding of the independent
review, and what the live national portal showed, fired as one test, each case logged.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/k1_audit.py                       (in another)

Writes docs/k1-audit/k1_audit_log.json and docs/k1-audit/k1_audit_log.md: for each case its ID, the
area, the input, what K1 requires, what Solara did, and PASS or FAIL. Resets the demo before and
after. Synthetic data only; the live portal is never contacted by this test.
"""
import asyncio, base64, io, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import httpx
from PIL import Image, ImageDraw
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, closeout, valid, config  # noqa: E402
import fixtures as fx  # noqa: E402

BASE = "http://127.0.0.1:8900"
ROOT = Path(__file__).resolve().parent.parent
LOG, FAIL = [], []


def case(cid, area, inp, want, ok, got):
    LOG.append({"id": cid, "area": area, "input": inp, "expected": want, "actual": str(got)[:300],
                "result": "PASS" if ok else "FAIL", "at": datetime.now().isoformat(timespec="seconds")})
    if not ok:
        FAIL.append(cid)
    print(f"  {'PASS' if ok else 'FAIL'}  {cid:6s} {area}: {inp}" + ("" if ok else f"  — got {str(got)[:160]}"))


def client(user):
    c = httpx.Client(base_url=BASE, timeout=120, follow_redirects=True)
    c.post("/api/login", json={"username": user, "password": "demo"}).raise_for_status()
    return c


def drawn():
    im = Image.new("RGBA", (420, 140), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(20, 90), (80, 30), (130, 100), (190, 40), (260, 95), (390, 50)], fill=(10, 20, 60, 255), width=4)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def detail(r):
    try:
        return r.json().get("detail", "")
    except Exception:
        return r.text[:120]


async def main():
    sup, op = client("r.deshmukh"), client("s.kale")
    sup.post("/api/demo/reset")
    if not db.one("SELECT 1 FROM signatures WHERE role='vendor'"):
        sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"}).raise_for_status()
    fx.register_consumer()
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        bill = await fx.bill_pdf(pg)
        await b.close()

    def new(name, mobile=None):
        r = sup.post("/api/customers", json={"name": name, **({"mobile": mobile} if mobile else {}), "allow_duplicate": True})
        r.raise_for_status()
        return r.json()["customer"]["id"]

    # ---------------- D01: two operators adding customers at once ----------------
    print("\n  -- the defect register (K1-D01 .. D15)")
    with ThreadPoolExecutor(12) as ex:
        rs = list(ex.map(lambda i: httpx.post(BASE + "/api/customers", cookies=sup.cookies,
                                              json={"name": f"Parallel Test {chr(65 + i)}", "allow_duplicate": True}, timeout=60), range(12)))
    ids = {r.json()["customer"]["id"] for r in rs if r.status_code == 200}
    case("D01", "create customer", "12 customers added at the same moment", "12 x 200, 12 different IDs",
         all(r.status_code == 200 for r in rs) and len(ids) == 12, [r.status_code for r in rs])

    # ---------------- D02, D11: the consumer number ----------------
    cid = new("Audit Customer")
    sup.put(f"/api/registration/{cid}", json={"consumer_no": "170055509871"})
    r = sup.put(f"/api/registration/{cid}", json={"consumer_no": "abc"})
    keep = db.one("SELECT consumer_no FROM customers WHERE id=?", (cid,))["consumer_no"]
    case("D02", "details: consumer no.", "'abc' over a saved number", "400; the saved number kept",
         r.status_code == 400 and keep == "170055509871", (r.status_code, keep))
    for bad in ("123456789", "1234567890123", "000000000000"):
        r = sup.put(f"/api/registration/{cid}", json={"consumer_no": bad})
        case("D11", "details: consumer no.", repr(bad), "400", r.status_code == 400, (r.status_code, detail(r)))
    r = sup.put(f"/api/registration/{cid}", json={"consumer_no": "1700-5550-9871"})
    case("D11", "details: consumer no.", "'1700-5550-9871' (hyphens)", "accepted as 170055509871",
         r.status_code == 200 and db.one("SELECT consumer_no FROM customers WHERE id=?", (cid,))["consumer_no"] == "170055509871", r.status_code)

    # ---------------- D03: installation cost, on both screens ----------------
    for raw, want in (("250000.50", "250000.50"), ("2,50,000.75", "250000.75"), ("₹2,10,000", "210000"), ("Rs 285000", "285000")):
        for route in ("registration", "closeout"):
            r = sup.put(f"/api/{route}/{cid}", json={"rts_cost": raw})
            got = closeout.data(cid)[1].get("rts_cost")
            case("D03", f"{route} page: cost", repr(raw), f"saved as {want}", r.status_code == 200 and got == want, (r.status_code, got))
    for raw in ("Rs 1.5 lakh", "-250000", "0", "999999999999", "abc"):
        for route in ("registration", "closeout"):
            r = sup.put(f"/api/{route}/{cid}", json={"rts_cost": raw})
            case("D03", f"{route} page: cost", repr(raw), "400, nothing saved", r.status_code == 400, (r.status_code, detail(r)))

    # ---------------- D09: names ----------------
    for bad in ("123", "@@@ ###", "Priya1234", "<script>x</script>", "A" * 81):
        r = sup.put(f"/api/registration/{cid}", json={"name": bad})
        case("D09", "details: name", repr(bad[:30]), "400", r.status_code == 400, (r.status_code, detail(r)))
    for good in ("A. K. Sharma", "D’Souza Maria", "Mary D'Souza", "प्रिया कुलकर्णी", "कऱ्हाडे‍ संजय", "Rajendra Kumar Venkataraman Subramaniam Iyer"):
        r = sup.put(f"/api/registration/{cid}", json={"name": good})
        case("D09/R7", "details: name", repr(good), "accepted", r.status_code == 200, (r.status_code, detail(r)))

    # ---------------- D10: Aadhaar, on both screens ----------------
    r = sup.put(f"/api/registration/{cid}", json={"aadhaar": "9999 4105 7058"})
    case("D10", "details: Aadhaar", "a valid full number 9999 4105 7058", "200; only 7058 kept",
         r.status_code == 200 and closeout.data(cid)[1].get("aadhaar_last4") == "7058", closeout.data(cid)[1].get("aadhaar_last4"))
    for bad in ("9999 4105 7050", "abcd", "12", "99999999", "0123 4567 8901"):
        r = sup.put(f"/api/registration/{cid}", json={"aadhaar": bad})
        case("D10", "details: Aadhaar", repr(bad), "400", r.status_code == 400, (r.status_code, detail(r)))
    r = sup.put(f"/api/closeout/{cid}", json={"aadhaar_last4": "999941057058"})
    stored = closeout.data(cid)[1].get("aadhaar_last4")
    row = db.one("SELECT data FROM closeout WHERE customer_id=?", (cid,))["data"]
    case("R1", "close-out page: Aadhaar", "full number in 'last 4 digits only'", "only 7058 stored; the full number nowhere",
         r.status_code == 200 and stored == "7058" and "999941057058" not in row, (r.status_code, stored))
    audits = json.dumps(db.q("SELECT * FROM audit"))
    case("R1", "audit trail", "after the Aadhaar was typed", "the full number is not in the audit trail", "999941057058" not in audits, "checked")

    # ---------------- D12: mobile, on both screens ----------------
    for raw in ("abcdefghij", "12345", "5028144599"):
        for route in ("registration", "closeout"):
            r = sup.put(f"/api/{route}/{cid}", json={"mobile": raw})
            case("D12", f"{route} page: mobile", repr(raw), "400", r.status_code == 400, (r.status_code, detail(r)))
    for raw in ("+91 90281 44599", "+91-90281-44599", "090281 44599", "9028144599"):
        r = sup.put(f"/api/registration/{cid}", json={"mobile": raw})
        case("M1", "details: mobile", repr(raw), "accepted as 9028144599",
             r.status_code == 200 and closeout.data(cid)[1].get("mobile") == "9028144599", (r.status_code, closeout.data(cid)[1].get("mobile")))
    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    maxes = [int(x) for x in re.findall(r"mobile: \{ hint: '[^']*', max: (\d+)", js) + re.findall(r'id="nMobile"[^>]*maxlength="(\d+)"', js)]
    case("M1", "dashboard boxes", "maxlength of the mobile boxes", "room for '+91 90281 44599' (15)", maxes and min(maxes) >= 15, maxes)

    # ---------------- D13: wrong-typed input ----------------
    for path, body in (("/api/registration/" + cid, {"name": 123}), ("/api/registration/" + cid, {"kw": [1]}),
                       ("/api/registration/" + cid, {"mobile": {"a": 1}}), ("/api/closeout/" + cid, {"mobile": [1]}),
                       ("/api/closeout/" + cid, {"aadhaar_last4": {"x": 1}}), ("/api/customers", {"name": ["a"]})):
        r = sup.put(path, json=body) if "customers" not in path else sup.post(path, json=body)
        case("D13", "wrong-typed input", f"{path} {body}", "400, never 500", r.status_code == 400, r.status_code)
    r = httpx.post(BASE + "/api/login", json={"username": 1, "password": None})
    case("D13", "wrong-typed input", "login with a number as username", "400 or 401, never 500", r.status_code in (400, 401), r.status_code)

    # ---------------- D04, R6: the application number ----------------
    ready = new("Ready Customer", "9028144599")
    sup.post(f"/api/registration/{ready}/document", params={"kind": "bill"}, files={"file": ("bill.pdf", bill, "application/pdf")})
    sup.post(f"/api/registration/{ready}/document", params={"kind": "aadhaar"}, files={"file": ("a.jpg", fx.aadhaar_photo(), "image/jpeg")})
    sup.post(f"/api/registration/{ready}/confirm", json={"key": "bill_name", "value": fx.NEW["billed_name"]})
    sup.put(f"/api/registration/{ready}", json={"kw": "3", "rts_cost": "210000", "email": "priya.k@example.com"})
    r = sup.post(f"/api/registration/{ready}/mark", json={"step": "registered", "app_no": "NP-MHSED26-3522641"})
    case("M2", "application no.", "a Maharashtra number one digit short", "400", r.status_code == 400, (r.status_code, detail(r)))
    r = sup.post(f"/api/registration/{ready}/mark", json={"step": "registered", "app_no": "NP-MHSED26-35226411"})
    case("D04", "application no.", "first number NP-MHSED26-35226411", "saved", r.status_code == 200, (r.status_code, detail(r)))
    r = op.post(f"/api/registration/{ready}/mark", json={"step": "registered", "app_no": "NP-MHSED26-35226412"})
    case("D04", "application no.", "an operator registers again with another number", "400; the first kept",
         r.status_code == 400 and db.one("SELECT application_no FROM customers WHERE id=?", (ready,))["application_no"] == "NP-MHSED26-35226411", r.status_code)
    other = new("Other Customer")
    db.ex("UPDATE customers SET application_no='NP-MHSED26-35226499' WHERE id=?", (other,))
    n0 = db.one("SELECT COUNT(*) k FROM audit WHERE action='Replaced application number'")["k"]
    r = sup.post(f"/api/registration/{ready}/mark", json={"step": "registered", "app_no": "NP-MHSED26-35226499", "replace": True})
    n1 = db.one("SELECT COUNT(*) k FROM audit WHERE action='Replaced application number'")["k"]
    case("R6", "application no.", "a supervisor replaces it with a number already on another customer", "400 and no 'Replaced' audit row",
         r.status_code == 400 and n1 == n0, (r.status_code, n1 - n0))
    r = sup.post(f"/api/registration/{ready}/mark", json={"step": "registered", "app_no": "NP-MHSED26-35226488", "replace": True})
    n2 = db.one("SELECT COUNT(*) k FROM audit WHERE action='Replaced application number'")["k"]
    case("R6", "application no.", "a supervisor replaces it correctly", "200 and one audit row",
         r.status_code == 200 and n2 == n0 + 1, (r.status_code, n2 - n0))

    # ---------------- D05, R8: step order ----------------
    bare = new("Bare Customer")
    r = sup.post(f"/api/registration/{bare}/mark", json={"step": "registered", "app_no": "NP-MHSED26-35226400"})
    case("D05", "step order", "register a customer with no documents (typed by hand)", "400", r.status_code == 400, (r.status_code, detail(r)))
    r = sup.post(f"/api/registration/{bare}/mark", json={"step": "accepted"})
    case("D05", "step order", "accept before registering", "400", r.status_code == 400, r.status_code)
    r = sup.post(f"/api/registration/{ready}/agreement")
    case("D05", "step order", "send the agreement before the vendor accepted (Registration)", "400", r.status_code == 400, (r.status_code, detail(r)))
    r = sup.post(f"/api/closeout/{ready}/sign", json={"docs": ["agreement"]})
    case("R8", "step order", "send the agreement before the vendor accepted (Close-out route)", "400", r.status_code == 400, (r.status_code, detail(r)))

    # ---------------- R4: the portal's number from the co-pilot is always kept ----------------
    key = sup.post("/api/copilot/key").json()["key"]
    r = httpx.post(BASE + "/api/copilot/report", headers={"X-Solara-Key": key},
                   json={"customer_id": bare, "event": "app_no", "app_no": "NP-MHSED26-35226401"})
    case("R4", "co-pilot", "number read off the portal for a customer Solara thought not ready", "kept (the portal registered them)",
         r.status_code == 200 and db.one("SELECT application_no FROM customers WHERE id=?", (bare,))["application_no"] == "NP-MHSED26-35226401",
         (r.status_code, detail(r)))

    # ---------------- R2, R3: the owner's mobile and the consumer-number Confirm box ----------------
    m = new("Mobile Customer", "9890022222")
    sup.post(f"/api/registration/{m}/document", params={"kind": "bill"}, files={"file": ("bill.pdf", bill, "application/pdf")})
    r = sup.post(f"/api/registration/{m}/confirm", json={"key": "bill_mobile", "value": fx.NEW["msisdn"]})
    case("R2", "extraction", "confirm the bill's mobile when the owner typed another", "the typed mobile (the OTP phone) kept",
         closeout.data(m)[1].get("mobile") == "9890022222", (r.status_code, closeout.data(m)[1].get("mobile")))
    fields = {f["key"]: f for f in sup.get(f"/api/registration/{m}").json()["fields"]}
    if "consumer_no" in fields:
        r = sup.post(f"/api/registration/{m}/confirm", json={"key": "consumer_no", "value": "abc"})
        case("R3", "extraction", "confirm the consumer number with 'abc'", "400", r.status_code == 400, (r.status_code, detail(r)))
        r = sup.post(f"/api/registration/{m}/confirm", json={"key": "consumer_no", "value": "1700 5550 1234"})
        case("R3", "extraction", "confirm it as '1700 5550 1234'", "stored as 170055501234",
             db.one("SELECT consumer_no FROM customers WHERE id=?", (m,))["consumer_no"] == "170055501234", (r.status_code, detail(r)))

    # ---------------- R11: a correction does not outlive its document ----------------
    sup.post(f"/api/registration/{m}/confirm", json={"key": "tariff", "value": "LT-II COMM"}) if "tariff" in fields else None
    time.sleep(1.1)
    sup.post(f"/api/registration/{m}/document", params={"kind": "bill"}, files={"file": ("bill2.pdf", bill, "application/pdf")})
    got = {f["key"]: f for f in sup.get(f"/api/registration/{m}").json()["fields"]}.get("tariff", {}).get("value")
    case("R11", "extraction", "a hand correction to the bill, then a new bill uploaded", "the new bill's reading wins",
         got == "LT-I RES", got)

    # ---------------- R12: a load value with words ----------------
    db.ex("UPDATE extractions SET value='3.5 kW approx.' WHERE customer_id=? AND field=?", (m, "Sanctioned load (kW)"))
    r = sup.get(f"/api/registration/{m}")
    case("R12", "registration page", "sanctioned load read as '3.5 kW approx.'", "the page loads (no 500)", r.status_code == 200, r.status_code)

    # ---------------- R3 (portal): email ----------------
    st = sup.get(f"/api/registration/{bare}").json()
    case("P3", "details", "a customer with no email", "'email' listed as missing (the portal verifies it by OTP)",
         any("email" in x for x in st["missing"]), st["missing"])

    # ---------------- D14, R10: the public e-sign page ----------------
    sup.post(f"/api/registration/{ready}/mark", json={"step": "accepted"})
    url = sup.post(f"/api/registration/{ready}/agreement").json()["url"]
    page = httpx.get(url + "?error=Your+payment+failed,+call+9123456789").text
    case("D14", "e-sign page", "?error= with crafted text", "the text is not shown", "payment failed" not in page, "checked")
    with httpx.Client(timeout=60, follow_redirects=True) as pub:
        page = pub.post(url + "/verify", data={"digits": "0000"}).text
        case("M6", "e-sign page", "wrong last-4 digits", "told in English and Marathi, with the tries left",
             "tries left" in page and "अंक जुळत नाहीत" in page, "checked" if "tries left" in page else page[:120])
        pub.post(url + "/verify", data={"digits": fx.NEW["consumer_no"][-4:]})
        big = Image.new("1", (9000, 9000), 1)
        buf = io.BytesIO(); big.save(buf, "PNG", optimize=True)
        t0 = time.time()
        page = pub.post(url, data={"approve": ["agreement"], "name": "Priya Kulkarni", "consent": "yes",
                                   "signature": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}).text
        took = time.time() - t0
        case("R10", "e-sign page", f"a 9000x9000 'signature' ({len(buf.getvalue()) // 1024} KB)", "refused in under 2 s, server keeps serving",
             took < 2 and "could not be read" in page and httpx.get(BASE + "/api/me").status_code == 200, f"{took:.2f}s")
        tok = url.rsplit("/", 1)[1]
        closeout.snapshot_path(tok, "agreement", ready).unlink(missing_ok=True)  # as a link sent before copies were kept
        page = pub.post(url, data={"approve": ["agreement"], "name": "D’Souza Priya", "consent": "yes", "signature": drawn()}).text
        case("R7", "e-sign page", "the customer signs as 'D’Souza Priya' (curly apostrophe)", "signed", "Thank you" in page, "signed" if "Thank you" in page else page[:120])
    v = sup.get(f"/api/registration/{ready}/agreement/check").json()
    case("R9", "e-sign evidence", "a link sent before copies were kept is signed", "a copy is kept at signing; the agreement verifies",
         closeout.snapshot_html(tok, "agreement", ready) is not None and v["ok"], v.get("problems") or "verified")
    case("D15", "dashboard", "GET /favicon.ico", "no 404", httpx.get(BASE + "/favicon.ico").status_code in (200, 204), "checked")

    # ---------------- P1, P2: the live portal's hosts ----------------
    print("\n  -- what the live portal showed")
    man = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))
    hosts = man["content_scripts"][0]["matches"]
    case("P1", "co-pilot", "manifest hosts", "consumer. and vendor.pmsuryaghar.gov.in included",
         {"https://consumer.pmsuryaghar.gov.in/*", "https://vendor.pmsuryaghar.gov.in/*"} <= set(hosts), hosts)
    os.environ["SOLARA_MODE"] = "live"
    pl = config.portals()
    os.environ.pop("SOLARA_MODE")
    case("P2", "dashboard links", "live 'Open customer registration' / 'Open vendor login'", "the real login pages",
         pl["pmsg"].startswith("https://consumer.pmsuryaghar.gov.in/") and pl["pmsg_vendor"].startswith("https://vendor.pmsuryaghar.gov.in/"), pl)
    case("P4", "rules", "valid.app_no on 8-digit MH numbers", "NP-MHSED26-12345678 accepted",
         valid.app_no("np-mhsed26-12345678") == "NP-MHSED26-12345678", "checked")

    # ---------------- M3-M5: what the manual review saw on the Registration screen ----------------
    print("\n  -- the Registration screen (manual review findings)")
    u = new("Screen Check Customer")
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1366, "height": 768})
        await pg.goto(BASE, wait_until="networkidle")
        await pg.locator('[data-as="r.deshmukh"]').click()
        await pg.locator('.navitem[data-view="reg"]').click()
        await pg.locator(f'[data-reg="{u}"]').click()
        await pg.wait_for_selector("#r_email")
        case("M3", "details form", "the email box", "marked as needed (*), not 'optional'",
             await pg.locator('label[for="r_email"] .req').count() == 1 and "optional" not in (await pg.inner_text('label[for="r_email"]')).lower(),
             await pg.inner_text('label[for="r_email"]'))
        was = await pg.evaluate("document.querySelector('#r_kw').closest('.field').classList.contains('miss')")
        await pg.fill("#r_kw", "3")
        now = await pg.evaluate("document.querySelector('#r_kw').closest('.field').classList.contains('miss')")
        case("M4", "details form", "type 3 into the highlighted capacity box", "the 'missing' highlight goes as soon as it has a value",
             was and not now, (was, now))
        await pg.fill("#r_rts_cost", "210000")
        shown = await pg.inner_text("#h_rts_cost")
        case("M5", "details form", "type 210000 as the cost", "read back as Rs 2,10,000 (a missed zero shows)", shown == "Rs 2,10,000", shown)
        await b.close()

    sup.post("/api/demo/reset")
    out = ROOT / "docs" / "k1-audit"
    out.mkdir(parents=True, exist_ok=True)
    (out / "k1_audit_log.json").write_text(json.dumps(LOG, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# KPI 1 audit test log", "", f"Run {datetime.now():%d %b %Y %H:%M}, `tests/k1_audit.py`. {len(LOG) - len(FAIL)} of {len(LOG)} cases pass.", "",
          "| # | ID | Area | Input | Expected | Actual | Result |", "|---|---|---|---|---|---|---|"]
    md += [f"| {i} | {x['id']} | {x['area']} | {x['input'][:70].replace('|', '/')} | {x['expected'].replace('|', '/')} | "
           f"{x['actual'][:60].replace('|', '/')} | {x['result']} |" for i, x in enumerate(LOG, 1)]
    (out / "k1_audit_log.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n  log: docs/k1-audit/k1_audit_log.md\n\n  {len(LOG) - len(FAIL)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
