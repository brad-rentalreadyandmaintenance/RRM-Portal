import streamlit as st
# MUST BE FIRST
st.set_page_config(page_title="RRM Master Portal", layout="wide")

import pandas as pd
from datetime import datetime
import time
import os
import requests
import base64
from PIL import Image

# ==============================================================================
# 1. SETTINGS & SECRETS
# ==============================================================================
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
REPO_NAME = st.secrets.get("REPO_NAME", "")
BRANCH = "main"

# Path definitions
B = "data/" 
TP, P, S, W = B+"tech_pics/", B+"site_photos/", B+"signatures/", B+"work_orders/"
T, L, M, C, U = B+"tasks.csv", B+"time_log.csv", B+"material_logs.csv", B+"clients.csv", B+"users.csv"

# ==============================================================================
# 2. FAIL-SAFE INITIALIZATION
# ==============================================================================
def sync_to_github(file_path, msg="Data update"):
    if not GITHUB_TOKEN or not REPO_NAME: return 
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None
    if not os.path.exists(file_path): return
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
    payload = {"message": msg, "content": content, "branch": BRANCH}
    if sha: payload["sha"] = sha
    requests.put(url, headers=headers, json=payload)

def init_files():
    for d in [B, TP, P, S, W]:
        if not os.path.exists(d): os.makedirs(d)
    
    # Headers for every file
    headers = {
        U: ["User", "PIN", "Rate", "Pic_File"],
        C: ["Client", "Address", "Cust_Rate"],
        L: ["User", "Site", "Unit", "Date", "Time In", "Time Out", "Status", "Seconds", "Total Time", "Notes", "Photo_In", "Photo_Out"],
        T: ["AssignedTo", "Site", "Unit", "Status", "WO_File", "Timestamp"],
        M: ["Date", "User", "Site", "Material", "Cost"]
    }
    
    for p, cols in headers.items():
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            df = pd.DataFrame(columns=cols)
            df.to_csv(p, index=False)
            sync_to_github(p, "Init file")

init_files()

def load_data(f):
    try:
        return pd.read_csv(f)
    except:
        # If it fails, recreate it
        init_files()
        return pd.read_csv(f)

# ==============================================================================
# 3. LOGIN SCREEN (Simplified)
# ==============================================================================
if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    udb = load_data(U)
    
    users = ["Admin"] + (udb['User'].tolist() if not udb.empty else [])
    selected_user = st.selectbox("Who is logging in?", users)
    pin_input = st.text_input("Enter 4-Digit PIN", type="password")
    
    if st.button("LOG IN", use_container_width=True):
        if selected_user == "Admin" and pin_input == "0000":
            st.session_state.auth = True
            st.session_state.user = "Admin"
            st.rerun()
        else:
            match = udb[udb['User'] == selected_user]
            if not match.empty and str(pin_input) == str(match.iloc[0]['PIN']):
                st.session_state.auth = True
                st.session_state.user = selected_user
                st.rerun()
            else:
                st.error("Access Denied: Check PIN")
    st.stop()

# ==============================================================================
# 4. MAIN APP LOGIC
# ==============================================================================
ld, td, cd, ud = load_data(L), load_data(T), load_data(C), load_data(U)
is_admin = (st.session_state.user == "Admin")
nav = st.sidebar.radio("Menu", ["Admin", "Technician"]) if is_admin else "Technician"

if is_admin and nav == "Admin":
    t1, t2, t3, t4 = st.tabs(["Dispatch", "Clients", "Payroll", "Staff Management"])
    
    with t4: # STAFF MANAGEMENT
        st.header("👤 Staff List")
        if ud.empty:
            st.warning("No staff found in system. Use the form below to add the first one.")
        else:
            st.table(ud[['User', 'Rate']])
        
        st.divider()
        st.subheader("Add New Worker")
        with st.form("staff_add_form", clear_on_submit=True):
            new_name = st.text_input("Name")
            new_pin = st.text_input("4-Digit PIN")
            new_rate = st.number_input("Pay Rate ($/hr)", value=25.0)
            if st.form_submit_button("ADD WORKER"):
                if new_name and new_pin:
                    new_row = pd.DataFrame([{"User":new_name, "PIN":new_pin, "Rate":new_rate, "Pic_File":""}])
                    ud = pd.concat([ud, new_row], ignore_index=True)
                    ud.to_csv(U, index=False)
                    sync_to_github(U, f"Added {new_name}")
                    st.success(f"Added {new_name} to system!")
                    time.sleep(1)
                    st.rerun()

    with t2: # CLIENTS
        st.header("🏢 Client List")
        with st.form("client_add"):
            c_name = st.text_input("Company Name")
            c_addr = st.text_input("Address")
            if st.form_submit_button("SAVE CLIENT"):
                new_c = pd.DataFrame([{"Client":c_name, "Address":c_addr, "Cust_Rate":0}])
                cd = pd.concat([cd, new_c], ignore_index=True)
                cd.to_csv(C, index=False)
                sync_to_github(C, "Added Client")
                st.success("Client Added")
                st.rerun()
        st.dataframe(cd, use_container_width=True)

    with t3: # PAYROLL
        st.header("💰 Payroll Logs")
        st.dataframe(ld, use_container_width=True)

    with t1: # DISPATCH
        st.header("🚀 Active Dispatch")
        # Logic for dispatch...
        st.write("Dispatch tools active.")

else: # TECHNICIAN VIEW
    st.header(f"Welcome, {st.session_state.user}")
    st.info("Check back here for assigned tasks.")

if st.sidebar.button("Log Out"):
    st.session_state.auth = False
    st.rerun()
