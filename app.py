import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
from datetime import datetime
from urllib.parse import urlencode

# ==============================
# 初始化 Session State
# ==============================
if "votes" not in st.session_state:
    st.session_state.votes = pd.DataFrame(columns=["戶號", "議題", "選項", "區分比例", "時間"])

# ==============================
# 功能函式
# ==============================
def save_votes(df):
    df.to_csv("votes.csv", index=False, encoding="utf-8-sig")
    # 備份檔案
    backup_name = f"votes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(backup_name, index=False, encoding="utf-8-sig")

def generate_qr(url):
    qr_img = qrcode.make(url)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================
# 主畫面邏輯
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
        issues_df = pd.read_excel(uploaded_issues)
        units_df = pd.read_excel(uploaded_units)

        st.success("✅ 成功讀取議題與戶號清單")

        # 顯示 QR Code 生成按鈕
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

        # 投票統計
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
            st.subheader("📊 投票統計結果")
            st.dataframe(stat_df)

            st.subheader("📈 區分比例長條圖（同意 vs 不同意）")
            chart_df = stat_df.set_index("議題")[["同意比例", "不同意比例"]]
            st.bar_chart(chart_df)

# ==============================
# 投票模式（一般住戶）
# ==============================
elif 戶號參數:
    st.header(f"🏠 戶號 {戶號參數} 投票頁面")

    if os.path.exists("議題清單.xlsx"):
        issues_df = pd.read_excel("議題清單.xlsx")
        st.write("請勾選以下議題的意見：")

        vote_records = []
        for _, row in issues_df.iterrows():
            issue = row["議題名稱"]
            option = st.radio(f"{issue}", ["同意", "不同意"], horizontal=True, key=issue)
            vote_records.append((戶號參數, issue, option))

        if st.button("📤 送出投票"):
            df = pd.DataFrame(vote_records, columns=["戶號", "議題", "選項"])
            df["時間"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.votes = pd.concat([st.session_state.votes, df], ignore_index=True)
            save_votes(st.session_state.votes)
            st.success("✅ 投票完成，感謝您的參與！")
    else:
        st.warning("⚠️ 尚未上傳議題清單，請聯絡管理員。")

# ==============================
# 預設首頁提示
# ==============================
else:
    st.info("請透過 QR Code 進入投票頁面，或於網址後加上 '?admin=true' 進入管理模式。")
