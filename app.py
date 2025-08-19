# FlashDecky — Streamlit app
# Ready-to-run, GitHub-friendly version
#
# Features:
# - Paste free-form text OR upload CSV/XLSX OR paste a table (TSV)
# - Smart parser for numbered/bulleted lists, separators, wrapped lines
# - Editable review grid (Front/Back)
# - PDF generator: 8 cards per US Letter, dashed cut lines
# - Duplex modes: Long-edge (mirrored back), Long-edge (not mirrored), Short-edge
# - Fine X/Y offsets for backs
# - Footer template with {subject}, {lesson}, {unit}, {index}, {page}

import io
import re
import math
import pandas as pd
import streamlit as st
from dataclasses import dataclass
from typing import List, Tuple, Optional

# PDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib import colors

st.set_page_config(page_title="FlashDecky", layout="wide")

# ----------------------------- Parsing ----------------------------------

ROW_START_RE = re.compile(r"^\s*(?:\d+[\.\)]\s+|[-*•]\s+)")  # numbered or bullet
SEP_TAB = "\t"
SEP_DASH = re.compile(r"\s[-–—]\s")  # space-dash-space variants
PARENS = re.compile(r"\(.*?\)")

def _split_term_def(line: str) -> Tuple[str, str]:
    # Priority: tab, colon (not inside parens), spaced dash, dictionary (term (pos) definition)
    if SEP_TAB in line:
        parts = line.split(SEP_TAB, 1)
        return parts[0].strip(), parts[1].strip()
    # colon not in parentheses
    # find first ":" not between parentheses
    depth = 0
    for i, ch in enumerate(line):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            return line[:i].strip(), line[i+1:].strip()
    # spaced dash
    m = SEP_DASH.search(line)
    if m:
        i = m.start()
        return line[:i].strip(), line[m.end():].strip()
    # dictionary: term (pos) def
    # term = up to first close paren then space
    m2 = re.match(r"^\s*([^\(]+)\s*\(.*?\)\s+(.*)$", line)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()
    # fallback: first space split
    parts = line.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return line.strip(), ""

def parse_text(raw: str) -> List[Tuple[str, str]]:
    lines = [l.rstrip() for l in raw.splitlines()]
    rows: List[str] = []
    buf = ""
    for ln in lines:
        if not ln.strip():
            continue
        if ROW_START_RE.match(ln):
            # commit previous buffer
            if buf.strip():
                rows.append(buf.strip())
            # remove bullet/number prefix
            ln = re.sub(r"^\s*(\d+[\.\)]\s+|[-*•]\s+)", "", ln).strip()
            buf = ln
        else:
            # continuation of previous line
            if buf:
                # join with space
                buf += " " + ln.strip()
            else:
                buf = ln.strip()
    if buf.strip():
        rows.append(buf.strip())

    result: List[Tuple[str, str]] = []
    for r in rows:
        term, definition = _split_term_def(r)
        term = term.strip(" —–-")
        definition = " ".join(definition.split())  # collapse spaces
        result.append((term, definition))
    return result


# ----------------------------- PDF ----------------------------------

@dataclass
class FooterConfig:
    enabled: bool
    subject: str
    lesson: str
    unit: str
    template: str  # e.g., "{subject} • {lesson}"

def wrap_text(text: str, font: str, size: float, max_width: float) -> List[str]:
    """Simple greedy word wrap using stringWidth."""
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if stringWidth(test, font, size) <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if not lines:
        lines = [""]
    return lines

def draw_dashed_grid(c: canvas.Canvas, page_w: float, page_h: float, cols: int, rows: int, margin: float):
    card_w = (page_w - 2*margin) / cols
    card_h = (page_h - 2*margin) / rows
    c.setDash(4, 6)
    c.setStrokeColor(colors.lightgrey)
    # verticals
    for i in range(1, cols):
        x = margin + i*card_w
        c.line(x, margin, x, page_h - margin)
    # horizontals
    for j in range(1, rows):
        y = margin + j*card_h
        c.line(margin, y, page_w - margin, y)
    c.setDash()  # reset

def render_page(c: canvas.Canvas, cards: List[Tuple[str, str]], start_index: int, front: bool, duplex_mode: str,
                offset_x_mm: float, offset_y_mm: float, footer: FooterConfig, page_num: int,
                cols: int = 2, rows: int = 4, margin: float = 0.5*inch):
    page_w, page_h = letter
    card_w = (page_w - 2*margin) / cols
    card_h = (page_h - 2*margin) / rows

    # offsets for BACK only
    dx = (offset_x_mm / 25.4) * inch if not front else 0
    dy = (offset_y_mm / 25.4) * inch if not front else 0

    # Transform for back mirroring
    if not front:
        if duplex_mode == "Long-edge (mirrored back)":
            # mirror horizontally around page center
            c.translate(page_w, 0)
            c.scale(-1, 1)
        elif duplex_mode == "Short-edge":
            # rotate 180 degrees
            c.translate(page_w, page_h)
            c.rotate(180)

    # draw cut guides
    draw_dashed_grid(c, page_w, page_h, cols, rows, margin)

    for idx in range(cols*rows):
        i = idx % cols
        j = idx // cols
        x0 = margin + i*card_w + (dx if not front else 0)
        y0 = margin + (rows-1-j)*card_h + (dy if not front else 0)

        ci = start_index + idx
        if ci >= len(cards):
            continue

        term, definition = cards[ci]

        # Inset
        pad = 12
        inner_w = card_w - 2*pad
        inner_h = card_h - 2*pad

        # Draw content
        if front:
            # big term centered
            title_size = 18
            # fit term size down if too wide
            while stringWidth(term, "Helvetica-Bold", title_size) > inner_w and title_size > 10:
                title_size -= 1
            c.setFont("Helvetica-Bold", title_size)
            c.setFillColor(colors.black)
            c.drawCentredString(x0 + card_w/2, y0 + card_h/2, term)
        else:
            # definition block top-left
            body_size = 11
            c.setFont("Helvetica", body_size)
            lines = wrap_text(definition, "Helvetica", body_size, inner_w)
            top = y0 + card_h - pad - body_size
            for line in lines[:12]:  # safety cap
                c.drawString(x0 + pad, top, line)
                top -= body_size * 1.25

        # Footer (small)
        if footer.enabled:
            tpl = footer.template or "{subject} • {lesson}"
            txt = tpl.format(subject=footer.subject or "",
                             lesson=footer.lesson or footer.unit or "",
                             unit=footer.unit or footer.lesson or "",
                             index=ci+1,
                             page=page_num)
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.grey)
            c.drawRightString(x0 + card_w - 6, y0 + 6, txt)

def build_pdf(cards: List[Tuple[str,str]], duplex_mode: str, offset_x_mm: float, offset_y_mm: float,
              footer: FooterConfig) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    cols, rows = 2, 4
    per_page = cols*rows
    num_pages = math.ceil(len(cards) / per_page)
    for p in range(num_pages):
        start = p * per_page
        # FRONT
        render_page(c, cards, start, front=True, duplex_mode=duplex_mode, offset_x_mm=offset_x_mm,
                    offset_y_mm=offset_y_mm, footer=footer, page_num=p+1, cols=cols, rows=rows)
        c.showPage()
        # BACK
        render_page(c, cards, start, front=False, duplex_mode=duplex_mode, offset_x_mm=offset_x_mm,
                    offset_y_mm=offset_y_mm, footer=footer, page_num=p+1, cols=cols, rows=rows)
        c.showPage()
    c.save()
    return buf.getvalue()

# ----------------------------- UI ----------------------------------

st.markdown("# ⚡ FlashDecky")
st.caption("Turn any list into perfect, printable flash cards (8 per page, duplex-ready).")

with st.expander("How to use (quick)", expanded=False):
    st.write("""
    1) Paste your list, upload CSV/XLSX, or paste a table.
    2) Fix anything in **Review & Edit**.
    3) Pick duplex alignment, enter optional footer, and **Generate PDF**.
    """)

colA, colB, colC = st.columns(3)
with colA:
    st.subheader("Paste text")
    raw_text = st.text_area("Your list", height=220, placeholder="1) term — definition\n2) another term: definition...\n• third term - definition")
with colB:
    st.subheader("Upload file (CSV/XLSX)")
    file = st.file_uploader("Choose a CSV or Excel file", type=["csv","xlsx"])
with colC:
    st.subheader("Paste table (Excel/Sheets)")
    paste_table = st.text_area("Paste a tab-separated table (two columns: term\tdefinition)", height=220, placeholder="term\tdefinition")

# Build initial df from inputs
data = []
if raw_text.strip():
    data = parse_text(raw_text)
elif paste_table.strip():
    # accept TSV/CSV-ish
    lines = [l for l in paste_table.splitlines() if l.strip()]
    for ln in lines:
        if "\t" in ln:
            t, d = ln.split("\t", 1)
        elif "," in ln:
            t, d = ln.split(",", 1)
        else:
            t, d = _split_term_def(ln)
        data.append((t.strip(), d.strip()))
elif file is not None:
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    # try to auto-map first two columns
    if df.shape[1] >= 2:
        data = list(zip(df.iloc[:,0].astype(str).tolist(),
                        df.iloc[:,1].astype(str).tolist()))

# dataframe for editor
if not data:
    data = [("munch", "to chew food loudly and completely"),
            ("bellowed", "to have shouted in a loud deep voice")]

df_edit = pd.DataFrame(data, columns=["Front of Flash Card (term)", "Back of Flash Card (definition)"])
st.subheader("2) Review & edit")
edited = st.data_editor(
    df_edit,
    num_rows="dynamic",
    hide_index=True,
    use_container_width=True,
    key="editor",
)

st.subheader("3) Download PDF")
with st.expander("Print alignment", expanded=True):
    duplex_mode = st.selectbox("Duplex mode", ["Long-edge (mirrored back)","Long-edge (not mirrored)","Short-edge"], index=0)
    x_mm = st.number_input("Back page offset X (mm)", value=0.0, step=0.5)
    y_mm = st.number_input("Back page offset Y (mm)", value=0.0, step=0.5)
st.write("**Card footer (subject • lesson)**")
footer_on = st.checkbox("Include footer text on cards", value=True)
col1, col2, col3 = st.columns(3)
with col1:
    subject = st.text_input("Subject", value="")
with col2:
    lesson = st.text_input("Lesson / Unit", value="")
with col3:
    footer_template = st.text_input("Footer template", value="{subject} • {lesson}")

cards = list(zip(edited["Front of Flash Card (term)"].astype(str),
                 edited["Back of Flash Card (definition)"].astype(str)))
footer_cfg = FooterConfig(enabled=footer_on, subject=subject, lesson=lesson, unit=lesson, template=footer_template)

if st.button("Generate PDF", type="primary"):
    pdf_bytes = build_pdf(cards, duplex_mode=duplex_mode, offset_x_mm=x_mm, offset_y_mm=y_mm, footer=footer_cfg)
    st.download_button("Download flashdecky.pdf", data=pdf_bytes, file_name="flashdecky.pdf", mime="application/pdf")
    st.success("PDF generated. Use your printer's **Two-sided** with the chosen duplex mode.")
