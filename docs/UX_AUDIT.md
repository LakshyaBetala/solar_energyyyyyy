# UI/UX audit: the customer link, and how much the owner has to learn

7 Nov 2026, branch `k1-owner`. The customer page was checked on a phone (390×844) and the dashboard on a laptop (1366×768), in light and dark.

## 1. The customer's document link

The link is sent on WhatsApp. On their own phone, the customer photographs the bill and the Aadhaar and types their email.

| # | Problem found | Who it hurts | Fixed |
|---|---|---|---|
| C1 | **The link did not open on the customer's phone.** It was built from the address the owner's browser used, which is `http://127.0.0.1:8900/…` when Solara runs on the laptop. The e-sign link had the same problem. | Every customer: blocker | Links now use `SOLARA_PUBLIC_URL`, Solara's internet address. When a link would only open on this computer or this office network, the dashboard says so before the owner sends it. Tested (k1_audit L1) |
| C2 | No overall state: after everything was sent, the page still showed four upload boxes, and the customer could not tell they were finished | Customer | The top of the page says "Still needed: …" or "All done. Thank you. You can close this page" (with Marathi). Tested (L2) |
| C3 | "Send it again" was as big as the first upload, inviting accidental re-sends | Customer, owner | A received item shows "✓ Received" and a small "Send a different photo" link |
| C4 | The optional passbook and roof photo looked as important as the required items | Customer | They are grouped under "Optional, if you have them now" |
| C5 | The email, which the portal needs, was last and below the fold | Customer | The bill, Aadhaar and email come first; all three fit on the first screen |
| C6 | Nothing happened on screen while a photo uploaded; on mobile data a 5 MB photo takes many seconds, so people tap again or leave | Customer | "Sending… keep this page open" appears and the other buttons wait |
| C7 | Phone photos are 3–8 MB, slow to send on mobile data | Customer | Photos over 3 MB are shrunk on the phone to 3000 px before sending; PDFs are never touched; the original is sent if anything fails |
| C8 | No way to ask for help | Customer | "Questions? Call your installer: …" appears when `SOLARA_VENDOR_PHONE` is set |
| C9 | After an update, browsers kept running the old dashboard script | Owner | Dashboard files are sent with `Cache-Control: no-cache`. The browser asks each time and gets a quick "unchanged" when nothing changed. Tested (L3) |

**Still to check, with the client:**
- The page on 2–3 real phones (Android with WhatsApp's built-in browser, and Chrome), including a real Aadhaar photo after shrinking: does the QR still read?
- A native Marathi speaker should read the Marathi lines.

Screens: [link, nothing sent yet](k1-audit/ux/link-start.png) · [link, all done](k1-audit/ux/link-done.png) · [owner's warning when the link is local only](k1-audit/ux/local-warning.png)

## 2. How to make the links work

Customers open two links on their own phones: the document link, and the signing link. **Both only work if Solara can be reached from the internet.** There are three ways to run Solara:

| Option | Customer links | What it takes | Verdict |
|---|---|---|---|
| **A. Hosted** on a small server in India with its own web address (https) | Work anywhere | A server and a domain. Set `SOLARA_PUBLIC_URL=https://…` in `.env`. The owner opens the dashboard at that address, and the co-pilot's options point to it | **Recommended**: matches the plan's "hosted in India, own address" |
| B. On the owner's laptop, plus a secure tunnel that publishes only the customer pages (`/up/…` and `/sign/…`) | Work while the laptop is on | A tunnel service; the laptop must stay on and online | Stop-gap only |
| C. On the owner's laptop only | **Do not work** for customers. The owner must collect documents personally, and signing works only on the owner's own phone on the same Wi-Fi | Nothing | Not enough for KPI 1 |

**What keeps a hosted Solara safe:**
- The dashboard needs a login, and each person has their own role.
- A customer link opens only one customer's page. It is a long random code, lasts 7 days, takes at most 30 files, and stops after 5 wrong tries on the signing check.
- Documents are encrypted on disk, and only the last 4 digits of the Aadhaar are kept.
- Use https only.

## 3. The dashboard: what is too much to learn

### What the owner faces today

- **Screens:** 9 in the demo, 5 in live mode (Pipeline, Registration, Close-out, Audit Trail, Reports). The four demo screens (Agent Runs, Document Intake, Number Pool, AI Calling) are already hidden in live mode.
- **Two customer lists.** A customer appears in Registration until the agreement is uploaded, then in Close-out after installation. Each list has its own 5- or 6-box step strip, so the owner has to know which screen a customer is in.
- **Pipeline** opens with four big-number tiles (one counts robot runs, which are demo-only), a stage bar chart and "Needs attention". Only "Needs attention" helps the owner act.
- **Close-out** is still in the old style: four tiles, a step strip, a seven-row document table and **34 inputs on one screen**. Labels are in small capitals, and the text is 13.5 px.
- **Words the owner does not need:** "Agent worker online", "Model off", "Connect co-pilot", "WCR", "Annexure-I", "MSEDCL 79435901". The top bar's status chips mean nothing to the owner.
- **Registration was redesigned this week** (one next step, 15 px text, finished sections folded). It is the model for the rest.

### The simple version: three places

| Place | What it shows | Replaces |
|---|---|---|
| **Today** | One list across all customers, oldest first, each line one action with one button: "Call Priya for the OTP", "Send Sunita the signing link", "Upload Anil's agreement", "Approve Ravi in Vendor Consent" | Pipeline's tiles, charts and "Needs attention" |
| **Customers** | One list. Each customer opens one page: a progress line of all 16 steps (order to subsidy), the one next step, then only the section that step needs | The separate Registration and Close-out screens |
| **Reports** | The monthly Excel and the stage counts; the audit trail below it, for supervisors | Reports and Audit Trail |

Also:
- Hide the top-bar status chips in live mode.
- Rename what remains in the owner's words: "Co-pilot key" becomes "Connect Chrome helper"; "WCR" becomes "Work completion report".

**What the owner has to learn then: open Today, do the top line, repeat.** A 15-minute walk-through is enough, and the team can be trained in the same session.

| | Now (live mode) | Simple version |
|---|---|---|
| Screens to learn | 5 | 3 |
| Customer lists | 2 | 1 |
| Step bars | 2 different (5 and 6 boxes) | 1 (16 steps, finished ones folded) |
| Inputs visible at once on close-out | 34 | Only those the next step needs |

### Order of work

1. **Now (done on this branch):** the customer link (C1–C9).
2. **Next:**
   - Bring over the **Today** list already built for KPI 3 on `k2-k3-filing-dashboard`, and open live mode on it.
   - Merge Registration and Close-out into one **Customers** page with the Registration screen's pattern.
   - Hide the top-bar chips in live mode.
3. **Then:** plain words for the remaining jargon; test on real phones; Marathi review.

**Needs the client:**
- Where Solara runs (section 2), which decides whether the customer links work at all.
- The installer's phone number for the customer page.

## 4. Done after the audit (same day)

Rohit asked for it much simpler. These are built and tested (the `ui` suite was rewritten for the simple UI: 26 checks):

| Change | What Rohit sees |
|---|---|
| **The menu has five places for everyone:** Today, Registration, Close-out, Audit Trail, Reports | No AI Calling, Number Pool, Agent Runs, Document Intake or Pipeline. Their code is still in the repo; nothing links to it |
| **Today is the home page,** and every sign-in starts there | One list of everything to do: *Calls to make*, *To do in Solara*, *On the government website*, *Waiting for the customer*. One line, one button; only the top line has the filled button ("do the top line first"); the menu badge counts the lines |
| **OTP calls are built in** | The call line and the Register step show the customer's number to tap, and a ready WhatsApp message: "two codes are coming, keep your phone near". Rohit taps Send; Solara sends nothing by itself |
| **The customer's page asks one thing at a time** | "Step 1 of 3: Electricity bill", one big button; then the Aadhaar; then the email. The optional items are folded away. At the end: "All done. Thank you" |
| **The installer's phone number on the customer page** | "Need help? Call your installer". Set by `SOLARA_VENDOR_PHONE`; the demo shows a placeholder |
| **No technical chips in the top bar** | Only who is signed in |
| **The demo reset restores the demo exactly** | A correction made during a rehearsal is dropped, and that customer's documents are read again |

Screens: [Today](k1-audit/ux/today.png) · [Register step with the OTP call](k1-audit/ux/register-call.png) · [customer page, step 1 of 3](k1-audit/ux/link-step1.png)

**Still to do from section 3:**
- Merge Registration and Close-out into one Customers page.
- Plainer words on Close-out.
- Test on real phones.
