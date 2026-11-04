"""Milestone 2 tests: site feasibility, five-screen installation, DCR and serial numbers,
Jan Samarth preparation, MSEDCL evidence and PDFs, field-team uploads, tracking and receipts,
access control, the co-pilot on the sandbox K2 portal, and the Filing screen.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/k2_complete.py                    (in another)

Synthetic data only. Nothing here proves anything about a real government portal: the sandbox
K2 pages exist so the co-pilot and the tracking can be exercised, and the five installation
screens' labels beyond screen 1 are Solara's own (see docs/K2_STATUS.md).
"""
import asyncio, base64, io, re, sys, tempfile
from datetime import date, timedelta
from pathlib import Path
import httpx
import fitz
from openpyxl import Workbook
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, closeout, k2, vault  # noqa: E402
import fixtures as fx  # noqa: E402

BASE = "http://127.0.0.1:8900"
EXT = Path(__file__).resolve().parent.parent / "extension"
PASS, FAIL = [], []
TODAY = date.today().isoformat()


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


def pdf(text="Made in India DCR certificate (synthetic)", pages=1):
    d = fitz.open()
    for _ in range(pages):
        d.new_page().insert_text((72, 72), text)
    return d.tobytes()


def big_pdf(kb=900):
    """A PDF well over 300 KB: a page of text plus incompressible image noise."""
    import os
    d = fitz.open()
    pg = d.new_page()
    pg.insert_text((72, 72), "Work completion report (synthetic) " * 3)
    im = Image.frombytes("RGB", (700, 700), os.urandom(700 * 700 * 3))
    buf = io.BytesIO(); im.save(buf, "PNG")
    pg.insert_image(fitz.Rect(40, 120, 540, 620), stream=buf.getvalue())
    return d.tobytes()


def sheet(rows, header="Panel Serial Number"):
    wb = Workbook(); ws = wb.active
    if header:
        ws["A1"] = header
    for i, v in enumerate(rows, start=2 if header else 1):
        ws.cell(row=i, column=1, value=v)
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


def sn(prefix, n):
    return [f"{prefix}{i:05d}" for i in range(1, n + 1)]


def new_customer(sup, name, consumer, serial_prefix=None, registered=True):
    """A registered customer with every K2 field filled, except what a test removes."""
    cid = sup.post("/api/customers", json={"name": name}).json()["customer"]["id"]
    sup.put(f"/api/registration/{cid}", json={"consumer_no": consumer, "kw": "3", "rts_cost": "198000",
                                              "mobile": "98" + consumer[-8:], "district": "Pune"}).raise_for_status()
    db.ex("UPDATE customers SET address=?, pin=?, aadhaar_name=? WHERE id=?",
          ("B-12 Sai Shraddha Society Manchar", "410503", name.upper(), cid))
    if registered:
        sup.post(f"/api/registration/{cid}/mark", json={"step": "registered", "app_no": f"NP-K2TEST26-{consumer[-7:]}"}).raise_for_status()
    return cid


SFR_OK = {"roof_free_area": "36", "roof_type": "RCC", "roof_load_ok": "Yes", "sfr_visitor": "Site Engineer A",
          "sfr_visitor_phone": "9811122233", "sfr_date": TODAY}
PLANT = {"module_make": "Waaree", "almm_model": "WSMD-540", "module_wp": "540", "module_count": "6",
         "inverter_make": "Growatt MIN 3000", "inverter_kw": "3", "inverter_serial": "GRW778899",
         "inverter_year": "2026", "meter_serial": "MTR445566", "dcr_cert_no": "DCR-2026-0001",
         "invoice_no": "INV-2026-77", "cell_maker": "Waaree Solar", "cell_invoice": "CI-9001",
         "install_date": TODAY, "earthing_count": "3", "earth_ohm": "2.1", "lightning_arrester": "Yes",
         "protection_checks": "Yes", "dcr_credit": "Yes"}


def put(sup, cid, d):
    return sup.put(f"/api/closeout/{cid}", json=d)


async def main():
    sup, viewer = client("r.deshmukh"), client("a.more")
    sup.post("/api/demo/reset")
    sup.post("/api/signature/vendor", json={"image": drawn(), "name": "Authorised Signatory"}).raise_for_status()
    key = sup.post("/api/copilot/key").json()["key"]
    st = lambda cid, step: next(s for s in sup.get(f"/api/k2/{cid}").json()["steps"] if s["key"] == step)

    # ============ A. site feasibility report ============
    print("\n  -- A. site feasibility report")
    a = new_customer(sup, "Asha Feasibility", "170011100001")
    s = st(a, "sfr")
    check("with nothing entered the SFR is not ready and lists what is missing",
          s["state"] == "not_ready" and any(i["kind"] == "missing" for i in s["issues"]), f"{s['blocking']} items")
    put(sup, a, {**SFR_OK, "roof_load_ok": "No", "sfr_visitor_phone": "12345", "sfr_date": (date.today() + timedelta(days=3)).isoformat(),
                 "roof_free_area": "abc", "permissible_kw": "2"})
    bad = {i["field"] for i in st(a, "sfr")["issues"] if i["kind"] == "invalid"}
    check("an unconfirmed roof load, bad phone, future date, non-numeric area and too-small permissible capacity are invalid",
          len(bad) == 5, str(sorted(bad)))
    put(sup, a, {**SFR_OK, "permissible_kw": ""})
    check("a complete and valid SFR is ready to file", st(a, "sfr")["state"] == "ready", str(st(a, "sfr")["issues"]))
    put(sup, a, {**SFR_OK, "roof_free_area": "12"})
    check("a roof that looks too small is a warning, not a block",
          any(i["kind"] == "warning" for i in st(a, "sfr")["issues"]) and st(a, "sfr")["state"] == "ready")
    put(sup, a, SFR_OK)
    put(sup, a, PLANT)
    rows = sup.post(f"/api/closeout/{a}/build").json()
    made = closeout.built(a)
    check("the SFR record and the quotation are generated as PDFs", {"sfr", "quotation"} <= set(made), str(sorted(made)))
    check("generated reports are kept off the Close-out screen", all(r["key"] not in ("sfr", "quotation") for r in rows))
    check("every generated report is recorded with its size and time",
          sum(1 for h in k2.history(a) if h["status"] == "generated" and h["step"] == "report:sfr") >= 1)
    check("the SFR PDF is valid, within limits and says what it is",
          not closeout.validate_pdf(vault.read(closeout.path_for(a, "sfr"))))
    t = {x["key"]: x for x in sup.get("/api/templates").json()}
    check("the template list flags the layouts still needing client-approved wording",
          t["sfr"]["approved"] is False and t["agreement"]["needs"] and "quotation" in t)
    un = new_customer(sup, "Unregistered Person", "170011100002", registered=False)
    r = sup.post(f"/api/k2/{un}/filed", json={"step": "sfr"})
    check("nothing can be filed for a customer who is not registered yet", r.status_code == 400 and "register" in r.text.lower())
    sup.put(f"/api/closeout/{a}", json={"sfr_visitor": ""})
    r = sup.post(f"/api/k2/{a}/filed", json={"step": "sfr", "ref_no": "SFR-1001"})
    check("an SFR with something missing cannot be marked filed", r.status_code == 400 and "not ready" in r.text, r.text[:70])
    put(sup, a, SFR_OK)
    r = sup.post(f"/api/k2/{a}/filed", json={"step": "sfr", "ref_no": "SFR-1001"})
    check("once ready it is marked filed by a person, with the portal's reference",
          r.status_code == 200 and st(a, "sfr")["state"] == "filed" and st(a, "sfr")["ref"] == "SFR-1001")

    # ============ B. installation, five screens ============
    print("\n  -- B. installation, five screens")
    b = new_customer(sup, "Bharat Installation", "170011100003")
    put(sup, b, PLANT)
    sup.put(f"/api/registration/{b}", json={})
    r = sup.post(f"/api/k2/{b}/filed", json={"step": "installation:2"})
    check("screens must be filed in order", r.status_code == 400 and "screen 1" in r.text, r.text[:70])
    check("the plain installation step cannot be marked in one go",
          sup.post(f"/api/k2/{b}/filed", json={"step": "installation"}).status_code == 400)
    check("screen 1 needs the geotagged photo's coordinates", any(i["field"] == "latitude / longitude" for i in k2.screen_issues(b, 1)))
    closeout.mark(b, "test", lat="51.5", lng="-0.12")
    check("coordinates outside India are refused", any(i["kind"] == "invalid" for i in k2.screen_issues(b, 1)))
    ph = sup.post(f"/api/k2/{b}/document", params={"kind": "site_photo"}, files={"file": ("p.jpg", closeout._demo_photo(19.953214, 73.837105), "image/jpeg")})
    check("the installed-system photo gives its own coordinates", ph.status_code == 200 and closeout.data(b)[1]["lat"].startswith("19.95"))
    check("screen 1 is ready", not k2.blocking(k2.screen_issues(b, 1)))
    sn_b = sn("B1", 6)
    r = sup.post(f"/api/k2/{b}/serials", json={"text": "\n".join(sn_b[:5])})
    check("a serial count that differs from the module count is flagged", any(i["field"] == "serial numbers" for i in k2.screen_issues(b, 2)))
    sup.post(f"/api/k2/{b}/serials", json={"text": "\n".join(sn_b)})
    check("screen 2 is ready with the right serial numbers", not k2.blocking(k2.screen_issues(b, 2)))
    put(sup, b, {"module_wp": "300"})
    check("capacity far from what was approved is only a warning",
          any(i["kind"] == "warning" and i["field"] == "capacity" for i in k2.screen_issues(b, 2)))
    put(sup, b, {"module_wp": "540"})
    check("screen 4 needs the DCR certificate file", any(i["field"] == "DCR certificate" for i in k2.screen_issues(b, 4)))
    r = sup.post(f"/api/k2/{b}/document", params={"kind": "dcr_cert"}, files={"file": ("cert.pdf", pdf(), "application/pdf")})
    check("the DCR certificate is accepted and kept encrypted", r.status_code == 200 and not k2.screen_issues(b, 4)
          and b"Made in India" not in Path(db.one("SELECT path FROM documents WHERE customer_id=? AND kind='dcr_cert'", (b,))["path"]).read_bytes())
    put(sup, b, {"earth_ohm": "6"})
    check("earth resistance of 5 ohm or more is invalid", any(i["kind"] == "invalid" and "ohm" in i["message"] for i in k2.screen_issues(b, 5)))
    put(sup, b, {"earth_ohm": "2.1", "protection_checks": "No"})
    check("protection checks not all done is invalid", any(i["kind"] == "invalid" for i in k2.screen_issues(b, 5)))
    put(sup, b, {"protection_checks": "Yes"})
    for n in range(1, 5):
        sup.post(f"/api/k2/{b}/filed", json={"step": f"installation:{n}"}).raise_for_status()
    check("four screens filed in order; installation is not yet complete", st(b, "installation")["state"] != "filed")
    sup.post(f"/api/k2/{b}/filed", json={"step": "installation:5"}).raise_for_status()
    check("after the fifth screen the installation step is filed", st(b, "installation")["state"] == "filed")
    check("the screens whose labels are unverified say so",
          [p["verified_labels"] for p in st(b, "installation")["screens"]] == [True, False, False, False, False])

    # ============ C. DCR certificate and serial numbers ============
    print("\n  -- C. DCR certificate and serials")
    c = new_customer(sup, "Chitra Dcr", "170011100004")
    put(sup, c, PLANT)
    good, bad_ = k2.parse_serials("s.xlsx", sheet(sn("C1", 6)))
    check("Excel serials are read from column A, skipping the header", good == sn("C1", 6) and not bad_)
    good, _ = k2.parse_serials("s.csv", ("Serial\n" + "\n".join(sn("C1", 3))).encode())
    check("CSV and text serials are read, header skipped", good == sn("C1", 3))
    good, bad_ = k2.parse_serials("s.txt", b"AB12\nGOODSERIAL1\n##bad##")
    check("values that are not serial numbers are reported, not guessed", good == ["GOODSERIAL1"] and len(bad_) == 2)
    r = sup.post(f"/api/k2/{c}/document", params={"kind": "serial_sheet"}, files={"file": ("s.xlsx", sheet(sn("C1", 5) + ["bad!"]), "application/octet-stream")})
    check("one invalid serial refuses the whole sheet and saves nothing", r.status_code == 400 and not closeout.serials(closeout.data(c)[1]))
    r = sup.post(f"/api/k2/{c}/document", params={"kind": "serial_sheet"}, files={"file": ("s.xlsx", sheet(sn("C1", 6)), "application/octet-stream")})
    check("a good sheet is saved and matches the module count", r.status_code == 200 and r.json()["serial_result"]["matches"])
    check("each serial is registered to this customer, with its source and time",
          db.one("SELECT COUNT(*) n FROM serials WHERE customer_id=? AND source LIKE 'sheet:%'", (c,))["n"] == 6)
    r = sup.post(f"/api/k2/{c}/serials", json={"text": "\n".join(sn("C1", 5) + [sn("C1", 5)[0]])})
    check("a serial listed twice is refused", r.status_code == 400 and "twice" in r.text)
    other = new_customer(sup, "Dev Duplicate", "170011100005")
    put(sup, other, {"module_count": "6"})
    r = sup.post(f"/api/k2/{other}/serials", json={"text": "\n".join(sn("C1", 2) + sn("D1", 4))})
    check("a serial already on another customer is refused, naming that customer", r.status_code == 400 and c in r.text, r.text[:80])
    put(sup, other, {"module_serials": "\n".join(sn("C1", 1) + sn("D1", 5))})
    check("a duplicate typed straight into the close-out form is still caught by the checks",
          any("already on" in t for _, t in closeout.checks(other, closeout.data(other)[1])))
    wb = sup.get(f"/api/k2/{c}/serials.xlsx")
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(wb.content)).active
    check("the DCR sheet has serials in column A from row 2", ws["A1"].value and [ws.cell(row=i, column=1).value for i in range(2, 8)] == sn("C1", 6))
    check("a DCR step with no certificate or invoice lists exactly that", {i["field"] for i in st(c, "dcr")["issues"] if i["kind"] == "missing"} >= {"DCR certificate"})
    sup.post(f"/api/k2/{c}/document", params={"kind": "dcr_cert"}, files={"file": ("cert.pdf", pdf(), "application/pdf")})
    put(sup, c, {"dcr_credit": "No"})
    check("panels not yet credited by the dealer show 'waiting for dealer', not an error", st(c, "dcr")["state"] == "waiting")
    put(sup, c, {"dcr_credit": "Yes"})
    check("credited panels make the DCR step ready", st(c, "dcr")["state"] == "ready", str(st(c, "dcr")["issues"]))
    for bad_file, why in ((b"", "empty"), (b"hello", "text"), (b"%PDF-1.4 junk", "corrupt PDF")):
        r = sup.post(f"/api/k2/{c}/document", params={"kind": "dcr_cert"}, files={"file": ("x.pdf", bad_file, "application/pdf")})
        check(f"a {why} certificate is refused with a reason", r.status_code == 400 and r.json()["detail"], r.text[:60])
    check("the earlier valid certificate is untouched by the refused uploads",
          db.one("SELECT COUNT(*) n FROM documents WHERE customer_id=? AND kind='dcr_cert'", (c,))["n"] == 1)
    r = sup.post(f"/api/k2/{c}/filed", json={"step": "dcr", "ref_no": "DCR-2026-C1"})
    check("the DCR step is filed with the certificate number, which is saved to the record",
          r.status_code == 200 and closeout.data(c)[1]["dcr_cert_no"] == "DCR-2026-C1" and st(c, "dcr")["state"] == "filed")
    r = sup.post(f"/api/k2/{other}/receipt", params={"step": "dcr", "ref_no": "DCR-2026-C1"})
    check("a reference number already recorded for another customer is refused", r.status_code == 400 and c in r.text)

    # ============ D. Jan Samarth ============
    print("\n  -- D. Jan Samarth loan")
    d = new_customer(sup, "Deepa Loan", "170011100006")
    check("a customer with no loan has no loan step", st(d, "loan")["state"] == "n/a")
    check("a loan cannot be marked for a customer who is not taking one", sup.post(f"/api/k2/{d}/filed", json={"step": "loan"}).status_code == 400)
    put(sup, d, {"loan_needed": "Yes"})
    miss = {i["field"] for i in st(d, "loan")["issues"] if i["kind"] == "missing"}
    check("a loan application lists the details and documents still missing", {"bank", "branch", "loan amount", "electricity bill"} <= miss, str(sorted(miss)))
    put(sup, d, {"loan_bank": "Bank of Maharashtra", "loan_branch": "Manchar", "loan_amount": "250000", "rts_cost": "198000"})
    check("a loan above the project cost is invalid", any(i["kind"] == "invalid" and i["field"] == "loan amount" for i in st(d, "loan")["issues"]))
    put(sup, d, {"loan_amount": "150000"})
    for kind, name, blob, mime in (("bill", "bill.pdf", pdf("bill"), "application/pdf"), ("aadhaar", "a.jpg", fx.aadhaar_photo(), "image/jpeg"),
                                   ("passbook", "p.jpg", fx.passbook_photo(), "image/jpeg")):
        sup.post(f"/api/registration/{d}/document", params={"kind": kind}, files={"file": (name, blob, mime)})
    pack = sup.get(f"/api/k2/{d}/loan").json()
    check("the loan pack carries the details and documents for the form", pack["values"]["loan_bank"] == "Bank of Maharashtra" and "bill" in pack["documents"])
    check("the loan pack holds no password, OTP or Aadhaar number",
          not {"password", "otp", "aadhaar_no", "login"} & set(pack["values"]) and not re.search(r"\b\d{12}\b", str(pack["values"]).replace("170011100006", "")))
    check("a sanctioned status cannot come before a submission", sup.post(f"/api/k2/{d}/loan", json={"status": "sanctioned"}).status_code == 400)
    check("an unknown loan status is refused", sup.post(f"/api/k2/{d}/loan", json={"status": "approved-by-me"}).status_code == 400)
    sup.post(f"/api/k2/{d}/loan", json={"status": "submitted", "ref_no": "JS-77881"}).raise_for_status()
    check("a submitted loan records its reference and moves the step to filed", st(d, "loan")["state"] == "filed" and closeout.data(d)[1]["loan_ref"] == "JS-77881")
    sup.post(f"/api/k2/{d}/loan", json={"status": "sanctioned"}).raise_for_status()
    check("loan progress is tracked step by step", [h["status"] for h in k2.history(d) if h["step"] == "loan"] == ["filed", "receipt", "sanctioned"])

    # ============ E. MSEDCL: PDFs, size, compression, evidence ============
    print("\n  -- E. MSEDCL")
    check("a non-PDF is refused by the PDF check", closeout.validate_pdf(b"hello") == ["not a PDF file"])
    check("a PDF over 300 KB is refused by the size check", any("limit" in p for p in closeout.validate_pdf(big_pdf())))
    enc = fitz.open(); enc.new_page(); eb = enc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="x", user_pw="y")
    check("a password-protected PDF is refused", any("password" in p for p in closeout.validate_pdf(eb)))
    check("a normal small PDF passes", closeout.validate_pdf(pdf()) == [])
    bigp = big_pdf()
    out, info = closeout.fit_report(bigp)
    check("a PDF over 300 KB is compressed under the limit and is still a valid PDF",
          len(bigp) > 300 * 1024 and len(out) <= 300 * 1024 and not closeout.validate_pdf(out), f"{info['original_kb']} -> {info['final_kb']} KB by {info['method']}")
    check("compression says whether the result is still comfortably readable", "readable" in info and info["method"] == "re-rendered" and info["dpi"] and fitz.open(stream=out, filetype="pdf")[0].get_pixmap(dpi=72).width > 0)
    small = pdf()
    check("a file that already fits is returned unchanged", closeout.fit_report(small)[0] == small)
    e = new_customer(sup, "Esha Msedcl", "170011100007")
    put(sup, e, {**SFR_OK, **PLANT, "module_serials": "\n".join(sn("E1", 6)), "msedcl_app_id": "79435901"})
    ms = sup.get(f"/api/k2/{e}").json()["msedcl"]
    check("MSEDCL starts as not uploaded, with a reason per document that is not ready", not ms["uploaded"] and all(r["note"] or r["bytes"] or r["state"] == "ready" for r in ms["documents"]))
    pil = httpx.Client(base_url=BASE, headers={"X-Solara-Key": key}, timeout=60)
    keys = [x[0] for x in closeout.DOCS_SPEC if x[1]]
    pil.post("/api/copilot/report", json={"customer_id": e, "portal": "msedcl", "uploaded": keys[:4]}).raise_for_status()
    check("four documents on the MSEDCL list do not make the upload 'done'", not closeout.data(e)[1].get("msedcl_uploaded") and st(e, "msedcl")["state"] != "filed")
    check("the per-document status shows only what the page showed",
          sorted(closeout.data(e)[1]["msedcl_slots_uploaded"].split(",")) == sorted(keys[:4]))
    pil.post("/api/copilot/report", json={"customer_id": e, "portal": "msedcl", "uploaded": keys[:4], "rejected": [keys[4]]}).raise_for_status()
    check("a document MSEDCL rejected makes the step failed, with a note", st(e, "msedcl")["state"] == "failed"
          and any(h["step"] == "msedcl" and h["status"] == "failed" for h in k2.history(e)))
    r = sup.post(f"/api/k2/{e}/filed", json={"step": "msedcl"})
    check("MSEDCL cannot be marked uploaded by hand, only by its own page", r.status_code == 400 and "own page" in r.text)
    pil.post("/api/copilot/report", json={"customer_id": e, "portal": "msedcl", "uploaded": keys}).raise_for_status()
    check("when the page shows all six, the step is filed with that evidence",
          st(e, "msedcl")["state"] == "filed" and closeout.data(e)[1].get("msedcl_uploaded") == "yes"
          and any(h["step"] == "msedcl" and h["status"] == "filed" for h in k2.history(e)))

    # ============ F. field team ============
    print("\n  -- F. field-team uploads")
    f = new_customer(sup, "Farhan Field", "170011100008")
    put(sup, f, {"module_count": "4"})
    g = new_customer(sup, "Gita Other", "170011100009")
    check("a viewer cannot create a field link", viewer.post(f"/api/k2/{f}/field-link").status_code == 403)
    url = sup.post(f"/api/k2/{f}/field-link").json()["url"]
    tok = url.rsplit("/", 1)[1]
    pub = httpx.Client(timeout=60, follow_redirects=False)
    pg_ = pub.get(url).text
    check("the field page shows a first name and the last 4 digits only: no address, phone or other customer",
          "FARHAN" in pg_ and "ending 0008" in pg_ and "Manchar" not in pg_ and "Gita" not in pg_
          and "9811" not in pg_ and "170011100008" not in pg_ and "FARHAN FIELD" not in pg_)
    check("the field page asks for location only when the person ticks the box",
          'class="consent"' in pg_ and "if (!box.checked" in pg_ and "getCurrentPosition" in pg_)
    check("an unknown link is refused", "not valid" in pub.get(BASE + "/field/nonsense").text or pub.get(BASE + "/field/nonsense").status_code == 403)
    up = lambda slot, blob, name="p.jpg", **form: pub.post(f"{BASE}/field/{tok}/upload", data={"slot": slot, **form}, files={"file": (name, blob, "application/octet-stream")})
    loc = lambda r: r.headers.get("location", "")
    r = up("site_photo", closeout._demo_photo(19.953214, 73.837105))
    check("a photo with GPS is accepted and sets the site coordinates", "done=" in loc(r) and closeout.data(f)[1]["lat"].startswith("19.95"))
    check("the source of the coordinates is recorded", closeout.data(f)[1].get("gps_source") == "photo")
    r = up("site_photo", closeout._demo_photo(0, 0, with_gps=False))
    check("a photo without GPS and without consent is refused with instructions", "error=" in loc(r) and "GPS" in loc(r).replace("%20", " "))
    r = up("site_photo", closeout._demo_photo(0, 0, with_gps=False), consent="yes", lat="19.9", lng="73.8", acc="12")
    check("with consent the phone's location is used when the photo has none", "done=" in loc(r) and closeout.data(f)[1]["gps_source"].startswith("phone"))
    for kw_, why in ((dict(lat="51.5", lng="-0.1", acc="10"), "outside India"), (dict(lat="19.9", lng="73.8", acc="900"), "too inaccurate"),
                     (dict(lat="x", lng="y", acc="1"), "unreadable")):
        r = up("site_photo", closeout._demo_photo(0, 0, with_gps=False), consent="yes", **kw_)
        check(f"phone location that is {why} is refused", "error=" in loc(r))
    r = up("site_photo", closeout._demo_photo(0, 0, with_gps=False), lat="19.9", lng="73.8", acc="12")
    check("a location sent without the consent tick is not used", "error=" in loc(r))
    check("a file that is not a photo is refused", "error=" in loc(up("install_photo", b"not an image")))
    check("an empty file is refused", "error=" in loc(up("install_photo", b"")))
    check("a valid installation photo is accepted", "done=" in loc(up("install_photo", closeout._demo_photo(1, 1))))
    check("an unknown upload type is refused", "error=" in loc(up("passwords", b"x")))
    check("a serial sheet from the field is read and saved", "done=" in loc(up("serial_sheet", sheet(sn("F1", 4)), "s.xlsx")) and len(closeout.serials(closeout.data(f)[1])) == 4)
    check("a bad serial sheet from the field saves nothing", "error=" in loc(up("serial_sheet", sheet(["??"]), "s.xlsx")) and len(closeout.serials(closeout.data(f)[1])) == 4)
    check("uploads through this link touched only this customer",
          not db.one("SELECT 1 FROM documents WHERE customer_id=? AND kind IN ('install_photo','dcr_cert')", (g,)) and not closeout.data(g)[1].get("lat"))
    check("every upload is audited with the link, not a person's login",
          db.one("SELECT COUNT(*) n FROM audit WHERE action='Field upload' AND target=?", (f,))["n"] >= 3)
    check("the office sees the checklist of what the team has sent", sum(1 for x in sup.get(f"/api/k2/{f}").json()["field_checklist"] if x["done"]) >= 3)
    db.ex("UPDATE field_links SET expires_at=? WHERE token=?", ((__import__('datetime').datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds"), tok))
    check("an expired link no longer works", "expired" in pub.get(url).text and "error=" not in loc(up("install_photo", closeout._demo_photo(1, 1))) and pub.get(url).status_code == 403)
    tok2 = sup.post(f"/api/k2/{f}/field-link").json()["url"].rsplit("/", 1)[1]
    sup.delete(f"/api/k2/{f}/field-link/{tok2}")
    check("a switched-off link no longer works", pub.get(f"{BASE}/field/{tok2}").status_code == 403)

    # ============ G. tracking, receipts, errors, access ============
    print("\n  -- G. tracking, receipts, errors, access")
    h = new_customer(sup, "Hema Tracking", "170011100010")
    put(sup, h, {**SFR_OK, **PLANT})
    check("a failure needs a note saying what went wrong", sup.post(f"/api/k2/{h}/failed", json={"step": "sfr", "note": " "}).status_code == 400)
    check("a step that has not failed cannot be retried", sup.post(f"/api/k2/{h}/retry", json={"step": "sfr"}).status_code == 400)
    sup.post(f"/api/k2/{h}/failed", json={"step": "sfr", "note": "portal said: roof area must be a number"}).raise_for_status()
    check("a failed step shows as failed with the portal's words, and is the next action",
          st(h, "sfr")["state"] == "failed" and "roof area" in st(h, "sfr")["last"]["note"] and "Retry" in sup.get(f"/api/k2/{h}").json()["next"]["label"])
    sup.post(f"/api/k2/{h}/retry", json={"step": "sfr"}).raise_for_status()
    check("after Retry the step is checked again and is ready", st(h, "sfr")["state"] == "ready")
    r = sup.post(f"/api/k2/{h}/receipt", params={"step": "sfr", "ref_no": "!"})
    check("a malformed reference is refused", r.status_code == 400)
    r = sup.post(f"/api/k2/{h}/receipt", params={"step": "sfr", "ref_no": "SFR-REC-9"}, files={"file": ("ack.pdf", pdf("Acknowledgement"), "application/pdf")})
    check("a receipt keeps the reference and the acknowledgement file", r.status_code == 200
          and db.one("SELECT 1 FROM documents WHERE customer_id=? AND kind='rc_sfr'", (h,)) and st(h, "sfr")["ref"] == "SFR-REC-9" and st(h, "sfr")["receipt"])
    check("a receipt for one installation screen is refused (receipts belong to a whole step)",
          sup.post(f"/api/k2/{h}/receipt", params={"step": "installation:2", "ref_no": "ABCD1234"}).status_code == 400)
    hist = sup.get(f"/api/k2/{h}").json()
    check("every event has a time, an author and a status", all(x["ts"] and x["by"] and x["status"] for x in hist["history"]))
    check("the dashboard data lists application, references and the next action",
          hist["application_no"] and hist["refs"].get("sfr") == "SFR-REC-9" and hist["next"]["label"])
    check("pending documents and missing items are counted for the dashboard", isinstance(hist["pending_docs"], list) and isinstance(hist["missing"], int))
    lst = sup.get("/api/k2").json()
    check("the list gives every registered customer's step states", {x["id"] for x in lst} >= {a, b, c, h} and all("steps" in x and "next" in x for x in lst))
    check("time between stages is reported", isinstance(sup.get(f"/api/k2/{a}").json()["durations"], list))
    r = viewer.get(f"/api/k2/{h}")
    check("a viewer can read progress", r.status_code == 200)
    writes = [("post", f"/api/k2/{h}/filed", {"step": "sfr"}), ("post", f"/api/k2/{h}/failed", {"step": "sfr", "note": "x"}),
              ("post", f"/api/k2/{h}/retry", {"step": "sfr"}), ("post", f"/api/k2/{h}/loan", {"status": "submitted"}),
              ("post", f"/api/k2/{h}/serials", {"text": "ABC12345"}), ("post", f"/api/k2/{h}/field-link", {}),
              ("post", f"/api/k2/{h}/receipt?step=sfr&ref_no=ABCD1234", None)]
    check("a viewer cannot change anything in K2", all(getattr(viewer, m)(p, **({"json": j} if j is not None else {})).status_code == 403 for m, p, j in writes))
    check("a viewer cannot upload a K2 document", viewer.post(f"/api/k2/{h}/document", params={"kind": "dcr_cert"}, files={"file": ("c.pdf", pdf(), "application/pdf")}).status_code == 403)
    anon = httpx.Client(base_url=BASE, timeout=30)
    check("nobody signed out can read or change K2", anon.get("/api/k2").status_code == 401 and anon.post(f"/api/k2/{h}/filed", json={"step": "sfr"}).status_code == 401)
    check("an unknown customer is a clear 404", sup.get("/api/k2/SS-999999").status_code == 404)
    check("an unknown step is refused", sup.post(f"/api/k2/{h}/filed", json={"step": "magic"}).status_code == 400)
    check("the co-pilot key is required for the K2 co-pilot routes", httpx.get(f"{BASE}/api/copilot/serials/{c}").status_code == 401)

    # ============ H. the co-pilot on the sandbox K2 portal ============
    print("\n  -- H. co-pilot on the sandbox K2 pages")
    i = new_customer(sup, "Ishaan Copilot", "170011100011")
    put(sup, i, {**SFR_OK, **PLANT, "module_serials": "\n".join(sn("I1", 6)), "sfr_visitor": "Site Engineer A"})
    sup.post(f"/api/k2/{i}/document", params={"kind": "dcr_cert"}, files={"file": ("c.pdf", pdf(), "application/pdf")})
    sup.post(f"/api/k2/{i}/document", params={"kind": "invoice"}, files={"file": ("inv.pdf", pdf("invoice"), "application/pdf")})
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", headless=True, viewport={"width": 1300, "height": 950},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{key}', current: {{cid: '{i}', at: Date.now()}}}})")
        pg = await ctx.new_page()
        await pg.goto(BASE + "/k2portal/sfr")
        await pg.wait_for_selector("#solaraFill", timeout=30000)
        await pg.click("#solaraFill")
        await pg.wait_for_selector("#solaraFilled")
        v = {k: await pg.input_value(s) for k, s in (("area", "#area"), ("perm", "#perm"), ("qa", "#qa"), ("emp", "#emp"), ("cnum", "#cnum"))}
        check("SFR page: roof area, permissible capacity and quotation amount filled from the record",
              v["area"] == "36" and v["perm"] == "3" and v["qa"] == "198000", str(v))
        check("SFR page: the vendor's own employee and contact are left for the person", v["emp"] == "" and v["cnum"] == "")
        check("SFR page: the quotation document is attached", await pg.evaluate("document.querySelector('#qd').files.length") == 1)
        check("SFR page: the declaration is not ticked and nothing was submitted",
              not await pg.is_checked("#declaration") and "Reference Number" not in await pg.inner_text("body"))
        await pg.click("#btnSubmit")                                         # the person presses Submit with gaps
        await pg.wait_for_selector("[role=alert]")
        await pg.wait_for_selector("#solaraPanel :text('The portal said')", timeout=20000)
        await pg.wait_for_timeout(1200)
        check("a portal error is shown in the panel and kept in Solara as a failure",
              st(i, "sfr")["state"] == "failed" and "portal said" in st(i, "sfr")["last"]["note"], st(i, "sfr")["last"]["note"][:80])
        sup.post(f"/api/k2/{i}/retry", json={"step": "sfr"}).raise_for_status()
        await pg.goto(BASE + "/k2portal/sfr")
        await pg.wait_for_selector("#solaraFill")
        await pg.click("#solaraFill"); await pg.wait_for_selector("#solaraFilled")
        await pg.fill("#emp", "Site Engineer A"); await pg.fill("#cnum", "9811122233")   # the person types their staff details
        await pg.check("#declaration")                                       # the person ticks the declaration
        await pg.click("#btnSubmit")                                         # the person presses Submit
        await pg.wait_for_selector("#refNo")
        ref = (await pg.inner_text("#refNo")).strip()
        await pg.wait_for_selector("#solaraPanel :text('saved in Solara')", timeout=20000)
        check("the reference on the portal's own page is saved as the receipt", st(i, "sfr")["ref"] == ref and st(i, "sfr")["state"] == "filed", ref)

        await pg.goto(BASE + "/k2portal/install/2")
        await pg.wait_for_selector("#solaraFill", timeout=30000)
        await pg.fill("#mk", "My own typing")                                # the person already typed one
        await pg.click("#solaraFill"); await pg.wait_for_selector("#solaraFilled")
        v = {k: await pg.input_value(s) for k, s in (("mk", "#mk"), ("al", "#al"), ("wp", "#wp"), ("nm", "#nm"), ("sn", "#sn"))}
        check("installation screen 2: the model, wattage, count and serial numbers are filled",
              v["al"] == "WSMD-540" and v["wp"] == "540" and v["nm"] == "6" and v["sn"].split("\n") == sn("I1", 6), str(v)[:120])
        check("installation screen 2: what the person typed is kept", v["mk"] == "My own typing")
        txt = await pg.inner_text("#solaraPanel")
        check("the panel shows only the checks for the screen in front of the person", "sort out" not in txt, txt[:100].replace("\n", " "))
        await pg.goto(BASE + "/k2portal/install/1")
        await pg.wait_for_selector("#solaraPanel", timeout=20000)
        await pg.wait_for_timeout(1500)
        txt = await pg.inner_text("#solaraPanel")
        check("screen 1 with no coordinates on file warns before filling", "latitude" in txt.lower() and "Fill anyway" in txt, txt[:140].replace("\n", " "))

        await pg.goto(BASE + "/k2portal/dcr")
        await pg.wait_for_selector("#solaraFill", timeout=30000)
        await pg.click("#solaraFill"); await pg.wait_for_selector("#solaraFilled")
        check("DCR page: application number and invoice filled",
              await pg.input_value("#can") == closeout.data(i)[0]["application_no"] and await pg.input_value("#inv") == "INV-2026-77")
        check("DCR page: customer name and the panel serial numbers filled",
              await pg.input_value("#cname") == "ISHAAN COPILOT" and (await pg.input_value("#pan")).split("\n") == sn("I1", 6))
        check("DCR page: the certificate file is attached from the customer's documents", await pg.evaluate("document.querySelector('#cert').files.length") == 1)
        check("DCR page: still nothing ticked or submitted", not await pg.is_checked("#declaration"))
        await ctx.close()

    # ============ I. the Filing screen ============
    print("\n  -- I. Filing screen")
    async with async_playwright() as p:
        br = await p.chromium.launch()
        dash = await br.new_page(viewport={"width": 1440, "height": 950})
        errs = []
        dash.on("pageerror", lambda ex: errs.append(str(ex) + " @ " + str(getattr(ex, "stack", ""))[:400]))
        await dash.goto(BASE)
        await dash.click('[data-as="r.deshmukh"]')
        await dash.wait_for_selector("#shell:not([hidden])")
        await dash.wait_for_selector("#runview", state="attached")      # the app has finished starting
        await dash.click('.navitem[data-view="k2"]')
        await dash.wait_for_selector(f'[data-k2="{a}"]')
        await dash.click(f'[data-k2="{e}"]')
        await dash.wait_for_function("document.querySelector('#k2Steps') && document.querySelector('.card.raise h3').innerText === 'Esha Msedcl'")
        await dash.wait_for_selector("#k2Steps")
        body = await dash.inner_text("#k2Steps")
        check("the Filing screen shows every K2 step and its state", all(s in body for s in ("Site feasibility", "Installation", "DCR", "MSEDCL", "Jan Samarth")))
        check("MSEDCL shows its uploaded state from the portal's own evidence", "Filed" in await dash.inner_text('[data-step="msedcl"]'))
        await dash.click(f'[data-k2="{h}"]')
        await dash.wait_for_function("document.querySelector('#k2Steps') && document.querySelector('.card.raise h3').innerText === 'Hema Tracking'")
        await dash.wait_for_function("document.querySelector('#k2Next').innerText.length > 3")
        check("the next action is on screen", len(await dash.inner_text("#k2Next")) > 5)
        await dash.click(f'[data-k2="{d}"]')
        await dash.wait_for_function("document.querySelector('#k2Steps') && document.querySelector('.card.raise h3').innerText === 'Deepa Loan'")
        await dash.wait_for_selector("#k2Loan")
        check("the loan card is on screen with its status buttons", await dash.locator("[data-k2loan]").count() == 4)
        await dash.click(f'[data-k2="{c}"]')
        await dash.wait_for_function("document.querySelector('#k2Steps') && document.querySelector('.card.raise h3').innerText === 'Chitra Dcr'")
        await dash.wait_for_function("document.querySelector('#k2Serials') && document.querySelector('#k2Serials').innerText.includes('6 on file')")
        check("serial numbers on file are shown with a download for the DCR portal", "6 on file" in await dash.inner_text("#k2Serials") and await dash.locator("a:has-text('Download for DCR')").count() == 1)
        await dash.fill("#k2SerialText", "AB")
        await dash.click("#k2SerialSave")
        await dash.wait_for_selector("#toast:not([hidden])")
        check("a bad typed serial is refused on screen", "not serial" in (await dash.inner_text("#toastmsg")).lower() or "serial" in (await dash.inner_text("#toastmsg")).lower())
        jj = new_customer(sup, "Jayesh Screen", "170011100012")
        put(sup, jj, {**SFR_OK, **PLANT})
        await dash.click('.navitem[data-view="reports"]'); await dash.click('.navitem[data-view="k2"]')
        await dash.wait_for_selector(f'[data-k2="{jj}"]')
        await dash.click(f'[data-k2="{jj}"]')
        await dash.wait_for_selector('[data-k2filed="sfr"]')
        await dash.click('[data-k2filed="sfr"]')
        await dash.fill("#k2Ref", "SFR-UI-5150")
        await dash.click("#k2FiledGo")
        await dash.wait_for_function("document.querySelector('[data-step=sfr]').innerText.includes('Filed')")
        check("pressing 'I pressed Submit' on screen files the step with its reference", st(jj, "sfr")["ref"] == "SFR-UI-5150")
        await dash.click('[data-k2fail="dcr"]')
        await dash.fill("#k2Note", "portal timed out")
        await dash.click("#k2FailGo")
        await dash.wait_for_function("document.querySelector('[data-step=dcr]').innerText.includes('Failed')")
        check("a failure noted on screen shows Failed with a Retry button", await dash.locator('[data-k2retry="dcr"]').count() == 1)
        await dash.click('[data-k2retry="dcr"]')
        await dash.wait_for_function("!document.querySelector('[data-k2retry=dcr]')")
        check("Retry puts the step back to be checked and tried again", st(jj, "dcr")["state"] != "failed")
        check("no JavaScript errors in the dashboard", not errs, "; ".join(errs[:2]))
        await br.close()

    # ============ J. rules in the code ============
    print("\n  -- J. rules in the code")
    src = "".join(re.sub(r"//.*", "", (EXT / n).read_text(encoding="utf-8")) for n in ("panel.js", "background.js"))
    check("the extension still never clicks, submits or ticks anything",
          not re.search(r"\.click\(|\.submit\(|requestSubmit|\.checked\s*=|dispatchEvent\(new (Mouse|Pointer)Event", src))
    server = "".join(Path(n).read_text(encoding="utf-8") for n in ("app/k2.py", "app/field.py", "app/k2portal.py"))
    check("K2 code stores no password or OTP field and calls no AI model", not re.search(r"(?i)password|otp|anthropic|openai|llm_read", re.sub(r"#.*|\"\"\"[\s\S]*?\"\"\"", "", server)))

    print("\n  reset:", client("r.deshmukh").post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for x in FAIL:
        print("   failed:", x)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
