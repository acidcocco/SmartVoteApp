# ==============================================
# SmartVoteApp - 完整修正版 (2025-10)
# ==============================================
import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode
from PIL import Image, ImageDraw, ImageFont
import sqlite3
import pytz

# ==============================================
# 設定區
# ==============================================
BASE_URL = "https://smartvoteapp.onrender.com"
DB_PATH = "votes.db"
CONFIG_FILE = "admin_config.json"
FONT_PATH = "kaiu.ttf"  # 標楷體字型放在同層目錄

# ==============================================
# 初始化資料庫
# ==============================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household TEXT,
                    issue TEXT,
                    choice TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    end_time TIMESTAMP,
                    active INTEGER DEFAULT 1
                )""")
    conn.commit()
    conn.close()

init_db()

# ==============================================
# 載入管理員帳號設定
# ==============================================
def load_admin_accounts():
    if not os.path.exists(CONFIG_FILE):
        st.error("⚠️ 找不到 admin_config.json，請確認設定檔存在。")
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ==============================================
# 時區設定
# ==============================================
TZ = pytz.timezone("Asia/Taipei")

# ==============================================
# 資料庫工具
# ==============================================
def add_vote(household, issue, choice):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO votes (household, issue, choice) VALUES (?, ?, ?)", (household, issue, choice))
    conn.commit()
    conn.close()

def get_results():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM votes", conn)
    conn.close()
    return df

def add_setting(end_time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO settings (end_time, active) VALUES (?, 1)", (end_time,))
    conn.commit()
    conn.close()

def get_latest_setting():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT end_time, active FROM settings ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row[0]), row[1]
    return None, 1

def update_setting_active(active):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE settings SET active = ? WHERE id = (SELECT id FROM settings ORDER BY id DESC LIMIT 1)", (active,))
    conn.commit()
    conn.close()

# ==============================================
# QR Code 生成（支援中文、標楷體）
# ==============================================
def generate_qr_with_text(unit):
    url = f"{BASE_URL}/?{urlencode({'戶號': unit})}"
    qr = qrcode.make(url).convert("RGB")

    try:
        font = ImageFont.truetype(FONT_PATH, 22)
    except Exception:
        font = ImageFont.load_default()

    text1 = f"戶號：{unit}"
    text2 = "議題討論後掃瞄QR Code進行投票"
    lines = [text1, text2]

    def measure_text(font, text):
        try:
            bbox = font.getbbox(text)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except Exception:
            w, h = font.getmask(text).size
        return w, h

    max_w, total_h = 0, 0
    for line in lines:
        w, h = measure_text(font, line)
        max_w = max(max_w, w)
        total_h += h + 4

    qr_w, qr_h = qr.size
    canvas_w = max(max_w + 20, qr_w + 20)
    canvas_h = qr_h + total_h + 40

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(canvas)
    y = 10
    for line in lines:
        w, h = measure_text(font, line)
        draw.text(((canvas_w - w)//2, y), line, font=font, fill="black")
        y += h + 4

    canvas.paste(qr, ((canvas_w - qr_w)//2, y + 10))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================================
# Streamlit App
# ==============================================
st.set_page_config(page_title="SmartVoteApp", layout="wide")

st.sidebar.title("功能選單")
page = st.sidebar.selectbox("請選擇頁面", ["住戶投票", "管理員登入", "管理後台"])

# ==============================================
# 住戶投票頁
# ==============================================
if page == "住戶投票":
    st.title("📮 住戶投票")

    params = st.query_params  # 修正新版 Streamlit API
    household = params.get("戶號")

    if not household:
        st.error("請使用專屬 QR Code 進入投票頁面（網址需包含 ?戶號=）")
        st.stop()

    issues_file = "issues.xlsx"
    if not os.path.exists(issues_file):
        st.warning("尚未上傳議題清單")
        st.stop()

    issues_df = pd.read_excel(issues_file)
    issues = issues_df["議題"].tolist()

    latest_end, active = get_latest_setting()
    now = datetime.now(TZ)
    if latest_end and now > latest_end:
        st.warning("投票已截止")
        st.stop()
    if not active:
        st.warning("投票暫停中")
        st.stop()

    st.write(f"歡迎戶號：**{household}**")

    for issue in issues:
        st.markdown(f"### 🗳️ {issue}")
        choice = st.radio(f"請選擇（{issue}）", ["同意", "不同意"], key=issue)
        if st.button(f"提交：{issue}"):
            add_vote(household, issue, choice)
            st.success(f"已提交「{issue}」投票！")

# ==============================================
# 管理員登入頁
# ==============================================
elif page == "管理員登入":
    st.title("🔐 管理員登入")
    accounts = load_admin_accounts()

    username = st.text_input("帳號")
    password = st.text_input("密碼", type="password")

    if st.button("登入"):
        if username in accounts and accounts[username] == password:
            st.session_state["admin"] = True
            st.success("登入成功 ✅")
        else:
            st.error("帳號或密碼錯誤")

# ==============================================
# 管理後台
# ==============================================
elif page == "管理後台":
    st.title("📊 管理後台")

    if not st.session_state.get("admin"):
        st.warning("請先登入管理員帳號")
        st.stop()

    st.subheader("📁 上傳議題與戶號清單")
    issues_file = st.file_uploader("上傳議題清單（需含「議題」欄）", type=["xlsx"])
    units_file = st.file_uploader("上傳戶號清單（需含「戶號」欄）", type=["xlsx"])

    if issues_file:
        df = pd.read_excel(issues_file)
        df.to_excel("issues.xlsx", index=False)
        st.success("已上傳議題清單 ✅")

    if units_file:
        df = pd.read_excel(units_file)
        df.to_excel("units.xlsx", index=False)
        st.success("已上傳戶號清單 ✅")

    st.markdown("---")
    st.subheader("⏰ 投票截止設定")
    latest_end, active = get_latest_setting()

    default_dt = latest_end or (datetime.now(TZ) + timedelta(days=1))
    date_part = st.date_input("截止日期", value=default_dt.date())
    time_part = st.time_input("截止時間", value=default_dt.time())

    end_time = datetime.combine(date_part, time_part)
    end_time = TZ.localize(end_time)

    if st.button("✅ 更新截止時間"):
        add_setting(end_time)
        st.success(f"已設定截止時間：{end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    if st.button("⏹ 停止投票"):
        update_setting_active(0)
        st.warning("已暫停投票")

    if st.button("▶️ 開啟投票"):
        update_setting_active(1)
        st.success("投票重新開啟")

    st.markdown("---")
    st.subheader("🧾 產生戶號專屬 QR Code")

    if st.button("📦 產生 ZIP 檔"):
        if not os.path.exists("units.xlsx"):
            st.warning("請先上傳戶號清單")
        else:
            df = pd.read_excel("units.xlsx")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for _, row in df.iterrows():
                    unit = str(row["戶號"])
                    qr_buf = generate_qr_with_text(unit)
                    zf.writestr(f"{unit}.png", qr_buf.getvalue())
            st.download_button(
                label="📥 下載 QR Code ZIP",
                data=zip_buffer.getvalue(),
                file_name="qrcodes.zip",
                mime="application/zip"
            )

    st.markdown("---")
    st.subheader("📈 投票結果")

    df = get_results()
    if not df.empty:
        summary = df.groupby(["issue", "choice"]).size().unstack(fill_value=0)
        for issue, row in summary.iterrows():
            agree = row.get("同意", 0)
            disagree = row.get("不同意", 0)
            total = agree + disagree
            agree_ratio = agree / total * 100 if total > 0 else 0
            disagree_ratio = disagree / total * 100 if total > 0 else 0
            st.markdown(f"### 🗳️ {issue}")
            st.bar_chart(pd.DataFrame({
                "人數": [agree, disagree],
                "比例": [round(agree_ratio, 1), round(disagree_ratio, 1)]
            }, index=["同意", "不同意"]))
        st.download_button(
            label="📤 匯出投票結果 (Excel)",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="投票結果.csv",
            mime="text/csv"
        )
    else:
        st.info("尚無投票資料。")
