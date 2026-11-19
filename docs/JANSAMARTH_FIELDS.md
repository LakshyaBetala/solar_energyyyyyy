# Jan Samarth: the rooftop solar loan, step by step

What each of the ten steps asks, and who fills each box. Read from the portal's own public code
(`www.jansamarth.in/sl/main.js` and its English text file) and checked against banks' guides and walkthroughs,
November 2026. Nothing here was taken from a logged-in session: lists the server sends after login (occupations,
house ownership, relationship, lenders, the documents list) are not public, so they are not listed.

**Who fills it:** **Solara** = the helper types it from the customer's record. **Customer** = the customer's own
answer; the owner types it with them. **Person** = OTP, consent, verify buttons: a person only. **Portal** = filled
or locked by the portal itself.

Before you start: the customer must already be registered on PM Surya Ghar **with your company selected as the
vendor**, and your company's email, PAN and mobile must be on record there. Step 2 checks all of it and stops
otherwise.

## 1. Required Documents (`/sl/requiredDocuments`)

| Box | Kind | Who |
|---|---|---|
| Documents to keep ready: Aadhaar (with the mobile linked to it), PAN, latest electricity bill | list | |
| Required Loan Amount * (Rs 5,000 to Rs 10,00,000) | number | Customer |
| Attention! (check the amount) → Proceed / Edit | box | Person |
| Consent (scroll each tab to the end, then Next / Agree & Proceed) | box | Person |

The loan amount decides the rest: **above Rs 2,00,000** step 3 also asks the PAN and the own contribution must be at
least 20% of the project cost; **up to Rs 2,00,000** no PAN, at least 10%, and an income self-declaration at the end.

## 2. Basic Details (`/sl/basicDetails`)

| Box | Kind | Who |
|---|---|---|
| Solar Roof Top Application Id * (e.g. NP-AAAAA00000-00000) | text | **Solara** (the PM Surya Ghar application number) |
| DISCOM Consumer Id * | text | **Solara** (consumer number) |
| Mobile Number * (must be the one registered on PM Surya Ghar) | text, 10 digits | **Solara** |
| Proceed: pulls name, address, PIN, DISCOM, capacity, vendor from PM Surya Ghar | button | Person |

## 3. Identity Verification (`/sl/identityDetails`)

| Box | Kind | Who |
|---|---|---|
| Verify with: Aadhaar number / Aadhaar Virtual ID | radio | Portal (Aadhaar number is pre-chosen) |
| Aadhaar number *: **one 12-digit number in three boxes of four** (first two hidden) | 3 boxes | **Solara** (when the full number is kept) |
| Aadhaar Virtual ID: 16 digits in four boxes | 4 boxes | Customer (never filled by Solara) |
| I provide my consent ... | tick | Person |
| Get OTP → Enter Otp Here (6 digits, 3 minutes) → Submit | OTP | Person (the OTP goes to the customer's Aadhaar mobile) |
| Details as per Aadhaar (photo, name, gender, DOB, address) | read-only | Portal |
| PAN * (only above Rs 2,00,000; must be a person's PAN, 4th letter P) → Submit | text | **Solara** |
| Date Of Birth (only if the Aadhaar gave the year alone; calendar, cannot be typed) | date | Customer |

## 4. Income Details (Verified/Declared) (`/sl/incomeDetails`)

| Box | Kind | Who |
|---|---|---|
| Gross annual income * (before deductions) | number | Customer |
| Net annual income * (take-home; not more than gross) | number | Customer |

For a PAN case the portal may have fetched income from the tax department already; then it is only Proceed.

## 5. Applicant Details (`/sl/solarInstallationDetails`)

| Box | Kind | Who |
|---|---|---|
| First Name *, Middle Name, Last Name * (letters only) | text | **Solara** (from the Aadhaar name; usually pre-filled) |
| Email Id * | text | **Solara** |
| Mobile No. * | text | **Solara** |
| Occupation * | list | Customer |
| Project Cost * | number | **Solara** (installation cost) |
| Own Contribution * (10% / 20% minimum, not more than the cost) | number | Customer |
| If collateral is required later, would you provide it? * | Yes / No | Customer |
| Address as per Aadhaar | read-only | Portal |
| Is current address same as above? (No opens street, landmark, state, district, sub-district, village, block, PIN) | Yes / No | Customer |
| Installation address, State, Pincode, RTS Capacity, Vendor Name, Vendor Contact | read-only | Portal (from PM Surya Ghar) |
| House Ownership * | list | Customer |
| Do you want to add a co-applicant? **(starts on Yes with an empty row: Name, DOB, Mobile Number, Relationship)** | Yes / No + row | Customer. Solara never puts the customer's own details in that row. Choose No if there is none, then No again in the box that asks |

## 6. Bank Account Details (`/sl/bankAccountDetails`): the customer's own account

| Box | Kind | Who |
|---|---|---|
| Account Holder Name * | read-only | Portal |
| Bank Account Number *, Confirm Bank Account Number * (hidden boxes) | number | Customer (Solara keeps the number only masked) |
| Account type * (Current / Saving) | list | **Solara** (from the passbook) |
| IFSC Code * | text | **Solara** (from the passbook) |
| Verify (the portal checks the account with the bank) | button | Person |

## 7. Credit Details (`/sl/creditDetails`)

Existing loans, usually fetched from the credit bureau: Name of lender, Type of loan, Sanctioned Amount, Outstanding
Amount, Overdues, EMI, **+ Add Other Loan**. All **Customer**. No loans: just Proceed.

## 8. Upload Documents (`/sl/uploadDocuments`)

One row per document, the list comes from the server (a star = compulsory). jpeg, pdf, png or tiff, **under 2 MB
together**. Electricity bill: up to the last 6 bills. One house-ownership choice in step 5 adds an extra row.
**Solara** attaches the electricity bill, the Aadhaar and the PAN card where a row names them; anything else, the
customer's file.

## 9. Application Review Details (`/sl/applicants`)

Read-only cards per section (Complete / Edit). Up to Rs 2,00,000: the Income Declaration page, filled by the portal
from earlier answers. Then **Submit Application** (Person).

## 10. Bank Selection (`/sl/matches`)

Offers from the customer's existing bank and other banks (amount, product, tenure, interest) → **Select offer**, or
**Go offline** and choose bank, state, district and branch. All **Customer**. Some banks then ask an Additional
Details page (tenure, moratorium, declarations).

## What the helper does on these screens

- It fills the **Solara** boxes above by itself on screens it knows, and shows "Fill now" on a screen new to it.
- It never types the OTP, never ticks consent, never presses Proceed, Verify, Submit or Select offer.
- On every page it leaves the portal's "Need Help?" form alone.
