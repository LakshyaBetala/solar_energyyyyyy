# K5: the two-week live run, and handover

For the team running K5 with the owner. **KPI:** 10 real customers from order to MSEDCL through
Solara · 0 wrong submissions caused by Solara · average owner's time 15 minutes or less per
application · staff trained, written guide handed over.

## Before day 1

- [ ] Solara.exe on the owner's computer, `SOLARA_MODE=live`, `SOLARA_PUBLIC_URL` set (customer links
      must open on a phone), `SOLARA_BACKUP_COPY` set to a second disk ([RUNNING.md](RUNNING.md)).
- [ ] `vault.key` copied to a USB stick kept elsewhere; Reports → **Restore drill** passes.
- [ ] People added with their own passwords (Reports → People). Nobody shares a login.
- [ ] Chrome panel connected on the owner's Chrome; the client's agreement and quotation formats in.
- [ ] `python tests/run_all.py` green on the build being installed.

## Every day

1. The owner works from **Today** only. We sit beside, never at the keyboard.
2. Anything the panel left for him to type, or anything odd: note the customer, the page, what
   happened. Fix within a day on a branch, with a test, run the suites, install the new build.
3. Look at Reports → **Health**: last backup under a day old, no portal changes flagged.

## How the KPI is proven

Reports → **The six milestones, measured** and **Owner's time per customer** are worked out from
what Solara records (each action's time; waits for OTPs, customers and the field team are left
out). At the end of the two weeks, export the monthly workbook and Export everything; together
they are the evidence. A "wrong submission caused by Solara" is any step re-filed with **Retry**
where the cause was Solara's value; the reason typed with Retry says which.

## Training (two sessions, about an hour each)

| Session | Who | Covers |
|---|---|---|
| Solara | owner and office staff | Today, a new customer end to end, Installation, Close-out, Pause/Retry, Reports, People, backups and the restore drill |
| The portals | owner | the panel on each portal, the side-by-side logins, the problem cases (wrong OTP, logged out, internet off, dealer stock) |

Hand over: [USER_GUIDE.md](USER_GUIDE.md) printed, the users list, the backup folder and where
`vault.key` is kept, [SECURITY_AND_DATA.md](SECURITY_AND_DATA.md).
