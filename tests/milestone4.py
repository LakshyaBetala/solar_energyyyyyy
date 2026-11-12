"""Milestone 4 acceptance test (KPI K4): the eight problem cases handled without filing anything
twice or wrong, separate staff logins, and a backup restored.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/milestone4.py                     (in another)

The co-pilot cases run in a browser with the extension loaded, on pages that show the portal's own
wording for each problem (the national portal's messages, as in docs/PRE_INSTALLATION_FIELDS.md and
the public manuals):
  1 wrong OTP              the panel says to read the newest SMS again; nothing typed, nothing filed
  2 OTP not received       the panel points at the portal's Resend button; a resend is recorded
  3 portal session timeout the panel says log in again; Solara checks what is filed before refilling
  4 internet cut mid-form  the panel says nothing is lost; when it is back the page is read again
The file cases run against Solara itself:
  5 file over the limit    a 2 MB photo goes to the portal as a JPEG under 300 KB
  6 repeated serial        a serial already on another customer is refused with whose it is
  7 photo without GPS      refused with what to do; nothing saved
  8 dealer not transferred the customer waits under "Waiting" on Today; nothing is filed
Then: nothing filed twice (a second "filed" report is recognised), staff logins with roles, a
locked-out password guesser, an expired session, and the restore drill on a fresh backup.
Every handled case leaves one line in the audit trail; /api/kpi counts them. Synthetic data only.
"""
import asyncio, io, random, re, sys, zipfile
from pathlib import Path
import httpx
from PIL import Image
from playwright.async_api import async_playwright
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, closeout, field  # noqa: E402
import fixtures as fx  # noqa: E402

BASE = "http://127.0.0.1:8900"
EXT = Path(__file__).resolve().parent.parent / "extension"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def client(user, pw="demo"):
    c = httpx.Client(base_url=BASE, timeout=120, follow_redirects=True)
    c.post("/api/login", json={"username": user, "password": pw}).raise_for_status()
    return c


def audited(action, since):
    return db.one("SELECT COUNT(*) k FROM audit WHERE action=? AND id>?", (action, since))["k"]


def noisy_photo(side=2400):
    """A photo that is large as a file: random noise compresses badly."""
    im = Image.frombytes("RGB", (side, side), random.randbytes(side * side * 3))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=95)
    return buf.getvalue()


# the portal's own wording for each problem, on an otherwise ordinary page
PAGES = {
    "otp_wrong": '<h3>Verify OTP</h3><div class="fg"><label for="otp">Enter OTP</label><input id="otp" type="text"></div>'
                 '<button type="button">Resend OTP</button><div class="alert">Invalid OTP. Please try again.</div>',
    "resend": '<h3>Verify OTP</h3><div class="fg"><label for="otp2">Enter OTP</label><input id="otp2" type="text"></div>'
              '<button type="button" id="rs">Resend OTP</button>',
    "resent": '<h3>Verify OTP</h3><div class="fg"><label for="otp3">Enter OTP</label><input id="otp3" type="text"></div>'
              '<div class="alert">A new OTP has been sent to your registered mobile number.</div>',
    "session": '<div class="alert">Your session has expired. Please login again.</div>'
               '<div class="fg"><label for="em">User/Register Email ID</label><input id="em" type="text"></div>',
}


async def show(pg, html):
    # the portal's page changes in place; the co-pilot's panel stays, as on a single-page portal
    await pg.evaluate("""h => { [...document.body.children].filter(el => el.id !== 'solaraPanel').forEach(el => el.remove());
        document.body.insertAdjacentHTML('afterbegin', '<main id="pageMain">' + h + '</main>'); }""", html)


async def panel_has(pg, sel, timeout=15000):
    try:
        await pg.wait_for_selector(f"#solaraPanel {sel}", timeout=timeout)
        return True
    except Exception:
        print("   the panel was:", " | ".join((await pg.inner_text("#solaraPanel"))[:300].splitlines()))
        return False


async def copilot_cases(sup, key, since):
    print("\n  -- the co-pilot on the four portal problems")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            fx.browser_profile(), channel="chromium", headless=True, viewport={"width": 1440, "height": 900},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        await sw.evaluate(f"chrome.storage.local.set({{url: '{BASE}', key: '{key}'}})")
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda ex: errors.append(str(ex)))
        await pg.goto(BASE + "/pmsg/vendor/")
        await pg.wait_for_selector("#solaraPanel")

        await show(pg, PAGES["otp_wrong"])
        ok = await panel_has(pg, '#solaraTrouble[data-kind="otp_wrong"]')
        txt = await pg.inner_text("#solaraPanel")
        check("1 wrong OTP: the panel says to read the newest SMS again", ok and "newest SMS" in txt)
        check("1 ...and the co-pilot typed nothing in the OTP box", await pg.input_value("#otp") == "")
        await pg.wait_for_timeout(800)
        check("1 ...recorded once in the audit trail", audited("Co-pilot: wrong OTP", since) == 1)

        await show(pg, PAGES["resend"])
        await pg.wait_for_function("(document.querySelector('#solaraPanel') || {innerText: ''}).innerText.includes('Resend OTP')", timeout=15000)
        check("2 OTP not received: the panel points at the portal's own Resend button", True)
        await show(pg, PAGES["resent"])
        ok = await panel_has(pg, '#solaraTrouble[data-kind="otp_resend"]')
        await pg.wait_for_timeout(800)
        check("2 ...the resend is noticed and recorded", ok and audited("Co-pilot: OTP resend", since) == 1)

        await show(pg, PAGES["session"])
        ok = await panel_has(pg, '#solaraTrouble[data-kind="session"]')
        txt = await pg.inner_text("#solaraPanel")
        await pg.wait_for_timeout(800)
        check("3 session timeout: the panel says log in again; Solara checks what is filed first",
              ok and "Log in again" in txt and "already filed" in txt and audited("Co-pilot: portal session ended", since) == 1)
        check("3 ...and the vendor's own login box is left alone", await pg.input_value("#em") == "")

        await show(pg, '<h3>Site Feasibility Report</h3><div class="fg"><label for="ra">Shadow free roof area</label><input id="ra"></div>')
        await pg.wait_for_timeout(1500)
        await pg.fill("#ra", "41")                      # the owner was typing when the line went
        await ctx.set_offline(True)
        ok = await panel_has(pg, "#solaraOffline")
        check("4 internet cut mid-form: the panel says nothing is lost", ok and "Nothing is lost" in await pg.inner_text("#solaraPanel"))
        await ctx.set_offline(False)
        await pg.wait_for_function("!document.querySelector('#solaraPanel #solaraOffline')", timeout=15000)
        await pg.wait_for_timeout(1000)
        check("4 ...back online: the page is read again, what was typed is still there, the cut is recorded",
              await pg.input_value("#ra") == "41" and audited("Co-pilot: internet off", since) == 1)
        check("no script errors on the portal pages", not errors, "; ".join(errors[:3]))
        await ctx.close()


def file_cases(sup, key, since):
    print("\n  -- the file cases")
    h = {"X-Solara-Key": key}
    a = sup.post("/api/customers", json={"name": "Kiran Deshpande"}).json()["customer"]["id"]
    b = sup.post("/api/customers", json={"name": "Meera Joshi"}).json()["customer"]["id"]
    big = noisy_photo()
    sup.post(f"/api/registration/{a}/document", params={"kind": "roof"}, files={"file": ("roof.jpg", big)}).raise_for_status()
    r = httpx.get(f"{BASE}/api/copilot/doc/{a}/roof", headers=h, timeout=60)
    check(f"5 a {len(big) // 1024} KB photo goes to the portal as a JPEG under 300 KB",
          r.status_code == 200 and r.content[:2] == b"\xff\xd8" and len(r.content) <= 300 * 1024, f"{len(r.content) // 1024} KB")
    check("5 ...and the shrink is recorded", audited("File made smaller for the portal", since) >= 1)
    # a box that says "File format only accepts PDF. Maximum Size: 500kB" (the plant-photo box in the manual)
    r = httpx.get(f"{BASE}/api/copilot/doc/{a}/roof", params={"to": "pdf", "max_kb": 500}, headers=h, timeout=60)
    name = r.headers.get("content-disposition", "")
    check("5 a box that takes PDF only, 500 KB: the photo goes as a one-page PDF under 500 KB",
          r.status_code == 200 and r.content.startswith(b"%PDF") and len(r.content) <= 500 * 1024, f"{len(r.content) // 1024} KB")
    check("5 ...with a name the portal accepts: letters, digits, underscores, one .pdf",
          bool(re.search(r'filename="[A-Za-z0-9_]+\.pdf"', name)), name)

    closeout.save(b, {"module_serials": "PE55026A900001"}, "test")             # already on another customer
    link = field.create_link(a, {"username": "r.deshmukh", "role": "supervisor"})
    r = httpx.post(f"{BASE}/field/{link}/typed", data={"serial": "PE55026A900001", "kind": "module"})
    reads = {x["serial"]: x for x in field.summary(a)["reads"]}
    check("6 a serial already on another customer is flagged as a repeat, with whose it is",
          r.status_code == 200 and reads.get("PE55026A900001", {}).get("status") == "clash" and b in reads["PE55026A900001"].get("note", ""))
    check("6 ...and the repeat is recorded", audited("Serial repeat refused", since) >= 1)

    plain = io.BytesIO(); Image.new("RGB", (800, 600), (120, 160, 200)).save(plain, "JPEG")
    r = httpx.post(f"{BASE}/field/{link}/photo", data={"kind": "site"}, files={"file": ("site.jpg", plain.getvalue())})
    check("7 a site photo without GPS is refused, with what to do", r.status_code == 400 and "location" in r.text, r.text[:120])
    check("7 ...nothing was saved, and the refusal is recorded",
          not closeout.data(a)[1].get("site_photo_at") and audited("Photo without GPS refused", since) >= 1)

    db.ex("UPDATE customers SET application_no=?, stage='feasible' WHERE id=?", ("NP-MHSED26-16477001", a))
    closeout.mark(a, "test", agreement_uploaded_at=db.now(), agreement_approved_at=db.now(), sfr_at=db.now(),
                  field_at=db.now(), serials_at=db.now())
    closeout.save_photo(a, closeout._demo_photo(18.52, 73.85), "test")   # the field work is in
    r = httpx.post(f"{BASE}/api/copilot/report", headers=h, json={"customer_id": a, "event": "dealer_wait",
                                                                  "message": "Panel Not in Your Stock (Not Claimed / Sold it)"})
    waiting = [x for x in sup.get("/api/today").json()["waiting"] if x["cid"] == a]
    check("8 dealer panels not transferred: the customer waits under Waiting on Today",
          r.status_code == 200 and any(x["act"] == "dealer" for x in waiting), str(waiting))
    check("8 ...no DCR certificate was recorded", not closeout.data(a)[1].get("dcr_cert_no"))

    print("\n  -- nothing filed twice")
    first = httpx.post(f"{BASE}/api/copilot/report", headers=h, json={"customer_id": a, "event": "filed", "step": "sfr"}).json()
    again = httpx.post(f"{BASE}/api/copilot/report", headers=h, json={"customer_id": a, "event": "filed", "step": "sfr"}).json()
    check("a filing Solara already has is recognised, not recorded twice", first.get("already") and again.get("already"))
    return a


def people(sup, since):
    print("\n  -- staff logins, roles, sessions")
    view = client("a.more")
    check("a viewer cannot change anything", view.put("/api/registration/SS-2047", json={"kw": "4"}).status_code == 403)
    op = client("s.kale")
    check("an operator cannot add people", op.post("/api/users", json={"username": "x.test"}).status_code == 403)
    name = f"t.staff{random.randint(100, 999)}"
    r = sup.post("/api/users", json={"username": name, "name": "Test Staff", "role": "operator", "password": "a-long-pass-123"})
    check("a supervisor adds a person in Solara, with a role", r.status_code == 200 and any(u["username"] == name for u in r.json()))
    check("the new person signs in with their own password",
          httpx.post(BASE + "/api/login", json={"username": name, "password": "a-long-pass-123"}).status_code == 200)
    short = sup.post("/api/users", json={"username": "t.short", "name": "Short", "role": "viewer", "password": "short"})
    check("a password under 10 characters is refused", short.status_code == 400)
    codes = [httpx.post(BASE + "/api/login", json={"username": name, "password": f"wrong{i}"}).status_code for i in range(6)]
    check("five wrong passwords lock that username for a while", codes[:5] == [401] * 5 and codes[5] == 429, str(codes))
    sup.delete(f"/api/users/{name}")
    old = client("a.more")
    db.ex("UPDATE sessions SET created_at='2020-01-01T00:00:00'")
    check("a session older than 12 hours is over, whatever the browser keeps", old.get("/api/today").status_code == 401)
    db.ex("DELETE FROM audit WHERE action='Failed sign-in' AND target=?", (name,))


def restore(sup):
    print("\n  -- backup, restore and the client's own copy")
    r = sup.get("/api/exports/everything.zip")
    z = zipfile.ZipFile(io.BytesIO(r.content)) if r.status_code == 200 else None
    names = z.namelist() if z else []
    check("Export everything: every customer, their documents decrypted, the audit trail",
          {"customers.xlsx", "audit_trail.csv", "README.txt"} <= set(names) and any(n.startswith("documents/SS-2041/") for n in names)
          and z.read(next(n for n in names if n.startswith("documents/SS-2041/") and n.endswith(".pdf"))).startswith(b"%PDF"), f"{len(names)} files")
    check("...only a supervisor can make it", client("s.kale").get("/api/exports/everything.zip").status_code == 403)
    sup.post("/api/backup").raise_for_status()
    r = sup.post("/api/backup/verify").json()
    check("the restore drill opens the newest backup: database whole, documents open with this key",
          r["ok"] and r["integrity"] == "ok" and r["customers"] > 0 and "opens" in r["document"], str(r))


async def reports_page():
    print("\n  -- Reports for the owner")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        pg.on("pageerror", lambda ex: errs.append(str(ex)))
        for who in ("r.deshmukh", "a.more"):
            await pg.goto(BASE)
            await pg.click(f'[data-as="{who}"]')
            await pg.wait_for_selector("#shell:not([hidden])")
            await pg.click('.navitem[data-view="reports"]')
            await pg.wait_for_selector("#milestones", timeout=15000)
            if who == "r.deshmukh":
                k4 = await pg.inner_text('#milestones [data-ms="K4"]')
                check("Reports: six milestones, K4 met with its cases, owner's time, people",
                      await pg.locator("#milestones [data-ms]").count() == 6 and "met" in k4 and "wrong OTP" in k4
                      and await pg.locator("#ownerTime tbody tr").count() > 0 and await pg.locator("#people [data-upass]").count() >= 3)
                await pg.click("#drill")
                await pg.wait_for_function("/Restore drill passed/.test(document.querySelector('#toastmsg').innerText)", timeout=30000)
                check("the restore drill runs from Reports", True)
            else:
                check("a viewer sees the milestones but no people and no upkeep buttons",
                      await pg.locator("#people").count() == 0 and await pg.locator("#drill").is_disabled())
            await pg.evaluate("fetch('/api/logout', {method: 'POST'})")
        check("no script errors on Reports", not errs, "; ".join(errs[:2]))
        await b.close()


async def main():
    sup = client("r.deshmukh")
    print("  reset:", sup.post("/api/demo/reset").json()["runnable"])
    since = db.one("SELECT MAX(id) k FROM audit")["k"] or 0
    key = sup.post("/api/copilot/key").json()["key"]
    await copilot_cases(sup, key, since)
    file_cases(sup, key, since)
    k4 = next(m for m in sup.get("/api/kpi").json()["milestones"] if m["key"] == "K4")
    check("the KPI page counts all eight cases as seen and handled", k4["met"], k4["value"])
    people(sup, since)
    sup = client("r.deshmukh")                       # every session ended in the session check
    restore(sup)
    await reports_page()
    print("\n  reset:", sup.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
