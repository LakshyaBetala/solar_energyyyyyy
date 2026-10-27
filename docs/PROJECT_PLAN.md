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
| **Built Phase 1** (close-out, e-sign, documents, co-pilot, sandbox MSEDCL portal) | `tests/closeout.py`: 59 checks pass; existing 61 + 38 still pass |

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
| **Jan Samarth** | loan: 9–10 steps, Aadhaar OTP, bank and branch | customer mobile + Aadhaar OTP; Imperva | **Customer does it.** We give a pre-filled sheet and track it |

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
| 8 | Bank loan (if any) | — | pre-filled details sheet; tracks the loan | does Jan Samarth |
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

Every phase is paid only when its KPI is met on the client's real customers.

### Start — ₹10,000 advance
Agreement signed, WhatsApp group created, access sessions booked.

### Phase 1 — Close-out and e-sign · ₹27,000 · week 1 after templates arrive · **built**
- **What will be done:** close-out screen; the client's templates for all six MSEDCL documents and
  the agreement; customer e-sign (English + Marathi); company signature; Chrome co-pilot for MSEDCL;
  hosting live.
- **Process:** we swap in their templates, then a 1-hour session where the owner logs in to the
  real MSEDCL portal and we confirm the co-pilot on the real page. Then three backlog customers go
  through end to end.
- **KPI:** 3 real backlog customers: all 6 documents generated (each ≤ 300 KB), customer e-signed,
  uploaded on MSEDCL through the co-pilot, **≤ 15 minutes of owner time per customer**.

### Phase 2 — Customer record and document reading · ₹27,000 · week 2
- **What will be done:** document intake (bill, Aadhaar, bank, photos) into one customer record;
  field-team upload page (photos with GPS, serial labels); serial numbers read from photos.
- **Process:** run on 10 recent customers' documents; every field compared with what was filed.
- **KPI:** details captured in **≤ 5 minutes per customer**; **≥ 95% of fields correct**, and every
  uncertain field flagged, never silently wrong.

### Phase 3 — Pre-installation on PM Surya Ghar · ₹27,000 · week 3
- **What will be done:** co-pilot for customer registration, application and vendor selection;
  vendor consent; agreement upload; site feasibility report; OTP call list.
- **Process:** a 1-hour session on PM Surya Ghar with a real new customer (customer side and vendor
  side) to map the live pages, then three new customers.
- **KPI:** 3 real new customers from registration to "agreement + feasibility report submitted",
  **≤ 10 minutes of typing each** (OTP waiting excluded). This is the 5-minute pre target in section
  5.1, with margin.

### Phase 4 — Installation, DCR, tracking and dashboard · ₹24,000 · week 4
- **What will be done:** co-pilot for the 5 installation screens and the DCR certificate; status
  tracking; full dashboard (pipeline, needs-attention, reports); loan helper and tracker.
- **Process:** a session on the DCR portal; one installation's photos and serials; then three
  installations.
- **KPI:** 3 real installations submitted through the co-pilot; the dashboard stage **matches the
  portal** for every live customer. This is the 5-minute post target in section 5.2.

### Phase 5 — Hardening, security and live testing · ₹20,000 · weeks 5–6
- **What will be done:** edge cases (timeouts, network drops, portal changes), staff logins and
  roles, backups, audit, training, written guide.
- **Process:** two weeks of supervised live use on real customers.
- **KPI:** 2 weeks of live use with **no wrong submission** caused by Solara; owner and staff
  trained; handover done.

| | Payment |
|---|---|
| Advance | ₹10,000 |
| Phase 1 | ₹27,000 |
| Phase 2 | ₹27,000 |
| Phase 3 | ₹27,000 |
| Phase 4 | ₹24,000 |
| Phase 5 | ₹20,000 |
| **Total** | **₹1,35,000** (taxes extra, if applicable) |

How the meeting's five modules map onto the phases: Module 1 (documents) is Phase 2. Module 2
(portal automation and loan tracking) is Phases 1, 3 and 4. Module 3 (dashboard) runs through every
phase and is finished in Phase 4. Modules 4 and 5 (security and testing) are Phase 5. The client asked
for registration first. We lead with close-out because it is built, needs no customer OTP, and clears
their backlog. If they insist, Phases 1 and 3 swap.

---

## 7. Pricing structure for the client

**Build: ₹1,35,000**, paid as in section 6. Agreed on the call: ₹10,000 to start, about 20% at the
first KPI, the rest per milestone.

**AMC: ₹6,000 a month, all-inclusive.** It starts the month Phase 1 goes live.

| Included | |
|---|---|
| Hosting | server in India, domain, SSL |
| AI | all document reading, up to 300 applications a month |
| Backups | daily, encrypted, kept 30 days |
| E-sign | unlimited signing links |
| Portal updates | when a portal changes, fixed within 1–2 working days |
| Bug fixes and security updates | yes |
| Support | WhatsApp, Mon–Sat 10 am–7 pm; urgent within 2 hours |
| Small changes | up to 4 hours a month (a field, a wording or template change, a report column) |

| Not included | |
|---|---|
| New features or portals | change requests at **₹4,500 per day**, quoted before starting |
| Aadhaar eSign provider fees | only if MSEDCL insists on formal Aadhaar eSign |
| AI calling, virtual numbers | not offered to this client; they declined virtual numbers |
| Above 300 applications a month | discussed first, never charged without their OK |

Monthly in advance. 30 days' notice to stop, and their data is handed over in full.

---

## 8. Deliverables

1. Solara web app, hosted in India, own address, logins for owner and staff.
2. Dashboard: pipeline, needs-attention, document intake, close-out, loan tracker, audit, reports,
   Excel export.
3. Chrome co-pilot for PM Surya Ghar, NISE DCR and MSEDCL.
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
| Phase 1 | Excel workbook with macros; Word templates; 3–5 past completed files (Aadhaar masked); MSEDCL's answer on e-sign; 1-hour MSEDCL session |
| Phase 2 | documents for 10 recent customers; field team's WhatsApp numbers |
| Phase 3 | 1-hour PM Surya Ghar session with a real new customer |
| Phase 4 | DCR portal session; one installation's photos and serials |
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
