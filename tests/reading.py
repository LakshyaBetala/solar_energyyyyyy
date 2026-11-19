"""Reading the Aadhaar and the electricity bill, with the AI model switched on.

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/reading.py                        (in another)

The model is a stand-in here (no key, nothing leaves the computer): the test checks what Solara does around
it. The rules:
- an Aadhaar whose QR code reads in full is never sent to the model;
- a card with no readable QR goes to it, the number comes back masked, the full number is kept only encrypted;
- SOLARA_AI_AADHAAR=0 keeps every card on the computer;
- a bill that is a photo (no text to read) is read by the model; what it was unsure of is flagged for the owner;
- one model call per version of a document; a model that fails leaves the document as "not read", never a crash.
Synthetic documents only.
"""
import asyncio, io, os, sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, "."); sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import db, extract, closeout, registration, vault  # noqa: E402
import fixtures as fx  # noqa: E402
from milestone4 import client  # noqa: E402

PASS, FAIL = [], []
FULL = "999941057058"   # passes the Aadhaar check digit; not a real person's number
CALLS, BREAK = [], []
sure = lambda v, ok=True: {"value": v, "sure": ok}
REPLY = {
    "aadhaar": {"aadhaar_name": sure(fx.AADHAAR_NAME), "aadhaar_gender": sure("Female"), "aadhaar_dob": sure("14-03-1981"),
                "aadhaar_address": sure("B-12 Sai Shraddha Society, Manchar"), "aadhaar_pin": sure("410503"),
                "aadhaar_district": sure("Pune"), "aadhaar_number": sure("9999 4105 7058")},
    "bill": {"consumer_no": sure(fx.NEW["consumer_no"]), "bill_name": sure(fx.NEW["billed_name"], False),
             "address": sure(fx.NEW["address"], False), "pin": sure(fx.NEW["pin"]), "bill_mobile": sure(fx.NEW["msisdn"]),
             "sanctioned_load": sure("5"), "bill_district": sure("Pune")},
}


async def stand_in(kind, st, text=None, images=None):
    CALLS.append(kind)
    if kind in BREAK:
        raise TimeoutError("the model did not answer")
    return REPLY.get(kind, {})


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def photo(words):
    im = Image.new("RGB", (1400, 900), (245, 244, 238))
    ImageDraw.Draw(im).text((60, 60), words, fill=(20, 20, 20))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def read(cid, kind):
    """Read the documents again in this process, where the model is the stand-in. Returns the rows by key."""
    asyncio.run(extract.run(cid, fresh=kind))
    return {extract.KEY_OF.get(r["field"]): r for r in extract.saved(cid)}


def main():
    sup = client("r.deshmukh")
    cid = sup.post("/api/customers", json={"name": "Reading Check"}).json()["customer"]["id"]
    up = lambda kind, name, blob: sup.post(f"/api/registration/{cid}/document?kind={kind}", files={"file": (name, blob, "image/jpeg")}).raise_for_status()
    extract.llm_status = lambda: {"enabled": True, "provider": "gemini", "model": "stand-in"}
    extract.llm_read = stand_in
    os.environ.pop("SOLARA_AI_AADHAAR", None)

    print("\n  -- the Aadhaar")
    up("aadhaar", "aadhaar.jpg", fx.aadhaar_photo())
    rows = read(cid, "aadhaar")
    check("a card whose QR code reads in full is never sent to the model",
          "aadhaar" not in CALLS and rows["aadhaar_name"]["source"] == "Aadhaar QR" and rows["aadhaar_masked"]["value"] == "XXXX XXXX 4471",
          f"{CALLS} {rows['aadhaar_name']['source']}")
    check("...and nothing but the last 4 digits of its number is kept", not closeout.data(cid)[1].get("aadhaar_enc"))

    up("aadhaar", "aadhaar.jpg", fx.aadhaar_photo(qr=False))          # the same card, photographed without its QR
    rows = read(cid, "aadhaar")
    check("a card with no readable QR goes to the model, once", CALLS.count("aadhaar") == 1, str(CALLS))
    check("...name, gender, date of birth, address, PIN and district are read",
          rows["aadhaar_name"]["value"] == fx.AADHAAR_NAME and rows["aadhaar_pin"]["value"] == "410503"
          and rows["aadhaar_district"]["value"] == "Pune" and "gemini" in rows["aadhaar_name"]["source"]
          and registration.values(cid)["gender"] == "Female", str({k: v["value"] for k, v in rows.items() if k}))
    sealed = closeout.data(cid)[1].get("aadhaar_enc")
    check("...the number is shown masked; the full number is kept only encrypted",
          rows["aadhaar_masked"]["value"] == "XXXX XXXX 7058" and bool(sealed) and vault.unseal(sealed) == FULL and FULL not in sealed)
    check("...and it is in no reading, no audit line and no log of what was read",
          not db.q("SELECT 1 FROM extractions WHERE value LIKE ? OR note LIKE ?", (f"%{FULL}%", f"%{FULL}%"))
          and not db.q("SELECT 1 FROM audit WHERE detail LIKE ?", (f"%{FULL}%",)))
    read(cid, None)
    check("the same document is not sent a second time", CALLS.count("aadhaar") == 1, str(CALLS))

    os.environ["SOLARA_AI_AADHAAR"] = "0"
    extract._LLM_CACHE.clear()
    rows = read(cid, "aadhaar")
    check("SOLARA_AI_AADHAAR=0: the card stays on the computer and is shown as not read, for the owner to type",
          CALLS.count("aadhaar") == 1 and "aadhaar_unread" in rows, f"{CALLS} {[k for k in rows if k]}")
    os.environ.pop("SOLARA_AI_AADHAAR")

    print("\n  -- the electricity bill")
    up("bill", "bill.jpg", photo("MSEDCL bill, photographed: no text a rule can read"))
    rows = read(cid, "bill")
    c = db.one("SELECT * FROM customers WHERE id=?", (cid,))
    check("a bill that is a photo is read by the model: consumer number, address, PIN, load, mobile",
          "bill" in CALLS and rows["consumer_no"]["value"] == fx.NEW["consumer_no"] and c["consumer_no"] == fx.NEW["consumer_no"]
          and c["pin"] == fx.NEW["pin"] and closeout.data(cid)[1].get("sanctioned_load") in ("5", "5.0"),
          f"{CALLS} consumer={rows.get('consumer_no', {}).get('value')} / {c['consumer_no']} pin={c['pin']} load={closeout.data(cid)[1].get('sanctioned_load')}")
    check("what the model was not sure of is flagged for the owner to check, not taken as read",
          rows["address"]["status"] == "review" and "not sure" in (rows["address"]["note"] or ""), str(rows["address"])[:200])
    check("...and registration waits for that check", any(i["field"] == rows["address"]["field"] for i in registration.validate(cid)["issues"]))

    BREAK.append("bill")
    up("bill", "bill.jpg", photo("another photo of the bill"))
    rows = read(cid, "bill")
    check("a model that does not answer leaves the bill as 'not read' with what to do; nothing crashes",
          "bill_unread" in rows and extract.MODEL_STATE.get((cid, "bill")) == "TimeoutError", str([k for k in rows if k]))

    print("\n  -- the Aadhaar as two files, and the PAN card")
    import fitz
    def pdf_of(image=None, words=None):
        d = fitz.open(); pg = d.new_page()
        if image:
            pg.insert_image(pg.rect, stream=image)
        if words:
            pg.insert_text((72, 100), words, fontsize=14)
        return d.tobytes()
    two = [("file", ("front.pdf", pdf_of(words="Government of India (front, no QR here)"), "application/pdf")),
           ("file", ("back.pdf", pdf_of(image=fx.aadhaar_photo()), "application/pdf"))]
    r = sup.post(f"/api/registration/{cid}/document?kind=aadhaar", files=two)
    doc = db.one("SELECT * FROM documents WHERE customer_id=? AND kind='aadhaar'", (cid,))
    pages = fitz.open(stream=vault.read(Path(doc["path"])), filetype="pdf").page_count if doc else 0
    rows = read(cid, "aadhaar")
    check("the Aadhaar is taken as two PDFs, front and back, kept as one two-page file",
          r.status_code == 200 and pages == 2, f"{r.status_code} {r.text[:80]} pages={pages}")
    check("...and read from the QR on the back page, on the computer", rows["aadhaar_name"]["source"] == "Aadhaar QR" and rows["aadhaar_masked"]["value"] == "XXXX XXXX 4471")
    mixed = [("file", ("front.jpg", photo("front of the card"), "image/jpeg")), ("file", ("back.pdf", pdf_of(image=fx.aadhaar_photo()), "application/pdf"))]
    check("a photo and a PDF together work too", sup.post(f"/api/registration/{cid}/document?kind=aadhaar", files=mixed).status_code == 200)
    three = two + [("file", ("extra.pdf", pdf_of(words="x"), "application/pdf"))]
    check("three files are refused", sup.post(f"/api/registration/{cid}/document?kind=aadhaar", files=three).status_code == 400)

    before = len(CALLS)
    sup.post(f"/api/registration/{cid}/document?kind=pan", files={"file": ("pan.pdf", pdf_of(words="INCOME TAX DEPARTMENT  Permanent Account Number  ABCPK1234F  Name PRIYA KULKARNI  Date of Birth 14/03/1981"), "application/pdf")}).raise_for_status()
    rows = read(cid, "pan")
    d = closeout.data(cid)[1]
    check("a PAN card as a PDF: the number is read from it without the model",
          rows["pan_number"]["value"] == "ABCPK1234F" and "pan" not in CALLS[before:] and d.get("pan") == "ABCPK1234F", str(rows.get("pan_number"))[:120])
    check("...and only the number is kept from the card: no name, no date of birth",
          [k for k in rows if k and k.startswith("pan")] == ["pan_number"] and registration.values(cid)["pan"] == "ABCPK1234F")
    REPLY["pan"] = {"pan_number": sure("AAAPZ 9999 Q"), "name": sure("SOMEONE"), "dob": sure("01/01/1990")}
    sup.put(f"/api/registration/{cid}", json={"pan": ""}).raise_for_status()
    png = io.BytesIO(); Image.new("RGB", (900, 560), (225, 235, 245)).save(png, "PNG")
    sup.post(f"/api/registration/{cid}/document?kind=pan", files={"file": ("pan.png", png.getvalue(), "image/png")}).raise_for_status()
    rows = read(cid, "pan")
    check("a PAN card as a PNG photo is read by the model, which is asked for the number only",
          rows["pan_number"]["value"] == "AAAPZ9999Q" and CALLS[before:].count("pan") == 1 and "pan_number" in extract.PROMPTS["pan"][1]
          and "name" not in extract.PROMPTS["pan"][1].replace("nothing else", ""), str(rows.get("pan_number"))[:120])
    REPLY["pan"] = {"pan_number": sure("NOT A PAN")}
    png2 = io.BytesIO(); Image.new("RGB", (910, 560), (225, 235, 245)).save(png2, "PNG")
    sup.post(f"/api/registration/{cid}/document?kind=pan", files={"file": ("pan.png", png2.getvalue(), "image/png")}).raise_for_status()
    rows = read(cid, "pan")
    check("something that is not a PAN is never saved as one; the card shows as not read",
          "pan_number" not in rows and "pan_unread" in rows, str([k for k in rows if k and k.startswith("pan")]))
    check("the PAN card is optional: an unread one does not hold registration back",
          not any("PAN" in i["field"] for i in registration.validate(cid)["issues"]))
    r1 = sup.put(f"/api/registration/{cid}", json={"pan": "abcpk 1234 f"})
    r2 = sup.put(f"/api/registration/{cid}", json={"pan": "12345"})
    check("the owner can type the PAN instead; a wrong one is refused", r1.status_code == 200 and closeout.data(cid)[1]["pan"] == "ABCPK1234F" and r2.status_code == 400, f"{r1.status_code} {r2.status_code}")

    print("\n  -- the AI key, set in the app")
    s = sup.get("/api/settings/ai").json()
    check("the settings say whether a key is set, never the key itself", set(s) == {"on", "provider", "model", "has_key", "tail", "aadhaar"} and len(s["tail"]) <= 4, str(s))
    check("only the owner or a supervisor sets the key", client("s.kale").post("/api/settings/ai", json={"key": "A" * 39}).status_code == 403)
    check("something that is not a key is refused before anything is saved",
          sup.post("/api/settings/ai", json={"key": "not a key!"}).status_code == 400 and sup.get("/api/settings/ai").json() == s)

    sup.delete(f"/api/customers/{cid}").raise_for_status()
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
