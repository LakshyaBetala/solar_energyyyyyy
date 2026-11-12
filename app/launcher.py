"""Solara on the owner's own Windows computer: one double-click on Solara.exe.

Starts Solara if it is not already running, opens it in the default browser, and keeps a daily
backup (app.upkeep). Settings live in `solara.env` beside the exe (the same lines as .env.example);
the data lives in the `data` folder beside it unless SOLARA_DATA says otherwise.

  python -m app.launcher            the same thing without the exe
  pyinstaller solara.spec           builds dist/Solara/Solara.exe (docs/RUNNING.md)
"""
import os, socket, sys, threading, time, webbrowser
from pathlib import Path

PORT = 8900
URL = f"http://127.0.0.1:{PORT}/"


def home():
    """The folder the owner sees: beside the exe, or the project folder when run from source."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def read_env(path):
    """KEY=VALUE lines; the computer's own environment wins over the file."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def running():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main():
    here = home()
    if running():  # a second double-click only opens the page
        webbrowser.open(URL)
        return
    read_env(here / "solara.env")
    os.environ.setdefault("SOLARA_DATA", str(here / "data"))
    log = Path(os.environ["SOLARA_DATA"]) / "logs"
    log.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):  # no console window: what would have been printed goes to a file
        sys.stdout = sys.stderr = open(log / f"solara_{time.strftime('%Y%m%d')}.log", "a", encoding="utf-8", buffering=1)
    import uvicorn
    from app.main import app  # after SOLARA_DATA is set: config reads it on import
    threading.Thread(target=lambda: (time.sleep(2.5), webbrowser.open(URL)), daemon=True).start()
    # 127.0.0.1 only: the office reaches it through the HTTPS proxy in OPERATIONS.md, never directly
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
