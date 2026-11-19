# Security, data and testing

What Solara does to keep the client's data safe, who owns it, and how it is tested. For the
client's records and for whoever looks after Solara (terms deliverables 10 and 11). Running it:
[RUNNING.md](RUNNING.md) and [OPERATIONS.md](OPERATIONS.md).

## Who can do what

| | Viewer | Operator | Supervisor |
|---|---|---|---|
| See customers, Today, reports | yes | yes | yes |
| Daily work: documents, details, links, marking steps | — | yes | yes |
| People, backups, restore drill, export everything | — | — | yes |

- Every person has their own username and password (10 or more characters, stored as scrypt hashes).
  Supervisors manage people in Reports → People; the very first supervisor is created on the
  computer Solara runs on, only while there is nobody.
- Five wrong passwords from one address lock that username, from that address, for 15 minutes; a
  good sign-in clears the count, so nobody elsewhere can lock the owner out. A sign-in lasts 12
  hours, checked by the server. A new password ends that person's sessions and helper keys at once.
- The session cookie is HttpOnly, SameSite=Lax, and Secure when Solara is reached over HTTPS.
- The Chrome panel uses its own key (Today → Connect the Chrome helper), stored hashed. It works
  only for an operator or supervisor, and stops when that person is removed or gets a new password.

## What the panel does, and what it never does

**Never:** type an OTP, CAPTCHA, password or Aadhaar number; tick a customer's declaration or consent;
work around a portal's bot checks; fill a page that Solara already has as filed, or that has an open
warning, without the owner pressing Fill.

**By itself:** fill the boxes it recognises, pick dropdown options, answer Yes/No questions from what was
recorded for that customer, attach files in the type and size each box takes, open the portal's
"+ Add Serial Number" box when that button cannot submit, press **Fetch Details**, and open the
**Apply for Solar Rooftop** card and the Site Feasibility Report from the application's Action menu.

**Only when the owner switches it on in the helper's options** (all off when installed):

| Switch | What the panel then does |
|---|---|
| Press Next / Submit for me | Presses the page's forward button, and **Select Vendor** (which locks the vendor for 45 days), only when every field is filled, the OTP and CAPTCHA are typed and any declaration is ticked by the person |
| Tick the equipment certification | Ticks the vendor's own certification on the Site Feasibility Report |

Without the switch the panel highlights the button and waits.

**Other sites.** The helper runs on the listed portals. On any other site it loads only after the owner
clicks the Solara button in the browser toolbar there; Chrome then asks whether to remember that site.
A box Solara does not know is taught once in the panel ("which value goes here") and remembered for
that site, in that browser. Sites and taught boxes are listed, and forgotten, in the helper's options.

`tests/k1_complete.py` reads the panel's own source and fails if it sends any click these rules do not name.

## The data

- **Documents** (bill, Aadhaar, passbook, photos, signed papers, receipts) are encrypted on disk
  (Fernet: AES-128 with an HMAC) with `data/vault.key`. A backup never contains the key.
- **Aadhaar**: read from the card's QR code on the computer; the number is masked on generated papers.
  The card is **not sent to an AI model** unless `SOLARA_AI_AADHAAR=1` is set. With it set, the card's
  image goes to the AI provider and the full number is kept, encrypted, for the people who file it.
  Decide this with the client in writing first.
- **AI reading of the electricity bill** happens when an AI key is in the settings
  (`SOLARA_USE_AI=0` switches it off). The bill's image and text go to that provider.
- **Map lookup**: latitude, longitude and urban/rural are found by sending the customer's address
  (no name) to OpenStreetMap's public search. Type the coordinates instead to avoid it.
- **Templates**: the agreement draft and the quotation templates are uploaded in Reports and kept in
  the data folder, never in the program's folder or the code.
- **Receipts** of portal pages are saved with every OTP, CAPTCHA and password box blanked.
- **The audit trail** records every action with who and when; it is append-only from the screens.
- **Backups**: daily, automatic, with a second copy if `SOLARA_BACKUP_COPY` is set; 14 kept. The
  restore drill (Reports) proves the newest one opens.
- **Retention**: `SOLARA_KEEP_MONTHS` deletes a customer's own documents (bill, Aadhaar, passbook,
  photos) that many months after the portal showed the subsidy disbursed. Off unless set. The
  record, the receipts, Solara's papers (agreement, MSEDCL documents) and the audit stay.

## Who owns what

- **The data is the client's.** Reports → Export everything gives every customer, every document
  (decrypted) and the whole audit trail as plain files, at any time, without Almmatix. The file is
  made for that download and deleted from the server once sent. On leaving
  the service the client gets this export in full.
- **The software**: source-code handover and transfer of intellectual property are **not decided**.
  They are for Almmatix to confirm with the client in writing; nothing here promises either.

## How it is tested

`python tests/run_all.py` runs 13 suites against a running Solara, with the Chrome panel loaded
in a real browser, before every release. CI runs them on every push.

| Suite | Covers |
|---|---|
| smoke, ui, validation, longevity, live_mode | sign-in, roles, every screen, input rules, old databases upgrading, the live install |
| milestone1, k1_complete, k1_audit, real_labels | KPI 1 end to end; 89 audit cases; the panel on the client's real field labels |
| closeout, milestone2 | KPI 2: e-sign, documents under 300 KB, the field page, DCR, installation, MSEDCL |
| milestone3 | KPI 3: ten customers at ten portal stages, Today, controls, monthly report |
| milestone4 | KPI 4: the eight problem cases, people and roles, lock-out, session expiry, restore drill |

Real government portals are only looked at during development: no test logs in or submits there.
