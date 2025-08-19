
# FlashDecky (v4.1)

A simple Streamlit app to turn lists into duplex-ready flash cards (8 per page).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Features
- Paste text, upload CSV/XLSX, paste a table, or upload an image (PNG/JPG) to OCR.
- Parsing supports numbered/bulleted lists, `:`, spaced dashes, and `term (pos) def`.
- Review & edit grid (add/remove rows).
- PDF generator (ReportLab) with 8 cards/page, dashed cut lines.
- Duplex options: **Long-edge (not mirrored)** and **Short-edge**; X/Y back page offsets.
- Optional footer with `{subject}`, `{lesson}`, `{unit}`, `{index}`, `{page}`.

## OCR for images
Add an OCR.space API key to Streamlit secrets as `OCR_SPACE_API_KEY`. Without a key, images cannot be parsed.
