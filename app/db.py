import sqlite3, hashlib, hmac, os, threading, json
from datetime import datetime, timedelta
from .config import DB_PATH

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE, name TEXT, role TEXT, pw TEXT);

CREATE TABLE IF NOT EXISTS customers(
  id TEXT PRIMARY KEY, name TEXT, aadhaar_name TEXT, place TEXT, consumer_no TEXT,
  kw REAL, category TEXT, stage TEXT, application_no TEXT, subsidy INTEGER,
  last_activity TEXT, blocked_note TEXT, pin TEXT, address TEXT, bank TEXT,
  workflow TEXT, discom_ref TEXT);

CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, username TEXT, created_at TEXT);

-- DISCOM-side service requests: new connection, load enhancement, load reduction
CREATE TABLE IF NOT EXISTS portal_requests(
  request_no TEXT PRIMARY KEY, kind TEXT, consumer_no TEXT, applicant TEXT,
  current_load REAL, requested_load REAL, submitted_at TEXT, payload TEXT);

CREATE TABLE IF NOT EXISTS numbers(
  id INTEGER PRIMARY KEY, msisdn TEXT UNIQUE, customer_id TEXT, assigned_at TEXT,
  expires_at TEXT, otp_count INTEGER DEFAULT 0, status TEXT DEFAULT 'free');

CREATE TABLE IF NOT EXISTS sms(
  id INTEGER PRIMARY KEY, msisdn TEXT, sender TEXT, body TEXT, code TEXT,
  ts TEXT, read_at TEXT);

CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, customer_id TEXT, kind TEXT, filename TEXT,
  path TEXT, bytes INTEGER, uploaded_at TEXT);

CREATE TABLE IF NOT EXISTS extractions(
  id INTEGER PRIMARY KEY, customer_id TEXT, field TEXT, value TEXT,
  confidence INTEGER, source TEXT, status TEXT, note TEXT, ts TEXT);

CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY, customer_id TEXT, workflow TEXT, status TEXT,
  started_at TEXT, finished_at TEXT, application_no TEXT, started_by TEXT,
  headless INTEGER DEFAULT 1, retries INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS run_steps(
  id INTEGER PRIMARY KEY, run_id INTEGER, idx INTEGER, key TEXT, label TEXT,
  status TEXT, note TEXT, ms INTEGER);

CREATE TABLE IF NOT EXISTS run_events(
  id INTEGER PRIMARY KEY, run_id INTEGER, ts TEXT, level TEXT, message TEXT);

CREATE TABLE IF NOT EXISTS holds(
  id INTEGER PRIMARY KEY, run_id INTEGER, kind TEXT, status TEXT, context TEXT,
  created_at TEXT, resolved_at TEXT, resolved_by TEXT, resolution TEXT);

CREATE TABLE IF NOT EXISTS screenshots(
  id INTEGER PRIMARY KEY, run_id INTEGER, step_key TEXT, label TEXT, kind TEXT,
  path TEXT, ts TEXT);

CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, role TEXT, action TEXT,
  target TEXT, detail TEXT);

CREATE TABLE IF NOT EXISTS calls(
  id TEXT PRIMARY KEY, customer_id TEXT, lang TEXT, duration TEXT, outcome TEXT,
  goal TEXT, when_label TEXT, transcript TEXT);

-- DISCOM-side consumer register. Deliberately holds the bill spelling of the name,
-- which is what makes the portal reject our Aadhaar spelling.
CREATE TABLE IF NOT EXISTS portal_consumers(
  consumer_no TEXT PRIMARY KEY, billed_name TEXT, address TEXT, pin TEXT,
  sanctioned_load REAL, tariff TEXT, msisdn TEXT, avg_units INTEGER, meter_no TEXT);

CREATE TABLE IF NOT EXISTS portal_applications(
  application_no TEXT PRIMARY KEY, consumer_no TEXT, applicant_name TEXT,
  capacity REAL, submitted_at TEXT, payload TEXT);

CREATE TABLE IF NOT EXISTS portal_sessions(
  sid TEXT PRIMARY KEY, consumer_no TEXT, stage TEXT, otp TEXT, otp_tries INTEGER
  DEFAULT 0, captcha TEXT, data TEXT, created_at TEXT);

-- Close-out: what was installed, and the documents generated from it
CREATE TABLE IF NOT EXISTS closeout(
  customer_id TEXT PRIMARY KEY, data TEXT, updated_at TEXT, updated_by TEXT);

-- E-sign. A request is a link sent to the customer for a set of documents; docs maps each
-- document to the hash of the exact content shown to them.
CREATE TABLE IF NOT EXISTS sign_requests(
  token TEXT PRIMARY KEY, customer_id TEXT, docs TEXT, created_by TEXT, created_at TEXT,
  expires_at TEXT, status TEXT, attempts INTEGER DEFAULT 0, verify_secret TEXT,
  signed_at TEXT, signer_name TEXT, ip TEXT, ua TEXT);
-- role 'consumer' (per customer) or 'vendor' (customer_id NULL, the company's signatory)
CREATE TABLE IF NOT EXISTS signatures(
  id INTEGER PRIMARY KEY, customer_id TEXT, role TEXT, name TEXT, path TEXT,
  created_at TEXT, request_token TEXT);
-- A signature is only ever placed on a document whose current hash has an approval row
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY, customer_id TEXT, doc_key TEXT, doc_hash TEXT,
  request_token TEXT, ts TEXT);

CREATE TABLE IF NOT EXISTS copilot_keys(
  key_hash TEXT PRIMARY KEY, username TEXT, created_at TEXT);

-- MSEDCL rooftop portal sandbox: files received per application and document slot
CREATE TABLE IF NOT EXISTS msedcl_uploads(
  application_id TEXT, slot INTEGER, filename TEXT, bytes INTEGER, ts TEXT);
"""


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
            have = {r[1] for r in _conn.execute("PRAGMA table_info(customers)")}
            for col in ("workflow", "discom_ref"):
                if col not in have:
                    _conn.execute(f"ALTER TABLE customers ADD COLUMN {col} TEXT")
            _conn.commit()
        return _conn


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def ex(sql, args=()):
    with _lock:
        c = conn().execute(sql, args)
        conn().commit()
        return c.lastrowid


def now():
    return datetime.now().isoformat(timespec="seconds")


def hhmmss():
    return datetime.now().strftime("%H:%M:%S")


def pwhash(p, salt=None):
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(p.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def pwcheck(p, stored):
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, _ = stored.split("$")
    return hmac.compare_digest(pwhash(p, bytes.fromhex(salt)), stored)


def audit(actor, role, action, target="", detail=""):
    ex(
        "INSERT INTO audit(ts,actor,role,action,target,detail) VALUES(?,?,?,?,?,?)",
        (now(), actor, role, action, target, detail),
    )


CUSTOMERS = [
    # id, crm name, aadhaar name, place, consumer_no, kW, category, stage, ref, subsidy, last, blocked, pin, address, bank, workflow
    ("SS-2041", "Mangesh Kulkarni", "Mangesh Anil Kulkarni", "Kothrud, Pune", "170024518893", 3, "Residential", "disbursed", "PMSG/MH/2026/118842", 78000, "4 Oct", None, "411038", "Flat 7, Shivtirth Nagar, Kothrud, Pune", "XXXXXX3310 / MAHB0000221", "rooftop_registration"),
    ("SS-2042", "Asha Deshpande", "Asha Vinayak Deshpande", "Nashik Road, Nashik", "170031277450", 5, "Residential", "install", "PMSG/MH/2026/121907", 78000, "22 Oct", None, "422101", "Plot 61, Jatra Hotel Road, Nashik Road", "XXXXXX8841 / SBIN0004012", "rooftop_registration"),
    ("SS-2043", "Royal Classic CHS Ltd.", "Royal Classic Co-op Housing Society Ltd.", "Baner, Pune", "170029903114", 40, "Housing society", "feasible", "PMSG/MH/2026/122416", 0, "23 Oct", None, "411045", "Survey 112, Baner Road, Pune", "XXXXXX5520 / HDFC0000412", "rooftop_registration"),
    ("SS-2044", "Irfan Shaikh", "Irfan Yusuf Shaikh", "Satpur MIDC, Nashik", "170044120867", 25, "Commercial", "docs", None, 0, "25 Oct", "Commercial connection, not covered by PM Surya Ghar. Net-metering application only; GST certificate pending", "422007", "W-18 Satpur MIDC, Nashik", "XXXXXX1174 / ICIC0000765", None),
    ("SS-2045", "Vaishali Pawar", "Vaishali Dattatray Pawar", "Panchavati, Nashik", "170038865021", 3, "Residential", "docs", None, 78000, "26 Oct", None, "422003", "Plot 14, Ganga Nagar, Panchavati, Nashik", "XXXXXX7792 / MAHB0000412", "rooftop_registration"),
    ("SS-2046", "Gurudatta Agro Industries", "Gurudatta Agro Industries Pvt Ltd", "Sinnar, Nashik", "170051340226", 100, "Industrial", "netmeter", "NM/MH/2026/04417", 0, "21 Oct", None, "422103", "Gat 204, Sinnar MIDC, Nashik", "XXXXXX2298 / AXIS0000118", None),
    ("SS-2047", "Prakash Jadhav", "Prakash Namdev Jadhav", "Hadapsar, Pune", "170027714309", 2, "Residential", "register", None, 60000, "26 Oct", "OTP not received; assigned number expires in 3 days", "411028", "Lane 4, Sasanenagar, Hadapsar, Pune", "XXXXXX6603 / BKID0000901", "rooftop_registration"),
    ("SS-2048", "Sheetal Rane", "Sheetal Mahesh Rane", "Gangapur Road, Nashik", "170036002985", 4, "Residential", "claim", "PMSG/MH/2026/120771", 78000, "24 Oct", None, "422013", "Row House 3, Gangapur Road, Nashik", "XXXXXX4417 / MAHB0000733", "rooftop_registration"),
    ("SS-2049", "Rahul Shinde", "Rahul Sanjay Shinde", "Pimple Saudagar, Pune", "170041190358", 5, "Residential", "lead", None, 78000, "26 Oct", "Sanctioned load 3 kW is below the 5 kW plant. Load enhancement must be filed with the DISCOM first", "411027", "Flat 902, Roseland Residency, Pimple Saudagar, Pune", "XXXXXX5031 / SBIN0011245", "load_enhancement"),
    ("SS-2050", "Sunita Patil", "Sunita Ramesh Patil", "Makhmalabad, Nashik", None, 5, "Residential", "lead", None, 0, "27 Oct", "New bungalow with no supply connection. A new LT connection must be applied for before any solar paperwork", "422003", "Plot 7, Shivkrupa Colony, Makhmalabad Road, Nashik", "XXXXXX2210 / BKID0000417", "new_connection"),
]

WORKFLOWS = {
    "rooftop_registration": "New rooftop registration",
    "load_enhancement": "Sanctioned load enhancement",
    "load_reduction": "Sanctioned load reduction",
    "new_connection": "New LT connection",
}

# billed_name is the DISCOM record: uppercase, initials instead of the full middle name
PORTAL_CONSUMERS = [
    ("170024518893", "MANGESH A KULKARNI", "FLAT 7 SHIVTIRTH NAGAR KOTHRUD PUNE", "411038", 3.0, "LT-I RES", "9028144517", 288, "MSEDCL/9001188"),
    ("170031277450", "ASHA V DESHPANDE", "PLOT 61 JATRA HOTEL ROAD NASHIK ROAD", "422101", 5.0, "LT-I RES", "9028144520", 402, "MSEDCL/9002233"),
    ("170029903114", "ROYAL CLASSIC CO-OP HSG SOC LTD", "SURVEY 112 BANER ROAD PUNE", "411045", 40.0, "LT-II COMM", "9028144522", 5120, "MSEDCL/9003011"),
    ("170044120867", "IRFAN Y SHAIKH", "W-18 SATPUR MIDC NASHIK", "422007", 25.0, "LT-V IND", "9028144529", 3180, "MSEDCL/9003744"),
    ("170038865021", "VAISHALI D PAWAR", "PLOT 14 GANGA NAGAR PANCHAVATI NASHIK", "422003", 3.0, "LT-I RES", "9028144531", 312, "MSEDCL/9004471"),
    ("170051340226", "GURUDATTA AGRO INDUSTRIES PVT LTD", "GAT 204 SINNAR MIDC NASHIK", "422103", 100.0, "LT-V IND", "9028144519", 14200, "MSEDCL/9005120"),
    ("170027714309", "PRAKASH N JADHAV", "LANE 4 SASANENAGAR HADAPSAR PUNE", "411028", 2.0, "LT-I RES", "9028144526", 194, "MSEDCL/9005880"),
    ("170036002985", "SHEETAL M RANE", "ROW HOUSE 3 GANGAPUR ROAD NASHIK", "422013", 4.0, "LT-I RES", "9028144524", 356, "MSEDCL/9006404"),
    ("170041190358", "RAHUL S SHINDE", "FLAT 902 ROSELAND RESIDENCY PIMPLE SAUDAGAR PUNE", "411027", 3.0, "LT-I RES", "9028144535", 410, "MSEDCL/9007712"),
]

NUMBERS = [
    ("+91 90281 44517", "SS-2041", 12, 9, "expiring"),
    ("+91 90281 44519", "SS-2046", 38, 14, "active"),
    ("+91 90281 44520", "SS-2042", 44, 11, "active"),
    ("+91 90281 44522", "SS-2043", 57, 6, "active"),
    ("+91 90281 44524", "SS-2048", 61, 8, "active"),
    ("+91 90281 44526", "SS-2047", 3, 4, "expiring"),
    ("+91 90281 44529", "SS-2044", 71, 2, "active"),
    ("+91 90281 44531", "SS-2045", 87, 1, "active"),
    ("+91 90281 44534", None, 90, 0, "free"),
    ("+91 90281 44535", "SS-2049", 89, 0, "active"),
    ("+91 90281 44537", "SS-2050", 90, 0, "active"),
]

CALLS = [
    ("C-6612", "SS-2044", "Hindi", "2:41", "Documents promised", "Document reminder: GST certificate and sanctioned load proof", "Today 11:04", [
        ["agent", "नमस्ते, मैं सूर्य ऊर्जा टीम से बोल रहा हूँ। आपके 25 किलोवाट सोलर आवेदन के लिए दो दस्तावेज़ बाक़ी हैं।", "Hello, calling from the solar team. Two documents are still pending for your 25 kW application."],
        ["customer", "हाँ बताइए, कौन से?", "Yes, tell me, which ones?"],
        ["agent", "जीएसटी प्रमाणपत्र और स्वीकृत भार का प्रमाण। व्हाट्सऐप पर भेज दीजिए तो आज ही पोर्टल पर जमा कर देंगे।", "GST certificate and sanctioned load proof. Send them on WhatsApp and we will file on the portal today."],
        ["customer", "ठीक है, शाम तक भेज देता हूँ।", "Fine, I will send them by evening."],
        ["agent", "धन्यवाद। शाम छह बजे तक न मिले तो एक रिमाइंडर भेजूँगा।", "Thank you. If I do not receive them by 6 pm I will send a reminder."]]),
    ("C-6609", "SS-2045", "Marathi", "3:18", "Site visit booked, 2 Nov 11:00", "Site survey scheduling and roof access confirmation", "Today 10:12", [
        ["agent", "नमस्कार, मी सूर्य ऊर्जा टीममधून बोलत आहे. तुमच्या ३ किलोवॅट छतावरील सोलर अर्जासाठी सर्व्हे ठरवायचा आहे.", "Hello, calling from the solar team. We need to schedule the survey for your 3 kW rooftop application."],
        ["customer", "हो, पण सकाळी घरी कोणी नसतं.", "Yes, but nobody is home in the morning."],
        ["agent", "चालेल. २ नोव्हेंबरला सकाळी अकरा वाजता जमेल का? अभियंता दोन तास थांबेल.", "That is fine. Would 2 November at 11 am work? The engineer will stay about two hours."],
        ["customer", "अकरा वाजता चालेल.", "Eleven works."],
        ["agent", "नोंद झाली. छतावर जाण्याची शिडी आणि मीटरजवळची जागा मोकळी ठेवा.", "Noted. Please keep the roof ladder available and the area near the meter clear."],
        ["customer", "ठीक, धन्यवाद.", "Okay, thank you."]]),
    ("C-6604", "SS-2047", "Marathi", "1:52", "Escalated to staff", "Registration status update after OTP delivery failure", "Yesterday 17:35", [
        ["agent", "नमस्कार, तुमच्या अर्जाची नोंदणी ओटीपी न आल्यामुळे थांबली आहे.", "Hello, your registration is on hold because the OTP did not arrive."],
        ["customer", "मला काहीच मेसेज आला नाही. दुसरा नंबर देऊ का?", "I received no message at all. Should I give another number?"],
        ["agent", "तुमचा निर्णय कार्यालयातील सहकाऱ्याकडे देतो, ते दोन मिनिटांत कॉल करतील.", "I am handing this to a colleague in the office; they will call you within two minutes."]]),
]

SEED_AUDIT = [
    ("system", "system", "Worker started", "", "chromium · isolated profile per consumer"),
    ("r.deshmukh", "supervisor", "Approved final submission", "SS-2048", "PMSG/MH/2026/120771"),
    ("agent", "agent", "Subsidy claim filed", "SS-2048", "acknowledgement captured"),
    ("agent", "agent", "AI call completed", "SS-2045", "C-6609 · site visit booked 2 Nov 11:00"),
    ("s.kale", "operator", "Released number", "+91 90281 44515", "retention expired"),
    ("agent", "agent", "AI call completed", "SS-2044", "C-6612 · documents promised by 18:00"),
]


# Post-installation details as the field team reports them. SS-2042 is complete and waiting
# only on signatures; SS-2048 is half entered, the way most backlog files start.
CLOSEOUT = {
    "SS-2042": {"msedcl_app_id": "79435901", "install_date": "2026-10-21",
                "agreement_date": "2026-10-02", "rts_cost": "285000", "invoice_no": "INV/26-27/0412",
                "aadhaar_last4": "4471", "billing_unit": "4642 Nashik Road", "phase": "Single phase",
                "module_make": "Premier Energies", "almm_model": "PE-M144-550", "module_wp": "550",
                "module_count": "9",
                "module_serials": "\n".join(f"PE55026A{n:06d}" for n in range(318410, 318419)),
                "cell_maker": "Premier Energies", "cell_invoice": "PEL/26/88412", "warranty": "10 + 25",
                "inverter_make": "Polycab PSIS-5K", "inverter_kw": "5", "inverter_serial": "PSIS5K26A01877",
                "inverter_year": "2026", "meter_serial": "GM2611042", "earthing_count": "3",
                "earth_ohm": "1.5", "lightning_arrester": "Yes", "protection_checks": "Yes",
                "dcr_cert_no": "7201-5530-1188-2042"},
    "SS-2048": {"msedcl_app_id": "79436117", "install_date": "2026-10-08",
                "agreement_date": "2026-09-14", "rts_cost": "232000", "phase": "Single phase",
                "module_make": "Premier Energies", "module_wp": "550", "module_count": "7",
                "inverter_make": "Polycab PSIS-4K", "inverter_kw": "4"},
}


def seed_closeout():
    for cid, d in CLOSEOUT.items():
        ex("INSERT OR REPLACE INTO closeout(customer_id,data,updated_at,updated_by) VALUES(?,?,?,?)",
           (cid, json.dumps(d), now(), "seed"))


def seeded():
    return bool(one("SELECT 1 FROM users LIMIT 1"))


def seed():
    if seeded():
        return False
    for u, n, r in [("r.deshmukh", "Rohit Deshmukh", "supervisor"),
                    ("s.kale", "Sneha Kale", "operator"),
                    ("a.more", "Amit More", "viewer")]:
        ex("INSERT INTO users(username,name,role,pw) VALUES(?,?,?,?)", (u, n, r, pwhash("demo")))

    for c in CUSTOMERS:
        ex("""INSERT INTO customers(id,name,aadhaar_name,place,consumer_no,kw,category,stage,
              application_no,subsidy,last_activity,blocked_note,pin,address,bank,workflow)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", c)

    for pc in PORTAL_CONSUMERS:
        ex("""INSERT INTO portal_consumers(consumer_no,billed_name,address,pin,sanctioned_load,
              tariff,msisdn,avg_units,meter_no) VALUES(?,?,?,?,?,?,?,?,?)""", pc)

    for msisdn, cid, days, otps, st in NUMBERS:
        ex("""INSERT INTO numbers(msisdn,customer_id,assigned_at,expires_at,otp_count,status)
              VALUES(?,?,?,?,?,?)""",
           (msisdn, cid, now(), (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds"), otps, st))

    for cid, cust, lang, dur, out, goal, when, tr in CALLS:
        ex("""INSERT INTO calls(id,customer_id,lang,duration,outcome,goal,when_label,transcript)
              VALUES(?,?,?,?,?,?,?,?)""", (cid, cust, lang, dur, out, goal, when, json.dumps(tr, ensure_ascii=False)))

    for actor, role, action, target, detail in SEED_AUDIT:
        audit(actor, role, action, target, detail)
    seed_closeout()
    return True
