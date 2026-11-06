# KPI 1 acceptance report (after fixes)

**Branch:** `feature/k1-completion-v2` · **Environment:** sandbox portals, synthetic data, Chromium with the co-pilot extension
**Replaces the verdict in:** `docs/K1_TEST_REPORT.md` (the first, pre-fix run). The defect-by-defect register is `docs/K1_DEFECT_REGISTER.xlsx`.

**KPI:** 3 new customers registered, accepted in the vendor login and the e-signed agreement uploaded, each in ≤ 5 min of the owner's time; nothing typed except OTP, CAPTCHA and flagged fields.

## 1. Verdict: sandbox passes; not yet signed off

| KPI clause | Before | Now |
|---|---|---|
| 3 customers registered, accepted, agreement e-signed and uploaded | Pass (sandbox) | **Pass (sandbox)**, 3 of 3 at 6/6, re-run after the fixes |
| Each ≤ 5 min of owner's time | Not proven (about 144 s, modelled) | **Not proven** (about 135 s, modelled; needs a real stopwatch) |
| Nothing typed except OTP, CAPTCHA, flagged fields | Fail as worded | **Partly**: see §4 |
| Details read automatically, doubts flagged, never guessed | Pass, with unvalidated inputs | **Pass**, inputs now validated |
| Real PM Surya Ghar portal | Not tested | **Not tested** |

Three things stand between this and sign-off, none of them code: a stopwatch session on the live portal with the owner, the client's decision on §4, and real customers' documents.

## 2. What was fixed

| Defect | Fix | Evidence |
|---|---|---|
| D01 parallel customer creation gave a 500 | retries on an ID clash | 12 simultaneous adds: all 200, 12 different IDs |
| D02 garbage consumer number erased the saved one | refused; saved value kept | `tests/validation.py` |
| D03 cost `250000.50` became `25000050` (×100); `-250000` became `250000` | amount parsed as rupees; decimals kept; negatives, zero, text and out-of-range (Rs 10,000 to 25,00,000) refused | 8 cost cases |
| D04 application number silently overwritten | refused; a supervisor can replace it, audited | API test |
| D05 steps could be skipped | register and send-agreement refused until documents and details are done; accept needs registered | 3 API tests |
| D06 blank form pre-selected the previous customer | a finished registration is not carried over; the panel asks who it is for | UI run: customers 2 and 3 got the pick list, no pre-select |
| D08 PIN conflict settled by one ambiguous click | two buttons naming the value and its source: "Use 411001 (bill)" / "Use 410503 (Aadhaar)" | customer 3 filed 411001 as chosen |
| D09 no name validation | letters, spaces, `.` `'` `-` only, 3 to 60 characters, Marathi allowed | 7 refused, 4 accepted |
| D10 no Aadhaar validation | only the last 4 digits (`1234` or `XXXX XXXX 1234`); a full number is refused; Aadhaar name follows the name rule | 5 refused |
| D11 consumer number accepted 9 to 14 digits | exactly 12 digits; repeated digit refused; spaces and hyphens tolerated | 6 refused |
| D12 letters in mobile accepted as "no mobile" | refused | API test |
| D13 wrong-typed input gave 500 | 400 with a clear message; a garbage signature gives a message | 6 fields, login, application number |
| D14 `?error=` text shown as given | only messages this server issued are shown | API test |
| D15 "Filled 4" summary; one console 404 | the filled field names are listed; worked-out values are flagged "check these"; the 404 was `/favicon.ico`, now answered | UI run, probe |

The registration page also got live checks while typing (hint and error under each field, Save disabled while any field is invalid), required-field marks, number keypads on phones, and a "Replace application no." confirmation.

## 3. Test results

| Suite | Result |
|---|---|
| All repo suites (`tests/run_all.py`) | **381 checks, all pass** (was 312) |
| New `tests/validation.py` | 69 checks, in CI |
| 3 customers through the browser UI and extension, after the fixes | 3 of 3 at 6/6; no findings |

| | Priya | Rahul | Sunita (PIN differs) |
|---|---|---|---|
| 6/6 steps | yes | yes | yes |
| Application number | saved by the co-pilot, not typed | same | same |
| PIN on the portal | 410503 | 410503 | **411001**, as the owner chose |
| Documents to accepted (system timer) | 14 s | 14 s | 15 s |
| Owner actions | 28 | 28 | 29 |
| Modelled owner time | 135 s | 135 s | 136 s |
| Agreement cost / file attached | 210000 / yes | same | same |

The time model is 2 s per click, 8 s per upload, 0.35 s per typed character plus 3 s per field, 20 s of reading. It excludes waiting for the OTP and the customer's e-sign. It is an estimate, not a measurement.

Evidence: `docs/k1-retest-evidence/` (blank-form panel for each customer, the Aadhaar read, the filled portal form, the final state). The earlier run's screenshots are in `docs/k1-evidence/`.

## 4. What the owner still types (the open point)

| Field | Typed by the owner | Why |
|---|---|---|
| Customer name | to create the record | allowed: it starts the record |
| OTP, CAPTCHA | yes | allowed by the KPI |
| Installation cost | yes | it is the vendor's quote; Solara does not guess a price. Shown as a flagged field |
| Roof area | yes, on the portal | it is measured on site; Solara does not guess it |
| Bank account | left to the owner | Solara keeps it masked by design |
| Capacity (kW) | **no longer**: one click on "Use 3 kW", suggested from the bill's units | |
| Module technology | **no longer**: filled from settings and flagged "check" | |

**Decision for the client:** does the KPI count cost, roof area and bank account as "flagged fields"? If yes, K1 is met as worded. If not, they need another source: cost from the quote, roof area from a site visit, bank from the passbook.

## 5. Known limits

- Real PM Surya Ghar pages and dropdowns, real bills and Aadhaar photos, a signature drawn on a real phone, and two operators working at once were not tested.
- The fixes are verified by automated tests and one scripted browser run, not by a person at the keyboard. A short manual re-check of §2 is advised.
- The 5-minute clause needs a stopwatch.
- The Aadhaar-name check is a name rule, not a match against the document.
- Changed vs the earlier suites: `tests/real_labels.py` now sets the application number directly and marks the customer as picked, because the flow guard and the blank-form rule block its old shortcuts.
- `smoke`, `ui` and `longevity` failed before any change when the repo's demo data pointed at a different folder; regenerating the demo documents (`POST /api/documents/regenerate`) fixes it.

## 6. Before sign-off

1. The client decides §4.
2. A stopwatch session on the live portal with the owner, 3 real customers, OTP and e-sign waits excluded.
3. A short manual re-check of the validation messages and the PIN choice on a phone and a laptop.
