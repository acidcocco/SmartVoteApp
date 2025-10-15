import streamlit as st
import pandas as pd
import os
import qrcode
import json
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image, ImageDraw
import time

# ===============================
# 🔧 初始化設定
# ===============================
st.set_page_config(page_title="社區投票系統", page_icon="🏘️", layout="wide")

VOTE_FILE = "votes.csv"
CONFIG_FILE = "admin_config.json"
CUTOFF_FILE = "cutoff_time.txt"

# 初始化投票資料
if not os.path.exists(VOTE_FILE):
    df_init = pd.DataFrame(columns=["戶號", "意見", "投票時間"])
    df_init.to_csv(VOTE_FILE, index=False, encoding="utf-8-sig")

# ===============================
# 🔐 管理員登入
# ===============================
def show_admin_login():
    st.header("🔐 管理員登入")

    # 嘗試讀取 admin_config.json
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            admin_data = json.load(f)
    except FileNotFoundError:
        st.error("⚠️ 找不到 admin_config.json，請確認檔案存在於專案根目錄。")
        return

    username = st.text_input("管理員帳號")
    password = st.text_input("管理員密碼", type="password")

    if st.button("登入"):
        if username in admin_data and password == str(admin_data[username]):
            st.session_state["is_admin"] = True
            st.session_state["admin_user"] = username
            st.success(f"登入成功！歡迎管理員 {username} 👋")
            time.sleep(1)
            st.rerun()
        else:
            st.error("帳號或密碼錯誤，請重新輸入。")

# ===============================
# 📊 統計顯示函式
# ===============================
def show_vote_statistics(df, admin_mode=False):
    if df.empty:
        st.info("目前尚無投票資料。")
        return

    agree_count = len(df[df["意見"] == "同意"])
    disagree_count = len(df[df["意見"] == "不同意"])
    total = agree_count + disagree_count
    agree_rate = round(agree_count / total * 100, 1) if total else 0
    disagree_rate = round(disagree_count / total * 100, 1) if total else 0

    st.write(f"🟩 同意：{agree_count} 票（{agree_rate}%）")
    st.write(f"🟥 不同意：{disagree_count} 票（{disagree_rate}%）")

    chart_data = pd.DataFrame(
        {"選項": ["同意", "不同意"], "票數": [agree_count, disagree_count]}
    )
    st.bar_chart(chart_data.set_index("選項"))

    st.caption(f"統計時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ===============================
# 🏠 管理後台
# ===============================
def admin_dashboard():
    st.title("📋 管理後台")
    st.markdown("---")

    # 讀取投票資料
    df = pd.read_csv(VOTE_FILE, encoding="utf-8-sig") if os.path.exists(VOTE_FILE) else pd.DataFrame(columns=["戶號", "意見", "投票時間"])

    # 設定截止時間
    st.subheader("📅 設定投票截止時間")
    now = datetime.now()
    cutoff_default = now + timedelta(days=1)
    cutoff_input = st.datetime_input("請選擇截止時間", value=cutoff_default)
    if st.button("儲存截止時間"):
        with open(CUTOFF_FILE, "w") as f:
            f.write(cutoff_input.strftime("%Y-%m-%d %H:%M:%S"))
        st.success(f"✅ 截止時間已設定為：{cutoff_input}")

    # 產生 QR Code 圖文
    st.subheader("🏘️ 住戶 QR Code 投票連結")
    st.markdown("請於議題討論後掃描 QR Code 進行投票。")

    unit_list = [f"A-{i:03d}" for i in range(1, 6)]  # 範例：A-001~A-005
    for unit in unit_list:
        qr = qrcode.make(f"{st.secrets.get('base_url', 'https://yourapp.streamlit.app')}?unit={unit}")
        qr_img = Image.new("RGB", (500, 550), "white")
        qr_img.paste(qr, (50, 20))
        draw = ImageDraw.Draw(qr_img)
        draw.text((160, 480), f"戶號：{unit}", fill="black")
        st.image(qr_img, caption=f"{unit}.png", width=180)

    st.markdown("---")

    # 📈 投票結果報表（含自動刷新開關）
    st.subheader("📈 投票結果統計")
    auto_refresh = st.toggle("🔄 自動更新（每 10 秒）", value=True)

    placeholder = st.empty()
    refresh_interval = 10  # 秒

    if auto_refresh:
        # 自動更新模式
        while True:
            with placeholder.container():
                df = pd.read_csv(VOTE_FILE, encoding="utf-8-sig") if os.path.exists(VOTE_FILE) else pd.DataFrame(columns=["戶號", "意見", "投票時間"])
                show_vote_statistics(df, admin_mode=True)
                st.caption(f"⏱️ 最後更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(refresh_interval)
            st.rerun()
    else:
        # 靜態模式
        with placeholder.container():
            show_vote_statistics(df, admin_mode=True)
            st.caption(f"⏱️ 統計時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ===============================
# 🗳️ 投票頁（僅允許 QR Code 進入）
# ===============================
def voter_page():
    unit = st.query_params.get("unit", [None])[0]
    if not unit:
        st.error("❌ 無法辨識戶號，請使用正確的 QR Code 連結進入。")
        st.stop()

    st.title(f"🗳️ {unit} 戶投票頁面")

    # 檢查是否截止
    if os.path.exists(CUTOFF_FILE):
        with open(CUTOFF_FILE, "r") as f:
            cutoff_str = f.read().strip()
            cutoff_time = datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > cutoff_time:
            st.warning("📢 投票已截止，以下為最終統計結果：")
            df = pd.read_csv(VOTE_FILE, encoding="utf-8-sig")
            show_vote_statistics(df)
            st.stop()

    # 已投過檢查
    df = pd.read_csv(VOTE_FILE, encoding="utf-8-sig")
    if unit in df["戶號"].values:
        st.info("您已完成投票，感謝您的參與 🙏")
        show_vote_statistics(df)
        st.stop()

    # 投票操作
    choice = st.radio("請選擇您的意見：", ["同意", "不同意"])
    if st.button("送出投票"):
        new_row = pd.DataFrame({"戶號": [unit], "意見": [choice], "投票時間": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]})
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(VOTE_FILE, index=False, encoding="utf-8-sig")
        st.success("✅ 投票成功，感謝您的參與！")

# ===============================
# 🚀 主頁流程
# ===============================
def main():
    query_params = st.query_params
    if "unit" in query_params:
        voter_page()
        return

    if st.session_state.get("is_admin"):
        admin_dashboard()
    elif st.session_state.get("page") == "admin_login":
        show_admin_login()
    else:
        st.title("🏘️ 社區投票系統")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔐 管理員登入"):
                st.session_state.page = "admin_login"
        with col2:
            if st.button("📋 管理後台"):
                st.session_state.page = "admin_login"

if __name__ == "__main__":
    main()
