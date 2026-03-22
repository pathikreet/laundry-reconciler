import streamlit as st
import time

if 'rerun_count' not in st.session_state:
    st.session_state.rerun_count = 0

st.write(f"Rerun count: {st.session_state.rerun_count}")

if st.button("Toast + Rerun"):
    st.toast("This toast should survive a rerun!")
    st.session_state.rerun_count += 1
    st.rerun()
