# K1 status (branch `feature/complete-k1`)

Code-level K1 is complete in the sandbox. The K1 KPI (3 real customers, each <= 5 min of owner effort)
is **not** claimed: it needs live customers. Tests prove the code paths, not the real portal.

## Added on this branch
- **Customer records**: duplicate detection (same mobile, same name ignoring case/spacing, same
  consumer number) with an explicit "add anyway"; mobile must be a valid Indian number; email,
  PIN and consumer-number checks; a consumer number can sit on only one customer.
- **Validation before portal fill** (`registration.validate`): missing / invalid / uncertain /
  mismatch, shown on the Registration screen and in the co-pilot panel. Nothing is hidden;
  the co-pilot button reads "Fill anyway" while issues remain.
- **Extraction**: new conflict checks (bill PIN vs Aadhaar PIN, bill mobile vs typed mobile,
  bill consumer number vs record). Corrections are kept across re-reads unless the corrected
  document is replaced; the original reading stays in the note. An unread Aadhaar or bill can
  now actually be corrected into the record. A typed full Aadhaar number is refused.
- **Uploads**: unknown kind and empty files refused on every route; a failed read no longer
  loses the upload and says what to do.
- **Agreement**: the exact version sent is kept encrypted and is the version the customer is
  shown; `GET /api/registration/{id}/agreement/check` verifies approval, kept copy hash,
  signatures and the stored PDF; "mark uploaded" requires that verification; blank address/name
  can no longer be printed ("None"); the draft wording is flagged on screen and in the panel.
- **Co-pilot**: never overwrites a field or dropdown the person set (tracked by trusted events);
  extra guard against OTP/CAPTCHA/password fields; custom dropdowns are listed, never clicked;
  a value the page rejects is reported; Solara refusals (bad application number, unverified
  agreement) are shown as NOT saved instead of success; timeouts, disconnected and wrong-key
  states give a message and Try again; fixed a label bug that mapped "Category" to the name rule.

## Needs the real PM Surya Ghar portal (not verifiable here)
Consumer registration/application page labels (HANDOVER A2-A3), Angular dropdowns on those
pages, Vendor Consent, Upload Agreement dialog, application-number page, any portal status text.
Only the labels already in `tests/real_labels.py` are verified against real screens.

## Needs client approval
Agreement wording (`closeout.t_agreement`, `TEMPLATE_DRAFT`); whether the portal accepts an
e-signed agreement (Q5); email requirement (Q3).

## Manual validation
Run HANDOVER section 5 "Manual test script" 3x in the sandbox, then on the real portal with the
owner, stopwatch per customer, OTP waiting excluded. Also: try a bill/Aadhaar with a different PIN
and mobile, add a duplicate customer, and check the panel lists every issue before Fill.
