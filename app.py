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

# 4. DATA LOADING
def load_and_fix(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    df = pd.read_csv(path)
    if not all(col in df.columns for col in columns):
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)
    return df

ud = load_and_fix(U_PATH, ["User", "PIN", "Rate"])
cd = load_and_fix(C_PATH, ["Client", "Address"])
ld = load_and_fix(L_PATH, ["User", "Client", "In", "Out", "Date", "Notes"])
td = load_and_fix(T_PATH, ["Tech", "Client", "Unit", "Status"])

# 5. LOGIN
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal")
    user_type = st.radio("Access Level", ["Admin", "Technician"])
    if user_type == "Admin":
        if st.text_input("Admin PIN", type="password") == "0000":
            if st.button("Login"):
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "Admin", "Admin"
                st.rerun()
    else:
        if ud.empty: st.warning("No staff found."); st.stop()
        tech_name = st.selectbox("Your Name", ud['User'].tolist())
        if st.text_input("Your PIN", type="password") == str(ud[ud['User']==tech_name].iloc[0]['PIN']):
            if st.button("Login"):
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "Tech", tech_name
                st.rerun()
    st.stop()

# 6. SIDEBAR
st.sidebar.subheader(f"User: {st.session_state.user}")
mode = "Technician View" if st.session_state.role == "Tech" else st.sidebar.radio("View", ["Admin Dashboard", "Technician View"])
if st.sidebar.button("Log Out"):
    st.session_state.auth = False
    st.rerun()

# 7. ADMIN DASHBOARD
if mode == "Admin Dashboard":
    st.title("🛠️ Admin Dashboard")
    t1, t2, t3, t4 = st.tabs(["Dispatch", "Staff", "Clients", "Work Logs"])
    
    with t1:
        with st.form("dispatch"):
            tech, cl, unit = st.selectbox("Tech", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit #")
            if st.form_submit_button("Assign"):
                new_t = pd.DataFrame([{"Tech": tech, "Client": cl, "Unit": unit, "Status": "Pending"}])
                td = pd.concat([td, new_t], ignore_index=True); td.to_csv(T_PATH, index=False); sync(T_PATH); st.rerun()
        st.dataframe(td)
    
    with t2:
        with st.form("staff"):
            sn, sp, sr = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", value=25.0)
            if st.form_submit_button("Add"):
                ud = pd.concat([ud, pd.DataFrame([{"User": sn, "PIN": sp, "Rate": sr}])], ignore_index=True)
                ud.to_csv(U_PATH, index=False); sync(U_PATH); st.rerun()
        st.dataframe(ud)

    with t3:
        with st.form("client"):
            cn, ca = st.text_input("Client"), st.text_input("Address")
            if st.form_submit_button("Save"):
                cd = pd.concat([cd, pd.DataFrame([{"Client": cn, "Address": ca}])], ignore_index=True)
                cd.to_csv(C_PATH, index=False); sync(C_PATH); st.rerun()
        st.dataframe(cd)

    with t4:
        st.subheader("Completed Work History")
        st.dataframe(ld, use_container_width=True)

# 8. TECH VIEW
else:
    st.title("📱 Technician Portal")
    
    if 'active_job' not in st.session_state:
        # A. DISPATCHED JOBS
        st.subheader("📌 Assigned to You")
        my_tasks = td[(td['Tech'] == st.session_state.user) & (td['Status'] == 'Pending')]
        if not my_tasks.empty:
            for i, r in my_tasks.iterrows():
                with st.container(border=True):
                    st.write(f"**{r['Client']}** - Unit {r['Unit']}")
                    if st.button(f"Clock In: {r['Client']} (Unit {r['Unit']})", key=f"d_{i}"):
                        st.session_state.active_job = {"Client": r['Client'], "Unit": r['Unit'], "Type": "Dispatched"}
                        st.session_state.start_time = datetime.now(); st.rerun()
        else:
            st.info("No assigned jobs.")

        st.divider()

        # B. MANUAL CLOCK IN (New Feature)
        st.subheader("⚡ Start Unassigned Job")
        with st.form("manual_clock_in"):
            m_client = st.selectbox("Select Client", cd['Client'].tolist())
            m_unit = st.text_input("Unit # (Optional)")
            if st.form_submit_button("Start Work Now"):
                st.session_state.active_job = {"Client": m_client, "Unit": m_unit, "Type": "Manual"}
                st.session_state.start_time = datetime.now(); st.rerun()

    else:
        # C. ACTIVE CLOCK
        st.success(f"WORKING: {st.session_state.active_job['Client']} (Unit {st.session_state.active_job['Unit']})")
        st.write(f"Start Time: {st.session_state.start_time.strftime('%I:%M %p')}")
        notes = st.text_area("Work Details / Parts Used")
        
        if st.button("🏁 FINALIZE & CLOCK OUT", type="primary"):
            end_val = datetime.now()
            # Save to Logs
            new_log = pd.DataFrame([{
                "User": st.session_state.user, "Client": st.session_state.active_job['Client'],
                "In": st.session_state.start_time.strftime('%H:%M'), "Out": end_val.strftime('%H:%M'),
                "Date": datetime.now().strftime('%Y-%m-%d'), "Notes": notes
            }])
            ld = pd.concat([ld, new_log], ignore_index=True); ld.to_csv(L_PATH, index=False); sync(L_PATH)
            
            # If it was a dispatched job, mark it done
            if st.session_state.active_job['Type'] == "Dispatched":
                td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.active_job['Client']) & (td['Unit'] == st.session_state.active_job['Unit']), 'Status'] = 'Done'
                td.to_csv(T_PATH, index=False); sync(T_PATH)
            
            del st.session_state.active_job
            st.success("Work Saved!"); st.rerun()
