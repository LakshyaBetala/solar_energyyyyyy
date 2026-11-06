"""Live-mode check: a fresh install with SOLARA_MODE=live starts empty, has no demo accounts or
demo screens, refuses the demo reset, and links to the real portals.

  python tests/live_mode.py        (starts its own server on port 8911 with a temporary data folder)
"""
import asyncio, os, subprocess, sys, tempfile, time
import httpx
from playwright.async_api import async_playwright
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORT, PASS, FAIL = 8911, [], []
BASE = f"http://127.0.0.1:{PORT}"


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main():
    data = tempfile.mkdtemp()
    env = {**os.environ, "SOLARA_MODE": "live", "SOLARA_DATA": data}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                httpx.get(BASE + "/api/me", timeout=2); break
            except httpx.HTTPError:
                time.sleep(0.5)
        me = httpx.get(BASE + "/api/me").json()
        check("the server reports live mode", me["live"] is True)
        r = httpx.post(BASE + "/api/login", json={"username": "r.deshmukh", "password": "demo"})
        check("no demo accounts exist on a live install", r.status_code == 401)
        # add the first person the way app.users does
        subprocess.run([sys.executable, "-c", "from app import db; db.ex(\"INSERT INTO users(username,name,role,pw) "
                        "VALUES('owner','Owner','supervisor',?)\", (db.pwhash('a-long-password'),))"], env=env, check=True)
        c = httpx.Client(base_url=BASE, timeout=60)
        c.post("/api/login", json={"username": "owner", "password": "a-long-password"}).raise_for_status()
        check("a live install starts with no customers", c.get("/api/registration").json() == [] and
              c.get("/api/customers").json() == [])
        check("the demo reset is refused on a live install", c.post("/api/demo/reset").status_code == 403)
        cid = c.post("/api/customers", json={"name": "First Real Customer"}).json()["customer"]["id"]
        g = c.get(f"/api/registration/{cid}").json()
        check("links open the real national portal logins", g["portals"]["pmsg"].startswith("https://consumer.pmsuryaghar.gov.in") and g["portals"]["pmsg_vendor"].startswith("https://vendor.pmsuryaghar.gov.in"))
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page()
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            await pg.goto(BASE)
            await pg.wait_for_timeout(800)
            check("the sign-in screen shows no demo accounts or prefilled password",
                  not await pg.locator(".whoami").is_visible() and await pg.input_value("#p") == "")
            await pg.fill("#u", "owner"); await pg.fill("#p", "a-long-password")
            await pg.click("#loginForm button[type=submit]")
            try:
                await pg.wait_for_selector("#shell:not([hidden])", timeout=8000)
            except Exception:
                print("gate:", await pg.inner_text("#gateErr"), errs); raise
            navs = await pg.locator(".navitem:visible").evaluate_all("els => els.map(e => e.dataset.view)")
            check("only the real screens are in the menu", "numbers" not in navs and "calls" not in navs
                  and "run" not in navs and "reg" in navs, ", ".join(navs))
            await b.close()
    finally:
        srv.terminate()
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
