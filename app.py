# app.py
import streamlit as st
import pandas as pd
import qrcode
import io
import zipfile
import json
import os
from datetime import datetime, date, time
import time as t

# ===============================
# 初始化設定
# ===============================
st.set_page_config(page_title="社區投票系統", layout="wide")

if "page" not in st.session_state:
    st.session_state.page = "home"
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

HOUSEHOLD_FILE = os.path.join(DATA_DIR, "households.csv")
TOPIC_FILE = os.path.join(DATA_DIR, "topics.csv")
VOTE_FILE = os.path.join(DATA_DIR, "votes.csv")
CUTOFF_FILE = os.path.join(DATA_DIR, "cutoff.txt")

# ===============================
# 工具函式
# ===============================

def load_data(file_path, columns=None):
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        if columns:
            df = df[[c for c in columns if c in df.columns]]
        return df
    else:
        return pd.DataFrame(columns=columns)

def save_data(df, file_path):
    df.to_csv(file_path, index=False)

def generate_qr_codes(base_url, households):
    """產生每戶 QR Code 並打包成 zip"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for _, row in households.iterrows():
            unit = row["戶號"]
            url = f"{base_url}?unit={unit}"
            img = qrcode.make(url)
            img_byte = io.BytesIO()
            img.save(img_byte, format="PNG")
            img_byte.seek(0)
            zipf.writestr(f"{unit}.png", img_byte.read())
    zip_buffer.seek(0)
    return zip_buffer

def current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ===============================
# 登入與權限
# ===============================
def show_admin_login():
    st.header("🔐 管理員登入")
    try:
        with open("admin_config.json", "r", encoding="utf-8") as f:
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
        else:
            st.error("帳號或密碼錯誤，請重新輸入。")

# ===============================
# 管理後台
# ===============================
def admin_dashboard():
    st.title("📋 管理後台")

    # 上傳住戶清單
    st.subheader("🏘️ 上傳住戶清單 (戶號 + 區分比例)")
    household_file = st.file_uploader("請選擇 households.csv", type=["csv"])
    if household_file:
        df_house = pd.read_csv(household_file)
        if "戶號" in df_house.columns and "區分比例" in df_house.columns:
            save_data(df_house, HOUSEHOLD_FILE)
            st.success(f"✅ 已上傳 {len(df_house)} 筆住戶資料")
        else:
            st.error("CSV 必須包含欄位：戶號、區分比例")

    # 上傳議題清單
    st.subheader("🗳️ 上傳議題清單 (欄位：議題)")
    topic_file = st.file_uploader("請選擇 topics.csv", type=["csv"])
    if topic_file:
        df_topic = pd.read_csv(topic_file)
        if "議題" in df_topic.columns:
            save_data(df_topic, TOPIC_FILE)
            st.success(f"✅ 已上傳 {len(df_topic)} 筆議題")
        else:
            st.error("CSV 必須包含欄位：議題")

    # 截止時間設定
    st.subheader("📅 設定投票截止時間")
    cutoff_default = datetime.now().date()
    cutoff_date = st.date_input("請選擇截止日期", value=cutoff_default)
    cutoff_time = st.time_input("請選擇截止時間", value=time(23, 59))
    if st.button("💾 儲存截止時間"):
        cutoff_str = f"{cutoff_date} {cutoff_time}"
        with open(CUTOFF_FILE, "w") as f:
            f.write(cutoff_str)
        st.success(f"截止時間已設定為：{cutoff_str}")

    # 產生 QR Code
    st.subheader("🏘️ 住戶 QR Code 投票連結")
    st.caption("請於議題討論後掃描 QR Code 進行投票。")

    df_house = load_data(HOUSEHOLD_FILE, ["戶號", "區分比例"])
    if len(df_house) == 0:
        st.warning("尚未上傳住戶清單，請先上傳包含「戶號」與「區分比例」的 CSV 檔。")
    else:
        base_url = st.text_input("投票網站基本網址（請包含 https://）", "https://yourapp.streamlit.app")
        st.info("網址會自動加上戶號參數，例如：https://yourapp.streamlit.app?unit=101")

        if st.button("📦 產生 QR Code ZIP"):
            try:
                qr_zip = generate_qr_codes(base_url, df_house)
                st.download_button(
                    "📥 下載 QR Code 壓縮包",
                    data=qr_zip,
                    file_name="QRcodes.zip",
                    mime="application/zip"
                )
                st.success("✅ 已成功產生 QR Code ZIP 檔。")
            except Exception as e:
                st.error(f"產生 QR Code 時發生錯誤：{e}")

    # 顯示投票統計
    st.subheader("📈 投票結果統計")
    if os.path.exists(VOTE_FILE):
        df_vote = pd.read_csv(VOTE_FILE)
        df_house = load_data(HOUSEHOLD_FILE, ["戶號", "區分比例"])
        df_topic = load_data(TOPIC_FILE, ["議題"])

        if len(df_vote) > 0 and len(df_topic) > 0:
            merged = df_vote.merge(df_house, on="戶號", how="left")
            result_list = []
            for topic in df_topic["議題"]:
                agree_sum = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "同意"), "區分比例"].sum()
                disagree_sum = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "不同意"), "區分比例"].sum()
                result_list.append({
                    "議題": topic,
                    "同意比例": round(agree_sum, 4),
                    "不同意比例": round(disagree_sum, 4)
                })
            df_result = pd.DataFrame(result_list)
            st.dataframe(df_result)

            st.caption(f"統計時間：{current_time_str()}")

            # 自動刷新控制
            st.markdown("---")
            auto_refresh = st.checkbox("🔄 自動更新開啟 / 停止", value=st.session_state.auto_refresh)
            st.session_state.auto_refresh = auto_refresh
            if st.session_state.auto_refresh:
                t.sleep(10)
                st.rerun()
        else:
            st.info("尚無投票紀錄或議題資料。")
    else:
        st.info("尚未有投票資料。")

# ===============================
# 住戶投票頁
# ===============================
def voter_page():
    unit = st.query_params.get("unit", [None])[0]
    if not unit:
        st.error("❌ 無法辨識戶號，請使用正確的 QR Code 連結進入。")
        return

    st.title("📮 投票頁面")
    st.write(f"👤 戶號：**{unit}**")

    # 檢查截止時間
    if os.path.exists(CUTOFF_FILE):
        with open(CUTOFF_FILE, "r") as f:
            cutoff_str = f.read().strip()
        cutoff_time = datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > cutoff_time:
            st.warning(f"📢 投票已截止（截止時間：{cutoff_str}）")
            show_final_results()
            return

    # 載入議題
    df_topic = load_data(TOPIC_FILE, ["議題"])
    if len(df_topic) == 0:
        st.info("尚未設定投票議題。")
        return

    df_vote = load_data(VOTE_FILE, ["戶號", "議題", "投票"])
    voted_topics = df_vote[df_vote["戶號"] == unit]["議題"].tolist()

    for topic in df_topic["議題"]:
        st.markdown(f"### 🗳️ {topic}")
        if topic in voted_topics:
            prev = df_vote[(df_vote["戶號"] == unit) & (df_vote["議題"] == topic)]["投票"].values[0]
            st.info(f"您已投票：{prev}")
        else:
            choice = st.radio(f"請選擇您對「{topic}」的意見：", ["同意", "不同意"], key=topic)
            if st.button(f"提交「{topic}」的投票", key=f"btn_{topic}"):
                df_vote.loc[len(df_vote)] = [unit, topic, choice]
                save_data(df_vote, VOTE_FILE)
                st.success(f"✅ 已提交：{choice}")
                st.rerun()

# ===============================
# 公告顯示
# ===============================
def show_final_results():
    st.header("📢 投票結果公告")

    df_vote = load_data(VOTE_FILE, ["戶號", "議題", "投票"])
    df_house = load_data(HOUSEHOLD_FILE, ["戶號", "區分比例"])
    df_topic = load_data(TOPIC_FILE, ["議題"])

    if len(df_vote) == 0 or len(df_topic) == 0:
        st.info("尚無可公告的投票結果。")
        return

    merged = df_vote.merge(df_house, on="戶號", how="left")
    result_list = []
    for topic in df_topic["議題"]:
        agree_sum = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "同意"), "區分比例"].sum()
        disagree_sum = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "不同意"), "區分比例"].sum()
        result_list.append({
            "議題": topic,
            "同意比例": round(agree_sum, 4),
            "不同意比例": round(disagree_sum, 4)
        })
    df_result = pd.DataFrame(result_list)
    st.dataframe(df_result)
    st.caption(f"統計時間：{current_time_str()}")

# ===============================
# 主邏輯流程
# ===============================
def main():
    st.sidebar.title("功能選單")
    choice = st.sidebar.radio("請選擇：", ["🏠 首頁", "🔐 管理員登入", "📋 管理後台"])

    if choice == "🏠 首頁":
        voter_page()
    elif choice == "🔐 管理員登入":
        show_admin_login()
    elif choice == "📋 管理後台":
        if st.session_state.is_admin:
            admin_dashboard()
        else:
            st.warning("請先登入管理員帳號。")

if __name__ == "__main__":
    main()
