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
}


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
            await pg.click("#solaraRescan")
            try:
                await pg.wait_for_function("/Vaishali|Nothing to do/.test(document.querySelector('#solaraPanel').innerText)", timeout=20000)
            except Exception:
                print("   panel:", (await pg.inner_text("#solaraPanel"))[:200]); raise
            if await pg.locator("#solaraFill").count():
                await pg.click("#solaraFill")
                await pg.wait_for_selector("#solaraFilled")
            wrong = []
            for fid, want in expect.items():
                got = await pg.input_value(f"#{fid}")
                if want is None and got:
                    wrong.append(f"{fid} should stay empty, got '{got}'")
                elif want and (got or "").strip() != str(values[want]).strip():
                    wrong.append(f"{fid} expected '{values[want]}', got '{got}'")
            check(f"{name} ({src})", not wrong, "; ".join(wrong) or f"{sum(1 for w in expect.values() if w)} filled, "
                  f"{sum(1 for w in expect.values() if w is None)} left alone")
        await ctx.close()
    print("\n  reset:", sup.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
