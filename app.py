import streamlit as st

# ⚠️ 必須放在第一個 Streamlit 指令
st.set_page_config(page_title="社區投票系統", layout="wide")

import pandas as pd
import qrcode
import io
import zipfile
import json
import os
from datetime import datetime, timedelta
from pytz import timezone
from streamlit_autorefresh import st_autorefresh

# ===============================
# 初始化設定
# ===============================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
HOUSEHOLD_FILE = os.path.join(DATA_DIR, "households.csv")
TOPIC_FILE = os.path.join(DATA_DIR, "topics.csv")
VOTE_FILE = os.path.join(DATA_DIR, "votes.csv")
ADMIN_FILE = "admin_config.json"

# ===============================
# 工具函式
# ===============================
def load_csv(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    return pd.DataFrame()

def save_csv(df, file_path):
    df.to_csv(file_path, index=False)

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

def get_taipei_time():
    return datetime.now(timezone("Asia/Taipei"))

# ===============================
# 首頁
# ===============================
def voter_page():
    st.title("🏠 社區投票系統")
    params = st.query_params
    unit = params.get("unit", [None])[0] if isinstance(params.get("unit"), list) else params.get("unit")

    if unit:
        st.info(f"目前登入戶號：{unit}")
        st.success("投票功能已關閉，此版本僅供展示 QR 登入提示。")
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
        if not os.path.exists(ADMIN_FILE):
            st.error("找不到 admin_config.json，請確認檔案存在。")
            return

        try:
            with open(ADMIN_FILE, "r", encoding="utf-8") as f:
                admin_data = json.load(f)
        except Exception as e:
            st.error(f"讀取 admin_config.json 失敗：{e}")
            return

        if username in admin_data and password == str(admin_data[username]):
            st.session_state.is_admin = True
            st.session_state.admin_user = username
            st.success(f"登入成功！歡迎管理員 {username}")
        else:
            st.error("帳號或密碼錯誤。")

# ===============================
# 管理後台
# ===============================
def admin_dashboard():
    st.title("🧩 管理後台")

    # 1️⃣ 投票控制
    st.subheader("投票控制")
    if "voting_open" not in st.session_state:
        st.session_state.voting_open = False

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🟢 開啟投票"):
            st.session_state.voting_open = True
            st.success("投票已開啟！")
    with col2:
        if st.button("🔴 停止投票"):
            st.session_state.voting_open = False
            st.warning("投票已停止。")

    st.write(f"目前狀態：{'✅ 開放中' if st.session_state.voting_open else '⛔ 已停止'}")

    # 2️⃣ 上傳住戶清單
    st.subheader("上傳住戶清單")
    uploaded_households = st.file_uploader("選擇 households.csv", type=["csv"], key="upload_households")
    if uploaded_households:
        df = pd.read_csv(uploaded_households)
        save_csv(df, HOUSEHOLD_FILE)
        st.success("✅ 住戶清單已上傳。")

    # 3️⃣ 上傳議題清單
    st.subheader("上傳議題清單")
    uploaded_topics = st.file_uploader("選擇 topics.csv", type=["csv"], key="upload_topics")
    if uploaded_topics:
        df = pd.read_csv(uploaded_topics)
        save_csv(df, TOPIC_FILE)
        st.success("✅ 議題清單已上傳。")

    # 4️⃣ 住戶 QR Code 產生
    st.subheader("住戶 QR Code 投票連結")
    base_url = st.text_input("投票網站基本網址（請包含 https://）", "https://smartvoteapp.onrender.com")

    if st.button("📦 產生 QR Code ZIP"):
        households_df = load_csv(HOUSEHOLD_FILE)
        if not households_df.empty:
            qr_zip_data = generate_qr_zip(households_df, base_url)
            if qr_zip_data:
                st.session_state["qr_zip_data"] = qr_zip_data.getvalue()
                st.success("✅ QR Code ZIP 產生完成！")
        else:
            st.error("請先上傳 households.csv。")

    if "qr_zip_data" in st.session_state:
        st.download_button(
            label="📥 下載 QR Code ZIP",
            data=st.session_state["qr_zip_data"],
            file_name="QR_Codes.zip",
            mime="application/zip"
        )

    # 5️⃣ 設定投票截止時間
    st.subheader("設定投票截止時間")
    now = get_taipei_time()
    default_end = now + timedelta(days=1)
    end_date = st.date_input("截止日期 (台北時間)", value=default_end.date())
    end_time = st.time_input("截止時間 (台北時間)", value=default_end.time())

    combined_end = datetime.combine(end_date, end_time).astimezone(timezone("Asia/Taipei"))

    if st.button("儲存截止時間"):
        with open(os.path.join(DATA_DIR, "end_time.txt"), "w", encoding="utf-8") as f:
            f.write(combined_end.strftime("%Y-%m-%d %H:%M:%S %z"))
        st.success(f"截止時間已設定為 {combined_end.strftime('%Y-%m-%d %H:%M:%S')}")

    # 6️⃣ 投票結果統計
    st.subheader("📈 投票結果統計（每 10 秒自動更新）")
    st_autorefresh(interval=10 * 1000, key="refresh_votes")

    votes_df = load_csv(VOTE_FILE)
    households_df = load_csv(HOUSEHOLD_FILE)

    if not votes_df.empty and not households_df.empty:
        total_households = len(households_df)
        voted_households = votes_df["戶號"].nunique()
        remaining = total_households - voted_households

        agree = (votes_df["投票結果"] == "同意").sum()
        disagree = (votes_df["投票結果"] == "不同意").sum()
        total_votes = agree + disagree

        agree_ratio = agree / total_votes * 100 if total_votes > 0 else 0
        disagree_ratio = disagree / total_votes * 100 if total_votes > 0 else 0

        st.metric("🏠 總戶數", total_households)
        st.metric("🗳 已投票人數", voted_households)
        st.metric("⏳ 剩餘可投票人數", remaining)

        st.write(f"✅ 同意：{agree} 戶（{agree_ratio:.4f}%）")
        st.write(f"❌ 不同意：{disagree} 戶（{disagree_ratio:.4f}%）")

    else:
        st.info("目前尚無投票資料或未上傳住戶清單。")

# ===============================
# 主邏輯
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
