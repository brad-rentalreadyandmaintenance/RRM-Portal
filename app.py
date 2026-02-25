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
st.markdown("<style>button {height: 3em !important; font-size: 1.1rem !important;}</style>", unsafe_allow_html=True)

# 2. CONFIG & GITHUB SETTINGS
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
REPO_NAME = st.secrets.get("REPO_NAME")
DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

U_PATH, C_PATH, L_PATH, T_PATH, P_PATH = "data/users.csv", "data/clients.csv", "data/logs.csv", "data/tasks.csv", "data/photos.csv"

# --- TIMEZONE FIX ---
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
            with open(path, "w") as f: f.write(content)
            return True
    except: pass
    return False

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

# 4. BLOCKING STARTUP
if 'booted' not in st.session_state:
    with st.spinner("🔄 Syncing Cloud Data..."):
        for p in [U_PATH, C_PATH, L_PATH, T_PATH, P_PATH]:
            pull_from_github(p)
        time.sleep(1)
    st.session_state.booted = True

# 5. DATA LOADING
def load_data(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    try:
        df = pd.read_csv(path, dtype={'PIN': str, 'Unit': str})
    except:
        df = pd.read_csv(path)
    return df

ud = load_data(U_PATH, ["User", "PIN", "Rate"])
cd = load_data(C_PATH, ["Client", "Address"])
ld = load_data(L_PATH, ["User", "Client", "In", "Out", "Date", "Notes", "Duration"])
td = load_data(T_PATH, ["Tech", "Client", "Unit", "Status"])
pd_photos = load_data(P_PATH, ["Date", "User", "Client", "Unit", "Type", "PhotoData"])

# 6. PHOTO HELPER
def save_photo(user, client, unit, p_type, uploaded_file):
    if uploaded_file:
        img = Image.open(uploaded_file)
        img.thumbnail((800, 800))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=70)
        encoded_string = base64.b64encode(buffer.getvalue()).decode()
        new_photo = pd.DataFrame([{"Date": get_mst_time().strftime('%Y-%m-%d'), "User": user, "Client": client, "Unit": str(unit), "Type": p_type, "PhotoData": encoded_string}])
        global pd_photos
        pd_photos = pd.concat([pd_photos, new_photo], ignore_index=True)
        pd_photos.to_csv(P_PATH, index=False)
        push_to_github(P_PATH)

# 7. AUTHENTICATION
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
        if ud.empty: st.warning("No staff found."); st.stop()
        t_name = st.selectbox("Name", ud['User'].tolist())
        t_pin = st.text_input("PIN", type="password")
        if st.button("Login"):
            actual = str(ud[ud['User'] == t_name].iloc[0]['PIN']).zfill(4)
            if t_pin.strip().zfill(4) == actual:
                st.session_state.update({"auth": True, "role": "Tech", "user": t_name})
                st.rerun()
    st.stop()

# 8. NAVIGATION
view = st.session_state.role if st.session_state.role == "Tech" else st.sidebar.radio("Nav", ["Admin", "Field Portal"])
if st.sidebar.button("Log Out"):
    st.session_state.clear(); st.rerun()

# 9. ADMIN DASHBOARD
if view == "Admin":
    st.title("🛠️ Admin Dashboard")
    t1, t2, t3, t4, t5 = st.tabs(["Dispatch", "Staff", "Clients", "Work History", "Photos & Reports"])
    
    with t1:
        with st.form("dispatch"):
            tech, client, unit = st.selectbox("Tech", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit")
            if st.form_submit_button("Send"):
                new_t = pd.DataFrame([{"Tech":tech,"Client":client,"Unit":str(unit),"Status":"Pending"}])
                td = pd.concat([td, new_t], ignore_index=True); td.to_csv(T_PATH, index=False); push_to_github(T_PATH); st.rerun()
        st.dataframe(td, use_container_width=True)

    with t2:
        col_a, col_b = st.columns(2)
        with col_a:
            with st.form("add_staff"):
                n, p, r = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", 25.0)
                if st.form_submit_button("Add"):
                    ud = pd.concat([ud, pd.DataFrame([{"User":n,"PIN":str(p).zfill(4),"Rate":r}])], ignore_index=True)
                    ud.to_csv(U_PATH, index=False); push_to_github(U_PATH); st.rerun()
        st.dataframe(ud)

    with t3:
        with st.form("add_client"):
            cn, ca = st.text_input("Client"), st.text_input("Address")
            if st.form_submit_button("Add"):
                cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])], ignore_index=True)
                cd.to_csv(C_PATH, index=False); push_to_github(C_PATH); st.rerun()
        st.dataframe(cd)

    with t4:
        st.dataframe(ld, use_container_width=True)

    with t5:
        st.subheader("Photo & Client Report Generator")
        if not ld.empty:
            log_choice = st.selectbox("Select a Job Entry to Report", ld.index, format_func=lambda x: f"{ld.iloc[x]['Date']} - {ld.iloc[x]['Client']} (Unit: {ld.iloc[x]['User']})")
            selected_job = ld.iloc[log_choice]
            
            # Find photos for this job
            job_photos = pd_photos[(pd_photos['Client'] == selected_job['Client']) & (pd_photos['Date'] == selected_job['Date'])]
            
            report_text = f"WORK REPORT\nClient: {selected_job['Client']}\nDate: {selected_job['Date']}\nTechnician: {selected_job['User']}\nWork Conducted: {selected_job['Notes']}\nDuration: {selected_job['Duration']}"
            st.text_area("Email Content (Copy/Paste)", report_text, height=150)
            
            if not job_photos.empty:
                for idx, p_row in job_photos.iterrows():
                    img_bytes = base64.b64decode(p_row['PhotoData'])
                    st.image(img_bytes, caption=f"Photo Type: {p_row['Type']}")
                    st.download_button(label=f"Download {p_row['Type']} Photo", data=img_bytes, file_name=f"{selected_job['Client']}_{p_row['Type']}.jpg", mime="image/jpeg")
            else:
                st.info("No photos found for this specific job date/client.")

# 10. TECHNICIAN PORTAL
else:
    st.title("📱 Technician Portal")
    if 'job' not in st.session_state:
        st.subheader("📌 Assigned Tasks")
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
            st.session_state.job = {"c": m_c, "u": str(m_u), "type": "M"}
            st.session_state.start = get_mst_time(); st.rerun()
    
    else:
        st.info(f"WORKING: {st.session_state.job['c']}")
        if 'before_taken' not in st.session_state:
            st.subheader("📸 Before Photos (Optional)")
            before_file = st.file_uploader("Capture Before Photo", type=['jpg','png','jpeg'], key="before")
            if st.button("Continue to Job"):
                if before_file: save_photo(st.session_state.user, st.session_state.job['c'], st.session_state.job['u'], "Before", before_file)
                st.session_state.before_taken = True; st.rerun()
        else:
            notes = st.text_area("Work Notes")
            st.subheader("📸 After Photos (Optional)")
            after_file = st.file_uploader("Capture After Photo", type=['jpg','png','jpeg'], key="after")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("⌛ PAUSE"):
                    end_t = get_mst_time()
                    new_log = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": end_t.strftime('%H:%M'), "Date": end_t.strftime('%Y-%m-%d'), "Notes": f"[PARTIAL] {notes}", "Duration": str(end_t - st.session_state.start).split(".")[0]}])
                    ld = pd.concat([ld, new_log], ignore_index=True); ld.to_csv(L_PATH, index=False); push_to_github(L_PATH)
                    if st.session_state.job['type'] == "M":
                        new_t = pd.DataFrame([{"Tech": st.session_state.user, "Client": st.session_state.job['c'], "Unit": st.session_state.job['u'], "Status": "Pending"}])
                        td = pd.concat([td, new_t], ignore_index=True); td.to_csv(T_PATH, index=False); push_to_github(T_PATH)
                    st.session_state.clear(); st.session_state.booted = True; st.rerun()
            with c2:
                if st.button("🏁 FINALIZE", type="primary"):
                    if after_file: save_photo(st.session_state.user, st.session_state.job['c'], st.session_state.job['u'], "After", after_file)
                    end_t = get_mst_time()
                    new_log = pd.DataFrame([{"User": st.session_state.user, "Client": st.session_state.job['c'], "In": st.session_state.start.strftime('%H:%M'), "Out": end_t.strftime('%H:%M'), "Date": end_t.strftime('%Y-%m-%d'), "Notes": notes, "Duration": str(end_t - st.session_state.start).split(".")[0]}])
                    ld = pd.concat([ld, new_log], ignore_index=True); ld.to_csv(L_PATH, index=False); push_to_github(L_PATH)
                    td.loc[(td['Tech'] == st.session_state.user) & (td['Client'] == st.session_state.job['c']) & (td['Unit'] == st.session_state.job['u']), 'Status'] = 'Done'
                    td.to_csv(T_PATH, index=False); push_to_github(T_PATH)
                    st.session_state.clear(); st.session_state.booted = True; st.rerun()
