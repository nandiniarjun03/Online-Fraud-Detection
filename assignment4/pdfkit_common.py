"""Shared ReportLab styles and helpers (fonts, code blocks, tables, notes)."""
import re
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, XPreformatted, KeepTogether, NextPageTemplate, CondPageBreak,
)
from reportlab.platypus.tableofcontents import TableOfContents

REPO = Path(".")

# ---------------------------------------------------------------- fonts
FD = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", FD + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", FD + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", FD + "DejaVuSansMono.ttf"))
pdfmetrics.registerFont(TTFont("Mono-Bold", FD + "DejaVuSansMono-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono-Oblique", FD + "DejaVuSansMono-Oblique.ttf"))
addMapping("Sans", 0, 0, "Sans")
addMapping("Sans", 1, 0, "Sans-Bold")
addMapping("Sans", 0, 1, "Sans")
addMapping("Sans", 1, 1, "Sans-Bold")
addMapping("Mono", 0, 0, "Mono")
addMapping("Mono", 1, 0, "Mono-Bold")
addMapping("Mono", 0, 1, "Mono-Oblique")
addMapping("Mono", 1, 1, "Mono-Bold")

# ---------------------------------------------------------------- palette
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5f6b7a")
ACCENT = colors.HexColor("#6b3e26")
ACCENT_SOFT = colors.HexColor("#f4ece4")
RULE = colors.HexColor("#d5dbe3")
CODE_BG = colors.HexColor("#f6f8fa")
WARN_BG = colors.HexColor("#fff7e6")
WARN_BORDER = colors.HexColor("#e0a841")

# ---------------------------------------------------------------- styles
body = ParagraphStyle("body", fontName="Sans", fontSize=9.6, leading=14.2,
                      textColor=INK, spaceAfter=6)
small = ParagraphStyle("small", parent=body, fontSize=8.4, leading=11.5, textColor=MUTED)
h1 = ParagraphStyle("h1", fontName="Sans-Bold", fontSize=17, leading=22,
                    textColor=ACCENT, spaceBefore=4, spaceAfter=10, keepWithNext=1)
h2 = ParagraphStyle("h2", fontName="Sans-Bold", fontSize=12, leading=16,
                    textColor=INK, spaceBefore=12, spaceAfter=5, keepWithNext=1)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=14, bulletIndent=4, spaceAfter=3)
caption = ParagraphStyle("caption", parent=small, alignment=TA_LEFT, spaceBefore=2, spaceAfter=10)
cell = ParagraphStyle("cell", parent=body, fontSize=8.8, leading=12, spaceAfter=0)
cell_b = ParagraphStyle("cellb", parent=cell, fontName="Sans-Bold")
code_style = ParagraphStyle("code", fontName="Mono", fontSize=7.4, leading=10.2, textColor=INK)
toc_l1 = ParagraphStyle("toc1", fontName="Sans", fontSize=10.5, leading=19, textColor=INK)


def P(text, style=body):
    return Paragraph(text, style)


def C(text):
    """Inline code."""
    return f'<font face="Mono" size="8.6" color="#9c2c4a">{text}</font>'


def bullets(items):
    return [Paragraph(i, bullet, bulletText="•") for i in items]


# ---------------------------------------------------------------- syntax highlighting
PY_KW = r"\b(?:import|from|as|def|class|return|if|else|elif|for|in|with|try|except|raise|not|and|or|is|None|True|False|pass)\b"
TOKEN_RE = {
    "python": re.compile(
        r"(?P<com>#[^\n]*)|(?P<str>f?\"[^\"\n]*\"|f?'[^'\n]*')|(?P<dec>@[\w.]+)|(?P<kw>" + PY_KW + r")|(?P<num>\b\d+(?:\.\d+)?\b)"),
    "yaml": re.compile(r"(?P<com>#[^\n]*)|(?P<str>'[^'\n]*')|(?P<kw>^\s*-?\s*[\w-]+(?=:))", re.M),
    "bash": re.compile(r"(?P<com>#[^\n]*)|(?P<kw>\b(?:python|pip|pytest|curl|cd)\b)|(?P<str>'[^'\n]*')"),
    "json": re.compile(r"(?P<kw>\"[\w_]+\"(?=\s*:))|(?P<str>\"[^\"\n]*\")|(?P<num>-?\b\d+(?:\.\d+)?\b)"),
    "text": None,
}
COLORS = {"com": ("#6a737d", True), "str": ("#0a6e3c", False), "kw": ("#8a1f7a", False),
          "num": ("#b35c00", False), "dec": ("#6b3e26", False)}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def highlight(src, lang):
    rx = TOKEN_RE.get(lang)
    if rx is None:
        return esc(src)
    out, pos = [], 0
    for m in rx.finditer(src):
        out.append(esc(src[pos:m.start()]))
        kind = m.lastgroup
        col, ital = COLORS[kind]
        t = esc(m.group())
        t = f'<font color="{col}">{t}</font>'
        if ital:
            t = f"<i>{t}</i>"
        if kind == "kw" and lang == "python":
            t = f"<b>{t}</b>"
        out.append(t)
        pos = m.end()
    out.append(esc(src[pos:]))
    return "".join(out)


CODE_MAXC = 104


def wrap_line(line, maxc):
    """Soft-wrap one source line at a space/comma boundary; continuation lines get extra indent."""
    if len(line) <= maxc:
        return [line]
    indent = len(line) - len(line.lstrip()) + 4
    out = []
    while len(line) > maxc:
        cut = max(line.rfind(", ", 0, maxc), line.rfind(" ", 0, maxc))
        if cut <= indent:
            cut = maxc
        else:
            cut += 1
        out.append(line[:cut].rstrip())
        line = " " * indent + line[cut:].lstrip()
    out.append(line)
    return out


def code_block(src, lang="python", title=None, first_line=None):
    lines = src.rstrip("\n").expandtabs(4).split("\n")
    width = len(str(first_line + len(lines) - 1)) if first_line is not None else 0
    maxc = CODE_MAXC - (width + 2 if width else 0)
    phys = []
    in_doc = False
    for i, l in enumerate(lines):
        toggles = l.count('"""') % 2 == 1
        whole_str = lang == "python" and (in_doc or toggles)
        if toggles:
            in_doc = not in_doc
        for j, part in enumerate(wrap_line(l, maxc)):
            hl = f'<font color="#0a6e3c">{esc(part)}</font>' if whole_str and part.strip() else highlight(part, lang)
            if width:
                num = str(first_line + i).rjust(width) if j == 0 else " " * width
                hl = f'<font color="#a0a8b3">{num}</font>  {hl}'
            phys.append(hl)
    rows = []
    if title:
        rows.append([Paragraph(f'<font face="Mono" size="7.8" color="#ffffff">{esc(title)}</font>',
                               ParagraphStyle("t", leading=10))])
    rows += [[XPreformatted(t, code_style) if t.strip() else Spacer(1, code_style.leading)] for t in phys]
    t = Table(rows, colWidths=[None], repeatRows=1 if title else 0)
    body0 = 1 if title else 0
    st = [
        ("BACKGROUND", (0, body0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, body0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, body0), (-1, -1), 0),
        ("TOPPADDING", (0, body0), (-1, body0), 6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
    ]
    if title:
        st += [("BACKGROUND", (0, 0), (-1, 0), ACCENT),
               ("TOPPADDING", (0, 0), (-1, 0), 3), ("BOTTOMPADDING", (0, 0), (-1, 0), 3)]
    t.setStyle(TableStyle(st))
    return [t, Spacer(1, 8)]


def snippet(path, start, end, title=None):
    """Pull lines [start, end] (1-based, inclusive) straight from the repository file."""
    lines = (REPO / path).read_text().split("\n")
    src = "\n".join(l.rstrip() for l in lines[start - 1:end])
    lang = "yaml" if path.endswith(".yml") else "python"
    return code_block(src, lang, title or f"{path}  (lines {start}–{end})", first_line=start)


def note(text, label="Note"):
    t = Table([[Paragraph(f"<b>{label}.</b> {text}", ParagraphStyle("n", parent=body, spaceAfter=0))]],
              colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WARN_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, WARN_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [t, Spacer(1, 8)]


def table(header, rows, widths):
    data = [[Paragraph(h, cell_b) for h in header]]
    data += [[Paragraph(c, cell) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [t, Spacer(1, 10)]


