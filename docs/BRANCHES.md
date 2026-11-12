# Branches, and what's next (13 Nov 2026)

**field-ready** is now the one branch with everything: k1-owner (KPI 1) and k2-k3-filing-dashboard
(KPI 2 and 3) merged, and KPI 4, 5 and 6 built on top. Work from field-ready from now on; it goes
to **main** in one pull request. What changed and when: [CHANGELOG.md](../CHANGELOG.md).

## The branches

| Branch | What it holds | What to do with it |
|---|---|---|
| **field-ready** | All six milestones: registration to the approved agreement, the filings after it, the dashboard, the problem cases and security, the live-run measures, Solara.exe and upkeep | **Cut your branch from here.** Pull request into field-ready, then field-ready into main. |
| **main** | The base: pinned versions, migrations, health check, lint, the PR process | Changes only through pull requests. |
| k1-owner, k2-k3-filing-dashboard | KPI 1, and KPI 2 and 3, before the merge | Frozen. Don't build on them. |
| k1-ui, k1-audit, k1-rpx, feature/k1-completion-v2, feature/complete-k2 | Earlier work, all inside field-ready | Nothing. |

## The six milestones

| | Milestone | Proven by | In the sandbox | On the real portal |
|---|---|---|---|---|
| K1 | Documents to the customer's approved agreement | milestone1, k1_complete, k1_audit, real_labels | green | look-only trial to do ([K1_FIRST_REAL_TRIAL.md](K1_FIRST_REAL_TRIAL.md)) |
| K2 | Post-installation paperwork the same day | closeout, milestone2 | green | with the owner, on a real installation |
| K3 | One screen: every customer's stage and today's list | milestone3 | green | 10 live customers |
| K4 | The eight problem cases, staff logins, a backup restored | milestone4 | green | the 30-minute demo with the owner |
| K5 | Two weeks live, owner's time measured | Reports → the six milestones | measures built | [K5_LIVE_RUN.md](K5_LIVE_RUN.md) |
| K6 | Runs and looks after itself (exe, backups, retention, export) | live_mode, longevity, milestone4 | green | install on the owner's computer ([RUNNING.md](RUNNING.md)) |

K6 is our name for what follows the handover: running Solara on the owner's computer, backups,
security and the client's data ([SECURITY_AND_DATA.md](SECURITY_AND_DATA.md)). It has no
payment milestone in the plan; the monthly service covers it.

## Testing by hand (sandbox)

1. `SOLARA_DATA=<a folder> python -m uvicorn app.main:app --port 8900`, open
   <http://127.0.0.1:8900>, sign in as `r.deshmukh` / `demo`.
2. Today → **Connect the Chrome helper**; `chrome://extensions` → Developer mode → Load unpacked →
   `extension/`; paste the address and key into the co-pilot's Options.
3. Walk [HANDOVER.md](HANDOVER.md) §5 (KPI 1), then Installation and Close-out for one customer
   (KPI 2), Today and the board (KPI 3), and the problem cases in [USER_GUIDE.md](USER_GUIDE.md).
4. `python tests/run_all.py` with the same `SOLARA_DATA`: all 13 suites green before a push.

## Real portals

Look only, in your own Chrome: the portal refuses scripted browsers, so no test can reach it. On
each page press "Send this page's layout to Solara". Then turn each layout into a page in
`tests/real_labels.py` (made-up values only), fix `RULES` in `extension/panel.js` until it passes.
Gaps found in the public manuals (13 Nov) and not yet seen live: the plant photo "PDF only,
500 kB" box, the DCR-number search that fills the module rows itself, the MSEDCL upload #1 bundle
(WCR + islanding + guarantee + self-attested Aadhaar) and Proforma-A, the FQI defect module.

## Still to do

- [ ] Real-portal look-only trial; the 3 KPI-1 runs with the owner.
- [ ] G6, G7: the quotation and agreement in the client's own format (waiting for his files).
- [ ] MSEDCL upload #1: does MSEDCL want the self-attested Aadhaar copy? A decision for the owner.
- [ ] G9 field-team list, G11 feasibility letter, G10 Bank of Maharashtra loan pages.
- [ ] Hosted install or Solara.exe on the owner's computer, `SOLARA_PUBLIC_URL` set.
- [ ] One pull request field-ready → main.

## Rules

- Work on your own branch, cut from field-ready; open a pull request. Never push to main directly.
- Tests need `SOLARA_DATA` set to the running server's data folder.
- The repo is public: no client names, phone or consumer numbers, application numbers, prices, or
  the client's own files and recordings. Stage files by name; never `git add -A`.
- The co-pilot never types an OTP, CAPTCHA or password, never ticks a consent box and never
  presses Submit, Accept or Approve.
- Aadhaar never goes to an AI model.
