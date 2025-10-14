import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
import sqlite3
from datetime import datetime, timedelta
import pytz
from urllib.parse import urlencode

# ========= 基本設定 =========
st.set_page_config(page_title="社區投票系統", layout="wide")
TZ = pytz.timezone("Asia/Taipei")
DB_PATH = "settings.db"

# ========= 資料庫初始化 =========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            end_time TEXT,
            active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def add_setting(end_time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO settings (end_time, active) VALUES (?, ?)", (end_time, 1))
    conn.commit()
    conn.close()

def get_latest_setting():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT end_time, active FROM settings ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row[0]), bool(row[1])
    return None, True

def update_setting_active(active):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE settings SET active=? WHERE id=(SELECT id FROM settings ORDER BY id DESC LIMIT 1)", (active,))
    conn.commit()
    conn.close()

init_db()

# ========= 頁面標題 =========
st.title("🏘️ 社區投票系統")

# ========= 取得網址參數 =========
try:
    query_params = st.query_params.to_dict()
except Exception:
    query_params = st.experimental_get_query_params()

is_admin = str(query_params.get("admin", ["false"])[0]).lower() == "true"
戶號參數 = query_params.get("unit", [None])[0]

# ========= 投票題目設定 =========
ISSUES = [
    "議題一：是否同意實施社區公設改善工程？",
    "議題二：是否同意增加監視設備？",
    "議題三：是否同意延長管理室服務時間？"
]

# ========= 產生 QR Code 壓縮包 =========
def generate_qr_zip(base_url, df):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, row in df.iterrows():
            unit = str(row["戶號"])
            params = urlencode({"unit": unit})
            url = f"{base_url}?{params}"
            img = qrcode.make(url)
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="PNG")
            img_buffer.seek(0)
            zf.writestr(f"{unit}.png", img_buffer.read())
    zip_buffer.seek(0)
    return zip_buffer

# ========= 管理員後台 =========
if is_admin:
    st.sidebar.success("👑 管理員模式")

    uploaded_file = st.file_uploader("📤 上傳戶號清單（Excel）", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        st.write("✅ 已載入資料，共", len(df), "筆")

        base_url = "https://acidcocco.onrender.com"
        zip_buffer = generate_qr_zip(base_url, df)

        st.download_button(
            label="📦 下載 QR Code 壓縮包",
            data=zip_buffer,
            file_name="qrcodes.zip",
            mime="application/zip"
        )

    st.markdown("---")
    st.subheader("⏰ 投票截止設定")

    latest_end, active = get_latest_setting()

    # ✅ 改為分鐘選項
    duration = st.selectbox("請選擇投票時間長度（分鐘）", [5, 10, 15, 20, 25, 30], index=2)
    if latest_end:
        st.info(f"目前截止時間：{latest_end.strftime('%Y-%m-%d %H:%M:%S')}")

    if st.button("✅ 設定截止時間"):
        end_time = datetime.now(TZ) + timedelta(minutes=duration)
        add_setting(end_time.isoformat())
        st.success(f"已設定投票截止時間：{end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    if st.button("⏹ 停止投票"):
        update_setting_active(0)
        st.warning("已暫停投票")

    if st.button("▶️ 開啟投票"):
        update_setting_active(1)
        st.success("投票重新開啟")

# ========= 投票頁面 =========
else:
    if not 戶號參數:
        st.error("❌ 無法辨識戶號，請使用正確的 QR Code 連結進入。")
        st.stop()

    st.info(f"🏠 戶號：{戶號參數}")

    end_time, active = get_latest_setting()
    now = datetime.now(TZ)

    if not active:
        st.warning("投票目前已暫停，請稍後再試。")
        st.stop()

    if end_time and now > end_time:
        st.error("⏰ 投票已截止，感謝您的參與！")
        st.stop()

    st.subheader("🗳️ 投票區")

    votes = {}
    for issue in ISSUES:
        votes[issue] = st.radio(issue, ["贊成", "反對"], index=None)

    if st.button("✅ 送出投票"):
        if None in votes.values():
            st.warning("請確實填答所有議題再送出。")
        else:
            st.success("投票成功！感謝您的參與。")
            st.write(votes)
