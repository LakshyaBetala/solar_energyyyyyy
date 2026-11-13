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
for good, want in [("250000", "250000"), ("2,50,000", "250000"), ("Rs 285000", "285000"), ("₹ 1,85,000.5", "185000.50"),
                   ("250000.50", "250000.50")]:
    check(f"cost {good!r} -> {want}", valid.cost(good) == want, valid.cost(good))
for bad in ["-250000", "0", "999999999999", "Rs 1.5 lakh", "250000.555", "abc", "1e6", "5000"]:
    check(f"cost {bad!r} refused", refuses(valid.cost, bad))
check("cost keeps paise: never 25000050", valid.cost("250000.50") != "25000050")

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

check("cost 250000.50 saved as 250000.50", put({"rts_cost": "250000.50"}).status_code == 200
      and sup.get(f"/api/registration/{cid}").json()["data"]["rts_cost"] == "250000.50")
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
check("the full number is nowhere in the saved record", good not in sup.get(f"/api/registration/{cid}").text)
from app import db as _db  # noqa: E402
dump = chr(10).join(str(tuple(row)) for (t,) in _db.conn().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                  for row in _db.conn().execute(f"SELECT * FROM {t}"))
check("...nor anywhere in the database, including the audit trail", good not in dump)
check("a wrong check digit is refused with a reason", put({"aadhaar": wrong}).status_code == 400)
check("a bad Aadhaar leaves the saved last 4 alone",
      sup.get(f"/api/registration/{cid}").json()["data"].get("aadhaar_last4") == good[-4:])
check("saving the masked form again changes nothing", put({"aadhaar": "XXXX XXXX " + good[-4:]}).status_code == 200)
check("AI is off by default", sup.get("/api/bootstrap").json().get("llm", {}).get("enabled") is False)

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
check("roof area is never guessed (it is measured on site)", "roof_area" not in v["values"])
check("module technology defaults from settings", bool(v["values"]["module_type"]))
key = sup.post("/api/copilot/key").json()["key"]
look = httpx.get(BASE + "/api/copilot/lookup", params={"cid": cid}, headers={"X-Solara-Key": key}).json()
check("co-pilot is told which values were worked out", set(look["derived"]) == {"module_type", "bank_name", "account_type"}, str(look.get("derived")))
check("co-pilot receives the module technology, not a roof area", "roof_area" not in look["values"] and look["values"].get("module_type"))

# ---- two PINs that disagree: the chosen one is what is kept
from app import db, extract, registration  # noqa: E402
rows = [("PIN code", "411001", "ok"), ("PIN on Aadhaar", "410503", "review")]
for f, val, st in rows:
    db.ex("INSERT INTO extractions(customer_id,field,value,confidence,source,status,note,ts) VALUES(?,?,?,?,?,?,?,?)",
          (cid, f, val, 90, "test", st, "differs", db.now()))
for k in ("pin", "aadhaar_pin"):
    sup.post(f"/api/registration/{cid}/confirm", json={"key": k, "value": "410503"}).raise_for_status()
check("the PIN the owner picked is the one on file", sup.get(f"/api/registration/{cid}").json()["customer"]["pin"] == "410503")
check("a PIN that is not 6 digits is refused", sup.post(f"/api/registration/{cid}/confirm", json={"key": "pin", "value": "41"}).status_code == 400)

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

sup.post("/api/demo/reset")
print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
