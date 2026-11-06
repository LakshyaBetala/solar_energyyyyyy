"""Input rules for the registration fields, in one place. Each function returns the clean value or
raises ValueError with a sentence the owner can act on. Nothing here guesses: a value that does not
fit is refused, never trimmed into something else."""
import re, unicodedata
from decimal import Decimal, InvalidOperation

COST_MIN, COST_MAX = Decimal("10000"), Decimal("2500000")  # Rs; a 0.5-10 kW home system
KW_MIN, KW_MAX = 0.5, 10


def text(v, field):
    """Only plain text or a number may come in; a list, object or true/false is a mistake."""
    if v is None:
        return ""
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        raise ValueError(f"{field} must be typed as plain text")
    return str(v)


def name(v, field="name", required=True):
    n = " ".join(text(v, field).split())
    if not n and not required:
        return ""
    if not 3 <= len(n) <= 60:
        raise ValueError(f"{field} must be 3 to 60 characters")
    letter = lambda ch: unicodedata.category(ch)[0] in "LM"  # letters and the marks that go on them (Marathi)
    if not any(ch.isalpha() for ch in n) or any(not (letter(ch) or ch in " .'-") for ch in n):
        raise ValueError(f"{field} can have letters, spaces, . ' and - only (no digits or symbols)")
    return n


def ok_name(v):
    try:
        name(v)
        return True
    except ValueError:
        return False


def mobile(v):
    raw = text(v, "mobile number")
    n = re.sub(r"\D", "", raw)
    if raw.strip() and not n:
        raise ValueError("the mobile number has digits only; it has none")
    n = n[-10:] if len(n) > 10 and n[:-10] in ("91", "091", "0091") else n
    n = n[1:] if len(n) == 11 and n[0] == "0" else n
    if n and not re.match(r"^[6-9]\d{9}$", n):
        raise ValueError("the mobile number has 10 digits and starts with 6, 7, 8 or 9")
    return n


def consumer_no(v):
    """An MSEDCL consumer number is 12 digits. Spaces and hyphens are allowed in typing."""
    raw = text(v, "consumer number").strip()
    if not raw:
        return ""
    if re.search(r"[^\d\s-]", raw):
        raise ValueError("the consumer number has digits only (spaces and hyphens are fine)")
    n = re.sub(r"\D", "", raw)
    if len(n) != 12:
        raise ValueError(f"the consumer number on an MSEDCL bill has 12 digits; this has {len(n)}")
    if len(set(n)) == 1:
        raise ValueError("that consumer number repeats one digit; check it on the bill")
    return n


def pin(v):
    n = re.sub(r"[\s-]", "", text(v, "PIN code"))
    if n and not re.match(r"^[1-9]\d{5}$", n):
        raise ValueError("the PIN code has 6 digits and does not start with 0")
    return n


def cost(v):
    """Rupees, whole or with up to 2 decimals; 1,50,000 / Rs / ₹ allowed. Kept exactly as typed:
    250000.50 stays 250000.50, it is never cut to 250000 or run together into 25000050."""
    raw = text(v, "installation cost")
    s = re.sub(r"(?i)^\s*(rs\.?|inr|₹)\s*", "", raw).replace(",", "").strip()
    if not s:
        return ""
    if not re.match(r"^\d+(\.\d{1,2})?$", s):
        raise ValueError("the installation cost is an amount in rupees, like 285000 or 285000.50")
    try:
        amt = Decimal(s)
    except InvalidOperation:
        raise ValueError("the installation cost is not a valid amount")
    if not COST_MIN <= amt <= COST_MAX:
        raise ValueError(f"the installation cost should be between Rs {COST_MIN:,.0f} and Rs {COST_MAX:,.0f}")
    return s if "." not in s else f"{amt:.2f}"


def kw(v):
    s = text(v, "capacity").strip()
    if not s:
        return None
    try:
        x = float(s)
    except ValueError:
        raise ValueError("capacity must be a number of kW, e.g. 3 or 3.3")
    if x != x or not KW_MIN <= x <= KW_MAX:
        raise ValueError(f"residential rooftop capacity is between {KW_MIN} and {KW_MAX} kW")
    return x


def email(v):
    s = text(v, "email").strip()
    if s and (len(s) > 120 or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s)):
        raise ValueError("that email address does not look right")
    return s


def aadhaar_last4(v):
    """Only the last 4 digits are ever kept. Accepts 1234 or XXXX XXXX 1234."""
    s = text(v, "Aadhaar").strip()
    m = re.match(r"^(?:[Xx*]{4}[ -]?[Xx*]{4}[ -]?)?(\d{4})$", s)
    if not m:
        raise ValueError("enter only the last 4 digits of the Aadhaar, e.g. 4471")
    return m.group(1)


_D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
      [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
      [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]


def verhoeff_ok(digits):
    """The check digit every real Aadhaar number carries (the Verhoeff algorithm). No lookup, no network."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def aadhaar_number(v):
    """A full 12-digit Aadhaar number, checked fully on this computer (format and check digit).
    Returns only its last 4 digits: the full number is checked and dropped, never stored or logged."""
    raw = text(v, "Aadhaar number").strip()
    if re.search(r"[^\d\s-]", raw):
        raise ValueError("the Aadhaar number has digits only (spaces and hyphens are fine)")
    n = re.sub(r"\D", "", raw)
    if len(n) != 12:
        raise ValueError(f"the Aadhaar number has 12 digits; this has {len(n)}")
    if n[0] in "01":
        raise ValueError("an Aadhaar number never starts with 0 or 1; check it on the card")
    if not verhoeff_ok(n):
        raise ValueError("this Aadhaar number does not pass the check-digit test; check each digit on the card")
    return n[-4:]


def aadhaar_any(v):
    """What the Details box takes: the full number (checked, then only the last 4 kept), the last 4
    alone, or the masked form Solara already shows. Returns the last 4."""
    s = text(v, "Aadhaar").strip()
    return aadhaar_number(s) if len(re.sub(r"\D", "", s)) == 12 else aadhaar_last4(s)


def ifsc(v):
    s = text(v, "IFSC").strip().upper()
    if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", s):
        raise ValueError("the IFSC code has 11 characters, like MAHB0000412")
    return s


def app_no(v):
    s = text(v, "application number").strip().upper()
    if not re.match(r"^NP-[A-Z0-9]+-\d{6,}$", s):
        raise ValueError("the application number looks like NP-MHSED26-16165074")
    return s
