# Where Solara goes from here

For the team and the client. What exists today is in [BRANCHES.md](BRANCHES.md) and [USER_GUIDE.md](USER_GUIDE.md);
this is what comes after, in the order it pays off. Nothing here is promised to the client until it is agreed.

## What stays true whatever is added

- A person types every OTP, CAPTCHA, password and Aadhaar number. The panel never works around a portal's
  bot checks, and it presses a portal's button only where the owner switched that on.
- The installer owns the data and can export all of it at any time.
- Every action is in the audit trail. Nothing is filed twice.
- Nothing about a client (name, prices, templates, customers) is in the code or the repository.

## 1. Before the first paying month (weeks)

| What | Why | Size |
|---|---|---|
| Three measured runs with the owner on the live portals (KPI 5) | Everything so far is proven on the sandbox and on pages captured from the live site, not end to end live | 3 sittings |
| Rules from the layouts the panel sends back | Each live page the panel does not fully know sends its field names (never values) to Solara; one pass turns them into rules | S, repeated |
| Publish the Chrome helper as an unlisted Chrome Web Store item | "Load unpacked" stops working when Chrome updates its rules, and cannot update itself | S |
| Quotation as a PDF without Microsoft Word | Today a Word template needs Word or LibreOffice on the computer. Ship LibreOffice with the desktop app, or accept a ready PDF per price | M |
| Bank of Maharashtra loan pages | Seen only by description. Model them after one sitting with a loan customer | M |
| MSEDCL first upload bundle, Proforma-A, the inspection (FQI) defect list | The owner's decision on the formats is still open | M |

## 2. One installer, running for years (months 2 to 4)

- **Portal packs.** The field rules move out of the extension's code into a file Solara serves ("PM Surya Ghar
  consumer", "Jan Samarth", "MSEDCL"). A portal change is then fixed in Solara in an hour, with no new extension,
  and what the owner teaches in the panel can be promoted into the pack.
- **Drift alarm.** Solara already notices when a portal's layout changes. Next: say which fields moved and hold
  auto-fill on that page until someone looks.
- **WhatsApp Business API** for the document link, OTP warnings and status updates, in place of opening WhatsApp by hand.
- **After the subsidy:** the 5-year maintenance register (visits, complaints, warranty cards), and reminders.
- **Money:** quotation to invoice with GST, payments received against the agreement's schedule, a monthly statement.
- **Stock:** DCR modules by serial from dealer invoice to installation, so "waiting for the dealer" is known before the site visit.
- **Offsite backup** to the client's own cloud drive, encrypted, with the restore drill run against it monthly.

## 3. More than one installer (months 4 to 9)

- **Hosted Solara**, one database and one encryption key per installer, with their own sign-in and their own price list
  and templates (already data, not code).
- **Other states and DISCOMs.** Each is a portal pack plus that DISCOM's close-out documents. The national portal
  part is the same everywhere.
- **Other schemes on Jan Samarth and the state portals** that the same customers apply for.
- **A phone app for the field team** in place of the field link: offline photos, serial scan, checklist.
- **Numbers the owner can act on:** days per stage against the portal's average, rejections by reason, cash locked
  in applications waiting for subsidy.

## Risks to settle early

| Risk | What to do |
|---|---|
| The Aadhaar card and the customer's address leave the computer (AI reading, map lookup) | Off by default. Decide with the client in writing, with advice on the Aadhaar Act and the DPDP Act before switching either on |
| A portal bans automated help | The panel only fills what the logged-in owner would type and never touches OTP or CAPTCHA. Keep it that way; read each portal's terms |
| One computer holds everything | Daily backup, a second copy, the key kept apart, the restore drill. Offsite backup next |
| Source code and IP | Not decided. For Almmatix and the client to agree in writing |
