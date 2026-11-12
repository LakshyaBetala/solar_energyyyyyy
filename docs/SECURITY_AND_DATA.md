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

## What the panel will never do

Type an OTP, CAPTCHA, password or Aadhaar number; tick a declaration; press Submit, Accept,
Approve or Final Submit. It picks dropdown options, answers Yes/No questions from the record,
opens the portal's "+ Add Serial Number" box when that button cannot submit, and attaches files.
`tests/k1_complete.py` checks the panel's own source for any other click. It asks Chrome for no
permissions beyond storage and the listed portals.

## The data

- **Documents** (bill, Aadhaar, passbook, photos, signed papers, receipts) are encrypted on disk
  (Fernet: AES-128 with an HMAC) with `data/vault.key`. A backup never contains the key.
- **Aadhaar**: the number is masked on generated papers and never sent to an AI model. The AI is off
  unless `SOLARA_USE_AI=1` is set, and then only for bill photos the rules cannot read.
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
