import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime
import time
from PIL import Image

# 1. PAGE CONFIG (Must be first)
st.set_page_config(page_title="RRM Master Portal", layout="wide")

# 2. SECRETS & PATHS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
REPO_NAME = st.secrets.get("REPO_NAME", "")

# Define folders and files
B = "data/"
U, C, L, T = B+"users.csv", B+"clients.csv", B+"time_log.csv", B+"tasks.csv"
P = B+"site_photos/"

# 3. SYNC LOGIC (Saves to GitHub)
def sync_to_github(file_path, msg="Update"):
    if not GITHUB_TOKEN or not REPO_NAME: return
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # Get existing file SHA to update it
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None
    
    if not os.path.exists(file_path): return
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
        
    payload = {"message": msg, "content": content, "branch": "main"}
    if sha: payload["sha"] = sha
    
    requests.put(url, headers=headers, json=payload)

# 4. INITIALIZE FILES
def init():
    if not os.path.exists(B): os.makedirs(B)
    if not os.path.exists(P): os.makedirs(P)
    headers = {
        U: ["User", "PIN", "Rate"],
        C: ["Client", "Address"],
        L: ["User", "Site", "Unit", "Date", "Time In", "Time Out", "Status", "Duration", "Notes"],
        T: ["AssignedTo", "Site", "Unit", "Status"]
    }
    for f, cols in headers.items():
        if not os.path.exists(f) or os.path.getsize(f) == 0:
            pd.DataFrame(columns=cols).to_csv(f, index=False)
            sync_to_github(f, "Initialize CSV")

init()

# 5. DATA LOADING
def load(f):
    try: return pd.read_csv(f)
    except: return pd.DataFrame()

ud, cd, ld, td = load(U), load(C), load(L), load(T)

# 6. LOGIN SCREEN
if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    user_list = ["Admin"] + (ud['User'].tolist() if not ud.empty else [])
    selected_user = st.selectbox("Who are you?", user_list)
    pin_input = st.text_input("Enter 4-Digit PIN", type="password")
    
    if st.button("LOG IN", use_container_width=True):
        if selected_user == "Admin" and pin_input == "0000":
            st.session_state.auth, st.session_state.user = True, "Admin"
            st.rerun()
        else:
            match = ud[ud['User'] == selected_user]
            if not match.empty and str(pin_input) == str(match.iloc[0]['PIN']):
                st.session_state.auth, st.session_state.user = True, selected_user
                st.rerun()
            else:
                st.error("Invalid PIN")
    st.stop()

# 7. MAIN NAVIGATION
is_admin = (st.session_state.user == "Admin")
mode = st.sidebar.radio("Navigation", ["Admin", "Technician"]) if is_admin else "Technician"

if st.sidebar.button("Log Out"):
    st.session_state.auth = False
    st.rerun()

# ==========================================
# ADMIN MODE
# ==========================================
if is_admin and mode == "Admin":
    st.title("🛠️ Admin Control Panel")
    t1, t2, t3, t4 = st.tabs(["Dispatch", "Clients", "Payroll", "Staff Management"])

    with t4: # STAFF
        st.header("👤 Staff Management")
        with st.form("add_staff", clear_on_submit=True):
            n, p, r = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", value=25.0)
            if st.form_submit_button("ADD NEW WORKER"):
                if n and p:
                    new_u = pd.DataFrame([{"User":n, "PIN":p, "Rate":r}])
                    ud = pd.concat([ud, new_u], ignore_index=True)
                    ud.to_csv(U, index=False); sync_to_github(U, f"Added {n}"); st.success(f"Added {n}"); st.rerun()
        st.divider()
        st.write("Current Staff Members:")
        st.dataframe(ud, use_container_width=True)

    with t2: # CLIENTS
        st.header("🏢 Client List")
        with st.form("add_client"):
            cn, ca = st.text_input("Company Name"), st.text_input("Address")
            if st.form_submit_button("SAVE CLIENT"):
                if cn:
                    new_c = pd.DataFrame([{"Client":cn, "Address":ca}])
                    cd = pd.concat([cd, new_c], ignore_index=True)
                    cd.to_csv(C, index=False); sync_to_github(C, "Added Client"); st.success("Saved"); st.rerun()
        st.dataframe(cd, use_container_width=True)

    with t1: # DISPATCH
        st.header("🚀 Dispatch New Job")
        with st.form("dispatch_form"):
            target_t = st.selectbox("Assign Tech", ud['User'].tolist() if not ud.empty else ["No Staff"])
            target_c = st.selectbox("Client", cd['Client'].tolist() if not cd.empty else ["No Clients"])
            unit = st.text_input("Unit # / Details")
            if st.form_submit_button("SEND DISPATCH"):
                new_t = pd.DataFrame([{"AssignedTo":target_t, "Site":target_c, "Unit":unit, "Status":"Pending"}])
                td = pd.concat([td, new_t], ignore_index=True)
                td.to_csv(T, index=False); sync_to_github(T, "Dispatching"); st.success("Sent!"); st.rerun()

    with t3: # PAYROLL
        st.header("💰 Payroll Audit")
        st.dataframe(ld, use_container_width=True)

# ==========================================
# TECHNICIAN MODE
# ==========================================
else:
    st.title(f"Technician: {st.session_state.user}")
    
    if 'active_job' not in st.session_state:
        st.subheader("Assigned Jobs")
        my_jobs = td[(td['AssignedTo'] == st.session_state.user) & (td['Status'] == 'Pending')]
        if my_jobs.empty:
            st.info("No active assignments.")
        else:
            for i, r in my_jobs.iterrows():
                with st.container(border=True):
                    st.write(f"**{r['Site']}** - {r['Unit']}")
                    if st.button(f"Clock In: {r['Site']}", key=f"in_{i}"):
                        st.session_state.active_job = r.to_dict()
                        st.session_state.start_time = datetime.now()
                        st.rerun()
    else:
        st.success(f"WORKING AT: {st.session_state.active_job['Site']}")
        st.write(f"Started at: {st.session_state.start_time.strftime('%H:%M')}")
        notes = st.text_area("Work Notes")
        if st.button("🚩 CLOCK OUT & FINALIZE", type="primary"):
            end_t = datetime.now()
            dur = (end_t - st.session_state.start_time).total_seconds() / 3600 # hours
            
            new_log = pd.DataFrame([{
                "User": st.session_state.user,
                "Site": st.session_state.active_job['Site'],
                "Unit": st.session_state.active_job['Unit'],
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Time In": st.session_state.start_time.strftime("%H:%M"),
                "Time Out": end_t.strftime("%H:%M"),
                "Status": "Completed",
                "Duration": round(dur, 2),
                "Notes": notes
            }])
            
            # Save Log
            ld = pd.concat([ld, new_log], ignore_index=True)
            ld.to_csv(L, index=False); sync_to_github(L, "Clock Out")
            
            # Update Task Status
            td.loc[(td['Site']==st.session_state.active_job['Site']) & (td['AssignedTo']==st.session_state.user), 'Status'] = 'Completed'
            td.to_csv(T, index=False); sync_to_github(T, "Job Finished")
            
            del st.session_state.active_job
            st.success("Job Finalized!")
            time.sleep(1); st.rerun()
