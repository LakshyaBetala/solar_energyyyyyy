# KPI 1 audit: documents to "agreement uploaded"

Audit of milestone 1 on branch `k1-audit`. The branch starts from `k1-rpx` (02fb99d), the K1 completion work.

Audit dates: 6–7 Nov 2026. It covers:

- the owner's real journey;
- what K1 must do at each step against what Solara and the co-pilot extension do;
- the live government portal, read only;
- a manual review in the browser, including a UI/UX pass on desktop and phone;
- every test that was run, before and after the fixes.

## Verdict

| | |
|---|---|
| **In the sandbox** | **Complete.** All 6 K1 steps run end to end with the real co-pilot extension: documents read → details complete → registered → accepted in the vendor login → agreement e-signed on the customer's phone → agreement uploaded. |
| **Tests** | **491 checks in 10 suites, all green.** This includes the new `tests/k1_audit.py`: 92 cases (89 for the audit, plus 3 for the redesigned Registration screen on `k1-ui`), each logged with its input, the expected result, the actual result and the verdict. On the starting branch (`k1-rpx`) the 89 audit cases pass **53 of 89**. |
| **Defects found in this audit** | **36 of the audit cases fail on `k1-rpx`.** All 36 are fixed on `k1-audit`. Four of the defects would have stopped K1 on the real portal or broken a promise to the client: 1. the co-pilot did not load on the real portal at all; 2. a full Aadhaar number could be stored; 3. one crafted image froze the server for 12.8 s; 4. the e-sign evidence for older links could never verify. |
| **On the real portal** | **Partly proven.** The live consumer and vendor login pages were read, and their markup is now a test. Everything after the customer's OTP has **not** been seen, because reaching it needs a real login. Those pages need one live session with the owner (see [Still open](#still-open-needs-a-live-session-with-the-owner)). |
| **The KPI itself** | **Not yet claimed.** It needs 3 real customers, each taking at most 5 minutes of the owner's time, timed with a stopwatch. |

## 1. What KPI 1 is

As agreed in the project plan:

> A new customer goes from documents to **registered on PM Surya Ghar → the client selected as vendor → accepted in the vendor login → vendor agreement uploaded**, all filled by Solara.

The agreement sets four conditions:

1. 3 real new customers.
2. Documents to "accepted in vendor login" in **≤ 5 min of the owner's time each**. Waiting for the customer's OTP does not count.
3. The agreement is e-signed by the customer and uploaded through Solara.
4. Nothing is typed by hand except OTPs, CAPTCHA and fields Solara flagged.

## 2. The owner's real journey

The portal's own published steps were read on the live consumer login page on 7 Nov 2026:

| Portal step | What it says |
|---|---|
| 1 | Mobile number + OTP; then name, state, district and other details; then **email + OTP**; save the profile |
| 2 | A vendor-select pop-up: "Yes" lets the vendor fill the application |
| 3 | Apply: state, district, DISCOM, consumer number → **Fetch Details** (pre-fills from the DISCOM) → fill and submit |
| 4 | After feasibility approval: select the vendor, add bank details (for the subsidy) |
| 5–6 | Installation, DISCOM inspection, subsidy (milestone 2, not K1) |

For one customer, the owner's day looks like this. Owner's hands-on actions are in **bold**.

| # | Real-world step | Who | What K1 must do | What Solara does now | Evidence | Status |
|---|---|---|---|---|---|---|
| 1 | Get the documents from the customer (WhatsApp photo or PDF of the bill, Aadhaar, mobile, email, later the bank passbook) | **Owner** collects; Solara reads | Read each document once; never guess | **Bill PDF** (downloaded from MSEDCL): read by rules, no AI. **Bill photo**: flagged for typing. **Aadhaar**: QR read **offline**; name, address, district and PIN taken; **only the last 4 digits kept**; never sent to a model. **Password-protected e-Aadhaar**: a clear instruction is shown. | milestone1.py:157–167, k1_complete section D, validation | Done (sandbox) |
| 2 | Resolve what doesn't match (the bill name vs the Aadhaar name, two PINs) | **Owner**, one click per flag | Show both values; the owner chooses; the choice survives a re-read | Each conflict shows both values and the one to be filed. A correction lasts until its document is replaced (R11). | milestone1.py:164, validation.py:144, k1_audit R11 | Done |
| 3 | Add the order details (kW, installation cost) and the contact details | **Owner** (kW is one click) | Only the order details are typed; everything is checked as it is typed | **kW**: suggested from the sanctioned load on the bill. **Cost**: flagged "from the vendor's quote"; read back in lakh (Rs 2,10,000). **Email**: required, because the portal verifies it by OTP. Every box has the same rules on screen and on the server. | k1_audit D02–D13, M1–M5, P3 | Done |
| 4 | Customer login on PM Surya Ghar (mobile, CAPTCHA, guidelines tick, Verify, OTP) | Co-pilot fills the mobile; **owner** does the CAPTCHA, the tick and Verify; **customer** reads out the OTP | Fill only the mobile; never the CAPTCHA, the OTP or the tick | Proven on the **live page's markup**. On the live page, the value is also taken by its PrimeNG number box. Nothing was pressed. | real_labels `pmsg-consumer-login` | Done on the login page |
| 5 | Profile (name, email + email OTP, address, state, district, PIN) | Co-pilot fills; **owner** does the email OTP | Fill from the record | Filled on the sandbox pages. **Not yet seen live.** | milestone1.py:192–214 | **Needs the live session** |
| 6 | Vendor pop-up "Yes"; Apply: state, district, DISCOM, consumer number, Fetch Details | **Owner** answers the pop-up and presses Fetch Details; co-pilot fills the boxes | Fill the boxes; never press Fetch or Submit | Sandbox only. The real dropdowns are PrimeNG and will be **listed, not clicked**: the panel names the value to pick. | real_labels `upload-agreement`, panel rules | **Needs the live session** |
| 7 | Application form after Fetch Details; upload the documents; declaration; Submit | Co-pilot fills and attaches; **owner** ticks the declaration and presses Submit | File the bill spelling of the name; never overwrite what the owner typed | 4 documents attached by the co-pilot. The application number is read off the portal page into Solara without typing, and is kept even if Solara thought the customer wasn't ready (R4). | milestone1.py:211–240 | Sandbox; **live labels needed** |
| 8 | Vendor login (email, password, CAPTCHA, OTP to the owner's phone) | **Owner only** | The co-pilot never fills the vendor's own login | Proven on the **live page's markup**: "User/Register Email ID", password, CAPTCHA and "Remember me" are all left alone. | real_labels `pmsg-vendor-login` | Done |
| 9 | Vendor Consent: accept the customer | **Owner** presses Accept; Solara marks the step | Recognise the customer; time documents → accepted | The panel names the customer. Solara marks "accepted" and shows "Documents to accepted" (this includes the OTP wait). | milestone1.py:245–255 | Sandbox |
| 10 | Agreement: printed from the record, e-signed by the customer | **Customer** on their phone | Sign only the exact version sent, on the customer's own number | A WhatsApp link goes to the customer's own number. The customer proves it is them with the **last 4 digits of the consumer number** (5 tries; the message is now in Marathi too, with the tries left). They read the kept copy, sign with a finger, and tick consent. A change after sending stops the signature. The evidence is tied to the customer, the request and the document hash. | k1_complete section E, k1_audit D14, R7, R9, R10, M6; manual phone run | Done |
| 11 | Upload Agreement (cost + PDF ≤ 2 MB) on PM Surya Ghar; Submit | Co-pilot fills and attaches; **owner** presses Submit, then "I pressed Submit" in the panel | The right customer behind the list; a PDF under 2 MB; mark uploaded only once it verifies | The co-pilot finds the row's customer, fills the cost and attaches the signed PDF. "Mark uploaded" requires the agreement to verify end to end. | milestone1.py:269–291, screenshot m1-3 | Sandbox; **live dialog needed** |

**What the owner still types by hand** (KPI condition 4): the kW (one click when it is suggested), the cost (flagged; from the quote), the CAPTCHAs, and the declaration tick. The customer reads out two OTPs: mobile and email. The kW and the cost are register item **D07**. The client has to agree that they count as "flagged fields". That is a wording decision, not a code change.

## 3. The co-pilot extension: what it should do and what it does

| Should | Does | Proof |
|---|---|---|
| Load on the real portal | It did **not**. The manifest matched only `pmsuryaghar.gov.in/*`, but the logins are on `consumer.` and `vendor.` subdomains (P1). The hosts are now added (manifest 1.1.1). | k1_audit P1 |
| Open the right page from Solara | The live links opened the portal's home page (P2). They now open the consumer and vendor login pages. | k1_audit P2, live_mode |
| Fill by visible label, even without ids | The real mobile box has no id, no name and no `label for`. It is found by its label. | real_labels (live markup) |
| Work with PrimeNG inputs | It sets the value with the native setter and sends input, change and blur. The PrimeNG model takes the value (checked on the live page with a dummy number; nothing submitted). | manual, 6 Nov 18:35 |
| Never type an OTP, CAPTCHA or password, never tick a declaration, never press Submit | Held on every page tested, including both live logins | real_labels (8 pages), milestone1.py:199, 231 |
| Never fill the vendor's own login with the customer's data | Held. The "register email / user id / login" labels are never filled. | real_labels `pmsg-vendor-login` |
| Never fill the wrong customer | A blank form asks who it is for (D06). The Fill button now **names the customer** (R5). "Not this customer?" is always shown. | validation, real_labels |
| Say what it filled | It said "Filled 4". After the first fix it read "state state…". It now lists the readable field names. | screenshot m1-2 |
| Leave custom dropdowns to the owner | Lists them and names the value; never clicks them open | panel rules |

## 4. The government website (read only)

These were done:

- The live consumer and vendor login pages were opened.
- Their visible text and form markup were read.
- The markup was saved, with the CAPTCHA image and icons removed, under `tests/real_pages/`.

None of these were done: no login, no OTP or CAPTCHA entered, no button pressed, no data sent. The one value typed was a dummy mobile number, entered into the box to see whether PrimeNG accepts it.

| ID | Found on the live site | Effect on K1 | Fixed |
|---|---|---|---|
| P1 | Customer login at `consumer.pmsuryaghar.gov.in/consumer/#/login`, vendor login at `vendor.pmsuryaghar.gov.in/vendor/#/login` | The co-pilot would not have loaded on either | Hosts added |
| P2 | The two logins are separate pages | Solara's buttons opened the home page | Links fixed |
| P3 | Step 1 verifies the **email by OTP** | A customer with no email cannot register | Email required, starred on screen |
| P4 | Maharashtra application numbers end in **8 digits** (NP-MHSED26-xxxxxxxx) | A number with a missed digit was accepted | Server and screen rule |
| P5 | Vendor login: "User/Register Email ID", password, maths CAPTCHA "Human Check", "Remember me" | It must stay the owner's | Already held; now a test on the live markup |
| P6 | Consumer login: a PrimeNG number box (maxlength 10) with no id or name; a 2-digit CAPTCHA; the guidelines checkbox | Fill the mobile only | Already held; now a test on the live markup |
| P7 | Step 3 "Fetch Details" pre-fills the application from the DISCOM; step 4 selects the vendor after feasibility | The application carries the **bill's** name, so Solara files the bill spelling. The bank passbook is needed later, so it does not block K1. | Matches the build |

## 5. Manual review and UI/UX (browser, desktop 1366×768 and phone 390×844)

The review was walked as the owner: create a customer, upload the bill and Aadhaar, confirm the flag, save the details, register on the sandbox portal, save and replace the application number, accept the customer, send the e-sign link, then sign it as the customer on a phone.

| ID | Finding | Fixed | Test |
|---|---|---|---|
| M1 | The mobile boxes cut "+91 90281 44599" (maxlength 14) | Room for 16; +91, 0 and spaces accepted | k1_audit M1 |
| M2 | A Maharashtra number one digit short was accepted | Refused on the server and on screen | k1_audit M2 |
| M3 | Email was labelled "optional"; the portal needs it | Starred as needed; the label says why | k1_audit M3 |
| M4 | The "missing" highlight stayed after typing, until Save | It clears as soon as the box has a value | k1_audit M4 |
| M5 | The cost was shown as raw digits, so a missed zero was easy to miss | Read back as "Rs 2,10,000" while typing | k1_audit M5 |
| M6 | E-sign wrong digits: English only, no tries left shown | English and Marathi, with the tries left | k1_audit M6 |
| U1 | "Sign out" wrapped onto two lines at 1366 px | The top bar no longer wraps | by eye |
| U2 | Live mode opened on the demo Pipeline | Live mode opens Registration; the demo is unchanged | by eye; ui (demo view unchanged) |
| U3 | The name error message was hard to read | "Use letters and spaces (a full stop, apostrophe or hyphen is fine)" | k1_audit D09 |
| U4 | The Aadhaar box invited the full number | "Last 4 digits (read from the QR)…" | by eye |
| U5 | The co-pilot "Filled:" list was garbled | Readable field names | screenshot m1-2 |
| U6 | The agreement on a phone had tiny text (no viewport) | A phone viewport is added to the response only; the signed document and its hash are unchanged | k1_complete "kept copy" |

**Redesign (branch `k1-ui`).** The owner found the Registration screen too full and the text too small. The screen was redesigned around one next step:

- The four big-number tiles became one line of counts.
- The six step boxes became a slim progress row.
- A single "Next step" bar holds the one filled button, a sentence on why, and what else is needed before registering.
- The section for the current step comes first, finished sections fold, and the full list of values read is folded.
- Text is 15px, labels are 13.5px in sentence case, and hints use a grey that passes AA. Light and dark both hold.

The rules are written down in [../PRODUCT.md](../PRODUCT.md) and [../DESIGN.md](../DESIGN.md). They are checked by k1_audit U7–U9: the current section comes first, the text sizes, and a section the owner opens stays open after a redraw.

Screens:

- after the fixes: [registration details](k1-audit/shots/reg-details-after.png);
- the customer's phone: [sign](k1-audit/shots/esign-phone-sign.png) and [done](k1-audit/shots/esign-phone-done.png);
- the co-pilot on the portal: [verify page filled](screenshots/m1-2-portal-filled.png) and [agreement attached](screenshots/m1-3-agreement-attached.png).

## 6. Every defect, before and after

"Before" is `k1-rpx` (02fb99d), and "After" is `k1-audit`.

**Defect register (K1-D01 to D15, from the earlier K1 test round)**

| ID | Defect | Before | After |
|---|---|---|---|
| D01 | Customers added at the same moment → 500 | pass | pass |
| D02 | Garbage in the consumer number erased the saved one | pass | pass |
| D03 | The cost lost its decimal point | Registration ok; **Close-out route still broken** (8 cases) | pass |
| D04 | The application number could be overwritten silently | pass (the failure on `k1-rpx` is a knock-on of M2) | pass |
| D05 | Steps could be skipped | pass | pass |
| D06 | A blank form pre-selected the previous customer | pass (validation, milestone1) | pass |
| D07 | The owner types kW and cost | partly: kW suggested, cost flagged | **client decision on the KPI wording** |
| D08 | A PIN conflict was settled by one ambiguous click | pass (validation) | pass |
| D09 | No name validation | Validation added, but **real names refused** ("D’Souza" with a phone apostrophe, Marathi with a joiner) | pass |
| D10 | No Aadhaar validation | Registration ok; **the Close-out page stored the full number** (R1) | pass |
| D11 | The consumer number accepted 9–14 digits | pass | pass |
| D12 | Letters in the mobile read as "no mobile" | **Close-out route** still accepted them | pass |
| D13 | Wrong-typed JSON → 500 | **Close-out route** still 200 on garbage | pass |
| D14 | Crafted `?error=` text on the public sign page | pass | pass |
| D15 | "Filled 4" with no names; a console 404 | Favicon ok; the names list was garbled | pass (U5) |

**Independent review of `k1-rpx` (R1 to R12)**

| ID | Defect | Before | After |
|---|---|---|---|
| R1 | A full Aadhaar typed in the Close-out "last 4" box was stored as typed | **FAIL** (999941057058 stored) | only 7058 kept, and nowhere in the audit trail |
| R2 | Confirming the bill's mobile replaced the mobile the owner typed, which is the phone that gets the OTP | **FAIL** | the typed mobile is kept |
| R3 | The Confirm box for the consumer number had no rules | **FAIL** ("abc" accepted) | same rules as Details |
| R4 | The portal's own application number was refused if Solara thought the customer wasn't ready | **FAIL** | the portal's number is always kept |
| R5 | The Fill button did not name the customer it would fill | **FAIL** (5 pages) | names the customer |
| R6 | A refused replacement still wrote a "Replaced" audit row | **FAIL** (partly a knock-on of M2) | the row is written only on success |
| R7 | Real names refused on Details (phone apostrophe, Marathi joiner) | **FAIL** (2 names) | accepted, here and on the e-sign page |
| R8 | The Close-out route could send the agreement before the vendor accepted | pass in this test (the guard is now explicit in `esign.create`) | pass |
| R9 | A link sent before kept copies existed could be signed but never verified | **FAIL** ("no copy … was kept") | a copy is kept at signing, after the unchanged check |
| R10 | A crafted 9000×9000 signature PNG (20 KB) blocked the server | **FAIL** (12.8 s) | refused in 0.02 s |
| R11 | A hand correction could outlive its document | pass in this test (the fix records when each correction was made, so only one made after the latest upload is kept) | pass |
| R12 | A sanctioned load of "3.5 kW approx." crashed the Registration page | **FAIL** (500) | the page loads |

The manual (M1–M6, U1–U6) and portal (P1–P7) findings are in sections 4 and 5. M1–M6 and P1–P3 fail on `k1-rpx`; P4 passes.

## 7. Every test that was run

Run against a local server with synthetic data only. No test contacts a government system.

| Suite | Checks | What it covers |
|---|---|---|
| `smoke` | 61 | the HTTP API end to end, with agent runs against both sandbox portals |
| `ui` | 38 | the dashboard in a real browser: each role, every view, checkpoints answered through the dialogs |
| `closeout` | 59 | details → customer e-sign → six MSEDCL PDFs → co-pilot upload; the consent rules |
| `milestone1` | 44 | **the whole K1 flow with the real extension** on the sandbox portals, screenshots on |
| `k1_complete` | 86 | duplicates, uploads, conflicts, corrections, Aadhaar privacy, agreement evidence and verification |
| `real_labels` | 8 | the co-pilot on 8 portal pages, including **the two live login pages** |
| `validation` | 85 | every field rule, D06 and D08 |
| `k1_audit` | 92 | **this audit**: D01–D15, R1–R12, M1–M6, P1–P4, and U7–U9 for the redesigned screen, each logged |
| `longevity` | 11 | old databases upgrade, the health check, pinned versions |
| `live_mode` | 7 | a fresh live install: empty, no demo accounts, real portal links |
| **Total** | **491** | **all green** |

Logs, committed with this audit:

- [k1-audit/k1_audit_log.md](k1-audit/k1_audit_log.md) (also `.json`): all 92 cases, each with its input, expected result, actual result and verdict.
- [k1-audit/suites/](k1-audit/suites/): the full output of every suite, one log each, every PASS line.
- [k1-audit/baseline_k1-rpx_audit.log](k1-audit/baseline_k1-rpx_audit.log): the same 89 cases on `k1-rpx`, **53 pass, 36 fail**.
- [k1-audit/baseline_k1-rpx_real_labels.log](k1-audit/baseline_k1-rpx_real_labels.log): `k1-rpx` on the real-page labels, **3 pass, 5 fail** (R5).

To re-run:

```
python -m uvicorn app.main:app --port 8900      # terminal 1
python tests/run_all.py                         # terminal 2: all 10 suites
python tests/k1_audit.py                        # rewrites docs/k1-audit/k1_audit_log.*
```

CI runs the audit on every push to main and on every pull request (the "KPI 1 audit" step).

## Still open: needs a live session with the owner

None of these can be proven without the owner logged in to the real portal.

1. **The pages after the OTP.** These are the profile, the vendor pop-up, Apply with its DISCOM dropdowns and Fetch Details, the application form, the document upload, Vendor Consent and the Upload Agreement dialog. For each new screen, save the page (Ctrl+S) and add it to `tests/real_pages/` with what must be filled and what must be left alone, as was done for the two logins.
2. **The stopwatch.** For 3 real customers, time the owner's hands-on minutes from "documents in Solara" to "accepted in the vendor login". Pause while waiting for the customer's OTP. Note every field typed by hand. Solara's own "Documents to accepted" figure includes the OTP wait, so it is an upper bound.
3. **The agreement wording.** The panel still shows "DRAFT format; the client has not approved the wording yet". The client must approve the text before a real customer signs it.
4. **D07.** The client must agree that the kW and cost count as flagged fields, or K1 condition 4 must be reworded.
5. **Real documents.** Check real MSEDCL bill PDFs and Aadhaar photos from the client's customers against the reader. They stay on the client's machine and are not committed.

## Files changed on this branch

| Area | Files |
|---|---|
| App | `app/config.py`, `app/registration.py`, `app/valid.py`, `app/extract.py`, `app/closeout.py`, `app/main.py`, `app/esign.py` |
| Co-pilot | `extension/manifest.json`, `extension/panel.js` |
| Dashboard | `web/app.js`, `web/index.html`, `web/styles.css` |
| Tests | new `tests/k1_audit.py` and `tests/real_pages/` (live markup); updates to `real_labels`, `k1_complete`, `milestone1`, `live_mode`, `run_all` and the CI workflow |
