# Running Solara on the owner's computer

For the owner (one Windows computer, Chrome) and whoever sets it up. The hosted, many-user install
is in [OPERATIONS.md](OPERATIONS.md); this is the single-computer way.

## Start it

Double-click **Solara.exe**. Solara opens in the browser at <http://127.0.0.1:8900>. A second
double-click only opens the page again. Closing the browser does not stop Solara; restarting the
computer does, so put a shortcut to Solara.exe in the Startup folder (`Win+R`, `shell:startup`).

Beside Solara.exe:

| What | Where | Notes |
|---|---|---|
| Customers, documents, backups | `data\` | Documents are encrypted with `data\vault.key`. |
| Settings | `solara.env` | Same lines as `.env.example`. Created by you; optional. |
| Logs | `data\logs\` | One file a day. Send it when something goes wrong; it holds no OTPs or Aadhaar numbers. |

**`data\vault.key` is the only way to open the documents.** Copy it once to a USB stick or a
password manager and keep it away from the backups.

## First time

1. Copy the `Solara` folder (Solara.exe and `_internal`) to `C:\Solara`.
2. Optional settings: create `C:\Solara\solara.env` with, for example:
   ```
   SOLARA_MODE=live
   SOLARA_PUBLIC_URL=https://solara.your-company.in
   SOLARA_VENDOR_NAME=Your Solar Company Pvt Ltd
   GEMINI_API_KEY=your key                (reads bill photos and Aadhaar cards whose QR code cannot be read)
   SOLARA_BACKUP_COPY=D:\Solara backups
   SOLARA_KEEP_MONTHS=24
   ```
   `SOLARA_MODE=live` gives the real portal links and no sample customers.
3. Double-click Solara.exe. The first time, the sign-in page asks for the supervisor's name,
   username and password (on this computer only, only once). Add everyone else in Reports → People.
4. In Chrome: `chrome://extensions` → Developer mode → **Load unpacked** →
   `C:\Solara\_internal\extension`. In Solara: Today → **Connect the Chrome helper**, paste the
   address and key into the helper's Options.

Documents (agreement, MSEDCL papers, reports) are made into PDF by a browser. Solara uses its own
copy when it has one and otherwise the computer's Chrome or Edge, so nothing else is installed.

## Looking after itself

Every hour Solara checks, and records each action in the Audit Trail:

- **Backup** once a day into `data\backups`, also copied to `SOLARA_BACKUP_COPY` if set. The newest
  14 are kept (`SOLARA_KEEP_BACKUPS`).
- **Finished customers' own documents** are deleted `SOLARA_KEEP_MONTHS` months after the portal
  showed the subsidy disbursed: bill, Aadhaar, passbook, photos. Off unless set. The customer's
  record, receipts, Solara's papers and the audit stay.

Reports → **Health** shows the database, the key, the last backup, disk space and portal changes.
Reports → **Restore drill** opens the newest backup on the side and proves it would restore.

## The desktop app

`desktop/` wraps the same program in its own window (Electron). It keeps the data in
`%APPDATA%\Solara\data` (or `SOLARA_DATA`), which an update or an uninstall leaves alone, and opens
portal and WhatsApp links in the computer's browser, where the Chrome helper is. The Solara menu opens
the data folder, the backups, the logs and the helper's folder.

```
pyinstaller --noconfirm solara.spec        the program itself, into dist\Solara
cd desktop
npm install
npm start                                  run it from source
npm run dist                               the installer, in desktop\out
```

## Templates and prices

Reports → **Quotations**: upload the agreement draft (PDF) once, and one Word quotation per price. A new
price is offered everywhere as soon as its quotation is added. Turning a Word quotation into a PDF needs
Microsoft Word or LibreOffice on this computer; without either, upload each customer's quotation as a PDF
on their page.

## Build Solara.exe (Almmatix)

```
pip install -r requirements.txt pyinstaller==6.21.0
pyinstaller --noconfirm solara.spec
```
The result is `dist\Solara`. Run `python tests\run_all.py` before every build that goes to the client.

## Run from source instead

```
pip install -r requirements.txt
python -m playwright install chromium
python -m app.launcher
```
