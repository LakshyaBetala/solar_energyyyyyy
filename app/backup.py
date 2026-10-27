"""Backups: a consistent snapshot of the database plus the encrypted documents and evidence.

  python -m app.backup

The database is copied with SQLite's online backup API, so it is consistent even while
the server is running. Documents and screenshots go into the archive still encrypted.
The vault key is deliberately NOT included: a backup that carries its own key protects
nothing. Keep data/vault.key somewhere else (a password manager, a sealed USB stick).

Restore: stop the server, unzip into data/, put vault.key back in data/, start the server.
"""
import sqlite3, tempfile, zipfile
from datetime import datetime
from pathlib import Path
from . import db
from .config import DATA, DOCS, SHOTS

BACKUPS = DATA / "backups"


def create():
    BACKUPS.mkdir(parents=True, exist_ok=True)
    out = BACKUPS / f"solara_{datetime.now():%Y%m%d_%H%M%S}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "solara.db"
        dst = sqlite3.connect(snap)
        with db._lock:
            db.conn().backup(dst)
        dst.close()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "solara.db")
            for root in (DOCS, SHOTS):
                for f in root.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(DATA).as_posix())
            z.writestr("RESTORE.txt",
                       "Stop the server, unzip this archive into the data folder, copy vault.key "
                       "back into it, then start the server.\n"
                       "Documents and screenshots in this archive are encrypted; without the "
                       "matching vault.key they cannot be read.\n")
    return out


if __name__ == "__main__":
    p = create()
    print(f"backup written: {p}  ({p.stat().st_size // 1024} KB)")
    print(f"remember: keep {DATA / 'vault.key'} somewhere other than this backup")
