import streamlit as st
import pandas as pd
import qrcode
import io
import zipfile
import json
import os
from datetime import datetime, timedelta
from pytz import timezone

# ===============================
# 初始化設定
# ===============================
st.set_page_config(page_title="社區投票系統", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
HOUSEHOLD_FILE = os.path.join(DATA_DIR, "households.csv")

# ===============================
# 輔助函式
# ===============================
def generate_qr_zip(households_df, base_url):
    if households_df.empty:
        st.warning("尚未上傳住戶清單，無法產生 QR Code。")
        return None

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for _, row in households_df.iterrows():
            house_id = str(row["戶號"]).strip()
            qr_link = f"{base_url}?unit={house_id}"
            qr_img = qrcode.make(qr_link)

            img_bytes = io.BytesIO()
            qr_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            zf.writestr(f"{house_id}.png", img_bytes.read())

    zip_buffer.seek(0)
    return zip_buffer

def current_time_str():
    tz = timezone("Asia/Taipei")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

# ===============================
# 首頁（住戶投票介面）
# ===============================
def voter_page():
    st.title("🏠 社區投票系統")
    params = st.query_params
    unit = params.get("unit", [None])[0] if isinstance(params.get("unit"), list) else params.get("unit")

    if unit:
        st.info(f"目前登入戶號：{unit}")
        st.write(f"系統時間：{current_time_str()}")
        st.success("歡迎進入投票頁面，功能待整合。")
    else:
        st.warning("未偵測到戶號參數，請由專屬 QR Code 登入。")

# ===============================
# 管理員登入
# ===============================
def admin_login():
    st.header("🔐 管理員登入")

    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False

    username = st.text_input("帳號")
    password = st.text_input("密碼", type="password")

    if st.button("登入"):
        if username == "admin" and password == "1234":
            st.session_state.is_admin = True
            st.success("登入成功！")
        else:
            st.error("帳號或密碼錯誤。")

# ===============================
# 管理後台
# ===============================
def admin_dashboard():
    st.title("🧩 管理後台")

    st.subheader("投票控制")
    st.write("控制投票開放、截止時間等功能。")

    st.subheader("上傳住戶清單")
    uploaded_households = st.file_uploader("選擇 households.csv", type=["csv"], key="upload_households")
    if uploaded_households:
        df = pd.read_csv(uploaded_households)
        df.to_csv(HOUSEHOLD_FILE, index=False)
        st.success("✅ 住戶清單已上傳。")

    st.subheader("住戶 QR Code 投票連結")
    base_url = st.text_input("投票網站基本網址（請包含 https://）", "https://smartvoteapp.onrender.com")

    if st.button("📦 產生 QR Code ZIP"):
        if os.path.exists(HOUSEHOLD_FILE):
            households_df = pd.read_csv(HOUSEHOLD_FILE)
            qr_zip_data = generate_qr_zip(households_df, base_url)
            if qr_zip_data:
                st.session_state["qr_zip_data"] = qr_zip_data.getvalue()
                st.success("✅ QR Code ZIP 產生完成！")
        else:
            st.error("找不到 households.csv，請先上傳住戶清單。")

    if "qr_zip_data" in st.session_state:
        st.download_button(
            label="📥 下載 QR Code ZIP",
            data=st.session_state["qr_zip_data"],
            file_name="QR_Codes.zip",
            mime="application/zip"
        )

# ===============================
# 主邏輯與左側選單
# ===============================
def main():
    st.sidebar.title("功能選單")
    menu = st.sidebar.radio("請選擇：", ["🏠 首頁", "🔐 管理員登入", "📋 管理後台"])

    if menu == "🏠 首頁":
        voter_page()
    elif menu == "🔐 管理員登入":
        admin_login()
    elif menu == "📋 管理後台":
        if st.session_state.get("is_admin", False):
            admin_dashboard()
        else:
            st.warning("請先登入管理員帳號。")

if __name__ == "__main__":
    main()
