"""Document extraction.

Reads the customer's documents on disk, whatever they arrived as (a PDF with text, a
scanned PDF, or a phone photo), and turns them into fields:

- Electricity bill and bank page: labelled regexes on the PDF text layer. If the text layer
  is missing or the regexes find little, and a model key is configured, the page is read by
  the model, which must say how sure it is; anything it is unsure of is flagged.
- Aadhaar: read from the card's QR code, offline, with no model involved. The QR carries
  the name, date of birth, gender and address, and only the last 4 digits of the number.

Then cross-document rules (name agreement, PIN agreement, duplicate consumer number) score
the fields. Nothing is guessed: a value that could not be read is flagged for a person.
Values that are read cleanly fill the customer record; flagged ones fill it once confirmed.
"""
import base64, gzip, io, re, os, json, difflib, asyncio, sys, zlib
from pathlib import Path
from pypdf import PdfReader
from . import db, vault, valid
from .config import ROOT

ENV_FILE = ROOT / ".env"


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


def llm_status():
    """AI is off unless SOLARA_USE_AI=1 is set AND a key is present. Reading a bill's text, the
    Aadhaar QR, validation and every other basic task are plain rules and never call a model."""
    load_env()
    if os.environ.get("SOLARA_USE_AI", "").lower() not in ("1", "true", "yes"):
        return {"enabled": False, "provider": None, "model": None}
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {"enabled": True, "provider": "anthropic",
                "model": os.environ.get("SOLARA_MODEL", "claude-sonnet-5-5")}
    if os.environ.get("OPENAI_API_KEY"):
        return {"enabled": True, "provider": "openai",
                "model": os.environ.get("SOLARA_MODEL", "gpt-4.1-mini")}
    return {"enabled": False, "provider": None, "model": None}


# ------------------------------- reading files -------------------------------
def pdf_text(path):
    try:
        reader = PdfReader(io.BytesIO(vault.read(Path(path))))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        return f"__unreadable__ {e}"


def read_doc(path):
    """(text layer, page images as PIL images, problem). Photos have no text layer; scanned
    PDFs have no usable one."""
    from PIL import Image
    raw = vault.read(Path(path))
    if raw.startswith(b"%PDF"):
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                return "", [], ("this PDF is password-protected (e-Aadhaar is). Send a photo "
                                "or a screenshot of it instead")
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            return "", [], f"the PDF could not be opened ({type(e).__name__})"
        import fitz
        doc = fitz.open(stream=raw, filetype="pdf")
        imgs = [Image.frombytes("RGB", (px.width, px.height), px.samples)
                for px in (doc[i].get_pixmap(dpi=200) for i in range(min(2, doc.page_count)))]
        return text, imgs, None
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        return "", [im.convert("RGB")], None
    except Exception:
        return "", [], "this file is neither a PDF nor a photo Solara can open (send JPG, PNG or PDF)"


# ------------------------------- Aadhaar QR -------------------------------
QR_FIELDS = ["indicator", "reference", "name", "dob", "gender", "care_of", "district", "landmark",
             "house", "location", "pin", "post_office", "state", "street", "sub_district", "vtc"]


def parse_secure_qr(digits):
    """UIDAI Secure QR: a decimal number whose bytes are a gzip stream of 0xFF-separated
    fields, optionally led by a version such as "V2". The reference starts with the last 4
    digits of the Aadhaar number; the full number is never in it.
    shortcut: the UIDAI signature at the end is not verified; add it if a document's
    authenticity is ever disputed."""
    sys.set_int_max_str_digits(max(sys.get_int_max_str_digits(), 20000))
    n = int(digits)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    try:
        data = gzip.decompress(raw)
    except OSError:
        data = zlib.decompress(raw)
    parts = [p.decode("iso-8859-1").strip() for p in data.split(b"\xff")]
    if parts and parts[0].startswith("V"):
        parts = parts[1:]
    f = dict(zip(QR_FIELDS, parts))
    f["last4"] = f.get("reference", "")[:4]
    return f


def parse_xml_qr(text):
    """Older printed Aadhaar QR: an XML element with attributes, including the full number,
    of which only the last 4 digits are kept."""
    a = dict(re.findall(r'(\w+)="([^"]*)"', text))
    return {"name": a.get("name", ""), "dob": a.get("dob") or a.get("yob", ""),
            "gender": a.get("gender", ""), "care_of": a.get("co", ""), "house": a.get("house", ""),
            "street": a.get("street", ""), "landmark": a.get("lm", ""), "location": a.get("loc", ""),
            "vtc": a.get("vtc", ""), "district": a.get("dist", ""), "state": a.get("state", ""),
            "pin": a.get("pc", ""), "last4": re.sub(r"\D", "", a.get("uid", ""))[-4:]}


def aadhaar_qr(images):
    import zxingcpp
    for im in images:
        for candidate in (im, im.convert("L")):
            for r in zxingcpp.read_barcodes(candidate):
                t = r.text.strip()
                try:
                    if t.isdigit() and len(t) > 200:
                        return parse_secure_qr(t)
                    if "PrintLetterBarcodeData" in t:
                        return parse_xml_qr(t)
                except Exception:
                    continue
    return None


def qr_address(q):
    parts, seen = [], set()
    for k in ("house", "street", "landmark", "location", "vtc", "post_office", "sub_district",
              "district", "state"):
        v = (q.get(k) or "").strip(" ,")
        if v and v.lower() not in seen:
            parts.append(v)
            seen.add(v.lower())
    return ", ".join(parts)


# ------------------------------- labelled regexes -------------------------------
LABELS = {
    "consumer_no": (r"Consumer\s*(?:Number|No\.?)\s*:?\s*([0-9]{8,14})", 99),
    "bill_name": (r"Consumer\s*Name\s*:?\s*([A-Z][A-Z .&'\-]{3,60})", None),
    "tariff": (r"Tariff\s*Category\s*([A-Z0-9\- ]{3,24})", 97),
    "sanctioned_load": (r"Sanctioned\s*Load\s*:?\s*([0-9.]+)\s*KW", 98),
    "meter_no": (r"Meter\s*Number\s*([A-Z/0-9]{6,24})", 96),
    "bill_mobile": (r"Registered\s*Mobile\s*([0-9]{10})", 98),
    "address": (r"Address\s+((?!Address)[A-Z0-9][A-Z0-9 ,.\-/]{10,90})", 94),
    "pin": (r"PIN\s*Code\s*([0-9]{6})", 98),
    "avg_units": (r"Average\s*Units\s*Per\s*Month\s*([0-9]+)\s*KWH", 95),
    "amount": (r"NET AMOUNT PAYABLE\s*INR\s*([0-9,.]+)", 93),
}
AADHAAR_LABELS = {
    "aadhaar_name": (r"Name\s*([A-Za-z][A-Za-z .'\-]{3,60})", 98),
    "aadhaar_masked": (r"Identity\s*Number\s*(X{4} X{4} [0-9]{4})", 99),
}
PASSBOOK_LABELS = {
    "account_holder": (r"Account\s*Holder\s*([A-Za-z][A-Za-z .'\-]{3,60})", 96),
    "account_no": (r"Account\s*Number\s*([X0-9]{6,20})", 95),
    "ifsc": (r"IFSC\s*Code\s*([A-Z]{4}0[A-Z0-9]{6})", 99),
}
OWNERSHIP_LABELS = {
    "owner_name": (r"Owner\s*Name\s*([A-Za-z][A-Za-z .'\-]{3,60})", 97),
    "property_address": (r"Property\s*Address\s+([A-Z0-9][A-Z0-9 ,.\-/]{10,90})", 95),
    "property_pin": (r"Property\s*PIN\s*([0-9]{6})", 98),
}

PRETTY = {
    "consumer_no": "Consumer number", "bill_name": "Consumer name (bill)",
    "tariff": "Tariff category", "sanctioned_load": "Sanctioned load (kW)",
    "meter_no": "Meter number", "bill_mobile": "Registered mobile",
    "address": "Billing address", "pin": "PIN code",
    "avg_units": "Average units per month", "amount": "Net amount payable",
    "aadhaar_name": "Name on identity document", "aadhaar_masked": "Identity number (masked)",
    "aadhaar_address": "Address on Aadhaar", "aadhaar_pin": "PIN on Aadhaar",
    "aadhaar_district": "District", "aadhaar_dob": "Date of birth", "aadhaar_gender": "Gender",
    "account_holder": "Bank account holder", "account_no": "Bank account (masked)",
    "ifsc": "IFSC code",
    "owner_name": "Property owner", "property_address": "Property address",
    "property_pin": "Property PIN code",
    "bill_unread": "Electricity bill", "aadhaar_unread": "Aadhaar", "passbook_unread": "Bank page",
}
KEY_OF = {v: k for k, v in PRETTY.items()}
ORDER = (list(LABELS) + list(AADHAAR_LABELS) +
         ["aadhaar_address", "aadhaar_pin", "aadhaar_district", "aadhaar_dob", "aadhaar_gender"] +
         list(PASSBOOK_LABELS) + list(OWNERSHIP_LABELS) +
         ["bill_unread", "aadhaar_unread", "passbook_unread"])


def grab(text, labels):
    out = {}
    for key, (pat, conf) in labels.items():
        m = re.search(pat, text, re.I)
        if m:
            out[key] = (" ".join(m.group(1).split()).strip(" ,."), conf)
    return out


def norm_name(n):
    return " ".join(re.sub(r"[^A-Z ]", "", (n or "").upper()).split())


def norm_cmp(a, b):
    """Same normalisation the portal applies, so pre-flight matches the real rule."""
    return norm_name(a) == norm_name(b)


def similarity(a, b):
    def toks(s):
        return [t for t in re.sub(r"[^A-Za-z ]", "", (s or "").upper()).split() if t]
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    # surname and first name carry the weight; a middle name reduced to an initial is a
    # near miss, not a different person
    base = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    ends = (ta[0] == tb[0]) + (ta[-1] == tb[-1])
    return min(1.0, base * 0.6 + ends * 0.2)


def kind_of(key):
    """Which uploaded document a field is read from."""
    if key.startswith("aadhaar"):
        return "aadhaar"
    if key in LABELS or key == "bill_unread":
        return "bill"
    if key in PASSBOOK_LABELS or key == "passbook_unread":
        return "passbook"
    return "ownership"


FULL_AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")


def refuse_aadhaar_number(key, value):
    """A whole Aadhaar number is never stored. It is accepted only in the Aadhaar number box (checked,
    then cut to the last 4 digits); in any other box it is refused with a pointer to that box."""
    if key.startswith("aadhaar") and key != "aadhaar_masked" and FULL_AADHAAR.search(value or ""):
        raise ValueError("that is an Aadhaar number: type it in the Aadhaar number box under Details "
                         "(Solara checks it and keeps only the last 4 digits). This box is for the name")


def _record(customer_id):
    from . import closeout
    return closeout.data(customer_id)


def mask_account(v):
    d = re.sub(r"\D", "", v or "")
    return ("X" * 6 + d[-4:]) if len(d) >= 4 else v


# ------------------------------- the run -------------------------------
def _f(value, conf, source, status="ok", note=""):
    return {"value": value, "confidence": conf, "source": source, "status": status, "note": note}


def _unread(why):
    return _f("not read", 0, "—", "review", why)


async def run(customer_id, use_llm=True, fresh=None):
    """fresh: the kind of document just uploaded; operator corrections to fields read from it are
    dropped (the document changed), corrections to every other field are kept."""
    c = db.one("SELECT * FROM customers WHERE id=?", (customer_id,))
    if not c:
        raise ValueError(f"unknown customer {customer_id}")
    docs = {d["kind"]: d for d in db.q("SELECT * FROM documents WHERE customer_id=?", (customer_id,))}
    if not docs.keys() & {"bill", "aadhaar"}:
        raise ValueError("no documents on file for this customer; upload the bill and Aadhaar first")
    st = llm_status()
    model = st if use_llm and st["enabled"] else None
    fields, notes = {}, []

    # ---- electricity bill (a new-connection applicant has none) ----
    bill_text = ""
    if "bill" in docs:
        bill_text, imgs, problem = read_doc(docs["bill"]["path"])
        fields.update({k: _f(v, conf, "bill") for k, (v, conf) in grab(bill_text, LABELS).items()})
        found = len(fields)
        primary = found < 4  # the parser does not know this bill's layout
        use_text = len(bill_text.strip()) >= 200
        if model and primary and (use_text or imgs):   # only when the rules cannot read this bill at all
            try:
                got = await llm_read("bill", st, text=bill_text if use_text else None,
                                     image=None if use_text else imgs[0])
                merge_model(fields, got, st, primary=primary)
                notes.append(f"bill read with {st['provider']}")
            except Exception as e:
                notes.append(f"model pass skipped: {type(e).__name__}")
        if not any(k in fields for k in ("consumer_no", "bill_name")):
            fields["bill_unread"] = _unread(
                problem or ("the bill could not be read automatically. " +
                            ("Upload the PDF from the MSEDCL website, or a sharper photo" if model
                             else "Photos need the AI model key; type the consumer number and name")))

    # ---- Aadhaar: QR first, offline ----
    if "aadhaar" in docs:
        text, imgs, problem = read_doc(docs["aadhaar"]["path"])
        q = aadhaar_qr(imgs) if imgs else None
        if q and q.get("name"):
            src = "Aadhaar QR"
            fields["aadhaar_name"] = _f(q["name"], 99, src)
            if q.get("last4"):
                fields["aadhaar_masked"] = _f(f"XXXX XXXX {q['last4']}", 99, src)
            for key, val in (("aadhaar_address", qr_address(q)), ("aadhaar_pin", q.get("pin")),
                             ("aadhaar_district", q.get("district")), ("aadhaar_dob", q.get("dob")),
                             ("aadhaar_gender", q.get("gender"))):
                if val:
                    fields[key] = _f(val, 99, src)
        else:
            got = grab(text, AADHAAR_LABELS)
            fields.update({k: _f(v, conf, "identity") for k, (v, conf) in got.items()})
            if not got:
                fields["aadhaar_unread"] = _unread(
                    problem or "the QR code on the Aadhaar could not be read. Take a straight, "
                               "sharp photo of the side with the QR code, or type the name")

    # ---- bank page ----
    if "passbook" in docs:
        text, imgs, problem = read_doc(docs["passbook"]["path"])
        got = {k: _f(v, conf, "passbook") for k, (v, conf) in grab(text, PASSBOOK_LABELS).items()}
        if len(got) < 2 and model and imgs:
            try:
                merge_model(got, await llm_read("passbook", st, image=imgs[0]), st, primary=True)
                notes.append(f"bank page read with {st['provider']}")
            except Exception as e:
                notes.append(f"model pass skipped: {type(e).__name__}")
        if "account_no" in got:
            got["account_no"]["value"] = mask_account(got["account_no"]["value"])
        fields.update(got)
        if not got:
            fields["passbook_unread"] = _unread(
                problem or ("the bank page could not be read" +
                            ("" if model else "; photos need the AI model key")))

    if "ownership" in docs:
        text, _, _ = read_doc(docs["ownership"]["path"])
        fields.update({k: _f(v, conf, "ownership proof") for k, (v, conf) in
                       grab(text, OWNERSHIP_LABELS).items()})
        if "property_address" in fields:
            # the PIN sits in its own field; drop it if the text layer ran it onto the address
            fields["property_address"]["value"] = re.sub(
                r"\s*\b\d{6}$", "", fields["property_address"]["value"])
        on, an = fields.get("owner_name", {}).get("value"), fields.get("aadhaar_name", {}).get("value")
        if on and an and not norm_cmp(on, an):
            fields["owner_name"]["status"] = "review"
            fields["owner_name"]["note"] = f"Identity document reads “{an}”."

    # ---- cross-document rules ----
    bn, an = fields.get("bill_name", {}).get("value"), fields.get("aadhaar_name", {}).get("value")
    if bn and an:
        sim = similarity(bn, an)
        fields["bill_name"]["confidence"] = int(round(sim * 100))
        if sim < 0.97:
            fields["bill_name"]["status"] = "review"
            fields["bill_name"]["note"] = (f"Does not match the identity document, which reads "
                                           f"“{an}”. The portal validates against the "
                                           f"bill, so the bill spelling is what must be filed.")
    if fields.get("pin", {}).get("value") and c["pin"] and fields["pin"]["value"] != c["pin"]:
        fields["pin"]["status"] = "review"
        fields["pin"]["note"] = f"CRM record holds {c['pin']}."
    cno = fields.get("consumer_no", {}).get("value") or c["consumer_no"]
    # conflicts between documents, and between a document and what a person already entered
    if fields.get("pin") and fields.get("aadhaar_pin") and fields["pin"]["value"] != fields["aadhaar_pin"]["value"]:
        fields["aadhaar_pin"]["status"] = "review"
        fields["aadhaar_pin"]["note"] = (f"The bill's PIN is {fields['pin']['value']}. Confirm only if "
                                         "the customer lives elsewhere; the bill PIN is what is filed.")
    if fields.get("consumer_no") and c["consumer_no"] and fields["consumer_no"]["value"] != c["consumer_no"]:
        fields["consumer_no"]["status"] = "review"
        fields["consumer_no"]["note"] = f"The record already holds {c['consumer_no']}."
    _, rec = _record(customer_id)
    rec_mobile = re.sub(r"\D", "", rec.get("mobile") or "")[-10:]
    if fields.get("bill_mobile") and rec_mobile and fields["bill_mobile"]["value"] != rec_mobile:
        fields["bill_mobile"]["status"] = "review"
        fields["bill_mobile"]["note"] = f"The record holds {rec_mobile}, typed by hand."
    dupes = db.q("SELECT id FROM customers WHERE consumer_no=? AND id<>?", (cno, customer_id)) if cno else []
    if dupes:
        fields.setdefault("consumer_no", _f(cno, 99, "bill"))
        fields["consumer_no"]["status"] = "review"
        fields["consumer_no"]["note"] = "Same consumer number appears on " + \
                                        ", ".join(d["id"] for d in dupes)

    # a person's corrections survive a re-read, unless the document they corrected was replaced
    for r in saved(customer_id):
        key = KEY_OF.get(r["field"])
        newer = (r["ts"] or "") >= ((docs.get(kind_of(key)) or {}).get("uploaded_at") or "")  # not for a replaced document
        if key and r["note"].startswith("Checked by") and kind_of(key) != fresh and key in PRETTY and newer:
            fields[key] = _f(r["value"], 100, r["source"], "ok", r["note"])
    if "aadhaar_name" in fields and fields["aadhaar_name"]["status"] == "ok":
        fields.pop("aadhaar_unread", None)
    if "consumer_no" in fields and fields["consumer_no"]["status"] == "ok":
        fields.pop("bill_unread", None)
    db.ex("DELETE FROM extractions WHERE customer_id=?", (customer_id,))
    rows = []
    for k in ORDER:
        if k in fields:
            f = fields[k]
            db.ex("""INSERT INTO extractions(customer_id,field,value,confidence,source,status,note,ts)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (customer_id, PRETTY[k], f["value"], f["confidence"], f["source"], f["status"],
                   f["note"], db.now()))
            rows.append({"key": k, "field": PRETTY[k], **f})
    apply_to_record(customer_id)
    model_note = "; ".join(notes) or None
    db.audit("agent", "agent", "Document extraction", customer_id,
             f"{len(rows)} fields, {sum(1 for r in rows if r['status'] == 'review')} flagged" +
             (f", {model_note}" if model_note else ""))
    return {"customer_id": customer_id, "fields": rows, "model": model_note, "llm": st,
            "chars_parsed": len(bill_text),
            "documents": [{"kind": k, "filename": d["filename"], "bytes": d["bytes"]}
                          for k, d in docs.items()]}


# ------------------------------- the model -------------------------------
PROMPTS = {
    "bill": ("an Indian electricity bill", "consumer_no, bill_name, tariff, sanctioned_load "
             "(number, kW), meter_no, bill_mobile, address, pin, avg_units"),
    "passbook": ("the first page of an Indian bank passbook or a cancelled cheque",
                 "account_holder, account_no, ifsc"),
    "serial": ("a photo of the label on a solar PV module or inverter", "serial (the serial number, "
               "often after S/N or Serial No.)"),
}


async def llm_read(kind, st, text=None, image=None):
    """Ask the model for the fields, each with how sure it is. Never used for Aadhaar."""
    what, keys = PROMPTS[kind]
    ask = (f"This is {what}. Reply with JSON only, no prose. For each of these keys: {keys} "
           'give {"value": <exact text as printed, or null if absent>, "sure": <true only if you '
           'can read it clearly>}.')
    content = [{"type": "text", "text": ask + ("\n\nTEXT:\n" + text[:6000] if text else "")}]
    if image is not None:
        im = image.copy()
        im.thumbnail((1600, 1600))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
    import httpx
    async with httpx.AsyncClient(timeout=60) as cl:
        if st["provider"] == "anthropic":
            if image is not None:
                content.insert(0, {"type": "image", "source": {"type": "base64",
                                                                "media_type": "image/jpeg", "data": b64}})
            r = await cl.post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                       "anthropic-version": "2023-06-01"},
                              json={"model": st["model"], "max_tokens": 900,
                                    "messages": [{"role": "user", "content": content}]})
            r.raise_for_status()
            out = r.json()["content"][0]["text"]
        else:
            if image is not None:
                content.append({"type": "image_url",
                                "image_url": {"url": "data:image/jpeg;base64," + b64}})
            r = await cl.post("https://api.openai.com/v1/chat/completions",
                              headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                              json={"model": st["model"], "max_tokens": 900,
                                    "messages": [{"role": "user", "content": content}]})
            r.raise_for_status()
            out = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else {}


def merge_model(fields, got, st, primary):
    """primary: the model is the only reader, so its unsure values are flagged. Otherwise it is
    a second opinion, and any disagreement with the parser is flagged."""
    for k, v in (got or {}).items():
        if k not in PRETTY:
            continue
        val, sure = (v.get("value"), v.get("sure")) if isinstance(v, dict) else (v, True)
        if val in (None, ""):
            continue
        val = " ".join(str(val).split())
        if k in fields:
            if val.upper() != str(fields[k]["value"]).upper():
                fields[k]["status"] = "review"
                fields[k]["note"] = (fields[k]["note"] + " " if fields[k]["note"] else "") + \
                                    f"The model read this as “{val}”."
            fields[k]["source"] += f" + {st['provider']}"
        elif primary:
            fields[k] = _f(val, 90 if sure else 50, st["provider"], "ok" if sure else "review",
                           "" if sure else "The model was not sure of this; check it on the document.")


# ------------------------------- into the record -------------------------------
def apply_to_record(customer_id, only=None, overwrite=False):
    """Copy extracted values into the customer record. Flagged values are skipped until a
    person confirms them; by default nothing already in the record is overwritten."""
    from . import closeout
    rows = {KEY_OF.get(r["field"]): r for r in saved(customer_id)}
    ok = {k: r["value"] for k, r in rows.items()
          if k and r["status"] != "review" and r["value"] != "not read" and (only is None or k in only)}
    c = db.one("SELECT * FROM customers WHERE id=?", (customer_id,))
    cols = {}
    for key, col in (("consumer_no", "consumer_no"), ("aadhaar_name", "aadhaar_name")):
        if key in ok:
            cols[col] = ok[key]
    if "aadhaar_address" in ok or "address" in ok:
        cols["address"] = ok.get("address") or ok.get("aadhaar_address")  # the premises is on the bill
    if "aadhaar_pin" in ok or "pin" in ok:
        cols["pin"] = ok.get("pin") or ok.get("aadhaar_pin")
    if "account_no" in ok and "ifsc" in ok:
        cols["bank"] = f"{ok['account_no']} / {ok['ifsc']}"
    if "aadhaar_name" in ok and not c["name"]:
        cols["name"] = ok["aadhaar_name"]
    for col, v in cols.items():
        if v and (overwrite or not c[col]):
            db.ex(f"UPDATE customers SET {col}=? WHERE id=?", (v, customer_id))
    _, d = closeout.data(customer_id)
    extra = {"mobile": ok.get("bill_mobile"), "sanctioned_load": ok.get("sanctioned_load"),
             "tariff": ok.get("tariff"), "district": valid.district(ok.get("aadhaar_district") or "", strict=False),
             "aadhaar_last4": (ok.get("aadhaar_masked") or "")[-4:] or None}
    # the mobile the owner typed is the one the OTP goes to: a bill never replaces it
    extra = {k: v for k, v in extra.items() if v and ((overwrite and k != "mobile") or not d.get(k))}
    if extra:
        closeout.save(customer_id, extra, "extraction")


def confirm(customer_id, key, value, user):
    """A person checked a field against the document: store their value and file it. The source
    and what was read are kept in the note. An unread document is resolved by typing the field
    it should have given."""
    label = PRETTY.get(key)
    row = db.one("SELECT * FROM extractions WHERE customer_id=? AND field=?", (customer_id, label))         if label else None
    if not row:
        raise KeyError(key)
    from . import valid
    value = " ".join(valid.text(value, "value").split())
    if not value:
        raise ValueError("enter the value as it appears on the document")
    refuse_aadhaar_number(key, value)
    if key in ("aadhaar_name", "bill_name", "owner_name", "account_holder"):
        value = valid.name(value, "the name")
    elif key == "aadhaar_masked":
        value = f"XXXX XXXX {valid.aadhaar_any(value)}"   # a full number is checked, then only 4 digits kept
    elif key in ("pin", "aadhaar_pin", "property_pin"):
        value = valid.pin(value)
    elif key == "ifsc":
        value = valid.ifsc(value)
    elif key == "consumer_no":
        value = valid.consumer_no(value)
    elif key == "bill_mobile":
        value = valid.mobile(value)
    if key == "aadhaar_unread":
        real = "aadhaar_name"  # typed text becomes the name, so it is checked as a name below
    elif key == "bill_unread":
        real = "consumer_no"
        try:
            value = valid.consumer_no(value)
        except ValueError:
            raise ValueError("type the 12-digit consumer number printed on the bill; the name goes in Details")
    else:
        real = key
    if real == "aadhaar_name":
        value = valid.name(value, "the name on the Aadhaar")
    was = row["value"] if row["value"] != "not read" else None
    note = f"Checked by {user['name']}" + (f" (read as “{was}”)" if was and was != value else "")
    if real != key:
        db.ex("DELETE FROM extractions WHERE customer_id=? AND field=?", (customer_id, label))
        db.ex("""INSERT INTO extractions(customer_id,field,value,confidence,source,status,note,ts)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (customer_id, PRETTY[real], value, 100, "typed from the document", "ok", note, db.now()))
    else:
        db.ex("""UPDATE extractions SET value=?, status='ok', confidence=100, note=?, ts=?
                 WHERE customer_id=? AND field=?""", (value, note, db.now(), customer_id, label))
    apply_to_record(customer_id, only={real, "account_no", "ifsc"}, overwrite=True)
    db.audit(user["username"], user["role"], "Confirmed extracted field", customer_id, PRETTY[real])


def saved(customer_id):
    return db.q("SELECT * FROM extractions WHERE customer_id=? ORDER BY id", (customer_id,))


def filing_values(customer_id):
    """What the agent should type into the portal, as decided by extraction."""
    rows = {r["field"]: r for r in saved(customer_id)}
    g = lambda k: (rows.get(k) or {}).get("value")
    return {
        "consumer_no": g("Consumer number"),
        "mobile": g("Registered mobile"),
        "bill_name": g("Consumer name (bill)"),
        "aadhaar_name": g("Name on identity document"),
        "address": g("Billing address"),
        "pin": g("PIN code"),
        "bank": f"{g('Bank account (masked)')} / {g('IFSC code')}",
        "load": g("Sanctioned load (kW)"),
        "roof_area": "41",  # sandbox agent only: the sandbox portal requires a roof area
        "owner_name": g("Property owner"),
        "owner_address": g("Property address"),
        "owner_pin": g("Property PIN code"),
        "flagged": [r["field"] for r in saved(customer_id) if r["status"] == "review"],
    }


if __name__ == "__main__":
    db.seed()
    print(json.dumps(asyncio.run(run("SS-2045")), indent=1, ensure_ascii=False))
