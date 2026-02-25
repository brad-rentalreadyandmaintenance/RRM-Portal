import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime, timedelta

# 1. PAGE SETUP
st.set_page_config(page_title="RRM Master Portal", layout="wide")

# Makes buttons larger and easier to tap on mobile
st.markdown("<style>button {height: 3em !important; font-size: 1.1rem !important;}</style>", unsafe_allow_html=True)

# 2. CONFIG & GITHUB SETTINGS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

U_PATH, C_PATH, L_PATH, T_PATH = "data/users.csv", "data/clients.csv", "data/logs.csv", "data/tasks.csv"

# --- TIMEZONE FIX ---
# MST is UTC - 7 hours. Change the -7 to -6 if you move to MDT (Daylight Savings)
def get_mst_time():
    return datetime.utcnow() - timedelta(hours=7)

# 3. GITHUB SYNC FUNCTIONS
def pull_from_github(path):
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

# 4. STARTUP BOOT
if 'booted' not in st.session_state:
    for p in [U_PATH, C_PATH, L_PATH, T_PATH]:
        pull_from_github(p)
    st.session_state.booted = True

# 5. DATA LOADING HELPERS
def load_data(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    try:
        df = pd.read_csv(path, dtype={'PIN': str, 'Unit': str})
    except:
        df = pd.read_csv(path)
    if not all(col in df.columns for col in columns):
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)
    return df

ud = load_data(U_PATH, ["User", "PIN", "Rate"])
cd = load_data(C_PATH, ["Client", "Address"])
ld = load_data(L_PATH, ["User", "Client", "In", "Out", "Date", "Notes", "Duration"])
td = load_data(T_PATH, ["Tech", "Client", "Unit", "Status"])

# 6. AUTHENTICATION
if 'auth' not in st.session_state: 
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    u_type = st.radio("Select Login Type", ["Admin", "Technician"])
    
    if u_type == "Admin":
        admin_pin = st.text_input("Admin PIN", type="password")
        if st.button("Access Admin Portal"):
            if admin_pin == "0000":
                st.session_state.update({"auth": True, "role": "Admin", "user": "Admin"})
                st.rerun()
            else:
                st.error("Invalid Admin PIN")
    else:
        if ud.empty: 
            st.warning("No staff found. Admin must log in.")
            st.stop()
        t_name = st.selectbox("Select Your Name", ud['User'].tolist())
        t_pin_input = st.text_input("Enter Your PIN", type="password")
        if st.button("Technician Login"):
            actual_pin = str(ud[ud['User'] == t_name].iloc[0]['PIN']).zfill(4)
            if t_pin_input.strip().zfill(4) == actual_pin:
                st.session_state.update({"auth": True, "role": "Tech", "user": t_name})
                st.rerun()
            else:
                st.error("Incorrect PIN")
    st.stop()

# 7. SIDEBAR NAVIGATION
st.sidebar.title(f"User: {st.session_state.user}")
view = st.session_state.role if st.session_state.role == "Tech" else st.sidebar.radio("Navigation", ["Admin Dashboard", "Field Portal"])

if st.sidebar.button("Log Out"):
    st.session_state.auth = False
    st.rerun()

# 8. ADMIN DASHBOARD
if view == "Admin Dashboard":
    st.title("🛠️ Admin Dashboard")
    tabs = st.tabs(["Dispatch Work", "Manage Staff", "Manage Clients", "Work History"])
    
    with tabs[0]:
        st.subheader("Assign Job to Tech")
        with st.form("dispatch_form"):
            t = st.selectbox("Worker", ud['User']) if not ud.empty else "None"
            c = st.selectbox("Client", cd['Client']) if not cd.empty else "None"
            u = st.text_input("Unit #")
            if st.form_submit_button("Send Job"):
                if t != "None" and c != "None":
                    new_t = pd.DataFrame([{"Tech":t,"Client":c,"Unit":str(u),"Status":"Pending"}])
                    td = pd.concat([td, new_t], ignore_index=True)
                    td.to_csv(T_PATH, index=False); push_to_github(T_PATH); st.success("Dispatched!"); st.rerun()
        st.dataframe(td, use_container_width=True)

    with tabs[1]:
        st.subheader("Add New Staff")
        with st.form("staff_form"):
            sn, sp, sr = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", 25.0)
            if st.form_submit_button("Save Staff"):
                ud = pd.concat([ud, pd.DataFrame([{"User":sn,"PIN":str(sp).zfill(4),"Rate":sr}])], ignore_index=True)
                ud.to_csv(U_PATH, index=False); push_to_github(U_PATH); st.success("Saved!"); st.rerun()
        st.dataframe(ud, use_container_width=True)

    with tabs[2]:
        st.subheader("Add New Client")
        with st.form("client_form"):
            cn, ca = st.text_input("Company Name"), st.text_input("Address")
            if st.form_submit_button("Save Client"):
                cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])], ignore_index=True)
                cd.to_csv(C_PATH, index=False); push_to_github(C_PATH); st.rerun()
        st.dataframe(cd, use_container_width=True)

    with tabs[3]:
        st.subheader("Master Logs (Times in MST)")
        st.dataframe(ld, use_container_width=True)

# 9. TECHNICIAN PORTAL
else:
    st.title("📱 Technician Field Portal")
    
    if 'job' not in st.session_state:
        st.subheader("📌 Your Active/Assigned Tasks")
        tasks = td[(td['Tech'] == st.session_state.user) & (td['Status'] == 'Pending')]
        if not tasks.empty:
            for i, r in tasks.iterrows():
                with st.container(border=True):
                    st.write(f"**{r['Client']}** - Unit: {r['Unit']}")
                    if st.button(f"Clock In: {r['Client']}", key=f"d_btn_{i}"):
                        st.session_state.job = {"c": r['Client'], "u": str(r['Unit']), "type": "D"}
                        st.session_state.start = get_mst_time(); st.rerun()
        else:
            st.info("No assigned jobs currently.")
        
        st.divider()
        st.subheader("⚡ Start New (Unassigned) Job")
        is_new_client = st.checkbox("➕ Add New/Unlisted Client")
        if is_new_client:
            m_client = st.text_input("Type Client Name")
        else:
            m_client = st.selectbox("Select Client", ["-- Select --"] + cd['Client'].tolist())
        m_unit = st.text_input("Unit # (Optional)")
        
        if st.button("Start Work Now"):
            if m_client == "-- Select --" or m_client == "":
                st.error("Select/type a client.")
            else:
                st.session_state.job = {"c": m_client, "u": str(m_unit), "type": "M"}
                st.session_state.start = get_mst_time(); st.rerun()

    else:
        st.success(f"ACTIVE JOB: {st.session_state.job['c']}")
        st.write(f"Started at: {st.session_state.start.strftime('%I:%M %p')}")
        notes = st.text_area("Work Notes")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⌛ PAUSE (CLOCK OUT ONLY)", use_container_width=True):
                end_t = get_mst_time()
                dur = str(end_t - st.session_state.start).split(".")[0]
                new_log = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": end_t.strftime('%H:%M'), "Date": end_t.strftime('%Y-%m-%d'), "Notes": f"[PARTIAL] {notes}", "Duration": dur}])
                ld = pd.concat([ld, new_log], ignore_index=True); ld.to_csv(L_PATH, index=False); push_to_github(L_PATH)
                if st.session_state.job['type'] == "M":
                    new_task = pd.DataFrame([{"Tech": st.session_state.user, "Client": st.session_state.job['c'], "Unit": st.session_state.job['u'], "Status": "Pending"}])
                    td = pd.concat([td, new_task], ignore_index=True); td.to_csv(T_PATH, index=False); push_to_github(T_PATH)
                del st.session_state.job; st.success("Progress Saved"); st.rerun()

        with col2:
            if st.button("🏁 FINALIZE & CLOSE JOB", type="primary", use_container_width=True):
                end_t = get_mst_time()
                dur = str(end_t - st.session_state.start).split(".")[0]
                new_log = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": end_t.strftime('%H:%M'), "Date": end_t.strftime('%Y-%m-%d'), "Notes": notes, "Duration": dur}])
                ld = pd.concat([ld, new_log], ignore_index=True); ld.to_csv(L_PATH, index=False); push_to_github(L_PATH)
                td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.job['c']) & (td['Unit'] == st.session_state.job['u']), 'Status'] = 'Done'
                td.to_csv(T_PATH, index=False); push_to_github(T_PATH)
                del st.session_state.job; st.success("Job Completed"); st.rerun()
