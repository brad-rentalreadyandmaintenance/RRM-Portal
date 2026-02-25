import streamlit as st
import pandas as pd
import os
import requests
import base64
from datetime import datetime, timedelta
import time
from PIL import Image
import io

# 1. PAGE SETUP & PERSISTENCE
st.set_page_config(page_title="RRM Master Portal", layout="wide")
st.markdown("<style>button {height: 3em !important; font-size: 1.1rem !important;}</style>", unsafe_allow_html=True)

# 2. CONFIG
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

# 3. ROBUST GITHUB SYNC
def pull_from_github(path):
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            content = base64.b64decode(res.json()['content']).decode('utf-8')
            # Safety: Only write if the content isn't inexplicably empty
            if len(content) > 5: 
                with open(path, "w") as f: f.write(content)
            return True
    except: pass
    return False

def push_to_github(path):
    if not os.path.exists(path): return
    try:
        # Safety: Don't push if the file is empty (prevents wiping GitHub)
        if os.path.getsize(path) < 10: return 
        
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

# 4. DATA LOADING WITH CACHE SHIELD
@st.cache_data(show_spinner=False)
def get_cached_data(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    try:
        df = pd.read_csv(path, dtype={'PIN': str, 'Unit': str})
        if df.empty and path != PATHS["photos"]: # Photos can be empty, others shouldn't be
            pull_from_github(path)
            df = pd.read_csv(path, dtype={'PIN': str, 'Unit': str})
    except:
        df = pd.DataFrame(columns=columns)
    return df

# Initial Sync on Boot
if 'booted' not in st.session_state:
    with st.spinner("🛡️ Securing Connection to Database..."):
        for p in PATHS.values():
            pull_from_github(p)
        time.sleep(1)
    st.session_state.booted = True

# Load working dataframes
ud = get_cached_data(PATHS["users"], ["User", "PIN", "Rate"])
cd = get_cached_data(PATHS["clients"], ["Client", "Address"])
ld = get_cached_data(PATHS["logs"], ["User", "Client", "In", "Out", "Date", "Notes", "Duration"])
td = get_cached_data(PATHS["tasks"], ["Tech", "Client", "Unit", "Status"])
pd_photos = get_cached_data(PATHS["photos"], ["Date", "User", "Client", "Unit", "Type", "PhotoData"])

# 5. AUTHENTICATION (Persistent)
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Portal Login")
    u_type = st.radio("Mode", ["Admin", "Technician"])
    if u_type == "Admin":
        pin = st.text_input("Admin PIN", type="password")
        if st.button("Access Admin"):
            if pin == "0000":
                st.session_state.update({"auth": True, "role": "Admin", "user": "Admin"})
                st.rerun()
    else:
        if ud.empty: 
            st.error("Data Syncing... please click 'Refresh' in 5 seconds.")
            if st.button("Refresh"): st.rerun()
            st.stop()
        t_name = st.selectbox("Name", ud['User'].tolist())
        t_pin = st.text_input("PIN", type="password")
        if st.button("Login"):
            actual = str(ud[ud['User'] == t_name].iloc[0]['PIN']).zfill(4)
            if t_pin.strip().zfill(4) == actual:
                st.session_state.update({"auth": True, "role": "Tech", "user": t_name})
                st.rerun()
    st.stop()

# 6. NAVIGATION
view = st.session_state.role if st.session_state.role == "Tech" else st.sidebar.radio("Nav", ["Admin", "Field Portal"])
if st.sidebar.button("Log Out"):
    st.session_state.clear()
    st.cache_data.clear()
    st.rerun()

# 7. ADMIN DASHBOARD
if view == "Admin":
    st.title("🛠️ Admin Dashboard")
    t1, t2, t3, t4, t5 = st.tabs(["Dispatch", "Staff", "Clients", "Work History", "Reports"])
    
    with t1:
        with st.form("dispatch"):
            tech, client, unit = st.selectbox("Tech", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit")
            if st.form_submit_button("Send"):
                new_t = pd.DataFrame([{"Tech":tech,"Client":client,"Unit":str(unit),"Status":"Pending"}])
                td = pd.concat([td, new_t], ignore_index=True)
                td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"])
                st.cache_data.clear(); st.rerun()
        st.dataframe(td, use_container_width=True)

    with t2:
        col_a, col_b = st.columns(2)
        with col_a:
            with st.form("add_staff"):
                n, p, r = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", 25.0)
                if st.form_submit_button("Add"):
                    new_staff = pd.DataFrame([{"User":n,"PIN":str(p).zfill(4),"Rate":r}])
                    temp_ud = pd.concat([ud, new_staff], ignore_index=True)
                    temp_ud.to_csv(PATHS["users"], index=False); push_to_github(PATHS["users"])
                    st.cache_data.clear(); st.rerun()
        st.dataframe(ud)

    with t3:
        with st.form("add_client"):
            cn, ca = st.text_input("Client"), st.text_input("Address")
            if st.form_submit_button("Add"):
                new_client = pd.DataFrame([{"Client":cn,"Address":ca}])
                temp_cd = pd.concat([cd, new_client], ignore_index=True)
                temp_cd.to_csv(PATHS["clients"], index=False); push_to_github(PATHS["clients"])
                st.cache_data.clear(); st.rerun()
        st.dataframe(cd)

    with t4:
        st.dataframe(ld, use_container_width=True)

    with t5:
        st.subheader("Photo & Client Reports")
        if not ld.empty:
            log_choice = st.selectbox("Select Entry", ld.index, format_func=lambda x: f"{ld.iloc[x]['Date']} - {ld.iloc[x]['Client']}")
            sel = ld.iloc[log_choice]
            job_p = pd_photos[(pd_photos['Client'] == sel['Client']) & (pd_photos['Date'] == sel['Date'])]
            st.text_area("Report", f"WORK REPORT\nClient: {sel['Client']}\nNotes: {sel['Notes']}")
            for _, pr in job_p.iterrows():
                img_b = base64.b64decode(pr['PhotoData'])
                st.image(img_b, caption=pr['Type'])
                st.download_button(f"Download {pr['Type']}", img_b, f"photo.jpg", "image/jpeg")

# 8. TECH PORTAL
else:
    st.title("📱 Technician Portal")
    if 'job' not in st.session_state:
        tasks = td[(td['Tech'] == st.session_state.user) & (td['Status'] == 'Pending')]
        for i, r in tasks.iterrows():
            with st.container(border=True):
                st.write(f"**{r['Client']}** - Unit: {r['Unit']}")
                if st.button(f"Clock In: {r['Client']}", key=f"in_{i}"):
                    st.session_state.job = {"c": r['Client'], "u": str(r['Unit']), "type": "D"}
                    st.session_state.start = get_mst_time(); st.rerun()
        
        st.divider()
        st.subheader("⚡ Manual Job")
        is_new = st.checkbox("New Client?")
        m_c = st.text_input("Name") if is_new else st.selectbox("Select", ["--"] + cd['Client'].tolist())
        m_u = st.text_input("Unit #")
        if st.button("Start Now"):
            if m_c and m_c != "--":
                st.session_state.job = {"c": m_c, "u": str(m_u), "type": "M"}
                st.session_state.start = get_mst_time(); st.rerun()
    else:
        st.info(f"WORKING: {st.session_state.job['c']}")
        # (Photo/Clockout logic remains same but uses cache-safe saves)
        if 'before_taken' not in st.session_state:
            bf = st.file_uploader("Before Photo", type=['jpg','png','jpeg'])
            if st.button("Continue"):
                if bf:
                    img = Image.open(bf); img.thumbnail((800,800))
                    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70)
                    enc = base64.b64encode(buf.getvalue()).decode()
                    new_p = pd.DataFrame([{"Date": get_mst_time().strftime('%Y-%m-%d'), "User": st.session_state.user, "Client": st.session_state.job['c'], "Unit": str(st.session_state.job['u']), "Type": "Before", "PhotoData": enc}])
                    temp_p = pd.concat([pd_photos, new_p], ignore_index=True)
                    temp_p.to_csv(PATHS["photos"], index=False); push_to_github(PATHS["photos"])
                    st.cache_data.clear()
                st.session_state.before_taken = True; st.rerun()
        else:
            notes = st.text_area("Notes")
            af = st.file_uploader("After Photo", type=['jpg','png','jpeg'])
            if st.button("🏁 FINALIZE", type="primary"):
                if af:
                    img = Image.open(af); img.thumbnail((800,800))
                    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70)
                    enc = base64.b64encode(buf.getvalue()).decode()
                    new_p = pd.DataFrame([{"Date": get_mst_time().strftime('%Y-%m-%d'), "User": st.session_state.user, "Client": st.session_state.job['c'], "Unit": str(st.session_state.job['u']), "Type": "After", "PhotoData": enc}])
                    temp_p = pd.concat([pd_photos, new_p], ignore_index=True)
                    temp_p.to_csv(PATHS["photos"], index=False); push_to_github(PATHS["photos"])
                
                et = get_mst_time()
                new_l = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": et.strftime('%H:%M'), "Date": et.strftime('%Y-%m-%d'), "Notes": notes, "Duration": str(et-st.session_state.start).split(".")[0]}])
                temp_l = pd.concat([ld, new_l], ignore_index=True)
                temp_l.to_csv(PATHS["logs"], index=False); push_to_github(PATHS["logs"])
                
                td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.job['c']), 'Status'] = 'Done'
                td.to_csv(PATHS["tasks"], index=False); push_to_github(PATHS["tasks"])
                
                st.session_state.clear(); st.cache_data.clear(); st.session_state.booted = True; st.rerun()
