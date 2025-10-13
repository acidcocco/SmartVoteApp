import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
from datetime import datetime, timedelta
from urllib.parse import urlencode
from streamlit_autorefresh import st_autorefresh
import matplotlib.pyplot as plt

# ==============================
# 初始化 Session State
# ==============================
if "votes" not in st.session_state:
    st.session_state.votes = pd.DataFrame(columns=["戶號", "議題", "選項", "區分比例", "時間"])
if "deadline" not in st.session_state:
    st.session_state.deadline = None

# ==============================
# 功能函式
# ==============================
def save_votes(df):
    df.to_csv("votes.csv", index=False, encoding="utf-8-sig")
    backup_name = f"votes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(backup_name, index=False, encoding="utf-8-sig")

def generate_qr(url):
    qr_img = qrcode.make(url)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================
# Streamlit 頁面設定
# ==============================
st.set_page_config(page_title="SmartVoteApp", layout="wide")
st.title("🗳️ SmartVoteApp 投票系統")

try:
    query_params = st.query_params.to_dict()
except Exception:
    query_params = st.experimental_get_query_params()

# ==============================
# 判斷模式參數
# ==============================
is_admin = False
戶號參數 = None

if "admin" in query_params and query_params["admin"] == "true":
    is_admin = True
elif "unit" in query_params:
    戶號參數 = query_params["unit"]

# ==============================
# 管理員模式
# ==============================
if is_admin:
    st.header("👨‍💼 管理員模式")

    uploaded_issues = st.file_uploader("📘 上傳議題清單 Excel", type=["xlsx"])
    uploaded_units = st.file_uploader("🏠 上傳戶號清單 Excel（含區分比例）", type=["xlsx"])

    if uploaded_issues and uploaded_units:
        with open("議題清單.xlsx", "wb") as f:
            f.write(uploaded_issues.getvalue())

        with open("戶號清單.xlsx", "wb") as f:
            f.write(uploaded_units.getvalue())
            
        issues_df = pd.read_excel(uploaded_issues)
        units_df = pd.read_excel(uploaded_units)

        st.success("✅ 成功讀取議題與戶號清單")

        # 產生 QR Code
        if st.button("🧾 產生戶號專屬 QR Code"):
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zipf:
                for _, row in units_df.iterrows():
                    params = {"unit": row["戶號"]}
                    url = f"https://smartvoteapp.onrender.com?{urlencode(params)}"
                    qr_buf = generate_qr(url)
                    zipf.writestr(f"{row['戶號']}.png", qr_buf.getvalue())
            zip_buf.seek(0)
            st.download_button("⬇️ 下載 QR Code 壓縮檔", data=zip_buf, file_name="QRCode_AllUnits.zip", mime="application/zip")

        # 📅 投票截止時間設定
        st.divider()
        st.subheader("📅 投票截止時間設定")
        col1, col2 = st.columns(2)
        with col1:
            deadline_date = st.date_input("截止日期", value=datetime.now().date())
        with col2:
            deadline_time = st.time_input("截止時間", value=(datetime.now() + timedelta(hours=1)).time())

        deadline = datetime.combine(deadline_date, deadline_time)
        st.session_state.deadline = deadline

        now = datetime.now()
        st.write(f"🕒 現在時間：{now.strftime('%Y-%m-%d %H:%M:%S')}")
        if now < deadline:
            remaining = deadline - now
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes = remainder // 60
            st.success(f"⏳ 距離截止還有 {remaining.days} 天 {hours} 小時 {minutes} 分鐘")
        else:
            st.warning("⚠️ 投票已截止。系統將顯示最終結果（不再自動刷新）")

        # ✅ 即時更新開關
        st.divider()
        enable_refresh = st.checkbox("✅ 即時更新投票結果（每 5 秒刷新一次）", value=True)

        # 若未超過截止時間且開啟刷新 → 啟用自動更新
        if enable_refresh and now < deadline:
            st_autorefresh(interval=5000, key="auto_refresh")
        elif now >= deadline:
            st.info("📢 投票截止，已自動停止刷新。")

        # ==============================
        # 投票統計結果顯示
        # ==============================
        if os.path.exists("votes.csv"):
            votes_df = pd.read_csv("votes.csv")
            merged_df = votes_df.merge(units_df, on="戶號", how="left")

            result_list = []
            for issue in merged_df["議題"].unique():
                issue_data = merged_df[merged_df["議題"] == issue]
                agree = issue_data[issue_data["選項"] == "同意"]
                disagree = issue_data[issue_data["選項"] == "不同意"]
                total = units_df["戶號"].nunique()
                unvote = total - issue_data["戶號"].nunique()

                agree_ratio = agree["區分比例"].sum()
                disagree_ratio = disagree["區分比例"].sum()

                result_list.append({
                    "議題": issue,
                    "同意人數": len(agree),
                    "不同意人數": len(disagree),
                    "未投票戶數": unvote,
                    "同意比例": round(agree_ratio, 4),
                    "不同意比例": round(disagree_ratio, 4),
                })

            stat_df = pd.DataFrame(result_list)

            # 📢 截止後自動顯示公告
            if now >= deadline:
                st.markdown("""
                <div style="background-color:#fce4ec;padding:15px;border-radius:10px;margin-bottom:10px">
                <h4>📢 投票已截止！</h4>
                <p>以下為最終投票結果。</p>
                </div>
                """, unsafe_allow_html=True)

            st.subheader("📊 投票統計結果")
            st.dataframe(stat_df, use_container_width=True)

            # 📈 長條圖
            st.subheader("📈 區分比例長條圖（同意 vs 不同意）")
            chart_df = stat_df.set_index("議題")[["同意比例", "不同意比例"]]
            fig, ax = plt.subplots(figsize=(8, 4))
            chart_df.plot(kind="bar", ax=ax, color=["green", "red"])
            ax.set_ylabel("區分比例")
            ax.set_xlabel("議題")
            ax.set_title("各議題投票比例圖")
            ax.legend(["同意", "不同意"])
            st.pyplot(fig)

            st.caption(f"📅 最後更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.warning("⚠️ 尚無投票資料。")

# ==============================
# 投票模式（一般住戶）
# ==============================
elif 戶號參數:
    st.header(f"🏠 戶號 {戶號參數} 投票頁面")

    if os.path.exists("議題清單.xlsx") and os.path.exists("戶號清單.xlsx"):
        issues_df = pd.read_excel("議題清單.xlsx")
        units_df = pd.read_excel("戶號清單.xlsx")

        # 檢查是否已投票
        if os.path.exists("votes.csv"):
            existing_votes = pd.read_csv("votes.csv")
            if 戶號參數 in existing_votes["戶號"].values:
                st.success("✅ 您已完成投票，感謝您的參與！")
                st.stop()

        st.write("請勾選以下議題的意見：")

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
                df = pd.DataFrame(vote_records, columns=["戶號", "議題", "選項"])
                df["區分比例"] = ratio
                df["時間"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.votes = pd.concat([st.session_state.votes, df], ignore_index=True)
                save_votes(st.session_state.votes)
                st.success("✅ 投票完成，感謝您的參與！")
    else:
        st.warning("⚠️ 尚未上傳議題或戶號清單，請聯絡管理員。")

# ==============================
# 預設首頁提示
# ==============================
else:
    st.info("請透過 QR Code 進入投票頁面，或於網址後加上 '?admin=true' 進入管理模式。")
