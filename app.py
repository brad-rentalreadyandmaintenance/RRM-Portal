import streamlit as st
import pandas as pd
import os
import requests
import base64

# 1. SETUP (Must be the very first Streamlit command)
st.set_page_config(page_title="RRM Portal v3", layout="wide")

# 2. DATA PATHS
if not os.path.exists("data"):
    os.makedirs("data")

U_PATH = "data/users.csv"
C_PATH = "data/clients.csv"

# 3. GITHUB SYNC (Safe Mode)
def sync_data(file_path):
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("REPO_NAME")
    if not token or not repo:
        return # Skip sync if secrets aren't set yet

    try:
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        headers = {"Authorization": f"token {token}"}
        res = requests.get(url, headers=headers)
        sha = res.json().get('sha') if res.status_code == 200 else None
        
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        
        payload = {"message": "Update", "content": content, "branch": "main"}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except Exception as e:
        st.sidebar.error(f"Sync Error: {e}")

# 4. INIT FILES
for path, cols in {U_PATH: ["User", "PIN", "Rate"], C_PATH: ["Client", "Address"]}.items():
    if not os.path.exists(path):
        pd.DataFrame(columns=cols).to_csv(path, index=False)

# 5. LOAD DATA
try:
    ud = pd.read_csv(U_PATH)
    cd = pd.read_csv(C_PATH)
except Exception as e:
    st.error(f"File Load Error: {e}")
    st.stop()

# 6. LOGIN (Simplified for testing)
if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Login")
    pin = st.text_input("Admin PIN", type="password")
    if st.button("Log In"):
        if pin == "0000":
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Incorrect PIN")
    st.stop()

# 7. MAIN TABS
t1, t2 = st.tabs(["Staff Management", "Client Manager"])

with t1:
    st.header("👤 Staff Roster")
    with st.form("staff_form_v4", clear_on_submit=True):
        name = st.text_input("Worker Name")
        pcode = st.text_input("4-Digit PIN")
        if st.form_submit_button("ADD WORKER"):
            if name and pcode:
                new_u = pd.DataFrame([{"User": name, "PIN": pcode, "Rate": 25.0}])
                ud = pd.concat([ud, new_u], ignore_index=True)
                ud.to_csv(U_PATH, index=False)
                sync_data(U_PATH)
                st.success(f"Added {name}!")
                st.rerun()
    st.divider()
    st.dataframe(ud, use_container_width=True)

with t2:
    st.header("🏢 Clients")
    with st.form("client_form_v4"):
        cname = st.text_input("Company Name")
        caddr = st.text_input("Address")
        if st.form_submit_button("Save Client"):
            new_c = pd.DataFrame([{"Client": cname, "Address": caddr}])
            cd = pd.concat([cd, new_c], ignore_index=True)
            cd.to_csv(C_PATH, index=False)
            sync_data(C_PATH)
            st.success("Saved!")
            st.rerun()
    st.dataframe(cd, use_container_width=True)

if st.sidebar.button("Logout"):
    st.session_state.auth = False
    st.rerun()
