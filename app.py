# app.py - 社區投票系統（僅允許 QR Code 連結進入）
import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
import sqlite3
import json
from datetime import datetime, timedelta
import pytz
from urllib.parse import urlencode

# ---------- 基本設定 ----------
st.set_page_config(page_title="社區投票系統", layout="wide")
TZ = pytz.timezone("Asia/Taipei")

DB_VOTES = "votes.db"
DB_SETTINGS = "settings.db"
ISSUES_FILE = "issues.xlsx"
UNITS_FILE = "units.xlsx"
ADMIN_CONFIG = "admin_config.json"

# ---------- 初始化 ----------
def init_votes_db():
    conn = sqlite3.connect(DB_VOTES)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        household TEXT,
        issue TEXT,
        choice TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit(); conn.close()

def init_settings_db():
    conn = sqlite3.connect(DB_SETTINGS)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        end_time TEXT,
        active INTEGER DEFAULT 1
    )""")
    conn.commit(); conn.close()

init_votes_db(); init_settings_db()

def load_admin_accounts():
    if not os.path.exists(ADMIN_CONFIG): return {}
    with open(ADMIN_CONFIG, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}

def add_vote(household, issue, choice):
    conn = sqlite3.connect(DB_VOTES)
    c = conn.cursor()
    c.execute("INSERT INTO votes (household, issue, choice, created_at) VALUES (?,?,?,?)",
              (household, issue, choice, datetime.now(TZ).isoformat()))
    conn.commit(); conn.close()

def get_all_votes_df():
    conn = sqlite3.connect(DB_VOTES)
    df = pd.read_sql_query("SELECT * FROM votes", conn)
    conn.close(); return df

def household_has_voted(household):
    conn = sqlite3.connect(DB_VOTES)
    c = conn.cursor()
    c.execute("SELECT COUNT(1) FROM votes WHERE household=?", (household,))
    r = c.fetchone(); conn.close()
    return r and r[0] > 0

def add_setting(end_time_iso):
    conn = sqlite3.connect(DB_SETTINGS)
    c = conn.cursor()
    c.execute("INSERT INTO settings (end_time, active) VALUES (?,1)", (end_time_iso,))
    conn.commit(); conn.close()

def get_latest_setting():
    conn = sqlite3.connect(DB_SETTINGS)
    c = conn.cursor()
    c.execute("SELECT end_time, active FROM settings ORDER BY id DESC LIMIT 1")
    row = c.fetchone(); conn.close()
    if row:
        try: return datetime.fromisoformat(row[0]), bool(row[1])
        except: return None, bool(row[1])
    return None, True

def update_setting_active(active):
    conn = sqlite3.connect(DB_SETTINGS)
    c = conn.cursor()
    c.execute("UPDATE settings SET active=? WHERE id=(SELECT id FROM settings ORDER BY id DESC LIMIT 1)",
              (int(active),))
    conn.commit(); conn.close()

def generate_qr_png_bytes(url):
    img = qrcode.make(url)
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return buf.getvalue()

def generate_qr_zip_from_units(base_url, units_df):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, r in units_df.iterrows():
            unit = str(r["戶號"])
            url = f"{base_url}?unit={unit}"
            png = generate_qr_png_bytes(url)
            zf.writestr(f"{unit}.png", png)
    buf.seek(0); return buf.getvalue()

def load_saved_issues():
    if os.path.exists(ISSUES_FILE):
        try:
            df = pd.read_excel(ISSUES_FILE)
            if "議題" in df.columns:
                return df["議題"].dropna().astype(str).tolist(), df
        except: pass
    return [], None

def load_saved_units():
    if os.path.exists(UNITS_FILE):
        try:
            df = pd.read_excel(UNITS_FILE)
            if "戶號" in df.columns: return df
        except: pass
    return None

# ---------- 網址參數 ----------
try: query_params = st.experimental_get_query_params()
except: query_params = {}

is_admin = str(query_params.get("admin", ["false"])[0]).lower() == "true"
戶號參數 = query_params.get("unit", [None])[0]

if "page" not in st.session_state:
    st.session_state.page = "home"
if is_admin: st.session_state.page = "admin_login"
if 戶號參數: 
    st.session_state.page = "voter"
    st.session_state.unit = 戶號參數

# ---------- 首頁 ----------
st.title("🏘️ 社區投票系統")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🏠 住戶投票"):
        st.session_state.page = "voter"
with col2:
    if st.button("🔐 管理員登入"):
        st.session_state.page = "admin_login"
with col3:
    if st.button("📋 管理後台"):
        st.session_state.page = "admin_login" if not st.session_state.get("logged_in_admin") else "admin"

st.markdown("---")

# ---------- 管理員登入 ----------
admin_accounts = load_admin_accounts()
if st.session_state.page == "admin_login":
    st.header("🔐 管理員登入")
    u = st.text_input("帳號")
    p = st.text_input("密碼", type="password")
    if st.button("登入"):
        if u in admin_accounts and admin_accounts[u] == p:
            st.session_state.logged_in_admin = u
            st.session_state.page = "admin"
            st.success("登入成功")
        else:
            st.error("帳號或密碼錯誤")

# ---------- 管理後台 ----------
elif st.session_state.page == "admin":
    if not st.session_state.get("logged_in_admin"):
        st.warning("請先登入"); st.session_state.page = "admin_login"; st.stop()
    st.header("📊 管理後台")
    st.write(f"登入帳號：{st.session_state.logged_in_admin}")
    st.markdown("---")

    # 上傳議題
    st.subheader("📋 上傳議題清單（需欄位「議題」）")
    up_issues = st.file_uploader("上傳議題", type=["xlsx"])
    if up_issues:
        df = pd.read_excel(up_issues)
        if "議題" not in df.columns: st.error("缺少「議題」欄位")
        else:
            df.to_excel(ISSUES_FILE, index=False)
            st.success(f"已儲存 {df.shape[0]} 題議題")
    issues_list, _ = load_saved_issues()
    if issues_list: [st.write(f"{i+1}. {v}") for i,v in enumerate(issues_list)]
    st.markdown("---")

    # 上傳住戶
    st.subheader("🏠 上傳住戶清單（需欄位「戶號」）")
    up_units = st.file_uploader("上傳住戶清單", type=["xlsx"])
    if up_units:
        dfu = pd.read_excel(up_units)
        if "戶號" not in dfu.columns: st.error("缺少「戶號」欄位")
        else:
            dfu.to_excel(UNITS_FILE, index=False)
            st.success(f"已儲存 {dfu.shape[0]} 戶資料")
    dfu = load_saved_units()
    if dfu is not None:
        url_base = st.text_input("網站基本URL", value="https://smartvoteapp.onrender.com")
        if st.button("📦 產生QR Code ZIP"):
            data = generate_qr_zip_from_units(url_base, dfu)
            st.download_button("下載 QR Code 壓縮包", data=data, file_name="QRcodes.zip", mime="application/zip")
    st.markdown("---")

    # 投票設定
    st.subheader("⏰ 投票截止時間")
    end, active = get_latest_setting()
    if end: st.info(f"目前截止時間：{end.astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    sel = st.selectbox("選擇時間(分鐘)", [5,10,15,20,25,30], index=2)
    if st.button("設定截止"):
        et = datetime.now(TZ) + timedelta(minutes=int(sel))
        add_setting(et.isoformat())
        st.success(f"已設定至 {et.strftime('%Y-%m-%d %H:%M:%S')}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⏹ 暫停投票"):
            update_setting_active(0); st.warning("已暫停")
    with c2:
        if st.button("▶️ 開啟投票"):
            update_setting_active(1); st.success("已開啟")

    st.markdown("---")

    # 統計結果
    st.subheader("📈 投票結果統計")
    votes = get_all_votes_df()
    dfu = load_saved_units()
    total = dfu.shape[0] if dfu is not None else 0
    if votes.empty:
        st.info("尚無資料")
    else:
        issues_list, _ = load_saved_issues()
        if not issues_list: issues_list = sorted(votes["issue"].unique().tolist())
        rows = []
        for i in issues_list:
            d = votes[votes["issue"] == i]
            agree = (d["choice"] == "同意").sum()
            disagree = (d["choice"] == "不同意").sum()
            voted = d["household"].nunique()
            notvote = total - voted if total>0 else 0
            agree_r = round(agree/(agree+disagree)*100 if (agree+disagree)>0 else 0,2)
            disagree_r = round(disagree/(agree+disagree)*100 if (agree+disagree)>0 else 0,2)
            rows.append({"議題":i,"同意人數":agree,"不同意人數":disagree,"未投票戶":notvote,
                         "同意比例(%)":agree_r,"不同意比例(%)":disagree_r})
            st.markdown(f"#### 🗳️ {i}")
            chart_df = pd.DataFrame({"人數":[agree,disagree]}, index=["同意","不同意"])
            st.bar_chart(chart_df)
        dfres = pd.DataFrame(rows)
        st.dataframe(dfres, use_container_width=True)
        csv = dfres.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 下載結果 CSV", data=csv, file_name="投票統計.csv", mime="text/csv")

    if st.button("登出"):
        st.session_state.logged_in_admin=None
        st.session_state.page="home"
        st.success("已登出")

# ---------- 投票頁（僅允許QR Code進入） ----------
elif st.session_state.page == "voter":
    unit = st.session_state.get("unit", None)
    if not unit:
        st.error("❌ 無法辨識戶號，請使用正確的 QR Code 連結進入。")
        st.stop()
    st.info(f"🏠 戶號：{unit}")
    end, active = get_latest_setting()
    now = datetime.now(TZ)
    if not active:
        st.warning("投票尚未開啟")
    elif end and now > end:
        st.error("⏰ 投票已截止")
    else:
        issues, _ = load_saved_issues()
        if not issues:
            st.warning("尚無議題，請稍後再試")
        elif household_has_voted(unit):
            st.info("您已完成投票，感謝您的參與。")
        else:
            st.subheader("🗳️ 投票表單")
            with st.form("vote_form"):
                selects = {}
                for i in issues:
                    selects[i] = st.radio(i, ["同意","不同意"])
                ok = st.form_submit_button("送出")
                if ok:
                    for i,c in selects.items():
                        add_vote(unit,i,c)
                    st.success("✅ 已完成投票，感謝您的參與！")
