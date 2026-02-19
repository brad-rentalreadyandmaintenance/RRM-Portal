import streamlit as st
# MUST BE FIRST
st.set_page_config(page_title="RRM Master Portal", layout="wide")

import pandas as pd
from datetime import datetime
import time
import os
import requests
import base64
from PIL import Image
from streamlit_autorefresh import st_autorefresh
from streamlit_cookies_manager import EncryptedCookieManager

# ==============================================================================
# 1. CLOUD PERSISTENCE LOGIC
# ==============================================================================
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
REPO_NAME = st.secrets.get("REPO_NAME", "")
BRANCH = "main"

def sync_to_github(file_path, msg="Data update"):
    """Pushes local CSV changes back to the private GitHub Repo."""
    if not GITHUB_TOKEN or not REPO_NAME:
        return 
        
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None

    if not os.path.exists(file_path):
        return

    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    payload = {"message": msg, "content": content, "branch": BRANCH}
    if sha: payload["sha"] = sha

    requests.put(url, headers=headers, json=payload)

# ==============================================================================
# 2. PATHS AND INITIALIZATION
# ==============================================================================
B = "data/" 
TP, P, S, W = B+"tech_pics/", B+"site_photos/", B+"signatures/", B+"work_orders/"
T, L, M, C, U = B+"tasks.csv", B+"time_log.csv", B+"material_logs.csv", B+"clients.csv", B+"users.csv"

cookie_pwd = st.secrets.get("COOKIE_PASSWORD", "RRM_PROD_ENCRYPT_2024")
cookies = EncryptedCookieManager(password=cookie_pwd)
if not cookies.ready(): st.stop()

def init():
    for d in [B, TP, P, S, W]:
        if not os.path.exists(d): os.makedirs(d)
    headers = {
        U: ["User", "PIN", "Rate", "Pic_File"],
        C: ["Client", "Address", "Cust_Rate"],
        L: ["User", "Site", "Unit", "Date", "Time In", "Time Out", "Status", "Seconds", "Total Time", "Notes", "Photo_In", "Photo_Out"],
        T: ["AssignedTo", "Site", "Unit", "Status", "WO_File", "Timestamp"],
        M: ["Date", "User", "Site", "Material", "Cost"]
    }
    for p, cols in headers.items():
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            pd.DataFrame(columns=cols).to_csv(p, index=False)
            sync_to_github(p, "Initialize file")

init()
st_autorefresh(interval=60000, key="global_hb")

# ==============================================================================
# 3. UTILITIES
# ==============================================================================
def load(f):
    if not os.path.exists(f): 
        # Create empty with correct headers if missing
        init()
    try:
        df = pd.read_csv(f)
        if df.empty: return df
        return df
    except:
        return pd.DataFrame()

def fmt_dur(s):
    if pd.isna(s) or s < 0: return "0h 0m"
    return f"{int(s//3600)}h {int((s%3600)//60)}m"

def save_img_cloud(img_file, prefix, user, folder=P):
    if img_file:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{prefix}_{user}_{ts}.jpg"
        full_path = os.path.join(folder, fname)
        Image.open(img_file).convert('RGB').save(full_path)
        sync_to_github(full_path, f"Upload image {fname}")
        return fname
    return ""

# ==============================================================================
# 4. AUTHENTICATION
# ==============================================================================
if 'authenticated' not in st.session_state and cookies.get("auth_status") == "True":
    st.session_state.authenticated, st.session_state.user = True, cookies.get("auth_user")

if 'authenticated' not in st.session_state:
    udb = load(U)
    st.title("🔐 RRM Cloud Access")
    user_list = udb['User'].tolist() if not udb.empty else []
    su = st.selectbox("Select User", ["Admin"] + user_list)
    pi = st.text_input("PIN", type="password")
    if st.button("LOG IN", use_container_width=True):
        if su == "Admin" and pi == "0000":
            st.session_state.authenticated, st.session_state.user = True, "Admin"
            cookies["auth_status"], cookies["auth_user"] = "True", "Admin"
            cookies.save(); st.rerun()
        else:
            match = udb[udb['User'] == su]
            if not match.empty and pi == str(match.iloc[0]['PIN']).zfill(4):
                st.session_state.authenticated, st.session_state.user = True, su
                cookies["auth_status"], cookies["auth_user"] = "True", su
                cookies.save(); st.rerun()
            else: st.error("Invalid PIN")
    st.stop()

# ==============================================================================
# 5. DATA LOADING
# ==============================================================================
ld, td, cd, ud = load(L), load(T), load(C), load(U)
is_adm = (st.session_state.user == "Admin")
mode = st.sidebar.radio("Navigation", ["Admin", "Technician"]) if is_adm else "Technician"

# ==============================================================================
# 6. ADMIN VIEW
# ==============================================================================
if is_adm and mode == "Admin":
    t1, t2, t3, t4 = st.tabs(["Dispatch", "Clients", "Payroll Audit", "Staff"])
    
    with t1: # Dispatch
        st.subheader("🚀 Dispatch Job")
        c1, c2 = st.columns(2)
        with c1:
            tech_opts = ud['User'].tolist() if not ud.empty else ["No Staff Found"]
            target_t = st.selectbox("Assign Tech", tech_opts)
            client_opts = ["Manual Entry"] + (cd['Client'].tolist() if not cd.empty else [])
            c_sel = st.selectbox("Client", client_opts)
            site_name = st.text_input("Site Name", value="" if c_sel=="Manual Entry" else c_sel)
            unit_name = st.text_input("Unit/Details")
        with c2:
            wo_file = st.file_uploader("Work Order", type=['pdf', 'jpg', 'png'])
            if st.button("DISPATCH", use_container_width=True):
                fname = ""
                if wo_file:
                    fname = f"WO_{site_name.replace(' ','_')}.{wo_file.name.split('.')[-1]}"
                    with open(os.path.join(W, fname), "wb") as f: f.write(wo_file.getbuffer())
                    sync_to_github(os.path.join(W, fname), "Upload WO")
                new_t = pd.DataFrame([{"AssignedTo": target_t, "Site": site_name, "Unit": unit_name, "Status": "Pending", "WO_File": fname, "Timestamp": datetime.now().strftime("%Y-%m-%d")}])
                td = pd.concat([td, new_t], ignore_index=True)
                td.to_csv(T, index=False); sync_to_github(T, "Dispatching"); st.success("Sent!"); st.rerun()

    with t2: # Clients
        st.subheader("📂 Add New Client")
        with st.form("add_c_fixed"):
            cn = st.text_input("Client Name")
            ca = st.text_input("Address")
            cr = st.text_input("Billing Rate")
            if st.form_submit_button("Save Client"):
                if cn:
                    new_c = pd.DataFrame([{"Client":cn,"Address":ca,"Cust_Rate":cr}])
                    cd = pd.concat([cd, new_c], ignore_index=True)
                    cd.to_csv(C, index=False); sync_to_github(C, "Add Client"); st.success("Saved"); st.rerun()
        
        st.divider()
        st.subheader("Current Clients")
        if cd.empty: st.info("No clients found.")
        else: st.dataframe(cd, use_container_width=True)

    with t3: # Payroll
        st.subheader("📊 Payroll Audit")
        if ld.empty: st.info("No time logs found yet.")
        else: st.dataframe(ld, use_container_width=True)

    with t4: # Staff
        st.subheader("👤 Add New Staff Member")
        with st.form("add_u_fixed"):
            unu = st.text_input("Worker Name")
            unp = st.text_input("4-Digit PIN")
            unr = st.number_input("Pay Rate ($/hr)", value=25.0)
            if st.form_submit_button("Create Account"):
                if unu and unp:
                    new_u = pd.DataFrame([{"User":unu,"PIN":unp,"Rate":unr,"Pic_File":""}])
                    ud = pd.concat([ud, new_u], ignore_index=True)
                    ud.to_csv(U, index=False); sync_to_github(U, "Add Staff"); st.success(f"Added {unu}!"); time.sleep(1); st.rerun()

        st.divider()
        st.subheader("Edit/Remove Staff")
        if ud.empty:
            st.info("Add a staff member above to see editing options.")
        else:
            edit_u = st.selectbox("Select Worker to Edit", ud['User'].tolist())
            u_idx = ud[ud['User'] == edit_u].index[0]
            with st.form("edit_u_vals"):
                upin = st.text_input("Update PIN", ud.at[u_idx, 'PIN'])
                urate = st.number_input("Update Rate", float(ud.at[u_idx, 'Rate']))
                if st.form_submit_button("Update Info"):
                    ud.at[u_idx, 'PIN'], ud.at[u_idx, 'Rate'] = upin, urate
                    ud.to_csv(U, index=False); sync_to_github(U, "Edit Staff"); st.success("Updated!"); st.rerun()

# ==============================================================================
# 7. TECHNICIAN VIEW
# ==============================================================================
else:
    if 'punch_in_dt' not in st.session_state:
        st.header(f"Worker: {st.session_state.user}")
        if td.empty:
            st.info("No jobs in the system.")
        else:
            jobs = td[(td['AssignedTo'] == st.session_state.user) & (td['Status'] == 'Pending')]
            if jobs.empty: st.info("No jobs assigned to you.")
            for i, r in jobs.iterrows():
                with st.container(border=True):
                    st.write(f"**{r['Site']}** | {r['Unit']}")
                    cam_in = st.camera_input("Arrival Photo", key=f"ci_{i}")
                    if st.button(f"🟢 START JOB", key=f"st_{i}", use_container_width=True):
                        p_in = save_img_cloud(cam_in, "IN", st.session_state.user)
                        st.session_state.active_site, st.session_state.active_unit, st.session_state.punch_in_dt = r['Site'], r['Unit'], datetime.now()
                        new_l = pd.DataFrame([{"User":st.session_state.user, "Site":r['Site'], "Unit":r['Unit'], "Date":datetime.now().strftime("%Y-%m-%d"), "Time In":datetime.now().strftime("%H:%M"), "Status":"Clocked In", "Seconds":0, "Photo_In": p_in}])
                        ld = pd.concat([ld, new_l], ignore_index=True)
                        ld.to_csv(L, index=False); sync_to_github(L, "Clock In"); st.rerun()
    else:
        st.header(f"Active: {st.session_state.active_site}")
        dur = (datetime.now() - st.session_state.punch_in_dt).total_seconds()
        st.metric("Work Duration", fmt_dur(dur))
        cam_out = st.camera_input("Departure Photo")
        notes = st.text_area("Job Notes")
        if st.button("🏁 FINALIZE JOB", type="primary", use_container_width=True):
            fs, p_out = (datetime.now() - st.session_state.punch_in_dt).total_seconds(), save_img_cloud(cam_out, "FINAL", st.session_state.user)
            ld.loc[(ld['User']==st.session_state.user)&(ld['Status']=='Clocked In'), ['Time Out','Status','Seconds','Total Time','Notes','Photo_Out']] = [datetime.now().strftime("%H:%M"), "FINALIZED", fs, fmt_dur(fs), notes, p_out]
            ld.to_csv(L, index=False); sync_to_github(L, "Clock Out")
            td.loc[(td['Site']==st.session_state.active_site)&(td['AssignedTo']==st.session_state.user), 'Status'] = 'Completed'
            td.to_csv(T, index=False); sync_to_github(T, "Job Done"); [st.session_state.pop(k) for k in ['punch_in_dt','active_site','active_unit']]; st.rerun()

if st.sidebar.button("Logout"):
    cookies["auth_status"] = "False"; cookies.save(); st.session_state.clear(); st.rerun()
