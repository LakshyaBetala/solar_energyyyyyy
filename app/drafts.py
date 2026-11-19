"""The two documents made once a customer's details are in, both filled into the client's own templates:

- the vendor-consumer agreement: the draft PDF in "agreement draft/", written onto at its blanks (date,
  customer name and address on page 1; both parties' name, address and date on page 4);
- the bank quotation: the Word file in the quotation folder for the chosen installation cost, with the date,
  the customer's name and their place changed; the outward number is kept as it is.

The templates are the client's files, kept in the repository ("agreement draft/", "Quoatation (all range)/"); their folders are found
beside the code, or through SOLARA_AGREEMENT_DIR and SOLARA_QUOTES_DIR.
"""
import html, io, os, re, zipfile
from datetime import date
from pathlib import Path
from .config import ROOT

FONT_FILE = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "calibri.ttf"   # the draft is set in Calibri


def own_agreement():
    """The agreement draft the owner uploaded in Solara (Reports), kept with the data."""
    from .config import DATA
    return DATA / "agreement" / "agreement_draft.pdf"


def agreement_template():
    if own_agreement().exists():
        return own_agreement()
    folder = Path(os.environ.get("SOLARA_AGREEMENT_DIR") or ROOT / "agreement draft")
    pdfs = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
    if not pdfs:
        raise FileNotFoundError("there is no agreement draft yet: upload the PDF in Reports")
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


def ink_only(png):
    """A signature photo as dark ink on a see-through background. Each spot is judged against its own
    surroundings, so a tinted, shaded or printed background (gradients, halftone dots) drops out, and marks
    too small to be part of a stroke are removed."""
    from PIL import Image, ImageFilter, ImageChops
    im = Image.open(io.BytesIO(png))
    if im.mode in ("RGBA", "LA", "P"):   # a signature drawn on the pad is see-through: lay it on white first
        im = im.convert("RGBA")
        white = Image.new("RGB", im.size, "white")
        white.paste(im, mask=im.getchannel("A"))
        im = white
    im.thumbnail((1200, 500))
    g = im.convert("L").filter(ImageFilter.MedianFilter(3))          # grain smoothed; thin strokes survive
    r = max(15, min(g.size) // 6) | 1                                  # wider than a pen stroke
    paper = g.filter(ImageFilter.MaxFilter(r)).filter(ImageFilter.GaussianBlur(r / 2))   # the local paper shade
    dark = ImageChops.subtract(paper, g)                               # how much darker than its surroundings
    hist = dark.histogram()
    total = sum(hist)
    pen = next(i for i in range(256) if sum(hist[:i + 1]) >= total * 0.998)   # the darkest 0.2% is always pen
    cut = max(28, int(pen * 0.4))                                      # relative to how dark the strokes are
    alpha = dark.point(lambda v: 0 if v < cut else min(255, (v - cut) * 255 // max(8, (pen - cut) // 2)))   # solid from halfway
    keep = _strokes(alpha.point(lambda v: 255 if v > 40 else 0))
    alpha = ImageChops.multiply(alpha, keep.filter(ImageFilter.MaxFilter(3)))
    ink = Image.new("RGBA", g.size, (20, 25, 70, 0))
    ink.putalpha(alpha)
    box = alpha.getbbox()   # trimmed to the ink: a loose crop still fills the Sign line
    if box:
        ink = ink.crop((max(0, box[0] - 6), max(0, box[1] - 6), min(ink.width, box[2] + 6), min(ink.height, box[3] + 6)))
    out = io.BytesIO()
    ink.save(out, "PNG")
    return out.getvalue()


def _strokes(mask):
    """The mask with only the marks big enough to be pen strokes: each connected mark must be at least 2% of the
    largest one (a letter's dot stays, background specks go)."""
    from PIL import Image
    w, h = mask.size
    px = mask.load()
    seen = bytearray(w * h)
    marks = []
    for y in range(h):
        for x in range(w):
            if px[x, y] and not seen[y * w + x]:
                seen[y * w + x] = 1
                stack, pts = [(x, y)], []
                while stack:
                    cx, cy = stack.pop()
                    pts.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and not seen[ny * w + nx]:
                            seen[ny * w + nx] = 1
                            stack.append((nx, ny))
                marks.append(pts)
    out = Image.new("L", mask.size, 0)
    if marks:
        least = max(12, len(max(marks, key=len)) * 0.02)
        op = out.load()
        for pts in marks:
            if len(pts) >= least:
                for x, y in pts:
                    op[x, y] = 255
    return out


def agreement_pdf(name, address, when=None, cost=None, sign=None, vendor_sign=None, template=None):
    import fitz
    when = when or date.today()
    doc = fitz.open(stream=template, filetype="pdf") if template else fitz.open(agreement_template())
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
        # the signatures (PNGs): the customer's on the First Party line, the company's on the Second; two lines high
        if r == "Sign" and (sign or vendor_sign):
            n = max(n, 2)
            for c, img in ((0, sign), (1, vendor_sign)):
                if not img:
                    continue
                if fitz.Pixmap(img).alpha == 0:   # a photo stored before cleaning; cleaned ones are see-through already
                    img = ink_only(img)
                pm = fitz.Pixmap(img)
                w = min(size * 2.4 * pm.width / pm.height, col_end[c] - col_x[c])
                p4.insert_image(fitz.Rect(col_x[c], base - size, col_x[c] + w, base - size + w * pm.height / pm.width), stream=img)
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


FLAT = '<w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/>'
# what may follow <w:spacing> inside <w:pPr>, in the order the Word schema requires
_AFTER_SPACING = ("ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
                  "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange")


def _flatten(par):
    """The same paragraph, 1 pt high: its line spacing set to exactly 1 pt, nothing before or after."""
    if re.search(r"<w:spacing\b[^>]*/>", par):
        return re.sub(r"<w:spacing\b[^>]*/>", FLAT, par, count=1)
    m = re.search(r"<w:pPr>(.*?)</w:pPr>", par, flags=re.S)
    if not m:
        return re.sub(r"(<w:p\b[^>]*>)", r"\1<w:pPr>" + FLAT + "</w:pPr>", par, count=1)
    body = m.group(1)
    at = min([j for t in _AFTER_SPACING if (j := body.find(f"<w:{t}")) >= 0] or [len(body)])
    return par[:m.start(1)] + body[:at] + FLAT + body[at:] + par[m.end(1):]


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
    # The white "GST NO." line sits on the letterhead's green banner, 9 pt above its bottom edge. A blank
    # line above it (two of the nine templates have one, holding only leftover picture definitions) pushes it
    # half off the banner, where white on white vanishes. Those lines are kept but made 1 pt high.
    gst = next((i for i, p in enumerate(pars) if "GST NO" in _plain(p.group(0))), None)
    for i in range(gst or 0):
        if not _plain(pars[i].group(0)).strip() and "<w:sectPr" not in pars[i].group(0):
            new[i] = _flatten(pars[i].group(0))
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


def can_pdf():
    """Is there a program on this computer that turns a Word file into a PDF (LibreOffice, or Microsoft Word)?"""
    import shutil
    if shutil.which("soffice") or shutil.which("libreoffice"):
        return True
    if os.name != "nt":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Word.Application"))
        return True
    except OSError:
        return False


def docx_to_pdf(blob):
    """A Word file as PDF bytes, through Microsoft Word (Windows) or LibreOffice (anywhere). ValueError when neither is there."""
    import hashlib, shutil, subprocess, tempfile
    from pathlib import Path
    key = hashlib.sha256(blob).hexdigest()[:20]
    work = Path(tempfile.gettempdir()) / "solara_pdf"
    work.mkdir(exist_ok=True)
    src, out = work / f"{key}.docx", work / f"{key}.pdf"
    if out.exists():
        return out.read_bytes()
    src.write_bytes(blob)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    try:
        if soffice:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(work), str(src)],
                           check=True, capture_output=True, timeout=90)
        elif os.name == "nt":
            ps = ("$w=New-Object -ComObject Word.Application;$w.Visible=$false;"
                  f"$d=$w.Documents.Open('{src}',$false,$true);$d.SaveAs([ref]'{out}',[ref]17);$d.Close($false);$w.Quit()")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True, timeout=90)
    except (subprocess.SubprocessError, OSError):
        pass
    if not out.exists():
        raise ValueError("the quotation as a PDF needs Microsoft Word or LibreOffice on the Solara computer")
    return out.read_bytes()
