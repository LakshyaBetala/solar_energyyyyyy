# Pre-installation on the real portals: every step and field

From the owner's 32-minute walkthrough on 7 Nov 2026 (screen recording plus meeting notes). He
registered a customer, applied, selected his company as vendor, accepted it in his vendor login,
uploaded the agreement, filed the site feasibility report, approved the agreement as the customer,
and started the bank loan. Field names only; no personal data is copied here.

**Legend for "Solara today":** ✅ filled or handled · 🟡 partly · ❌ missing · 👤 a person does it (OTP,
CAPTCHA, declarations, Submit), by design.

## 1. The process at a glance

| # | Step | Portal and login | Who acts | Codes | Solara today |
|---|---|---|---|---|---|
| 1 | Log in as the customer | consumer.pmsuryaghar.gov.in, customer's mobile | owner, customer reads the OTP | mobile OTP + arithmetic CAPTCHA | 👤, Today shows the call |
| 2 | Complete profile (first login only) | consumer | owner | — (email OTP only if an email is given) | ✅ name, state, district |
| 3 | "Do you want the Vendor to fill the Application form?" | consumer | owner answers **No** | — | ✅ the panel says answer No |
| 4 | Start a new application: fetch from the DISCOM | consumer (dialog) | owner | — | ✅ state, district, DISCOM, consumer no. |
| 5 | Application form, submit | consumer | owner | — | ✅ gender, category, kWp, bill (§6) |
| 6 | Feasibility | DISCOM, automatic | — | — | ✅ (auto-approved the same minute) |
| 7 | Select vendor | consumer | owner | — | ✅ vendor name |
| 8 | Subsidy bank details | consumer | owner | — | 🟡 type, bank, IFSC, holder, passbook; branch and account number typed (§6) |
| 9 | Vendor Consent: Accept | vendor.pmsuryaghar.gov.in, owner's login | owner | email + password + CAPTCHA + OTP to owner's phone | ✅ (KPI 1) |
| 10 | Upload Agreement | vendor | owner | — | ✅ cost + file |
| 11 | **Customer approves the agreement** | consumer | owner, logged in as the customer | mobile OTP again if logged out | ✅ step 7 in Solara; the panel records it (§6) |
| 12 | Site Feasibility Report | vendor | owner | — | 🟡 (§2.12) |
| 13 | Bank loan (loan customers only) | consumer → Jan Samarth → Bank of Maharashtra portal | customer + owner | Aadhaar OTP, bank OTP + CAPTCHA | 🟡 Jan Samarth stand-in only (§2.13) |

The portal enforces this order:
- **Bank Loan** is enabled only after the vendor uploads the agreement and the customer approves it.
- Once the agreement is uploaded, the vendor cannot be changed for 45 days.

## 2. Fields, step by step

### 2.1 Customer login — `consumer/#/login` ("Apply For Rooftop Solar")
| Field | Type / limit | Req. | Solara |
|---|---|---|---|
| Mobile Number | +91 fixed, 10 digits | * | ✅ mobile |
| Human Check | arithmetic CAPTCHA image | * | 👤 |
| "Yes, I have read all the guidelines…" | checkbox; Verify stays disabled until ticked | * | 👤 |
| OTP | 6 boxes, valid 15 min, resend after 60 s; sent to the mobile | * | 👤 |

### 2.2 Complete Your Profile — dialog on the first login
| Field | Type | Req. | Solara |
|---|---|---|---|
| Name | text | * | ✅ name (bill spelling) |
| Mobile Number | read-only, from login | | — |
| Email | text; an email triggers an email OTP | optional | 🟡 only if the owner wants it (answers our "no email" question: it is optional) |
| Communication Address | text | optional | ✅ address |
| State / District | searchable dropdowns | * / * | ✅ |
| Pin Code | text | optional | ✅ pin |
| Save | disabled until required fields are filled | | 👤 |

### 2.3 "Do you want the Vendor to fill the Application form?" — Yes / No
The owner answers **No** and fills the application himself (his words: "generally…").

### 2.4 Start a new Application — dialog
| Field | Type | Req. | Solara |
|---|---|---|---|
| State | searchable dropdown | * | ✅ |
| District | dropdown | * | ✅ |
| Electricity Distribution Company / Utility | dropdown ("Maharashtra State Electricity Distribution Co. Ltd") | * | ✅ discom |
| Consumer Account Number (CA No.) | 12 digits | * | ✅ consumer_no (from the bill) |
| Fetch Details | button; then shows Name, Circle, Division, Subdivision, Sanctioned Load (read-only) | | 👤 press |

### 2.5 Apply for Solar Roof Installation — `consumer/#/signed-in/new-application`
Section 1, Details of Applicant:

| Field | Type | Req. | Solara |
|---|---|---|---|
| Name as per Electricity Bill | read-only, fetched | * | — |
| **Gender** | dropdown: Male / Female / Other | * | ❌ **Solara reads gender from the Aadhaar QR but the co-pilot has no rule for it** |
| Address of Premises of Installation | read-only, fetched | * | — |
| Complete Postal Address (E-Token receipt of Subsidy) | text | optional | 🟡 could take the address |
| State, District | read-only, fetched | * | — |
| Pin Code | pre-filled, editable | * | ✅ |
| Type of Location | dropdown (options not seen) | optional | 🟡 location_type exists for later forms |
| Did Anyone Help? (Optional) | dropdown (options not seen) | optional | leave |
| SC/ST Status | dropdown (options not seen) | optional | leave; ask the customer only if relevant |

Section 2, DISCOM details: all read-only "(From Electricity Bill)". Fields: State, DISCOM name, Circle,
Division, Subdivision, Consumer Account number, Sanctioned Load.

Section 3, Solar Rooftop Details:

| Field | Type | Req. | Solara |
|---|---|---|---|
| Category | dropdown: Residential / Residential Welfare Association | * | ✅ category |
| Proposed Solar Plant Capacity (kWp) | number, e.g. 3.30 | * | ✅ kW tapped by the owner |
| Capacity of Solar Plant if any existing installed (kWp) | read-only, 0 | | — |
| Latitude / Longitude, "Pick from map" | text + map picker | optional | 🟡 left empty by the owner too |

Section 4, Upload Documents:

| Field | Type / limit | Req. | Solara |
|---|---|---|---|
| Upload Electricity Bill (Any from last 6 months) | JPG, JPEG or PDF, max 2 MB | no * | ✅ bill; 🟡 2 MB not checked |

Bottom of the form:

| Field | Type | Req. | Solara |
|---|---|---|---|
| Give Up Subsidy | checkbox, unticked | | leave |
| DCR Category Type | radio, "With DCR" by default | | leave (DCR) |
| I agree with Net Metering Agreement | checkbox, opens the agreement, Accept | * | 👤 |
| Save as Draft / Submit | buttons | | 👤 |

After Submit:
- Message: "Your Application has been submitted successfully."
- The application number and a 10-stage tracker appear.
- Downloads: Application Acknowledgement, E-token, Feasibility Letter, Net Metering Agreement.

The owner says gender, category and capacity "you have to take as input from me". Category and capacity
are already his taps in Solara; gender comes from the Aadhaar.

### 2.6 Feasibility
Nothing to fill. The DISCOM approves automatically (the letter says "Approved by : Auto Approved").
The approval is a downloadable "Approval of feasibility" PDF with the applied and approved kWp,
sanctioned load and approval date.

### 2.7 Select vendor — `consumer/#/signed-in/select-vendor`
| Field | Type | Solara |
|---|---|---|
| State / District | pre-filled filters | — |
| Search Vendor | type-ahead | ✅ vendor name |
| Select Vendor | button | 👤 |

Then a confirmation: "Are you sure with vendor selection?" (with the 45-day lock note), Yes, and
"Vendor has been selected successfully".

### 2.8 Savings Account Bank Details For Subsidy — `consumer/#/signed-in/bank-details`
| Field | Type / limit | Req. | Solara |
|---|---|---|---|
| Account Type | radio: Savings Account / Loan Account | * | ❌ |
| Bank Name | dropdown | * | ❌ |
| IFSC Code | text | * | ❌ (read from the passbook, but the co-pilot never fills bank fields) |
| Branch Name | text | * | ❌ |
| Account Holder Name | text; must match the electricity consumer's name | * | ❌ (read from the passbook) |
| Name as per Bank | read-only | | — |
| Account Number / Confirm Account Number | text, twice | * | ❌ (**Solara keeps only a masked number**) |
| Upload Cancelled Cheque / Passbook / E-statement | JPG, JPEG or PDF, max 2 MB | * | 🟡 passbook photo exists |

### 2.9 Vendor Consent — `vendor/#/signed-in/application-request-list`
Tabs: Pending / Rejected. The expanded row is read-only and offers Accept / Reject; Remark is required only
to reject. On Accept: "Your action is completed successfully." Solara: ✅ the owner marks it, or it is read back.

### 2.10 Upload Agreement — vendor, My Application → Action
| Field | Type / limit | Req. | Solara |
|---|---|---|---|
| Customer Name, Consumer Number, Application Number | read-only | | — |
| Total Cost of RTS Installation (inclusive of taxes and all other charges as in the Agreement) | number | * | ✅ rts_cost |
| Agreement Copy | JPG, JPEG or PDF, max 2 MB | * | ✅ |

After upload, the action reads "Update Agreement".

### 2.11 Customer approves the agreement — consumer, My Applications → "Submit Agreement Details"
- Read-only: total cost, uploaded on, agreement copy.
- **Consumer Action**: Approve / Reject (required).
- On Approve, a required declaration checkbox appears, ending "…this digital copy matches the physical
  agreement executed by me". The button reads **Verify & Approve**.
- Solara: ❌ **not a step**. It needs the customer's login, so a second OTP call if the session ended.
- Approving is what enables Bank Loan.

### 2.12 Site Feasibility Report — vendor, Action → "Site Feasibility Report"
| Field | Type / limit | Req. | Solara |
|---|---|---|---|
| Roof has enough load bearing capacity | Yes / No | * | ✅ roof_load_ok |
| Availability of shadow free roof for the RTS installation | Yes / No | * | ✅ shadow_free |
| Available shadow free roof area [Meter Square] | number | * | ✅ roof_area; owner's rule ≈ 10 m² per kW |
| Permissible RTS Installation Capacity By Vendor (kW) | number | * | ✅ capacity |
| Vendor has visited the installation site and carried out the assessment | Yes / No | * | ✅ site_visited |
| Quotation Amount (Rs.) | number | * | ✅ rts_cost (same as the agreement cost) |
| Quotation Document | **PDF only, max 2 MB** | * | 🟡 Solara's quotation is a draft, not his format |
| Name of vendor employee visited the project site | text | * | ✅ visitor_name |
| Contact Number | mobile | * | ✅ visitor_phone |
| Certification checkbox (equipment aligned with scheme guidelines) | checkbox | * | 👤 |
| Upload photo (Pre Installation) | **JPG/JPEG only, max 1 MB** | * | 🟡 roof photo exists; JPG and 1 MB not enforced; the sandbox accepts PNG |

- No confirmation message was seen after Submit.
- Reopened, the report is read-only and can be downloaded as "RTS Site Feasibility Report Format for
  Bank" (2 pages: consumer, vendor, site assessment, declaration, geo-tagged roof photo). This PDF is
  what goes to the bank.

### 2.13 Bank loan (loan customers only)
1. **Consumer portal, Bank Loan.** A check of the details: name, mobile, installation address, PIN,
   vendor, approved capacity, gender. "The loan amount disbursed will be credited to the bank account of
   the vendor only." Then Yes.
2. **Jan Samarth** (the redirect failed once with "Something went wrong"; it worked the second time):
   - An application ID `ANS-SOLAR-…` is created automatically, "Step 1/10".
   - Step 1, Required Documents: Required Loan Amount (*), then "Attention!", Proceed.
   - Three consent tabs (Aadhaar/UIDAI, Bureau check, Other consents), each read to the end, then Agree & Proceed.
   - Step 3, Identity: Aadhaar number (or Virtual ID) and a consent tick. The OTP goes to the
     **customer's Aadhaar-linked mobile**. The walkthrough stopped here.
3. **Bank of Maharashtra Solar Rooftop Loan**:
   - The link reaches the owner from his bank contact on WhatsApp.
   - Scheme details, then Accept.
   - Terms, then tick and Continue. Note: "in case of wrong submission… not allowed to apply for 30 days".
   - Sign in: Jan Samarth ID, Mobile Number, CAPTCHA, privacy tick, Send OTP.
   - Then, by his description (not shown): upload the feasibility report, quotation and proof of property.
   - The bank's document list: Aadhaar, PAN, property ownership proof, 6-month bank statement, latest
     electricity bill, roof ownership certificate, application details, DISCOM feasibility approval,
     vendor agreement, quotation/proforma invoice; later the net meter commissioning certificate.
   - Eligibility: loan ₹10,000 to ₹2 lakh, age 21–70, CIBIL 680+, savings account with the bank.

Solara today: a Jan Samarth stand-in in the sandbox, where the co-pilot leaves loan amount, bank and
Aadhaar to people. The **Bank of Maharashtra portal is not modelled**, and the loan documents (PAN,
property proof, statement, roof ownership) are not collected.

## 3. What comes from whom

| From | What |
|---|---|
| Customer (documents) | bill, Aadhaar (gives gender), passbook or cancelled cheque; loan only: PAN, property proof, 6-month statement, roof ownership certificate |
| Customer (live) | login OTP (one or more calls), Aadhaar OTP and bank OTP for a loan |
| Owner (per customer) | kW, cost (= quotation amount), roof area (≈10 m²/kW), site Yes/No answers, which field-team member visited (name + mobile), pre-installation photo (sent by the customer or the field team on WhatsApp), loan yes/no and amount |
| Owner (once) | quotation template, agreement template, field team names and mobiles |

## 4. Gaps and fixes, in order

| # | Gap | Fix | Size |
|---|---|---|---|
| G1 | The customer's agreement approval (§2.11) is not a step | Add "Customer approves the agreement" after the upload, a Today call line ("Call X: approve the agreement in their login"), and a panel hint for the radio + declaration (person-only) | M |
| G2 | Status reader: "Subsidy Disbursal (**Disbursed**)" and "Subsidy Request (**Redeemed**)" read as pending (`tracker.parse`; `disbursed$` fails on the closing bracket) | Fix the regex, keeping "Not Redeemed" pending; test all 8 wordings seen | S |
| G3 | Gender not filled | Map Aadhaar QR gender M/F/T to Male/Female/Other; co-pilot rule `gender` | S |
| G4 | Subsidy bank details (§2.8) all manual | Fill bank name, IFSC, branch and holder from the passbook. The account number stays masked, so either keep it a typed field (shown in "Left for you") or store it encrypted; **our decision** | M |
| G5 | Pre-installation photo must be JPG ≤ 1 MB; quotation PDF ≤ 2 MB; bill and agreement ≤ 2 MB | Convert and shrink before attaching; block oversize with a clear message; fix the sandbox to accept JPG/JPEG only | S |
| G6 | Quotation in his format | Template from his Word file: letterhead, outward no., 9 line items with HSN/SAC, GST 5% on modules and inverter, 18% on the rest, back-calculated from the total; T&C page; file named "<customer> <amount>.pdf" | M |
| G7 | Agreement in his format | His 4-page MNRE standard agreement (blanks: date, consumer name and address; vendor pre-printed; both signatures). The customer's declaration speaks of a "physical agreement executed", so check whether e-signed is accepted | M |
| G8 | "Vendor fill?" popup | Panel tip: answer No | S |
| G9 | Field team for the site report | A small list of field-team members (name + mobile) to pick from; roof area suggested as 10 × kW, editable | S |
| G10 | Bank of Maharashtra loan | Collect loan documents on the customer link (only for loan customers); model the BoM sign-in and upload pages in the sandbox after seeing them live; keep the SFR "for Bank" PDF and the feasibility letter in the customer's file | L |
| G11 | Feasibility letter | Download it into the customer's file; read approved kWp and date | S |
| G12 | OTP calls | Plan the customer-login steps (profile, application, vendor selection, bank details) for one call; the agreement approval needs a second, unless done while still logged in | — |

## 5. Things the walkthrough corrected

- **Email is optional** in the customer profile. Leave it blank unless the customer wants mails, and
  skip the email OTP.
- **Feasibility is automatic** and instant ("Approved by: Auto Approved").
- **The customer must approve the agreement in their own login.** The vendor upload alone is not enough.
- **The loan goes through Jan Samarth and then the Bank of Maharashtra's own portal.** It is not a single form.
- **The quotation amount equals the agreement's total cost.**

## 6. Done on k1-owner (7 Nov 2026), with tests

| # | What now happens | Test |
|---|---|---|
| G1 | Seventh step "Customer approved it on the portal". Today shows a call line with its own WhatsApp heads-up. The co-pilot shows the steps and an "I pressed Verify & Approve" button in the Submit Agreement Details dialog; the dashboard has "Mark it approved" | milestone1, real_labels |
| G3 | Gender is filled from the Aadhaar QR (M/F/T → Male/Female/Other) | rule only; no demo customer has a QR gender |
| G4 | Account type (Savings), bank name (from the IFSC), IFSC and holder are filled from the passbook; the panel asks to check bank name and account type. **Branch and the account number twice stay typed by hand** (Solara keeps only a masked number) | real_labels "subsidy-bank" |
| G5 | Photos go to the portal as JPEG under 2 MB, the pre-installation photo under 1 MB; a PDF over 2 MB is refused with a message | — |
| G8 | "Do you want the Vendor to fill": the panel says answer No | real_labels |
| — | "Proposed kWp" is filled with the capacity; Category with Residential; Type of Location, SC/ST and "Did anyone help" are left | real_labels "apply-form" |
| — | **Customer login tracker**: the panel reads the ten stages on My Applications and updates Solara (Upload Agreement Completed → uploaded; Installation In Progress or later → customer approved). A tracker behind Solara moves nothing back | real_labels |
| — | **Two logins side by side**: Today → "Open vendor + customer logins side by side" (and the Upload step) opens the vendor login on the left and the customer login on the right. What one tab marks (uploaded, approved) shows at once as a note in the other tab's panel; the Solara dashboard picks it up when you come back to it | real_labels (two tabs) |

Still by hand on purpose: every OTP, CAPTCHA and password; the guidelines, declaration and net-metering
ticks; every Submit / Accept / Verify & Approve; the bank account number; the site Yes/No answers and
the roof area (measured on site).
