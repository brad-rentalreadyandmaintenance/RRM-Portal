import streamlit as st
import pandas as pd
import os

# 1. SETUP
st.set_page_config(page_title="RRM Portal", layout="wide")

# 2. EMERGENCY DATA INIT
if not os.path.exists("data"):
    os.makedirs("data")

def get_data(path, cols):
    if not os.path.exists(path):
        pd.DataFrame(columns=cols).to_csv(path, index=False)
    return pd.read_csv(path)

# 3. LOAD DATA SAFELY
try:
    ud = get_data("data/users.csv", ["User", "PIN", "Rate"])
    cd = get_data("data/clients.csv", ["Client", "Address"])
except Exception as e:
    st.error(f"Data Error: {e}")
    ud = pd.DataFrame(columns=["User", "PIN", "Rate"])
    cd = pd.DataFrame(columns=["Client", "Address"])

# 4. LOGIN LOGIC
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 RRM Portal Login")
    
    # Create user list
    u_list = ["Admin"] + ud['User'].tolist()
    user = st.selectbox("User", u_list)
    pin = st.text_input("PIN", type="password")
    
    if st.button("LOG IN"):
        if user == "Admin" and pin == "0000":
            st.session_state.authenticated = True
            st.session_state.current_user = "Admin"
            st.rerun()
        else:
            # Check tech users
            match = ud[ud['User'] == user]
            if not match.empty and str(pin) == str(match.iloc[0]['PIN']):
                st.session_state.authenticated = True
                st.session_state.current_user = user
                st.rerun()
            else:
                st.error("Invalid PIN")
    st.stop()

# 5. MAIN APP
st.sidebar.write(f"Logged in as: {st.session_state.current_user}")
if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

tabs = st.tabs(["Staff Management", "Client Manager"])

with tabs[0]:
    st.header("👤 Staff Management")
    
    # THE FORM - Guaranteed to show
    with st.form("new_worker_form"):
        st.write("### Add New Worker")
        new_n = st.text_input("Name")
        new_p = st.text_input("PIN")
        new_r = st.number_input("Rate", value=25.0)
        if st.form_submit_button("SAVE WORKER"):
            if new_n and new_p:
                new_row = pd.DataFrame([{"User": new_n, "PIN": new_p, "Rate": new_r}])
                ud = pd.concat([ud, new_row], ignore_index=True)
                ud.to_csv("data/users.csv", index=False)
                st.success(f"Added {new_n}")
                st.rerun()
    
    st.divider()
    st.write("### Current Staff")
    st.dataframe(ud, use_container_width=True)

with tabs[1]:
    st.header("🏢 Client Manager")
    with st.form("new_client"):
        c_name = st.text_input("Client Name")
        c_addr = st.text_input("Address")
        if st.form_submit_button("SAVE CLIENT"):
            new_c = pd.DataFrame([{"Client": c_name, "Address": c_addr}])
            cd = pd.concat([cd, new_c], ignore_index=True)
            cd.to_csv("data/clients.csv", index=False)
            st.success("Client Saved")
            st.rerun()
    st.dataframe(cd, use_container_width=True)
