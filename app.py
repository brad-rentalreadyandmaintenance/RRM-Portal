import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime

# 1. SETUP
st.set_page_config(page_title="RRM Portal", layout="wide")

# 2. GITHUB SETTINGS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
REPO_NAME = st.secrets.get("REPO_NAME", "")

# 3. PATHS & INITIALIZATION
B = "data/"
U, C, L, T = B+"users.csv", B+"clients.csv", B+"time_log.csv", B+"tasks.csv"

def sync_to_github(file_path, msg="Update"):
    if not GITHUB_TOKEN or not REPO_NAME: return
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
    payload = {"message": msg, "content": content, "branch": "main"}
    if sha: payload["sha"] = sha
    requests.put(url, headers=headers, json=payload)

# Initialize files with correct headers if they don't exist
if not os.path.exists(B): os.makedirs(B)
headers = {
    U: ["User", "PIN", "Rate"],
    C: ["Client", "Address"],
    L: ["User", "Site", "Unit", "Date", "Time In", "Time Out", "Status", "Duration", "Notes"],
    T: ["AssignedTo", "Site", "Unit", "Status"]
}
for f, cols in headers.items():
    if not os.path.exists(f) or os.path.getsize(f) == 0:
        pd.DataFrame(columns=cols).to_csv(f, index=False)

# 4. DATA LOADING
ud = pd.read_csv(U)
cd = pd.read_csv(C)
ld = pd.read_csv(L)
td = pd.read_csv(T)

# 5. ADMIN VIEW
st.title("🛠️ RRM Admin Portal")
t1, t2, t3, t4 = st.tabs(["Dispatch", "Clients", "Payroll Audit", "Staff Management"])

with t1: # DISPATCH
    st.subheader("🚀 Dispatch Work Order")
    with st.form("dispatch_form"):
        # Use existing staff list for dropdown
        t_list = ud['User'].tolist() if not ud.empty else ["No Staff Found"]
        target_t = st.selectbox("Assign To", t_list)
        target_c = st.selectbox("Select Client", cd['Client'].tolist() if not cd.empty else ["No Clients Found"])
        unit = st.text_input("Unit/Job Details")
        if st.form_submit_button("Send Job"):
            new_job = pd.DataFrame([{"AssignedTo": target_t, "Site": target_c, "Unit": unit, "Status": "Pending"}])
            td = pd.concat([td, new_job], ignore_index=True)
            td.to_csv(T, index=False); sync_to_github(T, "Dispatched Job")
            st.success("Job Dispatched!"); st.rerun()

with t2: # CLIENTS (Added Edit/Update Function)
    st.subheader("🏢 Client Manager")
    with st.form("add_client"):
        c_name = st.text_input("Client Name")
        c_addr = st.text_input("Address")
        if st.form_submit_button("Save New Client"):
            new_c = pd.DataFrame([{"Client": c_name, "Address": c_addr}])
            cd = pd.concat([cd, new_c], ignore_index=True)
            cd.to_csv(C, index=False); sync_to_github(C, "Added Client")
            st.success("Client Saved!"); st.rerun()
    
    if not cd.empty:
        st.divider()
        st.write("### Edit Existing Clients")
        edit_c = st.selectbox("Select Client to Update", cd['Client'].tolist())
        c_idx = cd[cd['Client'] == edit_c].index[0]
        new_addr = st.text_input("Update Address", cd.at[c_idx, 'Address'])
        if st.button("Update Client Info"):
            cd.at[c_idx, 'Address'] = new_addr
            cd.to_csv(C, index=False); sync_to_github(C, "Updated Client")
            st.success("Updated!"); st.rerun()

with t3: # PAYROLL AUDIT (Now shows the list)
    st.subheader("📊 Payroll Audit")
    if ld.empty:
        st.info("No time logs found. Once a tech clocks out, entries will appear here.")
    else:
        st.dataframe(ld, use_container_width=True)

with t4: # STAFF MANAGEMENT (Guaranteed to show)
    st.subheader("👤 Staff Management")
    with st.form("add_staff_new"):
        st.write("Add a New Staff Member")
        sn = st.text_input("Name")
        sp = st.text_input("PIN (4 Digits)")
        sr = st.number_input("Pay Rate ($/hr)", value=25.0)
        if st.form_submit_button("Save Staff"):
            if sn and sp:
                new_s = pd.DataFrame([{"User": sn, "PIN": sp, "Rate": sr}])
                ud = pd.concat([ud, new_s], ignore_index=True)
                ud.to_csv(U, index=False); sync_to_github(U, f"Added {sn}")
                st.success(f"Added {sn}!"); st.rerun()
    
    if not ud.empty:
        st.divider()
        st.write("### Current Staff")
        st.dataframe(ud[['User', 'Rate']], use_container_width=True)
