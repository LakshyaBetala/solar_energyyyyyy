# First trial on the real portal (our side, once, before the owner's session)

**Goal:** see the real vendor pages after login with the Solara co-pilot running, and fix what does not
fit, so the owner's first session is not our first contact with those pages. **Nothing is submitted.**

**Who:** one of us at the keyboard, in our own Chrome. The owner on the phone for his vendor OTP.
**Takes:** about 45 minutes. **Needs:** the owner's OK and a time when he can read out the OTP.

## Ground rules

- **Nothing is changed on the portal.** No Save, Next, Accept, Submit, Upload or Reject on any page. Look,
  capture, read; then log out.
- **His password is typed by hand at login and kept nowhere:** not in Solara, `.env`, chat, notes, the
  repo or the browser's password manager (press "Never" if Chrome offers to save it).
- **Stop after 2 failed logins** (wrong CAPTCHA or OTP); the portal may lock the account. Call him first.
- **A page we do not recognise, or any popup asking to confirm: close it and stop.** Note what it was.
- Do not open or download customer documents beyond what each step needs. Real customer data stays on
  the portal; layouts carry field names only.
- Log out at the end. Tell the owner when we are done; he may change his password afterwards.

## Before the call

1. Start Solara on the laptop with its own data folder outside the repo:
   `SOLARA_DATA=<folder> python -m uvicorn app.main:app --port 8900`; open `http://127.0.0.1:8900`
   and sign in.
2. On **Today**, press **Connect the Chrome helper**. In Chrome: `chrome://extensions`, Developer mode on,
   **Load unpacked**, pick the `extension` folder. Open the co-pilot's Options, paste the address and the
   key, Save. The key is shown once; press the button again for a new one.
3. Check: on `https://pmsuryaghar.gov.in` the extension shows no errors (`chrome://extensions` → Errors).

## The trial

| # | Do | Capture | Expect |
|---|---|---|---|
| 1 | Open `vendor.pmsuryaghar.gov.in`, type the email, password and CAPTCHA, press Login; the owner reads the OTP from his phone | — | Logged in; the Solara panel appears bottom right |
| 2 | **My Application** list | The panel reads the list | The panel says "Read N application(s). Nothing new for Solara" (none of his customers are in Solara yet). Write down every different word in the Status column; Solara must learn them |
| 3 | On the list page | Panel → **Send this page's layout to Solara** | A file in `<data>/layouts/` |
| 4 | **Vendor Consent** (Pending and Rejected tabs) | Send layout | Same |
| 5 | Open one existing customer's **Upload Agreement** page (from the row's Action menu). Do not upload | Send layout | The file field and every other field on it are listed |
| 6 | Open one existing customer's **Submit Installation Details**, step 1 only. Do not Save & Next | Send layout | Matches the step-1 page from the recording |
| 7 | If there is one, a customer's **Site Feasibility Report** dialog. Close it without saving | Send layout | Yes/No questions listed |
| 8 | Check the panel never covers a portal button (Save & Next, Submit, Filter) on any page | Screenshot if it does | The panel moves or folds |
| 9 | Log out | — | — |

## After

1. Copy the files from `<data>/layouts/` and turn each into a page in `tests/real_labels.py` with
   **made-up values only**. Run `python tests/run_all.py`.
2. Add the status words from step 2 to `ACCEPTED` / `PAST_AGREEMENT` in `app/registration.py`, with a
   test.
3. Fix what did not fit, push, and only then send the owner the request for his session.
4. Delete the trial data folder (it holds his application statuses).

## What this trial cannot show

The customer's side after login (profile, application form) and a real Vendor Consent acceptance only
happen with a real new customer. They are seen for the first time in the owner's session with his
first test customer; until then they may need typing by hand.
