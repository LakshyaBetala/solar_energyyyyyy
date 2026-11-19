"""Which value the Chrome helper puts in which box: its rule table, read from extension/panel.js as it is and
run in a browser against labels. No server needed.

  python tests/rules.py

The rules decide what is typed into a government form, so the dangerous look-alikes are pinned here: the Aadhaar
number only into a box that asks for it, never a Virtual ID, a "uid" (often a user id) or a box that merely
mentions the Aadhaar; no bank box on a loan form except on the step for the customer's own account; and the
customer's own name, mobile, address, PAN or date of birth never into a box about somebody else.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = (Path(__file__).resolve().parent.parent / "extension" / "panel.js").read_text(encoding="utf-8")
A = SRC.index("const RULES = [")
TABLE = SRC[A + len("const RULES = "):SRC.index("\n  ];", A) + 4].rstrip().rstrip(";")
LOAN, PLAIN = "jan samarth loan application basic details", "pm surya ghar national portal subsidy bank details"
NEVER, UNKNOWN = "never", "not known"   # never touched (null) / left for the person, can be taught (undefined)

CASES = [  # label as the helper reads it, the page's text, is it the customer's-own-account step, the value that goes in
    # the Aadhaar number
    ("aadhar no first", LOAN, False, "aadhaar"), ("aadhar no second", LOAN, False, "aadhaar"), ("aadhar no third", LOAN, False, "aadhaar"),
    ("aadhaar number", PLAIN, False, "aadhaar"), ("aadhaar no", PLAIN, False, "aadhaar"), ("aadhaar card number", PLAIN, False, "aadhaar"),
    ("aadhaar card no", PLAIN, False, "aadhaar"), ("enter aadhaar number or virtual id", PLAIN, False, "aadhaar"),
    ("aadhaar virtual id mat radio group 0", LOAN, False, NEVER), ("vid no first", LOAN, False, NEVER), ("virtual no first", LOAN, False, NEVER), ("uid", PLAIN, False, NEVER),
    ("aadhaar otp", PLAIN, False, NEVER), ("mobile number linked with aadhaar number", PLAIN, False, "mobile"),
    ("email linked with aadhaar no", PLAIN, False, "email"), ("name as per aadhaar", PLAIN, False, "aadhaar_name"),
    ("name as per aadhaar number", PLAIN, False, "aadhaar_name"), ("aadhaar nominee", PLAIN, False, UNKNOWN), ("aadhaar notified area", PLAIN, False, UNKNOWN),
    ("co applicant aadhaar number", LOAN, False, UNKNOWN), ("guarantor aadhaar no", LOAN, False, UNKNOWN),
    ("last 4 digits of aadhaar number", PLAIN, False, NEVER), ("aadhaarno", PLAIN, False, "aadhaar"),
    # banks: nothing on a loan form, except on the step that asks for the customer's own account
    ("bank name", LOAN, False, NEVER), ("ifsc code", LOAN, False, NEVER), ("select bank", LOAN, False, NEVER), ("bank", LOAN, False, NEVER),
    ("preferred bank", LOAN, False, NEVER), ("account number", LOAN, False, NEVER), ("loan amount", LOAN, False, NEVER),
    ("bank name", LOAN, True, "bank_name"), ("ifsc code", LOAN, True, "ifsc"), ("account holder name", LOAN, True, "account_holder"),
    ("account type", LOAN, True, "account_type"), ("account number", LOAN, True, NEVER),
    ("bank name", PLAIN, False, "bank_name"), ("ifsc", PLAIN, False, "ifsc"), ("account number", PLAIN, False, NEVER),
    ("account number", "pm surya ghar installation details", False, UNKNOWN),
    ("consumer account number", PLAIN, False, "consumer_no"), ("consumer account number", LOAN, False, "consumer_no"),
    # somebody else's details, a second contact, a further address line: left for the person
    ("name of father", LOAN, False, UNKNOWN), ("father s name", LOAN, False, UNKNOWN), ("father husband name", LOAN, False, UNKNOWN),
    ("spouse name", LOAN, False, UNKNOWN), ("mother s maiden name", LOAN, False, UNKNOWN), ("name of employer", LOAN, False, UNKNOWN),
    ("employer name", LOAN, False, UNKNOWN), ("co applicant mobile number", LOAN, False, UNKNOWN), ("alternate mobile number", LOAN, False, UNKNOWN),
    ("guarantor pan", LOAN, False, UNKNOWN), ("date of birth of co applicant", LOAN, False, UNKNOWN), ("nominee name", LOAN, False, UNKNOWN),
    ("name of village", PLAIN, False, UNKNOWN), ("name of bank", PLAIN, False, UNKNOWN), ("name of organisation", LOAN, False, UNKNOWN),
    ("office address", LOAN, False, UNKNOWN), ("address line 2", LOAN, False, UNKNOWN), ("landmark", LOAN, False, UNKNOWN),
    # the customer's own, and the neighbours that must keep working
    ("name", LOAN, False, "name"), ("name as per electricity bill", PLAIN, False, "name"), ("name of the applicant", LOAN, False, "name"),
    ("name of consumer", PLAIN, False, "name"), ("full name", LOAN, False, "name"), ("customer name", PLAIN, False, "name"),
    ("borrower name", LOAN, False, "name"), ("applicant name", LOAN, False, "name"),
    ("address", LOAN, False, "address"), ("address line 1", LOAN, False, "address"), ("permanent address", LOAN, False, "address"),
    ("date of birth", LOAN, False, "dob"), ("pan", LOAN, False, "pan"), ("pan number", LOAN, False, "pan"), ("gram panchayat", PLAIN, False, "panchayat"),
    ("mobile number", LOAN, False, "mobile"), ("email id", LOAN, False, "email"), ("pin code", LOAN, False, "pin"),
    ("district", LOAN, False, "district"), ("state", LOAN, False, "state"),
    ("electricity distribution company", PLAIN, False, "discom"), ("name of vendor employee who visited", PLAIN, False, "visitor_name"),
    ("name of the vendor", PLAIN, False, "vendor"),
    ("password", PLAIN, False, NEVER), ("enter otp", PLAIN, False, NEVER), ("captcha", PLAIN, False, NEVER),
    # Jan Samarth's own names for its boxes
    ("solar roof top application id", LOAN, False, "application_no"), ("discom consumer id", LOAN, False, "consumer_no"),
    ("first name", LOAN, False, "first_name"), ("middle name", LOAN, False, "middle_name"), ("last name", LOAN, False, "last_name"),
    ("father first name", LOAN, False, UNKNOWN), ("name of lender", LOAN, False, NEVER), ("project cost", LOAN, False, "rts_cost"),
    ("required loan amount", LOAN, False, NEVER), ("gross annual income", LOAN, False, UNKNOWN),
]

RUN = """([table, cases]) => {
  let own = false; const ownAccountStep = () => own;   // the page's own-account test, set per case
  const RULES = eval(table);
  return cases.map(([label, pg, o]) => { own = o;
    const r = RULES.find(([re, , ctx]) => re.test(label) && (!ctx || (typeof ctx === 'function' ? ctx(pg) : ctx.test(pg))));
    return !r || r[1] === undefined ? 'not known' : r[1] === null ? 'never' : r[1]; });
}"""

with sync_playwright() as p:
    b = p.chromium.launch()
    got = b.new_page().evaluate(RUN, [TABLE, [list(c[:3]) for c in CASES]])
    b.close()

PASS, FAIL = 0, 0
for (label, pg, own, want), g in zip(CASES, got):
    if g == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  \"{label}\" on {'a loan page' if pg == LOAN else 'a plain page'}{' (own-account step)' if own else ''}: {g}, wanted {want}")
print(f"  PASS  {PASS} labels go where they should" if not FAIL else f"  {FAIL} label(s) go to the wrong value")
print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
