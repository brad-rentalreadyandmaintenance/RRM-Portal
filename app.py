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
        payload = {"message": "Update", "content": content, "branch": "master"}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except: pass

# 4. ROBUST INITIALIZATION
def load_and_fix(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    df = pd.read_csv(path)
    # If columns are missing, reset the file
    if not all(col in df.columns for col in columns):
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)
    return df

ud = load_and_fix(U_PATH, ["User", "PIN", "Rate"])
cd = load_and_fix(C_PATH, ["Client", "Address"])
ld = load_and_fix(L_PATH, ["User", "Client", "In", "Out", "Date", "Notes"])
td = load_and_fix(T_PATH, ["Tech", "Client", "Unit", "Status"])

# 5. LOGIN LOGIC
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal")
    user_type = st.radio("Access Level", ["Admin", "Technician"])
    
    if user_type == "Admin":
        admin_pin = st.text_input("Admin PIN", type="password")
        if st.button("Login"):
            if admin_pin == "0000":
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "Admin", "Admin"
                st.rerun()
            else: st.error("Wrong PIN")
    else:
        if ud.empty:
            st.warning("No staff found. Admin must add staff first.")
            st.stop()
        tech_name = st.selectbox("Your Name", ud['User'].tolist())
        pin = st.text_input("Your PIN", type="password")
        if st.button("Login"):
            match = ud[ud['User'] == tech_name]
            if not match.empty and str(pin) == str(match.iloc[0]['PIN']):
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "Tech", tech_name
                st.rerun()
            else: st.error("Invalid PIN")
    st.stop()

# 6. SIDEBAR
st.sidebar.subheader(f"Logged in: {st.session_state.user}")
mode = "Technician View"
if st.session_state.role == "Admin":
    mode = st.sidebar.radio("View Mode", ["Admin Dashboard", "Technician View"])

if st.sidebar.button("Log Out"):
    st.session_state.auth = False
    st.rerun()

# 7. ADMIN DASHBOARD
if mode == "Admin Dashboard":
    st.title("🛠️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["Dispatch Work", "Manage Staff", "Manage Clients"])
    
    with t1:
        st.subheader("Assign Job")
        with st.form("dispatch_form"):
            t_user = st.selectbox("Select Tech", ud['User'].tolist())
            t_client = st.selectbox("Select Client", cd['Client'].tolist())
            t_unit = st.text_input("Unit #")
            if st.form_submit_button("Assign"):
                new_task = pd.DataFrame([{"Tech": t_user, "Client": t_client, "Unit": t_unit, "Status": "Pending"}])
                td = pd.concat([td, new_task], ignore_index=True)
                td.to_csv(T_PATH, index=False); sync(T_PATH)
                st.success("Task Assigned!"); st.rerun()
        st.write("### Live Job Status")
        st.dataframe(td, use_container_width=True)

    with t2:
        st.subheader("Add Staff")
        with st.form("add_staff"):
            sn, sp, sr = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", value=25.0)
            if st.form_submit_button("Save"):
                ud = pd.concat([ud, pd.DataFrame([{"User": sn, "PIN": sp, "Rate": sr}])], ignore_index=True)
                ud.to_csv(U_PATH, index=False); sync(U_PATH); st.rerun()
        st.dataframe(ud)

    with t3:
        st.subheader("Add Clients")
        with st.form("add_client"):
            cn, ca = st.text_input("Name"), st.text_input("Address")
            if st.form_submit_button("Save"):
                cd = pd.concat([cd, pd.DataFrame([{"Client": cn, "Address": ca}])], ignore_index=True)
                cd.to_csv(C_PATH, index=False); sync(C_PATH); st.rerun()
        st.dataframe(cd)

# 8. TECH VIEW
else:
    st.title("📱 Technician Portal")
    my_tasks = td[(td['Tech'] == st.session_state.user) & (td['Status'] == 'Pending')]
    
    if 'active_job' not in st.session_state:
        if my_tasks.empty:
            st.info("No active jobs assigned to you.")
        else:
            for i, r in my_tasks.iterrows():
                with st.container(border=True):
                    st.markdown(f"### {r['Client']} - Unit {r['Unit']}")
                    if st.button("▶️ CLOCK IN", key=f"start_{i}"):
                        st.session_state.active_job = r.to_dict()
                        st.session_state.start_time = datetime.now()
                        st.rerun()
    else:
        st.warning(f"ACTING ON: {st.session_state.active_job['Client']} (Unit {st.session_state.active_job['Unit']})")
        notes = st.text_area("Work performed / Notes")
        if st.button("🏁 CLOCK OUT"):
            # Save Log
            end_val = datetime.now()
            new_log = pd.DataFrame([{
                "User": st.session_state.user, "Client": st.session_state.active_job['Client'],
                "In": st.session_state.start_time.strftime('%H:%M'), "Out": end_val.strftime('%H:%M'),
                "Date": datetime.now().strftime('%Y-%m-%d'), "Notes": notes
            }])
            ld = pd.concat([ld, new_log], ignore_index=True)
            ld.to_csv(L_PATH, index=False); sync(L_PATH)
            
            # Update Task Status
            td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.active_job['Client']), 'Status'] = 'Done'
            td.to_csv(T_PATH, index=False); sync(T_PATH)
            
            del st.session_state.active_job
            st.success("Shift Logged!"); st.rerun()
