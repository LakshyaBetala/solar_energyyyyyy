# Changelog

All notable changes to Solara on the KPI-1 branch, `k1-owner`, newest first. Which branch holds what,
and what is next: [docs/BRANCHES.md](docs/BRANCHES.md). The client's 7 Nov walkthrough, broken down
into every portal step and field: [docs/PRE_INSTALLATION_FIELDS.md](docs/PRE_INSTALLATION_FIELDS.md).

## 2026-11-07: the owner's way of working, and the customer login (k1-owner)

After the 7 Nov meeting with the owner: he works alone, logs in as each customer with their OTP, and
walked through the whole pre-installation process on the real portal. All 10 suites are green after
each change.

### Added
- **Today** is the home page: one list across all customers in plain words (calls to make, to do in
  Solara, on the government website, waiting for the customer), one button per line.
- **OTP calls**: the call line shows the customer's number to tap and a ready WhatsApp heads-up that
  a code is coming. The owner taps Send; Solara sends nothing itself.
- **Customer document link** (`/up/<token>`): the customer sends the bill, Aadhaar, passbook, roof
  photo and email from their own phone, one thing at a time. Links use `SOLARA_PUBLIC_URL`.
- **Seventh step, "Customer approved it on the portal"**: after the vendor uploads the agreement, the
  customer approves it in their own login. Today shows the call; the co-pilot shows the steps in the
  approval dialog and a mark button; the dashboard has "Mark it approved".
- **The co-pilot reads the customer login's ten-stage tracker** (My Applications) and updates Solara:
  agreement uploaded, customer approved. A tracker behind Solara moves nothing back.
- **Vendor and customer logins side by side** from Today and the upload step. What one window marks
  shows at once in the other window's panel; the dashboard refreshes when the owner comes back to it.
- **More fields filled**: State, District and DISCOM dropdowns on the live portal; gender (Aadhaar QR);
  subsidy bank details (account type, bank name from the IFSC, IFSC, holder); "Proposed kWp".
- The co-pilot reads the vendor's **My Application** list and marks customers accepted.
- **"Send this page's layout to Solara"**: the field names, types and choices of a real page, never values.
- **Connect the Chrome helper** button on Today (it was only reachable from Close-out before).
- Docs: `K1_AUDIT.md` (89 cases), `UX_AUDIT.md`, `K1_NEEDED_FROM_CLIENT.md`, `K1_FIRST_REAL_TRIAL.md`,
  `PRE_INSTALLATION_FIELDS.md`, `BRANCHES.md`, `PRODUCT.md`, `DESIGN.md`.

### Changed
- **Email is optional**, as on the real portal. It no longer blocks registering, and there is no
  email OTP unless one is entered.
- The registration screen is built around one next step; 15px text; finished sections fold.
- The menu shows five places: Today, Registration, Close-out, Audit Trail, Reports.
- kW is one tap; district is the portal's own list of 36 Maharashtra districts.
- Files sent to the portal: photos become JPEG under 2 MB (the pre-installation photo under 1 MB); a
  PDF over 2 MB is refused with a message instead of failing on the portal.
- "Do you want the Vendor to fill…": the panel says answer No.

### Fixed
- The customer's approval was silently not stored (`agreement_approved_at` was missing from the
  allowed close-out keys).
- A demo database with its documents removed crashed at startup on a customer with no address.
- All 89 audit cases (53 passed on k1-rpx), among them: the e-sign page took 12.8 s on a huge
  signature (now refused in 0.02 s), a viewer could type in a check box, "3.5 kW approx." crashed the
  page, and the owner's OTP mobile could be replaced by the bill's.

## 2026-11-04 to 06: K1 completion and validation (feature/k1-completion-v2, k1-rpx)

### Added
- **Full Aadhaar number entry.** A 12-digit Aadhaar number can be typed in a new "Aadhaar number" box
  under Details. It is checked on this computer (12 digits, does not start with 0 or 1, Verhoeff
  check digit) and then cut to its last 4 digits. The full number is never stored, never logged and
  never sent to an AI model. The box also takes the last 4 digits alone or the masked form
  `XXXX XXXX 1234`, so saving the form again changes nothing. The same check is used when
  confirming a flagged Aadhaar field. (`app/valid.py`, `app/registration.py`, `app/extract.py`,
  `web/app.js`)
- **Input rules for every registration field**, in one new module `app/valid.py`:
  - name: letters, spaces, `.` `'` `-` only, 3 to 60 characters, Marathi names allowed
  - mobile: 10 digits starting 6 to 9; letters refused; `+91` prefix tolerated
  - consumer number: exactly 12 digits, a repeated digit refused, spaces and hyphens tolerated
  - installation cost: rupees with up to 2 decimals, Rs 10,000 to Rs 25,00,000, `Rs`/`₹`/commas allowed
  - capacity: 0.5 to 10 kW
  - email, PIN code (6 digits), IFSC, application number
  - values of the wrong type (a list or object where text belongs) are refused
- **Live checks on the registration page** (`web/app.js`, `web/styles.css`): a hint and an error under
  each field while typing, required-field marks, number keypads on phones, maximum lengths, and Save /
  Add customer disabled while any field is invalid. The same Verhoeff check runs in the browser.
- **One-click capacity suggestion**: "Use 3 kW", worked out from the bill's monthly units and the
  sanctioned load. It is never saved by itself. (`registration.suggest`)
- **Explicit PIN choice** when the bill and the Aadhaar disagree: two buttons, "Use 411001 (bill)"
  and "Use 410503 (Aadhaar)". The chosen PIN is the one filed.
- **Module technology** is filled by the co-pilot from the `SOLARA_MODULE_TYPE` setting (default
  `Mono PERC (DCR)`) and flagged "check these".
- **Application number replacement**: a supervisor can replace a saved number (with confirmation in the
  UI); the change is recorded in the audit trail.
- **New test suite** `tests/validation.py` (85 checks), added to `tests/run_all.py` and the CI workflow.
- **Reports** (all under `docs/`):
  - `K1_TEST_REPORT.md`: the first, pre-fix run
  - `K1_ACCEPTANCE_REPORT.md`: the revamped report after the fixes
  - `K1_DEFECT_REGISTER.xlsx`: 15 defects with steps, evidence, status and retest columns
  - `k1-evidence/` and `k1-retest-evidence/`: screenshots from the two runs

### Changed
- **AI is off by default, and never used for basic tasks.** A model is tried only if
  `SOLARA_USE_AI=1` **and** an API key are both set, and then only for a bill the rules cannot read at
  all. Before, any key switched it on, and it ran as a "second opinion" on every text bill.
  Reading a bill's text, the Aadhaar QR, validation and the Aadhaar check all run on plain rules.
  Updated: `app/extract.py`, the health check message, the Documents hint in the UI, `.env.example`,
  `README.md`, `docs/HANDOVER.md`.
- **Co-pilot** (`extension/panel.js`):
  - a finished registration is no longer carried onto the next blank customer form; the panel asks who
    it is for. A customer you pick yourself is kept.
  - the "Filled" summary lists the field names instead of a bare count.
  - labels "Module technology" / "Panel type" are now recognised.
- **Cost is stored exactly as entered.** `250000.50` stays `250000.50`.
- The e-sign page signer name now follows the same name rule.

### Fixed
- Two people adding a customer at the same moment could give a server error (the same ID was picked
  twice). It now retries; 12 simultaneous adds all succeed. (`registration.create`)
- A garbage consumer number (`abc`) erased the saved one. It is now refused and the saved value kept.
- A cost with a decimal point was inflated 100 times (`250000.50` became `25000050`); `-250000` lost its
  sign and was saved as `250000`; `Rs 1.5 lakh` became `15`. All now refused or kept correctly.
- One bad field no longer saves the others; nothing is saved until every field passes.
- The application number could be silently overwritten by re-registering. It is now refused unless a
  supervisor replaces it.
- Steps could be skipped: a customer with no documents could be registered, accepted and sent an
  agreement link. Registering and sending the agreement now need the documents read and the details
  complete; accepting needs registering first.
- Wrong-typed input (login, name, mobile, capacity, consumer number, email, cost, application number,
  step, key) gave a 500 error. It now gives a 400 with a clear message. (`app/main.py`)
- A garbage signature posted to the public sign page gave a 500. It now shows "The signature could not
  be read. Please sign again."
- The public sign page showed any text passed in `?error=`. It now shows only messages the server issued.
- Letters in the mobile number were read as "no mobile". They are now refused.
- The browser console showed a 404 on every page: the browser asked for `/favicon.ico`. It is now
  answered with an empty 204.
- Typing a full 12-digit Aadhaar number into the name box now says where to type it, instead of just
  refusing.

### Tests
- `tests/real_labels.py`: sets the application number directly instead of through the API (the new step
  guard blocks the old shortcut), and marks its customer as "picked" so the co-pilot keeps it.
- `tests/run_all.py` and `.github/workflows/tests.yml` run the new `validation` suite.
- Totals: **397 checks, all passing** (was 312 at the start of this work).
- A scripted 3-customer run through the real browser UI and the extension reached 6 of 6 steps for all
  three, with no findings. Owner time is modelled at about 135 s per customer (an estimate, not a
  stopwatch measurement).

### Known limits (unchanged)
- The real PM Surya Ghar portal, real bills and Aadhaar photos, a drawn signature on a real phone and two
  operators at once are not tested.
- The owner still types installation cost (the vendor's quote), roof area (measured on site) and the
  bank account (kept masked by design). Whether the client counts these as "flagged fields" is open.
- Fixes are verified by automated tests and one scripted browser run, not by a person at the keyboard.
- On a fresh clone, `smoke`, `ui` and `longevity` can fail if the demo documents point at another folder;
  `POST /api/documents/regenerate` fixes it.

## Co-pilot: Start, auto-open and "type it here" (uncommitted)
- **Start button**: after picking a customer, Start begins a one-hour run. Pages fill by themselves (the phone number first); the owner types the OTP and CAPTCHA.
- **Auto-open "Apply for Solar Rooftop"**: during a run the co-pilot opens that card once per page address. It only opens a page, never submits. `tests/k1_complete.py` allows exactly this one extra click.
- **"Solara has no data" box**: a recognised field with no data gets an input in the panel; the typed value is filled on the page and saved in Solara (`event: detail`, validated).
- **Fixed "Extension context invalidated"**: all `chrome.storage` calls go through a guard that never throws; a stale page says "Reload this page (F5)".
- Hands-free option in the options page; `tests/milestone1.py` presses Start.

### Co-pilot: real "Start a new Application" form (uncommitted)
- Read on the live portal (13 Nov 2026): the modal has State, District, Electricity Distribution Company / Utility (PrimeNG dropdowns), Consumer Account Number (CA No.), **Fetch Details**, Next. The home page has four cards: Apply for Solar Rooftop, My Applications, "Do you want vendor to fill the form?", Raise a Query.
- During a Start run the co-pilot presses exactly three non-submitting buttons, once per page: the "Apply for Solar Rooftop" card, **Yes** on the vendor-fills question, and **Fetch Details** (after the consumer number is filled). Next, Submit, OTP and CAPTCHA stay with the owner. `tests/k1_complete.py` checks the list is exactly these three.
- New option "Answer Yes to: vendor fills the form" (default on); the old fixed "Answer No" text now follows it.

### Co-pilot: fallback popup at the bottom (uncommitted)
- A new popup at the bottom of the portal page collects everything the co-pilot cannot fill: a text box for each field Solara has no data for, and a list for each dropdown. Dropdown rows show the page's own options (read by opening the list and closing it again) with a "type to narrow" box, so a long list like the 36 states is easy. When **several options match** a value, or none do, the choices go there instead of the owner being told to "pick it yourself".
- What the owner chooses is filled on the page and, for capacity, cost, mobile, email, consumer number, district and name, saved in Solara.
- The old per-panel input box is replaced by this popup. `tests/real_labels.py` covers the text-field case.
- Read on the live portal: the State dropdown is a PrimeNG single-select with a filter and 36 states.

### Live recording of "Apply for Solar Rooftop" (uncommitted)
- `tools/portal/recording_apply_new_application.md`: the steps, timings and findings from a live run on the consumer login (nothing submitted).
- `tools/portal/apply_new_application.js`: the same procedure as a runnable script (values in `window.SOLARA_VALUES`; returns what the owner still has to do). Replayed live.
- Co-pilot: after Fetch Details it reads the answer. "Data not Available" (seen live for an unknown CA number) now says so and opens the bottom popup to correct the consumer number.

### Co-pilot: suggestions and the bottom popup for unknown fields (uncommitted)
- Suggestion chips ("mini AI", plain rules, no model): for a field Solara has no exact value for, up to 3 values from Solara's data whose names share words with the field label; one tap fills it. An empty dropdown is read and matched against the customer's address (a district named in the address is chosen automatically during a Start run).
- The bottom popup now also covers fields with **no rule at all** (for example "Bank account for subsidy", "Roof area"), and sits bottom-left so it does not cover the co-pilot panel.
- The lookup sends the customer's `place` as well.
- Shown live in the built-in browser on the sandbox portal: Start, phone page, OTP (owner), applicant form (9 filled, 2 through the popup), documents (4 attached). `tests/real_labels.py` has a new browser test for the address-based district pick; it could not run here (Playwright's Chromium is missing on this machine).

### Found and fixed by running the co-pilot on the real PM Surya Ghar portal (uncommitted)
Run live in the built-in browser on the signed-in consumer login, "Start a new Application" dialog (nothing submitted, dialog cancelled):
- **State, District and the distribution company now fill on the real form**, including a District chosen in the bottom popup and the company filling itself afterwards.
- Bug: a blank value from Solara (`""`) counted as a value and matched every dropdown option ("several match"). Blank now means "no value" (`has()`).
- Bug: the distribution-company list is empty until a district is chosen. Dependent dropdowns are now retried after the one above is set, and the popup's "No results found" line is no longer shown as a choice.
- Bug: the portal's modal dialog traps keyboard focus, so typing into the bottom popup was lost and the first option was picked. Key and focus events from the popup no longer reach the dialog.
- Bug: the popup redrew while the owner typed and lost the text. It now keeps what is typed.
- Bug: the portal clears the Consumer Account Number when State, District or Company changes, so text fields are now filled last, after the dropdowns.
- Bug: the address-based district suggestion ran before State was set (district locked). It now runs again after the fill.

### Clean light look (uncommitted)
- Light is now the default theme (dark is still one click away); the choice is applied before first paint so there is no flash.
- `web/styles.css`: a closing override layer gives a minimal, modern look: Inter typeface, white cards with hairline borders and soft shadows, 10 to 14 px rounded corners, one indigo accent, sentence-case labels instead of uppercase, quiet side rail with a soft active state, separate KPI tiles, rounded pills, calm form fields with a focus ring. No markup or script changed beyond the theme default; the dark theme is untouched.
- `web/index.html`: Inter font added.
