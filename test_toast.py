import streamlit as st

if "entries" not in st.session_state:
    st.session_state.entries = []

with st.expander("Add entry"):
    val = st.text_input("Value")
    if st.button("Add"):
        st.session_state.entries.append(val)
        st.toast(f"Added {val}!")
        st.rerun()

st.write(st.session_state.entries)
