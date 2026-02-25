import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime, timedelta
import time
from PIL import Image
import io

# 1. PAGE SETUP
st.set_page_config(page_title="RRM Master Portal", layout="wide")
st.markdown("<style>button {height: 3.5em !important; font-size: 1.1rem !important; font-weight: bold !important;}</style>", unsafe_allow_html=True)

# 2. CONFIG & PATHS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

PATHS = {
    "users": "data/users.csv",
    "clients": "data/clients.csv",
    "logs": "data/logs.csv",
    "tasks": "data/tasks.csv",
    "photos": "data/photos.csv"
}

def get_mst_time():
    return datetime.utcnow() - timedelta(hours=7)

# 3. GITHUB SYNC (Persistence Guard)
def pull_from_github(path):
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            content = base64.b64decode(res.json()['content']).decode('utf-8')
            if len(content) > 2: 
                with open(path, "w") as f: f.write(content)
            return True
    except: pass
    return False

def push_to_github(path):
    if not os.path.exists(path) or os.path.getsize(path) < 5: return
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

# 4. DATA LOADING (Cache Shield)
@st.cache_data(show_spinner=False)
def get_cached_data(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    try:
        df = pd.read_csv(path, dtype={'PIN': str, 'Unit': str})
    except:
        df = pd.DataFrame(columns=columns)
    return df

if 'booted' not in st.session_state:
    with st.spinner("🛡️ Finalizing Secure Data Link..."):
        for p in PATHS.values(): pull_from_github(p)
        time.sleep(1)
    st.session_state.booted = True

ud = get_cached_data(PATHS["users"], ["User", "PIN", "Rate"])
cd = get_cached_data(PATHS["clients"], ["Client", "Address"])
ld = get_cached_data(PATHS["logs"], ["User", "Client", "In", "Out", "Date", "Notes", "Duration"])
td = get_cached_data(PATHS["tasks"], ["Tech", "Client", "Unit", "Status"])
pd_photos = get_cached_data(PATHS["photos"], ["Date", "User", "Client", "Unit", "Type", "PhotoData"])

# 5. AUTHENTICATION
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    u_type = st.radio("Select Login Mode", ["Admin", "Technician"])
    if u_type == "Admin":
        pin = st.text_input("Admin PIN", type="password")
        if st.button("Enter Admin Portal"):
            if pin == "0000":
                st.session_state.update({"auth": True, "role": "Admin", "user": "Admin"})
                st.rerun()
            else: st.error("Invalid PIN")
    else:
        if ud.empty: st.warning("Loading Staff List..."); st.stop()
        t_name = st.selectbox("Select Your Name", ud['User'].tolist())
        t_pin = st.text_input("Enter Your PIN", type="password")
        if st.button("Technician Login"):
            actual = str(ud[ud['User'] == t_name].iloc[0]['PIN']).zfill(4)
            if t_pin.strip().zfill(4) == actual:
                st.session_state.update({"auth": True, "role": "Tech", "user": t_name})
                st.rerun()
            else: st.error("Incorrect PIN")
    st.stop()

# 6. SIDEBAR
st.sidebar.title(f"Logged in: {st.session_state.user}")
view = st.session_state.role if st.session_state.role == "Tech" else st.sidebar.radio("Navigation", ["Admin Dashboard", "Field Portal"])
if st.sidebar.button("Log Out"):
    st.session_state.clear(); st.cache_data.clear(); st.rerun()

# 7. ADMIN DASHBOARD
if view == "Admin Dashboard":
    st.title("🛠️ Admin Dashboard")
    tabs = st.tabs(["Dispatch Work", "Staff Management", "Client Management", "Work History", "Photo Reports"])
    
    with tabs[0]:
        st.subheader("Assign Job")
        with st.form("dispatch_form"):
            tech, client, unit = st.selectbox("Assign To", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit #")
            if st.form_submit_button("Send Job to Tech"):
                new_t = pd.DataFrame([{"Tech":tech,"Client":client,"Unit":str(unit),"Status":"Pending"}])
                td = pd.concat([td, new_t], ignore_index=True); td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"]); st.cache_data.clear(); st.rerun()
        
        st.divider()
        st.subheader("Current Assignments")
        for i, r in td.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"**{r['Tech']}** -> {r['Client']} (Unit: {r['Unit']}) | Status: {r['Status']}")
            if c2.button("🗑️ Delete", key=f"del_task_{i}"):
                td = td.drop(i); td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"]); st.cache_data.clear(); st.rerun()

    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Staff")
            with st.form("add_staff"):
                n, p, r = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", 25.0)
                if st.form_submit_button("Save New Staff"):
                    ud = pd.concat([ud, pd.DataFrame([{"User":n,"PIN":str(p).zfill(4),"Rate":r}])], ignore_index=True)
                    ud.to_csv(PATHS["users"], index=False); push_to_github(PATHS["users"]); st.cache_data.clear(); st.rerun()
        with c2:
            st.subheader("Edit Staff")
            if not ud.empty:
                edit_u = st.selectbox("Select Staff to Edit", ud['User'].tolist())
                u_row = ud[ud['User'] == edit_u].iloc[0]
                with st.form("edit_staff"):
                    en, ep, er = st.text_input("Name", u_row['User']), st.text_input("PIN", u_row['PIN']), st.number_input("Rate", float(u_row['Rate']))
                    if st.form_submit_button("Update Staff Info"):
                        ud.loc[ud['User'] == edit_u, ['User', 'PIN', 'Rate']] = [en, str(ep).zfill(4), er]
                        ud.to_csv(PATHS["users"], index=False); push_to_github(PATHS["users"]); st.cache_data.clear(); st.rerun()
                    if st.form_submit_button("🗑️ Permanently Delete"):
                        ud = ud[ud['User'] != edit_u]; ud.to_csv(PATHS["users"], index=False); push_to_github(PATHS["users"]); st.cache_data.clear(); st.rerun()

    with tabs[2]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Client")
            with st.form("add_client"):
                cn, ca = st.text_input("Client Name"), st.text_input("Address")
                if st.form_submit_button("Save New Client"):
                    cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])], ignore_index=True)
                    cd.to_csv(PATHS["clients"], index=False); push_to_github(PATHS["clients"]); st.cache_data.clear(); st.rerun()
        with c2:
            st.subheader("Edit Client")
            if not cd.empty:
                edit_c = st.selectbox("Select Client to Edit", cd['Client'].tolist())
                c_row = cd[cd['Client'] == edit_c].iloc[0]
                with st.form("edit_client"):
                    ecn, eca = st.text_input("Client Name", c_row['Client']), st.text_input("Address", c_row['Address'])
                    if st.form_submit_button("Update Client Info"):
                        cd.loc[cd['Client'] == edit_c, ['Client', 'Address']] = [ecn, eca]
                        cd.to_csv(PATHS["clients"], index=False); push_to_github(PATHS["clients"]); st.cache_data.clear(); st.rerun()
                    if st.form_submit_button("🗑️ Delete Client"):
                        cd = cd[cd['Client'] != edit_c]; cd.to_csv(PATHS["clients"], index=False); push_to_github(PATHS["clients"]); st.cache_data.clear(); st.rerun()

    with tabs[3]:
        st.subheader("All Work Logs")
        st.dataframe(ld, use_container_width=True)
        if st.button("Clear Cache & Force Sync"): st.cache_data.clear(); st.rerun()

    with tabs[4]:
        st.subheader("Client Job Reports")
        if not ld.empty:
            sel_log = st.selectbox("Select a Job Entry", ld.index, format_func=lambda x: f"{ld.iloc[x]['Date']} - {ld.iloc[x]['Client']}")
            sel = ld.iloc[sel_log]
            report = f"JOB REPORT\nClient: {sel['Client']}\nDate: {sel['Date']}\nWork: {sel['Notes']}\nDuration: {sel['Duration']}"
            st.text_area("Email Content", report, height=150)
            photos = pd_photos[(pd_photos['Client'] == sel['Client']) & (pd_photos['Date'] == sel['Date'])]
            for _, pr in photos.iterrows():
                img = base64.b64decode(pr['PhotoData']); st.image(img, caption=pr['Type'])
                st.download_button(f"Download {pr['Type']} Photo", img, f"{sel['Client']}_photo.jpg")

# 8. TECH PORTAL
else:
    st.title("📱 Technician Portal")
    if 'job' not in st.session_state:
        st.subheader("📌 Assigned Tasks")
        tasks = td[(td['Tech'] == st.session_state.user) & (td['Status'] == 'Pending')]
        if tasks.empty: st.info("No jobs assigned.")
        for i, r in tasks.iterrows():
            with st.container(border=True):
                st.write(f"**{r['Client']}** - Unit: {r['Unit']}")
                if st.button(f"Clock In: {r['Client']}", key=f"in_{i}"):
                    st.session_state.job = {"c": r['Client'], "u": str(r['Unit']), "type": "D"}
                    st.session_state.start = get_mst_time(); st.rerun()
        
        st.divider()
        st.subheader("⚡ Start Unlisted Job")
        is_new = st.checkbox("➕ Add New/Unlisted Client")
        m_c = st.text_input("Type Client Name") if is_new else st.selectbox("Select Existing Client", ["-- Select --"] + cd['Client'].tolist())
        m_u = st.text_input("Unit #")
        if st.button("Start Manual Work"):
            if m_c and m_c != "-- Select --":
                st.session_state.job = {"c": m_c, "u": m_u, "type": "M"}
                st.session_state.start = get_mst_time(); st.rerun()
    else:
        st.warning(f"ACTIVE JOB: {st.session_state.job['c']}")
        if 'before_taken' not in st.session_state:
            st.subheader("📸 Step 1: Before Photos")
            bf = st.file_uploader("Capture Photo", type=['jpg','png','jpeg'])
            if st.button("Skip / Continue to Job"):
                if bf:
                    img = Image.open(bf); img.thumbnail((800,800)); buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70); enc = base64.b64encode(buf.getvalue()).decode()
                    new_p = pd.DataFrame([{"Date": get_mst_time().strftime('%Y-%m-%d'), "User": st.session_state.user, "Client": st.session_state.job['c'], "Unit": str(st.session_state.job['u']), "Type": "Before", "PhotoData": enc}])
                    pd_photos = pd.concat([pd_photos, new_p], ignore_index=True); pd_photos.to_csv(PATHS["photos"], index=False); push_to_github(PATHS["photos"]); st.cache_data.clear()
                st.session_state.before_taken = True; st.rerun()
        else:
            notes = st.text_area("Work Details / Notes")
            af = st.file_uploader("📸 Step 2: After Photos", type=['jpg','png','jpeg'])
            c1, c2 = st.columns(2)
            with c1:
                if st.button("⌛ PAUSE (Lunch/Emergency)"):
                    et = get_mst_time(); dur = str(et-st.session_state.start).split(".")[0]
                    new_l = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": et.strftime('%H:%M'), "Date": et.strftime('%Y-%m-%d'), "Notes": f"[PAUSED] {notes}", "Duration": dur}])
                    ld = pd.concat([ld, new_l], ignore_index=True); ld.to_csv(PATHS["logs"], index=False); push_to_github(PATHS["logs"])
                    if st.session_state.job['type'] == "M":
                        new_t = pd.DataFrame([{"Tech": st.session_state.user, "Client": st.session_state.job['c'], "Unit": st.session_state.job['u'], "Status": "Pending"}])
                        td = pd.concat([td, new_t], ignore_index=True); td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"])
                    st.session_state.clear(); st.cache_data.clear(); st.session_state.booted = True; st.rerun()
            with c2:
                if st.button("🏁 FINALIZE JOB", type="primary"):
                    if af:
                        img = Image.open(af); img.thumbnail((800,800)); buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70); enc = base64.b64encode(buf.getvalue()).decode()
                        new_p = pd.DataFrame([{"Date": get_mst_time().strftime('%Y-%m-%d'), "User": st.session_state.user, "Client": st.session_state.job['c'], "Unit": str(st.session_state.job['u']), "Type": "After", "PhotoData": enc}])
                        pd_photos = pd.concat([pd_photos, new_p], ignore_index=True); pd_photos.to_csv(PATHS["photos"], index=False); push_to_github(PATHS["photos"])
                    et = get_mst_time(); dur = str(et-st.session_state.start).split(".")[0]
                    new_l = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": et.strftime('%H:%M'), "Date": et.strftime('%Y-%m-%d'), "Notes": notes, "Duration": dur}])
                    ld = pd.concat([ld, new_l], ignore_index=True); ld.to_csv(PATHS["logs"], index=False); push_to_github(PATHS["logs"])
                    td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.job['c']) & (td['Unit'] == st.session_state.job['u']), 'Status'] = 'Done'
                    td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"])
                    st.session_state.clear(); st.cache_data.clear(); st.session_state.booted = True; st.rerun()
