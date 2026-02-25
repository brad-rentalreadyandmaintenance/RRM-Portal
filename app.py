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
    .stButton>button { height: 3.5em; font-weight: bold; width: 100%; border-radius: 8px; }
    .job-card { background: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. SYSTEM SETTINGS
GIT_T = st.secrets.get("GITHUB_TOKEN")
REPO = st.secrets.get("REPO_NAME")
PATHS = {
    "u": "data/users.csv", "c": "data/clients.csv", "l": "data/logs.csv", 
    "t": "data/tasks.csv", "p": "data/photos.csv", "m": "data/materials.csv"
}

if not os.path.exists("data"): os.makedirs("data")

def get_mst(): return datetime.utcnow() - timedelta(hours=7)

def process_image(uploaded_file):
    if not uploaded_file: return None
    img = Image.open(uploaded_file)
    img.thumbnail((800, 800))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()

# 3. SYNC ENGINE
def sync(path, mode="pull"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {"Authorization": f"token {GIT_T}"}
    if mode == "pull":
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8')
                with open(path, "w") as f: f.write(content)
        except: pass
    else:
        if not os.path.exists(path): return
        try:
            res = requests.get(url, headers=headers)
            sha = res.json().get('sha') if res.status_code == 200 else None
            with open(path, "rb") as f: content = base64.b64encode(f.read()).decode("utf-8")
            payload = {"message": f"Sync {path}", "content": content, "branch": "master"}
            if sha: payload["sha"] = sha
            requests.put(url, headers=headers, json=payload)
        except: pass

def load_data():
    for p in PATHS.values(): sync(p, "pull")
    # Define schemas to prevent KeyErrors on first load
    u = pd.read_csv(PATHS["u"], dtype={'PIN': str}) if os.path.exists(PATHS["u"]) else pd.DataFrame(columns=["User", "PIN", "Rate"])
    c = pd.read_csv(PATHS["c"]) if os.path.exists(PATHS["c"]) else pd.DataFrame(columns=["Client", "Address"])
    l = pd.read_csv(PATHS["l"]) if os.path.exists(PATHS["l"]) else pd.DataFrame(columns=["User", "Client", "In", "Out", "Date", "Notes", "Duration", "TaskID"])
    t = pd.read_csv(PATHS["t"], dtype={'Unit': str}) if os.path.exists(PATHS["t"]) else pd.DataFrame(columns=["Tech", "Client", "Unit", "Status", "TaskID"])
    ph = pd.read_csv(PATHS["p"]) if os.path.exists(PATHS["p"]) else pd.DataFrame(columns=["Date", "User", "Client", "Unit", "Type", "PhotoData", "TaskID"])
    mat = pd.read_csv(PATHS["m"]) if os.path.exists(PATHS["m"]) else pd.DataFrame(columns=["TaskID", "Item", "Price"])
    
    # SAFETY: Patch any existing files missing the TaskID column
    for df in [l, t, ph, mat]:
        if 'TaskID' not in df.columns:
            df['TaskID'] = "None"
            
    if not l.empty: 
        l['Date'] = pd.to_datetime(l['Date']).dt.date
    return u, c, l, t, ph, mat

ud, cd, ld, td, pd_photos, md = load_data()

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
    m = st.radio("Portal", ["Admin", "Tech"], key="l_mode")
    name = st.selectbox("Name", ud['User']) if m == "Tech" else "Admin"
    pin = st.text_input("PIN", type="password")
    if st.button("Login"):
        stored = "0000" if m == "Admin" else str(ud[ud['User']==name]['PIN'].iloc[0]).zfill(4)
        if pin.zfill(4) == stored:
            st.query_params.update({"user": name, "role": m}); st.rerun()
    st.stop()

# 5. NAVIGATION
view = st.sidebar.radio("Nav", ["Admin", "Field"], key="nav") if st.session_state.role == "Admin" else "Field"
if st.sidebar.button("Logout"): 
    st.query_params.clear(); st.session_state.clear(); st.rerun()

# 6. ADMIN DASHBOARD
if view == "Admin":
    t1, t2, t3 = st.tabs(["Dispatch", "Management", "History"])
    
    with t1: # DISPATCH LOGIC
        with st.form("dispatch"):
            tech, client, unit = st.selectbox("Tech", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit")
            wo = st.file_uploader("Work Order Image")
            if st.form_submit_button("Assign Job"):
                tid = datetime.now().strftime("%Y%m%d%H%M%S")
                new_t = pd.DataFrame([{"Tech":tech,"Client":client,"Unit":unit,"Status":"Pending","TaskID":tid}])
                pd.concat([td, new_t]).to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                if wo:
                    new_p = pd.DataFrame([{"Date":get_mst().date(),"User":tech,"Client":client,"Unit":unit,"Type":"WorkOrder","PhotoData":process_image(wo), "TaskID":tid}])
                    pd.concat([pd_photos, new_p]).to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                st.rerun()
        st.write("### Active Tasks", td[td['Status']=="Pending"])

    with t2: # FULL STAFF & CLIENT MANAGEMENT
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Manage Staff")
            s_act = st.radio("Action", ["Add", "Edit/Delete"], key="s_r")
            s_target = st.selectbox("Select", ud['User'], key="s_s") if s_act == "Edit/Delete" else ""
            with st.form("staff_form"):
                n = st.text_input("Name", value=s_target if s_target else "")
                p = st.text_input("PIN", value=str(ud[ud['User']==s_target]['PIN'].iloc[0]) if s_target else "")
                r = st.number_input("Rate", value=float(ud[ud['User']==s_target]['Rate'].iloc[0]) if s_target else 25.0)
                if st.form_submit_button("Update Staff"):
                    if s_act == "Edit/Delete": ud = ud[ud['User'] != s_target]
                    ud = pd.concat([ud, pd.DataFrame([{"User":n,"PIN":p.zfill(4),"Rate":r}])])
                    ud.to_csv(PATHS["u"], index=False); sync(PATHS["u"], "push"); st.rerun()
        with c2:
            st.subheader("Manage Clients")
            c_act = st.radio("Action", ["Add", "Edit/Delete"], key="c_r")
            c_target = st.selectbox("Select", cd['Client'], key="c_s") if c_act == "Edit/Delete" else ""
            with st.form("client_form"):
                cn = st.text_input("Client", value=c_target if c_target else "")
                ca = st.text_input("Address", value=cd[cd['Client']==c_target]['Address'].iloc[0] if c_target else "")
                if st.form_submit_button("Update Client"):
                    if c_act == "Edit/Delete": cd = cd[cd['Client'] != c_target]
                    cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])])
                    cd.to_csv(PATHS["c"], index=False); sync(PATHS["c"], "push"); st.rerun()

    with t3: # HISTORY LOGIC
        if not ld.empty:
            sel = st.selectbox("View Log", ld.index, format_func=lambda x: f"{ld.loc[x, 'Date']} - {ld.loc[x, 'Client']} ({ld.loc[x, 'User']})")
            tid = str(ld.loc[sel, 'TaskID'])
            st.write("#### Job Details")
            st.write(md[md['TaskID']==tid]) # Materials
            for _, p in pd_photos[pd_photos['TaskID']==tid].iterrows():
                st.image(base64.b64decode(p['PhotoData']), caption=p['Type'])

# 7. FIELD PORTAL
else:
    if 'job' not in st.session_state:
        st.subheader("Assigned Tasks")
        assigned = td[(td['Tech']==st.session_state.user)&(td['Status']=="Pending")]
        for i, r in assigned.iterrows():
            if st.button(f"Start: {r['Client']} (U: {r['Unit']})", key=f"fjob_{i}"):
                st.session_state.job = r.to_dict(); st.session_state.start = get_mst(); st.rerun()
        
        st.divider()
        st.subheader("Manual/Emergency Entry")
        is_new = st.checkbox("New Client?")
        m_c = st.text_input("Client Name") if is_new else st.selectbox("Client", ["--"] + cd['Client'].tolist())
        m_u = st.text_input("Unit #")
        if st.button("Begin Manual Work"):
            if m_c and m_c != "--":
                tid = "M" + datetime.now().strftime("%Y%m%d%H%M")
                st.session_state.job = {"Client":m_c, "Unit":m_u, "TaskID":tid, "Tech":st.session_state.user}
                st.session_state.start = get_mst(); st.rerun()
    else:
        st.warning(f"Active Job: {st.session_state.job['Client']} (U: {st.session_state.job['Unit']})")
        # WO Expander
        wo_p = pd_photos[(pd_photos['TaskID']==str(st.session_state.job['TaskID'])) & (pd_photos['Type']=="WorkOrder")]
        if not wo_p.empty:
            with st.expander("📄 View Work Order"): st.image(base64.b64decode(wo_p.iloc[0]['PhotoData']))
        
        if 'photo_step' not in st.session_state:
            up_b = st.file_uploader("Upload BEFORE Photo")
            if st.button("Continue"):
                if up_b:
                    new_p = pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['Client'],"Unit":st.session_state.job['Unit'],"Type":"Before","PhotoData":process_image(up_b), "TaskID":st.session_state.job['TaskID']}])
                    pd.concat([pd_photos, new_p]).to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                st.session_state.photo_step = True; st.rerun()
        else:
            with st.expander("Add Used Materials"):
                mi, mp = st.text_input("Material Item"), st.number_input("Cost", step=0.01)
                if st.button("Save Material"):
                    new_m = pd.DataFrame([{"TaskID":str(st.session_state.job['TaskID']), "Item":mi, "Price":mp}])
                    pd.concat([md, new_m]).to_csv(PATHS["m"], index=False); sync(PATHS["m"], "push"); st.success("Added")
            
            notes = st.text_area("Final Work Notes")
            up_a = st.file_uploader("Upload AFTER Photo")
            if st.button("🏁 FINISH & SUBMIT"):
                if up_a:
                    new_p = pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['Client'],"Unit":st.session_state.job['Unit'],"Type":"After","PhotoData":process_image(up_a), "TaskID":st.session_state.job['TaskID']}])
                    pd.concat([pd_photos, new_p]).to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                dur = str(get_mst()-st.session_state.start).split(".")[0]
                new_l = pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['Client'],"In":st.session_state.start.strftime('%H:%M'),"Out":get_mst().strftime('%H:%M'),"Date":get_mst().date(),"Notes":notes,"Duration":dur, "TaskID":st.session_state.job['TaskID']}])
                pd.concat([ld, new_l]).to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push")
                td.loc[td['TaskID']==st.session_state.job['TaskID'], 'Status'] = 'Done'
                td.to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                del st.session_state.job; del st.session_state.photo_step; st.rerun()
