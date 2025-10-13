import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
from datetime import datetime
from urllib.parse import urlencode
import matplotlib.pyplot as plt

# ==============================
# 初始化 Session State
# ==============================
if "votes" not in st.session_state:
    st.session_state.votes = pd.DataFrame(columns=["戶號", "議題", "投票結果", "投票時間"])
if "admin" not in st.session_state:
    st.session_state.admin = False
if "admin_user" not in st.session_state:
    st.session_state.admin_user = None

# ==============================
# 後台帳號設定
# ==============================
admin_accounts = {
    "acidcocco": "131105",         # 預設管理員帳號與密碼
    "manager": "abcd2025"    # 可自行新增多組
}

base_url = "https://smartvoteapp.onrender.com"

# ==============================
# 上傳投票議題與戶號資料
# ==============================
issues_file = "issues.xlsx"
houses_file = "houses.xlsx"

if os.path.exists(issues_file):
    try:
        issues_df = pd.read_excel(issues_file)
    except Exception as e:
        st.error(f"❌ 無法讀取議題檔案：{e}")
        issues_df = pd.DataFrame(columns=["議題"])
else:
    issues_df = pd.DataFrame(columns=["議題"])

if os.path.exists(houses_file):
    try:
        houses_df = pd.read_excel(houses_file)
    except Exception as e:
        st.error(f"❌ 無法讀取戶號檔案：{e}")
        houses_df = pd.DataFrame(columns=["戶號"])
else:
    houses_df = pd.DataFrame(columns=["戶號"])

# ==============================
# 頁面選單
# ==============================
page = st.sidebar.selectbox("功能選單", ["住戶投票", "管理員登入", "管理後台"])

# ==============================
# 住戶投票
# ==============================
if page == "住戶投票":
    st.title("🏠 社區議題投票系統")

    params = st.experimental_get_query_params()
    house_id = params.get("戶號", [None])[0]

    if not house_id:
        st.warning("請使用專屬 QR Code 進入投票頁面")
    elif house_id not in houses_df["戶號"].astype(str).values:
        st.error("❌ 無效的戶號")
    else:
        st.subheader(f"您好，{house_id} 戶")
        with st.form("vote_form"):
            selections = {}
            for issue in issues_df["議題"]:
                selections[issue] = st.radio(
                    f"{issue}",
                    ["同意", "不同意", "不投票"],
                    horizontal=True,
                )
            submitted = st.form_submit_button("✅ 送出投票")

        if submitted:
            new_votes = []
            for issue, result in selections.items():
                new_votes.append({
                    "戶號": house_id,
                    "議題": issue,
                    "投票結果": result,
                    "投票時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            st.session_state.votes = pd.concat(
                [st.session_state.votes, pd.DataFrame(new_votes)],
                ignore_index=True
            )
            st.success("✅ 投票已送出，謝謝您的參與！")
            st.rerun()

# ==============================
# 管理員登入
# ==============================
elif page == "管理員登入":
    st.title("🔐 管理員登入")

    if not st.session_state.admin:
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")

        if st.button("登入"):
            if username in admin_accounts and password == admin_accounts[username]:
                st.session_state.admin = True
                st.session_state.admin_user = username
                st.success(f"登入成功 ✅（歡迎 {username}）")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤 ❌")
    else:
        st.success(f"您已登入：{st.session_state.admin_user}")
        if st.button("登出"):
            st.session_state.admin = False
            st.session_state.admin_user = None
            st.info("您已登出")
            st.rerun()

# ==============================
# 管理後台
# ==============================
elif page == "管理後台":
    st.title("📊 投票結果統計")

    if not st.session_state.get("admin"):
        st.warning("請先登入管理員帳號")
        st.stop()

    votes_df = st.session_state.votes
    if votes_df.empty:
        st.info("目前尚無投票資料")
        st.stop()

    results = []
    total_houses = len(houses_df)

    for issue in issues_df["議題"]:
        issue_votes = votes_df[votes_df["議題"] == issue]
        agree = issue_votes[issue_votes["投票結果"] == "同意"]
        disagree = issue_votes[issue_votes["投票結果"] == "不同意"]
        unvote = total_houses - len(issue_votes["戶號"].unique())

        agree_ratio = (len(agree) / total_houses * 100) if total_houses > 0 else 0
        disagree_ratio = (len(disagree) / total_houses * 100) if total_houses > 0 else 0

        results.append({
            "議題": issue,
            "同意人數": len(agree),
            "不同意人數": len(disagree),
            "未投票戶數": unvote,
            "同意比例(%)": round(agree_ratio, 2),
            "不同意比例(%)": round(disagree_ratio, 2)
        })

    results_df = pd.DataFrame(results)
    st.dataframe(results_df, use_container_width=True)

    # 匯出按鈕
    export_buffer = io.BytesIO()
    with pd.ExcelWriter(export_buffer, engine="xlsxwriter") as writer:
        results_df.to_excel(writer, index=False, sheet_name="投票結果")
        votes_df.to_excel(writer, index=False, sheet_name="明細資料")

    st.download_button(
        label="📤 匯出投票結果 (Excel)",
        data=export_buffer.getvalue(),
        file_name=f"vote_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # 長條圖
    st.subheader("📈 各議題投票結果（長條圖）")
    for _, row in results_df.iterrows():
        fig, ax = plt.subplots()
        categories = ["同意", "不同意"]
        values = [row["同意比例(%)"], row["不同意比例(%)"]]
        ax.bar(categories, values)
        ax.set_title(f"{row['議題']}")
        ax.set_ylabel("比例 (%)")
        ax.set_ylim(0, 100)
        for i, v in enumerate(values):
            ax.text(i, v + 1, f"{v:.2f}%", ha="center")
        st.pyplot(fig)
