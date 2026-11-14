"""The two documents made once a customer's details are in, both filled into the client's own templates:

- the vendor-consumer agreement: the draft PDF in "agreement draft/", written onto at its blanks (date,
  customer name and address on page 1; both parties' name, address and date on page 4);
- the bank quotation: the Word file in the quotation folder for the chosen installation cost, with the date,
  the customer's name and their place changed; the outward number is kept as it is.

The templates are the client's files and stay out of the repository (it is public); their folders are found
beside the code, or through SOLARA_AGREEMENT_DIR and SOLARA_QUOTES_DIR.
"""
import html, io, os, re, zipfile
from datetime import date
from pathlib import Path
from .config import ROOT

FONT_FILE = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "calibri.ttf"   # the draft is set in Calibri


def agreement_template():
    folder = Path(os.environ.get("SOLARA_AGREEMENT_DIR") or ROOT / "agreement draft")
    pdfs = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
    if not pdfs:
        raise FileNotFoundError(f"no agreement draft (a PDF) in {folder}")
    return pdfs[0]


def vendor_from_draft(text):
    """The second party exactly as the draft prints it: (name, registered office)."""
    t = " ".join(text.split())
    m = re.search(r"\bAnd (.+?) having registered office at (.+?) \(hereinafter", t)
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", "")


def inr(amount):
    """Rupees with Indian grouping: 185000 -> 1,85,000."""
    s = str(int(round(float(amount))))
    head, tail = s[:-3], s[-3:]
    return (re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head) + "," if head else "") + tail


def agreement_pdf(name, address, when=None, cost=None):
    import fitz
    when = when or date.today()
    doc = fitz.open(agreement_template())
    font = fitz.Font(fontfile=str(FONT_FILE)) if FONT_FILE.exists() else fitz.Font("helv")
    vname, vaddr = vendor_from_draft(doc[0].get_text())
    p1, p4 = doc[0], doc[3]
    for p in (p1, p4):
        p.wrap_contents()   # page 4 leaves its drawing state flipped; isolate it so what is added stands upright

    def spans(page):
        return [s for b in page.get_text("dict")["blocks"] for ln in b.get("lines", []) for s in ln["spans"]]

    def find(page, text, nth=0, after_x=None, line_of=None):
        """A printed word with its baseline and size, from the draft itself, so what is added matches it."""
        hits = [w for w in page.get_text("words") if w[4] == text and (after_x is None or w[0] > after_x)
                and (line_of is None or abs(w[1] - line_of[1]) < 2)]
        w = hits[nth]
        s = next(s for s in spans(page) if fitz.Rect(s["bbox"]).intersects(fitz.Rect(w[:4])))
        return {"x0": w[0], "x1": w[2], "y0": w[1], "y1": w[3], "base": s["origin"][1], "size": s["size"]}

    def write(page, x, base, text, size):
        tw = fitz.TextWriter(page.rect)
        tw.append((x, base), text, font=font, fontsize=size)
        tw.write_text(page)

    def wrap(text, width, size):
        """Lines that each fit the width; a single word longer than the width keeps its own line."""
        lines, cur = [], ""
        for w in text.split():
            t = f"{cur} {w}".strip()
            if cur and font.text_length(t, size) > width:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines = lines + [cur] if cur else lines
        if len(lines) == 2:   # two lines: split where they come out most even, never one word left alone
            words = text.split()
            cuts = [(" ".join(words[:k]), " ".join(words[k:])) for k in range(1, len(words))]
            fit = [c for c in cuts if font.text_length(c[0], size) <= width and font.text_length(c[1], size) <= width]
            if fit:
                lines = list(min(fit, key=lambda c: max(font.text_length(c[0], size), font.text_length(c[1], size))))
        return lines

    def white(page, r):
        page.draw_rect(fitz.Rect(r["x0"] - 1, r["y0"], r["x1"] + 1, r["y1"]), color=(1, 1, 1), fill=(1, 1, 1))

    day = f"{when:%d.%m.%Y}"   # as on the quotation
    # ---- page 1: "This agreement is executed on ______ 2026 for design ..."
    ex = find(p1, "executed")
    on = find(p1, "on", after_x=ex["x1"], line_of=(0, ex["y0"]))
    year = next(w for w in p1.get_text("words") if w[4].isdigit() and len(w[4]) == 4 and abs(w[1] - ex["y0"]) < 2)
    size = ex["size"]
    # the blank before the printed year is too narrow for a date at full size: the year is covered, the date
    # written in its place
    white(p1, {"x0": year[0], "x1": year[2], "y0": year[1], "y1": year[3]})
    write(p1, year[2] - font.text_length(day, size), ex["base"], day, size)
    # "______ having address ______ / ______ (hereinafter referred to as first Party ..."
    hv, ad = find(p1, "having"), find(p1, "address")
    here = find(p1, "(hereinafter")
    left, right = 88.8, 523.0
    write(p1, left, hv["base"], name, size)
    first = wrap(address, right - (ad["x1"] + 5), size)[0] if font.text_length(address, size) > right - (ad["x1"] + 5) else address
    rest = address[len(first):].strip()
    write(p1, ad["x1"] + 5, ad["base"], first, size)
    if rest:
        s2 = size
        while s2 > 8 and font.text_length(rest, s2) > here["x0"] - 6 - left:
            s2 -= 0.5
        write(p1, left, here["base"], rest, s2)

    # ---- page 4: First Party / Second Party, rows Name, Address, Sign, Date; values in one column per party.
    # A value that needs two lines pushes the rows below it down, in both columns, so the rows stay level.
    rows = ("Name", "Address", "Sign", "Date")
    lab = [[find(p4, r, col) for r in rows] for col in (0, 1)]
    size = lab[0][0]["size"]
    pitch = lab[0][1]["base"] - lab[0][0]["base"]   # the gap between rows
    lead = size * 1.25                              # the gap between two lines of one value
    vals = [{"Name": name, "Address": address, "Sign": "", "Date": day},
            {"Name": vname, "Address": vaddr, "Sign": "", "Date": day}]
    col_x = [max(c[i]["x1"] for i in range(4)) + 8 for c in lab]
    col_end = [lab[1][0]["x0"] - 14, right + 30]
    lines = [{r: wrap(v[r], col_end[c] - col_x[c], size) if v[r] else [] for r in rows} for c, v in enumerate(vals)]
    for c in (0, 1):
        for r in lab[c]:
            white(p4, r)
    base = lab[0][0]["base"]
    for r in rows:
        n = max(1, len(lines[0][r]), len(lines[1][r]))
        for c in (0, 1):
            write(p4, lab[c][0]["x0"], base, r, size)
            for i, t in enumerate(lines[c][r]):
                write(p4, col_x[c], base + i * lead, t, size)
        base += pitch + (n - 1) * lead
    # "19. Mutually Agreed Terms of Payment …": the installation cost in place of the "…"
    dots = next((w for w in p4.get_text("words") if w[4] == "…"), None)
    if cost and dots:
        white(p4, {"x0": dots[0], "x1": dots[2], "y0": dots[1], "y1": dots[3]})
        pay = find(p4, "Payment")
        write(p4, dots[0], pay["base"], f"Rs {inr(cost)}/- (including GST)", pay["size"])
    doc.subset_fonts()   # only the letters used: the whole of Calibri would more than double the file
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


# ------------------------------- quotation -------------------------------
def _set_span(par, pattern, new, group=0):
    """Replace the first match of pattern in a paragraph's text, even when Word split it over several runs.
    The text of the runs it covers is rewritten in place, so their formatting is kept."""
    runs = list(re.finditer(r"(<w:t(?: [^>]*)?>)([^<]*)(</w:t>)", par))
    texts = [html.unescape(r.group(2)) for r in runs]
    text = "".join(texts)
    m = re.search(pattern, text)
    if not m:
        return par, False
    s, e = m.span(group)
    out, pos, done = [], 0, False
    last = 0
    for r, t in zip(runs, texts):
        a, b = pos, pos + len(t)
        pos = b
        if b <= s or a >= e:
            continue
        keep = t[:max(0, s - a)] + ("" if done else new) + t[max(0, min(len(t), e - a)):]
        done = True
        open_tag = r.group(1) if ' xml:space="preserve"' in r.group(1) else r.group(1).replace("<w:t", '<w:t xml:space="preserve"', 1)
        out.append(par[last:r.start()] + open_tag + _esc(keep) + r.group(3))
        last = r.end()
    return "".join(out) + par[last:], True


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _plain(par):
    return html.unescape(re.sub(r"<[^>]+>", "", par))


def quotation_docx(template, name, place, when=None):
    """The quotation template with today's date, the customer's name and their place (two lines under "To,")."""
    when = when or date.today()
    with zipfile.ZipFile(template) as z:
        files = {n: z.read(n) for n in z.namelist()}
        infos = {n: z.getinfo(n) for n in z.namelist()}
    xml = files["word/document.xml"].decode("utf-8")
    pars = list(re.finditer(r"<w:p[ >].*?</w:p>", xml, flags=re.S))
    new = {}
    for i, p in enumerate(pars):
        if re.search(r"Date\s*:", _plain(p.group(0))):
            par, ok = _set_span(p.group(0), r"Date\s*:\s*(\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*\d{4})", f"{when:%d.%m.%Y}", 1)
            if ok:
                new[i] = par
                break
    else:
        raise ValueError("the quotation template has no 'Date : dd.mm.yyyy'")
    to = next((i for i, p in enumerate(pars) if _plain(p.group(0)).strip() == "To,"), None)
    if to is None:
        raise ValueError("the quotation template has no 'To,' line")
    lines = [i for i in range(to + 1, len(pars)) if _plain(pars[i].group(0)).strip()][:2]
    for i, value in zip(lines, (name, place)):
        new[i] = _set_span(pars[i].group(0), r"\S(?:.*\S)?", value)[0]
    out, last = [], 0
    for i, p in enumerate(pars):
        if i in new:
            out.append(xml[last:p.start()] + new[i])
            last = p.end()
    files["word/document.xml"] = ("".join(out) + xml[last:]).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in files.items():
            z.writestr(infos[n], data)
    return buf.getvalue()
