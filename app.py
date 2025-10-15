import streamlit as st
import pandas as pd
import qrcode
import io
import zipfile
import json
import os
from datetime import datetime, timedelta
import time as t
from PIL import Image, ImageDraw, ImageFont
import streamlit.components.v1 as components
from pytz import timezone
from streamlit_autorefresh import st_autorefresh

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
VOTING_STATUS_FILE = os.path.join(DATA_DIR, "voting_status.json")

# 初始化 voting status
if not os.path.exists(VOTING_STATUS_FILE):
    with open(VOTING_STATUS_FILE, "w") as f:
        json.dump({"open": False}, f)

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


def read_voting_status():
    try:
        with open(VOTING_STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"open": False}


def write_voting_status(status: bool):
    with open(VOTING_STATUS_FILE, "w") as f:
        json.dump({"open": bool(status)}, f)


def generate_qr_codes(base_url, households):
    """產生每戶 QR Code 並打包成 zip，且在圖片下方標示戶號"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for _, row in households.iterrows():
            unit = str(row["戶號"])
            url = f"{base_url}?unit={unit}"
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except Exception:
                font = ImageFont.load_default()

            text = f"戶號: {unit}"
            try:
                text_w, text_h = draw.textsize(text, font=font)
            except Exception:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]

            img_w, img_h = img.size
            padding = 8
            new_h = img_h + text_h + padding * 2
            new_img = Image.new("RGB", (img_w, new_h), "white")
            new_img.paste(img, (0, 0))
            draw2 = ImageDraw.Draw(new_img)
            text_x = (img_w - text_w) // 2
            text_y = img_h + padding
            draw2.text((text_x, text_y), text, fill=(0, 0, 0), font=font)

            img_byte = io.BytesIO()
            new_img.save(img_byte, format="PNG")
            img_byte.seek(0)
            safe_name = unit.replace("/", "_").replace("\\", "_").replace(" ", "_")
            zipf.writestr(f"{safe_name}.png", img_byte.read())
    zip_buffer.seek(0)
    return zip_buffer


def current_time_str_server():
    tz = timezone("Asia/Taipei")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

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

    # 投票開關
    st.subheader("🔁 投票控制")
    status = read_voting_status()
    st.write(f"目前投票狀態：**{'開啟' if status.get('open') else '關閉'}**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ 開啟投票"):
            write_voting_status(True)
            st.success("投票已開啟")
    with col2:
        if st.button("⏹ 停止投票"):
            write_voting_status(False)
            st.success("投票已停止")

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

    # 設定截止時間
    st.subheader("📅 設定投票截止時間（以現在起算）")
    minutes_option = st.selectbox("選擇距今的截止時間（分鐘）", [5,10,15,20,25,30], index=2)
    if st.button("💾 設定截止時間（從現在起）"):
        cutoff_dt = datetime.now(timezone("Asia/Taipei")) + timedelta(minutes=int(minutes_option))
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
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
        base_url = st.text_input("投票網站基本網址（請包含 https://）", "https://smartvoteapp.onrender.com")
        st.info("網址會自動加上戶號參數，例如：https://smartvoteapp.onrender.com?unit=A1-3F")

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
    count = st_autorefresh(interval=10 * 1000, key="datarefresh")

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
                agree_count = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "同意")].shape[0]
                disagree_count = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "不同意")].shape[0]
                result_list.append({
                    "議題": topic,
                    "同意比例": round(agree_sum, 4),
                    "不同意比例": round(disagree_sum, 4),
                    "同意人數": int(agree_count),
                    "不同意人數": int(disagree_count)
                })
            df_result = pd.DataFrame(result_list)
            st.dataframe(df_result)
            st.caption(f"統計時間（伺服器）：{current_time_str_server()}")
        else:
            st.info("尚無投票紀錄或議題資料。")
    else:
        st.info("尚未有投票資料。")

# ===============================
# 住戶投票頁
# ===============================

def voter_page():
    # 嘗試取得戶號
    try:
        unit = st.query_params.get("unit")
    except Exception:
        qp = st.experimental_get_query_params()
        unit = qp.get("unit", [None])[0] if "unit" in qp else None

    if not unit:
        st.error("❌ 無法辨識戶號，請使用正確的 QR Code 連結進入。")
        return

    st.title("📮 投票頁面")
    st.write(f"👤 戶號：**{unit}**")
    st.caption("系統時間（伺服器）: " + current_time_str_server())

    components.html("""
    <div id='client-time'></div>
    <script>
    function update(){
      const el = document.getElementById('client-time');
      el.innerText = new Date().toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
    }
    update();
    setInterval(update,1000);
    </script>
    """, height=50)

    voting_status = read_voting_status()
    if not voting_status.get("open"):
        st.warning("目前投票未開啟，請聯絡管理員。")
        return

    if os.path.exists(CUTOFF_FILE):
        with open(CUTOFF_FILE, "r") as f:
            cutoff_str = f.read().strip()
        try:
            cutoff_time = datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S")
            if datetime.now(timezone("Asia/Taipei")) > cutoff_time:
                st.warning(f"📢 投票已截止（截止時間：{cutoff_str}）")
                show_final_results()
                return
        except Exception:
            st.error("截止時間格式錯誤，請聯絡管理員。")
            return

    df_topic = load_data(TOPIC_FILE, ["議題"])
    if len(df_topic) == 0:
        st.info("尚未設定投票議題。")
        return

    df_vote = load_data(VOTE_FILE, ["戶號", "議題", "投票"]) if os.path.exists(VOTE_FILE) else pd.DataFrame(columns=["戶號", "議題", "投票"])
    voted_topics = df_vote[df_vote["戶號"] == unit]["議題"].tolist()

    st.markdown("請對下列所有議題選擇「同意/不同意」，完成後按「一次送出」")

    with st.form(key="vote_form"):
        choices = {}
        for topic in df_topic["議題"]:
            if topic in voted_topics:
                prev = df_vote[(df_vote["戶號"] == unit) & (df_vote["議題"] == topic)]["投票"].values[0]
                st.info(f"您已投票：{topic} -> {prev}")
            else:
                choices[topic] = st.radio(f"{topic}", ["同意", "不同意"], key=f"vote_{topic}")
        submit = st.form_submit_button("一次送出所有投票")
        if submit:
            for topic, choice in choices.items():
                df_vote.loc[len(df_vote)] = [unit, topic, choice]
            save_data(df_vote, VOTE_FILE)
            st.success("✅ 已成功送出所有投票。感謝您的參與！")
            st.rerun()

# ===============================
# 公告顯示
# ===============================

def show_final_results():
    st.header("📢 投票結果公告")

    df_vote = load_data(VOTE_FILE, ["戶號", "議題", "投票"]) if os.path.exists(VOTE_FILE) else pd.DataFrame()
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
        agree_count = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "同意")].shape[0]
        disagree_count = merged.loc[(merged["議題"] == topic) & (merged["投票"] == "不同意")].shape[0]
        result_list.append({
            "議題": topic,
            "同意比例": round(agree_sum, 4),
            "不同意比例": round(disagree_sum, 4),
            "同意人數": int(agree_count),
            "不同意人數": int(disagree_count)
        })
    df_result = pd.DataFrame(result_list)
    st.dataframe(df_result)
    st.caption(f"統計時間（伺服器）：{current_time_str_server()}")

# ===============================
# 主邏輯
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
