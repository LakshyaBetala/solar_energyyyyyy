# Solara — technical handover (Milestones 1 to 3)

**For:** the two technical interns taking Solara to the client's live portals.
**Covers:** what Milestones 1, 2 and 3 are, how the code does them, how to run and test them, the
rules that cannot be broken, who does what next, and what to ask the client (and when).
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
| **K2** | Portal filing, reports, loan and tracking | all post-installation paperwork closed the same day (DCR, installation, six MSEDCL documents), plus the feasibility report and the Jan Samarth application | weeks 2–3 | **built and passing in the sandbox** (`milestone2.py`, 81 checks); prove on real portals |
| **K3** | Dashboard | one screen with every customer's stage and today's to-do list | week 4 | **built and passing in the sandbox** (`milestone3.py`, 42 checks); prove on 10 live customers |
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

## 2a. Milestone 2: agreement uploaded → six documents on MSEDCL

After the agreement, the customer moves from **Registration** to **Installation**. The same pattern
holds: one next-action button decides what comes next (`filing.status()`), the co-pilot fills the
portal page, the owner checks it and presses the portal's own button, then **I pressed Submit** in the
panel stamps the step and keeps the page as the receipt.

| Step | Owner does | Solara does | Code |
|---|---|---|---|
| 1 Site feasibility report | enters the site visit once (roof load, shadow-free roof, area, who visited, location type); opens My Application → Action → Site Feasibility Report → **Fill**; ticks the certificate; Submit; **mark filed** | knows whose dialog it is from the row that was clicked; fills area, permissible kW, quotation amount, visitor and number; answers the three Yes/No questions; attaches the **quotation** (made from the agreement's cost) and the **pre-installation roof photo** | `filing.SFR_NEEDS`, `closeout.t_quotation`, `panel.js YESNO` |
| 2 Loan (only if the customer takes one) | sits with the customer on Jan Samarth; **Fill** on basic details and address | fills name as on Aadhaar, mobile, email, consumer no., capacity, cost, address; **never** the Aadhaar number, OTP, bank or branch (the customer's); saves the reference and the bank's in-principle letter | `app/jansamarth.py` (stand-in), `panel.js RULES` |
| 3 Photos and serials | **Send field team the link** (WhatsApp) | the phone page takes the site photo (GPS from the photo, or from the phone at that moment, printed on the picture) and every panel and inverter label; **serials are read from the barcode on the server (zxing-cpp, offline)**; the owner confirms each beside its photo; repeats are refused | `app/field.py` |
| 4 DCR certificate | logs in to the DCR portal; B2C form → **Fill**; types the invoice date; Submit | fills application no., customer, state, PIN, email, invoice, the panel numbers and quantity; a panel the dealer has not transferred marks **waiting for the dealer**; the certificate number is saved when issued | `panel.js results()`, `app/dcr.py` |
| 5 Installation, 5 steps | My Application → Submit Installation; **Fill** on each step; Save & Next; ticks the declaration; Final Submit; **mark filed** | step 1 vendor, lat/long (replacing the portal's 0.00), location type; step 2 phase, the first inverter row and module row only, serials, DCR number; step 3 the geotagged plant photo under 500 KB; step 4 the protection checklist from the record | `panel.js` (table headers, first row, add-serial) |
| 6 Customer accepts | sends the 3-line WhatsApp message | the next status the co-pilot reads off My Application records the acceptance | `tracker._advance` |
| 7–8 Six documents, MSEDCL | Close-out as before | e-sign, 300 KB pack, the co-pilot attaches all six; the post-installation clock (first field photo → six on MSEDCL) is shown | `closeout.py` |

**Customers installed before Solara** (the client's MSEDCL list shows documents pending for months)
go straight to steps 7–8: `filing.backlog()`.

**Per-customer controls** (the terms' Start, Pause, Resume, Review, Approve, Retry), on the
Installation screen: Start is the next-action button; Pause (with a reason) takes the customer off
Today and the co-pilot shows it; Review lists exactly what the co-pilot will put on a form; Approve
(supervisor) is shown in the panel and turns into "changed since approval" if a value changes; Retry
reopens a filing the portal rejected, with the portal's reason in the audit trail.

## 2b. Milestone 3: Today and the board

- **Board** (Pipeline, top): each customer on the national portal's own ten stages (Registration,
  Application, Feasibility, Vendor selection, Upload agreement, Installation, Inspection, Project
  commissioning, Subsidy request, Subsidy disbursal). When the owner opens **My Application** (or the
  MSEDCL consumer list), the co-pilot reads each row's status and sends it to Solara. It clicks nothing.
  The portal wins on where an application sits; if Solara filed something the portal does not show,
  or the portal rejected it, the customer is flagged. `tracker.py`.
- **Today** (opens first): calls to make (OTPs the portal is waiting for, the customer's own approvals),
  e-signs, filings, dealer waits, field work and checks, each with a button to the right screen.
  Worked out from live data on every load; nothing to maintain by hand.
- **Monthly report**: Today → Excel (every customer with each step's date, the portal's status, the
  month's filings, the audit trail) or PDF.

### Where the milestone 2 and 3 code lives

```
app/filing.py      Milestone 2: the eight steps, next action, marks, retry, pause, review, approve
app/field.py       field team phone page; serial reads (barcode → person confirms → record)
app/tracker.py     Milestone 3: portal stages, status capture, mismatches, Today, the board
app/dcr.py         sandbox: NISE DCR B2C (dealer credit, certificate)
app/jansamarth.py  sandbox: stand-in for the Jan Samarth loan journey (not seen on the call)
app/pmsg.py        + Site Feasibility Report dialog, 5-step installation, later stages
app/exports.py     + receipts (portal page → PDF, network off), DCR Excel, monthly workbook and PDF
web/app.js         VIEWS.today, VIEWS.inst, boardCard()
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
8. **A serial number reaches a document only after a person confirms it beside its photo.** Barcode
   reads are reliable, not infallible; MNRE rejects a wrong or repeated serial and it cannot be undone.
9. **Receipts never carry secrets.** The page snapshot blanks every OTP, CAPTCHA, password and Aadhaar
   number box before it leaves the browser (`snapshot()` in `panel.js`); `milestone2.py` checks it.
10. **The panel never covers the portal's own buttons.** It moves corner or folds (`dodge()`); if a
    real page still gets covered, fix `portalButtons()`, do not tell the owner to work around it.

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
The address in e-sign and field-team links: `SOLARA_PUBLIC_URL=https://…` in `.env` (behind the HTTPS proxy the
server only sees 127.0.0.1; without this, customers would be sent a link they cannot open).
Backups, restore and the encryption key: [OPERATIONS.md](OPERATIONS.md).

---

## 5. Tests

```bash
python tests/run_all.py          # every suite, one summary (server must be running on 8900)
```

| Suite | Checks | What it proves |
|---|---|---|
| `smoke.py` | 61 | API, access control, encryption, extraction, sandbox portals, agent runs |
| `ui.py` | 41 | every dashboard view in a real browser, Today first |
| `closeout.py` | 59 | e-sign consent rules, 300 KB pack, MSEDCL co-pilot (Milestone 2 work) |
| `milestone1.py` | 44 | **K1 end to end** with the extension loaded, plus the failure paths |
| `milestone2.py` | 81 | **K2 end to end**: feasibility report, Jan Samarth, field phone page and barcode serials (repeat, clash, unreadable), DCR with a dealer wait, 5 installation steps, acceptance, e-sign, MSEDCL; receipts free of OTP and Aadhaar |
| `milestone3.py` | 42 | **K3**: ten customers at ten portal statuses, 10/10 stages match, mismatches flagged, Today groups and buttons, every control, monthly Excel and PDF |
| `real_labels.py` | 10 | the co-pilot on the **real field labels** of the client's screens (vendor login, Upload Agreement, site feasibility report with its Yes/No questions, installation steps 1 and 2 with the inverter and module tables, DCR form, MSEDCL login): right values in, CAPTCHA/OTP/vendor-login/site-staff fields left alone |
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

### Manual test script, Milestone 2 (3 times before each client session)

Start from a customer whose agreement is uploaded (run the Milestone 1 script first).

| # | Do | Expect |
|---|---|---|
| 1 | Installation → the customer → fill the site visit, set Loan = Yes, **Save** | button says "File the site feasibility report" |
| 2 | **Review what will be filed** → Site feasibility report | every value shown, quotation and roof photo ✓; Approve (supervisor) |
| 3 | My Application → the row's **Site Feasibility Report** → panel **Fill** | area, kW, amount, visitor filled; Yes/No answered; 2 files attached; certificate box **not** ticked; panel shows "approved by" |
| 4 | Tick, Submit, **mark filed** | step 1 ticked; Receipts → Site feasibility report → View shows the filled dialog |
| 5 | Jan Samarth → **Fill** on basic details | name, mobile, email, consumer no., capacity, cost filled; date of birth and loan amount empty |
| 6 | Aadhaar page | panel fills nothing; Today shows "the portal is waiting for … OTP" |
| 7 | Finish as the customer; on the result page **Save the reference and the approval letter** | reference and letter in the customer's file |
| 8 | **Send field team the link**; open it on a phone; site photo; 6 panel labels (one twice, one blurred) | serials appear as read; the repeat counted once; the blurred one "not readable" |
| 9 | Installation → **Confirm all barcode reads**; type the blurred one; Remove a wrong one; then enter No. of modules = 6 (from the order) and Save | before the count: "Add the number of panels installed", nothing in the record; after: six in the record, step 3 ticked, DCR Excel link appears |
| 10 | DCR → B2C → **Fill** with one panel not in stock | refused; customer shows "Waiting for the dealer" on Today |
| 11 | Credit the panel (sandbox), **Fill**, Submit | certificate number saved by itself; receipt kept |
| 12 | Submit Installation, steps 1–5, **Fill** each | 0.00 replaced by the GPS; only the first table rows filled; plant photo attached; checklist answered; declaration left to you |
| 13 | Final Submit, **mark filed**; sandbox: advance once; open My Application | step 6 ticked by itself (customer accepted) |
| 14 | Close-out → e-sign → generate → MSEDCL → **Attach** → Upload | six on MSEDCL; "Post-installation" time shown on the Installation screen |

### Manual test script, Milestone 3 (3 times before each client session)

| # | Do | Expect |
|---|---|---|
| 1 | Open My Application with the co-pilot | panel: "Read N statuses: N updated in Solara"; nothing on the portal clicked |
| 2 | Pipeline → board | each customer at the portal's stage, the portal's wording and when it was seen |
| 3 | Make the portal reject one filing (sandbox: set a status to "(Rejected)") and read again | that customer flagged on the board and under Today → To check |
| 4 | Today → each group's **Open** | the right screen, the right customer, the right step |
| 5 | Installation → **Pause** with a reason | gone from Today, listed under Paused; co-pilot shows "Paused by …" |
| 6 | **Resume**; **Retry** a filed step with the portal's reason | back on Today; the step to do again; reason in the Audit Trail |
| 7 | Today → Monthly report → **Excel** and **PDF** | every customer with dates and portal status; this month's filings |
| 8 | Sign in as `a.more` (viewer) | Pause, Approve, Retry, Save all refused |

---

## 6. Known limits (read before touching the real portals)

| Limit | What it means | Owner of the fix |
|---|---|---|
| The real **registration** pages are not yet seen | the vendor-side screens from the recording pass `real_labels.py`; the consumer registration and application pages were not shown on the call, so some fields there may land in "Left for you" | Intern A, first client session (A2–A3) |
| The real MSEDCL bill layout is **not yet tested** | `LABELS` in `extract.py` match our sample bill. Real bills may fall back to the AI model (needs the key) or get flagged | Intern B, with real sample bills |
| Angular Material dropdowns (not native `<select>`) | the co-pilot fills native selects; custom dropdowns are listed as "left for you" | Intern A, if the real portal uses them |
| Agreement template is a **draft** | it prints a "draft format" footer until the client's wording is in (`closeout.t_agreement`, `TEMPLATE_DRAFT`) | Intern B |
| Aadhaar QR signature is not verified | the QR data is trusted as printed | later, only if needed |
| One machine, SQLite | fine for one office; PostgreSQL only if several branches use it | later |
| **Jan Samarth was not seen** | `app/jansamarth.py` is a stand-in built from the client's description (basic details, address, Aadhaar OTP, bank and branch, in-principle letter). Real labels will differ | Intern A, first loan customer (A10) |
| **Installation steps 3–5 and the DCR login were not seen** | steps 1–2 come from the recording and MNRE's vendor manual; 3–5 are built from the manual's step names. The DCR certificate number format is a guess (`NISE-B2C-…`); `results()` reads any "Certificate Number" | Intern A, first live installation (A8, A9) |
| The real "+ Add Serial Number" may open a dialog | the co-pilot opens a row's serial box and fills one per line, or one per box if the portal shows several | Intern A (A8) |
| Receipts are the page's own HTML | rendered to PDF with scripts and network off; pictures from the portal's servers are not included | — |
| The field page needs HTTPS on the phone | browsers give a web page the phone's location only over HTTPS (or localhost) | Intern B at deployment (B5) |
| Barcode type on the client's panels is unknown | Code 128 and QR are read; a label with only printed text falls back to the AI key (flagged for confirmation) or typing | Intern B, first real installation (B7) |

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

### K2 — Portal filing, reports, loan and tracking (weeks 2–3) · built, prove it live

**KPI:** 3 real customers from "agreement uploaded" to "6 documents on MSEDCL" through Solara ·
post-installation ≤ 5 min of owner's time each (customer's e-sign not counted) · reports made
automatically, 0 files rejected for size or format · Jan Samarth application submitted up to bank and
branch for 2 loan customers, basic details filled by Solara (the customer enters their own Aadhaar OTP).

**Built and passing in the sandbox** (`tests/milestone2.py`, 81 checks; section 2a): every step below
in code. What is left is **proving each on the real portal with the owner** and fixing what the real
pages do differently. A task is done when the "Done when" column is seen on a real customer.

| Intern A | Done when |
|---|---|
| A7 Site feasibility report on the real dialog: press Fill, note anything left; save the dialog's HTML (customer data removed) into `real_labels.py` | real SFR filled, owner submits, receipt kept · *built* |
| A8 Installation, all 5 real screens: Fill on each; add steps 3–5's real labels and the real add-serial behaviour to `real_labels.py`; fix `RULES`/`YESNO`/`FILES` | real installation submitted through the co-pilot · *built* |
| A9 DCR B2C on the real portal: Fill; confirm the dealer-not-transferred wording matches `results()`; note the real certificate-number format | a real certificate issued, its number saved by itself · *built* |
| A10 Jan Samarth with a real loan customer: Fill; note every label; replace the stand-in's labels in a `real_labels.py` page | 2 loan customers submitted · *stand-in built* |
| A11 MSEDCL on the real page: confirm the six rows match `MSEDCL` in `panel.js` | 6 files attached on the real page · *built* |

| Intern B | Done when |
|---|---|
| B7 Field page with the client's installers on a real roof: photos of the real panel labels; note the barcode type; tune `field.read_codes` if needed | 1 real installation's serials confirmed · *built* |
| B8 The client's report templates (WCR, Annexure-I, DCR declaration, net agreement, QC, quotation) from their Word/Excel files; switch off `TEMPLATE_DRAFT` when all are in | PDFs match the client's formats · *drafts built* |
| B9 Application tracking on real customers: every filed step's time on the Installation screen and in the monthly workbook | every step visible per customer · *built* |
| B10 Post-installation timer on a real customer | time shown per customer · *built* |
| B10a Receipts on the real portals: open each receipt and check it shows what was submitted | every filing has its receipt in Solara · *built* |

### K3 — Dashboard (week 4) · built, prove it live

**KPI:** 10 live customers, stage on screen matches the portal 10 out of 10 · today's list shows every
pending OTP call, e-sign and upload · monthly Excel in one click.

| Intern A | Done when |
|---|---|
| A12 Status capture on the real My Application and MSEDCL lists: the real table may not be a `<table>`; check `listRows()` reads it (it also reads `role=row` grids) and add the real status wordings to `tracker.WORDS` | statuses update without typing · *built* |
| A13 Check 10 live customers against the portals; fix any mismatch | 10/10 · *sandbox 10/10* |

| Intern B | Done when |
|---|---|
| B11 Board on the portal's ten stages, one row per customer | every live customer on one screen · *built* |
| B12 Today: OTP calls, e-signs, uploads, dealer waits, field work, checks, each with a button to the right screen | owner works from the list alone for a week · *built* |
| B13 Monthly Excel and PDF | one click · *built* |
| B13a Start, Pause, Resume, Review, Approve, Retry on the Installation screen | each control used on a live customer · *built* |

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
| Q7 | A8, before the first live installation | "When your next installation is done, can we watch you file it on the portal (all 5 steps) on a screen share? We only watch." | real labels of installation steps 3–5 |
| Q8 | A9 | "Can we watch one DCR certificate being made, from the DCR login?" | real DCR login and certificate page |
| Q9 | A10, when a loan customer comes | "Your next customer taking a loan: can we sit in when they fill Jan Samarth? They type their own Aadhaar and OTP." | real Jan Samarth labels |
| Q10 | B7 | "Which phones do your installers use, and can they open a link with location turned on?" | the field page and GPS |

Do **not** ask the client anything the code, the recording notes or a sandbox test can answer.

---

## 9. Glossary

**PM Surya Ghar / national portal** – pmsuryaghar.gov.in, where customers register and vendors
upload agreements. **Vendor Consent** – where the installer approves a customer who picked them.
**NP-… number** – the application number the portal gives on submission. **DISCOM / MSEDCL** – the
distribution company; its register holds the bill name, which is why the bill spelling is filed.
**Co-pilot** – the Chrome extension. **K1** – Milestone 1's acceptance KPI.
