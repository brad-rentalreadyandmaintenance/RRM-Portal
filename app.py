import streamlit as st
import pandas as pd
import os
import requests
import base64
import io
from datetime import datetime, timedelta
from PIL import Image

# 1. PAGE CONFIG & STYLING
st.set_page_config(page_title="RRM Portal", layout="wide")
st.markdown("""
    <style>
    .stButton>button {
        height: 3.5em; 
        font-weight: bold; 
        width: 100%; 
        border-radius: 8px;
    }
    .job-card {
        background: #f0f2f6; 
        padding: 15px; 
        border-radius: 10px; 
        border-left: 5px solid #ff4b4b; 
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# 2. SYSTEM SETTINGS
GIT_T = st.secrets.get("GITHUB_TOKEN")
REPO = st.secrets.get("REPO_NAME")
PATHS = {
    "u": "data/users.csv", 
    "c": "data/clients.csv", 
    "l": "data/logs.csv", 
    "t": "data/tasks.csv", 
    "p": "data/photos.csv"
}

if not os.path.exists("data"): 
    os.makedirs("data")

def get_mst(): 
    return datetime.utcnow() - timedelta(hours=7)

# 3. GITHUB SYNC ENGINE
def sync(path, mode="pull"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {"Authorization": f"token {GIT_T}"}
    
    if mode == "pull":
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8')
                if len(content) > 5:
                    with open(path, "w") as f: 
                        f.write(content)
        except: 
            pass
    else:
        if not os.path.exists(path) or os.path.getsize(path) < 5: 
            return
        try:
            res = requests.get(url, headers=headers)
            sha = res.json().get('sha') if res.status_code == 200 else None
            with open(path, "rb") as f: 
                content = base64.b64encode(f.read()).decode("utf-8")
            
            payload = {
                "message": f"Sync {path}", 
                "content": content, 
                "branch": "master"
            }
            if sha: 
                payload["sha"] = sha
            requests.put(url, headers=headers, json=payload)
        except: 
            pass

def load_data():
    for p in PATHS.values(): 
        sync(p, "pull")
    
    u = pd.read_csv(PATHS["u"], dtype={'PIN': str}) if os.path.exists(PATHS["u"]) else pd.DataFrame(columns=["User", "PIN", "Rate"])
    c = pd.read_csv(PATHS["c"]) if os.path.exists(PATHS["c"]) else pd.DataFrame(columns=["Client", "Address"])
    l = pd.read_csv(PATHS["l"]) if os.path.exists(PATHS["l"]) else pd.DataFrame(columns=["User", "Client", "In", "Out", "Date", "Notes", "Duration"])
    t = pd.read_csv(PATHS["t"], dtype={'Unit': str}) if os.path.exists(PATHS["t"]) else pd.DataFrame(columns=["Tech", "Client", "Unit", "Status"])
    ph = pd.read_csv(PATHS["p"]) if os.path.exists(PATHS["p"]) else pd.DataFrame(columns=["Date", "User", "Client", "Unit", "Type", "PhotoData"])
    
    if not l.empty: 
        l['Date'] = pd.to_datetime(l['Date']).dt.date
    return u, c, l, t, ph

ud, cd, ld, td, pd_photos = load_data()

# 4. AUTHENTICATION
params = st.query_params
if "user" in params:
    st.session_state.auth = True
    st.session_state.user = params["user"]
    st.session_state.role = params.get("role", "Tech")
else:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Login")
    m = st.radio("Select Portal Type", ["Admin Portal", "Technician Portal"], key="login_mode_radio")
    
    if m == "Admin Portal":
        p_in = st.text_input("Enter Admin PIN", type="password", key="admin_pin_input")
        if st.button("Enter Admin System", key="admin_login_btn") and p_in == "0000":
            st.query_params.update({"user": "Admin", "role": "Admin"})
            st.rerun()
    else:
        if ud.empty:
            st.error("No staff found in database.")
            st.stop()
        name = st.selectbox("Select Your Name", ud['User'], key="tech_name_select")
        p_in = st.text_input("Enter Your PIN", type="password", key="tech_pin_input")
        if st.button("Clock In to System", key="tech_login_btn"):
            actual = str(ud[ud['User']==name]['PIN'].iloc[0]).zfill(4)
            if p_in.zfill(4) == actual:
                st.query_params.update({"user": name, "role": "Tech"})
                st.rerun()
            else:
                st.error("Invalid PIN")
    st.stop()

# 5. SIDEBAR NAVIGATION
st.sidebar.title(f"User: {st.session_state.user}")
if st.session_state.role == "Admin":
    view = st.sidebar.radio("Navigation", ["Admin Dashboard", "Field Portal"], key="sidebar_nav_radio")
else:
    view = "Field Portal"

if st.sidebar.button("Log Out / Reset", key="logout_btn"): 
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()

# 6. ADMIN DASHBOARD
if view == "Admin Dashboard":
    t1, t2, t3 = st.tabs(["Dispatch Work", "Staff/Client Management", "Work History & Logs"])
    
    with t1:
        with st.form("dispatch_form", clear_on_submit=True):
            t = st.selectbox("Assign Technician", ud['User'], key="disp_tech")
            cl = st.selectbox("Select Client", cd['Client'], key="disp_client")
            u = st.text_input("Unit #", key="disp_unit")
            if st.form_submit_button("Send to Field"):
                new_task = pd.DataFrame([{"Tech":t,"Client":cl,"Unit":u,"Status":"Pending"}])
                td = pd.concat([td, new_task])
                td.to_csv(PATHS["t"], index=False)
                sync(PATHS["t"], "push")
                st.rerun()
        st.write("### Active Assignments")
        st.dataframe(td[td['Status']=="Pending"], use_container_width=True)

    with t2:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Manage Staff")
            s_act = st.radio("Staff Task", ["Add New", "Edit/Delete Existing"], key="staff_logic_radio")
            s_target = st.selectbox("Choose Staff Member", ud['User'], key="staff_edit_select") if s_act == "Edit/Delete Existing" else ""
            with st.form("staff_mgmt_form"):
                n = st.text_input("Full Name", value=s_target if s_target else "")
                p = st.text_input("Access PIN", value=str(ud[ud['User']==s_target]['PIN'].iloc[0]) if s_target else "")
                r = st.number_input("Hourly Rate", value=float(ud[ud['User']==s_target]['Rate'].iloc[0]) if s_target else 25.0)
                if st.form_submit_button("Commit Staff Changes"):
                    if s_act == "Edit/Delete Existing": ud = ud[ud['User'] != s_target]
                    ud = pd.concat([ud, pd.DataFrame([{"User":n,"PIN":p.zfill(4),"Rate":r}])])
                    ud.to_csv(PATHS["u"], index=False); sync(PATHS["u"], "push"); st.rerun()

        with c2:
            st.subheader("Manage Clients")
            c_act = st.radio("Client Task", ["Add New", "Edit/Delete Existing"], key="client_logic_radio")
            c_target = st.selectbox("Choose Client", cd['Client'], key="client_edit_select") if c_act == "Edit/Delete Existing" else ""
            with st.form("client_mgmt_form"):
                cn = st.text_input("Client/Site Name", value=c_target if c_target else "")
                ca = st.text_input("Physical Address", value=cd[cd['Client']==c_target]['Address'].iloc[0] if c_target else "")
                if st.form_submit_button("Commit Client Changes"):
                    if c_act == "Edit/Delete Existing": cd = cd[cd['Client'] != c_target]
                    cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])])
                    cd.to_csv(PATHS["c"], index=False); sync(PATHS["c"], "push"); st.rerun()

    with t3:
        dr = st.date_input("Filter by Date", [get_mst().date()-timedelta(7), get_mst().date()], key="history_date_picker")
        f_tech = st.multiselect("Filter by Technician", ud['User'].unique(), default=ud['User'].unique(), key="history_tech_filter")
        mask = (ld['Date'] >= dr[0]) & (ld['Date'] <= dr[1]) if len(dr)==2 else True
        f_ld = ld[mask & ld['User'].isin(f_tech)].sort_values("Date", ascending=False)
        
        def to_h(s):
            try:
                h,m,s = map(int, s.split(':'))
                return h + m/60 + s/3600
            except: return 0
        st.metric("Total Billable Hours", f"{f_ld['Duration'].apply(to_h).sum():.2f}")
        st.dataframe(f_ld, use_container_width=True)
        
        if not f_ld.empty:
            sel_idx = st.selectbox("Select Log Entry to View Photos", f_ld.index, key="history_row_select")
            det = f_ld.loc[sel_idx]
            ph = pd_photos[(pd_photos['Client']==det['Client']) & (pd_photos['Date']==str(det['Date']))]
            for _, p in ph.iterrows():
                st.image(base64.b64decode(p['PhotoData']), caption=f"{p['Type']} - {p['Unit']}")

# 7. FIELD PORTAL
else:
    if 'job' not in st.session_state:
        st.subheader("Your Assigned Jobs")
        assigned_tasks = td[(td['Tech']==st.session_state.user)&(td['Status']=="Pending")]
        for i, r in assigned_tasks.iterrows():
            if st.button(f"Start: {r['Client']} (Unit {r['Unit']})", key=f"job_btn_{i}"):
                st.session_state.job = {"c": r['Client'], "u": r['Unit'], "m": "D"}
                st.session_state.start = get_mst()
                st.rerun()
        
        st.divider()
        st.subheader("Manual / Emergency Entry")
        is_new = st.checkbox("New Client/Not on List", key="manual_check")
        m_c = st.text_input("New Client Name", key="manual_client_in") if is_new else st.selectbox("Select Existing Client", ["--"] + cd['Client'].tolist(), key="manual_client_sel")
        m_u = st.text_input("Unit #", key="manual_unit_in")
        if st.button("Begin Manual Shift", key="manual_start_btn"):
            if m_c and m_c != "--":
                st.session_state.job = {"c": m_c, "u": m_u, "m": "M"}
                st.session_state.start = get_mst()
                st.rerun()
    else:
        st.warning(f"Currently Working: {st.session_state.job['c']}")
        if 'photo_step' not in st.session_state:
            up = st.file_uploader("Upload Before Photo", key="before_photo_up")
            if st.button("Continue to Work", key="before_photo_done"):
                if up:
                    img = Image.open(up); img.thumbnail((800,800)); buf = io.BytesIO()
                    img.save(buf, format="JPEG"); enc = base64.b64encode(buf.getvalue()).decode()
                    new_p = pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['c'],"Unit":st.session_state.job['u'],"Type":"Before","PhotoData":enc}])
                    pd_photos = pd.concat([pd_photos, new_p])
                    pd_photos.to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                st.session_state.photo_step = True
                st.rerun()
        else:
            n = st.text_area("Work Notes / Description", key="job_notes_input")
            up2 = st.file_uploader("Upload After Photo", key="after_photo_up")
            c1, c2 = st.columns(2)
            if c1.button("⌛ PAUSE WORK", key="pause_btn"):
                dur = str(get_mst()-st.session_state.start).split(".")[0]
                new_l = pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['c'],"In":st.session_state.start.strftime('%H:%M'),"Out":get_mst().strftime('%H:%M'),"Date":get_mst().date(),"Notes":f"[PAUSED] {n}","Duration":dur}])
                pd.concat([ld, new_l]).to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push")
                if st.session_state.job["m"] == "M":
                    pd.concat([td, pd.DataFrame([{"Tech":st.session_state.user,"Client":st.session_state.job['c'],"Unit":st.session_state.job['u'],"Status":"Pending"}])]).to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                del st.session_state.job; del st.session_state.photo_step; st.rerun()
            if c2.button("🏁 FINISH JOB", type="primary", key="finish_btn"):
                if up2:
                    img = Image.open(up2); img.thumbnail((800,800)); buf = io.BytesIO()
                    img.save(buf, format="JPEG"); enc = base64.b64encode(buf.getvalue()).decode()
                    new_p = pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['c'],"Unit":st.session_state.job['u'],"Type":"After","PhotoData":enc}])
                    pd_photos = pd.concat([pd_photos, new_p])
                    pd_photos.to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                dur = str(get_mst()-st.session_state.start).split(".")[0]
                new_l = pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['c'],"In":st.session_state.start.strftime('%H:%M'),"Out":get_mst().strftime('%H:%M'),"Date":get_mst().date(),"Notes":f"[COMPLETE] {n}","Duration":dur}])
                pd.concat([ld, new_l]).to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push")
                td.loc[(td['Tech']==st.session_state.user)&(td['Client']==st.session_state.job['c']), 'Status'] = 'Done'
                td.to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                del st.session_state.job; del st.session_state.photo_step; st.rerun()
