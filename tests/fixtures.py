"""Realistic test documents for a brand-new customer, generated on the fly. Synthetic data only.

- a bill PDF with a text layer, like the one downloaded from the DISCOM website
- an Aadhaar card photo whose QR follows the UIDAI Secure QR layout (V2, gzip, 0xFF fields)
- a passbook photo (an image, so it has no text layer)
"""
import gzip, io, os, sys
import qrcode
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, ".")
from app import db  # noqa: E402

NEW = {"consumer_no": "170055501234", "billed_name": "PRIYA S KULKARNI",
       "address": "B-12 SAI SHRADDHA SOCIETY MANCHAR AMBEGAON", "pin": "410503",
       "sanctioned_load": 5.0, "tariff": "LT-I RES", "msisdn": "9028144599", "avg_units": 330,
       "meter_no": "MSEDCL/9008812"}
AADHAAR_NAME = "Priya Sanjay Kulkarni"


def register_consumer():
    """Put the consumer in the sandbox DISCOM register, as the real one already holds them."""
    db.ex("""INSERT OR REPLACE INTO portal_consumers(consumer_no,billed_name,address,pin,
             sanctioned_load,tariff,msisdn,avg_units,meter_no) VALUES(?,?,?,?,?,?,?,?,?)""",
          tuple(NEW[k] for k in ("consumer_no", "billed_name", "address", "pin", "sanctioned_load",
                                 "tariff", "msisdn", "avg_units", "meter_no")))


async def bill_pdf(page):
    from app.docs_gen import bill_html
    await page.set_content(bill_html({}, NEW))
    return await page.pdf(format="A4")


def aadhaar_photo(name=AADHAAR_NAME, qr=True):
    sys.set_int_max_str_digits(0)
    fields = ["V2", "3", "4471" + "20190101123456789", name, "14-03-1981", "F", "W/O Sanjay Kulkarni",
              "Pune", "Near Ganpati Mandir", "B-12 Sai Shraddha Society", "Manchar", "410503",
              "Manchar", "Maharashtra", "Pune Nashik Road", "Ambegaon", "Manchar"]
    payload = b"\xff".join(f.encode() for f in fields) + b"\xff" + os.urandom(900) + os.urandom(256)
    card = Image.new("RGB", (1500, 860), (238, 234, 224))
    d = ImageDraw.Draw(card)
    d.rectangle([40, 40, 1460, 820], outline=(180, 60, 40), width=6)
    d.text((80, 90), "GOVERNMENT OF INDIA (synthetic test card)", fill=(30, 30, 30))
    d.text((80, 140), name, fill=(10, 10, 10))
    if qr:
        q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=4)
        q.add_data(str(int.from_bytes(gzip.compress(payload), "big")), optimize=0)
        q.make(fit=True)
        card.paste(q.make_image().convert("RGB"), (800, 110))
    photo = card.rotate(3, expand=True, fillcolor=(120, 110, 100)).filter(ImageFilter.GaussianBlur(0.7))
    buf = io.BytesIO()
    photo.save(buf, "JPEG", quality=78)
    return buf.getvalue()


def passbook_photo():
    im = Image.new("RGB", (1200, 800), (250, 250, 245))
    ImageDraw.Draw(im).text((60, 60), "BANK PASSBOOK  Account Holder PRIYA S KULKARNI  "
                                      "A/c 60123456789  IFSC MAHB0000412", fill=(0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def label_photo(serial, kind="module", code=True):
    """A phone photo of a panel's (or inverter's) rating label: barcode of the serial, printed
    text, slightly rotated, on the grey back sheet. Synthetic."""
    import numpy as np
    import zxingcpp
    back = Image.new("RGB", (1200, 900), (128, 134, 140))
    card = Image.new("RGB", (860, 520), (250, 250, 247))
    d = ImageDraw.Draw(card)
    d.text((30, 24), ("PV MODULE  550 Wp  MONO PERC (synthetic)" if kind == "module" else "GRID-TIE INVERTER 5 kW (synthetic)"),
           fill=(0, 0, 0))
    if code:
        bc = zxingcpp.create_barcode(serial, zxingcpp.BarcodeFormat.Code128).to_image(scale=4)
        card.paste(Image.fromarray(np.array(bc)).convert("RGB").resize((760, 170)), (50, 90))
    d.text((50, 300), f"S/N: {serial}", fill=(0, 0, 0))
    d.text((50, 340), "Voc 49.8V  Isc 14.0A  Made in India", fill=(0, 0, 0))
    back.paste(card, (170, 190))
    photo = back.rotate(4, fillcolor=(120, 126, 132)).filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    photo.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def site_photo_without_gps():
    """The installed system, as a phone hands it to a web page with GPS stripped."""
    im = Image.new("RGB", (1600, 1200), (150, 190, 225))
    d = ImageDraw.Draw(im)
    d.polygon([(0, 700), (1600, 600), (1600, 1200), (0, 1200)], fill=(160, 105, 75))
    for k in range(3):
        d.rectangle([300 + k * 360, 640, 620 + k * 360, 800], fill=(29, 47, 85), outline=(200, 210, 220), width=5)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def browser_profile():
    """A fresh Chrome profile with the password manager off: its "Save password?" prompt, shown
    after a portal login, takes the tab's mouse input in a headless run."""
    import json, tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "Default").mkdir()
    (d / "Default" / "Preferences").write_text(json.dumps(
        {"credentials_enable_service": False, "profile": {"password_manager_enabled": False}}))
    return str(d)
