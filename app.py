import streamlit as st
import pandas as pd
import os
import requests
import base64

# 1. PAGE SETUP
st.set_page_config(page_title="RRM Master Portal", layout="wide")

# 2. LOAD SECRETS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")

# 3. DIRECTORY SETUP
if not os.path.exists("data"):
    os.makedirs("data")

U_PATH = "data/users.csv"

# 4. GITHUB SYNC FUNCTION (Targeting 'master' branch)
def sync_to_github(file_path):
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        # Get the file SHA if it exists
        res = requests.get(url, headers=headers)
        sha = res.json().get('sha') if res.status_code == 200 else None
        
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        
        payload = {
            "message": "Update Staff Data",
            "content": content,
            "branch": "master"  # Set to master based on your repo
        }
        if sha:
            payload["sha"] = sha
            
        put_res = requests.put(url, headers=headers, json=payload)
        if put_res.status_code in [200, 201]:
            st.sidebar.success("✅ GitHub Sync Successful")
        else:
            st.sidebar.error(f"❌ Sync Failed: {put_res.json().get('message')}")
    except Exception as e:
        st.sidebar.error(f"⚠️ Error: {str(e)}")

# 5. DATA INITIALIZATION
if not os.path.exists(U_PATH):
    pd.DataFrame(columns=["User", "PIN", "Rate"]).to_csv(U_PATH, index=False)

ud = pd.read_csv(U_PATH)

# 6. LOGIN SYSTEM
if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    pin_attempt = st.text_input("Admin PIN", type="password")
    if st.button("Enter Portal"):
        if pin_attempt == "0000":
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Access Denied")
    st.stop()

# 7. ADMIN INTERFACE
st.title("🛠️ RRM Admin Dashboard")
tabs = st.tabs(["Staff Management", "System Debug"])

with tabs[0]:
    st.header("👤 Staff Roster")
    with st.form("staff_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Worker Name")
        with col2:
            new_pin = st.text_input("4-Digit PIN")
        new_rate = st.number_input("Hourly Rate", value=25.0)
        
        if st.form_submit_button("ADD WORKER"):
            if new_name and new_pin:
                new_data = pd.DataFrame([{"User": new_name, "PIN": new_pin, "Rate": new_rate}])
                ud = pd.concat([ud, new_data], ignore_index=True)
                ud.to_csv(U_PATH, index=False)
                sync_to_github(U_PATH) # Pushes to GitHub
                st.success(f"Added {new_name}")
                st.rerun()

    st.divider()
    st.write("### Current Employees")
    st.dataframe(ud, use_container_width=True)

with tabs[1]:
    st.write("### Connection Status")
    st.write(f"**Target Repo:** {REPO_NAME}")
    st.write(f"**Token Configured:** {'Yes' if GITHUB_TOKEN else 'No'}")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
