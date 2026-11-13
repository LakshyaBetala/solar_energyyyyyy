"""The co-pilot against the REAL field labels of the client's portals.

Each page below copies, word for word, the labels on a screen the client showed us (frame numbers
from the call recording) or the live public page. The real extension is loaded, presses Fill, and
every field is checked: the right value where Solara should fill, and still empty where it must not
(the vendor's own login, CAPTCHA, OTP, the vendor's site staff).

  python tests/real_labels.py        (server on 8900)
"""
import asyncio, sys, tempfile
from pathlib import Path
import httpx
from playwright.async_api import async_playwright
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, closeout  # noqa: E402
from app.config import DATA  # noqa: E402

BASE, CID = "http://127.0.0.1:8900", "SS-2045"
EXT = Path(__file__).resolve().parent.parent / "extension"
PASS, FAIL = [], []
STATES = ["Andaman and Nicobar Islands", "Maharashtra", "Gujarat"]


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def field(i, label, kind="text", value="", readonly=False, options=None):
    ro = " readonly" if readonly else ""
    if kind == "select":
        opts = '<option value="">Select</option>' + "".join(f"<option>{o}</option>" for o in options)
        ctl = f'<select id="{i}">{opts}</select>'
    elif kind == "textarea":
        ctl = f'<textarea id="{i}"></textarea>'
    else:
        ctl = f'<input type="{kind}" id="{i}" value="{value}"{ro}>'
    return f'<div class="fg"><label for="{i}">{label}</label>{ctl}</div>'


# page: (where the labels come from, [fields], {id: expected value key or None for "must stay empty"})
PAGES = {
    "vendor-login": ("national portal vendor login, f0035/f0048", [
        field("u", "User/Register Email ID*"), field("p", "Password*", "password"),
        field("cap", "Human Check*"), field("otp", "OTP*")],
        {"u": None, "cap": None, "otp": None}),
    "upload-agreement": ("Upload Agreement dialog, f0107", [
        field("cn", "Customer Name:", value="VAISHALI D PAWAR", readonly=True),
        field("cno", "Consumer Number:", value="170038865021", readonly=True),
        field("an", "Application Number:", value="NP-MHSED26-16188888", readonly=True),
        field("cost", "Total Cost of RTS Installation:*"), field("agr", "Agreement Copy:*", "file")],
        {"cost": "rts_cost"}),
    "site-feasibility": ("Site Feasibility Report, f0141", [
        field("area", "Available shadow free roof area [Meter Square]:*"),
        field("perm", "Permissible RTS Installation Capacity By Vendor(kW):*"),
        field("qa", "Quotation Amount(Rs.):*"), field("qd", "Quotation Document:*", "file"),
        field("emp", "Name of vendor employee visited the project site:*"),
        field("cnum", "Contact Number:*")],
        {"area": None, "perm": "capacity", "qa": "rts_cost", "emp": None, "cnum": None}),
    "installation-step1": ("Submit Installation step 1, f0165", [
        field("vn", "Name of Vendor:*"), field("lat", "Latitude:*"), field("lng", "Enter longitude:*")],
        {"vn": "vendor", "lat": "lat", "lng": "lng"}),
    # the customer login's own forms, from the 7 Nov 2026 recording: the account number is always the person's
    "subsidy-bank": ("Subsidy bank details, customer login, 7 Nov 2026 recording", [
        field("atype", "Account Type*", "select", options=["Savings", "Current"]),
        field("bname", "Bank Name*", "select", options=["Bank of Baroda", "Bank of Maharashtra", "State Bank of India"]),
        field("ifsc", "IFSC Code*"), field("br", "Branch Name*"), field("hold", "Account Holder Name*"),
        field("acc", "Bank Account Number*"), field("acc2", "Confirm Bank Account Number*")],
        {"atype": "account_type", "bname": "bank_name", "ifsc": "ifsc", "br": None, "hold": "account_holder",
         "acc": None, "acc2": None}),
    "apply-form": ("Application form, customer login, 7 Nov 2026 recording", [
        field("cat", "Category*", "select", options=["Residential", "Residential Welfare Association"]),
        field("kwp", "Proposed kWp*"), field("loc", "Type of Location", "select", options=["Urban", "Rural"])],
        {"cat": "category", "kwp": "capacity", "loc": None}),
    "dcr-b2c": ("NISE DCR Details (B2C), f0009/f0011", [
        field("br", "Branch", "select", options=["Maharashtra - Flat No. 203"]),
        field("it", "Item Type", "select", options=["Solar Panels"]),
        field("ss", "Subsidy Scheme", "select", options=["PM Surya Ghar: Muft Bijli Yojana"]),
        field("can", "Consumer Application Number"), field("cname", "Customer Name"),
        field("cmob", "Consumer Mobile"), field("caddr", "Customer Address", "textarea"),
        field("cst", "Customer State", "select", options=STATES), field("cpin", "Customer Pin Code"),
        field("ccp", "Customer Contact Person"), field("cce", "Customer Contact Email"),
        field("inv", "Invoice Number / E-Way Bill"), field("pan", "Panel Numbers (Enter Or Upload Via Excel)", "textarea")],
        {"can": "application_no", "cname": "name", "cmob": "mobile", "caddr": "address", "cst": "state",
         "cpin": "pin", "ccp": None, "cce": "email", "inv": None}),
    "msedcl-login": ("MSEDCL vendor login, live page", [
        '<input type="radio" name="userType" value="vendor" checked> Vendor',
        '<p>User Id <input type="text" id="userIdField" name="username"></p>',
        '<p>Password <input type="password" id="pw" name="password"></p>'],
        {"userIdField": None}),
    # the live site's own markup, saved read-only on 6 Nov 2026 (public page, nothing typed or sent):
    # PrimeNG input with no id, name or label[for]; a maths CAPTCHA; the guidelines checkbox
    "pmsg-consumer-login": ("PM Surya Ghar consumer login, live site 6 Nov 2026",
        [(Path(__file__).parent / "real_pages" / "pmsg_consumer_login_2026-11.html").read_text(encoding="utf-8")],
        {"rmob": "mobile", "rcap": None}),
    # the live vendor login, saved read-only on 7 Nov 2026: "User/Register Email ID" must never get the customer's email
    "pmsg-vendor-login": ("PM Surya Ghar vendor login, live site 7 Nov 2026",
        [(Path(__file__).parent / "real_pages" / "pmsg_vendor_login_2026-11.html").read_text(encoding="utf-8")],
        {"vemail": None, "vpw": None, "vcap": None}),
    # the Apply page's State, District and DISCOM: PrimeNG dropdowns the co-pilot opens and picks
    "pmsg-apply": ("PM Surya Ghar Apply page dropdowns, live PrimeNG markup",
        [(Path(__file__).parent / "real_pages" / "pmsg_apply_dropdowns.html").read_text(encoding="utf-8")],
        {"cno": "consumer_no"}),
}

# how the live PrimeNG dropdowns behaved (checked on the public filter, 7 Nov 2026)
PRIMENG = """() => {
  const OPTS = { state: ['MADHYA PRADESH', 'MAHARASHTRA', 'MANIPUR'], sort: ['Name ASC', 'Name DESC'],
    discom: ['Adani Electricity Mumbai Ltd.', 'Maharashtra State Electricity Distribution Co. Ltd.', 'Tata Power'] };
  const DIST = { MAHARASHTRA: ['Nagpur', 'Nandurbar', 'Nashik', 'Pune'] };
  const close = () => document.querySelectorAll('.p-dropdown-panel').forEach(x => x.remove());
  document.querySelectorAll('p-dropdown').forEach(pd => {
    const lab = pd.querySelector('.p-dropdown-label');
    pd.querySelector('.p-dropdown').addEventListener('click', () => {
      if (pd.classList.contains('disable-input')) return;
      if (document.querySelector('.p-dropdown-panel')) { close(); return; }
      const list = pd.id === 'district' ? (DIST[document.querySelector('#state .p-dropdown-label').innerText] || []) : OPTS[pd.id];
      setTimeout(() => {   // the portal fetches the list first
        const panel = document.createElement('div'); panel.className = 'p-dropdown-panel';
        panel.innerHTML = '<ul role="listbox">' + list.map(o => `<li role="option" aria-label="${o}">${o}</li>`).join('') + '</ul>';
        document.body.appendChild(panel);
        panel.querySelectorAll('li').forEach(li => li.addEventListener('click', () => {
          lab.textContent = li.getAttribute('aria-label'); lab.classList.remove('p-placeholder'); close();
          if (pd.id === 'state') document.querySelector('#district').classList.remove('disable-input');
        }));
      }, pd.id === 'district' ? 400 : 100);
    });
  });
}"""


# the customer login's My Applications card as on 7 Nov 2026: per stage, who / name / state / when
def tracker(app_no, states):
    names = ["Registration", "Application", "Feasibility", "Vendor Selection", "Upload Agreement", "Installation",
             "Inspection", "Project Commissioning", "Subsidy Request", "Subsidy Disbursal"]
    who = ["Consumer", "Consumer", "Discom", "Consumer", "Vendor", "Vendor", "Discom", "Discom", "Consumer", "REC"]
    steps = "".join(f'<div class="st"><div>{w}</div><div>{n}</div><div class="badge">{s}</div><div>07-11-2026 7:08 pm</div></div>'
                    for w, n, s in zip(who, names, states))
    return (f'<div class="card"><button>Action</button><div class="steps">{steps}</div>'
            f'<table><tr><td>Application Number:</td><td>{app_no}</td></tr><tr><td>Approved capacity (kWp):</td><td>3.300</td></tr></table></div>')


def html(title, fields):
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<style>.fg{{margin:8px}}label{{display:block}}</style></head><body><h3>{title}</h3>
<form>{''.join(fields)}</form></body></html>"""


async def main():
    sup = httpx.Client(base_url=BASE, timeout=60)
    sup.post("/api/login", json={"username": "r.deshmukh", "password": "demo"}).raise_for_status()
    sup.post("/api/demo/reset")
    sup.put(f"/api/registration/{CID}", json={"mobile": "9028144531", "email": "vaishali.p@example.com",
                                             "kw": "3", "rts_cost": "198000", "district": "Nashik"}).raise_for_status()
    # this suite is about portal labels, not the flow; the flow guard is tested in k1_complete.py
    db.ex("UPDATE customers SET application_no=?, stage='feasible' WHERE id=?", ("NP-MHSED26-16188888", CID))
    closeout.save(CID, {"pmsg_app_no": "NP-MHSED26-16188888"}, "test")
    closeout.mark(CID, "test", lat="19.997654", lng="73.789012")
    values = sup.get(f"/api/registration/{CID}").json()["values"]
    key = sup.post("/api/copilot/key").json()["key"]

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            tempfile.mkdtemp(), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{key}'}})")
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for name, (src, fields, expect) in PAGES.items():
            await sw.evaluate(f"chrome.storage.local.set({{current: {{cid: '{CID}', at: Date.now(), picked: true}}}})")
            await pg.goto(f"{BASE}/portal/verify")
            await pg.wait_for_selector("#solaraPanel")
            # the screen changes under the panel, as on a single-page portal; then ↻ re-reads it
            await pg.evaluate("""h => { [...document.body.children].forEach(n => { if (n.id !== 'solaraPanel') n.remove(); });
                document.body.insertAdjacentHTML('afterbegin', h); }""", html(src, fields))
            if name == "pmsg-apply":
                await pg.evaluate(PRIMENG)
            await pg.click("#solaraRescan")
            try:
                await pg.wait_for_function("/Vaishali|Nothing to do/.test(document.querySelector('#solaraPanel').innerText)", timeout=20000)
            except Exception:
                print("   panel:", (await pg.inner_text("#solaraPanel"))[:200]); raise
            wrong = []
            if await pg.locator("#solaraFill").count():
                if "Vaishali" not in await pg.inner_text("#solaraFill"):  # a recalled customer is named on the button
                    wrong.append("the Fill button does not name the customer")
                await pg.click("#solaraFill")
                await pg.wait_for_selector("#solaraFilled")
            for fid, want in expect.items():
                got = await pg.input_value(f"#{fid}")
                if want is None and got:
                    wrong.append(f"{fid} should stay empty, got '{got}'")
                elif want and (got or "").strip() != str(values[want]).strip():
                    wrong.append(f"{fid} expected '{values[want]}', got '{got}'")
            if name == "pmsg-consumer-login" and await pg.is_checked("#rguide"):
                wrong.append("the guidelines checkbox must be left to the person")
            if name == "pmsg-apply":
                picked = await pg.evaluate("Object.fromEntries([...document.querySelectorAll('p-dropdown')].map(d => [d.id, d.querySelector('.p-dropdown-label').innerText]))")
                want = {"state": "MAHARASHTRA", "district": values["district"], "discom": values["discom"], "sort": "Sort Vendors"}
                wrong += [f"{k} shows '{picked.get(k)}', expected '{v}'" for k, v in want.items() if picked.get(k) != v]
            if name == "pmsg-vendor-login" and await pg.is_checked("#vrem"):
                wrong.append("'Remember me' must be left to the person")
            check(f"{name} ({src})", not wrong, "; ".join(wrong) or f"{sum(1 for w in expect.values() if w)} filled, "
                  f"{sum(1 for w in expect.values() if w is None)} left alone")
            if name == "pmsg-apply":   # the layout button used in the live session: names only, never what is filled in
                await pg.click("#solaraLayout")
                await pg.wait_for_function("/^(Sent|Not sent)/.test(document.querySelector('#solaraLayout').innerText)")
                files = sorted((DATA / "layouts").glob("*.json"))
                saved = files[-1].read_text(encoding="utf-8") if files else ""
                check("the page layout reaches Solara with field names, and none of the values on the page",
                      '"rule": "district"' in saved and '"name": "consumerNo"' in saved
                      and str(values["consumer_no"]) not in saved and "Nashik" not in saved, files[-1].name if files else "no file")

        # ---- suggestions: Solara has no district, so the co-pilot reads the dropdown and takes the one named in the address
        d0 = closeout.data(CID)[1].get("district")
        closeout.save(CID, {"district": ""}, "test")
        c0 = db.one("SELECT place, address FROM customers WHERE id=?", (CID,))
        db.ex("UPDATE customers SET address=? WHERE id=?", ("Plot 14, Ganga Nagar, Panchavati, Nashik", CID))
        await sw.evaluate(f"chrome.storage.local.set({{current: {{cid: '{CID}', at: Date.now(), picked: true}}, run: {{cid: '{CID}', at: Date.now()}}}})")
        await pg.goto(f"{BASE}/portal/verify"); await pg.wait_for_selector("#solaraPanel")
        await pg.evaluate("""h => { [...document.body.children].forEach(n => { if (n.id !== 'solaraPanel') n.remove(); });
            document.body.insertAdjacentHTML('afterbegin', h); }""", PAGES["pmsg-apply"][1][0])
        await pg.evaluate(PRIMENG)
        await pg.click("#solaraRescan")
        await pg.wait_for_function("document.querySelector('#district .p-dropdown-label') && /Nashik/i.test(document.querySelector('#district .p-dropdown-label').innerText)", timeout=30000)
        check("no district in Solara: the one named in the customer's address is chosen from the portal's list", True)
        await sw.evaluate("chrome.storage.local.remove('run')")
        closeout.save(CID, {"district": d0 or "Nashik"}, "test")
        db.ex("UPDATE customers SET address=? WHERE id=?", (c0["address"], CID))

        # ---- the fallback popup at the bottom: a field Solara has no data for is typed there
        await sw.evaluate(f"chrome.storage.local.set({{current: {{cid: '{CID}', at: Date.now(), picked: true}}}})")
        await pg.goto(f"{BASE}/portal/verify"); await pg.wait_for_selector("#solaraPanel")
        await pg.evaluate("""h => { [...document.body.children].forEach(n => { if (n.id !== 'solaraPanel') n.remove(); });
            document.body.insertAdjacentHTML('afterbegin', h); }""",
            '<form><label for="ifsc1">Gender</label><input id="ifsc1"><label for="mob1">Mobile</label><input id="mob1"></form>')
        await pg.click("#solaraRescan")
        await pg.wait_for_selector("#solaraFallback", timeout=20000)
        check("a field Solara has no data for opens the popup at the bottom, named",
              "Gender" in await pg.inner_text("#solaraFallback") and "Mobile" not in await pg.inner_text("#solaraFallback"))
        await pg.fill("#solaraFallback [data-fbv]", "Female")
        await pg.click("#solaraFallback [data-fbgo]")
        await pg.wait_for_function("document.querySelector('#ifsc1').value === 'Female'", timeout=10000)
        check("what the owner types in the popup is filled on the page", await pg.input_value("#ifsc1") == "Female")
        await pg.wait_for_function("!document.querySelector('#solaraFallback')", timeout=10000)
        check("the popup goes away once everything is filled", True)

        # ---- the two logins side by side: the customer login's screens, and the hand-off to the other tab ----
        async def show(page, body):
            await page.evaluate("""h => { [...document.body.children].forEach(n => { if (n.id !== 'solaraPanel') n.remove(); });
                document.body.insertAdjacentHTML('afterbegin', h); }""", body)
            await page.click("#solaraRescan")
        panel = lambda page: page.inner_text("#solaraPanel")
        closeout.mark(CID, "test", accepted_at=db.now(), agreement_uploaded_at=db.now())
        await sw.evaluate("chrome.storage.local.remove(['current', 'handoff'])")
        await pg.goto(f"{BASE}/portal/verify"); await pg.wait_for_selector("#solaraPanel")
        await show(pg, '<div role="dialog">Do you want the Vendor to fill the application on your behalf? <button>Yes</button><button>No</button></div>')
        await pg.wait_for_function("/Answer Yes/.test(document.querySelector('#solaraPanel').innerText)", timeout=20000)
        check("customer login: 'Do you want the Vendor to fill' gets the answer Yes (the owner's standing setting)", True)
        await show(pg, '<div role="dialog"><h4>Submit Agreement Details</h4><p>Application Number: NP-MHSED26-16188888</p>'
                       '<label for="aotp">Enter OTP</label><input id="aotp"><button>Verify &amp; Approve</button></div>')
        await pg.wait_for_selector("#solaraMarkApproved", timeout=20000)
        check("customer login: the approval dialog shows the steps and a mark button; the OTP box stays the person's",
              "Submit Agreement Details" in await panel(pg) and not await pg.input_value("#aotp"), (await panel(pg))[:160])
        other = await ctx.new_page()   # the vendor login in the second tab
        await other.goto(f"{BASE}/pmsg/vendor/consent"); await other.wait_for_selector("#solaraPanel")
        await show(pg, tracker("NP-MHSED26-16188888", ["Completed"] * 5 + ["In Progress"] + ["Pending"] * 4))
        try:
            await pg.wait_for_function("/Solara updated|Nothing new|not updated/.test(document.querySelector('#solaraPanel').innerText)", timeout=20000)
        except Exception:
            print("   panel:", repr((await panel(pg))[:400])); raise
        check("customer login tracker: Installation In Progress marks the customer's approval in Solara",
              bool(closeout.data(CID)[1].get("agreement_approved_at")) and "approved" in await panel(pg), (await panel(pg))[:200])
        try:
            await other.wait_for_selector("#solaraHandoff", timeout=8000)
            told = await other.inner_text("#solaraHandoff")
        except Exception:
            told = ""
        check("the other tab is told at once: approved, installation can start", "approved the agreement" in told, told or "no banner")
        await show(pg, tracker("NP-MHSED26-16188888", ["Completed"] * 4 + ["Pending"] * 6))
        await pg.wait_for_function("/Solara updated|Nothing new|not updated/.test(document.querySelector('#solaraPanel').innerText)", timeout=20000)
        check("a tracker behind Solara moves nothing back", bool(closeout.data(CID)[1].get("agreement_approved_at")))
        await other.close()
        await ctx.close()
    print("\n  reset:", sup.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
