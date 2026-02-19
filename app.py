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
from streamlit_drawable_canvas import st_canvas
from streamlit_cookies_manager import EncryptedCookieManager

# ==============================================================================
# 1. CLOUD PERSISTENCE LOGIC (OPTION B)
# ==============================================================================
# Retrieve secrets from Streamlit Cloud dashboard
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
REPO_NAME = st.secrets.get("REPO_NAME", "")
BRANCH = "main"

def sync_to_github(file_path, msg="Data update"):
    """Pushes local CSV changes back to the private GitHub Repo."""
    if not GITHUB_TOKEN or not REPO_NAME:
        return # Skip if local or secrets not set
        
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Get current file SHA to allow overwrite
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None

    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    payload = {"message": msg, "content": content, "branch": BRANCH}
    if sha: payload["sha"] = sha

    requests.put(url, headers=headers, json=payload)

# ==============================================================================
# 2. PATHS AND CONFIG
# ==============================================================================
B = "data/" 
TP, P, S, W = B+"tech_pics/", B+"site_photos/", B+"signatures/", B+"work_orders/"
T, L, M, C, U = B+"tasks.csv", B+"time_log.csv", B+"material_logs.csv", B+"clients.csv", B+"users.csv"
DM = B+"draft_mats.csv"

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
        M: ["Date", "User", "Site", "Material", "Cost"],
        DM: ["Material", "Cost", "User", "Site"]
    }
    for p, cols in headers.items():
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            pd.DataFrame(columns=cols).to_csv(p, index=False)
            sync_to_github(p, "Initialize data file")

init()
st_autorefresh(interval=30000, key="global_hb")

# ==============================================================================
# 3. CORE UTILITIES
# ==============================================================================
if os.path.exists("logo.png"): st.sidebar.image("logo.png", use_container_width=True)

@st.cache_data(ttl=5)
def load(f):
    if not os.path.exists(f): return pd.DataFrame()
    try: return pd.read_csv(f)
    except: return pd.DataFrame()

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
    su = st.selectbox("User", udb['User'].tolist() if not udb.empty else ["Admin"])
    pi = st.text_input("PIN", type="password")
    if st.button("LOG IN", use_container_width=True):
        if su == "Admin" and pi == "0000":
            st.session_state.authenticated, st.session_state.user = True, "Admin"
            cookies["auth_status"], cookies["auth_user"] = "True", "Admin"
            cookies.save(); st.rerun()
        else:
            match = udb[udb['User'] == su]
            if not match.empty and pi == str(match['PIN'].values[0]).zfill(4):
                st.session_state.authenticated, st.session_state.user = True, su
                cookies["auth_status"], cookies["auth_user"] = "True", su
                cookies.save(); st.rerun()
            else: st.error("Invalid PIN")
    st.stop()

# ==============================================================================
# 5. ADMIN & TECHNICIAN LOGIC
# ==============================================================================
ld, td, cd, ud = load(L), load(T), load(C), load(U)
is_adm = (st.session_state.user == "Admin")
mode = st.sidebar.radio("Navigation", ["Admin", "Technician"]) if is_adm else "Technician"

if is_adm and mode == "Admin":
    t1, t2, t3, t4 = st.tabs(["Dispatch", "Clients", "Payroll Audit", "Staff"])
    
    with t1: # Dispatch
        st.subheader("Dispatch Job")
        c1, c2 = st.columns(2)
        with c1:
            target_t = st.selectbox("Assign Tech", ud['User'].tolist() if not ud.empty else ["No Techs"])
            c_sel = st.selectbox("Client", ["Manual"] + cd['Client'].tolist() if not cd.empty else ["Manual"])
            site_name = st.text_input("Site", value="" if c_sel=="Manual" else c_sel)
            unit_name = st.text_input("Unit/Details")
        with c2:
            wo_file = st.file_uploader("Work Order", type=['pdf', 'jpg', 'png'])
            if st.button("Dispatch", use_container_width=True):
                fname = ""
                if wo_file:
                    fname = f"WO_{site_name.replace(' ','_')}.{wo_file.name.split('.')[-1]}"
                    with open(os.path.join(W, fname), "wb") as f: f.write(wo_file.getbuffer())
                    sync_to_github(os.path.join(W, fname), "Upload WO")
                new_t = {"AssignedTo": target_t, "Site": site_name, "Unit": unit_name, "Status": "Pending", "WO_File": fname, "Timestamp": datetime.now().strftime("%Y-%m-%d")}
                pd.concat([td, pd.DataFrame([new_t])], ignore_index=True).to_csv(T, index=False)
                sync_to_github(T, "Dispatching job"); st.success("Dispatched"); st.rerun()

    with t2: # Client Manager
        st.subheader("Client Manager")
        with st.form("add_c"):
            n1, n2, n3 = st.text_input("Client Name"), st.text_input("Address"), st.text_input("Rate")
            if st.form_submit_button("Add Client"):
                pd.concat([cd, pd.DataFrame([{"Client":n1,"Address":n2,"Cust_Rate":n3}])], ignore_index=True).to_csv(C, index=False)
                sync_to_github(C, "Added Client"); st.rerun()

    with t4: # Staff Management (Restore Edit Logic)
        st.subheader("Staff Management")
        if not ud.empty:
            edit_u = st.selectbox("Edit Staff", ud['User'].tolist())
            u_idx = ud[ud['User'] == edit_u].index[0]
            with st.form("edit_staff"):
                up1, up2 = st.text_input("PIN", ud.at[u_idx,'PIN']), st.number_input("Rate", float(ud.at[u_idx,'Rate']))
                if st.form_submit_button("Update"):
                    ud.at[u_idx,'PIN'], ud.at[u_idx,'Rate'] = up1, up2
                    ud.to_csv(U, index=False); sync_to_github(U, "Updated staff"); st.rerun()

else: # ==================== TECHNICIAN VIEW ====================
    if 'punch_in_dt' not in st.session_state:
        st.header(f"Worker: {st.session_state.user}")
        jobs = td[(td['AssignedTo'] == st.session_state.user) & (td['Status'] == 'Pending')]
        for i, r in jobs.iterrows():
            with st.container(border=True):
                st.write(f"**{r['Site']}** | {r['Unit']}")
                cam_in = st.camera_input("Arrival Photo", key=f"ci_{i}")
                if st.button(f"🟢 START JOB", key=f"st_{i}", use_container_width=True):
                    p_in = save_img_cloud(cam_in, "IN", st.session_state.user)
                    st.session_state.active_site, st.session_state.active_unit, st.session_state.punch_in_dt = r['Site'], r['Unit'], datetime.now()
                    new_l = {"User":st.session_state.user, "Site":r['Site'], "Unit":r['Unit'], "Date":datetime.now().strftime("%Y-%m-%d"), "Time In":datetime.now().strftime("%H:%M"), "Status":"Clocked In", "Seconds":0, "Photo_In": p_in}
                    pd.concat([ld, pd.DataFrame([new_l])], ignore_index=True).to_csv(L, index=False)
                    sync_to_github(L, "New clock in"); st.rerun()
        
        with st.expander("➕ Manual Project Entry"):
            msite, munit = st.text_input("Site Name"), st.text_input("Unit #")
            mcam = st.camera_input("Arrival Photo (Manual)")
            if st.button("Manual Clock In") and msite:
                p_in = save_img_cloud(mcam, "IN_MAN", st.session_state.user)
                st.session_state.active_site, st.session_state.active_unit, st.session_state.punch_in_dt = msite, munit, datetime.now()
                new_l = {"User":st.session_state.user, "Site":msite, "Unit":munit, "Date":datetime.now().strftime("%Y-%m-%d"), "Time In":datetime.now().strftime("%H:%M"), "Status":"Clocked In", "Seconds":0, "Photo_In": p_in}
                pd.concat([ld, pd.DataFrame([new_l])], ignore_index=True).to_csv(L, index=False)
                sync_to_github(L, "Manual clock in"); st.rerun()
    else:
        # Active Shift
        st.header(f"Active: {st.session_state.active_site}")
        dur = (datetime.now() - st.session_state.punch_in_dt).total_seconds()
        st.metric("Duration", fmt_dur(dur))
        cam_out = st.camera_input("Departure Photo")
        notes = st.text_area("Notes")
        
        if st.button("⏸️ PAUSE (Multi-day)", use_container_width=True):
            fs, p_out = (datetime.now() - st.session_state.punch_in_dt).total_seconds(), save_img_cloud(cam_out, "PAUSE", st.session_state.user)
            ld.loc[(ld['User']==st.session_state.user)&(ld['Status']=='Clocked In'), ['Time Out','Status','Seconds','Total Time','Notes','Photo_Out']] = [datetime.now().strftime("%H:%M"), "FINALIZED", fs, fmt_dur(fs), f"[PAUSED] {notes}", p_out]
            ld.to_csv(L, index=False); sync_to_github(L, "Paused session"); [st.session_state.pop(k) for k in ['punch_in_dt','active_site','active_unit']]; st.rerun()
            
        if st.button("🏁 FINALIZE JOB", type="primary", use_container_width=True):
            fs, p_out = (datetime.now() - st.session_state.punch_in_dt).total_seconds(), save_img_cloud(cam_out, "FINAL", st.session_state.user)
            ld.loc[(ld['User']==st.session_state.user)&(ld['Status']=='Clocked In'), ['Time Out','Status','Seconds','Total Time','Notes','Photo_Out']] = [datetime.now().strftime("%H:%M"), "FINALIZED", fs, fmt_dur(fs), notes, p_out]
            ld.to_csv(L, index=False); sync_to_github(L, "Finalized shift")
            td.loc[(td['Site']==st.session_state.active_site)&(td['AssignedTo']==st.session_state.user), 'Status'] = 'Completed'
            td.to_csv(T, index=False); sync_to_github(T, "Completed Job"); [st.session_state.pop(k) for k in ['punch_in_dt','active_site','active_unit']]; st.rerun()

if st.sidebar.button("Logout"):
    cookies["auth_status"] = "False"; cookies.save(); st.session_state.clear(); st.rerun()