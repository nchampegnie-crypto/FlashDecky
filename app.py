
import io
import os
import re
import math
import json
import requests
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.colors import black
from reportlab.lib.utils import ImageReader

# ---------------------
# Helpers
# ---------------------

def ocr_space(image_bytes, api_key):
    """Return extracted text from OCR.space; None if it fails."""
    try:
        url = "https://api.ocr.space/parse/image"
        files = {'filename': ('upload.png', image_bytes)}
        data = {"language":"eng","isOverlayRequired":"false"}
        if api_key:
            data["apikey"] = api_key
        else:
            # public test key has strict limits; better to show a friendly error
            return None, "No OCR API key configured. Add OCR_SPACE_API_KEY to Streamlit secrets."
        r = requests.post(url, files=files, data=data, timeout=60)
        r.raise_for_status()
        js = r.json()
        if js.get("IsErroredOnProcessing"):
            return None, js.get("ErrorMessage") or "OCR processing error"
        text = "".join(p.get("ParsedText","") for p in js.get("ParsedResults",[]))
        return text, None
    except Exception as e:
        return None, str(e)

def split_rows(text):
    """Split text into logical rows by list markers; keep wrapped lines together."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    rows = []
    buf = []
    for ln in lines:
        if not ln.strip():
            # keep blank as a separator for paragraphs
            if buf:
                rows.append(" ".join(buf).strip())
                buf = []
            continue
        # new-row markers: numbered 1. / 1) or bullets -, •, *
        if re.match(r'^\s*(\d+)[\.\)]\s+', ln) or re.match(r'^\s*[•\-\*]\s+', ln):
            if buf:
                rows.append(" ".join(buf).strip())
                buf = []
            # remove the marker
            ln = re.sub(r'^\s*(?:\d+[\.\)]\s+|[•\-\*]\s+)', '', ln, count=1)
            buf.append(ln)
        else:
            buf.append(ln)
    if buf:
        rows.append(" ".join(buf).strip())
    # as a fallback: if no markers at all and multiple lines, treat each non-empty line as its own row
    if len(rows)==1 and '\n' in text:
        candidates = [l.strip() for l in text.splitlines() if l.strip()]
        if len(candidates) > 1:
            rows = candidates
    return rows

SEP_REGEXES = [
    re.compile(r'\t'),                                # tab
    re.compile(r':(?![^()]*\))'),                    # first colon not inside parentheses
    re.compile(r'\s—\s|\s–\s|\s-\s'),                # spaced dashes
]

def parse_term_def(line):
    # dictionary pattern: term (pos) definition
    m = re.match(r'^\s*([^()]+?)\s*\([^)]*\)\s+(.+)$', line)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    for rx in SEP_REGEXES:
        sp = rx.split(line, maxsplit=1)
        if len(sp)==2:
            return sp[0].strip(), sp[1].strip()

    # fallback: single token as term, rest as def if possible
    sp = line.split(None, 1)
    if len(sp)==2:
        return sp[0].strip(), sp[1].strip()
    return line.strip(), ""

def text_to_df(text):
    text = text.replace('\u2019',"'").replace('\u2013','–').replace('\u2014','—')
    rows = split_rows(text)
    data = [parse_term_def(r) for r in rows if r.strip()]
    df = pd.DataFrame(data, columns=["Front of Flash Card (term)","Back of Flash Card (definition)"])
    return df

def sheet_layout(pdf, cards):
    """Compute positions for 8 cards on US Letter portrait (2 cols x 4 rows)."""
    # margins and grid
    W, H = letter
    cols = 2
    rows = 4
    gutter = 12 * mm
    margin_x = 15 * mm
    margin_y = 18 * mm
    card_w = (W - 2*margin_x - gutter) / cols
    card_h = (H - 2*margin_y - gutter* (rows-1)) / rows
    positions = []
    for r in range(rows):
        for c in range(cols):
            x = margin_x + c*(card_w + gutter)
            y = H - margin_y - (r+1)*card_h - r*gutter
            positions.append((x,y,card_w,card_h))
    return positions

def draw_card(pdf, x,y,w,h, front_text, footer_text=None, small=False):
    # dashed cut rect
    pdf.setDash(4,4)
    pdf.rect(x, y, w, h)
    pdf.setDash()

    # text box
    left = x + 10*mm
    top = y + h - 12*mm
    max_w = w - 20*mm
    pdf.setFont("Helvetica-Bold", 14 if not small else 12)
    pdf.drawString(left, top, front_text[:80])

    # footer
    if footer_text:
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(black)
        pdf.drawRightString(x + w - 6*mm, y + 6*mm, footer_text)

def draw_back(pdf, x,y,w,h, back_text, footer_text=None):
    pdf.setDash(4,4)
    pdf.rect(x, y, w, h)
    pdf.setDash()

    left = x + 10*mm
    top = y + h - 18*mm
    max_w = w - 20*mm
    # wrap definition roughly
    pdf.setFont("Helvetica", 11)
    # naive wrap
    words = back_text.split()
    lines, cur = [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if len(test) > 70:
            lines.append(cur)
            cur = wd
        else:
            cur = test
    if cur: lines.append(cur)
    yline = top
    for ln in lines[:12]:
        pdf.drawString(left, yline, ln)
        yline -= 12
    if footer_text:
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(x + w - 6*mm, y + 6*mm, footer_text)

def build_pdf(cards_df, duplex_mode, offset_x_mm, offset_y_mm, footer_on, subject, lesson, footer_tpl):
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    pos = sheet_layout(pdf, cards_df)
    N = len(cards_df)
    per_page = 8

    def footer(idx, page):
        if not footer_on:
            return None
        local = {
            "subject": subject or "",
            "lesson": lesson or "",
            "unit": lesson or "",
            "index": idx,
            "page": page,
        }
        try:
            return footer_tpl.format(**local)
        except Exception:
            return f"{subject or ''} {lesson or ''}".strip()

    page = 1
    for i in range(0, N, per_page):
        batch = cards_df.iloc[i:i+per_page]
        # FRONT
        for j, (_,row) in enumerate(batch.iterrows()):
            x,y,w,h = pos[j]
            draw_card(pdf, x,y,w,h, str(row[0]), footer(idx=i+j+1, page=page))
        pdf.showPage()

        # BACK
        # Alignment: Long-edge (not mirrored) vs Short-edge (rotate 180)
        rotate = (duplex_mode == "Short-edge")
        # apply offsets
        offx = offset_x_mm * mm
        offy = offset_y_mm * mm

        for j, (_,row) in enumerate(batch.iterrows()):
            x,y,w,h = pos[j]
            # For long-edge (not mirrored), keep same positions.
            # For short-edge, rotate around page center.
            if rotate:
                W,H = letter
                pdf.saveState()
                pdf.translate(W/2, H/2)
                pdf.rotate(180)
                pdf.translate(-W/2, -H/2)
                draw_back(pdf, x + offx, y + offy, w, h, str(row[1]), footer(idx=i+j+1, page=page))
                pdf.restoreState()
            else:
                draw_back(pdf, x + offx, y + offy, w, h, str(row[1]), footer(idx=i+j+1, page=page))

        pdf.showPage()
        page += 1

    pdf.save()
    buf.seek(0)
    return buf

# ---------------------
# App UI / State
# ---------------------

st.set_page_config(page_title="FlashDecky", page_icon="⚡", layout="wide")

if "step" not in st.session_state:
    st.session_state.step = 1
if "cards_df" not in st.session_state:
    st.session_state.cards_df = None

# Sidebar progress
with st.sidebar:
    st.markdown("### Progress")
    s = st.session_state.step
    st.markdown(("✅" if s>1 else "➤") + " 1) Upload / Paste")
    st.markdown(("✅" if s>2 else "➤") + " 2) Review & Edit")
    st.markdown(("✅" if s>3 else "➤") + " 3) Download PDF")

st.title("⚡ FlashDecky")
st.caption("Turn any list into perfect, printable flash cards (8 per page, duplex‑ready).")

# STEP 1 -----------------------------------------------------------------
if st.session_state.step == 1:
    with st.expander("How to use (quick)", expanded=False):
        st.markdown("""
        - Paste text, upload CSV/XLSX, paste a table, or upload an image (PNG/JPG) of a list.
        - We auto-parse lines like `1) term — definition`, `term : definition`, or `term (v.) definition`.
        - Click **Submit** to review and edit.
        """)

    col1,col2,col3 = st.columns([1,1,1])
    with col1:
        st.subheader("Paste text")
        sample = "1) term — definition\n2) another term: definition line wraps ok\n• third term - definition"
        pasted = st.text_area("Your list", value=sample, height=230, label_visibility="collapsed")
    with col2:
        st.subheader("Upload file (CSV/XLSX/PNG/JPG)")
        file = st.file_uploader("Choose a CSV, Excel, or image file", type=["csv","xlsx","png","jpg","jpeg"], accept_multiple_files=False)
        uploaded_text = ""
        if file is not None:
            if file.type in ("image/png","image/jpeg"):
                api_key = st.secrets.get("OCR_SPACE_API_KEY", None)
                text, err = ocr_space(file.read(), api_key)
                if err:
                    st.error(f"OCR error: {err}")
                else:
                    uploaded_text = text or ""
                    st.success("Image text extracted ✔")
                    st.text_area("Extracted text (you can edit)", value=uploaded_text, height=180, key="ocr_out")
            elif file.type in ("text/csv","application/vnd.ms-excel","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
                try:
                    if file.type == "text/csv":
                        df = pd.read_csv(file)
                    else:
                        df = pd.read_excel(file)
                    st.dataframe(df.head())
                    # map columns if possible
                    if df.shape[1] >= 2:
                        c1 = st.selectbox("Front column", options=df.columns, index=0)
                        c2 = st.selectbox("Back column", options=df.columns, index=1)
                        uploaded_text = "\n".join([f"{str(a)}\t{str(b)}" for a,b in zip(df[c1], df[c2])])
                except Exception as e:
                    st.error(f"Failed to read file: {e}")
    with col3:
        st.subheader("Paste table (Excel/Sheets)")
        st.caption("Paste two columns (Front TAB Back)")
        table_text = st.text_area("Paste a tab-separated table", value="", height=230, label_visibility="collapsed")

    # Submit
    st.markdown("---")
    if st.button("Submit ➜ Review", type="primary"):
        raw = ""
        if uploaded_text:
            raw = uploaded_text
        elif table_text.strip():
            raw = table_text
        else:
            raw = pasted

        df = text_to_df(raw)
        st.session_state.cards_df = df
        st.session_state.step = 2
        st.experimental_rerun()

# STEP 2 -----------------------------------------------------------------
if st.session_state.step == 2:
    st.header("2) Review & edit")
    st.caption("Click a cell to edit. Add/remove rows if needed.")
    df = st.session_state.cards_df.copy()

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True
    )
    colA, colB = st.columns([1,1])
    with colA:
        if st.button("⬅ Back to upload"):
            st.session_state.step = 1
            st.experimental_rerun()
    with colB:
        if st.button("Continue ➜ Download PDF", type="primary"):
            st.session_state.cards_df = edited
            st.session_state.step = 3
            st.experimental_rerun()

# STEP 3 -----------------------------------------------------------------
if st.session_state.step == 3:
    st.header("3) Download PDF")

    with st.expander("Print alignment", expanded=True):
        duplex = st.selectbox("Duplex mode", ["Long-edge (not mirrored)", "Short-edge"])
        offx = st.number_input("Back page offset X (mm)", value=0.0, step=0.25)
        offy = st.number_input("Back page offset Y (mm)", value=0.0, step=0.25)
        tiny = st.checkbox("Show tiny corner marker", value=False)

    st.subheader("Card footer (subject • lesson)")
    on = st.checkbox("Include footer text on cards", value=True)
    subj = st.text_input("Subject", value="")
    lesson = st.text_input("Lesson / Unit", value="")
    tpl = st.text_input("Footer template", value="{subject} • {lesson}")

    if st.button("Generate PDF", type="primary"):
        buf = build_pdf(
            st.session_state.cards_df,
            duplex_mode = "Short-edge" if duplex=="Short-edge" else "Long-edge (not mirrored)",
            offset_x_mm = float(offx),
            offset_y_mm = float(offy),
            footer_on = on,
            subject = subj,
            lesson = lesson,
            footer_tpl = tpl
        )
        st.download_button("Download flashcards.pdf", data=buf, file_name="flashcards.pdf", mime="application/pdf")
    if st.button("⬅ Back to edit"):
        st.session_state.step = 2
        st.experimental_rerun()
