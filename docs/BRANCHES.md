# Branches, and what's next (9 Nov 2026)

Two branches carry all the live work: **k1-owner** (KPI 1: registering a customer up to the approved
agreement) and **k2-k3-filing-dashboard** (KPI 2 and 3: the filings after installation, and the
dashboard). They have not been merged with each other yet. That merge, **field-ready**, is the next
big step, then one pull request into **main**. What changed and when: [CHANGELOG.md](../CHANGELOG.md).

## The branches

| Branch | What it holds | State | What to do with it |
|---|---|---|---|
| **k1-owner** | KPI 1, from the customer's documents to the customer approving the agreement: reading documents, details, registration, vendor consent, e-sign, agreement upload, customer approval. The Chrome co-pilot for the vendor and customer logins; the owner's Today page. | Active | The KPI-1 field-test branch. Small fixes for the field test go here. |
| **k2-k3-filing-dashboard** | KPI 2 and 3: site feasibility report, loan, field photos and serials, DCR, 5-step installation, receipts; the stage board on the portal's ten stages, controls, monthly report. Already has two lessons from feature/complete-k2. | Active | KPI 2 and 3 work. The status-word fix (G2 below) goes here. |
| **field-ready** | The merge of the two above. Started locally, not pushed yet. | Merge in progress | Don't start a second merge of these two; wait until it is pushed. |
| **main** | The base: pinned versions, schema migrations, health check, lint, the PR process. | Base | Changes only through pull requests. |
| k1-ui, k1-audit, k1-rpx, feature/k1-completion-v2 | Earlier KPI-1 work: registration screen, KPI-1 audit, validation rules, K1 completion. | Merged into k1-owner | Nothing; don't build on them. |
| feature/complete-k2 | The first K2 build: filing tracker, serial registry, field-team upload, Jan Samarth sandbox, receipts. | Replaced by k2-k3 | Don't continue it. Anything missing from k2-k3: port it there as a small commit. |

## KPI 1: how to test it by hand

The KPI: 3 real new customers, each in under 5 minutes of the owner's time (OTP waits not counted);
nothing typed except OTPs, CAPTCHA and flagged fields; agreement e-signed and uploaded through Solara.

1. **Sandbox, 3 runs, each logged** (date, steps passed, anything odd, screenshots of anything odd).
   - `SOLARA_DATA=<a folder> python -m uvicorn app.main:app --port 8900`, open
     <http://127.0.0.1:8900>, sign in as `r.deshmukh` / `demo`.
   - Today → **Connect the Chrome helper**; `chrome://extensions` → Developer mode → Load unpacked →
     `extension/`; paste the address and key into the co-pilot's Options.
   - Walk the manual script in [HANDOVER.md](HANDOVER.md) §5 (now 15 steps, ending with the customer's
     approval). Also try **Open vendor + customer logins side by side** on Today: mark the upload in one
     window, and the other window's panel shows it.
   - `python tests/run_all.py` with the same `SOLARA_DATA`: every suite green before a push.
2. **First real-portal trial**, once, before the owner's session:
   [K1_FIRST_REAL_TRIAL.md](K1_FIRST_REAL_TRIAL.md). Look only. On each page press "Send this page's
   layout to Solara". Besides the vendor pages, capture the customer login's My Applications (the
   10-stage tracker), Subsidy Bank Details and the agreement approval dialog.
3. **After the trial:** turn each layout into a page in `tests/real_labels.py` with made-up values only;
   fix `RULES` in `extension/panel.js` until it passes; add new status words to `app/registration.py`
   with a test; delete the trial data folder.

## What needs to be done

G numbers are the gaps in [PRE_INSTALLATION_FIELDS.md](PRE_INSTALLATION_FIELDS.md) (the 7 Nov
walkthrough, step by step).

**Now**
- [ ] Read PRE_INSTALLATION_FIELDS.md, especially §6 (what is done).
- [ ] G2, on k2-k3-filing-dashboard: `tracker.parse()` reads "Subsidy Disbursal (Disbursed)" and
  "Subsidy Request (Redeemed)" as pending (`disbursed$` fails on the closing bracket). "Not Redeemed"
  stays pending, "Return" is rejected. Test every wording seen: Upload Agreement (Pending), Installation
  (Pending / In Progress), Inspection (Pending), Subsidy Request (Not Redeemed / Redeemed / Return),
  Subsidy Disbursal (Pending / Disbursed).
- [ ] The sandbox runs and the real-portal trial above.

**After field-ready is pushed**
- [ ] The merge: one Today page (both branches built their own `/api/today` and Today view); the field
  link uses `config_public_url` and `is_local` instead of `public_base`; the co-pilot keeps both
  branches' features; all 12 suites green; one PR into main.
- [ ] G9: a list of field-team members (name and mobile) to pick on the site feasibility report.
- [ ] G11: save the feasibility letter in the customer's file; read the approved kWp and date.

**For KPI 1 to be shown**
- [ ] G6 and G7: the quotation and the agreement in the client's own format (waiting for his files;
  they never go in the repo).
- [ ] Package the extension (zip + a one-page install guide) so the owner installs it alone.
- [ ] Hosted install: `SOLARA_MODE=live`, HTTPS, its own `SOLARA_DATA`, daily backup
  ([OPERATIONS.md](OPERATIONS.md)).
- [ ] The 3 KPI runs with the owner on real customers, a stopwatch per customer, logged.

**Later:** G10, the Bank of Maharashtra loan pages, after they have been seen live.

## Rules

- Work on your own branch, cut from the branch the change belongs to; open a pull request. Never push
  to main, k1-owner or k2-k3-filing-dashboard directly.
- Tests need `SOLARA_DATA` set to the running server's data folder; without it 7 suites fail for no
  real reason.
- The repo is public: no client names, phone or consumer numbers, application numbers, prices, or the
  client's own files and recordings. Stage files by name; never `git add -A`.
- The co-pilot never types an OTP, CAPTCHA or password, never ticks a consent box and never presses
  Submit, Accept or Approve. Real portals are only looked at during development.
- Aadhaar goes to an AI model only when the owner turns AI on (Gemini); the full number is stored only encrypted.
