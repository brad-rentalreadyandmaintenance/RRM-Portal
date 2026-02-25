import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime

# 1. PAGE SETUP
st.set_page_config(page_title="RRM Master Portal", layout="wide")

# 2. CONFIG & GITHUB SETTINGS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

U_PATH, C_PATH, L_PATH, T_PATH = "data/users.csv", "data/clients.csv", "data/logs.csv", "data/tasks.csv"

# 3. GITHUB SYNC FUNCTIONS (The "Memory" Logic)
def pull_from_github(path):
    """Pulls the latest file from GitHub to local storage on boot."""
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            content = base64.b64decode(res.json()['content']).decode('utf-8')
            with open(path, "w") as f:
                f.write(content)
    except: pass

def push_to_github(path):
    """Saves local changes up to GitHub."""
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        res = requests.get(url, headers=headers)
        sha = res.json().get('sha') if res.status_code == 200 else None
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        payload = {"message": "Data Backup", "content": content, "branch": "master"}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except: pass

# 4. STARTUP BOOT (Runs only once when the server starts)
if 'booted' not in st.session_state:
    for p in [U_PATH, C_PATH, L_PATH, T_PATH]:
        pull_from_github(p)
    st.session_state.booted = True

# 5. DATA LOADING
def load_data(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    return pd.read_csv(path)

ud = load_data(U_PATH, ["User", "PIN", "Rate"])
cd = load_data(C_PATH, ["Client", "Address"])
ld = load_data(L_PATH, ["User", "Client", "In", "Out", "Date", "Notes"])
td = load_data(T_PATH, ["Tech", "Client", "Unit", "Status"])

# 6. AUTHENTICATION (Persists through Refresh)
if 'auth' not in st.session_state: 
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    u_type = st.radio("Mode", ["Admin", "Technician"])
    
    if u_type == "Admin":
        if st.text_input("Admin PIN", type="password") == "0000":
            if st.button("Access"):
                st.session_state.update({"auth": True, "role": "Admin", "user": "Admin"})
                st.rerun()
    else:
        if ud.empty: st.warning("Add staff in Admin mode first."); st.stop()
        t_name = st.selectbox("Worker", ud['User'])
        if st.text_input("PIN", type="password") == str(ud[ud['User']==t_name].iloc[0]['PIN']):
            if st.button("Login"):
                st.session_state.update({"auth": True, "role": "Tech", "user": t_name})
                st.rerun()
    st.stop()

# 7. NAVIGATION
st.sidebar.title(f"Logged in: {st.session_state.user}")
view = st.session_state.role if st.session_state.role == "Tech" else st.sidebar.radio("View", ["Admin", "Tech Portal"])

# 8. ADMIN VIEW
if view == "Admin":
    st.title("🛠️ Admin Control")
    tabs = st.tabs(["Dispatch", "Staff", "Clients", "Work History"])
    
    with tabs[0]:
        with st.form("dispatch"):
            t, c, u = st.selectbox("Worker", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit")
            if st.form_submit_button("Assign"):
                td = pd.concat([td, pd.DataFrame([{"Tech":t,"Client":c,"Unit":u,"Status":"Pending"}])], ignore_index=True)
                td.to_csv(T_PATH, index=False); push_to_github(T_PATH); st.rerun()
        st.dataframe(td)

    with tabs[1]:
        with st.form("staff"):
            sn, sp, sr = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", 25.0)
            if st.form_submit_button("Add Staff"):
                ud = pd.concat([ud, pd.DataFrame([{"User":sn,"PIN":sp,"Rate":sr}])], ignore_index=True)
                ud.to_csv(U_PATH, index=False); push_to_github(U_PATH); st.rerun()
        st.dataframe(ud)

    with tabs[2]:
        with st.form("client"):
            cn, ca = st.text_input("Client"), st.text_input("Address")
            if st.form_submit_button("Add Client"):
                cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])], ignore_index=True)
                cd.to_csv(C_PATH, index=False); push_to_github(C_PATH); st.rerun()
        st.dataframe(cd)

    with tabs[3]:
        st.dataframe(ld)

# 9. TECH VIEW
else:
    st.title("📱 Field Portal")
    if 'job' not in st.session_state:
        st.subheader("Assigned Work")
        tasks = td[(td['Tech']==st.session_state.user) & (td['Status']=='Pending')]
        for i, r in tasks.iterrows():
            if st.button(f"Clock In: {r['Client']} - {r['Unit']}", key=f"t{i}"):
                st.session_state.job = {"c": r['Client'], "u": r['Unit'], "type": "D"}
                st.session_state.start = datetime.now(); st.rerun()
        
        st.divider()
        st.subheader("Manual Clock In")
        m_c = st.selectbox("Client", cd['Client'])
        m_u = st.text_input("Unit")
        if st.button("Start Unassigned Job"):
            st.session_state.job = {"c": m_c, "u": m_u, "type": "M"}
            st.session_state.start = datetime.now(); st.rerun()
    else:
        st.success(f"ACTIVE: {st.session_state.job['c']}")
        notes = st.text_area("Job Notes")
        if st.button("🏁 FINISH JOB"):
            end = datetime.now()
            log = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": end.strftime('%H:%M'), "Date": end.strftime('%Y-%m-%d'), "Notes": notes}])
            ld = pd.concat([ld, log], ignore_index=True); ld.to_csv(L_PATH, index=False); push_to_github(L_PATH)
            if st.session_state.job['type'] == "D":
                td.loc[(td['Tech']==st.session_state.user)&(td['Client']==st.session_state.job['c']), 'Status'] = 'Done'
                td.to_csv(T_PATH, index=False); push_to_github(T_PATH)
            del st.session_state.job; st.rerun()

if st.sidebar.button("Log Out"):
    st.session_state.auth = False
    st.rerun()
