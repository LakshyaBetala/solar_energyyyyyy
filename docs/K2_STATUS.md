# K2 status (branch `feature/complete-k2`)

Code-level K2 is built and tested **in the sandbox**. Nothing here has been run against a real
government portal, so no portal integration is claimed as working. K2's KPI (3 real customers,
post-installation <= 5 min of owner time each; 0 files rejected for size or format; 2 loan
customers) needs live customers and is **not** claimed.

## Status by requirement

| Requirement | Status | Notes |
|---|---|---|
| A. Site feasibility report: record, validation, working-copy PDF, tracking | Implemented and tested | `k2.sfr_issues`, `closeout.t_sfr`; the portal's own form is the official document, Solara's PDF is a record |
| A. Filling the SFR form with the co-pilot | Implemented, not live-validated | 6 labels are real (`tests/real_labels.py`); roof area is filled when on file; vendor's employee/contact are always left to the person |
| B. Installation, five screens: data, validation, order, tracking | Implemented and tested | `k2.screen_issues`, filed in order, each refusing unready data |
| B. Matching the real screens 2-5 | **Partially implemented / blocked** | only screen 1 (vendor, latitude, longitude) has labels seen on the real portal. Screens 2-5 use Solara's field names; `SCREENS_VERIFIED` and the Filing screen say so |
| C. DCR: serial parsing (Excel/CSV/text), duplicates, registry, Excel export, certificate upload | Implemented and tested | all-or-nothing saves; first holder of a serial keeps it; each serial has customer, source, time |
| C. Filling the NISE DCR form | Implemented, not live-validated | labels from the client's recording; a certificate file is attached when the page asks for one |
| D. Jan Samarth: details, validation, documents, status tracking | Partially implemented | loan pack + checks + status (submitted/sanctioned/rejected/withdrawn). The portal's labels are unknown, so the co-pilot fills only generic name/mobile/address/PIN there; `https://www.jansamarth.in/*` is matched but unverified. No bank credentials or OTP are held; nothing is submitted for the customer |
| E. MSEDCL: PDF validation, 300 KB, compression, customer association, status | Implemented and tested | lossless clean-up first, then re-render at falling resolution; result says if it is low resolution. "Uploaded" only when the MSEDCL page itself lists the six; a rejected row makes the step failed. Real-page check = handover A11 |
| F. Field-team upload | Implemented and tested | per-customer link, 3 days, switch-off, one customer only, shows first name + last 4 only; GPS from the photo, or from the phone only if the person ticks the box (must be in India, accuracy <= 100 m) |
| F. Reading serial numbers from label photos (model) | **Not implemented** | photos are stored; serials come from a sheet or typed. Needs the AI key and real label photos (B7) |
| G. Report templates | Implemented; wording **blocked on client** | `/api/templates` lists each generated document and that it is still the draft layout |
| H. Tracking, receipts, history, timings, failed/retry | Implemented and tested | `filings` table (append only), receipts with optional file, per-stage minutes |
| Dashboard (Filing screen) | Implemented and tested | steps, pending documents, failed, missing, references, next action, history |

## Added on this branch
- `app/k2.py` (logic), `app/field.py` (field page), `app/k2portal.py` (sandbox pages), K2 routes in `app/main.py`.
- Tables (in `SCHEMA`, `CREATE IF NOT EXISTS`, no ALTERs, so every older database upgrades by just starting): `filings`, `serials`, `field_links`.
- Close-out fields for the SFR, DCR credit and the loan; documents `sfr` and `quotation` (hidden from the Close-out screen, shown in Filing).
- `closeout.fit_report`, `closeout.validate_pdf`; `build()` refuses to store a file the portal would refuse.
- Co-pilot: K2 rules (marked unverified), quotation/certificate/invoice/serial-sheet attachment, receipt capture, portal-error capture, rejected-row detection, issue list matched to the page in front of the person.
- Fixes found on the way: `labelOf` no longer lets a neighbour's label rename a field; a confirmation page with no form is now read for its reference; `render()` no longer throws if clicked before the first load finishes.

## Rules kept
Nothing clicks Submit/Upload/Approve; no CAPTCHA/OTP/password/declaration handling; no Aadhaar number is stored or sent to a model (K2 code has no model call); field links never expose address or phone; every upload and status change is audited.

## Needs the real portals (handover A7-A11)
Real labels and dropdowns for SFR (beyond the 6 seen), installation screens 2-5, the DCR confirmation page, MSEDCL list statuses (`Verification Pending/Approved/Rejected`), Jan Samarth. The confirmation-page labels the panel looks for ("Reference Number", ...) are Solara's guess and must be checked.

## Needs client approval
Wording/layout of the SFR record, quotation, agreement, WCR, Annexure-I, DCR declaration and net-metering bond (`closeout.TEMPLATE_DRAFT`); who may use the field link (office staff vs installers).

## Manual validation
1. Sandbox: Filing screen, open a registered customer, enter the SFR facts in Close-out, open `/k2portal/sfr`, press Fill, type the employee and contact yourself, tick the declaration, press Submit; the reference should appear in Filing.
2. Repeat for `/k2portal/install/1..5` (in order) and `/k2portal/dcr`.
3. Create a field link, open it on a phone, upload a photo with location on, then one with location off and the box ticked.
4. Real portals: follow handover A7-A11 with the owner; save each page's HTML (customer data removed) and add its labels to `tests/real_labels.py`.
