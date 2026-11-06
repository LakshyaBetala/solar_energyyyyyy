# KPI 1 test report

**Branch:** `feature/k1-completion-v2` · **Date:** 2026-11-05 · **Environment:** sandbox portals, synthetic data, Chromium with the co-pilot extension

**KPI:** 3 new customers registered, accepted in the vendor login and the e-signed agreement uploaded, each in ≤ 5 min of the owner's time; nothing typed except OTP, CAPTCHA and flagged fields.

## 1. Verdict: NOT READY FOR SIGN-OFF
| KPI clause | Result |
|---|---|
| 3 customers registered, accepted, agreement e-signed and uploaded | **Pass** (sandbox): all 3 reached 6/6 through the real UI |
| Each ≤ 5 min of owner time | **Not proven**: estimated about 2.5 min from about 28 owner actions (crude model); needs a real stopwatch session |
| Nothing typed except OTP, CAPTCHA, flagged fields | **Fail as worded**: the owner also typed kW, installation cost and roof area, and picked the module type |
| Documents read automatically, doubts flagged | **Pass** |
| Real PM Surya Ghar portal | **Not tested** |

## 2. What was run
| Test | Result |
|---|---|
| Repo suites (`tests/run_all.py`) | 312 checks, all pass |
| 3 customers through the browser UI and co-pilot, owner actions and typed fields logged | 3 of 3 reached 6/6 |
| Independent API adversarial test | 228 checks, 198 pass, 30 fail (defects in §3) |
| Phone-size e-sign page | layout OK; wrong digits show an error; thin signature blocked |

## 3. Defects (priority order)
| # | Severity | Defect |
|---|---|---|
| 1 | High | Parallel customer creation fails: 2 of 12 simultaneous creates gave a 500 error |
| 2 | High | A garbage consumer number (`abc`) erases the saved one |
| 3 | High | Cost `-250000` is saved as `250000` on the agreement |
| 4 | High | A registered customer's application number is silently replaced by re-registering |
| 5 | High | Steps can be skipped: registered, accepted and an e-sign link were created with no documents or details |
| 6 | High | A new blank portal form pre-selects the previous customer (risk of filing the wrong person) |
| 7 | High (KPI wording) | Owner types kW and cost every time; the co-pilot leaves roof area, module type and bank account to the owner |
| 8 | Medium | A PIN conflict is resolved by one confirm click that doesn't say which value is accepted (the Aadhaar PIN went to the portal) |
| 9 | Medium | Letters in the mobile are accepted as "no mobile"; names have no length limit; `123` is accepted as a name |
| 10 | Medium | Wrong-typed input gives 500 on login, name, mobile, kW, consumer number, email, cost and application number; a garbage signature to the sign page also gives 500 |
| 11 | Low | The `?error=` text on the public sign page is shown as given, so a crafted link can show a customer any message |
| 12 | Low | Co-pilot summary says only "Filled 4", not which fields; one console 404 not identified |

## 4. What works
- Consumer number, address and PIN were read correctly in all 3 runs. Aadhaar is read offline and only the last four digits kept.
- The co-pilot never touched OTP or CAPTCHA and never pressed Submit.
- The application number was saved from the portal page without typing.
- E-sign: wrong digits error, a changed document is refused, and editing the cost after signing invalidates the agreement.
- The duplicate-customer warning works, ignoring case and spacing.
- The agreement PDF reached the portal with the cost, under 2 MB.

## 5. Per-customer results
| | Priya | Rahul | Sunita (PIN differs) |
|---|---|---|---|
| 6/6 steps | yes | yes | yes |
| Documents to accepted (system timer) | 13 s | 16 s | 17 s |
| Estimated human time | about 144 s | about 145 s | about 146 s |
| Flags confirmed by owner | 1 | 1 | 2 |

The estimate is 2 s per click, 8 s per upload, 0.35 s per character plus 3 s per field, and 20 s of reading. Waiting for the OTP and the customer's e-sign is excluded.

## 6. Not covered
Real PM Surya Ghar pages and dropdowns; a real stopwatch with the owner; real bills and Aadhaar photos; a drawn signature on a real phone; two operators working at once.

## 7. Before sign-off
1. Agree the "typed by hand" rule with the client, or pre-fill kW and cost.
2. Fix defects 1–6.
3. Run a real session with the owner on the live portal, with a stopwatch.

Evidence: screenshots in `docs/k1-evidence/`.
