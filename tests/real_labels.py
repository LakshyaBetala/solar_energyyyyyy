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


def yesno(name, label):
    """A Yes/No question as the national portal draws it: the question, then two radio buttons."""
    return (f'<div class="fg"><label>{label}</label><label><input type="radio" name="{name}" value="Y"> Yes</label>'
            f'<label><input type="radio" name="{name}" value="N"> No</label></div>')


def grid(heading, cols, rows=2):
    """A repeating table of inputs (one row per make), as on Submit Installation step 2."""
    head = "".join(f"<th>{c}</th>" for c in ["S.No."] + [c for c, _ in cols] + ["Action"])
    body = "".join("<tr><td>" + str(r + 1) + "</td>" + "".join(f'<td><input type="text" id="{k}{r}"></td>' for _, k in cols) +
                   "<td></td></tr>" for r in range(rows))
    return f"<h3>{heading}</h3><table><tr>{head}</tr>{body}</table>"


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
        field("cnum", "Contact Number:*"),
        yesno("roofLoad", "Roof has enough load bearing capacity:*"),
        yesno("shadowFree", "Availability of shadow free roof for the RTS installation:*"),
        yesno("visited", "Vendor has visited the installation site and carried out the assessment:*")],
        {"area": "roof_area", "perm": "capacity", "qa": "rts_cost", "emp": "visitor_name", "cnum": "visitor_phone",
         "radio:roofLoad": "Y", "radio:shadowFree": "Y", "radio:visited": "N"}),
    "installation-step1": ("Submit Installation step 1, f0165", [
        field("vn", "Name of Vendor:*"), field("lat", "Latitude:*"), field("lng", "Enter longitude:*")],
        {"vn": "vendor", "lat": "lat", "lng": "lng"}),
    "installation-step2": ("Submit Installation step 2, MNRE vendor manual pages 10C and 10E", [
        field("ph", "Phase of Solar Inverter", "select", options=["Single Phase", "Three Phase"]),
        grid("Solar Inverter Details", [("Capacity/Rating(in kW) of each inverter", "ikw"), ("Quantity of Inverter", "iq"),
                                        ("Manufacturer of Inverter", "im")]),
        grid("Solar PV Modules Details", [("Capacity/Rating(in Wp) of each Solar PV Module", "mwp"),
                                          ("Quantity of Solar PV Module", "mq"), ("Manufacturer of Solar PV Module", "mm")])],
        {"ph": "phase", "ikw0": "inverter_kw", "iq0": "inverter_qty", "im0": "inverter_make", "mwp0": "module_wp",
         "mq0": "module_count", "mm0": "module_make", "ikw1": None, "mwp1": None, "mm1": None}),
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
        field("inv", "Invoice Number / E-Way Bill"), field("pan", "Panel Numbers (Enter Or Upload Via Excel)", "textarea"),
        field("po", "Purchase Order Ref"), field("qty", "Quantity")],
        {"can": "application_no", "cname": "name", "cmob": "mobile", "caddr": "address", "cst": "state",
         "cpin": "pin", "ccp": None, "cce": "email", "inv": "invoice_no", "pan": "module_serials", "qty": "module_count",
         "po": None, "br": "only", "it": "item_type", "ss": "scheme"}),
    "msedcl-login": ("MSEDCL vendor login, live page", [
        '<input type="radio" name="userType" value="vendor" checked> Vendor',
        '<p>User Id <input type="text" id="userIdField" name="username"></p>',
        '<p>Password <input type="password" id="pw" name="password"></p>'],
        {"userIdField": None}),
    "owner-chose": ("a dropdown the owner already set differs from the record", [
        '<div class="fg"><label for="cst2">Customer State</label><select id="cst2"><option value="">Select</option>'
        '<option>Maharashtra</option><option selected>Gujarat</option></select></div>', field("cn2", "Customer Name")],
        {"cst2": "=Gujarat", "cn2": "name"}),
    "add-serial-submits": ("an Add Serial button with no type, which would submit its form", [
        '<h3>Solar PV Modules Details</h3><table><tr><th>S.No.</th><th>Quantity of Solar PV Module</th><th>Action</th></tr>'
        '<tr><td>1</td><td><input type="text" id="mq9"></td><td><button>+ Add Serial Number</button>'
        '<textarea id="sn9" aria-label="Serial Numbers" hidden></textarea></td></tr></table>'],
        {"mq9": "module_count", "sn9": None}),
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
    closeout.save(CID, {"roof_area": "38", "visitor_name": "Amol Kadam", "visitor_phone": "9890012345",
                        "roof_load_ok": "Yes", "shadow_free": "Yes", "site_visited": "No", "invoice_no": "INV/26-27/0601",
                        "module_serials": "TLRL26A0000001\nTLRL26A0000002", "module_count": "2", "module_wp": "550",
                        "module_make": "Premier Energies", "inverter_kw": "1.1", "inverter_make": "Polycab PSIS-1K",
                        "phase": "Single phase"}, "test")
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
                document.body.insertAdjacentHTML('afterbegin', h); window.__stay = 1; }""", html(src, fields))
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
            await pg.wait_for_timeout(300)
            wrong = [] if await pg.evaluate("window.__stay === 1") else ["the co-pilot submitted the page"]
            if not wrong:
                for fid, want in expect.items():
                    if fid.startswith("radio:"):
                        got = await pg.evaluate(f"(document.querySelector('input[name={fid[6:]}]:checked') || {{}}).value || ''")
                        if got != want:
                            wrong.append(f"{fid} expected {want}, got '{got}'")
                        continue
                    got = await pg.input_value(f"#{fid}")
                    if want == "only":  # the one option there is
                        if not got:
                            wrong.append(f"{fid} should take its only option")
                        continue
                    if fid == "ph":  # the portal's wording for the record's "Single phase"
                        want_v = "Single Phase"
                        if got != want_v:
                            wrong.append(f"ph expected {want_v}, got '{got}'")
                        continue
                    if want and want.startswith("="):  # the owner's own choice, kept
                        if got != want[1:]:
                            wrong.append(f"{fid} should keep '{want[1:]}', got '{got}'")
                        continue
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
        await pg.wait_for_function("/Answer No/.test(document.querySelector('#solaraPanel').innerText)", timeout=20000)
        check("customer login: 'Do you want the Vendor to fill' gets the answer No", True)
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
    calls = [x for x in sup.get("/api/today").json()["calls"] if x["cid"] == CID and "waiting for" in x["text"]]
    check("the owner's own login OTP does not put a customer call on Today", not calls, str(calls))
    print("\n  reset:", sup.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
