import streamlit as st
import pandas as pd
import qrcode
import io
import zipfile
import os
import datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# === 初始化資料 ===
if "topics" not in st.session_state:
    st.session_state["topics"] = []
if "votes" not in st.session_state:
    st.session_state["votes"] = {}
if "vote_counts" not in st.session_state:
    st.session_state["vote_counts"] = {}
if "deadline" not in st.session_state:
    st.session_state["deadline"] = None
if "announcement_mode" not in st.session_state:
    st.session_state["announcement_mode"] = False
if "last_update" not in st.session_state:
    st.session_state["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# === 標題 ===
st.set_page_config(page_title="社區投票系統", layout="wide")

st.sidebar.title("🏘️ 社區投票系統")
menu = st.sidebar.selectbox(
    "功能選擇",
    ["🏠 住戶投票", "🔐 管理員登入", "🧾 管理後台"]
)

# === QR Code 產生輔助函式 ===
def generate_qr_png_bytes_with_text(url, unit):
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # 繪製文字
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except:
        font = ImageFont.load_default()
    line = f"戶號：{unit}"

    # ✅ Pillow >=10.0 相容寫法
    bbox = draw.textbbox((0, 0), line, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    iw, ih = img.size

    # 建立新畫布並加入下方文字
    new_img = Image.new("RGB", (iw, ih + th + 15), "white")
    new_img.paste(img, (0, 0))
    draw = ImageDraw.Draw(new_img)
    draw.text(((iw - tw) // 2, ih + 5), line, fill="black", font=font)

    buf = BytesIO()
    new_img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def generate_qr_zip_from_units(base_url, df):
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _, row in df.iterrows():
            unit = str(row["戶號"])
            qr_url = f"{base_url}/?unit={unit}"
            png = generate_qr_png_bytes_with_text(qr_url, unit)
            zf.writestr(f"{unit}.png", png)
    mem_zip.seek(0)
    return mem_zip


# === 頁面 1：住戶投票 ===
def show_resident_page():
    st.header("🏠 住戶投票")

    unit = st.text_input("請輸入戶號以進行投票")
    if not st.session_state["topics"]:
        st.warning("目前尚未建立任何議題。")
        return

    if unit:
        # 如果截止時間已過 → 公告模式
        if st.session_state["announcement_mode"]:
            st.success(f"📢 投票已截止。以下為最終統計（統計時間 {st.session_state['last_update']}）")
            show_statistics()
            return

        # 投票操作
        for idx, topic in enumerate(st.session_state["topics"]):
            st.subheader(f"{idx+1}. {topic}")
            vote = st.radio("請選擇您的意見：", ["同意", "不同意"], key=f"vote_{idx}")
            if st.button(f"提交第 {idx+1} 題投票", key=f"submit_{idx}"):
                if unit in st.session_state["votes"] and idx in st.session_state["votes"][unit]:
                    st.warning("⚠️ 您已經對此議題投過票。")
                else:
                    if unit not in st.session_state["votes"]:
                        st.session_state["votes"][unit] = {}
                    st.session_state["votes"][unit][idx] = vote
                    if idx not in st.session_state["vote_counts"]:
                        st.session_state["vote_counts"][idx] = {"同意": 0, "不同意": 0}
                    st.session_state["vote_counts"][idx][vote] += 1
                    st.success(f"✅ 您的投票「{vote}」已提交！")

        # 自動公告模式檢查
        check_deadline()

# === 頁面 2：管理員登入 ===
def show_admin_login():
    st.header("🔐 管理員登入")

    # 嘗試讀取 admin_config.json
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

# === 頁面 3：管理後台 ===
def show_admin_dashboard():
    if not st.session_state.get("is_admin"):
        st.warning("請先登入管理員帳號。")
        return

    st.header("🧾 管理後台")

    # 上傳議題
    topic_file = st.file_uploader("上傳議題檔（.xlsx）", type="xlsx")
    if topic_file:
        df = pd.read_excel(topic_file)
        st.session_state["topics"] = df.iloc[:, 0].tolist()
        st.session_state["vote_counts"] = {
            i: {"同意": 0, "不同意": 0} for i in range(len(df))
        }
        st.success(f"已儲存 {len(df)} 題議題")

    # 顯示目前議題
    if st.session_state["topics"]:
        for i, t in enumerate(st.session_state["topics"]):
            st.write(f"{i+1}. {t}")

    # 上傳住戶清單
    st.subheader("🏡 上傳住戶清單（需欄位「戶號」）")
    dfu_file = st.file_uploader("上傳住戶清單", type="xlsx")
    if dfu_file:
        dfu = pd.read_excel(dfu_file)
        st.session_state["units"] = dfu
        st.success(f"已儲存 {len(dfu)} 戶資料")

        base_url = st.text_input("網站基本 URL", value="https://smartvoteapp.onrender.com")
        if st.button("📦 產生 QR Code ZIP"):
            try:
                zip_data = generate_qr_zip_from_units(base_url, dfu)
                st.download_button(
                    label="⬇️ 下載 QR Code ZIP",
                    data=zip_data,
                    file_name="qr_codes.zip",
                    mime="application/zip"
                )
                st.success("✅ 已完成 QR Code ZIP 產生")
            except Exception as e:
                st.error(f"產生 QR Code 時發生錯誤：{e}")

    # 截止時間設定
    st.subheader("📅 投票截止時間設定")
    deadline = st.datetime_input("設定截止時間", value=st.session_state["deadline"])
    if st.button("儲存截止時間"):
        st.session_state["deadline"] = deadline
        st.success(f"截止時間已設定為 {deadline}")

    # 統計區塊
    st.subheader("📈 投票結果統計（每 10 秒自動更新）")
    show_statistics()


# === 統計顯示 ===
def show_statistics():
    import time
    if not st.session_state["vote_counts"]:
        st.info("目前尚無投票資料。")
        return

    for i, topic in enumerate(st.session_state["topics"]):
        data = st.session_state["vote_counts"].get(i, {"同意": 0, "不同意": 0})
        st.write(f"**{i+1}. {topic}**")
        st.progress(data["同意"] / (sum(data.values()) + 0.0001))
        st.write(f"🟩 同意：{data['同意']}　🟥 不同意：{data['不同意']}")
    st.session_state["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.caption(f"⏱️ 統計時間 {st.session_state['last_update']}")
    st_autorefresh(interval=10_000, key="refresh_stat")


# === 自動刷新 ===
def st_autorefresh(interval=10000, key=None):
    st.markdown(
        f"""
        <meta http-equiv="refresh" content="{interval / 1000}">
        """,
        unsafe_allow_html=True,
    )


# === 截止時間檢查 ===
def check_deadline():
    if st.session_state["deadline"] and datetime.datetime.now() > st.session_state["deadline"]:
        st.session_state["announcement_mode"] = True
        st.session_state["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# === 主選單切換 ===
if menu == "🏠 住戶投票":
    show_resident_page()
elif menu == "🔐 管理員登入":
    show_admin_login()
elif menu == "🧾 管理後台":
    show_admin_dashboard()
