import streamlit as st

def upload_section():
    uploaded_file = st.file_uploader("Upload a text/Excel file", type=["txt", "csv", "xlsx"])
    text_input = st.text_area("Or paste your text here")
    
    if uploaded_file:
        return uploaded_file.read().decode("utf-8")
    elif text_input:
        return text_input
    return None
