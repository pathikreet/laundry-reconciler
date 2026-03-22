import streamlit as st
import time

if st.button("Test Flash"):
    st.success("You will barely see this!")
    st.rerun()

if st.button("Test Sleep"):
    st.success("You will see this for 1s")
    time.sleep(1)
    st.rerun()

if st.button("Test Toast"):
    st.toast("This is a toast!", icon="🍞")
    time.sleep(1)
    st.rerun()
