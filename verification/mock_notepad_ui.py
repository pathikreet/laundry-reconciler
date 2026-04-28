import streamlit as st
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.ui.app import render_notepad_step
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

if 'imports' not in st.session_state:
    st.session_state.imports = {
        'notepad': {'done': False, 'result': None}
    }

engine = create_engine('sqlite:///:memory:')
Session = sessionmaker(bind=engine)
session = Session()

st.title("Notepad Step Isolated Mock")
render_notepad_step(session, is_unlocked=True)
