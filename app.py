import streamlit as st
import pandas as pd
import qrcode
import io
import zipfile
import json
import os
from datetime import datetime, timedelta
from PIL import Image
from pytz import timezone

# ===============================
# 初始化設定
# ===============================
st.set_page_config(page_title="社區投票系統", layout="wide")

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
            qr_link = f"{base_url}?house_id={house_id}"
            qr_img = qrcode.make(qr_link)

            img_bytes = io.BytesIO()
            qr_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            zf.writestr(f"{house_id}.png", img_bytes.read())

    zip_buffer.seek(0)
    return zip_buffer

# ===============================
# 主程式
# ===============================
params = st.query_params  # 修正新版 API

page = params.get("page", ["home"])[0]
house_id = params.get("house_id", [None])[0]

# ===============================
# 首頁（住戶投票介面）
# ===============================
def voter_page():
    st.title("🏠 社區投票系統")
    st.write("請使用 QR Code 登入您的投票頁面。")

    if house_id:
        st.info(f"目前登入戶號：{house_id}")
    else:
        st.warning("未偵測到戶號參數，請由專屬 QR Code 登入。")

# ===============================
# 管理後台
# ===============================
def admin_dashboard():
    st.title("🧩 管理後台")

    st.subheader("投票控制")
    st.write("控制投票開放、截止時間等功能。")

    households_file = "data/households.csv"

    st.subheader("上傳住戶清單")
    uploaded_households = st.file_uploader("選擇 households.csv", type=["csv"], key="upload_households")
    if uploaded_households:
        os.makedirs("data", exist_ok=True)
        df = pd.read_csv(uploaded_households)
        df.to_csv(households_file, index=False)
        st.success("✅ 住戶清單已上傳。")

    st.subheader("住戶 QR Code 投票連結")
    if st.button("產生 QR Code ZIP"):
        if os.path.exists(households_file):
            households_df = pd.read_csv(households_file)
            base_url = st.request.url.split("?")[0]  # 自動取目前網址基底
            qr_zip_data = generate_qr_zip(households_df, base_url)
            if qr_zip_data:
                st.session_state["qr_zip_data"] = qr_zip_data.getvalue()
                st.success("✅ QR Code ZIP 產生完成！")
        else:
            st.error("找不到 households.csv，請先上傳住戶清單。")

    if "qr_zip_data" in st.session_state:
        st.download_button(
            label="📦 下載全部 QR Code ZIP",
            data=st.session_state["qr_zip_data"],
            file_name="QR_Codes.zip",
            mime="application/zip"
        )

# ===============================
# 頁面導向
# ===============================
if page == "admin":
    admin_dashboard()
else:
    voter_page()
