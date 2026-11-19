"""Quotations and the panel's memory.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/quotes.py                         (in another)

- The price list is the quotation templates on file. The owner adds a Word template for a new price in Reports;
  the price is offered at once, the template is filled with each customer's name, place and the date, and the
  portal gets it as a PDF. A template Solara could not fill is refused when it is added, with the reason.
- One customer's own quotation (a PDF, or a Word file turned into a PDF) goes to the portal instead.
- In the panel: the quotation box gets the PDF; a box Solara does not know is taught once and filled from then on.
Synthetic data only; the templates are made here, in the test.
"""
import asyncio, io, sys, zipfile
from datetime import date
import httpx
from playwright.async_api import async_playwright
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, drafts  # noqa: E402
import fixtures as fx  # noqa: E402
from milestone4 import client, show, EXT, BASE  # noqa: E402

CID, CONSUMER, NAME = "SS-2042", "170031277450", "Asha Deshpande"
NEW = "275000"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def docx(lines):
    """A small, valid Word file with one paragraph per line."""
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>' for t in lines)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                   f'{body}<w:sectPr/></w:body></w:document>')
    return buf.getvalue()


TEMPLATE = docx(["Demo Solar Solutions Pvt Ltd", "Outward no. demo/2026/01 Date : 01.01.2026", "Quotation", "To,",
                 "Sample Person", "Sample Town", "Total Rs 2,75,000/-"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
post = lambda c, amount, blob, name="q.docx": c.post("/api/quotes", data={"amount": amount}, files={"file": (name, blob, DOCX)})
text_of = lambda blob: " ".join(zipfile.ZipFile(io.BytesIO(blob)).read("word/document.xml").decode().split())


def pdf_text(blob):
    from pypdf import PdfReader
    return " ".join(" ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(blob)).pages).split())


def price_list(sup, view, op):
    print("\n  -- the owner adds a quotation for a new price")
    sup.delete(f"/api/quotes/{NEW}")
    before = sup.get("/api/quotes").json()
    check("the price list is the quotations on file", len(before["quotes"]) >= 1 and all("amount" in q for q in before["quotes"]),
          str([q["amount"] for q in before["quotes"]]))
    check("a price with no quotation is not accepted for a customer", sup.put(f"/api/registration/{CID}", json={"rts_cost": NEW}).status_code == 400)
    check("a viewer cannot add a quotation", post(view, NEW, TEMPLATE).status_code == 403)
    check("an operator cannot add one either", post(op, NEW, TEMPLATE).status_code == 403)
    bad = [("abc", TEMPLATE), ("5000", TEMPLATE), ("99999999", TEMPLATE), (NEW, b"%PDF-1.4 not a word file"), (NEW, b"PK\x03\x04 broken"),
           (NEW, docx(["Quotation", "Date : 01.01.2026", "no addressee line"])), (NEW, docx(["To,", "Name", "Place", "no date line"]))]
    got = [post(sup, a, b) for a, b in bad]
    check("a wrong amount, a file that is not Word, or a template Solara cannot fill is refused with the reason",
          all(r.status_code == 400 and r.json().get("detail") for r in got), str([(r.status_code, r.text[:50]) for r in got]))
    check("...and nothing was saved by the refusals", sup.get("/api/quotes").json() == before)
    r = post(sup, "Rs 2,75,000", TEMPLATE)
    q = next((q for q in r.json().get("quotes", []) if q["amount"] == NEW), None)
    check("the supervisor adds the Rs 2,75,000 quotation (Rs and commas allowed)", r.status_code == 200 and q and q["own"], r.text[:150])
    check("...in the audit trail", db.one("SELECT 1 FROM audit WHERE action='Quotation template added' AND detail LIKE '%2,75,000%'") is not None)
    r = sup.put(f"/api/registration/{CID}", json={"rts_cost": NEW})
    check("the new price can be picked for a customer at once", r.status_code == 200, r.text[:120])
    r = sup.get(f"/api/registration/{CID}/draft/quotation")
    t = text_of(r.content) if r.status_code == 200 else ""
    check("the quotation is the template with this customer's name and today's date; the rest is untouched",
          NAME in t and f"{date.today():%d.%m.%Y}" in t and "Sample Person" not in t and "01.01.2026" not in t
          and "Outward no. demo/2026/01" in t and "Total Rs 2,75,000/-" in t, t[-260:])
    check("the price list tells the panel too", NEW in httpx.get(f"{BASE}/api/copilot/lookup?cid={CID}", headers=KEY, timeout=120).json()["cost_options"])
    return before


def pdf_and_own(sup, op, before):
    print("\n  -- the portal gets a PDF; one customer's own quotation")
    can = sup.get("/api/quotes").json()["can_pdf"]
    r = httpx.get(f"{BASE}/api/copilot/draft/{CID}/quotation?fmt=pdf", headers=KEY, timeout=180)
    if can:
        check("the quotation goes to the portal as a PDF under 2 MB, with the customer's name in it",
              r.status_code == 200 and r.content.startswith(b"%PDF") and len(r.content) < 2 * 1024 * 1024 and NAME in pdf_text(r.content),
              f"{r.status_code} {len(r.content)} bytes")
    else:
        check("with no Word or LibreOffice on this computer the panel is told why there is no PDF (not a broken file)",
              r.status_code == 400 and "Word" in r.text, r.text[:120])
    own = drafts.agreement_pdf("Own Quotation Holder", "1 Test Lane, Pune")   # any real PDF stands in for the customer's own file
    r = op.post(f"/api/registration/{CID}/quotation", files={"file": ("my quotation.pdf", own, "application/pdf")})
    check("an operator uploads this customer's own quotation as a PDF", r.status_code == 200 and r.json()["quotation_own"] is True, r.text[:120])
    r = httpx.get(f"{BASE}/api/copilot/draft/{CID}/quotation?fmt=pdf", headers=KEY, timeout=60)
    check("...and that exact file is what goes to the portal for them", r.status_code == 200 and r.content == own)
    check("another customer still gets the template, not this file",
          httpx.get(f"{BASE}/api/copilot/draft/SS-2048/quotation?fmt=pdf", headers=KEY, timeout=180).content != own)
    r = op.post(f"/api/registration/{CID}/quotation", files={"file": ("notes.txt", b"just some text", "text/plain")})
    check("a file that is neither a PDF nor Word is refused", r.status_code == 400, r.text[:100])
    if can:
        r = op.post(f"/api/registration/{CID}/quotation", files={"file": ("q.docx", TEMPLATE, DOCX)})
        got = httpx.get(f"{BASE}/api/copilot/draft/{CID}/quotation?fmt=pdf", headers=KEY, timeout=60).content
        check("their own quotation sent as a Word file is kept as a PDF", r.status_code == 200 and got.startswith(b"%PDF") and "Sample Person" in pdf_text(got))
    r = op.delete(f"/api/registration/{CID}/quotation")
    check("removing it brings the template back", r.status_code == 200 and r.json()["quotation_own"] is False
          and op.delete(f"/api/registration/{CID}/quotation").status_code == 404)

    print("\n  -- removing a quotation")
    check("only a supervisor removes one", op.delete(f"/api/quotes/{NEW}").status_code == 403)
    folder = next((q["amount"] for q in before["quotes"] if q.get("file")), None)
    if folder:
        check("a quotation from the folder is not removed from Solara", sup.delete(f"/api/quotes/{folder}").status_code == 404)
    r = sup.delete(f"/api/quotes/{NEW}")
    check("the supervisor removes the one added here; the customer still at that price is named",
          r.status_code == 200 and CID in r.json()["using"] and NEW not in [q["amount"] for q in r.json()["quotes"]], r.text[:160])
    check("...and that price is no longer accepted for anyone else", sup.put("/api/registration/SS-2048", json={"rts_cost": NEW}).status_code == 400)
    back = next(q["amount"] for q in before["quotes"])
    sup.put(f"/api/registration/{CID}", json={"rts_cost": back}).raise_for_status()
    return can


SFR = f'''<h3>Site Feasibility Report</h3><table><tr><td>Consumer Number</td><td>{CONSUMER}</td></tr></table>
<div class="fg"><label for="amt">Quotation Amount (Rs.)</label><input id="amt" type="text"></div>
<div class="fg"><label for="qd">Quotation Document (PDF only, Maximum Size 2 MB)</label><input type="file" id="qd" accept=".pdf"></div>'''
STRANGE = f'''<h3>Applicant details</h3><table><tr><td>Consumer Number</td><td>{CONSUMER}</td></tr></table>
<div class="fg"><label for="lm">Nearest landmark of the premises</label><input id="lm" type="text"></div>
<div class="fg"><label for="pc">PIN Code</label><input id="pc" type="text"></div>
<div class="fg"><label for="otp">Enter OTP</label><input id="otp" type="text"></div>'''


def agreement_draft(sup, op):
    print("\n  -- the agreement draft")
    draft = drafts.agreement_template().read_bytes()          # the draft this install already uses
    was_own = drafts.own_agreement().exists()
    up = lambda c, blob: c.post("/api/templates/agreement", files={"file": ("draft.pdf", blob, "application/pdf")})
    check("only a supervisor uploads the agreement draft", up(op, draft).status_code == 403)
    import fitz
    blank = fitz.open(); blank.new_page().insert_text((72, 72), "A letter that is not the agreement"); other = blank.tobytes()
    r = up(sup, other)
    check("a PDF Solara cannot fill is refused, with what the draft needs", r.status_code == 400 and "Name / Address / Sign / Date" in r.text, r.text[:160])
    check("a file that is not a PDF is refused", up(sup, b"PK not a pdf").status_code == 400)
    r = up(sup, draft)
    check("the draft is saved with the data and used from then on",
          r.status_code == 200 and r.json()["agreement"] == "own" and drafts.agreement_template() == drafts.own_agreement(), r.text[:120])
    made = sup.get(f"/api/registration/{CID}/draft/agreement")
    check("the customer's agreement is made from it, with their name", made.status_code == 200 and NAME in pdf_text(made.content), str(made.status_code))
    if not was_own:
        drafts.own_agreement().unlink()


async def panel(can):
    print("\n  -- in the Chrome panel")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            fx.browser_profile(), channel="chromium", headless=True, viewport={"width": 1440, "height": 900},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{KEY['X-Solara-Key']}'}})")
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda ex: errors.append(str(ex)))
        await pg.goto(BASE + "/pmsg/vendor/")
        await pg.wait_for_selector("#solaraPanel")

        await show(pg, SFR)
        await pg.wait_for_selector("#solaraPanel #solaraFill", timeout=30000)
        await pg.click("#solaraFill")
        await pg.wait_for_selector("#solaraFilled", timeout=90000)
        name = await pg.evaluate("(document.querySelector('#qd').files[0] || {}).name || ''")
        txt = await pg.inner_text("#solaraPanel")
        check("the quotation box (PDF only) gets a PDF, and the amount is filled",
              name.endswith(".pdf") and await pg.input_value("#amt") != "", f"{name!r} | {txt[:160]}")

        await show(pg, STRANGE)
        await pg.wait_for_selector("#solaraPanel [data-teach]", state="attached", timeout=30000)
        asked = await pg.inner_text("#solaraTeach")
        check("a box Solara has no rule for is offered to be taught; the OTP box never is",
              "Nearest landmark" in asked and "OTP" not in asked and "PIN" not in asked, asked[:160])
        await pg.evaluate("document.querySelector('#solaraTeach').open = true")
        await pg.select_option("#solaraPanel [data-teach='0']", "address")
        await pg.wait_for_function("document.querySelector('#solaraPanel').dataset.taught === 'address'", timeout=20000)
        taught = await pg.input_value("#lm")
        check("the owner says which value goes there: it is filled now", taught != "", taught)
        await show(pg, "<h3>My Application</h3><p>Another page of the portal.</p>")
        await pg.wait_for_function("!document.querySelector('#solaraPanel #solaraFill')", timeout=30000)
        await show(pg, STRANGE)                       # the same page, opened again later
        await pg.wait_for_selector("#solaraPanel #solaraFill", timeout=30000)
        check("...and it is not asked about again", await pg.query_selector("#solaraPanel [data-teach]") is None)
        await pg.click("#solaraFill")
        await pg.wait_for_selector("#solaraFilled", timeout=60000)
        check("...the next time the page opens, Fill puts it there by itself; the OTP box stays empty",
              await pg.input_value("#lm") == taught and await pg.input_value("#otp") == "", await pg.input_value("#lm"))
        await pg.wait_for_selector("#solaraPanel #solaraForget", timeout=30000)
        await pg.click("#solaraForget")
        await pg.wait_for_function("!document.querySelector('#solaraPanel #solaraForget')", timeout=30000)
        left = await sw.evaluate("chrome.storage.local.get({learned: {}}).then(v => Object.keys(v.learned).length)")
        check("'forget what I was taught on this site' takes it back", left == 0, str(left))
        # a site that is not one of the portals: nothing until the owner clicks the Solara button in the toolbar
        other = await ctx.new_page()
        await other.goto(BASE + "/sign/not-a-real-link")
        await other.wait_for_timeout(1500)
        check("on any other site the panel is not there by itself", await other.query_selector("#solaraPanel") is None)
        await other.bring_to_front()
        await sw.evaluate("""async url => { const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
            chrome.action.onClicked.dispatch({ id: tabs[0].id, url }); }""", other.url)
        try:
            await other.wait_for_selector("#solaraPanel", timeout=15000)
            there = True
        except Exception:
            there = False
        check("the Solara button in the toolbar loads the panel on that page", there)
        await other.close()
        # one click connects the helper: Solara's own page hands it the address and a fresh key
        dash = await ctx.new_page()
        await dash.goto(BASE + "/")
        await dash.evaluate("""() => fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: 's.kale', password: 'demo' }) })""")
        await dash.reload()
        await dash.wait_for_selector("#coKey", timeout=30000)
        await dash.click("#coKey")
        try:
            await dash.wait_for_selector("#helperOk", timeout=10000)
        except Exception:
            pass
        got = await sw.evaluate("chrome.storage.local.get(['url', 'key'])")
        check("'Connect the Chrome helper' in Solara connects it in one click: no address or key is copied by hand",
              got.get("url") == BASE and str(got.get("key", "")).startswith("sk_") and got["key"] != KEY["X-Solara-Key"]
              and httpx.get(f"{BASE}/api/copilot/pending", headers={"X-Solara-Key": got["key"]}, timeout=30).status_code == 200, str(got)[:80])
        await dash.close()
        check("no script errors on the portal pages", not errors, "; ".join(errors[:3]))
        await ctx.close()


async def main():
    global KEY
    sup, view, op = client("r.deshmukh"), client("a.more"), client("s.kale")
    print("  reset:", sup.post("/api/demo/reset").json()["runnable"])
    KEY = {"X-Solara-Key": op.post("/api/copilot/key").json()["key"]}
    before = price_list(sup, view, op)
    can = pdf_and_own(sup, op, before)
    agreement_draft(sup, op)
    await panel(can)
    print("\n  reset:", sup.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
