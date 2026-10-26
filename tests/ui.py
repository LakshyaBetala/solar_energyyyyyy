"""UI test. Drives the dashboard in a real browser the way the presenter will:
signs in, walks every view, starts a run, resolves all four checkpoints through the
modals, and asserts the application number lands on screen.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/ui.py                             (in another)
"""
import asyncio, re, sys
from playwright.async_api import async_playwright
sys.path.insert(0, ".")
from app import db  # noqa: E402

BASE = "http://127.0.0.1:8900"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main():
    cid = "SS-2045"
    db.ex("DELETE FROM portal_applications")
    db.ex("DELETE FROM portal_sessions")
    db.ex("UPDATE customers SET application_no=NULL, stage='docs' WHERE id=?", (cid,))

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1500, "height": 950})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # any run left held by an earlier attempt would reopen its gate on sign-in
        import httpx
        with httpx.Client(base_url=BASE) as hc:
            hc.post("/api/login", json={"username": "s.kale", "password": "demo"})
            act = hc.get("/api/bootstrap").json().get("active_run")
            if act:
                hc.post(f"/api/runs/{act}/stop")
                print(f"  (stopped run {act} left held by an earlier attempt)")

        await pg.goto(BASE, wait_until="networkidle")
        check("sign-in screen renders", await pg.locator("#gate h1").is_visible())

        # ---- RBAC through the UI ----
        await pg.locator('[data-as="a.more"]').click()
        await pg.wait_for_selector("#shell:not([hidden])")
        check("viewer signs in", (await pg.locator("#whoRole").inner_text()) == "viewer")
        await pg.locator('[data-view="pipeline"]').click()
        btn = pg.locator('[data-run="SS-2045"]')
        check("viewer sees Run agent disabled", await btn.is_disabled())

        await pg.locator("#signout").click()
        await pg.wait_for_selector("#gate:not([hidden])")
        await pg.locator('[data-as="r.deshmukh"]').click()
        await pg.wait_for_selector("#shell:not([hidden])")
        check("supervisor signs in", (await pg.locator("#whoRole").inner_text()) == "supervisor")

        # ---- walk the views ----
        for view, needle in [("pipeline", "Application pipeline"), ("numbers", "Dedicated number pool"),
                             ("calls", "Call log"), ("audit", "Append-only audit trail"),
                             ("reports", "Exports"), ("docs", "Documents on file")]:
            await pg.locator(f'[data-view="{view}"]').click()
            await pg.wait_for_timeout(450)
            body = await pg.locator("#otherview").inner_text()
            check(f"{view} view renders", needle in body, needle if needle not in body else "")

        # ---- extraction through the UI ----
        await pg.locator("#extract").click()
        await pg.wait_for_selector(".fld", timeout=30000)
        n = await pg.locator(".fld").count()
        flagged = await pg.locator(".fld.review").count()
        check("extraction populated the field list", n >= 14, f"{n} fields")
        check("one field flagged for review in the UI", flagged == 1, f"{flagged} flagged")

        # ---- the run ----
        await pg.locator('[data-view="run"]').click()
        await pg.select_option("#runcid", cid)
        check("idle browser pane explains itself",
              "Start run" in await pg.locator("#stageIdle").inner_text())
        await pg.locator('[data-speed="4"]').click()
        await pg.locator("#bstart").click()

        seen = []
        for _ in range(140):
            await pg.wait_for_timeout(700)
            if await pg.locator("#scrim:not([hidden])").count():
                title = (await pg.locator("#mtitle").inner_text()).strip().lower()
                if title.startswith("otp"):
                    seen.append("otp")
                    body = await pg.locator("#mbody").inner_text()
                    code = re.search(r"\b(\d{6})\b", body).group(1)
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
                    await pg.locator("#appgo").click()
                else:
                    print(f"      !! unexpected modal: {title!r}")
                    break
                await pg.wait_for_timeout(500)
                continue
            state = (await pg.locator("#runstate").inner_text()).strip()
            if state in ("Completed", "Failed", "Stopped"):
                break

        state = (await pg.locator("#runstate").inner_text()).strip()
        check("run completed in the UI", state == "Completed", state)
        check("all four checkpoints appeared as modals",
              seen == ["otp", "captcha", "fix", "approve"], str(seen))

        frame_src = await pg.locator("#frame").get_attribute("src")
        check("live frames reached the browser pane",
              bool(frame_src and frame_src.startswith("data:image/jpeg")),
              (frame_src or "")[:28])
        shots = await pg.locator(".shot").count()
        check("evidence thumbnails rendered", shots >= 5, f"{shots} thumbnails")
        fails = await pg.locator(".shot.fail").count()
        check("a failure screenshot is marked in the UI", fails >= 1, f"{fails}")
        steps_done = await pg.locator('.step[data-s="done"]').count()
        check("step list shows completed steps", steps_done >= 11, f"{steps_done} done")
        log_lines = await pg.locator("#log .le").count()
        check("live log streamed", log_lines >= 25, f"{log_lines} lines")

        await pg.locator('[data-view="pipeline"]').click()
        await pg.wait_for_timeout(500)
        txt = await pg.locator("#otherview").inner_text()
        check("pipeline now shows the application number", "PMSG/MH/" in txt)
        check("stage advanced to DISCOM feasibility", "DISCOM feasibility" in txt)

        await pg.locator('[data-view="audit"]').click()
        await pg.wait_for_timeout(400)
        a = await pg.locator("#otherview").inner_text()
        check("audit shows the supervisor approval", "APPROVED final submission" in a)
        check("audit shows the filing", "Application filed" in a)

        # ---- theme + responsive ----
        await pg.locator('[data-theme-set="light"]').click()
        await pg.wait_for_timeout(250)
        bg = await pg.evaluate("getComputedStyle(document.body).backgroundColor")
        check("light theme applies", bg not in ("rgb(12, 14, 17)", "rgba(0, 0, 0, 0)"), bg)
        await pg.locator('[data-theme-set="dark"]').click()

        await pg.set_viewport_size({"width": 420, "height": 860})
        await pg.wait_for_timeout(400)
        over = await pg.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow at 420px", over <= 1, f"{over}px")

        real = [e for e in errors if "favicon" not in e.lower()]
        check("no JavaScript errors", not real, "; ".join(real[:2]))
        await b.close()

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("   failed:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
