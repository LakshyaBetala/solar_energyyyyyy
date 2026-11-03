from pathlib import Path

import os
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("SOLARA_DATA") or ROOT / "data")  # a live install keeps its own folder
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

MAX_UPLOAD_KB = 300  # MSEDCL rooftop portal: PDF only, 300 KB per file


def live():
    """SOLARA_MODE=live: no demo data, and the links open the real portals."""
    import os
    return os.environ.get("SOLARA_MODE", "").lower() == "live"


def portals():
    if live():
        return {"pmsg": "https://pmsuryaghar.gov.in/", "pmsg_vendor": "https://pmsuryaghar.gov.in/",
                "msedcl": "https://rts.mahadiscom.in/RoofTopSolarVendor/"}
    return {"pmsg": "/portal/verify", "pmsg_vendor": "/pmsg/vendor/consent", "msedcl": "/msedcl/"}


def region():
    """What the installer always picks on the portals: their state and distribution company."""
    import os
    return {"state": os.environ.get("SOLARA_STATE", "Maharashtra"),
            "discom": os.environ.get("SOLARA_DISCOM", "Maharashtra State Electricity Distribution Co. Ltd.")}


def vendor():
    """The installer named on generated documents, from .env (read late: .env loads after
    this module). The public repo never carries a client's identity."""
    import os
    return {"name": os.environ.get("SOLARA_VENDOR_NAME", "Demo Solar Solutions Pvt Ltd"),
            "signatory": os.environ.get("SOLARA_VENDOR_SIGNATORY", "Authorised Signatory")}
