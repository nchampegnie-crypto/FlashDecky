# FlashDecky Final (v1.0.0)

A stable Streamlit app that converts lists (or spreadsheets/screenshots) into **8-up, duplex-ready** flashcards (US Letter).

## Features
- Inputs:
  - Paste free-form text (supports `term - def`, `term: def`, en/em dash, dictionary style like `word (v.) ...`).
  - Paste table from Excel/Google Sheets with column mapping.
  - Upload CSV/XLSX with column mapping.
  - Upload/paste **screenshots (PNG/JPG)** → optional OCR via OCR.space (only if user supplies API key).
- Parsing:
  - New item by number/bullet or line with separators; wrapped lines append to previous definition.
  - Priority order: tab → colon (outside parentheses) → spaced hyphen/en/em dash → dictionary pattern.
- Review & Edit:
  - Editable grid with headers: **Front of Flash Card (term)** / **Back of Flash Card (definition)**.
  - Live counts: cards and sheets (8 per page).
- PDF & Print Alignment:
  - 8-up layout with dashed cut guides.
  - Duplex modes: **Long-edge (mirrored back)** (default), Long-edge (not mirrored), Short-edge (mirrored back).
  - Back-page offsets (X/Y in mm) and optional tiny corner marker.
  - Auto-wrap definitions; slight font downscale if overflowing.
- Footer on cards:
  - Toggle + Subject + Unit/Lesson + Template; supports `{subject}`, `{unit}`, `{lesson}`, `{index}`, `{page}`.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
