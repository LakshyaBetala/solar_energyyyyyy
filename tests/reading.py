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
    "aadhaar": {"aadhaar_name": sure(fx.AADHAAR_NAME), "aadhaar_gender": sure("F"), "aadhaar_dob": sure("14-03-1981"),
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
          and c["pin"] == fx.NEW["pin"] and closeout.data(cid)[1].get("sanctioned_load") in ("5", "5.0"), str(CALLS))
    check("what the model was not sure of is flagged for the owner to check, not taken as read",
          rows["address"]["status"] == "review" and "not sure" in (rows["address"]["note"] or ""), str(rows["address"])[:200])
    check("...and registration waits for that check", any(i["field"] == rows["address"]["field"] for i in registration.validate(cid)["issues"]))

    BREAK.append("bill")
    up("bill", "bill.jpg", photo("another photo of the bill"))
    rows = read(cid, "bill")
    check("a model that does not answer leaves the bill as 'not read' with what to do; nothing crashes",
          "bill_unread" in rows and extract.MODEL_STATE.get((cid, "bill")) == "TimeoutError", str([k for k in rows if k]))

    sup.delete(f"/api/customers/{cid}").raise_for_status()
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
