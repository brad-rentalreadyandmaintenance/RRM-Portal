import streamlit as st
import pandas as pd
import os
import requests
import base64

# 1. SETUP
st.set_page_config(page_title="RRM Portal v3", layout="wide")

# 2. DATA PATHS
if not os.path.exists("data"):
    os.makedirs("data")

U_PATH = "data/users.csv"
C_PATH = "data/clients.csv"

# 3. GITHUB SYNC (WITH SAFETY VALVE)
def sync_data(file_path):
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("REPO_NAME")
    if not token or not repo:
        st.warning("GitHub Token/Repo not found in Secrets. Saving locally only.")
        return

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
        st.error(f"Sync Error: {e}")

# 4. INIT FILES
for path, cols in {U_PATH: ["User", "PIN", "Rate"], C_PATH: ["Client", "Address"]}.items():
    if not os.path.exists(path):
        pd.DataFrame(columns=cols).to_csv(path, index=False)

# 5. LOAD
ud = pd.read_csv(U_PATH)
cd = pd.read_csv(C_PATH)

# 6. ADMIN LOGIN
if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Admin Login")
    if st.text_input("PIN", type="password") == "0000":
        if st.button("Login"):
            st.session_state.auth = True
            st.rerun()
    st.stop()

# 7. TABS
t1, t2 = st.tabs(["Staff", "Clients"])

with t1:
    st.header("Staff Management")
    with st.form("add_staff_final"):
        name = st.text_input("Name")
        pin = st.text_input("PIN")
        if st.form_submit_button("Add Worker"):
            new_u = pd.DataFrame([{"User": name, "PIN": pin, "Rate": 25.0}])
            ud = pd.concat([ud, new_u], ignore_index=True)
            ud.to_csv(U_PATH, index=False)
            sync_data(U_PATH)
            st.success("Added!")
            st.rerun()
    st.dataframe(ud)

with t2:
    st.header("Client Manager")
    with st.form("add_client_final"):
        cname = st.text_input("Client Name")
        caddr = st.text_input("Address")
        if st.form_submit_button("Save Client"):
            new_c = pd.DataFrame([{"Client": cname, "Address": caddr}])
            cd = pd.concat([cd, new_c], ignore_index=True)
            cd.to_csv(C_PATH, index=False)
            sync_data(C_PATH)
            st.success("Saved!")
            st.rerun()
    st.dataframe(cd)
