import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
from src.ui.app import render_notepad_step, get_session

if 'imports' not in st.session_state:
    st.session_state.imports = {
        'crm_sales': {'done': True, 'result': None},
        'crm_orders': {'done': False, 'result': None},
        'crm_delivery': {'done': False, 'result': None},
        'mswipe': {'done': False, 'result': None},
        'notepad': {'done': False, 'result': None},
        'cash_register': {'done': False, 'result': None},
    }

session_db = get_session()
render_notepad_step(session_db, is_unlocked=True)
