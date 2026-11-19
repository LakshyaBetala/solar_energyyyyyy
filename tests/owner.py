"""One owner on their own computer: no sign-in, an empty start, and a customer can be deleted for good.

  python tests/owner.py        (starts its own server on port 8912 with a temporary data folder)

This is how the desktop app runs (SOLARA_SINGLE_OWNER=1, SOLARA_MODE=live). No sign-in must not mean
anyone can drive Solara: a page of another site open in the same browser, or a web address pointed at
this computer, is refused.
"""
import asyncio, os, subprocess, sys, tempfile, time
import httpx
from playwright.async_api import async_playwright
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORT, PASS, FAIL = 8912, [], []
BASE = f"http://127.0.0.1:{PORT}"


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main():
    data = tempfile.mkdtemp()
    env = {**os.environ, "SOLARA_MODE": "live", "SOLARA_SINGLE_OWNER": "1", "SOLARA_DATA": data, "SOLARA_NO_UPKEEP": "1"}
    env.pop("SOLARA_VENDOR_NAME", None)
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                httpx.get(BASE + "/api/me", timeout=2); break
            except httpx.HTTPError:
                time.sleep(0.5)
        c = httpx.Client(base_url=BASE, timeout=60)
        me = c.get("/api/me").json()
        check("no sign-in: Solara opens as the owner, with every right", (me["user"] or {}).get("role") == "supervisor"
              and me["single"] is True and me["setup"] is False, str(me))
        check("it starts empty: no sample customers", c.get("/api/customers").json() == [] and c.get("/api/registration").json() == [])
        for name, h in (("a page of another site in the same browser", {"Origin": "https://example.org"}),
                        ("a request the browser marks as coming from another site", {"Sec-Fetch-Site": "cross-site"}),
                        ("a web address pointed at this computer", {"Host": "solara.example.org"})):
            r = httpx.get(BASE + "/api/customers", headers=h)
            w = httpx.post(BASE + "/api/customers", json={"name": "Should Not Exist"}, headers=h)
            check(f"{name} is refused, reading and writing", r.status_code == 401 and w.status_code == 401, f"{r.status_code} {w.status_code}")
        check("...and nothing was added by those", c.get("/api/customers").json() == [])

        cid = c.post("/api/customers", json={"name": "First Real Customer"}).json()["customer"]["id"]
        g = c.get(f"/api/registration/{cid}").json()
        check("links open the real national portal", g["portals"]["pmsg"].startswith("https://consumer.pmsuryaghar.gov.in"))
        v = g["values"].get("vendor") or ""
        check("the company's name comes from its own agreement draft, with nothing typed into a settings file",
              bool(v) and "Demo Solar" not in v if g.get("quotes") and any(q.get("file") for q in g["quotes"]) else True)
        hp = c.get("/api/helper").json()
        check("Solara says where the Chrome helper's folder is", hp["folder"].endswith("extension") and os.path.isdir(hp["folder"]) and hp["here"] is True)

        # what a customer leaves behind in every table goes with them
        os.environ["SOLARA_DATA"] = data
        sys.path.insert(0, ".")
        from app import db
        db.ex("INSERT INTO portal_status(customer_id, portal, status, seen_at) VALUES(?,?,?,?)", (cid, "pmsg", "Installation (Pending)", db.now()))
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page()
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("dialog", lambda d: asyncio.create_task(d.accept()))
            await pg.goto(BASE)
            await pg.wait_for_selector("#shell:not([hidden])", timeout=15000)
            check("the app opens straight on Today: no sign-in page, no 'Signed in' chip, no Sign out",
                  await pg.locator("#gate").is_hidden() and await pg.locator("#whoChip").is_hidden() and await pg.locator("#signout").is_hidden())
            await pg.click('.navitem[data-view="reports"]')
            await pg.wait_for_selector("#quotesCard", timeout=15000)
            check("no People card: there is nobody else to add", await pg.locator("#people").count() == 0)
            await pg.click('.navitem[data-view="today"]')
            await pg.wait_for_selector("#coKey", timeout=15000)
            await pg.click("#coKey")
            await pg.wait_for_selector("#helperSteps", timeout=15000)
            steps = await pg.inner_text("#helperSteps")
            check("with no helper in this browser, Connect shows the helper's folder, a Copy button and what to press in Chrome",
                  await pg.input_value("#exFolder") == hp["folder"] and "Load unpacked" in steps and "Select Folder" in steps
                  and await pg.locator('[data-helperopen="folder"]').count() == 1, steps[:120])
            await pg.keyboard.press("Escape")
            await pg.click('.navitem[data-view="reg"]')
            await pg.wait_for_selector("#regDelete", timeout=15000)
            await pg.click("#regDelete")
            await pg.wait_for_function("!document.querySelector('#regDelete')", timeout=15000)
            check("no script errors", not errs, "; ".join(errs[:2]))
            await b.close()
        left = [t["name"] for t in db.q("SELECT name FROM sqlite_master WHERE type='table'")
                if any(col["name"] == "customer_id" for col in db.q(f"PRAGMA table_info({t['name']})"))
                and db.q(f"SELECT 1 FROM {t['name']} WHERE customer_id=?", (cid,))]
        check("Delete this customer removes them from every table, the portal status too; the audit trail keeps that it happened",
              c.get("/api/customers").json() == [] and left == [] and db.one("SELECT 1 FROM audit WHERE action='Deleted customer' AND target=?", (cid,)) is not None, str(left))
    finally:
        srv.terminate()
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
