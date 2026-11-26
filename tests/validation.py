"""Input rules and step-order guards for registration (the defects in docs/K1_DEFECT_REGISTER.xlsx).

  python -m uvicorn app.main:app --port 8900     (in one terminal)
  python tests/validation.py                     (in another)
"""
import sys, threading
import httpx
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import valid  # noqa: E402

BASE = "http://127.0.0.1:8900"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def refuses(fn, *a):
    try:
        fn(*a)
        return False
    except ValueError:
        return True


# ---- pure rules
for good, want in [("250000", "250000"), ("2,50,000", "250000"), ("Rs 300000", "300000"), ("₹ 1,85,000", "185000"),
                   ("143000", "143000"), ("125000.00", "125000")]:
    check(f"cost {good!r} -> {want}", valid.cost(good) == want, valid.cost(good))
for bad in ["-250000", "0", "999999999999", "Rs 1.5 lakh", "250000.50", "abc", "1e6", "5000", "210000", "199999", "300001"]:
    check(f"cost {bad!r} refused (not on the price list)", refuses(valid.cost, bad))
check("exactly the nine listed costs are accepted", sorted(c for c in range(100000, 350001, 1000) if not refuses(valid.cost, str(c)))
      == sorted(valid.COST_OPTIONS))

for bad in ["123", "@@@ ###", "Priya1234", "<script>x</script>", "A" * 300, "ab", "..."]:
    check(f"name {bad[:20]!r} refused", refuses(valid.name, bad))
for good in ["Priya Sanjay Kulkarni", "D'Souza", "Anne-Marie O.", "प्रिया कुलकर्णी"]:
    check(f"name {good!r} accepted", not refuses(valid.name, good))

for bad in ["abc", "123456789", "1234567890123", "0000000000000", "111111111111", "1700555O1234"]:
    check(f"consumer no {bad!r} refused", refuses(valid.consumer_no, bad))
check("consumer no tolerates spaces and hyphens", valid.consumer_no("1700-5550 1234") == "170055501234")

for bad in ["abcd", "12", "99999999", "12345"]:
    check(f"Aadhaar last 4 {bad!r} refused", refuses(valid.aadhaar_last4, bad))
def aadhaar_with_check_digit(base):
    return next(base + d for d in "0123456789" if valid.verhoeff_ok(base + d))
good = aadhaar_with_check_digit("23456789012")
check("a real 12-digit Aadhaar passes and only its last 4 come back", valid.aadhaar_number(good) == good[-4:])
check("spaces in the 12 digits are fine", valid.aadhaar_number(f"{good[:4]} {good[4:8]} {good[8:]}") == good[-4:])
wrong = good[:-1] + str((int(good[-1]) + 1) % 10)
for bad in [wrong, "123456789012", "0" + good[1:], good[:11], good + "1", "2345 6789 01AB"]:
    check(f"Aadhaar {bad!r} refused", refuses(valid.aadhaar_number, bad))
check("Aadhaar box takes the full number, the last 4, or the masked form",
      valid.aadhaar_any(good) == valid.aadhaar_any(good[-4:]) == valid.aadhaar_any("XXXX XXXX " + good[-4:]) == good[-4:])
check("Aadhaar masked form accepted", valid.aadhaar_last4("XXXX XXXX 4471") == "4471")
check("mobile letters refused", refuses(valid.mobile, "abcdefghij"))
check("mobile 91 prefix tolerated", valid.mobile("+91 90281 44599") == "9028144599")
check("a list is not text", refuses(valid.text, ["x"], "name"))

# ---- through the API
sup = httpx.Client(base_url=BASE, timeout=60)
sup.post("/api/login", json={"username": "r.deshmukh", "password": "demo"}).raise_for_status()
sup.post("/api/demo/reset")
mk = lambda name, mobile="": sup.post("/api/customers", json={"name": name, "mobile": mobile, "allow_duplicate": True})

check("name '123' refused when adding a customer", mk("123").status_code == 400)
cid = mk("Validation Tester One", "9028140001").json()["customer"]["id"]
put = lambda body: sup.put(f"/api/registration/{cid}", json=body)

check("good consumer number saved", put({"consumer_no": "170011122233"}).status_code == 200)
r = put({"consumer_no": "abc"})
check("garbage consumer number refused with 400", r.status_code == 400, r.text[:80])
check("...and the saved number is still there",
      sup.get(f"/api/registration/{cid}").json()["customer"]["consumer_no"] == "170011122233")

check("a listed cost is saved", put({"rts_cost": "250000"}).status_code == 200
      and sup.get(f"/api/registration/{cid}").json()["data"]["rts_cost"] == "250000")
check("a cost that is not on the list is refused and the saved one kept", put({"rts_cost": "210000"}).status_code == 400
      and sup.get(f"/api/registration/{cid}").json()["data"]["rts_cost"] == "250000")
check("negative cost refused", put({"rts_cost": "-250000"}).status_code == 400)
check("one bad field saves nothing", put({"kw": "3", "rts_cost": "abc"}).status_code == 400
      and sup.get(f"/api/registration/{cid}").json()["customer"]["kw"] != 3)

for field, val in [("name", 123), ("kw", [1]), ("mobile", {"a": 1}), ("email", 5), ("rts_cost", [9]), ("consumer_no", [1])]:
    check(f"wrong-typed {field} gives 400, not 500", put({field: val}).status_code == 400)
check("wrong-typed login gives 400", httpx.post(BASE + "/api/login", json={"username": 5, "password": ["x"]}).status_code == 400)
check("wrong-typed application number gives 400",
      sup.post(f"/api/registration/{cid}/mark", json={"step": "registered", "app_no": 123}).status_code == 400)

# ---- the full Aadhaar number: accepted, checked, and only the last 4 kept
r = put({"aadhaar": good})
check("the Details box accepts a full valid Aadhaar number", r.status_code == 200, r.text[:80])
g = sup.get(f"/api/registration/{cid}").json()
check("only the last 4 are on file", g["data"].get("aadhaar_last4") == good[-4:])
check("the full number is shown to a supervisor", g["data"].get("aadhaar_full") == good.replace(" ", ""))
from app import db as _db  # noqa: E402
_row = _db.one("SELECT data FROM closeout WHERE customer_id=?", (cid,))["data"]
check("the full number is stored only encrypted", good.replace(" ", "") not in _row and good not in _row and '"aadhaar_enc"' in _row)
viewer = httpx.Client(base_url=BASE, timeout=60)
viewer.post("/api/login", json={"username": "a.more", "password": "demo"}).raise_for_status()
check("a viewer never sees the full number", good.replace(" ", "") not in viewer.get(f"/api/registration/{cid}").text)
from app import db as _db  # noqa: E402
dump = chr(10).join(str(tuple(row)) for (t,) in _db.conn().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                  for row in _db.conn().execute(f"SELECT * FROM {t}"))
check("...nor anywhere in the database, including the audit trail", good not in dump)
check("a wrong check digit is refused with a reason", put({"aadhaar": wrong}).status_code == 400)
check("a bad Aadhaar leaves the saved last 4 alone",
      sup.get(f"/api/registration/{cid}").json()["data"].get("aadhaar_last4") == good[-4:])
check("saving the masked form again changes nothing", put({"aadhaar": "XXXX XXXX " + good[-4:]}).status_code == 200)
import os as _os  # noqa: E402
from app import extract as _ex  # noqa: E402
_os.environ["SOLARA_USE_AI"] = "0"
check("SOLARA_USE_AI=0 switches the AI off even with a key in .env", _ex.llm_status()["enabled"] is False)
_os.environ.pop("SOLARA_USE_AI", None)

# ---- order of steps
r = sup.post(f"/api/registration/{cid}/mark", json={"step": "registered", "app_no": "NP-MHSED26-16190001"})
check("cannot register before documents are read", r.status_code == 400, r.text[:90])
r = sup.post(f"/api/registration/{cid}/agreement")
check("cannot send the agreement before registration", r.status_code == 400, r.text[:90])
r = sup.post(f"/api/registration/{cid}/mark", json={"step": "accepted"})
check("cannot accept before registering", r.status_code == 400)

# ---- two people adding customers at the same moment
codes = []
def add(i):
    codes.append(mk(f"Parallel Person {'abcdefghijkl'[i]}", f"90281{i:05d}").status_code)
ts = [threading.Thread(target=add, args=(i,)) for i in range(12)]
[t.start() for t in ts]; [t.join() for t in ts]
check("12 customers added at once: no 500", 500 not in codes and codes.count(200) == 12, str(sorted(set(codes))))
ids = [c["id"] for c in sup.get("/api/registration").json()]
check("...and every one has its own ID", len(ids) == len(set(ids)))

# ---- values the owner no longer types
check("favicon request is answered, not a 404", httpx.get(BASE + "/favicon.ico").status_code == 204)
put({"kw": "3"})
v = sup.get(f"/api/registration/{cid}").json()
check("site feasibility standing answers: Yes/Yes/Yes and about 10 m2 per kW until recorded",
      [v["values"].get(k) for k in ("roof_load_ok", "shadow_free", "site_visited")] == ["Yes"] * 3 and v["values"].get("roof_area") == "30")
check("module technology defaults from settings", bool(v["values"]["module_type"]))
key = sup.post("/api/copilot/key").json()["key"]
look = httpx.get(BASE + "/api/copilot/lookup", params={"cid": cid}, headers={"X-Solara-Key": key}).json()
check("co-pilot is told which values were worked out", {"module_type", "bank_name", "account_type", "permissible_kw"} <= set(look["derived"]), str(look.get("derived")))
check("co-pilot receives the module technology, not a roof area", look["values"].get("roof_area") == "30" and look["values"].get("module_type"))
# the loan pages' answers, typed once in Details; the bank account kept encrypted, shown only as its last 4
import json  # noqa: E402
r = put({"jansamarth_id": "ans-solar-12345678-1234567", "occupation": "Salaried", "collateral": "Yes", "co_applicant": "No",
         "address_same": "Yes", "house_ownership": "Single", "landmark": "Near the temple", "village": "Dighi",
         "rts_cost": "250000", "loan_amount": "225000", "bank_account": "601234567890", "ifsc": "mahb0000412", "account_type": "Savings"})
check("loan details save", r.status_code == 200, r.text[:120])
g = sup.get(f"/api/registration/{cid}").json()
lk = lambda: httpx.get(BASE + "/api/copilot/lookup", params={"cid": cid}, headers={"X-Solara-Key": key}).json()["values"]
lv = lk()
check("the helper gets every loan answer, the own contribution worked out as cost less loan",
      (lv.get("jansamarth_id"), lv.get("occupation"), lv.get("own_contribution"), lv.get("co_applicant"), lv.get("ifsc"), lv.get("bank_name"))
      == ("ANS-SOLAR-12345678-1234567", "Salaried", "25000", "No", "MAHB0000412", "Bank of Maharashtra"), str(lv)[:300])
check("the bank account reaches the helper in full but is stored only encrypted (Solara's screen sees the last 4)",
      lv.get("bank_account") == "601234567890" and "601234567890" not in json.dumps(g) and g["data"].get("bank_account_last4") == "7890")
check("a bad bank account or Jan Samarth ID is refused", put({"bank_account": "12ab"}).status_code == 400 and put({"jansamarth_id": "12345"}).status_code == 400)
check("the masked copy sent back by Save keeps the number", put({"bank_account": "XXXX7890"}).status_code == 200 and lk().get("bank_account") == "601234567890")
r = put({"loan_required": "Yes", "first_name": "Ramesh", "middle_name": "Sopan", "last_name": "Patil"})
lv = lk()
check("Bank loan needed and the name in three parts are kept; what is typed wins over the split of the Aadhaar name",
      r.status_code == 200 and (lv.get("loan_required"), lv.get("first_name"), lv.get("middle_name"), lv.get("last_name")) == ("Yes", "Ramesh", "Sopan", "Patil"), r.text[:120])
check("a co-applicant is No until said otherwise; a name part with digits is refused",
      put({"co_applicant": ""}).status_code == 200 and lk().get("co_applicant") == "No" and put({"last_name": "Patil2"}).status_code == 400)
# what the owner types in the helper's "needs your help" box is kept in Details for next time
rep = lambda k, v: httpx.post(BASE + "/api/copilot/report", json={"customer_id": cid, "event": "detail", "key": k, "value": v}, headers={"X-Solara-Key": key}).json()
saved = [rep("occupation", "Self Employed"), rep("ifsc", "sbin0001234"), rep("account_type", "Saving"), rep("visitor_name", "Amol Kadam")]
lv = lk()
check("a value typed in the helper's box is saved in Details (occupation, IFSC, the loan site's 'Saving', the visitor)",
      all(s.get("saved") for s in saved) and (lv.get("occupation"), lv.get("ifsc"), lv.get("account_type"), lv.get("visitor_name"))
      == ("Self Employed", "SBIN0001234", "Savings", "Amol Kadam"), str(saved))

# ---- two PINs that disagree: the chosen one is what is kept
from app import db, extract, registration  # noqa: E402
# the name in three parts: the bill's name first, in the Aadhaar's order when it is the same words (bills print the surname first)
sp = lambda bill, aad: tuple(registration.name_parts(registration.split_source(bill, aad)).values())
check("the bill's name is split for First / Middle / Last; same words reordered follow the Aadhaar's order",
      sp("Shri PATIL RAMESH SOPAN", "Ramesh Sopan Patil") == ("Ramesh", "Sopan", "Patil")
      and sp("Ramesh S Patil", "Ramesh Sopan Patil") == ("Ramesh", "S", "Patil")
      and sp(None, "Priya Sanjay Kulkarni") == ("Priya", "Sanjay", "Kulkarni"))
rows = [("PIN code", "411001", "ok"), ("PIN on Aadhaar", "410503", "review")]
for f, val, st in rows:
    db.ex("INSERT INTO extractions(customer_id,field,value,confidence,source,status,note,ts) VALUES(?,?,?,?,?,?,?,?)",
          (cid, f, val, 90, "test", st, "differs", db.now()))
for k in ("pin", "aadhaar_pin"):
    sup.post(f"/api/registration/{cid}/confirm", json={"key": k, "value": "410503"}).raise_for_status()
check("the PIN the owner picked is the one on file", sup.get(f"/api/registration/{cid}").json()["customer"]["pin"] == "410503")
check("a PIN that is not 6 digits is refused", sup.post(f"/api/registration/{cid}/confirm", json={"key": "pin", "value": "41"}).status_code == 400)

# ---- the name on the electricity bill is the final name: a different spelling on the Aadhaar holds nothing back
before = db.one("SELECT name, aadhaar_name FROM customers WHERE id=?", (cid,))
db.ex("UPDATE customers SET name=?, aadhaar_name=? WHERE id=?", ("SHRI KUMAR DEEPAK", "Deepak Kumar", cid))
g = sup.get(f"/api/registration/{cid}").json()
check("a bill name that differs from the Aadhaar is not an issue and does not block the details step",
      not any(i["field"] == "name" for i in registration.validate(cid)["issues"]) and "match the Aadhaar" not in g["next"]["label"], g["next"]["label"])
db.ex("UPDATE customers SET name=?, aadhaar_name=? WHERE id=?", (before["name"], before["aadhaar_name"], cid))

# ---- a value typed in the co-pilot box because Solara had none
r = httpx.post(BASE + "/api/copilot/report", headers={"X-Solara-Key": key},
               json={"customer_id": cid, "event": "detail", "key": "email", "value": "typed.here@example.com"})
check("a detail typed in the co-pilot is saved in Solara", r.status_code == 200 and r.json().get("saved") is True
      and sup.get(f"/api/registration/{cid}").json()["data"].get("email") == "typed.here@example.com", r.text[:80])
r = httpx.post(BASE + "/api/copilot/report", headers={"X-Solara-Key": key},
               json={"customer_id": cid, "event": "detail", "key": "rts_cost", "value": "-5"})
check("...and it is validated like any other entry", r.status_code == 400)

# ---- the public sign page
tok = "x" * 24
check("an unknown link shows no crafted text",
      "Your payment failed" not in httpx.get(f"{BASE}/sign/{tok}?error=Your payment failed").text)

# ---- the quotation: date, name and place changed in a Word file whose date is split over runs, as Word saves it
import io as _io, re as _re, tempfile as _tf, zipfile as _zf  # noqa: E402
from datetime import date as _date  # noqa: E402
from pathlib import Path as _P  # noqa: E402
from app import drafts  # noqa: E402
_body = ('<w:document><w:body><w:p><w:r><w:t>Outward no. x/2026/13/01   Date : </w:t></w:r><w:r><w:t>13</w:t></w:r>'
         '<w:r><w:t>.10.2026</w:t></w:r></w:p><w:p><w:r><w:t>To,</w:t></w:r></w:p><w:p><w:r><w:t>Old </w:t></w:r>'
         '<w:r><w:t>Name</w:t></w:r></w:p><w:p><w:r><w:t>Manchar, Pune</w:t></w:r></w:p><w:p><w:r><w:t>A &amp; B</w:t></w:r></w:p></w:body></w:document>')
_tmp = _P(_tf.mkdtemp()) / "q.docx"
with _zf.ZipFile(_tmp, "w") as _z:
    _z.writestr("word/document.xml", _body)
_out = _zf.ZipFile(_io.BytesIO(drafts.quotation_docx(_tmp, "ASHA D SAMPLE", "Dighi, Pune", _date(2026, 11, 14)))).read("word/document.xml").decode()
_lines = [_re.sub(r"<[^>]+>", "", q) for q in _re.findall(r"<w:p[ >].*?</w:p>", _out)]
check("the quotation gets the date, the name and the place; the outward number and the rest stay",
      _lines == ["Outward no. x/2026/13/01   Date : 14.11.2026", "To,", "ASHA D SAMPLE", "Dighi, Pune", "A &amp; B"], str(_lines))
# the customer's signature from a photo: saved through the API, and put on the agreement as ink only
from PIL import Image as _Im, ImageDraw as _Dr  # noqa: E402
import base64 as _b64  # noqa: E402
_ph = _Im.new("RGB", (600, 200), (240, 236, 225))
_Dr.Draw(_ph).line([(40, 150), (120, 50), (200, 150), (300, 60), (420, 140), (560, 90)], fill=(20, 25, 70), width=6)
_buf = _io.BytesIO(); _ph.save(_buf, "JPEG")
_url = "data:image/jpeg;base64," + _b64.b64encode(_buf.getvalue()).decode()
_r = sup.post(f"/api/registration/{cid}/signature", json={"image": _url})
check("a cropped signature photo is saved and shown back", _r.status_code == 200 and (_r.json().get("customer_sign") or "").startswith("data:image/png"), _r.text[:80])
check("anything that is not an image is refused", sup.post(f"/api/registration/{cid}/signature", json={"image": "data:text/plain;base64,aGk="}).status_code == 400)
_ink = _Im.open(_io.BytesIO(drafts.ink_only(_b64.b64decode(_r.json()["customer_sign"].split(",", 1)[1])))).getchannel("A").histogram()
check("on the agreement the paper drops out and the ink stays", _ink[0] > 0.7 * sum(_ink) and sum(_ink[200:]) > 0)
# a blank line above "GST NO." (as in two templates) is made 1 pt high, so the white text stays on the banner
_gst = _body.replace("<w:body>", '<w:body><w:p><w:pPr><w:spacing w:after="0" w:line="276"/></w:pPr><w:r><w:pict/></w:r></w:p>'
                     '<w:p><w:r><w:t>GST NO. 27XXXXX</w:t></w:r></w:p>')
with _zf.ZipFile(_tmp, "w") as _z:
    _z.writestr("word/document.xml", _gst)
_out = _zf.ZipFile(_io.BytesIO(drafts.quotation_docx(_tmp, "ASHA D SAMPLE", "Dighi, Pune"))).read("word/document.xml").decode()
_first = _re.findall(r"<w:p[ >].*?</w:p>", _out)[0]
check("a blank line above the GST number is flattened, its picture kept",
      drafts.FLAT in _first and "<w:pict/>" in _first and 'w:line="276"' not in _first, _first[:120])

# ---- a phone's file name in Hindi, or with quote marks: stored and opened again without a crash
for fname in ("बिजली बिल.pdf", 'bill "final".pdf'):
    up = sup.post(f"/api/documents/{cid}/upload?kind=passbook", files={"file": (fname, b"%PDF-1.4 test", "application/pdf")})
    stored = up.json().get("filename", "") if up.status_code == 200 else ""
    back = sup.get(f"/files/docs/{cid}/{stored}") if stored else None
    check(f"an upload named {fname!r} is stored under a plain name and opens again",
          stored.isascii() and '"' not in stored and back is not None and back.status_code == 200, f"{up.status_code} {stored!r}")

sup.post("/api/demo/reset")
print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
