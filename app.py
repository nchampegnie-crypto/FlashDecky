import streamlit as st
from utils.pdf_generator import generate_pdf
from utils.parser import parse_input
from components.editor import flashcard_editor
from components.uploader import upload_section

st.set_page_config(page_title="FlashDecky", layout="wide")

st.title("⚡ FlashDecky")

# Upload or paste text
with st.sidebar:
    st.header("📤 Upload or Paste")
    user_input = upload_section()

if user_input:
    terms = parse_input(user_input)
    edited_terms = flashcard_editor(terms)

    if st.button("📥 Generate PDF"):
        pdf_file = generate_pdf(edited_terms)
        st.download_button("⬇️ Download Flashcards", data=pdf_file, file_name="flashcards.pdf")
