# Solara — Phase 1 project plan

**For:** our team (Lakshya, Mouriyan, the project manager)
**Client:** a rooftop-solar installer in Pune, Maharashtra. The name is kept out because this repo
is public; the named client copy lives in `internal/`, which git ignores.
**Date:** 28 October 2026
**Prices here are what the client pays. Our own costs are never written here.**

---

## 1. The short version

- **What the client wants:** "enter once, use everywhere". The owner does all the portal work alone,
  at about **1 hour per application**: register the customer, call for OTPs, type the same details
  into four portals, copy data into Excel macros, print, get signatures, scan, shrink and upload.
  Their targets: **pre-registration done in 5 minutes** once they have the documents, and
  **post-installation paperwork done in 5 minutes**, closed the same day.
- **Feasible? Yes**, as a **co-pilot in the owner's own Chrome**, not a robot on our server.
  The PM Surya Ghar portal returned **HTTP 403 to an automated browser**, and every login needs a
  CAPTCHA plus an OTP to the owner's phone. So: the owner logs in, Solara fills the forms and attaches
  the files, **the owner presses every Submit**. We never try to get past a portal's security.
- **Price to the client:** **₹1,35,000** build in five phases, each paid on a KPI, plus **₹6,000 a
  month** all-inclusive AMC (hosting, AI, backups, e-sign, portal updates, support).
- **The five phases are the meeting's five modules**, and the milestones are the client's own words.
  Phase 1 is "registration, vendor selection, accepted in vendor login, agreement uploaded"
  (31:24, 22:39). Phase 2 is post-installation closed same day plus at least applying on Jan Samarth
  (34:19, 36:12). Section 6 has the details.
- **Already built and tested:** post-installation close-out. That covers customer e-sign (sign once,
  reused only with consent), all six MSEDCL documents under 300 KB, and the Chrome co-pilot attaching
  them on the MSEDCL page in one click. **59 checks pass.**

---

## 2. What we have done so far

| Work | Result |
|---|---|
| Went through the 47-minute call recording (transcribed) and the meeting notes | requirements, the client's volumes and their targets captured with timestamps |
| Reviewed every portal screen shown on the call (137 distinct screens) | field lists, file limits, OTP and CAPTCHA points for each portal |
| Probed the public login pages of all four portals | PM Surya Ghar blocks automated browsers (403); Jan Samarth runs Imperva bot protection; MSEDCL login is plain user ID + password |
| Independent second review of the same material | agreed on the verdict; was stricter on consumer acceptances and Jan Samarth; both points adopted |
| Proved the co-pilot mechanism on our sandbox | typed every field incl. dropdowns, attached files the server received, stopped at every Submit (6/6) |
| **Built ahead of schedule**: e-sign (Phase 1's agreement), the reports and six-file MSEDCL pack, the MSEDCL co-pilot (Phase 2), plus a sandbox MSEDCL portal | `tests/closeout.py`: 59 checks pass; existing 61 + 38 still pass |

What the client said, for reference (recording timestamps):
"It takes an hour for me to process one application" (25:45). "Currently I manage myself" (16:36).
4–5 applications a day, practically 3–4 (26:22). 1–2 installations a day (27:52). "Registered in
five minutes… post-installation in five minutes" (34:06–34:37). First milestone they asked for:
registration + vendor selection + vendor acceptance (31:24). Jan Samarth must be in the milestones
(34:54). Nothing on the live portal can be undone (38:04–38:54).

---

## 3. Feasibility

### 3.1 The four portals

| Portal | Work done there | Login | Verdict |
|---|---|---|---|
| **PM Surya Ghar** | customer registration and application, vendor consent, agreement upload (JPG/PDF ≤ 2 MB), site feasibility report, 5-step installation, status | Vendor: email + password + maths CAPTCHA + OTP to owner's phone (15 min). Customer: mobile + OTP; one mobile per customer | **Co-pilot.** Blocks scripted browsers |
| **NISE DCR** | B2C certificate: application no., customer, invoice, panel serials (typed or Excel) | own login, 45-min session | **Co-pilot.** Fails until the dealer transfers the panels |
| **MSEDCL rooftop** | six documents per customer, **PDF only, 300 KB each**, all mandatory; list shows uploads pending up to 230 days | user ID + password, no CAPTCHA | **Easiest. Built.** |
| **Jan Samarth** | loan: 9–10 steps, Aadhaar OTP, bank and branch; opens only after the feasibility report (35:07) | customer mobile + Aadhaar OTP; Imperva | **Co-pilot fills the basic details**; the customer enters their own Aadhaar OTP and picks bank and branch |

### 3.2 Who does what

| Solara | Owner (seconds each) | Customer |
|---|---|---|
| reads documents into one record, flags mismatches | logs in (CAPTCHA + OTP) | reads out OTPs on the call |
| fills forms, attaches files | checks the form | e-signs once, then taps Approve |
| generates every document, signed, ≤ 300 KB | presses Submit / Upload | accepts agreement and installation on own phone |
| tracks status, builds the call list | calls when Solara says an OTP is due | Aadhaar OTP and bank choice on Jan Samarth |

### 3.3 Not doing, and why (put these in the contract as exclusions)

- **Unattended robots on the government portals.** They are blocked, and getting around that risks
  the client's vendor account.
- **Pressing the customer's accept buttons.** That is the customer's consent under the scheme.
- **Typing the customer's Aadhaar OTP into a loan application.** It is credit in their name, paid
  out to the vendor.
- **Making a pasted signature look scanned.** That would be a false document on a subsidy claim.
  Our e-sign is open and consent-based.
- **Virtual numbers for customers.** One mobile per customer is the portal rule, and the customer
  must get the scheme's messages. The client dropped virtual numbers on cost anyway.

### 3.4 What can break, and the fix

| Risk | Fix |
|---|---|
| Portal changes its screens | one field map per portal; fixed under AMC in 1–2 working days; Copy buttons as fallback |
| Wrong data on a live form (can't be undone) | checks before filling (bill vs Aadhaar name, kW vs sanctioned load, serial count, sizes); owner presses Submit |
| Customer doesn't answer for the OTP | call list on the dashboard; OTP steps done live on the call |
| File too large or wrong type | converted to PDF and shrunk under 300 KB automatically |
| Dealer hasn't transferred panels | "waiting for dealer"; nothing to file until then |
| Wrong or repeated serial | refuses a serial already used on another customer; photo beside each serial |
| Photo without GPS | refused with the reason; the field upload page captures GPS |
| Network drop mid-way | every step saved; portal status checked before re-filling, so nothing is filed twice |
| Session timeouts | co-pilot resumes where the owner left off |

### 3.5 Open questions for the client

1. Does MSEDCL accept **e-signed** PDFs? Does the net-metering agreement need **stamp paper**?
2. Their **Excel workbook with macros** and **Word templates**. Our templates are rebuilt from the
   recording and print a "draft format" footer until swapped.
3. Real monthly volume of new applications. The vendor account showed 61 applications in total.
4. The scheme banner reads **"closes on 31 March 2027"**. The PM Surya Ghar parts live until then
   unless the scheme is extended; close-out and MSEDCL keep working for net-metering jobs.

---

## 4. The process, end to end

### 4.1 Pre-installation

| # | Step | Owner | Solara | Customer |
|---|---|---|---|---|
| 1 | Order + documents arrive | uploads them | reads bill, Aadhaar, bank, roof photo into one record; flags mismatches | sends documents |
| 2 | Customer registration (PM Surya Ghar, consumer login) | enters mobile + CAPTCHA, calls for OTP, types it, checks, Submit | fills the application (state, DISCOM, consumer no., name, kW, category) | reads out the OTP |
| 3 | Select vendor | one click | — | — |
| 4 | Vendor consent (vendor login, once a day) | approves | — | — |
| 5 | Agreement | Submit | generates it; sends the e-sign link; fills total cost; attaches the signed PDF | signs on phone |
| 6 | Site feasibility report (after site visit) | checks, Submit | fills roof, shade, area, permissible kW, visitor, quotation, pre-install photo | — |
| 7 | Customer accepts agreement | — | sends a 3-line how-to; shows "waiting for customer" | accepts on own phone |
| 8 | Bank loan on Jan Samarth (if any) | opens it with the customer | fills basic details and address; saves the in-principle approval PDF; tracks the loan | enters own Aadhaar OTP, picks bank and branch |
| 9 | DISCOM feasibility | — | shows it on the dashboard | — |

### 4.2 Post-installation

| # | Step | Owner | Solara | Customer / field team |
|---|---|---|---|---|
| 10 | Field upload | confirms each serial against its photo | reads serials from label photos; checks count and repeats; reads GPS | field team uploads photos from site |
| 11 | DCR certificate (NISE) | Submit | fills application no., customer, invoice, serials | — |
| 12 | Submit installation (PM Surya Ghar, 5 screens) | checks each, Save & Next, Final Submit | fills location (photo GPS), inverter, modules, DCR cert no., photos, checklist | — |
| 13 | Customer accepts installation | — | tracks it | accepts on own phone |
| 14 | Close-out pack | sends approval link | makes 6 MSEDCL documents ≤ 300 KB with signatures | taps Approve (saved signature reused) |
| 15 | MSEDCL upload | logs in, Attach, checks, Upload | co-pilot attaches all six in one click; marks done | — |
| 16 | Inspection, commissioning, subsidy | — | tracked on the dashboard | — |

---

## 5. The 5-minute targets

The client asked for **5 minutes pre** and **5 minutes post**. Here is the owner's **hands-on time**
step by step once Solara is complete. Waiting on the customer (OTP, signing) is shown separately,
because that is what really sets the pace.

### 5.1 Pre-installation: registration in about 5 minutes

| Step | Owner's hands-on time |
|---|---|
| Check the record Solara read from the documents (only flagged fields) | 0:45 |
| Open consumer login, mobile, CAPTCHA | 0:20 |
| Call the customer, type the OTP | 1:00 (customer must answer) |
| Co-pilot fills the application; owner checks and submits | 0:45 |
| Select the vendor | 0:15 |
| Vendor consent (already logged in for the day) | 0:15 |
| Send the agreement e-sign link | 0:10 |
| **Registration done** | **≈ 3:30** |
| *Later:* agreement upload once signed + feasibility report after the visit | 1:30 |

**What makes it 5 minutes:** documents read automatically, one OTP call, every form pre-filled.
**What can stop it:** the customer not answering for the OTP, or a document mismatch that needs a
real correction. Solara flags these instead of guessing.

### 5.2 Post-installation: close-out in about 5 minutes

| Step | Owner's hands-on time |
|---|---|
| Confirm the serials Solara read from the field photos | 1:00 |
| DCR certificate: co-pilot fills, owner submits | 0:40 |
| Submit installation, 5 screens: co-pilot fills, owner checks and saves | 1:45 |
| Send the approval link (or the installer hands over the phone on site) | 0:10 |
| Generate the six documents | 0:10 |
| MSEDCL: log in, open customer, Attach, check, Upload | 1:00 |
| **Close-out done** | **≈ 5:00** |

**What makes it 5 minutes:** no Excel, no printing, no scanning, no shrinking files, one click to
attach six files.
**What makes it same-day:** the **installer gets the customer to tap Approve and accept the
installation on site at handover**. Otherwise it waits on the customer's phone. The dealer's panel
transfer must also be done before the DCR certificate.

---

## 6. The five phases, KPIs and payments (client prices)

**Phase N is the meeting's Module N**, in the meeting's order. The milestones are the ones the client
asked for, in their own words:

| What the client said | When | Where it lands |
|---|---|---|
| "First show me consumer registration and selection of vendor, and through vendor login it should accept… I will pay you till that part" | 31:24 | **Phase 1 milestone** (first payment) |
| "Getting the OTP, filling the form, submitting the application, selecting the vendor, uploading the vendor agreement" | 22:39 | **Phase 1 scope** |
| "Gives me documents, it should get registered in five minutes" (later "5–10 minutes") | 34:06–34:37 | **Phase 1 KPI** |
| "We need to first create these reports automated" (WCR, DCR declaration, net agreement for MSEDCL) | 17:56 | **Phase 2** |
| "Once my installation is done, all the post-installation process should get completed in say five minutes… close on the same day" | 34:19–34:25 | **Phase 2 KPI** |
| "At least applying to the Jan Samarth portal" kept in a milestone | 36:12 | **Phase 2 KPI** |
| Sign once on the phone; reuse the signature on the reports instead of print, sign, scan | 44:21–45:43 | Phase 1 (agreement) and Phase 2 (reports) |
| Everything on one dashboard | 33:31 | **Phase 3** |

Every phase ends in **one final milestone the client can see** and a **KPI they can check with a
stopwatch and a count**. A phase is paid only when its KPI is met on their real customers.

| Phase = module (meeting) | Final milestone the client sees | KPI (all must pass) | Time | Payment |
|---|---|---|---|---|
| **Start** | agreement signed, WhatsApp group, project manager named, sessions booked | — | — | ₹10,000 advance |
| **1. Documents → registration and agreement** (Module 1: document processing, data reuse) | a new customer goes from documents to **registered on PM Surya Ghar → the client selected as vendor → accepted in the vendor login → vendor agreement uploaded**, all filled by Solara | 3 real new customers · documents to "accepted in vendor login" in **≤ 5 min of owner's time each** (waiting for the customer's OTP not counted) · agreement e-signed by the customer and uploaded through Solara · nothing typed by hand except OTPs, CAPTCHA and fields Solara flagged | week 1 | ₹27,000 (20%, as agreed) |
| **2. Portal filing, reports, loan and tracking** (Module 2: portal automation, application tracking, Jan Samarth) | **all post-installation paperwork closed the same day**: DCR certificate, installation submitted, reports made and uploaded on MSEDCL; plus the feasibility report and the Jan Samarth application before installation | 3 real customers from "agreement uploaded" to "6 documents on MSEDCL" through Solara · **post-installation ≤ 5 min of owner's time each** (customer's e-sign not counted) · reports made automatically, **0 files rejected** for size or format · **Jan Samarth application submitted up to bank and branch for 2 loan customers**, basic details filled by Solara | weeks 2–3 | ₹35,000 |
| **3. Dashboard** (Module 3) | **one screen shows where every customer stands and what to do today** | 10 live customers: stage on screen matches the portal **10 out of 10** · today's list shows every pending OTP call, e-sign and upload · monthly Excel in one click | week 4 | ₹20,000 |
| **4. OTP, security and problem cases** (Module 4) | Solara **handles the common problems without filing anything twice or wrong** | live demo, **8 of 8 cases handled**: wrong OTP · OTP not received (resend) · portal session timeout · internet cut mid-form · file over 300 KB · repeated serial number · photo without GPS · dealer panels not yet transferred · plus separate staff logins and one backup restored | week 5 | ₹20,000 |
| **5. Live testing and handover** (Module 5) | **the client's team runs Solara on real customers for 2 weeks** | 10 real customers order → MSEDCL through Solara · **0 wrong submissions** caused by Solara · **average ≤ 15 min of owner's time per application** (vs about 1 hour today) · staff trained | weeks 5–6 | ₹23,000 |
| | | | **Total** | **₹1,35,000** (taxes extra, if applicable) |

### What each phase builds

**Phase 1 — Documents → registration and agreement.** The client's own first milestone:
1. The owner uploads the customer's documents. Solara reads the bill, Aadhaar, bank page and roof
   photo into one record and flags mismatches, such as the bill name differing from the Aadhaar name.
2. Solara prompts the OTP call to the customer.
3. The co-pilot fills the PM Surya Ghar customer registration and application, and the client is
   selected as vendor.
4. In the vendor login, the owner approves the customer in Vendor Consent.
5. Solara generates the vendor agreement. The customer e-signs it on their phone, and the co-pilot
   uploads it with the installation cost.

*Process:* a 1-hour live session on PM Surya Ghar with a real new customer (customer side and vendor
side) to map the pages, then 3 customers. The e-sign used here is already built.

**Phase 2 — Portal filing, reports, loan and tracking.** This phase covers:
- Site feasibility report.
- **Jan Samarth application** ("at least applying"). Solara fills the basic details and address. The
  customer enters their own Aadhaar OTP and chooses the bank and branch. The in-principle approval
  PDF is saved to the customer's file.
- Field-team upload page: GPS photos, plus serial labels that Solara reads.
- DCR certificate.
- The 5 installation screens.
- **Reports made automatically**, replacing the Excel macros: WCR, Annexure-I, DCR declaration and
  net agreement, signed with the customer's saved signature only after they tap Approve. Plus the
  datasheet and the GPS photo. All six are attached on MSEDCL in one click.
- Every filed step recorded (application tracking).

*Already built ahead of schedule:* the reports, the six-file MSEDCL pack and the MSEDCL co-pilot.
*Process:* their templates swapped in; live sessions on MSEDCL and DCR; one installation's photos;
two customers who need a loan.

**Phase 3 — Dashboard.** The screen shows:
- Every customer and their stage across the four portals.
- Today's list: OTP calls, pending e-signs, pending uploads, waiting-for-dealer.
- Loan status.
- Reports and Excel export.

**Phase 4 — OTP, security and problem cases.** This phase covers:
- The OTP call flow with resend.
- Separate staff logins and roles, encrypted documents, masked Aadhaar, daily backups.
- The eight problem cases listed in the KPI.

Module 4 was pitched as "anti-bot". It now means **working inside the owner's own browser, so the
portals have nothing to block**. It never means tricks to get around portal security, and we stop
promising "you'll never get blocked".

**Phase 5 — Live testing and handover.** Two weeks of supervised use on real customers, fixes as they
come up, then training and a short written guide.

### Meeting action items

| Action (from the notes) | Owner | Status |
|---|---|---|
| Inspect the 4 portals, confirm security and permissions | Lakshya, Mouriyan | done (section 3) |
| Feasibility study of the portal workflows | Lakshya, Mouriyan | done (section 3) |
| Prototype the phone-based digital signature | Lakshya | done: built and tested (section 9) |
| Include the Jan Samarth loan application in the milestones as a required part | Mouriyan | done: Phase 2 KPI |
| Send modules and milestone breakdown to the client | Mouriyan | client copy in `internal/`, ready to send |
| Share the contract with KPIs and payment terms | Mouriyan | to do, from the client copy |
| Create the WhatsApp group | Mouriyan | to do |
| Assign a project manager | Mouriyan | to do; name them in the contract |
| Register on PM Surya Ghar with our own number and pick the client as vendor (agreed homework) | Lakshya, Mouriyan | to do; use a real connection of ours and stop after vendor selection |

---

## 7. Pricing structure for the client

**Build: ₹1,35,000**, paid as in section 6. Agreed on the call: ₹10,000 to start, about 20% at the
first KPI, the rest per milestone.

**AMC: ₹6,000 a month, all-inclusive.** It starts the month Phase 1 goes live.

| Included | |
|---|---|
| Hosting | server in India, domain, SSL |
| AI | all document reading (bills, Aadhaar, passbooks, serial-number photos) |
| Backups | daily, encrypted, kept 30 days |
| E-sign | unlimited signing links |
| Portal updates | when a portal changes, fixed within 1–2 working days |
| Bug fixes and security updates | yes |
| Support | WhatsApp, Mon–Sat 10 am–7 pm; urgent within 2 hours |
| Small changes | up to 10 hours a month (a field, a wording or template change, a report column) |

| Not included | |
|---|---|
| Change requests | anything that does not match the requirements in this plan (new features, portals, documents) is charged separately, quoted and agreed before we start |
| Aadhaar eSign provider fees | only if MSEDCL insists on formal Aadhaar eSign |
| AI calling, virtual numbers | not offered to this client; they declined virtual numbers |

Monthly in advance. 30 days' notice to stop, and their data is handed over in full.

---

## 8. Deliverables

1. Solara web app, hosted in India, own address, logins for owner and staff.
2. Dashboard: pipeline, needs-attention, document intake, close-out, loan tracker, audit, reports,
   Excel export.
3. Chrome co-pilot for PM Surya Ghar, NISE DCR, MSEDCL and Jan Samarth.
4. Customer e-sign with consent records (English + Marathi).
5. Document generation from their templates: agreement + six MSEDCL documents.
6. Field-team upload page (GPS photos, serial labels).
7. Security: encryption, roles, audit, masked Aadhaar, daily backups.
8. Training session and a written guide.
9. Data stays theirs; full export at any time.

---

## 9. E-sign: how it works and what to tell the client

- The customer opens a private link (WhatsApp, or the installer's phone on site), confirms the
  **last 4 digits of their consumer number** (5 wrong tries lock it), reads each document, ticks the
  ones they approve, signs once, and consents.
- The signature is stored encrypted and placed **only on ticked documents**, and only on the **exact
  version** they saw (content hash). Change a document and it goes back to them for one tap.
- Later documents only need **Approve**. They don't sign again.
- **Legally:** the drawn signature with its consent record proves agreement. It is not an IT Act
  section 3A "electronic signature" (that is Aadhaar eSign or a DSC). The client must confirm MSEDCL
  accepts it. If not, add Aadhaar eSign per document (provider fee) or print for ink.

---

## 10. What we need from the client

| When | What |
|---|---|
| Now | signed agreement, ₹10,000 advance |
| Phase 1 | 1-hour PM Surya Ghar session with a real new customer (customer side and vendor side); documents of 3 new customers; their agreement template |
| Phase 2 | Excel workbook with macros and Word templates (WCR, Annexure-I, DCR declaration, net agreement); 3–5 past completed files (Aadhaar masked); MSEDCL's answer on e-sign; sessions on MSEDCL and DCR; one installation's photos and serials; field team's numbers; 2 customers taking a loan |
| Phase 3 | nothing new; it uses the customers already in Solara |
| Phase 4 | 30 minutes to watch the eight problem cases |
| Phase 5 | two weeks of normal work through Solara; staff free for training |
| Throughout | Chrome on their computer; replies on WhatsApp within a working day |

Recommend they add to their customer agreement: *"The customer authorises [installer] to file the
PM Surya Ghar, DCR and MSEDCL applications on their behalf and to use the OTPs they share for that
purpose."*

---

## 11. See it working

1. `python -m uvicorn app.main:app --port 8900`, open `http://127.0.0.1:8900`, sign in as
   `r.deshmukh` / `demo`.
2. **Close-out** → SS-2042 → the button always shows the next step: company signature → send for
   signature → generate → open MSEDCL.
3. Open the signing link on a phone-sized window: bill digits are the last 4 of `170031277450`.
4. Load `extension/` in Chrome (Developer mode → Load unpacked), paste the key from **Connect
   co-pilot**, open `/msedcl/` (any user ID, password `demo`), open 79435901, press **Attach**.
5. `python tests/closeout.py` runs all of it automatically: 59 checks.
