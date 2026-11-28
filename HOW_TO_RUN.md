# How to run the Solara portal

These steps run the Solara web portal on one Windows computer, from this branch (`ui-ux`).
It takes about 10 minutes the first time.

## 1. What you need

- **Windows 10 or 11** with **Python 3.11 or newer** (3.12 is tested). Tick "Add Python to PATH" when you install it.
- **Git**
- **Google Chrome**, for the portal and for the Chrome helper (co-pilot)
- **Microsoft Word**, only to download a quotation as a PDF. Without Word, quotations still download as Word files.

## 2. Get the code

```
git clone https://github.com/LakshyaBetala/solar_energyyyyyy.git
cd solar_energyyyyyy
git checkout ui-ux
```

If you already have the folder, update it instead:

```
git fetch
git checkout ui-ux
git pull
```

## 3. Install the parts once

```
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 4. Settings (optional, but needed for reading documents with AI)

Copy `.env.example` to a new file named `.env`, in the same folder, then fill in what you use. The main lines are:

```
SOLARA_USE_AI=1
GEMINI_API_KEY=key1,key2
```

- **`GEMINI_API_KEY`:** your keys from Google AI Studio, separated by commas. Gemini then reads the electricity bill and the Aadhaar as soon as they are uploaded. Without a key, Solara still works: the bill text and the Aadhaar QR code are read by fixed rules.
- **`SOLARA_MODE=live`:** turns off the sample customers. Links then open the real government portals.

Never commit `.env`. It holds your keys, and git already ignores it.

A `GEMINI_API_KEY` set in the Windows environment variables wins over the one in `.env`. If an old one is there, remove it:
Windows search, then "Edit environment variables for your account", then delete `GEMINI_API_KEY`.

## 5. Start the portal

```
python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
```

Then open **http://127.0.0.1:8900** in Chrome. Leave the terminal window open: closing it stops Solara.

You can also double-click **`run.bat`**. It installs anything missing, then starts Solara.

### Signing in

- **Demo setup (the default):** sign in as `r.deshmukh` with the password `demo`. Two other accounts, `s.kale` (operator) and `a.more` (viewer), are listed on the sign-in page.
- **Live setup (`SOLARA_MODE=live`), first time only:** the sign-in page asks you to create the supervisor's name, username and password. Add everyone else later in Reports, then People.

### Where the data lives

- **Customers, documents and backups:** the `data\` folder.
- **The encryption key:** `data\vault.key`. It is the only way to open the documents. Keep a copy somewhere safe, away from the backups.
- **Another folder:** to use a different data folder, set `SOLARA_DATA` before starting:

  ```
  set SOLARA_DATA=D:\solara-data
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
  ```

- **The desktop app's customers:** `run_web.bat` runs this code on the desktop app's data (`%APPDATA%\solara-desktop\data`). Close the desktop app first; only one Solara can run at a time.

## 6. Connect the Chrome helper (co-pilot)

The helper fills the government portals for you.

1. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**.
2. Choose the `extension` folder inside this project.
3. Open Solara, then the account menu (your name, top right), then **Connect the Chrome extension**.

## 7. Documents Solara makes

- **The agreement:** made from the PDF in `agreement draft\`.
- **The quotation:** made from the Word file in `Quoatation (all range)\` that matches the installation cost.

Both folders ship with the code. To use copies kept somewhere else, set `SOLARA_AGREEMENT_DIR` and `SOLARA_QUOTES_DIR` in `.env`.

## 8. Using the portal

- **Today:** what to do now, top line first.
- **Registration:**
  - Add a customer and upload the bill and the Aadhaar. The details fill themselves, and changes save as you type.
  - Download the agreement and the quotation.
- **Installation and Close-out:** the steps after the agreement.
- **Shortcuts:**
  - Press **/** to search the customer list.
  - The address bar remembers the screen and the customer (for example `#reg/SS-2051`), so refresh, Back and shared links open the same place.
- **Light or dark:** in the account menu.

## 9. Check that everything works (optional)

The tests reset the data they run on, so run them on a throwaway folder and **never on your real `data\`**. Stop any running Solara first, since the tests use port 8900.

In one window:

```
set SOLARA_DATA=%TEMP%\solara-test
set SOLARA_USE_AI=0
python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
```

In a second window, set the same two lines, then run:

```
set SOLARA_DATA=%TEMP%\solara-test
set SOLARA_USE_AI=0
python tests\run_all.py
```

## When something goes wrong

| What you see | What to do |
|---|---|
| `address already in use` / port 8900 busy | Solara (or the desktop app) is already running. Close it, or use `--port 8901` and open http://127.0.0.1:8901 |
| "Gemini did not answer" next to a document | Check the keys in `.env` and the old Windows variable (step 4), then press **Read again** |
| "Model off" | `SOLARA_USE_AI=1` or `GEMINI_API_KEY` is missing from `.env`. Restart Solara after editing `.env` |
| Quotation PDF does not download | Microsoft Word is not installed. Download the Word version instead |
| A code change does not show | Restart Solara for Python changes. For page changes, refresh the browser (Ctrl+F5) |
| Fonts look plain | The page loads its fonts from Google Fonts. Offline, it uses the Windows font, and everything still works |
