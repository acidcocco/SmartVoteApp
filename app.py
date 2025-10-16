# app.py
import streamlit as st
import pandas as pd
import qrcode
import io
import zipfile
import json
import os
from datetime import datetime, timedelta
from pytz import timezone
import streamlit.components.v1 as components

# ===============================
# 初始化設定
# ===============================
st.set_page_config(page_title="社區投票系統", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
HOUSEHOLD_FILE = os.path.join(DATA_DIR, "households.csv")
TOPIC_FILE = os.path.join(DATA_DIR, "topics.csv")
VOTE_FILE = os.path.join(DATA_DIR, "votes.csv")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
ENDTIME_FILE = os.path.join(DATA_DIR, "end_time.txt")
ADMIN_FILE = "admin_config.json"

TAIPEI_TZ = timezone("Asia/Taipei")

# ===============================
# Helper functions
# ===============================
def get_taipei_now():
    return datetime.now(TAIPEI_TZ)

def load_csv(file_path):
    if os.path.exists(file_path):
        try:
            return pd.read_csv(file_path, dtype=str)
        except Exception:
            # fallback: try reading with default options
            return pd.read_csv(file_path)
    return pd.DataFrame()

def save_csv(df, file_path):
    df.to_csv(file_path, index=False)

def ensure_admin_file():
    # 如果 admin_config.json 不存在，建立一個範例檔
    if not os.path.exists(ADMIN_FILE):
        sample = {"acidcocco": "131105"}
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)

def load_admins():
    ensure_admin_file()
    with open(ADMIN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {"open": False}
    return {"open": False}

def save_status(status_dict):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status_dict, f, ensure_ascii=False, indent=2)

def generate_qr_zip(households_df, base_url):
    """
    households_df: pandas DataFrame with a column indicating unit/戶號
    base_url: base voting url (e.g. https://example.com)
    returns: BytesIO of zip file or None
    """
    if households_df is None or households_df.empty:
        return None

    # 尋找可能的戶號欄位名稱
    candidates = ["戶號", "unit", "household", "戶號(戶)", "戶號 "]
    col = None
    for c in candidates:
        if c in households_df.columns:
            col = c
            break
    # 如果都沒有，嘗試第一欄
    if col is None:
        col = households_df.columns[0]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, row in households_df.iterrows():
            house_id = str(row[col]).strip()
            if not house_id:
                continue
            qr_link = f"{base_url}?unit={house_id}"
            qr = qrcode.QRCode(box_size=10, border=2)
            qr.add_data(qr_link)
            qr.make(fit=True)
            qr_img = qr.make_image()

            img_bytes = io.BytesIO()
            qr_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            zf.writestr(f"{house_id}.png", img_bytes.read())

    zip_buffer.seek(0)
    return zip_buffer

def format_datetime_taipei(dt: datetime):
    return dt.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")

def save_end_time(dt: datetime):
    # 儲存包含 timezone info 的字串
    with open(ENDTIME_FILE, "w", encoding="utf-8") as f:
        f.write(dt.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S %z"))

def load_end_time():
    if os.path.exists(ENDTIME_FILE):
        with open(ENDTIME_FILE, "r", encoding="utf-8") as f:
            txt = f.read().strip()
            return txt
    return None

# ===============================
# 首頁（顯示固定訊息）
# ===============================
def voter_page():
    st.title("🏠 社區投票系統")
    params = st.experimental_get_query_params()
    unit = None
    if "unit" in params:
        val = params.get("unit")
        if isinstance(val, list) and len(val) > 0:
            unit = val[0]
        elif isinstance(val, str):
            unit = val

    if unit:
        st.info(f"目前登入戶號：{unit}")
        st.success("投票功能目前示範版，請依管理員指示操作。")
    else:
        st.warning("未偵測到戶號參數，請由專屬 QR Code 登入。")
        st.write("請使用管理後台 → 產生 QR Code ZIP，或管理員直接提供含 `?unit=戶號` 的連結。")

# ===============================
# 管理員登入
# ===============================
def admin_login():
    st.header("🔐 管理員登入")
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False
        st.session_state.admin_user = None

    username = st.text_input("帳號", key="admin_username")
    password = st.text_input("密碼", type="password", key="admin_password")

    if st.button("登入"):
        try:
            admins = load_admins()
        except Exception as e:
            st.error(f"讀取 admin_config.json 失敗：{e}")
            return

        if username in admins and str(password) == str(admins[username]):
            st.session_state.is_admin = True
            st.session_state.admin_user = username
            st.success(f"登入成功！歡迎管理員 {username}")
        else:
            st.error("帳號或密碼錯誤。")

# ===============================
# 管理後台（功能順序與要求）
# ===============================
def admin_dashboard():
    st.title("🧩 管理後台")
    st.write(f"管理員：{st.session_state.get('admin_user', '')}")

    # 1️⃣ 投票控制（開啟 / 停止）
    st.subheader("1️⃣ 投票控制")
    status = load_status()
    col1, col2 = st.columns([1, 2])
    with col1:
        current_state_text = "開啟中" if status.get("open", False) else "已停止"
        st.markdown(f"**目前狀態：** {current_state_text}")
    with col2:
        if st.button("開啟投票"):
            status["open"] = True
            save_status(status)
            st.success("投票已開啟。")
        if st.button("停止投票"):
            status["open"] = False
            save_status(status)
            st.info("投票已停止。")

    st.markdown("---")

    # 2️⃣ 上傳住戶清單
    st.subheader("2️⃣ 上傳住戶清單 (households.csv)")
    uploaded_households = st.file_uploader("選擇 households.csv", type=["csv"], key="upload_households")
    if uploaded_households is not None:
        try:
            df = pd.read_csv(uploaded_households, dtype=str)
            # 存檔
            save_csv(df, HOUSEHOLD_FILE)
            st.success("✅ 住戶清單已上傳並儲存。")
            st.write("預覽前 5 筆：")
            st.dataframe(df.head(5))
        except Exception as e:
            st.error(f"讀取或儲存 households.csv 失敗：{e}")

    st.markdown("---")

    # 3️⃣ 上傳議題清單
    st.subheader("3️⃣ 上傳議題清單 (topics.csv)")
    uploaded_topics = st.file_uploader("選擇 topics.csv", type=["csv"], key="upload_topics")
    if uploaded_topics is not None:
        try:
            df = pd.read_csv(uploaded_topics, dtype=str)
            save_csv(df, TOPIC_FILE)
            st.success("✅ 議題清單已上傳並儲存。")
            st.write("預覽前 5 筆：")
            st.dataframe(df.head(5))
        except Exception as e:
            st.error(f"讀取或儲存 topics.csv 失敗：{e}")

    st.markdown("---")

    # 4️⃣ 住戶 QR Code 投票連結與 ZIP 產生
    st.subheader("4️⃣ 住戶 QR Code 投票連結與 ZIP 產生")
    base_url = st.text_input("投票網站基本網址（請包含 https://，預設可改）", "https://smartvoteapp.onrender.com", key="base_url")
    if st.button("📦 產生 QR Code ZIP"):
        households_df = load_csv(HOUSEHOLD_FILE)
        if households_df is None or households_df.empty:
            st.error("請先上傳 households.csv，或確認檔案內有可用之戶號欄位。")
        else:
            zip_buf = generate_qr_zip(households_df, base_url)
            if zip_buf:
                st.session_state["qr_zip_bytes"] = zip_buf.getvalue()
                st.success("✅ QR Code ZIP 產生完成！請按下方下載。")
            else:
                st.error("產生 ZIP 失敗（可能所有戶號欄位為空）。")

    if "qr_zip_bytes" in st.session_state:
        st.download_button(
            label="📥 下載 QR Code ZIP",
            data=st.session_state["qr_zip_bytes"],
            file_name="QR_Codes.zip",
            mime="application/zip"
        )

    st.markdown("---")

    # 5️⃣ 設定投票截止時間（台北時區）
    st.subheader("5️⃣ 設定投票截止時間 (台北時間)")
    now = get_taipei_now = get_taipei_now = get_taipei_now if False else None  # placeholder to satisfy linter in some environments
    now = datetime.now(TAIPEI_TZ)
    default_end = now + timedelta(days=1)
    # Streamlit datetime_input expects a naive datetime or timezone-aware depending on environment.
    end_time = st.datetime_input("截止時間 (台北時間)", value=default_end)
    if st.button("儲存截止時間"):
        try:
            # make timezone-aware and save
            # If user-provided datetime has no tzinfo, localize to Taipei
            if end_time.tzinfo is None:
                end_time = TAIPEI_TZ.localize(end_time)
            save_end_time(end_time)
            st.success(f"截止時間已設定為 {format_datetime_taipei(end_time)} (台北時間)")
        except Exception as e:
            st.error(f"儲存失敗：{e}")

    saved_end = load_end_time()
    if saved_end:
        st.info(f"目前儲存的截止時間：{saved_end}")

    st.markdown("---")

    # 6️⃣ 📈 投票結果統計（同意/不同意人數 + 比例，保留4位小數，自動更新選項）
    st.subheader("6️⃣ 📈 投票結果統計")
    st.write("顯示：同意 / 不同意 人數與比例（4 位小數）")

    auto_refresh = st.checkbox("自動每 10 秒更新（整頁重新載入）", value=False, key="auto_refresh_stats")
    if auto_refresh:
        # 注入 JS 在 10 秒後 reload 整頁（簡單直接）
        components.html(
            """
            <script>
            setTimeout(() => { window.location.reload(); }, 10000);
            </script>
            """,
            height=0
        )

    votes_df = load_csv(VOTE_FILE)
    if votes_df is None or votes_df.empty:
        st.info("目前尚無投票資料（votes.csv 為空或不存在）。")
    else:
        # 假設 votes.csv 含有欄位 'vote' 或 '選擇'，內容可能為 '同意' / '不同意' 或 'agree'/'disagree'
        vcol = None
        for c in ["vote", "選擇", "選項", "vote_choice"]:
            if c in votes_df.columns:
                vcol = c
                break
        if vcol is None:
            # 若沒有明確欄位，嘗試第一欄
            vcol = votes_df.columns[0]

        # 標準化內容
        def normalize_choice(x):
            if pd.isna(x):
                return "未知"
            s = str(x).strip().lower()
            if s in ["同意", "agree", "yes", "y", "1", "a"]:
                return "同意"
            if s in ["不同意", "disagree", "no", "n", "0", "d"]:
                return "不同意"
            return str(x).strip()

        votes_df["__choice__"] = votes_df[vcol].apply(normalize_choice)

        total = len(votes_df)
        agree_count = int((votes_df["__choice__"] == "同意").sum())
        disagree_count = int((votes_df["__choice__"] == "不同意").sum())
        other_count = total - agree_count - disagree_count

        def safe_prop(cnt, tot):
            if tot == 0:
                return 0.0
            return round(cnt / tot, 4)

        agree_prop = safe_prop(agree_count, total)
        disagree_prop = safe_prop(disagree_count, total)
        other_prop = safe_prop(other_count, total)

        st.metric("總投票數", total)
        cols = st.columns(3)
        cols[0].metric("同意 人數", agree_count, f"{agree_prop:.4f}")
        cols[1].metric("不同意 人數", disagree_count, f"{disagree_prop:.4f}")
        cols[2].metric("其他/未分類 人數", other_count, f"{other_prop:.4f}")

        st.write("詳細表（前 200 筆）")
        st.dataframe(votes_df.head(200))

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
    # 確保 admin_config.json 存在（若不存在會建立示範帳號）
    ensure_admin_file()
    main()
