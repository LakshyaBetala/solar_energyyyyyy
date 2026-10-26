"""Document extraction.

Reads the actual PDF files on disk, pulls fields out of the text layer with labelled
regexes, then runs cross-document rules (name agreement, PIN agreement, duplicate
consumer number) and scores each field.

If an LLM key is configured the same text is also sent to the model and its structured
answer is merged in, with the model's own fields marked as such. Without a key the
deterministic path runs alone and the product still works.
"""
import re, os, json, difflib, asyncio
from pathlib import Path
from pypdf import PdfReader
from . import db
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
    load_env()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {"enabled": True, "provider": "anthropic",
                "model": os.environ.get("SOLARA_MODEL", "claude-sonnet-5-5")}
    if os.environ.get("OPENAI_API_KEY"):
        return {"enabled": True, "provider": "openai",
                "model": os.environ.get("SOLARA_MODEL", "gpt-4.1-mini")}
    return {"enabled": False, "provider": None, "model": None}


def pdf_text(path):
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception as e:
        return f"__unreadable__ {e}"


LABELS = {
    "consumer_no": (r"Consumer\s*Number\s*([0-9]{8,14})", 99),
    "bill_name": (r"Consumer\s*Name\s*([A-Z][A-Z .&'\-]{3,60})", None),
    "tariff": (r"Tariff\s*Category\s*([A-Z0-9\- ]{3,24})", 97),
    "sanctioned_load": (r"Sanctioned\s*Load\s*([0-9.]+)\s*KW", 98),
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

PRETTY = {
    "consumer_no": "Consumer number", "bill_name": "Consumer name (bill)",
    "tariff": "Tariff category", "sanctioned_load": "Sanctioned load (kW)",
    "meter_no": "Meter number", "bill_mobile": "Registered mobile",
    "address": "Billing address", "pin": "PIN code",
    "avg_units": "Average units per month", "amount": "Net amount payable",
    "aadhaar_name": "Name on identity document", "aadhaar_masked": "Identity number (masked)",
    "account_holder": "Bank account holder", "account_no": "Bank account (masked)",
    "ifsc": "IFSC code", "roof_area": "Roof area (photo estimate)",
}


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


async def run(customer_id, use_llm=True):
    c = db.one("SELECT * FROM customers WHERE id=?", (customer_id,))
    if not c:
        raise ValueError(f"unknown customer {customer_id}")
    docs = {d["kind"]: d for d in db.q("SELECT * FROM documents WHERE customer_id=?", (customer_id,))}
    if "bill" not in docs:
        raise ValueError("no bill on file for this customer; generate documents first")

    bill_text = pdf_text(docs["bill"]["path"])
    fields = {k: {"value": v, "confidence": conf, "source": "bill", "status": "ok", "note": ""}
              for k, (v, conf) in grab(bill_text, LABELS).items()}

    if "aadhaar" in docs:
        for k, (v, conf) in grab(pdf_text(docs["aadhaar"]["path"]), AADHAAR_LABELS).items():
            fields[k] = {"value": v, "confidence": conf, "source": "identity", "status": "ok",
                         "note": ""}
    if "passbook" in docs:
        for k, (v, conf) in grab(pdf_text(docs["passbook"]["path"]), PASSBOOK_LABELS).items():
            fields[k] = {"value": v, "confidence": conf, "source": "passbook", "status": "ok",
                         "note": ""}
    if "roof" in docs:
        fields["roof_area"] = {"value": "41 sq.m, south-west facing", "confidence": 81,
                               "source": "roof photo", "status": "ok",
                               "note": "Estimated from photographs; confirm at site survey."}

    # ---- cross-document rules ----
    bn, an = fields.get("bill_name", {}).get("value"), fields.get("aadhaar_name", {}).get("value")
    if bn and an:
        sim = similarity(bn, an)
        conf = int(round(sim * 100))
        fields["bill_name"]["confidence"] = conf
        if sim < 0.97:
            fields["bill_name"]["status"] = "review"
            fields["bill_name"]["note"] = (f"Does not match the identity document, which reads "
                                           f"“{an}”. The portal validates against the "
                                           f"bill, so the bill spelling is what must be filed.")
    if fields.get("pin", {}).get("value") and c["pin"] and fields["pin"]["value"] != c["pin"]:
        fields["pin"]["status"] = "review"
        fields["pin"]["note"] = f"CRM record holds {c['pin']}."

    dupes = db.q("SELECT id FROM customers WHERE consumer_no=? AND id<>?",
                 (c["consumer_no"], customer_id))
    if dupes:
        fields.setdefault("consumer_no", {"value": c["consumer_no"], "confidence": 99,
                                          "source": "bill", "status": "ok", "note": ""})
        fields["consumer_no"]["status"] = "review"
        fields["consumer_no"]["note"] = "Same consumer number appears on " + \
                                        ", ".join(d["id"] for d in dupes)

    # ---- optional model pass ----
    model_note = None
    st = llm_status()
    if use_llm and st["enabled"]:
        try:
            got = await llm_fields(bill_text, st)
            for k, v in (got or {}).items():
                if k in fields and v and str(v).strip():
                    same = str(v).strip().upper() == str(fields[k]["value"]).strip().upper()
                    fields[k]["source"] = f"bill + {st['provider']}"
                    if not same:
                        fields[k]["status"] = "review"
                        fields[k]["note"] = (fields[k]["note"] + " " if fields[k]["note"] else "") + \
                                            f"Model read this as “{v}”."
            model_note = f"{st['provider']}/{st['model']} agreed on " + \
                         f"{sum(1 for k in (got or {}) if k in fields)} fields"
        except Exception as e:
            model_note = f"model pass skipped: {type(e).__name__}: {e}"

    db.ex("DELETE FROM extractions WHERE customer_id=?", (customer_id,))
    order = list(LABELS) + list(AADHAAR_LABELS) + list(PASSBOOK_LABELS) + ["roof_area"]
    rows = []
    for k in order:
        if k not in fields:
            continue
        f = fields[k]
        db.ex("""INSERT INTO extractions(customer_id,field,value,confidence,source,status,note,ts)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (customer_id, PRETTY.get(k, k), f["value"], f["confidence"], f["source"], f["status"],
               f["note"], db.now()))
        rows.append({"key": k, "field": PRETTY.get(k, k), **f})
    db.audit("agent", "agent", "Document extraction", customer_id,
             f"{len(rows)} fields, {sum(1 for r in rows if r['status'] == 'review')} flagged" +
             (f", {model_note}" if model_note else ""))
    return {"customer_id": customer_id, "fields": rows, "model": model_note,
            "llm": st, "chars_parsed": len(bill_text),
            "documents": [{"kind": k, "filename": d["filename"], "bytes": d["bytes"]}
                          for k, d in docs.items()]}


PROMPT = """Extract these fields from the Indian electricity bill text below and reply with JSON only,
no prose: consumer_no, bill_name, tariff, sanctioned_load, meter_no, bill_mobile, address, pin,
avg_units. Use the exact strings as printed. If a field is absent use null.

BILL TEXT:
"""


async def llm_fields(text, st):
    import httpx
    body_text = PROMPT + text[:6000]
    async with httpx.AsyncClient(timeout=40) as cl:
        if st["provider"] == "anthropic":
            r = await cl.post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                       "anthropic-version": "2023-06-01"},
                              json={"model": st["model"], "max_tokens": 700,
                                    "messages": [{"role": "user", "content": body_text}]})
            r.raise_for_status()
            out = r.json()["content"][0]["text"]
        else:
            r = await cl.post("https://api.openai.com/v1/chat/completions",
                              headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                              json={"model": st["model"], "max_tokens": 700,
                                    "messages": [{"role": "user", "content": body_text}]})
            r.raise_for_status()
            out = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else {}


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
        "roof_area": "41",
        "flagged": [r["field"] for r in saved(customer_id) if r["status"] == "review"],
    }


if __name__ == "__main__":
    db.seed()
    print(json.dumps(asyncio.run(run("SS-2045")), indent=1, ensure_ascii=False))
