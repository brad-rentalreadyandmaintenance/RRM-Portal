import streamlit as st
import pandas as pd
import os

# 1. MUST BE FIRST
st.set_page_config(page_title="RRM Recovery", layout="wide")

# 2. SIMPLE LOGIN STATE
if 'auth' not in st.session_state:
    st.session_state.auth = False

# 3. EMERGENCY LOGIN SCREEN
if not st.session_state.auth:
    st.title("🔐 RRM Emergency Access")
    st.write("If you can see this, the app is alive.")
    
    user_choice = st.selectbox("User", ["Admin", "Tech Test"])
    pin_input = st.text_input("PIN", type="password")
    
    if st.button("LOG IN"):
        if user_choice == "Admin" and pin_input == "0000":
            st.session_state.auth = True
            st.session_state.user = "Admin"
            st.rerun()
        else:
            st.error("Try Admin and 0000")
    st.stop()

# 4. SIMPLE TABS
st.title(f"Welcome, {st.session_state.user}")
t1, t2 = st.tabs(["Staff", "Settings"])

with t1:
    st.header("Staff Management")
    st.write("Testing if this tab renders...")
    with st.form("test_form"):
        name = st.text_input("Name")
        if st.form_submit_button("Test Add"):
            st.success(f"Form works! Hello {name}")

with t2:
    if st.button("Log Out"):
        st.session_state.auth = False
        st.rerun()
