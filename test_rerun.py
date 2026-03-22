import streamlit as st
import time

if st.button("Test Success + Rerun"):
    st.success("This should be seen")
    time.sleep(1) # just to simulate work
    st.rerun()

if st.button("Test Toast + Rerun"):
    st.toast("This is a toast")
    st.rerun()
