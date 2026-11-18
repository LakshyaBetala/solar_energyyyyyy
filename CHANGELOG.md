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

### Processing bar, missing highlights, and a faster, fuller co-pilot (uncommitted)
- **Solara web:** a slim bar at the top ("Reading the electricity bill with Gemini… 7s") shows while a bill or Aadhaar is being read, on both the Registration and Documents uploads. A red "Still missing" bar lists what the customer still needs (consumer number, name, mobile, capacity); each chip jumps to the field and flashes it, and empty required fields glow red.
- **Co-pilot, customer first:** it asks "Fill this page for:" and only then fills; a "FILLING FOR <name>" header stays on every page with a Change link. The customer's data is fetched the moment they are picked and kept for the tab, so the first page fills at once.
- **Co-pilot, missing data:** a document Solara does not have (passbook, roof photos) is outlined red on the portal and offered in the bottom popup with a file picker; the chosen file is attached to the portal's box.
- **Co-pilot, forward button (opt-in):** after a page is filled it shows "Looks right: press <Save and continue / Upload / Next / Submit>". With the new option "Press Save and continue / Upload / Next / Submit for me" it presses it itself, but only when nothing is missing, the popup is empty, the OTP and CAPTCHA are typed and any declaration is ticked by the person. It never types the OTP or CAPTCHA and never ticks a consent box. Off by default.
- `tests/k1_complete.py` safety check updated for the new button (still limited to the card, Yes, Fetch Details and the gated forward button). Browser tests could not run (Playwright's Chromium is missing).
- `.env` with a Gemini key is now used: AI turns on when a key is present (set `SOLARA_USE_AI=0` to switch off). A bill read took about 19 s and an Aadhaar about 8 s on the first try.

### Installation cost list, extension options page, "Connect extension" (uncommitted)
- **Installation cost is limited to the vendor's price list:** 125000, 143000, 170000, 185000, 200000, 220000, 240000, 250000, 300000 (`valid.COST_OPTIONS`). On the Registration form the field is a dropdown you can also type in; a typed value that is not on the list is refused with the list shown, in the browser and again on the server (400). Decimals are gone. The Close-out page uses the same list as a dropdown. The extension's popup offers the nine amounts as chips when a portal asks for a cost Solara lacks. `registration.quotes()` falls back to this list when there is no quotation folder. Seed customers and the tests were moved onto listed amounts.
- **`extension/options.html` and `options.js` redesigned:** a clean card layout, a Connection card (address, key with Show/Hide, "Save and test"), and three switches that save as you flip them (fill on open, answer Yes to vendor-fills, press Save/Upload/Next/Submit for me), plus a short first-time guide.
- **Solara: "Connect extension" button in the top bar** opens a window with the address and a new key, each with Copy (and Show for the key), and the three setup steps. The key is shown once.
- `tests/validation.py`: cost tests rewritten for the list; the "AI off by default" test now checks that `SOLARA_USE_AI=0` switches it off.

### Co-pilot fills one field at a time, with a toast, and the CA number bug (uncommitted)
- **Bug fixed: the Consumer Account Number was not filled.** The portal re-draws that input whenever State, District or the distribution company changes, so the co-pilot was holding a dead copy of the field. Fields are now found again by meaning at the moment they are filled, and re-filled after any later dropdown change (including a district chosen in the bottom popup, followed by Fetch Details again).
- **Fills one by one, slowly:** each field is scrolled into view, dropdowns are picked with a pause, and text such as the consumer number is typed character by character. A toast at the top reads "Filling State (1 of 3)", "Filling Consumer Account Number (3 of 3)", "Pressing Fetch Details…".
- **Closing toast:** "All filled. Press Next to continue." with the Next button ringed in green; if something is missing it names it ("District still to fill in the box below"); if Fetch Details must be pressed first it says so and rings that button; if the portal has no data for the number it says so.
- **Race fixed:** reading the dropdown lists (for suggestions) no longer opens lists while the automatic fill is running.
- Checked against a copy of the "Start a new Application" dialog built from the user's screenshot (including the field re-draw), not on the real portal (the session had ended).

### Island, paced fill order, and placement options (uncommitted)
- **Fill order on "Start a new Application":** State, District and the distribution company first, then a deliberate pause ("The portal needs a moment. The consumer number is next…", 1.8 s), then the Consumer Account Number typed in, then **Fetch Details** pressed (now whenever the co-pilot has just typed the number, not only in a Start run). Measured on a copy of the dialog: 0.2 s State, 1.1 s District, 2.1 s Company, 3.1 s wait, 4.9 s consumer number, 5.6 s Fetch, 7.1 s "Press Next".
- **Dynamic island** replaces the toast: a dark pill at the top that shrinks to "● Solara · <customer>" when idle, grows with a spring animation and a progress bar while filling, and turns into a green "All filled. Press Next to continue." or an amber warning.
- **Options page, "Where things appear":** island top/bottom and left/centre/right, panel top/bottom and left/right, and the distance from the edge (0 to 120 px). Applied live; the bottom help box always sits on the opposite side of the panel.

### Bento island, a fixed rule for "Start a new Application", no more refresh clicks (uncommitted)
- **The island is the whole interface.** Collapsed it is a small frosted-glass pill; a click opens a bento grid: who you are filling for (with Change), the steps (State, District, Company, Consumer no., Fetch, Ready) with live state, four value tiles (State, District, Company, Consumer no.) that turn green when confirmed, and buttons: Fill now, Retry, Fetch Details, Next, More. When no customer is chosen it shows a picker. The old side panel is hidden by default (options: "Show the classic side panel"; "More" in the island also shows it).
- **Apple-style look:** system font, frosted glass, 32 px corners, spring animation, SF-like colours (blue, green, orange).
- **A fixed rule for the "Start a new Application" box** (`startAppPlaybook`): it starts by itself as soon as that box opens, for the customer you picked, with no refresh click. Order: State, District (from Solara, else the one named in the address, else you choose in the box below), Company, a pause, the Consumer Account Number, Fetch Details. Every step is checked and retried up to three times; at the end it re-checks everything (the portal clears the consumer number when a dropdown changes) and fixes what is missing, then shows "All set. Press Next" and rings Next. Opt-in "press for me" presses Next too.
- **Real mouse clicks** (pointer down/up and click) for Fetch Details and Next, retried and confirmed by the "Consumer Details" panel appearing.
- Measured on a copy of the dialog opened by hand after the co-pilot loaded. Timings in a hidden browser tab are slower because Chrome throttles timers there.

### Fix: the "Start a new Application" rule looped (uncommitted)
- Cause: the portal re-draws the dialog after each step, and the rule treated every re-drawn dialog as a new one, so it started again and again.
- Fix: once the rule has finished (done or failed) it stays finished for that opening of the box. It runs again only when you press **Retry** in the island (or the refresh icon), or when the box has been closed for about 3 seconds and opened again. A page change no longer restarts it.
- Checked on a copy of the dialog: one run, then the dialog was re-drawn and the page address changed twice over 22 s with no new run; Retry started a second run.

### Calm, fast, and it waits for the person (uncommitted)
- **Stops and waits.** When the "Start a new Application" rule has filled everything it says "Filled. Check it, then press Next when you are ready. I will wait." and does nothing more: no clicks, no typing, no page changes, no re-checks. It never presses Next unless "Press for me" is on. It runs again only on Retry, or after the box has been closed and reopened.
- **No loops, no flicker.** The page watcher ignores the co-pilot's own changes and does nothing while a run is active or finished; a run cannot start more than once every 20 s on its own; the island batches its drawing and plays its entrance animation once (it was replaying on every update, which looked like constant refreshing); a hands-free fill on an ordinary page runs once per page.
- **Aggressive and fast by default.** A new Speed setting (Instant / Fast / Smooth, default Fast): faster typing, shorter pauses and quicker dropdown polling. Measured on a copy of the dialog: State, District, Company, consumer number, Fetch Details and the final check in about 2.8 s, then zero page changes for the next 16 s; a number edited by hand afterwards is left alone.

### Site Feasibility Report: the equipment certification box (uncommitted)
- `extension/options.html` / `options.js`: a switch "Tick the equipment certification on the Site Feasibility Report" (`certify`, on). `extension/panel.js` ticks only the box whose text starts "This is to certify that the proposed equipment…" (the portal names it `certificationCheck`) and only when the switch is on; the customer's declarations are still never ticked. Checked on the real dialog: the box answers a click on `.p-checkbox-box` (not on its outer div); the label is five levels up from the hidden input, so the search now goes six.
- Seen live with the previous build: capacity 5.5, contact 8149111471 and the quotation amount went in; the radios did not (fixed since); the box asked for the roof area and the visiting employee's name.

### Site Feasibility Report: Yes, Yes, Yes, same capacity, fixed contact number (uncommitted)
- `app/registration.py`: the three Yes/No answers default to Yes (changeable per customer in Details, flagged as "check"); permissible capacity = the customer's capacity; the contact number comes from `.env` (`SOLARA_SITE_VISITOR_PHONE`, `SOLARA_SITE_VISITOR_NAME` optional), so the client's number is not in the public repo.
- `extension/panel.js`, checked against the real dialog's HTML (opened and cancelled, nothing submitted): the radios are hidden native inputs inside `.p-radiobutton` with value true/false and no id; the "Yes" text sits in the label beside the box and the question in the label above. Options are now read that way and chosen with a plain click on the box. The question is also named from the input's own name (roofLoadCapacity, shadowFreeRoof, vendorVisited), and the rule matching is done on lower-case text.
- The portal's menus answer a plain click, not the pointer sequence: opening "Site Feasibility Report" from Action used the sequence and did nothing (the island sat on "Opening…"); now it uses a plain click. Errors in that step are shown on the island.

### Agreement uploaded for Amanatali Sherali Meer (SS-2002) through the vendor login (uncommitted)
- Done in the real vendor portal with the extension and Claude in Chrome: the extension detected the dialog for that application, checked the names and numbers, and typed the cost 2,20,000 (Rs 220000); the agreement PDF made by Solara (`/api/registration/SS-2002/draft/agreement`, 4 pages, 145 KB) was attached with the file-upload tool; Submit was pressed once. The portal then offered "Update Agreement" in place of "Upload Agreement". Only that application was touched.
- Two bugs found: the real portal formats the cost as 2,20,000, which the extension called "not accepted" (digits are compared now); the file box's own label is "Choose File", so the agreement box was not recognised (the button's text is skipped now, so "Agreement Copy:" is found). Reload the extension to get both.

### Vendor "Upload Agreement" dialog: cost and agreement filled by the extension (uncommitted)
- `extension/panel.js`: the vendor's Upload Agreement dialog is a screen of its own. It names its own customer (application and consumer number), so no customer needs to be chosen. It fills Total Cost of RTS Installation from Solara and attaches the agreement (the signed copy when there is one, otherwise the agreement Solara makes, `GET /api/copilot/draft/{cid}/agreement`, with the customer's uploaded signature on it). Submit stays the person's (or the opt-in press setting).
- A file box whose label is not linked to it (the real portal's says "Choose File") is named by the nearest label before it ("Agreement Copy:").
- Checked on the real vendor portal (read-only, nothing submitted): the application row's chevron opens an expansion row whose Action button opens a menu (Upload Agreement, View Application, Site Feasibility Report, Track Application). `openVendorAction` follows exactly that; the feasibility opener now uses it.

### Consumer login first; Find A Vendor instantly (uncommitted)
- `extension/panel.js`: on the consumer login page (a mobile box with a CAPTCHA or OTP box) it fills the chosen customer's mobile number and puts the cursor in the CAPTCHA box. It never types the CAPTCHA or OTP and never presses Send OTP or Login. No customer chosen: the island asks who. Manual mode: a Fill button.
- Find A Vendor now runs the moment the page is open (no 2 second wait, checked every 0.6 s) and no longer needs a customer chosen.

### Button: Find and select vendor (uncommitted)
- `extension/panel.js`: on the Find A Vendor screen the island (click it to open) has a "Find and select vendor" button that searches the vendor and presses Select Vendor at once, in both modes and whatever the earlier tries did. If the search box is not seen, the island opens by itself so the button is in view.
- Bug fixed: the island's own buttons were answered before the "Vendor login" button, so that button did nothing. Fixed.

### Find A Vendor: finding the search box on the real page, two ways (uncommitted)
- `extension/panel.js` `vendorBox`: (1) the heading "Search Vendor" is found by its text in any tag, and the nearest text box below it is used; (2) otherwise any text box in the left sidebar whose placeholder or label says Search. When neither works the island reports how many text boxes it can see.

### Find A Vendor: why it did not act on the real page (uncommitted)
- Found by reproducing it on the mock: the island's own tile is labelled "Search vendor", and the co-pilot took that label for the page's Search Vendor heading, so it never found the real search box after the first try. Our own island, panel and popup are now ignored when looking for the heading.
- A search box that is itself an autocomplete (`role=combobox`) was being skipped; it is not now.
- The route `#/signed-in/find-vendor` is recognised first; a stale run from the earlier Start box can no longer hold this screen; a failed try repeats after 20 s, a done one is not repeated for 10 minutes.

### Find A Vendor: screen-aware and more reliable (uncommitted)
- `extension/panel.js`: the Search Vendor box is found by where it is on the screen (the nearest ordinary text box under its heading), not by the first input in its container (which could be a dropdown's own box). If the screen is Find A Vendor but the box is not there, the island says so. It searches the full name (default `SOLARSEA ELECTROTECH SOLUTIONS PVT LTD`, changeable in the options), then either clicks the suggestion or, when the page filters its cards while typing, goes straight to the one card left and presses Select Vendor. The island also names the screen it recognises while idle ("Screen: Find A Vendor").

### Site Feasibility Report, quotation PDF, vendor login (uncommitted)
- `app/closeout.py` / `registration.py`: the form's facts (roof load OK, shadow-free roof, roof area, permissible capacity (defaults to the proposed kW, flagged to check), vendor visited, visitor name and phone). Same key names as the K2 branch where they overlap. Facts seen on site are never guessed.
- `app/drafts.py` `docx_to_pdf` (Microsoft Word on Windows, or LibreOffice); `GET /api/copilot/draft/{cid}/quotation?fmt=pdf` (the form takes PDF only, 2 MB at most).
- `web/app.js`: those fields in "Details for the portal".
- `extension/panel.js`: labels of the form, Yes/No questions as radio buttons, dropdowns or boxes; quotation attached as PDF; a box is named by its own label first (a wrapper holding two file boxes had given the photo box the quotation); on the vendor portal it opens Action > Site Feasibility Report for the customer's application by itself (Manual mode: a Fill button); "Vendor login" button on the island opens vendor.pmsuryaghar.gov.in. The certification tick, Submit, OTP, CAPTCHA and passwords stay the person's.
- `tests/validation.py`: three checks adjusted for the new defaults.

### Find A Vendor screen: search "solarsea", pick it, press Select Vendor (uncommitted)
- `extension/panel.js`: on the Find A Vendor screen (customer chosen) it types the word from the options page (default `solarsea`) in Search Vendor, picks the matching line in the list, then presses Select Vendor only when exactly one card names that vendor (never another vendor's). Once per address (Retry repeats). Manual mode shows two tiles with Fill buttons instead.
- `extension/options.html` / `options.js`: "Vendor to select on Find A Vendor" (stored as `vendorSearch`).

### Two modes for the extension: Automatic and Manual (uncommitted)
- Options page: a choice at the top, Automatic (fills every detail, screen after screen) or Manual (shows each value with a Fill button; nothing is filled until pressed). Stored as `mode`; replaces the old "Fill each page as soon as it opens" switch.
- `extension/panel.js`: in Manual the Start box, the screen watcher and the forms only show the values on the island, each with its own Fill button, plus Fill now for all. Found while testing: reading the dropdown lists also filled dropdowns when no run was active (`retryPending` inside `suggestLists`); removed.

### Every new screen fills itself, with live status on the island (uncommitted)
- Why "Fill now" was needed: the automatic fill depended on a click handler and a one-time marker, and the island said "Filling it now" even when nothing would start. 
- `extension/panel.js`: a screen watcher (every 1.2 s) recognises each screen of the application form by its fixed headings, waits 2 seconds and fills it, once per screen and address; no click needed. Issues no longer stop it. Only one fill runs at a time.
- The island opens during the fill with one tile per value (blue while typing, green when done, amber when it needs you), a moving progress bar, then collapses; softer spring easing, message and tile animations.
- Pressing Next shows the portal's refusal reason, or "Looking for the next screen".

### Fix: a name the portal lists twice (Urban Local Body "Pune", "Pune") (uncommitted)
- `extension/panel.js` `pickCustom`: when several options have exactly the same text, the first is chosen instead of asking. Different names that merely contain the word are still left to the person.

### Agreement and quotation uploaded by the extension (uncommitted)
- `app/main.py`: `GET /api/copilot/draft/{cid}/{kind}` (same documents as the Solara buttons, one shared `_draft`). `extension/background.js` fetches it; `extension/panel.js` recognises an upload box labelled Quotation and attaches the quotation (Word file, made from the chosen installation cost's template); the agreement is attached as before once it is signed. A reason (e.g. "pick the installation cost first") is shown when a file cannot be made.

### Position from the bill's address; the next screen fills itself (uncommitted)
- `app/registration.py` `locate`: Urban/Rural, position, urban body and taluka now come from the electricity bill's billing address, PIN and district; the Aadhaar's address is only the fallback.
- `extension/panel.js`: after Next, it waits 2 seconds and fills the next screen on its own; no Fill button to press. This also works inside the 10-minute quiet period after the first box.

### Portal lists for Urban local body and Taluka (Pune district) (uncommitted)
- `app/geo.py`: the portal's 22 urban local bodies and 13 talukas. A map hint or a typed value is kept only if it is a sure match to one (Pimpri-Chinchwad becomes Pimpri Chinchwad, Haveli Subdistrict becomes Haveli); otherwise nothing is guessed. Solara shows them as dropdowns. The village panchayat has no list in Solara: the extension matches the customer's Solara value or one name in the address against the portal's list, else asks the person to choose.

### New: boxes that appear after Urban / Rural; the portal's own errors shown (uncommitted)
- Urban shows "Urban Local Body Name"; Rural shows "Development Block / Taluka" and "Village Panchayat". Rules, Solara fields (`ulb`, `taluka`, `panchayat`, map hint from OpenStreetMap) and a re-look in the co-pilot (up to 4 passes) that fills them or asks with the portal's own list.
- `extension/panel.js`: the portal's red messages (e.g. "must be filled", "capacity is more than the sanctioned load") are read and shown in the island as "The portal says"; if Next is refused it shows why and does not wait for a new screen.

### New: gender, urban/rural, residence category, latitude/longitude, next-screen fill (uncommitted)
- `app/geo.py` (new): latitude, longitude and Urban/Rural from the address through OpenStreetMap Nominatim (no key; the address is sent to that service). `registration.locate`, `POST /api/registration/{cid}/locate`; the co-pilot lookup finds it once when a customer has none.
- `app/valid.py`: `choice` (Gender, Urban/Rural, Residential (usual method) / Residential Welfare Association) and `coord` (inside India). `closeout.FIELDS`: gender, location_type, residence_category, lat, lng. `registration.values`: gender from the Aadhaar unless changed, `category` is now the portal's residence category (default Residential (usual method)).
- `web/app.js`: those fields in "Details for the portal", and a "Find latitude and longitude from the address" button.
- `extension/panel.js`: rule for "Type of Location"; latitude/longitude boxes the portal greys out are still filled; the screens of the application form are recognised by their fixed headings; pressing Next (by anyone) waits for the next screen, asks Solara again and fills it.

### Hardening: the fill can run only once per Start box (uncommitted)
- `extension/panel.js`: instead of timing guesses, a run is tied to the box itself. Each Start-a-new-Application box (page node) is run once (`handled`); the same customer is not run again within 3 minutes even if the portal rebuilds the box (`solaraRun:<id>` lock); Fetch Details at most once per 10 minutes.
- Only the newest copy of the script on a page may act (owner marker); an older copy left by an extension reload stops mid-run.
- Pressing Retry, the refresh icon, or choosing a customer in the island clears the locks, so a deliberate re-run still works.

### Fix: no more "needs your help" popup for fields Solara has no rule for (uncommitted)
- `extension/panel.js`: the header's "Raise a Query" menu was asked about on every page. Only fields Solara has a rule for, and no data, are asked about now; menus and unknown boxes are ignored.

### Fix: the fill ran a second time right after the first finished (uncommitted)
- Found by reading the user's screen recording frame by frame: after the details appeared, the island went back to "Filling State…" and pressed Fetch again.
- Cause: the watcher, its timer and the page-change scan could all start the flow at once; the late ones were still waiting for Solara when the first finished, then ran it again. `startModalFlow` now lets one start at a time and re-checks "finished / box closed" after each wait.

### Fix: Fetch Details pressed again after the details filled; Search box prompt (uncommitted)
- `extension/panel.js`: the once-only guard for Fetch Details was per page address, so when the portal changed its address after Fetch the generic filler pressed Fetch again (rate-limit risk). It is now once per tab per 10 minutes, also counting the Fetch the playbook pressed. The generic filler stays out for 10 minutes after the playbook ran.
- Search / filter boxes are never filled and never asked about (no more yellow "missing field" for Search).

### Fix: the loop on the real portal; stop after Fetch Details (uncommitted)
- **Cause of the loop:** when the "Start a new Application" box opened and no customer was chosen, the co-pilot asked Solara "who is this for?" again every 1.5 s and redrew the island each time. It now asks once per opening of the box and waits for the answer (also when Solara cannot be reached: it says so and waits for Retry). The watcher does nothing while a question is open, only looks for a box when one exists, and the island leaves the page alone when its content has not changed.
- **After Fetch Details it stops.** The "check and fix, up to three rounds" loop after Fetch is gone. The only re-check is one look just before pressing Fetch (the portal clears the consumer number when a dropdown changes). After Fetch, Next is pressed only if "Press Save, Upload, Next and Submit for me" is on in the options; otherwise it waits.
- Checked on a copy of the dialog: no customer chosen: one question in 12 s (was one every 1.5 s); after choosing: Fetch pressed once, Next pressed 0 times, "I will wait"; with the permission on: Fetch once, Next once.
- Server restarted.

## Site Feasibility: nothing left to type
- Shadow-free roof area defaults to 10 m² per kW (change per customer in Details); the visiting employee defaults to the vendor name, or `SOLARA_SITE_VISITOR_NAME` in `.env`.
