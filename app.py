import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime

# 1. SETUP
st.set_page_config(page_title="RRM Master Portal", layout="wide")

# 2. CONFIG
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# File Paths
U_PATH, C_PATH, L_PATH, T_PATH = "data/users.csv", "data/clients.csv", "data/logs.csv", "data/tasks.csv"

# 3. GITHUB SYNC
def sync(path):
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        res = requests.get(url, headers=headers)
        sha = res.json().get('sha') if res.status_code == 200 else None
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        payload = {"message": "Update", "content": content, "branch": "master", "sha": sha} if sha else {"message": "Init", "content": content, "branch": "master"}
        requests.put(url, headers=headers, json=payload)
    except: pass

# 4. INIT FILES
for p, cols in {U_PATH: ["User", "PIN", "Rate"], C_PATH: ["Client", "Address"], 
                L_PATH: ["User", "Client", "In", "Out", "Date", "Notes"],
                T_PATH: ["Tech", "Client", "Unit", "Status"]}.items():
    if not os.path.exists(p): pd.DataFrame(columns=cols).to_csv(p, index=False)

# Load Data
ud, cd, ld, td = pd.read_csv(U_PATH), pd.read_csv(C_PATH), pd.read_csv(L_PATH), pd.read_csv(T_PATH)

# 5. LOGIN
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal")
    user_type = st.radio("I am a...", ["Admin", "Technician"])
    
    if user_type == "Admin":
        if st.text_input("Admin PIN", type="password") == "0000":
            if st.button("Login"):
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "Admin", "Admin"
                st.rerun()
    else:
        tech_name = st.selectbox("Select Name", ud['User'].tolist() if not ud.empty else ["No Staff"])
        pin = st.text_input("Enter PIN", type="password")
        if st.button("Login"):
            match = ud[ud['User'] == tech_name]
            if not match.empty and str(pin) == str(match.iloc[0]['PIN']):
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "Tech", tech_name
                st.rerun()
    st.stop()

# 6. SIDEBAR
st.sidebar.title(f"Hi, {st.session_state.user}")
if st.session_state.role == "Admin":
    mode = st.sidebar.radio("View Mode", ["Admin Dashboard", "Technician View"])
else:
    mode = "Technician View"

if st.sidebar.button("Logout"):
    st.session_state.auth = False
    st.rerun()

# 7. ADMIN DASHBOARD
if mode == "Admin Dashboard":
    st.title("🛠️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["Dispatch", "Staff", "Clients"])
    
    with t1:
        st.subheader("🚀 Dispatch Work")
        with st.form("dispatch"):
            tech = st.selectbox("Assign Tech", ud['User'].tolist())
            cl = st.selectbox("Client", cd['Client'].tolist())
            un = st.text_input("Unit #")
            if st.form_submit_button("Send"):
                new_t = pd.DataFrame([{"Tech": tech, "Client": cl, "Unit": un, "Status": "Pending"}])
                td = pd.concat([td, new_t], ignore_index=True)
                td.to_csv(T_PATH, index=False); sync(T_PATH); st.success("Sent"); st.rerun()

    with t2:
        st.subheader("👤 Staff Management")
        with st.form("staff"):
            n, p, r = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", value=25.0)
            if st.form_submit_button("Add"):
                new_u = pd.DataFrame([{"User": n, "PIN": p, "Rate": r}])
                ud = pd.concat([ud, new_u], ignore_index=True)
                ud.to_csv(U_PATH, index=False); sync(U_PATH); st.rerun()
        st.dataframe(ud)

    with t3:
        st.subheader("🏢 Client List")
        with st.form("client"):
            cn, ca = st.text_input("Client Name"), st.text_input("Address")
            if st.form_submit_button("Save"):
                new_c = pd.DataFrame([{"Client": cn, "Address": ca}])
                cd = pd.concat([cd, new_c], ignore_index=True)
                cd.to_csv(C_PATH, index=False); sync(C_PATH); st.rerun()
        st.dataframe(cd)

# 8. TECHNICIAN VIEW
else:
    st.title("📱 Technician Portal")
    my_tasks = td[(td['Tech'] == st.session_state.user) & (td['Status'] == 'Pending')]
    
    if 'active_job' not in st.session_state:
        st.subheader("Your Assigned Tasks")
        if my_tasks.empty:
            st.info("No pending jobs.")
        for i, r in my_tasks.iterrows():
            with st.container(border=True):
                st.write(f"**{r['Client']}** - Unit {r['Unit']}")
                if st.button(f"Clock In: {r['Client']}", key=f"btn_{i}"):
                    st.session_state.active_job = r.to_dict()
                    st.session_state.start_time = datetime.now()
                    st.rerun()
    else:
        st.success(f"WORKING AT: {st.session_state.active_job['Client']}")
        st.write(f"Start Time: {st.session_state.start_time.strftime('%H:%M')}")
        notes = st.text_area("Job Notes")
        if st.button("🚩 CLOCK OUT"):
            end_t = datetime.now()
            # Save Log
            new_log = pd.DataFrame([{
                "User": st.session_state.user, "Client": st.session_state.active_job['Client'],
                "In": st.session_state.start_time.strftime('%H:%M'), "Out": end_t.strftime('%H:%M'),
                "Date": datetime.now().strftime('%Y-%m-%d'), "Notes": notes
            }])
            ld = pd.concat([ld, new_log], ignore_index=True)
            ld.to_csv(L_PATH, index=False); sync(L_PATH)
            
            # Update Task
            td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.active_job['Client']), 'Status'] = 'Done'
            td.to_csv(T_PATH, index=False); sync(T_PATH)
            
            del st.session_state.active_job
            st.success("Log Saved!"); st.rerun()
