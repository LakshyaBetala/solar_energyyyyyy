"""UI test. Drives the dashboard in a real browser the way the presenter will: signs in
as each role, walks every view, starts runs from the pipeline, answers every checkpoint
through the dialogs (including a refused approval), and checks what lands on screen.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/ui.py                             (in another)

It resets the demo first and again at the end.
"""
import asyncio, re, sys, httpx
from playwright.async_api import async_playwright
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db  # noqa: E402

BASE = "http://127.0.0.1:8900"
PASS, FAIL = [], []
LIVE = ("Starting", "Running", "Held for a person", "Paused")


async def settled(pg, timeout_s=40):
    """Wait for the run console to reach a final state rather than sleeping a fixed time."""
    for _ in range(timeout_s * 4):
        state = (await pg.locator("#runstate").inner_text()).strip()
        if state not in LIVE:
            return state
        await pg.wait_for_timeout(250)
    return state


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def reset():
    with httpx.Client(base_url=BASE, timeout=60) as hc:
        hc.post("/api/login", json={"username": "r.deshmukh", "password": "demo"})
        return hc.post("/api/demo/reset").json()


async def sign_in(pg, who):
    if await pg.locator("#shell:not([hidden])").count():
        await pg.keyboard.press("Escape")
        await pg.locator("#signout").click()
        await pg.wait_for_selector("#gate:not([hidden])")
    await pg.locator(f'[data-as="{who}"]').click()
    await pg.wait_for_selector("#shell:not([hidden])")
    await pg.wait_for_timeout(500)


async def drive(pg, on_approve=None):
    """Answer each dialog as it appears until the run ends. Returns (dialogs, final state)."""
    seen = []
    for _ in range(180):
        await pg.wait_for_timeout(600)
        if await pg.locator("#scrim:not([hidden])").count():
            title = (await pg.locator("#mtitle").inner_text()).strip().lower()
            if title.startswith("otp"):
                seen.append("otp")
                code = re.search(r"\b(\d{6})\b", await pg.locator("#mbody").inner_text()).group(1)
                for i, d in enumerate(code):
                    await pg.fill(f"#o{i}", d)
                await pg.locator("#otpgo").click()
            elif title.startswith("captcha"):
                seen.append("captcha")
                cap = db.one("SELECT captcha FROM portal_sessions ORDER BY rowid DESC")["captcha"]
                await pg.fill("#capin", cap)
                await pg.locator("#capgo").click()
            elif "correction" in title or "rejected" in title:
                seen.append("fix")
                await pg.locator('[data-choice="use_bill"]').click()
            elif title.startswith("approval"):
                seen.append("approve")
                if on_approve:
                    await on_approve()
                    on_approve = None
                    continue
                await pg.locator("#appgo").click()
            else:
                print(f"      !! unexpected dialog: {title!r}")
                break
            await pg.wait_for_timeout(450)
            continue
        state = (await pg.locator("#runstate").inner_text()).strip()
        if state in ("Completed", "Failed", "Stopped"):
            return seen, state
    return seen, (await pg.locator("#runstate").inner_text()).strip()


async def main():
    print("  reset:", reset()["runnable"])
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1500, "height": 950})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        await pg.goto(BASE, wait_until="networkidle")
        check("sign-in screen renders", await pg.locator("#gate h1").is_visible())

        # ---- viewer ----
        await sign_in(pg, "a.more")
        check("viewer signs in", (await pg.locator("#whoRole").inner_text()) == "viewer")
        check("viewer sees Run agent disabled",
              await pg.locator('[data-run="SS-2045"]').is_disabled())

        # ---- supervisor walks every view ----
        await sign_in(pg, "r.deshmukh")
        for view, needle in [("pipeline", "Application pipeline"), ("numbers", "Dedicated number pool"),
                             ("calls", "Call log"), ("audit", "Append-only audit trail"),
                             ("reports", "Exports"), ("docs", "Documents on file")]:
            await pg.locator(f'.navitem[data-view="{view}"]').click()
            await pg.wait_for_timeout(500)
            body = await pg.locator("#otherview").inner_text()
            check(f"{view} view renders", needle in body)

        await pg.locator('.navitem[data-view="pipeline"]').click()
        await pg.wait_for_timeout(500)
        fus = await pg.locator(".fu").count()
        check("Needs attention lists live follow-ups", fus >= 5, f"{fus} items")
        order = await pg.locator(".stagebar .nm").all_inner_texts()
        check("stage order puts Installation before Net metering",
              order.index("Installation") < order.index("Net metering"))
        check("commercial customer has no Run agent button (not eligible)",
              await pg.locator('[data-run="SS-2044"]').count() == 0)

        # ---- extraction ----
        await pg.locator('.navitem[data-view="docs"]').click()
        await pg.wait_for_timeout(600)
        await pg.locator("#extract").click()
        await pg.wait_for_selector(".fld", timeout=30000)
        check("extraction populates fields", await pg.locator(".fld").count() >= 14)
        check("one field flagged for review", await pg.locator(".fld.review").count() == 1)

        # ---- regression: Run agent starts THAT row's customer ----
        await pg.locator('.navitem[data-view="pipeline"]').click()
        await pg.wait_for_timeout(500)
        await pg.locator('[data-run="SS-2047"]').click()
        await pg.wait_for_timeout(2500)
        started = db.one("SELECT customer_id FROM runs ORDER BY id DESC")["customer_id"]
        check("Run agent on SS-2047 starts SS-2047 (not whichever customer was last open)",
              started == "SS-2047", started)
        await pg.keyboard.press("Escape")
        await pg.locator("#bstop").click()
        state = await settled(pg)
        check("Abandon stops the run", state == "Stopped", state)

        # ---- full rooftop run as the operator, with a refused approval ----
        await sign_in(pg, "s.kale")
        await pg.locator('.navitem[data-view="run"]').click()
        await pg.wait_for_timeout(500)
        await pg.select_option("#runcid", "SS-2045")
        check("workflow follows the customer",
              await pg.locator("#runwf").input_value() == "rooftop_registration")
        await pg.locator('[data-speed="4"]').click()
        await pg.locator("#bstart").click()

        async def refused_then_supervisor():
            label = await pg.locator("#appgo").inner_text()
            check("operator is offered the approval button, not a disabled one",
                  "Try to approve" in label and await pg.locator("#appgo").is_enabled(), label)
            await pg.locator("#appgo").click()
            await pg.wait_for_timeout(900)
            toast = await pg.locator("#toastmsg").inner_text()
            check("server refusal is shown to the operator", "requires the supervisor" in toast,
                  toast)
            await sign_in(pg, "r.deshmukh")

        seen, state = await drive(pg, on_approve=refused_then_supervisor)
        check("rooftop run completed in the UI", state == "Completed", state)
        check("checkpoints appeared as dialogs: OTP, CAPTCHA, correction, approval",
              seen[:4] == ["otp", "captcha", "fix", "approve"], str(seen))
        src = await pg.locator("#frame").get_attribute("src")
        check("live frames reached the browser pane", bool(src) and src.startswith("data:image/jpeg"))
        check("evidence thumbnails rendered", await pg.locator(".shot").count() >= 5)
        imgs_ok = await pg.evaluate("""() => [...document.querySelectorAll('.shot img')]
            .every(i => i.complete && i.naturalWidth > 0)""")
        check("encrypted screenshots decrypt and display", imgs_ok)
        check("live log streamed", await pg.locator("#log .le").count() >= 25)
        check("plan title names the workflow",
              "rooftop" in (await pg.locator("#planTitle").inner_text()).lower())

        # ---- DISCOM workflow from the pipeline ----
        await pg.locator('.navitem[data-view="pipeline"]').click()
        await pg.wait_for_timeout(600)
        await pg.locator('[data-run="SS-2049"]').click()
        await pg.wait_for_timeout(800)
        check("SS-2049 opens on load enhancement",
              await pg.locator("#runwf").input_value() == "load_enhancement")
        seen, state = await drive(pg)
        check("load enhancement completed in the UI", state == "Completed", state)
        check("DISCOM run checkpoints: OTP, approval", seen == ["otp", "approve"], str(seen))
        check("plan shows the DISCOM step list",
              "DISCOM" in await pg.locator("#steps").inner_text())

        await pg.locator('.navitem[data-view="pipeline"]').click()
        await pg.wait_for_timeout(600)
        txt = await pg.locator("#otherview").inner_text()
        check("pipeline shows the new rooftop application number", "PMSG/MH/" in txt)
        check("pipeline shows the DISCOM request", "SR/MH/" in txt)
        await pg.locator('.navitem[data-view="audit"]').click()
        await pg.wait_for_timeout(500)
        a = await pg.locator("#otherview").inner_text()
        check("audit shows the refused approval and the real one",
              "REFUSED approve" in a and "APPROVED final submission" in a)

        # ---- held runs never trap anyone ----
        await pg.locator('.navitem[data-view="run"]').click()
        await pg.select_option("#runcid", "SS-2050")
        await pg.locator("#bstart").click()
        await pg.wait_for_selector("#scrim:not([hidden])", timeout=60000)
        await pg.keyboard.press("Escape")
        check("a checkpoint dialog can be dismissed and reopened",
              await pg.locator("#scrim[hidden]").count() == 1 and
              await pg.locator("#reopen").count() == 1)
        await pg.locator("#bstop").click()
        await settled(pg)

        # ---- theme + phone width ----
        await pg.locator('[data-theme-set="light"]').click()
        await pg.wait_for_timeout(250)
        bg = await pg.evaluate("getComputedStyle(document.body).backgroundColor")
        check("light theme applies", bg == "rgb(238, 241, 244)", bg)
        await pg.locator('[data-theme-set="dark"]').click()
        await pg.set_viewport_size({"width": 420, "height": 860})
        await pg.wait_for_timeout(400)
        over = await pg.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow at 420px", over <= 1, f"{over}px")

        # the one 403 is the approval refusal this test provokes on purpose
        real = [e for e in errors if "favicon" not in e.lower() and "status of 403" not in e]
        check("no JavaScript errors", not real, "; ".join(real[:2]))
        await b.close()

    print("  reset:", reset()["runnable"])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("   failed:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
