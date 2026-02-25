import streamlit as st
import pandas as pd
import os, requests, base64, io
from datetime import datetime, timedelta
from PIL import Image

# 1. SETUP
st.set_page_config(page_title="RRM Portal v2.4", layout="wide")
GIT_T, REPO = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("REPO_NAME")
PATHS = {"u": "data/users.csv", "c": "data/clients.csv", "l": "data/logs.csv", "t": "data/tasks.csv", "p": "data/photos.csv", "m": "data/materials.csv"}
if not os.path.exists("data"): os.makedirs("data")

def get_mst(): return datetime.utcnow() - timedelta(hours=7)

def process_image(uploaded_file):
    if not uploaded_file: return None
    img = Image.open(uploaded_file); img.thumbnail((800, 800)); buf = io.BytesIO()
    img.save(buf, format="JPEG"); return base64.b64encode(buf.getvalue()).decode()

# 2. SYNC ENGINE
def sync(path, mode="pull"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {"Authorization": f"token {GIT_T}"}
    try:
        res = requests.get(url, headers=headers)
        if mode == "pull" and res.status_code == 200:
            content = base64.b64decode(res.json()['content']).decode('utf-8')
            with open(path, "w") as f: f.write(content)
        elif mode == "push":
            sha = res.json().get('sha') if res.status_code == 200 else None
            with open(path, "rb") as f: content = base64.b64encode(f.read()).decode("utf-8")
            payload = {"message":f"Update {path}","content":content,"branch":"master"}
            if sha: payload["sha"] = sha
            requests.put(url, headers=headers, json=payload)
    except: pass

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
    return u, c, l, t, ph, mat

ud, cd, ld, td, pd_photos, md = load_data()

# 3. AUTH & URL PERSISTENCE
params = st.query_params
if "user" in params:
    st.session_state.user, st.session_state.role = params["user"], params.get("role", "Tech")

if "user" not in st.session_state:
    st.title("🔐 RRM Login")
    m = st.radio("Portal", ["Admin", "Tech"])
    name = st.selectbox("Name", ud['User']) if m == "Tech" else "Admin"
    pin = st.text_input("PIN", type="password")
    if st.button("Login"):
        stored = "0000" if m == "Admin" else str(ud[ud['User']==name]['PIN'].iloc[0]).zfill(4)
        if pin.zfill(4) == stored:
            st.query_params.update({"user": name, "role": m}); st.rerun()
    st.stop()

# 4. NAVIGATION
view = st.sidebar.radio("Nav", ["Admin", "Field"]) if st.session_state.role == "Admin" else "Field"
if st.sidebar.button("Logout"):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

# 5. ADMIN
if view == "Admin":
    t1, t2, t3 = st.tabs(["Dispatch", "Staff/Clients", "History"])
    with t1:
        with st.form("dsp"):
            tech, clnt, unt = st.selectbox("Tech", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit")
            wo = st.file_uploader("Work Order")
            if st.form_submit_button("Assign"):
                tid = datetime.now().strftime("%Y%m%d%H%M%S")
                pd.concat([td, pd.DataFrame([{"Tech":tech,"Client":clnt,"Unit":unt,"Status":"Pending","TaskID":tid}])]).to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                if wo:
                    pd.concat([pd_photos, pd.DataFrame([{"Date":get_mst().date(),"User":tech,"Client":clnt,"Unit":unt,"Type":"WorkOrder","PhotoData":process_image(wo), "TaskID":tid}])]).to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                st.rerun()
    with t2:
        c1, c2 = st.columns(2)
        with c1: # Staff Edit/Delete
            sm = st.radio("S-Mode", ["Add", "Edit/Delete"])
            st_target = st.selectbox("Select Staff", ud['User']) if sm == "Edit/Delete" else None
            with st.form("sf"):
                sn = st.text_input("Name", value=st_target if st_target else "")
                sp = st.text_input("PIN", value=str(ud[ud['User']==st_target]['PIN'].iloc[0]) if st_target else "")
                sr = st.number_input("Rate", value=float(ud[ud['User']==st_target]['Rate'].iloc[0]) if st_target else 25.0)
                if st.form_submit_button("Save Staff"):
                    if sm == "Edit/Delete": ud = ud[ud['User'] != st_target]
                    pd.concat([ud, pd.DataFrame([{"User":sn,"PIN":sp.zfill(4),"Rate":sr}])]).to_csv(PATHS["u"], index=False); sync(PATHS["u"], "push"); st.rerun()
        with c2: # Client Edit/Delete
            cm = st.radio("C-Mode", ["Add", "Edit/Delete"])
            ct_target = st.selectbox("Select Client", cd['Client']) if cm == "Edit/Delete" else None
            with st.form("cf"):
                cn = st.text_input("Client", value=ct_target if ct_target else "")
                ca = st.text_input("Addr", value=cd[cd['Client']==ct_target]['Address'].iloc[0] if ct_target else "")
                if st.form_submit_button("Save Client"):
                    if cm == "Edit/Delete": cd = cd[cd['Client'] != ct_target]
                    pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])]).to_csv(PATHS["c"], index=False); sync(PATHS["c"], "push"); st.rerun()
    with t3:
        if st.button("🔄 Refresh Data From Cloud"):
            for p in PATHS.values(): sync(p, "pull")
            st.rerun()
        if not ld.empty:
            sel = st.selectbox("Select Job", ld.index, format_func=lambda x: f"{ld.loc[x, 'Date']} - {ld.loc[x, 'Client']}")
            tid = str(ld.loc[sel, 'TaskID'])
            st.subheader("Job Details")
            st.write("**Materials:**", md[md['TaskID']==tid])
            st.write("**Log Entry:**", ld.loc[sel])
            for _, p in pd_photos[pd_photos['TaskID']==tid].iterrows():
                st.image(base64.b64decode(p['PhotoData']), caption=p['Type'])

# 6. FIELD
else:
    if 'job' not in st.session_state:
        st.subheader("Assigned Tasks")
        for i, r in td[(td['Tech']==st.session_state.user)&(td['Status']=="Pending")].iterrows():
            if st.button(f"Start: {r['Client']} (U: {r['Unit']})", key=f"j{i}"):
                st.session_state.job, st.session_state.start = r.to_dict(), get_mst(); st.rerun()
        st.divider()
        is_n = st.checkbox("New Client?")
        m_c = st.text_input("Client Name") if is_n else st.selectbox("Client", ["--"] + cd['Client'].tolist())
        m_u = st.text_input("Unit #")
        if st.button("Begin Work") and m_c != "--":
            st.session_state.job = {"Client":m_c, "Unit":m_u, "TaskID":"M"+datetime.now().strftime("%H%M"), "Tech":st.session_state.user}
            st.session_state.start = get_mst(); st.rerun()
    else:
        st.info(f"Active Job: {st.session_state.job['Client']}")
        # Non-Finalizing Log
        with st.expander("Update Progress (Non-Finalizing)"):
            p_notes = st.text_area("Notes so far", key="p_notes")
            if st.button("Save Draft & Pause"):
                new_l = pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['Client'],"In":st.session_state.start.strftime('%H:%M'),"Out":"PAUSED","Date":get_mst().date(),"Notes":p_notes,"Duration":"Ongoing","TaskID":st.session_state.job['TaskID']}])
                pd.concat([ld, new_l]).to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push")
                del st.session_state.job; st.success("Draft Saved!"); st.rerun()

        if 'photo_step' not in st.session_state:
            up_b = st.file_uploader("Before Photo")
            if st.button("Lock Before Photo") and up_b:
                pd.concat([pd_photos, pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['Client'],"Unit":st.session_state.job['Unit'],"Type":"Before","PhotoData":process_image(up_b), "TaskID":st.session_state.job['TaskID']}])]).to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                st.session_state.photo_step = True; st.rerun()
        else:
            with st.expander("Materials"):
                mi, mp = st.text_input("Item"), st.number_input("Cost", step=0.01)
                if st.button("Add Material"):
                    pd.concat([md, pd.DataFrame([{"TaskID":str(st.session_state.job['TaskID']), "Item":mi, "Price":mp}])]).to_csv(PATHS["m"], index=False); sync(PATHS["m"], "push"); st.success("Added")
            
            f_notes, up_a = st.text_area("Final Notes"), st.file_uploader("After Photo")
            if st.button("🏁 FINISH & CLOSE JOB"):
                if up_a:
                    pd.concat([pd_photos, pd.DataFrame([{"Date":get_mst().date(),"User":st.session_state.user,"Client":st.session_state.job['Client'],"Unit":st.session_state.job['Unit'],"Type":"After","PhotoData":process_image(up_a), "TaskID":st.session_state.job['TaskID']}])]).to_csv(PATHS["p"], index=False); sync(PATHS["p"], "push")
                dur = str(get_mst()-st.session_state.start).split(".")[0]
                pd.concat([ld, pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['Client'],"In":st.session_state.start.strftime('%H:%M'),"Out":get_mst().strftime('%H:%M'),"Date":get_mst().date(),"Notes":f_notes,"Duration":dur, "TaskID":st.session_state.job['TaskID']}])]).to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push")
                td.loc[td['TaskID']==st.session_state.job['TaskID'], 'Status'] = 'Done'
                td.to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push")
                del st.session_state.job; del st.session_state.photo_step; st.rerun()
