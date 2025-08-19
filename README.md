# FlashDecky

Turn any list into perfect, printable flash cards (8 per page, duplex-ready).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Features
- Paste free-form text OR upload CSV/XLSX OR paste a tab-separated table
- Smart parser for numbered/bulleted lists, wrapped definitions, dictionary formats (`term (pos) def`), `term : def`, `term — def`, tab-splits
- Review & edit in an editable grid
- PDF generator (ReportLab): 8 cards per US Letter, dashed cut lines
- Duplex alignment:
  - Long-edge (mirrored back) — default
  - Long-edge (not mirrored)
  - Short-edge
- Fine-tune back page X/Y offsets (mm)
- Optional footer per card with template: `{subject}`, `{lesson}`, `{unit}`, `{index}`, `{page}`

## Deploy on Streamlit Cloud
- Push this folder to GitHub (e.g., `flashdecky/` repo)
- On Streamlit Cloud, set:
  - **Main file path:** `app.py`
  - **Python version:** 3.10+
  - **Dependencies:** from `requirements.txt`
