import streamlit as st
import pandas as pd
import os
import requests
import base64

# 1. PAGE SETUP (MUST BE FIRST)
st.set_page_config(page_title="RRM Portal", layout="wide")

# 2. GITHUB CONFIG
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
REPO_NAME = st.secrets.get("REPO_NAME", "")

# 3. DIRECTORY & FILE SETUP
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

U_PATH = os.path.join(DATA_DIR, "users.csv")
C_PATH = os.path.join(DATA_DIR, "clients.csv")
L_PATH = os.path.join(DATA_DIR, "time_log.csv")

def sync_to_github(file_path, msg="Update"):
    if not GITHUB_TOKEN or not REPO_NAME: return
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        res = requests.get(url, headers=headers)
        sha = res.json().get('sha') if res.status_code == 200 else None
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        payload = {"message": msg, "content": content, "branch": "main"}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except Exception as e:
        st.error(f"GitHub Sync Error: {e}")

# 4. INITIALIZE DATA (Headers)
def init_csv(path, cols):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        pd.DataFrame(columns=cols).to_csv(path, index=False)
        sync_to_github(path, "Init File")

init_csv(U_PATH, ["User", "PIN", "Rate"])
init_csv(C_PATH, ["Client", "Address"])
init_csv(L_PATH, ["User", "Site", "Unit", "Date", "Time In", "Time Out", "Status", "Duration", "Notes"])

# 5. LOAD DATA
ud = pd.read_csv(U_PATH)
cd = pd.read_csv(C_PATH)
ld = pd.read_csv(L_PATH)

# 6. APP INTERFACE
st.title("🛠️ RRM Admin Portal")

# Sidebar for Login State
if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.subheader("🔐 Admin Login")
    pwd = st.text_input("Enter Admin PIN", type="password")
    if st.button("Access Portal"):
        if pwd == "0000":
            st.session_state.auth = True
            st.rerun()
        else: st.error("Wrong PIN")
    st.stop()

# TABS
t1, t2, t3, t4 = st.tabs(["Dispatch", "Clients", "Payroll", "Staff"])

with t1:
    st.header("🚀 Dispatch Job")
    with st.form("dispatch_form"):
        tech = st.selectbox("Assign Tech", ud['User'].tolist() if not ud.empty else ["No Staff"])
        clnt = st.selectbox("Select Client", cd['Client'].tolist() if not cd.empty else ["No Clients"])
        unit = st.text_input("Unit #")
        if st.form_submit_button("Send Job"):
            st.success("Job Dispatched!")

with t2:
    st.header("🏢 Client Manager")
    with st.form("add_client"):
        c_name = st.text_input("New Client Name")
        c_addr = st.text_input("New Client Address")
        if st.form_submit_button("Add Client"):
            new_c = pd.DataFrame([{"Client": c_name, "Address": c_addr}])
            cd = pd.concat([cd, new_c], ignore_index=True)
            cd.to_csv(C_PATH, index=False)
            sync_to_github(C_PATH, "Added Client")
            st.success("Client Saved!")
            st.rerun()
    
    st.divider()
    st.write("### Current Clients")
    if not cd.empty:
        st.dataframe(cd, use_container_width=True)
        # UPDATE LOGIC
        sel_c = st.selectbox("Edit Client", cd['Client'].tolist())
        idx = cd[cd['Client'] == sel_c].index[0]
        new_a = st.text_input("Update Address", cd.at[idx, 'Address'])
        if st.button("Update Address"):
            cd.at[idx, 'Address'] = new_a
            cd.to_csv(C_PATH, index=False)
            sync_to_github(C_PATH, "Updated Client")
            st.success("Updated!")
            st.rerun()

with t3:
    st.header("💰 Payroll Audit")
    if ld.empty: st.info("No work logs found yet.")
    else: st.dataframe(ld, use_container_width=True)

with t4:
    st.header("👤 Staff Management")
    # FORM IS OUTSIDE OF "IF EMPTY" TO ENSURE IT ALWAYS SHOWS
    with st.form("add_staff"):
        st.write("### Add New Staff Member")
        sn = st.text_input("Staff Name")
        sp = st.text_input("4-Digit PIN")
        sr = st.number_input("Pay Rate", value=25.0)
        if st.form_submit_button("Save Staff"):
            if sn and sp:
                new_s = pd.DataFrame([{"User": sn, "PIN": sp, "Rate": sr}])
                ud = pd.concat([ud, new_s], ignore_index=True)
                ud.to_csv(U_PATH, index=False)
                sync_to_github(U_PATH, f"Added {sn}")
                st.success(f"Added {sn}!")
                st.rerun()

    st.divider()
    st.write("### Current Staff List")
    if not ud.empty:
        st.dataframe(ud[['User', 'Rate']], use_container_width=True)
    else:
        st.warning("No staff members found. Add one above.")

if st.sidebar.button("Logout"):
    st.session_state.auth = False
    st.rerun()
