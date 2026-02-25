import streamlit as st
import pandas as pd
import os, requests, base64, io
from datetime import datetime, timedelta
from PIL import Image

# 1. SETUP & STYLES (Fixed Syntax)
st.set_page_config(page_title="RRM Portal", layout="wide")
st.markdown("""
    <style>
    .stButton>button {height: 3.5em; font-weight: bold; width: 100%; border-radius: 8px;}
    .job-card {background: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 10px;}
    </style>
    """, unsafe_allow_html=True)

# 2. CONFIG
GIT_T = st.secrets.get("GITHUB_TOKEN")
REPO = st.secrets.get("REPO_NAME")
PATHS = {"u": "data/users.csv", "c": "data/clients.csv", "l": "data/logs.csv", "t": "data/tasks.csv", "p": "data/photos.csv"}
if not os.path.exists("data"): os.makedirs("data")

def get_mst(): return datetime.utcnow() - timedelta(hours=7)

# 3. SYNC ENGINE
def sync(path, mode="pull"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {"Authorization": f"token {GIT_T}"}
    if mode == "pull":
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content']).decode('utf-8')
                if len(content) > 5:
                    with open(path, "w") as f: f.write(content)
        except: pass
    else:
        if not os.path.exists(path) or os.path.getsize(path) < 5: return
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
    u = pd.read_csv(PATHS["u"], dtype={'PIN': str}) if os.path.exists(PATHS["u"]) else pd.DataFrame(columns=["User", "PIN", "Rate"])
    c = pd.read_csv(PATHS["c"]) if os.path.exists(PATHS["c"]) else pd.DataFrame(columns=["Client", "Address"])
    l = pd.read_csv(PATHS["l"]) if os.path.exists(PATHS["l"]) else pd.DataFrame(columns=["User", "Client", "In", "Out", "Date", "Notes", "Duration"])
    t = pd.read_csv(PATHS["t"], dtype={'Unit': str}) if os.path.exists(PATHS["t"]) else pd.DataFrame(columns=["Tech", "Client", "Unit", "Status"])
    ph = pd.read_csv(PATHS["p"]) if os.path.exists(PATHS["p"]) else pd.DataFrame(columns=["Date", "User", "Client", "Unit", "Type", "PhotoData"])
    if not l.empty: l['Date'] = pd.to_datetime(l['Date']).dt.date
    return u, c, l, t, ph

ud, cd, ld, td, pd_photos = load_data()

# 4. PERSISTENT AUTH
params = st.query_params
if "user" in params:
    st.session_state.update({"auth": True, "user": params["user"], "role": params.get("role", "Tech")})
else:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 RRM Login")
    m = st.radio("Mode", ["Admin", "Tech"])
    if m == "Admin":
        p_in = st.text_input("PIN", type="password")
        if st.button("Login") and p_in == "0000":
            st.query_params.update({"user": "Admin", "role": "Admin"}); st.rerun()
    else:
        name = st.selectbox("Name", ud['User']) if not ud.empty else st.stop()
        p_in = st.text_input("PIN", type="password")
        if st.button("Login"):
            actual = str(ud[ud['User']==name]['PIN'].iloc[0]).zfill(4)
            if p_in.zfill(4) == actual:
                st.query_params.update({"user": name, "role": "Tech"}); st.rerun()
    st.stop()

# 5. NAVIGATION
view = st.session_state.role if st.session_state.role == "Tech" else st.sidebar.radio("Nav", ["Admin", "Field"])
if st.sidebar.button("Logout"): st.query_params.clear(); st.session_state.clear(); st.rerun()

# 6. ADMIN DASHBOARD
if view == "Admin":
    t1, t2, t3, t4 = st.tabs(["Dispatch", "Management", "Work History", "Reports"])
    with t1:
        with st.form("disp"):
            t, cl, u = st.selectbox("Tech", ud['User']), st.selectbox("Client", cd['Client']), st.text_input("Unit")
            if st.form_submit_button("Assign"):
                td = pd.concat([td, pd.DataFrame([{"Tech":t,"Client":cl,"Unit":u,"Status":"Pending"}])])
                td.to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push"); st.rerun()
        st.write(td[td['Status']=="Pending"])
    
    with t2:
        col1, col2 = st.columns(2)
        with col1:
            with st.form("add_s"):
                n, p, r = st.text_input("Name"), st.text_input("PIN"), st.number_input("Rate", 25.0)
                if st.form_submit_button("Add Staff"):
                    ud = pd.concat([ud, pd.DataFrame([{"User":n,"PIN":p.zfill(4),"Rate":r}])])
                    ud.to_csv(PATHS["u"], index=False); sync(PATHS["u"], "push"); st.rerun()
        with col2:
            with st.form("add_c"):
                cn, ca = st.text_input("Client"), st.text_input("Address")
                if st.form_submit_button("Add Client"):
                    cd = pd.concat([cd, pd.DataFrame([{"Client":cn,"Address":ca}])])
                    cd.to_csv(PATHS["c"], index=False); sync(PATHS["c"], "push"); st.rerun()

    with t3:
        st.subheader("Work History")
        dr = st.date_input("Range", [get_mst().date()-timedelta(7), get_mst().date()])
        f_tech = st.multiselect("Filter Tech", ud['User'].unique(), default=ud['User'].unique())
        f_s = st.radio("Status", ["All", "Complete", "Paused"], horizontal=True)
        
        mask = (ld['Date'] >= dr[0]) & (ld['Date'] <= dr[1]) if len(dr)==2 else True
        f_ld = ld[mask & ld['User'].isin(f_tech)].sort_values("Date", ascending=False)
        if f_s != "All": f_ld = f_ld[f_ld['Notes'].str.contains(f"\[{f_s.upper()}\]", na=False)]
        
        # Payroll Logic
        def to_hours(td_str):
            try:
                h, m, s = map(int, td_str.split(':'))
                return h + m/60 + s/3600
            except: return 0
        total_h = f_ld['Duration'].apply(to_hours).sum()
        st.metric("Total Hours for Selection", f"{total_h:.2f} hrs")
        
        st.dataframe(f_ld.style.applymap(lambda x: 'background-color: #d4edda' if '[COMPLETE]' in str(x) else ('background-color: #fff3cd' if '[PAUSED]' in str(x) else ''), subset=['Notes']))

    with t4:
        if not ld.empty:
            sel_i = st.selectbox("Log", ld.index, format_func=lambda x: f"{ld.iloc[x]['Date']} - {ld.iloc[x]['Client']}")
            sel = ld.iloc[sel_i]
            st.write(sel.to_dict())
            ph = pd_photos[(pd_photos['Client']==sel['Client']) & (pd_photos['Date']==str(sel['Date']))]
            for _, p in ph.iterrows(): st.image(base64.b64decode(p['PhotoData']), caption=p['Type'])

# 7. FIELD PORTAL
else:
    if 'job' not in st.session_state:
        st.subheader("Assignments")
        for i, r in td[(td['Tech']==st.session_state.user)&(td['Status']=="Pending")].iterrows():
            if st.button(f"In: {r['Client']} (Unit {r['Unit']})"):
                st.session_state.job = {"c": r['Client'], "u": r['Unit']}; st.session_state.start = get_mst(); st.rerun()
    else:
        st.warning(f"Working: {st.session_state.job['c']}")
        notes = st.text_area("Notes")
        c1, c2 = st.columns(2)
        if c1.button("⌛ PAUSE"):
            dur = str(get_mst()-st.session_state.start).split(".")[0]
            new = pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['c'],"In":st.session_state.start.strftime('%H:%M'),"Out":get_mst().strftime('%H:%M'),"Date":get_mst().date(),"Notes":f"[PAUSED] {notes}","Duration":dur}])
            pd.concat([ld, new]).to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push"); del st.session_state.job; st.rerun()
        if c2.button("🏁 FINALIZE", type="primary"):
            dur = str(get_mst()-st.session_state.start).split(".")[0]
            new = pd.DataFrame([{"User":st.session_state.user,"Client":st.session_state.job['c'],"In":st.session_state.start.strftime('%H:%M'),"Out":get_mst().strftime('%H:%M'),"Date":get_mst().date(),"Notes":f"[COMPLETE] {notes}","Duration":dur}])
            pd.concat([ld, new]).to_csv(PATHS["l"], index=False); sync(PATHS["l"], "push")
            td.loc[(td['Tech']==st.session_state.user)&(td['Client']==st.session_state.job['c']), 'Status'] = 'Done'
            td.to_csv(PATHS["t"], index=False); sync(PATHS["t"], "push"); del st.session_state.job; st.rerun()
