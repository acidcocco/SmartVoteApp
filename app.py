# app.py - SmartVoteApp（帳號密碼外部設定 + 自動QR + 修正 query_params）
import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
import sqlite3
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode
from streamlit_autorefresh import st_autorefresh
import pytz
import plotly.express as px
from PIL import Image, ImageDraw, ImageFont

# ==============================
# 基本設定
# ==============================
BASE_URL = "https://smartvoteapp.onrender.com"
DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "votes.db")
CONFIG_PATH = "config.json"
os.makedirs(DATA_DIR, exist_ok=True)
TZ = pytz.timezone("Asia/Taipei")

# ==============================
# 讀取外部設定（config.json）
# ==============================
if not os.path.exists(CONFIG_PATH):
    st.error("❌ 找不到設定檔 config.json，請建立並放入管理員帳號密碼。")
    st.stop()

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    admin_accounts = config.get("admin_accounts", {})
except Exception as e:
    st.error(f"❌ 讀取 config.json 發生錯誤：{e}")
    st.stop()

if not admin_accounts:
    st.error("❌ 設定檔中沒有定義任何管理員帳號。")
    st.stop()

# ==============================
# 初始化資料庫
# ==============================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            戶號 TEXT,
            議題 TEXT,
            選項 TEXT,
            區分比例 REAL,
            時間 TEXT,
            PRIMARY KEY (戶號, 議題)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            end_time TEXT,
            is_active INTEGER DEFAULT 1,
            note TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==============================
# 資料庫輔助函式
# ==============================
def get_conn():
    return sqlite3.connect(DB_PATH)

def save_votes_sql(records):
    conn = get_conn()
    c = conn.cursor()
    for r in records:
        c.execute("""
            INSERT OR REPLACE INTO votes (戶號, 議題, 選項, 區分比例, 時間)
            VALUES (?, ?, ?, ?, ?)
        """, r)
    conn.commit()
    conn.close()

def fetch_votes_df():
    conn = get_conn()
    try:
        df = pd.read_sql("SELECT * FROM votes", conn)
    except Exception:
        df = pd.DataFrame(columns=["戶號","議題","選項","區分比例","時間"])
    conn.close()
    return df

def get_latest_setting():
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT end_time, is_active FROM settings ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        end_time_iso, is_active = row
        if end_time_iso:
            dt = datetime.fromisoformat(end_time_iso)
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
            return dt, int(is_active)
    return None, 1

def add_setting(end_time_dt, is_active=1):
    conn = get_conn()
    c = conn.cursor()
    created = datetime.now(TZ).isoformat()
    c.execute("INSERT INTO settings (end_time, is_active, created_at) VALUES (?, ?, ?)",
              (end_time_dt.isoformat(), int(is_active), created))
    conn.commit()
    conn.close()

def update_setting_active(active):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT end_time FROM settings ORDER BY id DESC LIMIT 1").fetchone()
    end_time_iso = row[0] if row else None
    created = datetime.now(TZ).isoformat()
    c.execute("INSERT INTO settings (end_time, is_active, created_at) VALUES (?, ?, ?)",
              (end_time_iso, int(active), created))
    conn.commit()
    conn.close()

# ==============================
# QR 產生函式（含文字）
# ==============================
def generate_qr_with_text(unit):
    url = f"{BASE_URL}/?{urlencode({'戶號': unit})}"
    qr = qrcode.make(url).convert("RGB")

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    text1 = f"戶號：{unit}"
    text2 = "議題討論後掃瞄QR Code進行投票"
    lines = [text1, text2]

    max_w = 0
    total_h = 0
    for line in lines:
        w, h = font.getsize(line)
        max_w = max(max_w, w)
        total_h += h + 4

    qr_w, qr_h = qr.size
    canvas_w = max(max_w + 20, qr_w + 20)
    canvas_h = qr_h + total_h + 40

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(canvas)

    y = 10
    for line in lines:
        w, h = font.getsize(line)
        draw.text(((canvas_w - w)//2, y), line, font=font, fill="black")
        y += h + 4

    canvas.paste(qr, ((canvas_w - qr_w)//2, y + 10))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================
# Streamlit 主介面
# ==============================
st.set_page_config(page_title="SmartVoteApp", layout="wide")
st.title("🗳️ SmartVoteApp 投票系統")

# 使用新版 API（取代 experimental_get_query_params）
qp = st.query_params
unit_q = qp.get("戶號")

# Session 狀態
if "admin" not in st.session_state:
    st.session_state.admin = False
if "admin_user" not in st.session_state:
    st.session_state.admin_user = None

# 選單
page = st.sidebar.selectbox("功能選單", ["首頁", "住戶投票", "管理員登入", "管理後台"])

# ==============================
# 首頁
# ==============================
if page == "首頁":
    st.info("請使用專屬 QR Code 進入投票頁面（網址會包含 ?戶號=xxx）。")

# ==============================
# 住戶投票（透過戶號進入）
# ==============================
elif page == "住戶投票":
    if not unit_q:
        st.warning("請從 QR Code 連結進入（網址需包含 ?戶號=xxx）")
        st.stop()

    unit = str(unit_q)

    issues_path = os.path.join(DATA_DIR, "議題清單.xlsx")
    units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
    if not os.path.exists(issues_path) or not os.path.exists(units_path):
        st.warning("尚未由管理員上傳議題或戶號清單。")
        st.stop()

    issues_df = pd.read_excel(issues_path)
    units_df = pd.read_excel(units_path)

    if str(unit) not in units_df.iloc[:,0].astype(str).values:
        st.error("查無此戶號，請確認 QR Code 或聯絡管理員。")
        st.stop()

    latest_end, active = get_latest_setting()
    now = datetime.now(TZ)
    if not latest_end or active == 0 or now >= latest_end:
        st.warning("投票已截止或被管理員停止。")
        st.stop()

    # 判斷是否已投票
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM votes WHERE 戶號 = ?", (unit,))
    if c.fetchone()[0] > 0:
        st.success("您已完成投票，感謝您的參與！")
        st.stop()
    conn.close()

    st.header(f"🏠 戶號 {unit} 投票頁面")
    st.info(f"截止時間（台北）：{latest_end.strftime('%Y-%m-%d %H:%M:%S')}")
    issues = issues_df.iloc[:,0].astype(str).tolist()

    form = st.form("vote_form")
    choices = {}
    for i, issue in enumerate(issues):
        choices[issue] = form.radio(issue, ["同意", "不同意"], horizontal=True)
    submit = form.form_submit_button("📤 送出投票")

    if submit:
        ratio = 1.0
        row = units_df[units_df.iloc[:,0].astype(str) == unit]
        if row.shape[1] >= 2:
            try:
                ratio = float(row.iloc[0, 1])
            except Exception:
                pass
        now_iso = datetime.now(TZ).isoformat()
        recs = [(unit, issue, choice, ratio, now_iso) for issue, choice in choices.items()]
        save_votes_sql(recs)
        st.success("✅ 投票完成！謝謝您的參與。")
        st.rerun()

# ==============================
# 管理員登入
# ==============================
elif page == "管理員登入":
    st.header("🔐 管理員登入")
    if not st.session_state.admin:
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        if st.button("登入"):
            if username in admin_accounts and password == admin_accounts[username]:
                st.session_state.admin = True
                st.session_state.admin_user = username
                st.success(f"登入成功（{username}）")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤")
    else:
        st.success(f"您已登入：{st.session_state.admin_user}")
        if st.button("登出"):
            st.session_state.admin = False
            st.session_state.admin_user = None
            st.rerun()

# ==============================
# 管理後台
# ==============================
elif page == "管理後台":
    st.header("👨‍💼 管理後台")
    if not st.session_state.admin:
        st.warning("請先登入管理員帳號")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        issues_file = st.file_uploader("📘 上傳議題清單", type=["xlsx"])
    with col2:
        units_file = st.file_uploader("🏠 上傳戶號清單", type=["xlsx"])

    if issues_file:
        with open(os.path.join(DATA_DIR, "議題清單.xlsx"), "wb") as f:
            f.write(issues_file.getvalue())
        st.success("已上傳議題清單")

    if units_file:
        with open(os.path.join(DATA_DIR, "戶號清單.xlsx"), "wb") as f:
            f.write(units_file.getvalue())
        st.success("已上傳戶號清單")

    # 產生 QR Code ZIP
    st.markdown("---")
    st.subheader("🧾 產生戶號專屬 QR Code")
    units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
    if os.path.exists(units_path):
        units_df = pd.read_excel(units_path)
        if st.button("📦 產生 ZIP 檔"):
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for _, r in units_df.iterrows():
                    unit = str(r.iloc[0])
                    qr_buf = generate_qr_with_text(unit)
                    zf.writestr(f"{unit}.png", qr_buf.getvalue())
            zip_buf.seek(0)
            st.download_button("⬇️ 下載 QR Code ZIP", zip_buf, "QRCodes.zip", "application/zip")
    else:
        st.info("請先上傳戶號清單。")
