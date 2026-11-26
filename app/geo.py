"""Latitude, longitude and urban/rural for an address, from OpenStreetMap's free Nominatim service.
The address is sent to that service (no key, no account). Only an operator's action or a co-pilot lookup
for a customer that has no coordinates yet calls this. A failure returns None; nothing is guessed."""
import re
import httpx

URL = "https://nominatim.openstreetmap.org/search"
# the portal's own lists for Pune district (read from the portal's dropdowns); a value is kept only if it matches one
ULB_PUNE = ["Alandi", "Baramati", "Bhor", "Chakan", "Daund", "Dehu", "Dehurood", "Indapur", "Jejuri", "Junnar", "Khadki",
            "Lonavala", "Malegaon Budruk", "Manchar", "Pimpri Chinchwad", "Pune", "Rajgurunagar", "Sasvad", "Shirur",
            "Talegaon Dabhade", "Vadgaon Mawal", "Wadgaon"]
TALUKA_PUNE = ["Ambegaon", "Baramati", "Bhor", "Daund", "Haveli", "Indapur", "Junnar", "Khed", "Maval", "Mulshi",
               "Purandar", "Shirur", "Velhe"]
_flat = lambda t: re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def canon(name, options):
    """The portal's spelling of a place, or '' when none of the options is a sure match (never a guess)."""
    n = _flat(name)
    if not n:
        return ""
    for o in options:
        if _flat(o) == n:
            return o
    hit = [o for o in options if len(_flat(o)) > 3 and (_flat(o) in n or n in _flat(o))]
    return hit[0] if len(hit) == 1 else ""


def from_address(address, options):
    """A place from the list that the address names, only when exactly one does."""
    t = _flat(address)
    hit = [o for o in options if len(_flat(o)) > 3 and _flat(o) in t]
    return hit[0] if len(hit) == 1 else ""


UA = {"User-Agent": "Solara-backoffice/1.0 (solar installer CRM)"}
URBAN = ("city", "town", "suburb", "city_district", "neighbourhood", "quarter", "borough")
RURAL = ("village", "hamlet", "isolated_dwelling")
RURAL_WORDS = re.compile(r"\b(village|gram|gaon|gav|wadi|vasti|tal\.?|taluka|tq)\b", re.I)


def _ask(q):
    r = httpx.get(URL, params={"q": q, "format": "jsonv2", "addressdetails": 1, "limit": 1, "countrycodes": "in"},
                  headers=UA, timeout=7)
    r.raise_for_status()
    hits = r.json()
    return hits[0] if hits else None


def locate(address, pin=""):
    """{'lat','lng','kind':'Urban'|'Rural'|None,'accuracy':'address'|'area','found':'text'} or None.
    Tries the whole address, then shorter ones (the house number and building drop off first), then the PIN."""
    parts = [p.strip() for p in re.split(r"[,\n]+", address or "") if p.strip()]
    tries = [", ".join(parts[i:] + ([pin] if pin else [])) for i in range(min(len(parts), 4))] if parts else []
    if parts:   # "Shiv Sai Nagar SNO 72/3B Dighi, Pune": the plot and house words drop off, the area name stays
        words = [w for w in re.split(r"\s+", re.split(r"\b(?:nr|near)\b", parts[0], flags=re.I)[0]) if not re.search(r"\d|^(sno|s\.no|nr|near|plot|flat|gat|survey)$", w, re.I)]
        if len(words) > 1:
            tries.insert(1, ", ".join([" ".join(words[-1:])] + parts[1:] + ([pin] if pin else [])))
    if pin:
        tries.append(pin)
    seen = set()
    for n, q in enumerate(t for t in tries if t and not (t in seen or seen.add(t))):
        try:
            hit = _ask(q + ", India")
        except (httpx.HTTPError, ValueError):
            return None
        if hit:
            a = hit.get("address", {})
            kind = "Urban" if any(k in a for k in URBAN) else "Rural" if any(k in a for k in RURAL) else None
            if RURAL_WORDS.search(address or "") and kind != "Urban":
                kind = "Rural"
            town = a.get("city") or a.get("town") or a.get("municipality") or ""
            sub = re.sub(r"(?i)\s*sub-?district$", "", a.get("county") or a.get("state_district") or "")
            return {"lat": round(float(hit["lat"]), 6), "lng": round(float(hit["lon"]), 6), "kind": kind,
                    "ulb": (canon(town, ULB_PUNE) or from_address(address, ULB_PUNE)) if kind == "Urban" else "",
                    "taluka": (canon(sub, TALUKA_PUNE) or from_address(address, TALUKA_PUNE)) if kind == "Rural" else "",
                    "accuracy": "address" if n == 0 else "area", "found": hit.get("display_name", "")[:160]}
    return None
