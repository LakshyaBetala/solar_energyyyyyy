# Changelog

All notable changes to Solara. This file lists **uncommitted** work on `feature/k1-completion-v2`,
on top of commit `6a0c2ec` ("K1 completion: duplicates, validation, durable corrections, ...").
Nothing below is committed yet.

## Unreleased

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
