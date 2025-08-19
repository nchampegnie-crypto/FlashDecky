
import io, re, math, textwrap, pathlib
from typing import List, Tuple

import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.units import mm
import requests

st.set_page_config(page_title="FlashDecky Final", layout="wide")

# --------------------- Utilities ---------------------
def mm_to_points(val_mm: float) -> float:
    return float(val_mm) * 72.0 / 25.4

def safe(s: str) -> str:
    return (s or "").strip()

# --------------------- Parsing -----------------------
SEP_PATTERNS = [
    "\t",                              # tab
    ":",                               # colon
    " — ", " – ", " - ",               # spaced em dash, en dash, hyphen
    "—", "–",                          # bare em/en dash
]

def line_starts_new_item(line: str) -> bool:
    line = line.lstrip()
    if not line:
        return False
    if re.match(r"^(\d+[\.\)]\s+|[-*•]\s+)", line):
        return True
    # looks like "term - def" or "term: def" or "term (pos.) def"
    if re.match(r"^[A-Za-z][^\n]{0,60}?(?:\s[\-–—:]\s|\s\([^)]+\))", line):
        return True
    return False

def coalesce_lines(text: str) -> List[str]:
    # Merge wrapped lines into their previous item unless a new item starts
    chunks = []
    curr = ""
    for raw in (text or "").replace("\r\n","\n").splitlines():
        line = raw.rstrip()
        if line_starts_new_item(line):
            if curr.strip():
                chunks.append(curr.strip())
            curr = line
        else:
            if line.strip():
                curr = (curr + " " + line.strip()).strip() if curr else line.strip()
    if curr.strip():
        chunks.append(curr.strip())
    # Also split on blank-blank boundaries just in case
    out = []
    for part in "\n\n".join(chunks).split("\n\n"):
        if part.strip():
            out.append(part.strip())
    return out

def split_term_def(s: str) -> Tuple[str,str]:
    s = s.strip()
    # remove leading numbering/bullet
    s = re.sub(r"^(\d+[\)\.\-]*\s+|[-*•]\s+)", "", s).strip()
    # 1) Tab (most explicit for spreadsheets pasted)
    if "\t" in s:
        lhs, rhs = s.split("\t", 1)
        return safe(lhs), safe(rhs)
    # Helper: colon outside parentheses
    def find_colon_outside_parens(text):
        depth = 0
        for i,ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth-1)
            elif ch == ":" and depth == 0:
                return i
        return -1
    idx = find_colon_outside_parens(s)
    if idx != -1:
        return safe(s[:idx]), safe(s[idx+1:])
    # 3) Spaced hyphen/en/em dash
    for token in [" - ", " — ", " – "]:
        if token in s:
            lhs, rhs = s.split(token, 1)
            return safe(lhs), safe(rhs)
    # 4) Bare dash variants (fallback)
    for token in ["—", "–"]:
        if token in s:
            lhs, rhs = s.split(token, 1)
            return safe(lhs), safe(rhs)
    # 5) Dictionary style: term (pos.) def
    m = re.match(r"^\s*([A-Za-z][\w'‑\-]*)\s*\(([^)]+)\)\s*(.+)$", s)
    if m:
        term = m.group(1)
        pos = m.group(2)
        rest = m.group(3)
        return safe(term), safe(f"({pos}) {rest}")
    # 6) Last resort: first token as term
    parts = s.split(None, 1)
    if len(parts) == 2:
        return safe(parts[0]), safe(parts[1])
    return safe(s), ""

def parse_text_to_df(raw_text: str) -> pd.DataFrame:
    items = []
    for block in coalesce_lines(raw_text or ""):
        t, d = split_term_def(block)
        if t or d:
            items.append((t, d))
    return pd.DataFrame(items, columns=["Front of Flash Card (term)", "Back of Flash Card (definition)"])

# --------------------- Ingest helpers ----------------
def parse_pasted_table(raw: str) -> pd.DataFrame:
    # Split on tabs / pipes / 2+ spaces; keep first two segments
    rows = []
    for line in (raw or "").splitlines():
        parts = [p.strip() for p in re.split(r"\t+|\|+|\s{2,}", line) if p.strip()]
        if len(parts) >= 2:
            rows.append((parts[0], " ".join(parts[1:])))
    return pd.DataFrame(rows, columns=["col1","col2"])

def map_columns_ui(df: pd.DataFrame, key_prefix: str="") -> pd.DataFrame:
    st.write("**Map your columns:**")
    cols = list(df.columns)
    col_left, col_right = st.columns(2)
    term_col = col_left.selectbox("Term column", cols, index=0, key=f"{key_prefix}_term_col")
    def_col  = col_right.selectbox("Definition column", cols, index=1 if len(cols)>1 else 0, key=f"{key_prefix}_def_col")
    mapped = pd.DataFrame({
        "Front of Flash Card (term)": df[term_col].astype(str).fillna(""),
        "Back of Flash Card (definition)": df[def_col].astype(str).fillna("")
    })
    return mapped

def ocr_space_image(image_bytes: bytes, api_key: str) -> str:
    try:
        r = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": ("upload.png", image_bytes, "application/octet-stream")},
            data={"language": "eng", "OCREngine": 2},
            headers={"apikey": api_key},
            timeout=60
        )
        r.raise_for_status()
        js = r.json()
        if js.get("IsErroredOnProcessing"):
            return ""
        return " ".join([res.get("ParsedText","") for res in js.get("ParsedResults",[])])
    except Exception:
        return ""

# --------------------- PDF Builder -------------------
def wrap_text(text: str, font: str, size: float, max_width: float) -> list:
    words = (text or "").split()
    lines, cur = [], ""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    for w in words:
        test = (cur + " " + w).strip()
        if stringWidth(test, font, size) <= max_width:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def map_back_index(i: int, cols: int, rows: int, mode: str) -> int:
    # Mode options: "Long-edge (mirrored back)", "Long-edge (not mirrored)", "Short-edge (mirrored back)"
    row = i // cols
    col = i % cols
    if "mirrored" in mode.lower():
        col = (cols - 1) - col
    if mode.lower().startswith("short-edge"):
        row = (rows - 1) - row
    return row * cols + col

def render_footer(template: str, subject: str, unit: str, lesson: str, index1: int, page1: int) -> str:
    # support both {unit} and {lesson}
    txt = (template or "")
    txt = txt.replace("{subject}", subject or "")
    txt = txt.replace("{unit}", unit or lesson or "")
    txt = txt.replace("{lesson}", lesson or unit or "")
    txt = txt.replace("{index}", str(index1))
    txt = txt.replace("{page}", str(page1))
    return txt.strip()

def create_pdf(df: pd.DataFrame, duplex_mode: str, offx_mm: float, offy_mm: float,
               include_footer: bool, subject: str, unit: str, lesson: str, footer_template: str,
               show_corner: bool) -> bytes:
    PAGE_W, PAGE_H = letter
    MARGIN = 18  # points
    COLS, ROWS = 2, 4
    card_w = (PAGE_W - 2*MARGIN) / COLS
    card_h = (PAGE_H - 2*MARGIN) / ROWS
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    records = df.to_dict("records")
    total = len(records)
    pages = math.ceil(total / (COLS*ROWS))

    # ---- FRONT PAGES ----
    global_idx = 0
    page_no = 0
    for start in range(0, total, COLS*ROWS):
        page_no += 1
        batch = records[start:start+COLS*ROWS]
        # grid guides (one big grid)
        c.setStrokeColor(colors.lightgrey); c.setDash(3,3)
        # vertical lines
        for i in range(1, COLS):
            x = MARGIN + i*card_w
            c.line(x, MARGIN, x, PAGE_H - MARGIN)
        # horizontal lines
        for j in range(1, ROWS):
            y = MARGIN + j*card_h
            c.line(MARGIN, y, PAGE_W - MARGIN, y)
        c.rect(MARGIN, MARGIN, PAGE_W - 2*MARGIN, PAGE_H - 2*MARGIN)
        c.setDash()

        # draw terms
        for i, rec in enumerate(batch):
            term = safe(rec.get("Front of Flash Card (term)",""))
            col = i % COLS
            row = i // COLS
            # top-left coordinate of card box
            x = MARGIN + col*card_w
            y = PAGE_H - MARGIN - (row+1)*card_h
            # term centered
            size = 18
            c.setFont("Helvetica-Bold", size)
            # if too wide, shrink slightly
            if stringWidth(term, "Helvetica-Bold", size) > (card_w - 16):
                size = 16
                c.setFont("Helvetica-Bold", size)
            c.drawCentredString(x + card_w/2, y + card_h/2 + 8, term[:200])

            if include_footer:
                footer = render_footer(footer_template, subject, unit, lesson, global_idx+1, page_no)
                if footer:
                    c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
                    c.drawRightString(x + card_w - 6, y + 6, footer)
                    c.setFillColor(colors.black)
            global_idx += 1
        c.showPage()

        # ---- BACK PAGE (definitions) ----
        c.setStrokeColor(colors.lightgrey); c.setDash(3,3)
        for i in range(1, COLS):
            x = MARGIN + i*card_w
            c.line(x, MARGIN, x, PAGE_H - MARGIN)
        for j in range(1, ROWS):
            y = MARGIN + j*card_h
            c.line(MARGIN, y, PAGE_W - MARGIN, y)
        c.rect(MARGIN, MARGIN, PAGE_W - 2*MARGIN, PAGE_H - 2*MARGIN)
        c.setDash()

        # definitions
        for i, rec in enumerate(batch):
            j = map_back_index(i, COLS, ROWS, duplex_mode)
            col = j % COLS
            row = j // COLS
            x = MARGIN + col*card_w + mm_to_points(offx_mm)
            y = PAGE_H - MARGIN - (row+1)*card_h + mm_to_points(offy_mm)
            definition = safe(rec.get("Back of Flash Card (definition)",""))

            size = 12
            c.setFont("Helvetica", size)
            lines = wrap_text(definition, "Helvetica", size, card_w - 14)
            # Downscale slightly if too many lines
            if len(lines) > 12:
                size = 11; c.setFont("Helvetica", size)
                lines = wrap_text(definition, "Helvetica", size, card_w - 14)
            if len(lines) > 13:
                size = 10; c.setFont("Helvetica", size)
                lines = wrap_text(definition, "Helvetica", size, card_w - 14)

            top = y + card_h - 22
            for li, line in enumerate(lines[:14]):
                c.drawString(x + 7, top - li*14, line)

            if include_footer:
                footer = render_footer(footer_template, subject, unit, lesson, 0, page_no)  # index optional on back
                if footer:
                    c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
                    c.drawRightString(x + card_w - 6, y + 6, footer)
                    c.setFillColor(colors.black)

        if show_corner:
            c.setFillColor(colors.red); c.circle(PAGE_W-6, PAGE_H-6, 2, fill=1); c.setFillColor(colors.black)
        c.showPage()

    c.save()
    return buf.getvalue()

# --------------------- UI ---------------------------
st.title("FlashDecky Final")

st.header("1) Upload or paste your list")

tab_paste, tab_table, tab_upload, tab_shot = st.tabs([
    "Paste text", "Paste table / Spreadsheet", "Upload CSV/XLSX", "Screenshot (PNG/JPG)"
])

with tab_paste:
    sample = st.text_area(
        "Paste free-form text (one item per line or numbered/bulleted):",
        value="1. abhor (v.) to hate, detest\n2) abide: to accept or act in accordance with\nmunch - to chew food loudly and completely",
        height=180,
        key="raw_text"
    )
    if st.button("Parse → Review", key="parse_from_text"):
        st.session_state["cards_df"] = parse_text_to_df(sample)

with tab_table:
    st.caption("Paste a 2-column table. We’ll try to detect columns; then you map Term/Definition.")
    pasted = st.text_area("Paste clipboard table here", height=150, key="pasted_table")
    if st.button("Parse table", key="parse_table_btn"):
        df_guess = parse_pasted_table(pasted)
        if df_guess.empty:
            st.warning("No valid rows detected. Make sure there are at least two columns (TERM | DEFINITION).")
        else:
            mapped = map_columns_ui(df_guess, key_prefix="paste_map")
            st.session_state["cards_df"] = mapped

with tab_upload:
    up = st.file_uploader("Upload CSV or Excel", type=["csv","xlsx"], key="up_sheet")
    if up is not None:
        try:
            if up.name.lower().endswith(".csv"):
                df = pd.read_csv(up)
            else:
                df = pd.read_excel(up)
            if df.empty or df.shape[1] < 2:
                st.error("Need at least two columns (term, definition).")
            else:
                st.dataframe(df.head(), use_container_width=True)
                st.info("Map columns below, then click 'Use these columns'.")
                mapped = map_columns_ui(df, key_prefix="upload_map")
                if st.button("Use these columns", key="use_upload_cols"):
                    st.session_state["cards_df"] = mapped
        except Exception as e:
            st.error(f"Could not read file: {e}")

with tab_shot:
    img = st.file_uploader("Paste or upload a screenshot (PNG/JPG)", type=["png","jpg","jpeg"], key="up_img")
    with st.expander("OCR (optional)"):
        ocr_key = st.text_input("OCR.space API key", type="password", key="ocr_key")
    extracted = ""
    if img is not None and ocr_key:
        extracted = ocr_space_image(img.read(), ocr_key) or ""
    st.text_area("Extracted text (edit before parsing):", value=extracted, height=160, key="shot_text")
    if st.button("Use extracted text", key="use_shot_text"):
        st.session_state["cards_df"] = parse_text_to_df(st.session_state.get("shot_text",""))

st.header("2) Review & edit")
df_cards = st.session_state.get("cards_df", pd.DataFrame(columns=["Front of Flash Card (term)","Back of Flash Card (definition)"]))
df_cards = df_cards.fillna("")
df_cards = st.data_editor(df_cards, num_rows="dynamic", use_container_width=True, key="editor")
st.session_state["cards_df"] = df_cards

# Live counts
num_cards = len(df_cards)
num_pages = math.ceil(max(1, num_cards) / 8) if num_cards else 0
st.caption(f"Cards: **{num_cards}**  •  Sheets (8-up): **{math.ceil(num_cards/8) if num_cards else 0}**")

st.header("3) Download PDF")
with st.expander("Print alignment", expanded=True):
    duplex_mode = st.selectbox("Duplex mode", ["Long-edge (mirrored back)","Long-edge (not mirrored)","Short-edge (mirrored back)"], index=0)
    colx, coly = st.columns(2)
    offx = colx.number_input("Back page offset X (mm)", value=0.0, step=0.25, key="offx")
    offy = coly.number_input("Back page offset Y (mm)", value=0.0, step=0.25, key="offy")
    show_corner = st.checkbox("Show tiny corner marker", value=False, key="corner")

st.subheader("Card footer")
enable_footer = st.checkbox("Include footer text on cards", value=True, key="enable_footer")
c1, c2 = st.columns(2)
subject = c1.text_input("Subject", value=st.session_state.get("subject",""), key="subject", disabled=not enable_footer)
unit    = c2.text_input("Unit / Lesson", value=st.session_state.get("unit",""), key="unit", disabled=not enable_footer)
template = st.text_input("Footer template", value=st.session_state.get("tmpl","{subject} • {unit}"), key="tmpl", disabled=not enable_footer)

if st.button("Generate PDF", type="primary"):
    if df_cards.empty:
        st.warning("Please add at least one card.")
    else:
        pdf = create_pdf(
            df=df_cards,
            duplex_mode=duplex_mode,
            offx_mm=offx,
            offy_mm=offy,
            include_footer=enable_footer,
            subject=subject,
            unit=unit,
            lesson=unit,  # support {lesson} synonym
            footer_template=template,
            show_corner=show_corner
        )
        st.success("PDF ready!")
        st.download_button("Download flashdecky_cards.pdf", data=pdf, file_name="flashdecky_cards.pdf", mime="application/pdf")
