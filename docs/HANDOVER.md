# Solara — technical handover (Milestone 1)

**For:** the two technical interns taking Solara to the client's live portals.
**Covers:** what Milestone 1 is, how the code does it, how to run and test it, the rules that
cannot be broken, who does what next, and what to ask the client (and when).
Commercial terms are not part of this document.

---

## 0. The whole project

### The problem
The client is a rooftop-solar installer. For every customer, the owner files paperwork on **four
government portals**, typing the same name, consumer number and address again and again. It takes
about **an hour per application** today:

| Portal | What is filed there |
|---|---|
| **PM Surya Ghar** (national portal) | customer registration and application, vendor consent, the vendor–consumer agreement, the site feasibility report, the 5-screen installation submission, status |
| **NISE DCR portal** | the B2C "made in India" panel certificate with every panel's serial number |
| **MSEDCL rooftop portal** | six documents per customer after installation, PDF only, 300 KB each |
| **Jan Samarth** | the customer's bank-loan application, if they take a loan |

On top of that: Excel macros to make the reports, print, get signatures, scan, shrink the files and
upload them again.

### What Solara is
**Enter once, use everywhere.** The owner adds a customer's documents once; Solara reads them into one
customer record, generates every document, gets the customer's e-signature on their phone, and a
**co-pilot extension in the owner's own Chrome** fills every portal form from that record. The owner
logs in, types the OTP and CAPTCHA, checks the form and presses Submit. One dashboard shows where every
customer stands and what to do next.

### The five milestones (the client's KPIs)

| # | Milestone | Final result the client sees | Planned | Status |
|---|---|---|---|---|
| **K1** | Documents → registration and agreement | a new customer registered, accepted in the vendor login, agreement e-signed and uploaded — in ≤ 5 min of owner's time | week 1 | **built; prove on real portals** |
| **K2** | Portal filing, reports, loan and tracking | all post-installation paperwork closed the same day (DCR, installation, six MSEDCL documents), plus the feasibility report and the Jan Samarth application | weeks 2–3 | built and tested in the sandbox (see [K2_STATUS.md](K2_STATUS.md)); real-portal checks still to do |
| **K3** | Dashboard | one screen with every customer's stage and today's to-do list | week 4 | pipeline and screens exist; to finish |
| **K4** | OTP, security and problem cases | 8 common problems handled without filing anything twice or wrong | week 5 | partly built; to finish and demonstrate |
| **K5** | Live testing and handover | the client's team runs Solara on real customers for 2 weeks | weeks 5–6 | — |

Week 7 is held in reserve. The detailed KPI for each milestone and who does what is in section 7.

---

## 1. Milestone 1 in one line

A new customer's documents go in once; the customer is **registered on PM Surya Ghar → the
installer is selected as vendor → accepted in the vendor login → the vendor agreement is e-signed
by the customer and uploaded**. All portal fields are filled by Solara; the owner types only OTPs
and CAPTCHAs, confirms anything Solara flagged, and presses every Submit.

**Acceptance (KPI K1), all must pass on the client's real customers:**

| # | Check | How it is measured |
|---|---|---|
| 1 | 3 real new customers, each in **≤ 5 minutes of owner's time** from documents to "accepted in vendor login" | stopwatch; time waiting for the customer's OTP is not counted. Solara also shows "Documents to accepted" (includes waiting) |
| 2 | **Customer details read automatically** from the documents; anything unclear is **flagged, never guessed** | the "What Solara read" card: every value has a source; unread items say why |
| 3 | **Agreement e-signed** by the customer and **uploaded through Solara** | step 5 and 6 ticked on the Registration screen; the portal shows the agreement |
| 4 | **Nothing typed by hand** except OTPs, CAPTCHA and fields Solara flagged | watch the owner; the co-pilot panel lists anything "left for you" |

Status today: **built and passing in the sandbox** (section 5). What remains is proving it on the
real portals with the client (section 7).

---

## 2. How it works

```
 Owner's Chrome                                  Solara server (FastAPI + SQLite)
 ┌──────────────────────────────┐   X-Solara-Key  ┌────────────────────────────────────┐
 │ PM Surya Ghar (real portal)  │ ◄────────────►  │ /api/copilot/*   lookup, pending,  │
 │  └ Solara co-pilot extension │                 │                  doc, file, report │
 │    fills by label, attaches, │                 │ registration.py  6 steps + next    │
 │    saves the application no. │                 │ extract.py       bill / Aadhaar QR │
 ├──────────────────────────────┤                 │ closeout.py      agreement + docs  │
 │ Solara dashboard             │ ◄────────────►  │ esign.py         customer signing  │
 │  Registration screen         │   session       │ vault.py         files encrypted   │
 └──────────────────────────────┘                 └────────────────────────────────────┘
                                   customer's phone ──► /sign/<token>  (e-sign page)
```

**Why a co-pilot and not a robot:** the national portal returns HTTP 403 to automated browsers and
every login needs a CAPTCHA plus an OTP to the owner's phone. So Solara works inside the owner's own
Chrome: they log in, the extension fills, they press Submit. **We never try to get past a portal's
security.**

### The flow, step by step

| Step | Owner does | Solara does | Code |
|---|---|---|---|
| 1 Documents read | **+ New customer** (name), upload bill and Aadhaar (photo or PDF) | reads the bill's text layer; reads Aadhaar from its **QR code offline** (zxing-cpp, UIDAI Secure QR or the older XML QR); keeps only the last 4 Aadhaar digits; flags the bill-vs-Aadhaar name difference; fills the record | `extract.py` `run`, `aadhaar_qr`, `apply_to_record` |
| 2 Details complete | confirms flagged fields (one click), types the order's capacity and price | validates mobile, capacity, consumer number | `registration.save_details`, `extract.confirm` |
| 3 Registered | opens the portal; on the blank form picks the customer in the Solara panel; **Fill**; types the OTP; Fill on each page; CAPTCHA; ticks the declaration; Submit | fills by visible label; attaches the bill, Aadhaar, bank page and roof photo to upload boxes; reads the **NP-… application number** off the result page and saves it | `extension/panel.js`; `/api/copilot/report` event `app_no` |
| 4 Accepted | approves the customer in Vendor Consent, then **I approved it** in Solara | stamps the time; times documents → accepted | `registration.mark("accepted")` |
| 5 Agreement e-signed | **Send the agreement for e-sign** → WhatsApp or hands over the phone | the customer enters the last 4 digits of their consumer number, reads, signs once; the signature is bound to that exact document version | `esign.py`, `closeout.doc_hash` |
| 6 Agreement uploaded | My Application → Update Agreement; **Fill** in the panel; Submit; **I pressed Submit** | finds the customer inside the dialog, fills the cost, attaches the signed PDF, marks the step | `panel.js formMode`; event `agreement_uploaded` |

The Registration screen always shows **one** next-action button, decided in
`registration.status()`. If a user is ever unsure what to do, the button says it.

### Where things live

```
app/registration.py   Milestone 1: steps, next action, details, marks, new customer
app/extract.py        document reading: regexes, Aadhaar QR, optional model for photos
app/closeout.py       customer record (closeout.data), document templates incl. the agreement,
                      consent-bound signing, 300 KB fit
app/esign.py          the customer's signing page (English + Marathi)
app/pmsg.py           sandbox: vendor side of the national portal (consent, upload agreement)
app/portal.py         sandbox: consumer side (verify, OTP, form, documents, CAPTCHA, submit)
app/msedcl.py         sandbox: MSEDCL six-document upload (Milestone 2 work, already built)
app/users.py          add / remove people, set passwords
app/config.py         live mode, portal links, state and DISCOM, vendor name (from .env)
extension/            Chrome co-pilot (Manifest V3): panel.js, background.js, options
web/app.js            dashboard; Registration view is VIEWS.reg
tests/                smoke, ui, closeout, milestone1, live_mode, run_all, fixtures
```

---

## 3. Rules that cannot be broken

1. **Never get past a portal's security.** No stealth browsers, no user-agent tricks, no CAPTCHA
   solvers, no OTP readers. The co-pilot runs in the owner's own browser and that is the design.
2. **A person presses every Submit, Upload and Approve.** The extension never clicks them.
3. **The co-pilot never types an OTP, CAPTCHA or password, never ticks a consent or declaration
   box, and never overwrites something already typed.** (`RULES` in `panel.js`, first rule.)
4. **The customer's consent steps stay with the customer**: accepting the agreement on the portal,
   and their e-signature. The signature goes only on documents they approved, in the version they saw.
5. **Aadhaar never goes to an AI model.** It is read from the QR on our server. Only the last 4
   digits are stored. Never log, print or commit a full Aadhaar number.
6. **This repository is public.** No client name, no real customer documents, no pricing, no keys.
   Real samples live outside the repo; fixtures are synthetic (`tests/fixtures.py`).
7. **Run `python tests/run_all.py` before every push.** CI runs the same on GitHub; keep it green.

### Keeping it working for years

Solara's advantage is that it keeps working. These are the habits that protect it:

| Risk | The guard | Your habit |
|---|---|---|
| A library releases a breaking version | `requirements.txt` pins exact versions; `tests/longevity.py` fails if one is loose | upgrade one line at a time, run every test, push only when green |
| A live database is older than the code | `db.MIGRATIONS` upgrades any database once, in order (`PRAGMA user_version`) | a schema change is **a new line at the end** of `MIGRATIONS`; never edit or reorder a shipped line; new tables go in `SCHEMA` |
| A portal renames a field | the co-pilot reports every field it could not fill; **Reports → System health** lists the page and the fields | check System health every Monday; a new entry is a task for Intern A the same week |
| Backups stop, the key is wrong, the disk fills | System health checks all three | look at it weekly; red is fixed the same day |
| A small bug slips in | `ruff` (real-bug rules only, `ruff.toml`) and every test run on each push | never merge with CI red |
| Knowledge leaves with a person | every rule and task is in this file; the PR checklist asks for it to be updated | update HANDOVER.md in the same pull request as the change |

**How changes reach `main`:** work on a branch, open a pull request, fill in the checklist
(`.github/pull_request_template.md`), CI green, Lakshya reviews (`.github/CODEOWNERS`), then merge.
Never push straight to `main` once both of you are working.

---

## 4. Setup

```bash
git clone https://github.com/LakshyaBetala/solar_energyyyyyy.git solara && cd solara
pip install -r requirements.txt
python -m playwright install chromium
python -m uvicorn app.main:app --port 8900        # demo mode, sample data, sandbox portals
```

Open <http://127.0.0.1:8900>, sign in as `r.deshmukh` / `demo` (supervisor) and go to
**Registration**.

**Load the co-pilot:** Chrome → `chrome://extensions` → Developer mode → Load unpacked → the
`extension/` folder. In Solara: Close-out → **Connect co-pilot** gives a key. Extension → Options →
address `http://127.0.0.1:8900` and the key → Save.

**AI key (needed for photos of bills and bank pages):** put `ANTHROPIC_API_KEY=...` in `.env`
(gitignored). Never paste it into chat or commit it. Without it, bill PDFs with a text layer and
Aadhaar QR still read; photos of bills are flagged for typing.

**Live install (the client's machine or server):**

```bash
export SOLARA_MODE=live                    # no demo data, real portal links, reset disabled
export SOLARA_DATA=/srv/solara-data        # its own folder, never the demo's data/
python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
python -m app.users add owner "Owner Name" supervisor     # asks for the password
```

Vendor name and signatory for documents: `SOLARA_VENDOR_NAME`, `SOLARA_VENDOR_SIGNATORY` in `.env`.
Backups, restore and the encryption key: [OPERATIONS.md](OPERATIONS.md).

---

## 5. Tests

```bash
python tests/run_all.py          # every suite, one summary (server must be running on 8900)
```

| Suite | Checks | What it proves |
|---|---|---|
| `smoke.py` | 61 | API, access control, encryption, extraction, sandbox portals, agent runs |
| `ui.py` | 38 | every dashboard view in a real browser |
| `closeout.py` | 59 | e-sign consent rules, 300 KB pack, MSEDCL co-pilot (Milestone 2 work) |
| `milestone1.py` | 44 | **K1 end to end** with the extension loaded, plus the failure paths |
| `k1_complete.py` | 86 | **K1 completion**: duplicates, validation, uploads, mismatches, manual corrections surviving re-reads, Aadhaar privacy, the kept agreement copy and its verification, co-pilot safety on a synthetic portal page, dashboard |
| `k2_complete.py` | 138 | **K2**: SFR, five installation screens, DCR serials, Jan Samarth preparation, MSEDCL evidence and PDFs, field-team uploads and GPS, tracking and receipts, access control, co-pilot on the sandbox K2 pages, Filing screen |
| `real_labels.py` | 6 | the co-pilot on the **real field labels** of the client's screens (vendor login, Upload Agreement, site feasibility report, installation step 1, DCR form, MSEDCL login): right values in, CAPTCHA/OTP/vendor-login/site-staff fields left alone |
| `longevity.py` | 11 | old databases upgrade, dependencies pinned, health check, portal drift reported |
| `live_mode.py` | 7 | fresh live install: empty, no demo accounts, reset refused, real portal links |

`milestone1.py` with `SOLARA_SHOTS=docs/screenshots` saves the four reference screenshots
(`docs/screenshots/m1-*.png`). CI: `.github/workflows/tests.yml` runs all nine, plus the linter, on every push.

### Manual test script (do this 3 times before each client session)

Use the sandbox first; then the same script on the real portals with the owner at the keyboard.

| # | Do | Expect |
|---|---|---|
| 1 | Registration → **+ New customer** → name only | customer appears; button says "Upload the bill and Aadhaar" |
| 2 | Upload a bill PDF and an Aadhaar photo | toast "Read. 1 detail to check."; Aadhaar fields show source "Aadhaar QR"; number shows `XXXX XXXX ____` only |
| 3 | Upload an Aadhaar photo **without** the QR side | "Aadhaar · not read" flagged with the reason; type the name and **Confirm** |
| 4 | Upload a password-protected PDF | flagged: "password-protected… send a photo" |
| 5 | Confirm the name flag, enter capacity and cost, **Save** | button says "Register on PM Surya Ghar" |
| 6 | Enter mobile `12345` and Save | refused: "the mobile number has 10 digits" |
| 7 | **Open customer registration**; in the panel pick the customer; **Fill** | state, DISCOM, consumer number, mobile outlined green; OTP box empty |
| 8 | Type the OTP; on the form, type something in one field first, then **Fill** | your typed value kept; panel says "Kept 1 you had typed" and lists what is left |
| 9 | Documents page → **Fill** | the customer's files attached to the upload boxes |
| 10 | CAPTCHA, declaration, Submit | panel: "Application number NP-… saved in Solara"; dashboard step 3 ticked |
| 11 | Vendor Consent → Approve; in Solara **I approved it** | step 4 ticked; "Documents to accepted" time shown |
| 12 | **Send the agreement for e-sign**; open the link on a phone-sized window; wrong digits once, then right | wrong digits refused; after signing "Thank you"; step 5 ticked |
| 13 | Vendor → Update Agreement → **Fill**, check, Submit, then **I pressed Submit** in the panel | cost filled and `…_agreement.pdf` attached; after marking, step 6 ticked and the button reads "Milestone 1 done" |
| 14 | Sign in as `a.more` (viewer) | every button that changes something is disabled |

Record each run in a sheet: date, who, steps passed, anything odd, screenshots of anything odd.

---

## 6. Known limits (read before touching the real portals)

| Limit | What it means | Owner of the fix |
|---|---|---|
| The real **registration** pages are not yet seen | the vendor-side screens from the recording pass `real_labels.py`; the consumer registration and application pages were not shown on the call, so some fields there may land in "Left for you" | Intern A, first client session (A2–A3) |
| The real MSEDCL bill layout is **not yet tested** | `LABELS` in `extract.py` match our sample bill. Real bills may fall back to the AI model (needs the key) or get flagged | Intern B, with real sample bills |
| Angular Material dropdowns (not native `<select>`) | the co-pilot fills native selects; custom dropdowns are listed as "left for you" | Intern A, if the real portal uses them |
| Agreement template is a **draft** | it prints a "draft format" footer until the client's wording is in (`closeout.t_agreement`, `TEMPLATE_DRAFT`) | Intern B |
| K2 status | see `docs/K2_STATUS.md`: installation screens 2-5 and Jan Samarth labels are not yet seen on the real portals |
| The agreement wording is a draft | see `docs/K1_STATUS.md` for what K1 code is done and what only the live portal or the client can settle |
| Aadhaar QR signature is not verified | the QR data is trusted as printed | later, only if needed |
| One machine, SQLite | fine for one office; PostgreSQL only if several branches use it | later |

---

## 7. Who does what: all five milestones

**Intern A owns the portals and the co-pilot. Intern B owns documents, data, the dashboard and
deployment.** Each milestone ends with its KPI demonstrated on the client's real customers; a milestone
is done only when every KPI line passes. Keep the order: never start the next milestone's live work
until the current KPI is signed off.

Every task follows the same loop: **build → add or extend a test → `tests/run_all.py` green → push →
CI green → try it on the real portal with the owner.**

### K1 — Documents → registration and agreement (week 1) · built, prove it live

**KPI:** 3 real new customers · documents to "accepted in vendor login" in ≤ 5 min of owner's time
(OTP wait not counted) · agreement e-signed and uploaded through Solara · nothing typed except OTPs,
CAPTCHA and flagged fields.

| Intern A | Done when |
|---|---|
| A1 Run the manual script (section 5) 3× in the sandbox; log each run | 3 clean runs logged |
| A2 Client session on the **real PM Surya Ghar** (owner at the keyboard): on registration, application, vendor selection, Vendor Consent and Upload Agreement, press Fill and note every field left over. Save each page's HTML (Ctrl+S) with customer data removed | a field list per page |
| A3 Add each real page's labels to `tests/real_labels.py` (it already holds the five screens from the recording and the MSEDCL login); fix `RULES`/`FILES` in `extension/panel.js` until it passes | `real_labels.py` green with the real pages |
| A4 Confirm on the real portal: application number saved without typing; Upload Agreement finds the right customer | both seen working |
| A5 Package the extension (zip + one-page install guide); set the hosted Solara address in Options | owner installs it alone |
| A6 KPI runs 1–3 with the owner, stopwatch per customer | 3 customers ≤ 5 min each, logged |

| Intern B | Done when |
|---|---|
| B1 Collect 3–5 real MSEDCL bills (website PDF and photos) and 3 Aadhaar QR photos **with consent**, kept **outside the repo**; tune `LABELS` in `extract.py` | every sample's consumer no., name, address, PIN, load, tariff, mobile read |
| B2 Add synthetic copies of those layouts to `tests/fixtures.py` with checks | `milestone1.py` covers the real layout |
| B3 Set the AI key on the client install; check photo bills and bank pages read, unsure values flagged | photos read |
| B4 Put the client's agreement wording into `closeout.t_agreement`; drop the draft footer for it | agreement matches the client's format |
| B5 Deploy: server in India (or the owner's PC), HTTPS (e.g. Caddy), `SOLARA_MODE=live`, `SOLARA_DATA`, users via `app.users`, daily backup, vault key kept apart (OPERATIONS.md) | owner signs in at the hosted address; e-sign link opens on a phone |
| B6 Restore drill on a separate folder | a restored document opens |

### K2 — Portal filing, reports, loan and tracking (weeks 2–3)

**KPI:** 3 real customers from "agreement uploaded" to "6 documents on MSEDCL" through Solara ·
post-installation ≤ 5 min of owner's time each (customer's e-sign not counted) · reports made
automatically, 0 files rejected for size or format · Jan Samarth application submitted up to bank and
branch for 2 loan customers, basic details filled by Solara (the customer enters their own Aadhaar OTP).

Already built: the six MSEDCL documents (`closeout.py`), consent-bound e-sign, the 300 KB fit, the
MSEDCL co-pilot attach (`tests/closeout.py`, 59 checks). Field labels for the feasibility report,
installation step 1 and the DCR form are already in `tests/real_labels.py`.

| Intern A | Done when |
|---|---|
| A7 Site feasibility report: values in the record (roof load, shade-free area, permissible kW, visitor, quotation PDF, pre-installation photo); co-pilot fills and attaches; sandbox page + test | real SFR filled, owner submits |
| A8 Installation, all 5 screens: lat/long from the photo GPS, inverter and module rows, DCR certificate number, photos, protection checklist; sandbox copy + test | real installation submitted through the co-pilot |
| A9 DCR B2C certificate: fill from the record; serial numbers as the portal's Excel (column A from row 2); "waiting for dealer" when the panels are not credited | a real certificate issued |
| A10 Jan Samarth: co-pilot fills basic details and address; the customer enters the Aadhaar OTP and picks bank and branch; the approval PDF is saved to the customer | 2 loan customers submitted |
| A11 MSEDCL on the real page: confirm the six rows match `MSEDCL` in `panel.js` | 6 files attached on the real page |

| Intern B | Done when |
|---|---|
| B7 Field-team upload page (phone): GPS photos and serial-label photos; serials read and shown beside their photo for one-tap confirm; count and repeat checks | 1 real installation's serials confirmed |
| B8 The client's report templates (WCR, Annexure-I, DCR declaration, net agreement, QC) from their Word/Excel files; switch off `TEMPLATE_DRAFT` when all are in | PDFs match the client's formats |
| B9 Application tracking: each filed step stored with its time; statuses read when the owner opens a portal list | every step visible per customer |
| B10 Timer for "post-installation": first field upload → six on MSEDCL | time shown per customer |
| B10a Receipts: save each portal acknowledgement (application, agreement, installation, DCR, MSEDCL) to the customer's file | every filing has its receipt in Solara |

### K3 — Dashboard (week 4)

**KPI:** 10 live customers, stage on screen matches the portal 10 out of 10 · today's list shows every
pending OTP call, e-sign and upload · monthly Excel in one click.

| Intern A | Done when |
|---|---|
| A12 Status capture: when the owner opens My Application (PM Surya Ghar) or the MSEDCL list, the co-pilot reports each customer's status to Solara (read-only, no clicks) | statuses update without typing |
| A13 Check 10 live customers against the portals; fix any mismatch | 10/10 |

| Intern B | Done when |
|---|---|
| B11 Pipeline built from real stages (registration → feasibility → agreement → installation → inspection → subsidy), one row per customer | every live customer on one screen |
| B12 "Today" list: OTP calls due, e-signs pending, uploads pending, waiting for dealer, with a button per item that opens the right screen | owner works from the list alone |
| B13 Monthly Excel and PDF export of the pipeline and the audit trail | one click |
| B13a Per-customer controls promised in the terms: Start, Pause, Resume, Review, Approve, Retry (in the co-pilot model: start a step, hold it, carry on, show what will be filed, the owner's approval, re-fill after a failure) | each control works on a live customer |

### K4 — OTP, security and problem cases (week 5)

**KPI:** a live demo with 8 of 8 handled — wrong OTP · OTP not received (resend) · portal session
timeout · internet cut mid-form · file over 300 KB · repeated serial number · photo without GPS ·
dealer panels not yet transferred — plus separate staff logins and one backup restored.

| Intern A | Done when |
|---|---|
| A14 Co-pilot behaviour on wrong OTP, resend, session timeout (re-reads the page and carries on), internet cut (nothing filed twice: status checked before re-filling) | 4 cases shown live |
| A15 Re-test every rule in `real_labels.py` against the real pages again (portals change) | green |
| A15a Screenshot on failure: when a fill or upload fails, the co-pilot saves a screenshot of the page to the customer's file (`chrome.tabs.captureVisibleTab`), never with an OTP shown | a failed step has its screenshot |
| A15b OTP steps on the list: when the co-pilot reaches an OTP field it adds "call the customer" to Today and carries on after | OTP calls appear on Today |

| Intern B | Done when |
|---|---|
| B14 File over 300 KB, repeated serial, photo without GPS, dealer not transferred: each refused with a clear message (most exist; test each on real files) | 4 cases shown live |
| B15 Staff logins with roles for each person; check a viewer cannot change anything; backup restored on demo day | done in the demo |
| B15a Document-retention period the client can set (e.g. delete customer documents N months after subsidy); runs daily; logged | setting works, deletions in the audit |
| B15b Testing and security documentation, and backup and recovery instructions (terms deliverables 10, 11) | documents handed over |

### K5 — Live testing and handover (weeks 5–6)

**KPI:** 10 real customers from order to MSEDCL through Solara · 0 wrong submissions caused by Solara ·
average ≤ 15 min of owner's time per application · staff trained, written guide handed over.

| Intern A | Intern B |
|---|---|
| A16 Sit with the owner on each live customer; log time per customer and every field left over; fix within a day | B16 Log every flagged document and its cause; fix reading problems within a day |
| A17 Installation guide and the co-pilot user manual (with screenshots) | B17 Administrator and user manual for Solara (Registration, Close-out, Today, users, backups) |
| A18 Training session with the owner and staff (portal side) | B18 Training session (Solara side); hand over users, backup copy and key procedure |

**Not in scope unless separately quoted:** MSEDCL new connection, load enhancement and load reduction; AI calling; dedicated or virtual numbers. Source-code handover and IP transfer to the client are still to be confirmed by Almmatix; do not promise either.

**Together, every milestone:** both run `tests/run_all.py` before a client session; after it, write
down what changed, push, and keep CI green. Pair on the KPI runs: A drives the portal side, B watches
Solara and the documents and keeps the stopwatch sheet.

---
## 8. Questions for the client — ask only after the test named, and only if still stuck

Keep each message short, one topic, on the project WhatsApp group.

| # | Ask after | Question (as sent) | Why we need it |
|---|---|---|---|
| Q1 | A1 done, before A2 | "Can we do a 1-hour screen share on Thursday or Friday where you register one new customer on PM Surya Ghar and approve them in Vendor Consent? We will only watch and note the fields." | real page labels (A2–A4) |
| Q2 | B1, if bills fail to read | "Could you share 3 recent electricity bills as the PDF from the MSEDCL website (not photos), with the customer's permission? We use them only to test reading and delete them after." | real bill layout |
| Q3 | A2, if registration asks for it | "Does PM Surya Ghar insist on the customer's email at registration, or is it optional? If needed, do you use your own office email?" | the email field |
| Q4 | B4 | "Please send the Word file of your vendor–consumer agreement, exactly as you use it today." | the agreement template |
| Q5 | step 12 tested, before the first live upload | "Has the portal ever rejected an agreement because the signature was electronic rather than ink? If unsure, we will upload the first one and check it is accepted." | e-signed agreement acceptance |
| Q6 | A6 planning | "For the 3 test customers, can you keep the customer reachable on the phone for the OTP during the session?" | the 5-minute KPI excludes OTP waiting only if the customer answers |

Do **not** ask the client anything the code, the recording notes or a sandbox test can answer.

---

## 9. Glossary

**PM Surya Ghar / national portal** – pmsuryaghar.gov.in, where customers register and vendors
upload agreements. **Vendor Consent** – where the installer approves a customer who picked them.
**NP-… number** – the application number the portal gives on submission. **DISCOM / MSEDCL** – the
distribution company; its register holds the bill name, which is why the bill spelling is filed.
**Co-pilot** – the Chrome extension. **K1** – Milestone 1's acceptance KPI.
