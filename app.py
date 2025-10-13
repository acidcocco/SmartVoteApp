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
import matplotlib.pyplot as plt

# ==============================
# 🔧 系統設定
# ==============================
BASE_URL = "https://acidcocco.onrender.com"  # ⚙️ 修改成你的實際網址
DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "votes.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ==============================
# 🔹 初始化資料庫
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
    conn.commit()
    conn.close()

init_db()

# ==============================
# 🔹 設定檔管理
# ==============================
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"deadline": None}

def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

# ==============================
# 🔹 功能函式
# ==============================
def save_vote_to_db(records):
    conn = sqlite3.connect(DB_PATH)
    df = pd.DataFrame(records, columns=["戶號", "議題", "選項", "區分比例", "時間"])
    df.to_sql("votes", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()

def fetch_votes():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM votes", conn)
    conn.close()
    return df

def has_voted(戶號):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM votes WHERE 戶號 = ?", (戶號,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def generate_qr(url):
    qr_img = qrcode.make(url)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================
# 🧭 頁面設定
# ==============================
st.set_page_config(page_title="SmartVoteApp", layout="wide")
st.title("🗳️ SmartVoteApp 投票系統")

try:
    query_params = st.query_params.to_dict()
except Exception:
    query_params = st.experimental_get_query_params()
query_params = {k: v[0] if isinstance(v, list) else v for k, v in query_params.items()}

is_admin = query_params.get("admin", "false").lower() == "true"
戶號參數 = query_params.get("unit")

# ==============================
# 👨‍💼 管理員模式
# ==============================
if is_admin:
    st.header("👨‍💼 管理員模式")

    uploaded_issues = st.file_uploader("📘 上傳議題清單 Excel", type=["xlsx"])
    uploaded_units = st.file_uploader("🏠 上傳戶號清單 Excel（含區分比例）", type=["xlsx"])

    if uploaded_issues and uploaded_units:
        issues_path = os.path.join(DATA_DIR, "議題清單.xlsx")
        units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
        with open(issues_path, "wb") as f:
            f.write(uploaded_issues.getvalue())
        with open(units_path, "wb") as f:
            f.write(uploaded_units.getvalue())

        issues_df = pd.read_excel(uploaded_issues)
        units_df = pd.read_excel(uploaded_units)

        st.success("✅ 成功讀取議題與戶號清單")

        # 🧾 產生 QR Code
        if st.button("🧾 產生戶號專屬 QR Code"):
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zipf:
                for _, row in units_df.iterrows():
                    params = {"unit": row["戶號"]}
                    url = f"{BASE_URL}?{urlencode(params)}"
                    qr_buf = generate_qr(url)
                    zipf.writestr(f"{row['戶號']}.png", qr_buf.getvalue())
            zip_buf.seek(0)
            st.download_button(
                "⬇️ 下載 QR Code 壓縮檔",
                data=zip_buf,
                file_name="QRCode_AllUnits.zip",
                mime="application/zip"
            )

        # 📅 投票截止時間設定
        st.divider()
        st.subheader("📅 投票截止時間設定")
        col1, col2 = st.columns(2)
        with col1:
            deadline_date = st.date_input("截止日期", value=datetime.now().date())
        with col2:
            deadline_time = st.time_input("截止時間", value=(datetime.now() + timedelta(hours=1)).time())

        deadline = datetime.combine(deadline_date, deadline_time)
        config["deadline"] = deadline.strftime("%Y-%m-%d %H:%M:%S")
        save_config(config)

        now = datetime.now()
        st.write(f"🕒 現在時間：{now.strftime('%Y-%m-%d %H:%M:%S')}")

        if now < deadline:
            remaining = deadline - now
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes = remainder // 60
            st.success(f"⏳ 距離截止還有 {remaining.days} 天 {hours} 小時 {minutes} 分鐘")
        else:
            st.warning("⚠️ 投票已截止。")

        enable_refresh = st.checkbox("✅ 即時更新投票結果（每 5 秒刷新一次）", value=True)
        if enable_refresh and now < deadline:
            st_autorefresh(interval=5000, key="auto_refresh")

    # 📊 統計結果顯示
    if os.path.exists(DB_PATH) and os.path.exists(os.path.join(DATA_DIR, "戶號清單.xlsx")):
        votes_df = fetch_votes()
        units_df = pd.read_excel(os.path.join(DATA_DIR, "戶號清單.xlsx"))
        if len(votes_df) > 0:
            merged_df = votes_df.merge(units_df, on="戶號", how="left")
            ratio_col = next((col for col in merged_df.columns if "比例" in col or "比率" in col or "持分" in col), None)

            result_list = []
            for issue in merged_df["議題"].unique():
                issue_data = merged_df[merged_df["議題"] == issue]
                agree = issue_data[issue_data["選項"] == "同意"]
                disagree = issue_data[issue_data["選項"] == "不同意"]
                total = units_df["戶號"].nunique()
                unvote = total - issue_data["戶號"].nunique()
                agree_ratio = agree[ratio_col].sum()
                disagree_ratio = disagree[ratio_col].sum()
                result_list.append({
                    "議題": issue,
                    "同意人數": len(agree),
                    "不同意人數": len(disagree),
                    "未投票戶數": unvote,
                    "同意比例": round(agree_ratio, 4),
                    "不同意比例": round(disagree_ratio, 4),
                })
            stat_df = pd.DataFrame(result_list)
            st.subheader("📊 投票統計結果")
            st.dataframe(stat_df, use_container_width=True)

            st.subheader("📈 區分比例長條圖")
            chart_df = stat_df.set_index("議題")[["同意比例", "不同意比例"]]
            fig, ax = plt.subplots(figsize=(8, 4))
            chart_df.plot(kind="bar", ax=ax, color=["green", "red"])
            ax.set_ylabel("區分比例")
            st.pyplot(fig)

# ==============================
# 🏠 住戶投票模式
# ==============================
elif 戶號參數:
    st.header(f"🏠 戶號 {戶號參數} 投票頁面")

    if os.path.exists(os.path.join(DATA_DIR, "議題清單.xlsx")) and os.path.exists(os.path.join(DATA_DIR, "戶號清單.xlsx")):
        issues_df = pd.read_excel(os.path.join(DATA_DIR, "議題清單.xlsx"))
        units_df = pd.read_excel(os.path.join(DATA_DIR, "戶號清單.xlsx"))

        deadline_str = config.get("deadline")
        if deadline_str:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")
            if datetime.now() > deadline:
                st.warning("⚠️ 投票已截止，無法再投票。")
                st.stop()

        if has_voted(戶號參數):
            st.success("✅ 您已完成投票，感謝您的參與！")
            st.stop()

        vote_records = []
        for _, row in issues_df.iterrows():
            issue = row["議題名稱"]
            option = st.radio(f"{issue}", ["同意", "不同意"], horizontal=True, key=issue)
            vote_records.append((戶號參數, issue, option))

        if st.button("📤 送出投票"):
            unit_info = units_df[units_df["戶號"] == 戶號參數]
            if unit_info.empty:
                st.error("查無此戶號，請確認 QR Code 是否正確。")
            else:
                ratio = float(unit_info["區分比例"].iloc[0])
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                records = [(戶號參數, issue, opt, ratio, timestamp) for _, issue, opt in [(戶號參數, i[1], i[2]) for i in vote_records]]
                save_vote_to_db(records)
                st.success("✅ 投票完成，感謝您的參與！")

    else:
        st.warning("⚠️ 尚未上傳議題或戶號清單。")

# ==============================
# 🏠 預設首頁
# ==============================
else:
    st.info("請透過 QR Code 進入投票頁面，或於網址後加上 '?admin=true' 進入管理模式。")
