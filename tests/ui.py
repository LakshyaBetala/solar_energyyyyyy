"""UI test for the simple Solara: the menu has six places and the day starts on Today.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/ui.py                             (in another)

Signs in as each role, checks Today groups the work as one list with one button per line, that the
OTP call line carries the customer's number and the WhatsApp heads-up, that each line opens the
right customer at the right step, that the customer's document page asks one thing at a time, and
that both themes and a phone-width screen work. Resets the demo first and again at the end.
"""
import asyncio, sys, httpx
from playwright.async_api import async_playwright
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8900"
PASS, FAIL = [], []
MENU = ["today", "reg", "inst", "closeout", "audit", "reports"]


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def sup():
    c = httpx.Client(base_url=BASE, timeout=60)
    c.post("/api/login", json={"username": "r.deshmukh", "password": "demo"}).raise_for_status()
    return c


async def sign_in(pg, who):
    if await pg.locator("#shell:not([hidden])").count():
        await pg.keyboard.press("Escape")
        await pg.locator("#signout").click()
        await pg.wait_for_selector("#gate:not([hidden])")
    await pg.locator(f'[data-as="{who}"]').click()
    await pg.wait_for_selector("#shell:not([hidden])")
    await pg.wait_for_selector(".tdrow, #todayNew", timeout=15000)


async def main():
    s = sup()
    print("  reset:", s.post("/api/demo/reset").json()["runnable"])
    # one customer ready to register, so Today has a call to make
    bill = next(f for f in s.get("/api/registration/SS-2045").json()["fields"] if f["key"] == "bill_name")["value"]
    s.post("/api/registration/SS-2045/confirm", json={"key": "bill_name", "value": bill}).raise_for_status()
    s.put("/api/registration/SS-2045", json={"email": "vaishali.p@example.com", "kw": "3"}).raise_for_status()

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1366, "height": 768})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        await pg.goto(BASE, wait_until="networkidle")
        check("sign-in screen renders", await pg.locator("#gate h1").is_visible())

        # ---- the supervisor's day ----
        await sign_in(pg, "r.deshmukh")
        menu = await pg.locator(".navitem:visible").evaluate_all("els => els.map(e => e.dataset.view)")
        check("the menu has six places: Today, Registration, Installation, Close-out, Audit Trail, Reports", menu == MENU, ", ".join(menu))
        check("no AI calling, number pool, agent runs or pipeline in the menu",
              not {"calls", "numbers", "run", "docs", "pipeline"} & set(menu))
        check("the day opens on Today", await pg.evaluate("S.view") == "today")
        chips = await pg.locator(".topbar .chip:visible").all_inner_texts()
        check("the top bar shows who is signed in, nothing technical", len(chips) == 1 and "Signed in" in chips[0], " / ".join(chips))

        call = pg.locator(".tdrow", has_text="Call Vaishali")
        check("the OTP call to make is listed first", await call.count() == 1 and
              "Call Vaishali" in (await pg.locator(".tdrow").first.inner_text()))
        check("the call line shows the customer's number to tap",
              await call.locator('a[href="tel:+919028144531"]').count() == 1)
        wa = await call.locator('a[href*="wa.me/919028144531"]').get_attribute("href")
        check("the call line carries the WhatsApp heads-up that one SMS code is coming", wa and "a%20code%20by%20SMS" in wa)
        check("only the top line has the filled button", await pg.locator(".tdrow .btn.go").count() == 1)
        lines = await pg.locator(".tdrow").count()
        tag = await pg.locator("#tagToday").inner_text()
        check("the menu badge counts the lines to do", tag == str(lines - await pg.locator(".tdrow.muted").count()), f"{tag} vs {lines}")

        await call.locator("[data-today]").click()
        await pg.wait_for_function("document.querySelector('#rgName') && document.querySelector('#rgName').innerText.includes('Vaishali')")
        nb = pg.locator(".rgnext")
        check("Register now opens that customer at the Register step, with the number to call",
              "Register on PM Surya Ghar" in await pg.locator("#regNext").inner_text()
              and await nb.locator('a[href^="tel:"]').count() == 1 and await nb.locator('a[href*="wa.me"]').count() == 1)

        await pg.locator('.navitem[data-view="today"]').click()
        await pg.locator(".tdrow", has_text="Check what Solara read for Prakash").locator("[data-today]").click()
        await pg.wait_for_function("document.querySelector('#rgName') && document.querySelector('#rgName').innerText.includes('Prakash')")
        await pg.wait_for_timeout(600)
        focused = await pg.evaluate("document.activeElement && document.activeElement.dataset.fval")
        check("Check it opens the customer with the value to check in focus", focused == "bill_name", str(focused))

        await pg.locator('.navitem[data-view="today"]').click()
        await pg.locator(".tdrow", has_text="installation details").first.locator("[data-today]").click()
        await pg.wait_for_function("typeof S !== 'undefined' && S.view === 'closeout' && S.coData")
        check("a close-out line opens that customer in Close-out", await pg.evaluate("S.view") == "closeout")

        for view, needle in [("audit", "audit"), ("reports", "Exports")]:
            await pg.locator(f'.navitem[data-view="{view}"]').click()
            try:   # Reports fills in once its numbers arrive
                await pg.wait_for_function(f"document.querySelector('#otherview').innerText.toLowerCase().includes('{needle.lower()}')", timeout=10000)
            except Exception:
                pass
            check(f"{view} opens", needle.lower() in (await pg.locator("#otherview").inner_text()).lower())

        # ---- a new customer from Today, and the document link ----
        await pg.locator('.navitem[data-view="today"]').click()
        await pg.locator("#todayNew").click()
        await pg.fill("#nName", "Anil Shinde")
        await pg.fill("#nMobile", "9822012345")
        await pg.click("#regCreate")
        await pg.wait_for_selector("#regAskDocs")
        await pg.click("#regAskDocs")
        await pg.wait_for_selector("#askUrl")
        link = await pg.input_value("#askUrl")
        check("a new customer is one name away, then one tap to ask for documents on WhatsApp",
              "/up/" in link and await pg.locator('a[href^="https://wa.me/919822012345"]').count() == 1)
        check("the owner is warned when the link would only open on this computer",
              "only opens on this computer" in await pg.locator("#scrim").inner_text())
        await pg.keyboard.press("Escape")

        # ---- the customer's page: one thing at a time ----
        cust = await b.new_page(viewport={"width": 390, "height": 844})
        await cust.goto(link)
        check("the customer is asked for one thing: step 1 of 3, the electricity bill",
              "Step 1 of 3" in await cust.inner_text("body") and "Electricity bill" in await cust.locator("h1").inner_text()
              and await cust.locator("label.pick:visible").count() == 1)
        check("the customer sees the installer's number for help", await cust.locator('a[href^="tel:"]').count() == 1)
        over = await cust.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("the customer page fits a phone", over <= 1, f"{over}px")
        await cust.close()

        # ---- the viewer: can look, cannot act ----
        await sign_in(pg, "a.more")
        check("viewer signs in", (await pg.locator("#whoRole").inner_text()) == "viewer")
        acts = await pg.locator(".tdrow:not(.muted) [data-today]").evaluate_all("bs => bs.map(b => [b.dataset.act, b.disabled])")
        check("viewer cannot send links or documents from Today",
              all(dis for act, dis in acts if act in ("docs", "sign", "build", "vsig", "field")) and not await pg.locator("#todayNew").is_enabled())

        # ---- the supervisor walks every place in the menu ----
        await sign_in(pg, "r.deshmukh")
        for view, needle in [("today", "Monthly report"), ("reg", "New customer"), ("inst", "customers with filing left"),
                             ("closeout", "installed, not yet on MSEDCL"), ("audit", "Append-only audit trail"), ("reports", "Exports")]:
            await pg.locator(f'.navitem[data-view="{view}"]').click()
            await pg.wait_for_timeout(500)
            body = await pg.locator("#otherview").inner_text()
            check(f"{view} view renders", needle in body, "" if needle in body else " ".join(body[:160].split()))

        await pg.locator('[data-theme-set="light"]').click()
        await pg.wait_for_timeout(250)
        bg = await pg.evaluate("getComputedStyle(document.body).backgroundColor")
        check("light theme applies", bg == "rgb(238, 241, 244)", bg)
        await pg.locator('[data-theme-set="dark"]').click()
        await pg.wait_for_timeout(250)
        check("dark theme applies", await pg.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(12, 14, 17)")
        await pg.set_viewport_size({"width": 420, "height": 860})
        await pg.wait_for_timeout(400)
        over = await pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("Today has no sideways scroll at 420px", over <= 1, f"{over}px")

        real = [e for e in errors if "favicon" not in e.lower()]
        check("no JavaScript errors", not real, "; ".join(real[:2]))
        await b.close()

    print("  reset:", s.post("/api/demo/reset").json()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("   failed:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
