# Solara: the owner's guide

How to do a day's work in Solara. Setting it up is in [RUNNING.md](RUNNING.md).

## The idea

Enter a customer's documents once. Solara reads them, makes every paper, gets the customer's
e-signature on their phone, and the **Solara panel** in Chrome fills the government forms. You log
in, type the OTP and CAPTCHA, check the form and press Submit. Solara never presses Submit, never
types an OTP, and never ticks a declaration.

## Start of the day: Today

Today is one list of everything to do, for every customer, in this order:

| List | What it means |
|---|---|
| **Calls to make** | The customer must read out an OTP, approve the agreement, or accept the installation. Tap the number to call; **WhatsApp: codes are coming** warns them first. A red line means a portal is waiting for an OTP right now. |
| **To do in Solara** | One click each: check what was read, add a detail, send for e-sign, confirm serial numbers. Red lines first: something the portal sent back. |
| **On the government website** | The panel fills it; you check and press Submit. |
| **Waiting** | For the customer, the dealer (DCR stock) or the field team. Nothing to do. |
| **Paused** | Customers you paused, with the reason. |

Do the top line first; its button is green. Under the list is **every customer on the portal's ten
stages**, and the **monthly report** (Excel or PDF).

**Open vendor + customer logins side by side** puts the two portal logins next to each other. What
you mark in one window shows at once in the other window's panel.

## A new customer (Registration)

1. **+ New customer**, the name only. **Send the WhatsApp link**: the customer sends the bill,
   Aadhaar, passbook and roof photo from their phone.
2. Solara reads them. Check anything highlighted.
3. Call for the OTP and register on PM Surya Ghar; the panel fills the form. The application
   number is saved by itself.
4. Approve in Vendor Consent. Add the company signature once; send the agreement to e-sign.
5. Upload the signed agreement (the panel attaches it) and press **I pressed Submit**.
6. The customer approves it in their login (they read out the SMS code). Press **I pressed Verify &
   Approve**, or open My Applications in the customer login: the panel reads it.

## After the agreement (Installation)

Site feasibility report → loan on Jan Samarth (only with the customer, who types their own Aadhaar
and OTP) → **Send the field link**: the team photographs the site and every panel label → confirm
the serial numbers → DCR certificate → the 5 installation screens → the customer accepts on their
phone → **Close-out**: six documents e-signed and uploaded on MSEDCL.

**Pause** a customer who is away; **Retry** a step the portal sent back (say what it said).

## When something goes wrong

The panel says it in plain words and Solara records it. Nothing is filed twice.

| What happens | What the panel says | What you do |
|---|---|---|
| Wrong OTP | the code was not accepted | ask for the newest SMS again |
| No OTP SMS | points at **Resend OTP** | press it yourself; use the newest code |
| The portal logged you out | log in again | open the same page; Solara checks what is filed first |
| Internet off | nothing is lost | wait; the page is read again when it is back |
| A file too big | (nothing: Solara makes it small enough) | — |
| A serial already on another customer | shown in red, with whose it is | new photo of the right label |
| A site photo without location | refused, with why | photo again with location on, the original file |
| DCR: panels not in your stock | customer goes to **Waiting** | call the dealer; apply again when they confirm |

If the panel says **Solara already has this filed**, check My Application before filling again.

## Reports

- **The six milestones, measured**: each target, where it stands now, met or not yet.
- **Owner's time per customer**: registration, after installation, and the whole of it.
- **Health and upkeep**: database, key, last backup, disk, portal changes. **Back up now**,
  **Restore drill**, **Export everything** (all customers, documents and the audit trail; it holds
  Aadhaar copies, keep it safe).
- **People** (supervisor): add someone, change a role, give a new password, remove someone.

## Rules Solara keeps

- The OTP, CAPTCHA, passwords and the Aadhaar number are typed by a person only.
- Every action is in the **Audit Trail**, with who and when.
- Aadhaar is never sent to an AI model. Documents are stored encrypted.
- Five wrong passwords lock that username for 15 minutes; a sign-in lasts 12 hours.
