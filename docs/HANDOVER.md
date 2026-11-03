# Solara — technical handover (Milestone 1)

**For:** the two technical interns taking Solara to the client's live portals.
**Covers:** what Milestone 1 is, how the code does it, how to run and test it, the rules that
cannot be broken, who does what next, and what to ask the client (and when).
Commercial terms are not part of this document.

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
| `live_mode.py` | 7 | fresh live install: empty, no demo accounts, reset refused, real portal links |

`milestone1.py` with `SOLARA_SHOTS=docs/screenshots` saves the four reference screenshots
(`docs/screenshots/m1-*.png`). CI: `.github/workflows/tests.yml` runs all five on every push.

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
| The real portal's field labels are **not yet confirmed** | `RULES` in `panel.js` are written from the recording and common wording. On the real pages some fields may land in "Left for you" | Intern A, first client session |
| The real MSEDCL bill layout is **not yet tested** | `LABELS` in `extract.py` match our sample bill. Real bills may fall back to the AI model (needs the key) or get flagged | Intern B, with real sample bills |
| Angular Material dropdowns (not native `<select>`) | the co-pilot fills native selects; custom dropdowns are listed as "left for you" | Intern A, if the real portal uses them |
| Agreement template is a **draft** | it prints a "draft format" footer until the client's wording is in (`closeout.t_agreement`, `TEMPLATE_DRAFT`) | Intern B |
| Aadhaar QR signature is not verified | the QR data is trusted as printed | later, only if needed |
| One machine, SQLite | fine for one office; PostgreSQL only if several branches use it | later |

---

## 7. Who does what next

### Intern A — portals and the co-pilot

| Task | Done when |
|---|---|
| A1 Run the manual script (section 5) 3× in the sandbox; log results | 3 clean runs logged |
| A2 Client session on the **real PM Surya Ghar** (owner at the keyboard): for each page of registration, application, vendor selection, Vendor Consent and Upload Agreement, open the panel, press Fill, and note every field in "Left for you". Save the page's HTML (Ctrl+S) **without customer data** for offline work | a field list per page |
| A3 Update `RULES` / `FILES` in `extension/panel.js` so every field on those pages fills; add a sandbox copy of any page that differs (in `app/portal.py` / `app/pmsg.py`) and a check in `tests/milestone1.py` | `milestone1.py` green, no "left for you" except OTP/CAPTCHA/declaration on the real pages |
| A4 Check the application-number capture and the dialog detection on the real portal | number saved without typing; Upload Agreement finds the right customer |
| A5 Package the extension (zip + one-page install guide for the owner); set the hosted Solara address in Options | owner installs it alone |
| A6 KPI run 1–3 with the owner: stopwatch each customer, documents → accepted | 3 customers ≤ 5 min each, logged |

### Intern B — documents, data and deployment

| Task | Done when |
|---|---|
| B1 Get 3–5 real MSEDCL bills (PDF from the MSEDCL site and photos) and 3 Aadhaar QR photos **with the customers' consent**; keep them **outside the repo**; run extraction; tune `LABELS` for the real bill layout | consumer no., name, address, PIN, load, tariff, mobile read from every sample |
| B2 Make synthetic copies of the real layouts in `tests/fixtures.py` and add checks | `milestone1.py` covers the real layout |
| B3 Set the AI key in `.env` on the client install and check a bill photo and a bank-page photo read with "sure" values; unsure ones flagged | photo bills read |
| B4 Put the client's agreement wording into `closeout.t_agreement`; switch off the draft footer for it | agreement PDF matches the client's format |
| B5 Deploy: a server in India (or the owner's PC), HTTPS in front (e.g. Caddy), `SOLARA_MODE=live`, `SOLARA_DATA`, users via `app.users`, daily backup, vault key stored apart from backups (OPERATIONS.md) | owner signs in at the hosted address; the e-sign link opens on a customer's phone |
| B6 Restore drill: restore yesterday's backup on another folder and open a document | restore works |

**Together:** before each client session, both run `tests/run_all.py`; after each, write down what
changed and push. Pair on A6 (A drives the portal side, B watches Solara and the documents).

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
