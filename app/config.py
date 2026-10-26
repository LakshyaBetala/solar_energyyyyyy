from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = DATA / "documents"
SHOTS = DATA / "screenshots"
EXPORTS = DATA / "exports"
WEB = ROOT / "web"

for d in (DATA, DOCS, SHOTS, EXPORTS):
    d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA / "solara.db"

HOST = "127.0.0.1"
PORT = 8900
BASE_URL = f"http://{HOST}:{PORT}"
PORTAL_URL = f"{BASE_URL}/portal"

# The agent window: headless streams frames into the dashboard, headful also opens a
# real Chromium window beside it. Both are genuine browser sessions.
HEADLESS_DEFAULT = True
FRAME_INTERVAL = 0.45
FRAME_QUALITY = 55

ROLES = {"viewer": 0, "operator": 1, "supervisor": 2}
