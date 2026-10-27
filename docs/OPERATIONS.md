# Solara — operations guide

For whoever looks after Solara in the office: starting and stopping it, users, backups and
restore, the encryption key, and what to do when something goes wrong.

---

## Starting and stopping

| | |
|---|---|
| Start | double-click `run.bat`, or `python -m uvicorn app.main:app --host 127.0.0.1 --port 8900` |
| Stop | close the window, or press `Ctrl+C` in it |
| Open | <http://127.0.0.1:8900> |

Stopping while an agent run is open is safe. On the next start, the run is closed out and
recorded in the audit trail as "Run closed on restart". Nothing is submitted.

Signed-in sessions survive a restart. Nobody has to sign in again.

---

## Where everything lives

```
data/
  solara.db          database: customers, runs, checkpoints, audit, sessions
  vault.key          THE ENCRYPTION KEY — see below
  documents/         customer documents, encrypted
  screenshots/       run evidence, encrypted
  exports/           Excel and PDF exports as they are generated
  backups/           zip backups
  portal_uploads/    files received by the sandbox portals (demo only)
```

---

## The encryption key

`data/vault.key` decrypts every document and screenshot. **Without it they cannot be read, and
there is no way to recover it.**

- Keep a copy somewhere other than this PC: a password manager, or a sealed USB stick in a drawer.
- Never email it, and never keep it in the same place as the backups.
- To supply the key from outside instead of a file, set the environment variable
  `SOLARA_VAULT_KEY` before starting.
- If the key is lost, the documents are gone. Re-collect them from the customers.

---

## Backups

**From the console:** sign in as a supervisor → **Reports** → **Create a backup**. The zip
downloads and a copy stays in `data/backups/`.

**From the command line:** `python -m app.backup`

What is in a backup: a consistent snapshot of the database (safe to take while Solara is running),
and every document and screenshot, still encrypted. What is **not** in it: `vault.key`. That is
deliberate, because a backup that carries its own key protects nothing.

Suggested routine: one backup a day, copied off the PC, with the last 7 kept.

### Restore

1. Stop Solara.
2. Rename the current `data/` folder to `data-old/`.
3. Create a new `data/` folder and unzip the backup into it.
4. Copy `vault.key` into `data/`.
5. Start Solara and open a customer document to confirm it decrypts.

---

## Users and roles

| Role | Can |
|---|---|
| viewer | read everything; change nothing |
| operator | run the agent, answer OTP / CAPTCHA / corrections, upload documents, manage numbers |
| supervisor | everything an operator can, plus approve filings, create backups, reset |

The demo ships three accounts with the password `demo`. **Before real use, change every password**
and create named accounts per person, so the audit trail says who did what. User management in the
console is part of the delivery scope; until then, passwords are set with:

```bash
python -c "from app import db; db.ex('UPDATE users SET pw=? WHERE username=?', (db.pwhash('NEW-PASSWORD'), 'r.deshmukh'))"
```

---

## The audit trail

Every sign-in, extraction, document view, run start, checkpoint decision, refused attempt,
approval, filing, export and backup is written to the audit table by the server. It is append-only
from the application's side. Export it from **Audit Trail → Download Excel**.

---

## When something goes wrong

| Symptom | Do this |
|---|---|
| A run fails with a portal error | Open the run's PDF report. The last screenshot shows the page the portal returned. If the portal moved a field, the field map needs updating (maintenance). |
| A run waits forever on a checkpoint | Someone needs to answer it. **Reopen** in the run console shows the dialog again; **Abandon** stops the run without submitting. |
| "requires the supervisor role" | The person signed in is not a supervisor. Sign in as one. |
| A document will not open (`InvalidToken`) | The `vault.key` in `data/` is not the key the file was encrypted with. Restore the correct key. |
| The console will not load | Check the Solara window is still running. Restart it. |
| Port 8900 busy | `netstat -ano \| findstr :8900`, then `taskkill /F /PID <pid>`, then start again. |

---

## Resetting the demo

**Reports → Reset the demo environment**, or `python -m app.reset`. It clears runs, evidence,
portal filings and messages, and restores the sample customers and numbers. It does not touch
documents, extractions, users or the key.
