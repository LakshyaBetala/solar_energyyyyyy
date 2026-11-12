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


async def pdf_browser(p):
    """A headless browser for printing PDFs: Playwright's own Chromium when installed (development,
    the server), otherwise the Chrome or Edge already on the owner's computer (Solara.exe)."""
    try:
        return await p.chromium.launch()
    except Exception:
        for channel in ("chrome", "msedge"):
            try:
                return await p.chromium.launch(channel=channel)
            except Exception:
                pass
        raise


def live():
    """SOLARA_MODE=live: no demo data, and the links open the real portals."""
    import os
    return os.environ.get("SOLARA_MODE", "").lower() == "live"


def portals():
    if live():
        # the national portal's logins live on their own hosts (seen on the live site, Nov 2026)
        return {"pmsg": "https://consumer.pmsuryaghar.gov.in/consumer/#/login",
                "pmsg_vendor": "https://vendor.pmsuryaghar.gov.in/vendor/#/login",
                "pmsg_apps": "https://vendor.pmsuryaghar.gov.in/vendor/#/login",
                "msedcl": "https://rts.mahadiscom.in/RoofTopSolarVendor/",
                "dcr": "https://solardcrportal.nise.res.in/", "jansamarth": "https://www.jansamarth.in/"}
    return {"pmsg": "/portal/verify", "pmsg_vendor": "/pmsg/vendor/consent", "pmsg_apps": "/pmsg/vendor/applications",
            "msedcl": "/msedcl/", "dcr": "/dcr/", "jansamarth": "/jansamarth/"}


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
            "signatory": os.environ.get("SOLARA_VENDOR_SIGNATORY", "Authorised Signatory"),
            # the demo shows a placeholder so the customer page's help line is visible; live uses the real one or none
            "phone": os.environ.get("SOLARA_VENDOR_PHONE") or ("" if live() else "+91 90000 00000")}


def public_url(request, path):
    """A link the customer opens on their own phone. SOLARA_PUBLIC_URL is Solara's internet address
    (for example https://solara.example.in); without it the link uses the address this request came in on."""
    import os
    base = (os.environ.get("SOLARA_PUBLIC_URL") or str(request.base_url)).rstrip("/")
    return base + path


def is_local(url):
    """True when a link would open only on this computer or this office network, never on a customer's phone."""
    import ipaddress
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host in ("localhost", "") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False
