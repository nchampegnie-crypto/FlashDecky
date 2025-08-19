import streamlit as st

def flashcard_editor(terms):
    st.subheader("✏️ Edit Flashcards")
    edited = []
    for i, (term, definition) in enumerate(terms):
        col1, col2 = st.columns(2)
        with col1:
            term = st.text_input(f"Term {i+1}", term)
        with col2:
            definition = st.text_input(f"Definition {i+1}", definition)
        edited.append((term, definition))
    return edited
