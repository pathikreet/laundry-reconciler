import streamlit as st

if "counter" not in st.session_state:
    st.session_state.counter = 0

st.write("Counter:", st.session_state.counter)

if st.button("Increment and rerun with st.success"):
    st.session_state.counter += 1
    st.success("Success!")
    st.rerun()

if st.button("Increment and rerun with st.toast"):
    st.session_state.counter += 1
    st.toast("Toast!")
    st.rerun()

if st.button("Increment via callback with st.toast", on_click=lambda: st.toast("Toast from callback!")):
    st.session_state.counter += 1
