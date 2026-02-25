import streamlit as st
import pandas as pd
import os
import requests
import base64
import io
from datetime import datetime, timedelta
from PIL import Image

# 1. PAGE CONFIG & UI
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
    "u": "data/users.csv", 
    "c": "data/clients.csv", 
    "l": "data/logs.csv", 
    "t": "data/tasks.csv", 
    "p": "data/photos.csv", 
    "m": "data/materials.csv"
}

if not os.path.exists("data"): 
    os.makedirs("data")

def get_mst(): 
    return datetime.utcnow() - timedelta(hours=7)

def process_image(uploaded_file):
    if not uploaded_file: return None
    img = Image.open(uploaded_file)
    img.thumbnail((800, 800))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()

# 3. ROBUST SYNC ENGINE (Handles SHA Versioning)
def sync(path, mode="pull"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {"Authorization": f"token {GIT_T}"}
    try:
        res = requests.get(url, headers=headers)
        if mode == "pull":
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8')
                with open(path, "w") as f: f.write(content)
        else:
            if not os.path.exists(path): return
            sha = res.json().get('sha') if res.status_code == 200 else None
            with open(path, "rb") as f: 
                content = base64.b64encode(f.read()).decode("utf-8")
            payload = {"message": f"Push {path}", "content": content, "branch": "master"}
            if sha: payload["sha"] = sha
            requests.put(url, headers=headers, json=payload)
    except: 
        pass

def load_data():
    for p in PATHS.values(): sync(p, "pull")
    u = pd.read_csv(PATHS["u"], dtype={'PIN': str}) if os.path.exists(PATHS["u"]) else pd.DataFrame(columns=["User", "PIN", "Rate"])
    c = pd.read_csv(PATHS["c"]) if os.path.exists(PATHS["c"]) else pd.DataFrame(columns=["Client", "Address"])
    l = pd.read_csv(PATHS["l"]) if os.path.exists(PATHS["l"]) else pd.DataFrame(columns=["User", "Client", "In", "Out", "Date", "Notes", "Duration", "TaskID"])
    t = pd.read_csv(PATHS["t"], dtype={'Unit': str}) if os.path.exists(PATHS["t"]) else pd.DataFrame(columns=["Tech", "Client", "Unit", "Status", "TaskID"])
    ph = pd.read_csv(PATHS["p"]) if os.path.exists(PATHS["p"]) else pd.DataFrame(columns=["Date", "User", "Client", "Unit", "Type", "PhotoData", "TaskID"])
    mat = pd.read_csv(PATHS["m"]) if os.path.exists(PATHS["m"]) else pd.DataFrame(columns=["TaskID", "Item", "Price"])
    
    for df in [l, t, ph, mat]:
        if 'TaskID' not in df.columns: df['TaskID'] = "None"
            
    if not l.empty: 
        l['Date'] = pd.to_datetime(l['Date']).dt.date
    return u, c, l, t, ph, mat

ud, cd, ld, td, pd_photos, md = load_data()

# 4. AUTHENTICATION
if "user" not in st.session_state:
    st.title("🔐 RRM Login")
    m = st.radio("Portal", ["Admin", "Tech"])
    name = st.selectbox("Name", ud['User']) if m == "Tech" else "Admin"
    pin = st.text_input("PIN", type="password")
    if st.button("Login"):
        stored = "0000" if m == "Admin" else str(ud[ud['User']==name]['PIN'].iloc[0]).zfill(4)
        if pin.zfill(4) == stored:
            st.session_state.user, st.session_state.role = name, m
            st.rerun()
    st.stop()

# 5. NAVIGATION
view = st.sidebar.radio("Nav", ["Admin", "Field"]) if st.session_state.role == "Admin" else "Field"
if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

# 6. ADMIN DASHBOARD
if view == "Admin":
    t1, t2, t3 = st.tabs(["Dispatch", "Management", "History"])
    
    with t1: # DISPATCH
        with st.form("dispatch"):
            tech, client, unit = st.selectbox("Tech", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit")
            wo = st.file_uploader("Work Order Image")
            if st.form_submit_button("Assign"):
                tid = datetime.now().strftime("%Y%m%d%H%M%S")
                new_task = pd.DataFrame([{"Tech":tech,"Client":client,"Unit":unit,"Status":"Pending","TaskID":tid}])
                td = pd.concat([td, new_task])
                td.to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                if wo:
                    new_photo = pd.DataFrame([{"Date":get_mst().date(),"User":tech,"Client":client,"Unit":unit,"Type":"WorkOrder","PhotoData":process_image(wo), "TaskID":tid}])
                    pd_photos = pd.concat([pd_photos, new_photo])
                    pd_photos.to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                st.rerun()
        st.write("### Pending Tasks", td[td['Status']=="Pending"])

    with t2: # FULL RESTORE: MANAGEMENT
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Staff")
            s_mode = st.radio("Staff Action", ["Add", "Edit/Delete"])
            s_target = st.selectbox("Select Staff", ud['User']) if s_mode == "Edit/Delete" else None
            with st.form("staff_f"):
                sn = st.text_input("Name", value=s_target if s_target else "")
                sp = st.text_input("PIN", value=str(ud[ud['User']==s_target]['PIN'].iloc[0]) if s_target else "")
                sr = st.number_input("Rate", value=float(ud[ud['User']==s_target]['Rate'].iloc[0]) if s_target else 25.0)
                if st.form_submit_button("Save Staff"):
                    if s_mode == "Edit/Delete": ud = ud[ud['User'] != s_target]
                    ud = pd.concat([ud, pd.DataFrame([{"User":sn,"PIN":sp.zfill(4),"Rate":sr}])])
                    ud.to_csv(PATHS["u"], index=False); sync(PATHS["u"], "push"); st.rerun()
        with c2:
            st.subheader("Clients")
            c_mode = st.radio("Client Action", ["Add", "Edit/Delete"])
            c_target = st.selectbox("Select Client", cd['Client']) if c_mode == "Edit/Delete" else None
            with st.form("client_f"):
                cn = st.text_input("Client", value=c_target if c_target else "")
                ca = st.text_input("Address", value=cd[cd['Client']==c_target]['Address'].iloc[0] if c_target else "")
                if st.form_submit_button("Save Client"):
                    if c_mode == "Edit/Delete": cd = cd[cd['Client'] != c_target]
                    cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])])
                    cd.to_csv(PATHS["c"], index=False); sync(PATHS["c"], "push"); st.rerun()

    with t3: # HISTORY & MATERIALS VIEW
        if not ld.empty:
            sel = st.selectbox("Log", ld.index, format_func=lambda x: f"{ld.loc[x, 'Date']} - {ld.loc[x, 'Client']}")
            job_tid = str(ld.loc[sel, 'TaskID'])
            st.write("#### Materials Used")
            st.table(md[md['TaskID']==job_tid])
            st.write("#### Job Photos")
            for _, p in pd_photos[pd_photos['TaskID']==job_tid].iterrows():
                st.image(base64.b64decode(p['PhotoData']), caption=p['Type'])

# 7. FIELD PORTAL (FULL TECH WORKFLOW)
else:
    if 'job' not in st.session_state:
        st.subheader("Assigned Tasks")
        assigned = td[(td['Tech']==st.session_state.user)&(td['Status']=="Pending")]
        for i, r in assigned.iterrows():
            if st.button(f"Start: {r['Client']} (U: {r['Unit']})", key=f"job_{i}"):
                st.session_state.job = r.to_dict(); st.session_state.start = get_mst(); st.rerun()
        
        st.divider()
        st.subheader("Manual/Emergency Entry")
        m_c = st.selectbox("Client", ["--"] + cd['Client'].tolist())
        m_u = st.text_input("Unit #")
        if st.button("Begin Manual Work"):
            if m_c != "--":
                tid = "M" + datetime.now().strftime("%Y%m%d%H%M")
                st.session_state.job = {"Client":m_c, "Unit":m_u, "TaskID":tid, "Tech":st.session_state.user}
                st.session_state.start = get_mst(); st.rerun()
    else:
        st.warning(f"Active Job: {st.session_state.job['Client']}")
        # Show Work Order
        wo_p = pd_photos[(pd_photos['TaskID']==str(st.session_state.job['TaskID'])) & (pd_photos['Type']=="WorkOrder")]
        if not wo_p.empty:
            with st.expander("📄 View Work Order"): st.image(base64.b64decode(wo_p.iloc[0]['PhotoData']))
        
        if 'photo_step' not in st.session_state:
            up_b = st.file_uploader("Before Photo")
            if st.button("Continue"):
                if up_b:
                    new_p = pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['Client'],"Unit":st.session_state.job['Unit'],"Type":"Before","PhotoData":process_image(up_b), "TaskID":st.session_state.job['TaskID']}])
                    pd_photos = pd.concat([pd_photos, new_p])
                    pd_photos.to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                st.session_state.photo_step = True; st.rerun()
        else:
            with st.expander("Add Materials/Costs"):
                mi, mp = st.text_input("Item"), st.number_input("Cost", step=0.01)
                if st.button("Add to Job"):
                    new_m = pd.DataFrame([{"TaskID":str(st.session_state.job['TaskID']), "Item":mi, "Price":mp}])
                    md = pd.concat([md, new_m])
                    md.to_csv(PATHS["m"], index=False); sync(PATHS["m"], "push"); st.success("Added")
            
            notes = st.text_area("Work Performed Notes")
            up_a = st.file_uploader("After Photo")
            if st.button("🏁 FINISH & CLOCK OUT"):
                if up_a:
                    new_p = pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['Client'],"Unit":st.session_state.job['Unit'],"Type":"After","PhotoData":process_image(up_a), "TaskID":st.session_state.job['TaskID']}])
                    pd_photos = pd.concat([pd_photos, new_p])
                    pd_photos.to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                
                dur = str(get_mst()-st.session_state.start).split(".")[0]
                new_log = pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['Client'],"In":st.session_state.start.strftime('%H:%M'),"Out":get_mst().strftime('%H:%M'),"Date":get_mst().date(),"Notes":notes,"Duration":dur, "TaskID":st.session_state.job['TaskID']}])
                ld = pd.concat([ld, new_log])
                ld.to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push")
                
                td.loc[td['TaskID']==st.session_state.job['TaskID'], 'Status'] = 'Done'
                td.to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                
                del st.session_state.job
                del st.session_state.photo_step
                st.rerun()
