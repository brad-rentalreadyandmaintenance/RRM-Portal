import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime, timedelta
import time
from PIL import Image
import io

# 1. PAGE SETUP & STYLING
st.set_page_config(page_title="RRM Master Portal", layout="wide")
st.markdown("""
    <style>
    .stButton>button {height: 3.5em; font-size: 1.1rem; font-weight: bold; width: 100%; border-radius: 8px;}
    .job-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 10px;}
    </style>
    """, unsafe_allow_html=True)

# 2. CONFIG & PATHS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

PATHS = {
    "users": "data/users.csv", "clients": "data/clients.csv",
    "logs": "data/logs.csv", "tasks": "data/tasks.csv", "photos": "data/photos.csv"
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

# 4. DATA LOADING
@st.cache_data(show_spinner=False)
def get_cached_data(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    try:
        return pd.read_csv(path, dtype={'PIN': str, 'Unit': str})
    except:
        return pd.DataFrame(columns=columns)

if 'booted' not in st.session_state:
    for p in PATHS.values(): pull_from_github(p)
    st.session_state.booted = True

ud = get_cached_data(PATHS["users"], ["User", "PIN", "Rate"])
cd = get_cached_data(PATHS["clients"], ["Client", "Address"])
ld = get_cached_data(PATHS["logs"], ["User", "Client", "In", "Out", "Date", "Notes", "Duration"])
td = get_cached_data(PATHS["tasks"], ["Tech", "Client", "Unit", "Status"])
pd_photos = get_cached_data(PATHS["photos"], ["Date", "User", "Client", "Unit", "Type", "PhotoData"])

# 5. PERSISTENT LOGIN ENGINE (URL PARAMETERS)
params = st.query_params
if "user" in params:
    st.session_state.auth = True
    st.session_state.user = params["user"]
    st.session_state.role = params.get("role", "Tech")
else:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    u_type = st.radio("Select Login Mode", ["Admin", "Technician"])
    if u_type == "Admin":
        pin = st.text_input("Admin PIN", type="password")
        if st.button("Enter Admin Portal"):
            if pin == "0000":
                st.query_params.update({"user": "Admin", "role": "Admin"})
                st.rerun()
            else: st.error("Invalid PIN")
    else:
        if ud.empty: st.warning("Syncing data... please wait."); st.stop()
        t_name = st.selectbox("Your Name", ud['User'].tolist())
        t_pin = st.text_input("Your PIN", type="password")
        if st.button("Technician Login"):
            actual = str(ud[ud['User'] == t_name].iloc[0]['PIN']).zfill(4)
            if t_pin.strip().zfill(4) == actual:
                st.query_params.update({"user": t_name, "role": "Tech"})
                st.rerun()
            else: st.error("Incorrect PIN")
    st.stop()

# 6. SIDEBAR NAV
st.sidebar.title(f"👤 {st.session_state.user}")
view = st.session_state.role if st.session_state.role == "Tech" else st.sidebar.radio("Nav", ["Admin Dashboard", "Field Portal"])
if st.sidebar.button("🚪 Log Out"):
    st.query_params.clear(); st.session_state.clear(); st.cache_data.clear(); st.rerun()

# 7. ADMIN DASHBOARD
if view == "Admin Dashboard":
    st.title("🛠️ Admin Master Control")
    t1, t2, t3, t4, t5 = st.tabs(["Dispatch", "Staff Management", "Client List", "Work History", "Reports & Photos"])
    
    with t1:
        st.subheader("Assign New Job")
        with st.form("dispatch"):
            tech, client, unit = st.selectbox("Assign To", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit #")
            if st.form_submit_button("Assign Job"):
                new_t = pd.DataFrame([{"Tech":tech,"Client":client,"Unit":str(unit),"Status":"Pending"}])
                td = pd.concat([td, new_t], ignore_index=True); td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"]); st.cache_data.clear(); st.rerun()
        st.subheader("Active Tasks")
        for i, r in td.iterrows():
            c1, c2 = st.columns([5, 1])
            c1.info(f"**{r['Tech']}** is assigned to **{r['Client']}** (Unit {r['Unit']}) | Status: {r['Status']}")
            if c2.button("🗑️", key=f"dt_{i}"):
                td = td.drop(i); td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"]); st.cache_data.clear(); st.rerun()

    with t2:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Staff")
            with st.form("add_s"):
                n, p, r = st.text_input("Name"), st.text_input("PIN"), st.number_input("Hourly Rate", 25.0)
                if st.form_submit_button("Add Staff Member"):
                    ud = pd.concat([ud, pd.DataFrame([{"User":n,"PIN":str(p).zfill(4),"Rate":r}])], ignore_index=True)
                    ud.to_csv(PATHS["users"], index=False); push_to_github(PATHS["users"]); st.cache_data.clear(); st.rerun()
        with c2:
            st.subheader("Edit/Delete Staff")
            if not ud.empty:
                sel_u = st.selectbox("Select Staff", ud['User'].tolist())
                u_data = ud[ud['User'] == sel_u].iloc[0]
                with st.form("edit_s"):
                    en, ep, er = st.text_input("Name", u_data['User']), st.text_input("PIN", u_data['PIN']), st.number_input("Rate", float(u_data['Rate']))
                    if st.form_submit_button("Update Staff"):
                        ud.loc[ud['User'] == sel_u, ['User', 'PIN', 'Rate']] = [en, str(ep).zfill(4), er]
                        ud.to_csv(PATHS["users"], index=False); push_to_github(PATHS["users"]); st.cache_data.clear(); st.rerun()
                    if st.form_submit_button("🗑️ Delete"):
                        ud = ud[ud['User'] != sel_u]; ud.to_csv(PATHS["users"], index=False); push_to_github(PATHS["users"]); st.cache_data.clear(); st.rerun()

    with t3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Client")
            with st.form("add_c"):
                cn, ca = st.text_input("Client Name"), st.text_input("Address")
                if st.form_submit_button("Save Client"):
                    cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])], ignore_index=True)
                    cd.to_csv(PATHS["clients"], index=False); push_to_github(PATHS["clients"]); st.cache_data.clear(); st.rerun()
        with c2:
            st.subheader("Edit Client")
            if not cd.empty:
                sel_c = st.selectbox("Select Client", cd['Client'].tolist())
                c_data = cd[cd['Client'] == sel_c].iloc[0]
                with st.form("edit_c"):
                    ecn, eca = st.text_input("Name", c_data['Client']), st.text_input("Address", c_data['Address'])
                    if st.form_submit_button("Update Client"):
                        cd.loc[cd['Client'] == sel_c, ['Client', 'Address']] = [ecn, eca]
                        cd.to_csv(PATHS["clients"], index=False); push_to_github(PATHS["clients"]); st.cache_data.clear(); st.rerun()
                    if st.form_submit_button("🗑️ Delete Client"):
                        cd = cd[cd['Client'] != sel_c]; cd.to_csv(PATHS["clients"], index=False); push_to_github(PATHS["clients"]); st.cache_data.clear(); st.rerun()

    with t4: st.dataframe(ld, use_container_width=True)
    with t5:
        if not ld.empty:
            s_log = st.selectbox("Select Job Log", ld.index, format_func=lambda x: f"{ld.iloc[x]['Date']} - {ld.iloc[x]['Client']}")
            sel = ld.iloc[s_log]
            st.info(f"**Report Preview:**\n{sel['Client']} on {sel['Date']} by {sel['User']}\nWork: {sel['Notes']}")
            st.download_button("Export as Text", f"Client: {sel['Client']}\nWork: {sel['Notes']}", "report.txt")
            ph = pd_photos[(pd_photos['Client'] == sel['Client']) & (pd_photos['Date'] == sel['Date'])]
            for _, p in ph.iterrows():
                st.image(base64.b64decode(p['PhotoData']), caption=p['Type'])

# 8. TECH PORTAL
else:
    st.title("📱 Technician Portal")
    if 'job' not in st.session_state:
        st.subheader("📅 Your Assignments")
        tasks = td[(td['Tech'] == st.session_state.user) & (td['Status'] == 'Pending')]
        if tasks.empty: st.info("No assigned jobs. Use 'Manual Work' below if needed.")
        for i, r in tasks.iterrows():
            st.markdown(f"<div class='job-card'><b>{r['Client']}</b><br>Unit: {r['Unit']}</div>", unsafe_allow_html=True)
            if st.button(f"Clock In: {r['Client']}", key=f"in_{i}"):
                st.session_state.job = {"c": r['Client'], "u": str(r['Unit']), "type": "D"}
                st.session_state.start = get_mst_time(); st.rerun()
        st.divider()
        st.subheader("⚡ Manual Entry")
        is_new = st.checkbox("➕ Add New/Unlisted Client")
        m_c = st.text_input("New Client Name") if is_new else st.selectbox("Existing Client", ["--"] + cd['Client'].tolist())
        m_u = st.text_input("Unit #")
        if st.button("Start Manual Clock-In"):
            if m_c and m_c != "--":
                st.session_state.job = {"c": m_c, "u": m_u, "type": "M"}
                st.session_state.start = get_mst_time(); st.rerun()
    else:
        st.warning(f"🕒 WORKING: {st.session_state.job['c']} (Unit: {st.session_state.job['u']})")
        if 'before_taken' not in st.session_state:
            st.subheader("📸 Step 1: Before Photos (Optional)")
            bf = st.file_uploader("Snap/Upload Before Photo", type=['jpg','png','jpeg'])
            if st.button("Continue to Work"):
                if bf:
                    img = Image.open(bf); img.thumbnail((800,800)); buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70); enc = base64.b64encode(buf.getvalue()).decode()
                    new_p = pd.DataFrame([{"Date": get_mst_time().strftime('%Y-%m-%d'), "User": st.session_state.user, "Client": st.session_state.job['c'], "Unit": str(st.session_state.job['u']), "Type": "Before", "PhotoData": enc}])
                    pd_photos = pd.concat([pd_photos, new_p], ignore_index=True); pd_photos.to_csv(PATHS["photos"], index=False); push_to_github(PATHS["photos"]); st.cache_data.clear()
                st.session_state.before_taken = True; st.rerun()
        else:
            notes = st.text_area("Job Details / Progress Notes")
            af = st.file_uploader("📸 Step 2: After Photo (Optional)", type=['jpg','png','jpeg'])
            c1, c2 = st.columns(2)
            with c1:
                if st.button("⌛ PAUSE JOB"):
                    et = get_mst_time(); dur = str(et-st.session_state.start).split(".")[0]
                    new_l = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": et.strftime('%H:%M'), "Date": et.strftime('%Y-%m-%d'), "Notes": f"[PAUSED] {notes}", "Duration": dur}])
                    ld = pd.concat([ld, new_l], ignore_index=True); ld.to_csv(PATHS["logs"], index=False); push_to_github(PATHS["logs"])
                    if st.session_state.job['type'] == "M":
                        new_t = pd.DataFrame([{"Tech": st.session_state.user, "Client": st.session_state.job['c'], "Unit": st.session_state.job['u'], "Status": "Pending"}])
                        td = pd.concat([td, new_t], ignore_index=True); td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"])
                    del st.session_state.job; del st.session_state.before_taken; st.cache_data.clear(); st.rerun()
            with c2:
                if st.button("🏁 FINALIZE JOB", type="primary"):
                    if af:
                        img = Image.open(af); img.thumbnail((800,800)); buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70); enc = base64.b64encode(buf.getvalue()).decode()
                        new_p = pd.DataFrame([{"Date": get_mst_time().strftime('%Y-%m-%d'), "User": st.session_state.user, "Client": st.session_state.job['c'], "Unit": str(st.session_state.job['u']), "Type": "After", "PhotoData": enc}])
                        pd_photos = pd.concat([pd_photos, new_p], ignore_index=True); pd_photos.to_csv(PATHS["photos"], index=False); push_to_github(PATHS["photos"])
                    et = get_mst_time(); dur = str(et-st.session_state.start).split(".")[0]
                    new_l = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": et.strftime('%H:%M'), "Date": et.strftime('%Y-%m-%d'), "Notes": notes, "Duration": dur}])
                    ld = pd.concat([ld, new_l], ignore_index=True); ld.to_csv(PATHS["logs"], index=False); push_to_github(PATHS["logs"])
                    td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.job['c']), 'Status'] = 'Done'
                    td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"])
                    del st.session_state.job; del st.session_state.before_taken; st.cache_data.clear(); st.rerun()
