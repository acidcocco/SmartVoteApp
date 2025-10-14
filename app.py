# app.py - SmartVoteApp 完整版（部署於 https://smartvoteapp.onrender.com）
import streamlit as st
import pandas as pd
import qrcode
import io
import os
import zipfile
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import urlencode
from streamlit_autorefresh import st_autorefresh
import pytz
import plotly.express as px
from PIL import Image, ImageDraw, ImageFont

# ==============================
# 基本設定（固定為你提供的部署網址）
# ==============================
BASE_URL = "https://smartvoteapp.onrender.com"
DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "votes.db")
os.makedirs(DATA_DIR, exist_ok=True)
TZ = pytz.timezone("Asia/Taipei")

# ==============================
# 管理員帳號設定（你要求的帳號密碼）
# ==============================
admin_accounts = {
    "acidcocco": "131105"
}

# ==============================
# 初始化資料庫（votes, settings）
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            end_time TEXT,
            is_active INTEGER DEFAULT 1,
            note TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==============================
# DB 輔助函式
# ==============================
def get_conn():
    return sqlite3.connect(DB_PATH)

def add_setting(end_time_dt, is_active=1, note=None):
    conn = get_conn()
    c = conn.cursor()
    created = datetime.now(TZ).isoformat()
    iso = end_time_dt.isoformat() if end_time_dt is not None else None
    c.execute("INSERT INTO settings (end_time, is_active, note, created_at) VALUES (?, ?, ?, ?)",
              (iso, int(is_active), note, created))
    conn.commit()
    conn.close()

def update_setting_active(new_active, note=None):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT end_time FROM settings ORDER BY id DESC LIMIT 1").fetchone()
    end_time_iso = row[0] if row else None
    created = datetime.now(TZ).isoformat()
    c.execute("INSERT INTO settings (end_time, is_active, note, created_at) VALUES (?, ?, ?, ?)",
              (end_time_iso, int(new_active), note, created))
    conn.commit()
    conn.close()

def get_latest_setting():
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT end_time, is_active FROM settings ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        end_time_iso, is_active = row
        if end_time_iso:
            try:
                dt = datetime.fromisoformat(end_time_iso)
            except Exception:
                # 無法解析就視為 None
                return None, 1
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
            return dt, int(is_active)
    return None, 1

def save_votes_sql(records):
    """
    records: list of tuples (戶號, 議題, 選項, 區分比例, iso_time)
    使用 INSERT OR REPLACE 防止同一戶同議題重複
    """
    conn = get_conn()
    c = conn.cursor()
    for r in records:
        c.execute("""
            INSERT OR REPLACE INTO votes (戶號, 議題, 選項, 區分比例, 時間)
            VALUES (?, ?, ?, ?, ?)
        """, r)
    conn.commit()
    conn.close()

def fetch_votes_df():
    conn = get_conn()
    try:
        df = pd.read_sql("SELECT * FROM votes", conn)
    except Exception:
        df = pd.DataFrame(columns=["戶號","議題","選項","區分比例","時間"])
    conn.close()
    return df

def has_voted(unit):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM votes WHERE 戶號 = ?", (unit,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

# ==============================
# 檔案與 Excel 讀取防呆
# ==============================
def safe_read_excel(path):
    if not os.path.exists(path):
        return None
    try:
        if os.path.getsize(path) == 0:
            return None
        return pd.read_excel(path)
    except Exception as e:
        # 不拋出錯誤，回傳 None
        return None

# ==============================
# 產生 QR（含上方文字）
# ==============================
def generate_qr_with_text(unit, help_text="議題討論後掃瞄QR Code進行投票"):
    """
    回傳 PNG bytes。圖上方顯示戶號與說明文字（兩行）
    """
    # 先產生 QR 圖
    params = {"戶號": unit}
    url = f"{BASE_URL}/?{urlencode(params)}"
    qr = qrcode.make(url).convert("RGB")
    qr_w, qr_h = qr.size

    # 建立字體（使用預設載入字型）
    try:
        # 嘗試載入較好看的字體（若環境有）
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    # 建立上方文字影像
    text_lines = [f"戶號：{unit}", help_text]
    # 計算文字高度
    max_w = 0
    total_h = 0
    line_heights = []
    for ln in text_lines:
        (w, h) = font.getsize(ln)
        if w > max_w: max_w = w
        line_heights.append(h)
        total_h += h + 4
    padding = 10
    canvas_w = max(qr_w, max_w + padding*2)
    canvas_h = total_h + qr_h + padding*2

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(canvas)

    # 計算文字起始 y
    current_y = padding
    for i, ln in enumerate(text_lines):
        w, h = font.getsize(ln)
        x = (canvas_w - w)//2
        draw.text((x, current_y), ln, fill="black", font=font)
        current_y += line_heights[i] + 4

    # paste QR under text, centered
    qr_x = (canvas_w - qr_w)//2
    canvas.paste(qr, (qr_x, current_y + padding//2))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================
# Streamlit UI
# ==============================
st.set_page_config(page_title="SmartVoteApp", layout="wide")
st.title("🗳️ SmartVoteApp 投票系統")

# query params
try:
    qp = st.experimental_get_query_params()
except Exception:
    qp = st.query_params.to_dict()
qp = {k: v[0] if isinstance(v, list) else v for k, v in qp.items()}
is_admin_q = qp.get("admin", "false").lower() == "true"
unit_q = qp.get("戶號") or qp.get("unit") or qp.get("unit_id")

# Session 管理
if "admin" not in st.session_state:
    st.session_state.admin = False
if "admin_user" not in st.session_state:
    st.session_state.admin_user = None

# ------------------------------
# 側欄選單（簡單）
# ------------------------------
page = st.sidebar.selectbox("功能選單", ["首頁", "住戶投票", "管理員登入", "管理後台"])

# ==============================
# 首頁
# ==============================
if page == "首頁":
    st.info("請透過 QR Code 進入投票頁面（網址包含 ?戶號=xxx），或於側邊選單選擇「管理員登入」。")

# ==============================
# 住戶投票
# ==============================
elif page == "住戶投票" or unit_q:
    # 若從 QR 連過來（query param 有戶號），優先使用
    unit = unit_q if unit_q else None
    if page == "住戶投票":
        # 或者讓使用者手動輸入戶號（方便測試）
        unit = st.text_input("請輸入戶號（或從 QR 連結進入）", value="")
        unit = unit.strip() if unit else None

    if not unit:
        st.warning("請使用 QR Code 進入投票頁面（網址包含 ?戶號=xxx）或於此輸入戶號測試。")
        st.stop()

    # 讀取議題與戶號清單
    issues_path = os.path.join(DATA_DIR, "議題清單.xlsx")
    units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
    issues_df = safe_read_excel(issues_path)
    units_df = safe_read_excel(units_path)

    if issues_df is None or units_df is None:
        st.warning("尚未由管理員上傳議題或戶號清單（或檔案損壞）。請聯絡管理員。")
        st.stop()

    # 正常化議題欄位
    if "議題名稱" in issues_df.columns:
        issues = issues_df["議題名稱"].astype(str).tolist()
    else:
        issues = issues_df.iloc[:, 0].astype(str).tolist()

    # 判斷戶號是否存在
    if str(unit) not in units_df.iloc[:,0].astype(str).values:
        st.error("查無此戶號，請確認 QR Code 或聯絡管理員。")
        st.stop()

    latest_end, latest_active = get_latest_setting()
    if latest_end is None:
        st.warning("尚未設定投票截止時間，請聯絡管理員。")
        st.stop()

    if latest_end.tzinfo is None:
        latest_end = TZ.localize(latest_end)
    latest_end_local = latest_end.astimezone(TZ)
    now_local = datetime.now(TZ)

    if latest_active == 0 or now_local >= latest_end_local:
        st.warning("投票已截止或被管理員停止，感謝您的參與。")
        st.stop()

    if has_voted(unit):
        st.success("您已完成投票，感謝您的參與。")
        st.stop()

    st.header(f"🏠 戶號 {unit} 投票頁面")
    st.info(f"投票截止時間（台北）：{latest_end_local.strftime('%Y-%m-%d %H:%M:%S')}")
    st.write("請為下列議題選擇意見（同一戶一次送出）：")

    choices = {}
    with st.form("vote_form"):
        for idx, it in enumerate(issues):
            choices[f"q_{idx}"] = st.radio(it, ["同意", "不同意"], horizontal=True, key=f"q_{idx}")
        submitted = st.form_submit_button("📤 送出投票")

    if submitted:
        # 嘗試讀取該戶的比例（若存在）
        user_row = units_df[units_df.iloc[:,0].astype(str) == str(unit)]
        ratio = 1.0
        if not user_row.empty and user_row.shape[1] >= 2:
            try:
                ratio = float(user_row.iloc[0, 1])
            except Exception:
                ratio = 1.0
        iso_time = datetime.now(TZ).isoformat()
        recs = []
        for idx, it in enumerate(issues):
            choice = choices.get(f"q_{idx}")
            recs.append((str(unit), it, choice, ratio, iso_time))
        save_votes_sql(recs)
        st.success("✅ 投票已送出，謝謝您的參與！")
        st.rerun()

# ==============================
# 管理員登入
# ==============================
elif page == "管理員登入":
    st.header("🔐 管理員登入")
    if not st.session_state.admin:
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        if st.button("登入"):
            if username in admin_accounts and password == admin_accounts[username]:
                st.session_state.admin = True
                st.session_state.admin_user = username
                st.success(f"登入成功 ✅（{username}）")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤 ❌")
    else:
        st.success(f"您已登入：{st.session_state.admin_user}")
        if st.button("登出"):
            st.session_state.admin = False
            st.session_state.admin_user = None
            st.info("已登出")
            st.rerun()

# ==============================
# 管理後台
# ==============================
elif page == "管理後台":
    st.header("👨‍💼 管理員後台")
    if not st.session_state.get("admin"):
        st.warning("請先登入管理員帳號")
        st.stop()

    # 上傳議題與戶號
    col1, col2 = st.columns(2)
    with col1:
        uploaded_issues = st.file_uploader("📘 上傳議題清單（Excel，欄位：議題名稱 或 第一欄）", type=["xlsx"])
    with col2:
        uploaded_units = st.file_uploader("🏠 上傳戶號清單（Excel，欄位：戶號、區分比例(可選)）", type=["xlsx"])

    # 儲存上傳
    if uploaded_issues:
        issues_path = os.path.join(DATA_DIR, "議題清單.xlsx")
        with open(issues_path, "wb") as f:
            f.write(uploaded_issues.getvalue())
        st.success("已儲存議題清單（data/議題清單.xlsx）")
    if uploaded_units:
        units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
        with open(units_path, "wb") as f:
            f.write(uploaded_units.getvalue())
        st.success("已儲存戶號清單（data/戶號清單.xlsx）")

    st.markdown("---")
    # 顯示現在時間
    now = datetime.now(TZ)
    st.info(f"🕒 現在時間（台北）：{now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 設定截止時間（日期 + 時間）
    st.subheader("📅 設定投票截止時間（台北時區）")
    default_minutes = 60
    minutes = st.number_input("從現在起多少分鐘後截止？（輸入整數，範例：60）", min_value=1, max_value=7*24*60, value=default_minutes, step=5)
    computed_deadline = now + timedelta(minutes=int(minutes))
    st.caption(f"計算後截止時間：{computed_deadline.strftime('%Y-%m-%d %H:%M:%S')}")
    if st.button("✅ 設定截止時間並啟用投票"):
        add_setting(computed_deadline, is_active=1)
        st.success("已新增設定並啟用投票（設定會保留為歷史紀錄）。")

    col_stop, col_start = st.columns(2)
    with col_stop:
        if st.button("🛑 停止投票（管理員）"):
            update_setting_active(0)
            st.warning("管理員已停止投票（新增紀錄）。")
    with col_start:
        if st.button("▶️ 啟用投票（保留最新截止時間）"):
            latest_end, latest_active = get_latest_setting()
            if latest_end is None:
                st.error("尚未設定截止時間，請先設定截止時間。")
            else:
                update_setting_active(1)
                st.success("已啟用投票（新增紀錄）。")

    st.markdown("---")
    # 產生 QR Code ZIP（若已上傳戶號）
    units_df = safe_read_excel(os.path.join(DATA_DIR, "戶號清單.xlsx"))
    if units_df is not None:
        if st.button("🧾 產生戶號專屬 QR Code（ZIP）"):
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for _, r in units_df.iterrows():
                    unit_val = str(r.iloc[0])
                    png_buf = generate_qr_with_text(unit_val, help_text="議題討論後掃瞄QR Code進行投票")
                    zf.writestr(f"{unit_val}.png", png_buf.getvalue())
            zip_buf.seek(0)
            st.download_button("⬇️ 下載 QR Code ZIP", zip_buf, file_name="QRCode_AllUnits.zip", mime="application/zip")
    else:
        st.info("尚未上傳戶號清單，無法產生 QR Code。")

    st.markdown("---")
    # 統計與圖表、匯出
    st.subheader("📊 投票統計與圖表")

    votes_df = fetch_votes_df()
    issues_df = safe_read_excel(os.path.join(DATA_DIR, "議題清單.xlsx"))
    units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")

    if os.path.exists(units_path) and issues_df is not None and not votes_df.empty:
        units_df = safe_read_excel(units_path)
        # 嘗試自動找到比例欄位（若上傳有分攤比例欄）
        ratio_col_candidate = None
        if units_df is not None:
            for c in units_df.columns:
                if "比例" in c or "比率" in c or "持分" in c or "比例" in str(c):
                    ratio_col_candidate = c
                    break

        merged = votes_df.merge(units_df, left_on="戶號", right_on=units_df.columns[0].astype(str), how="left")
        # 以 units_df 第一欄為戶號欄名比對（保持彈性）
        total_units = units_df.iloc[:,0].nunique()
        results = []
        for issue in issues_df.iloc[:,0].astype(str).unique():
            d = merged[merged["議題"] == issue]
            agree = d[d["選項"] == "同意"]
            disagree = d[d["選項"] == "不同意"]
            voted_units = d["戶號"].nunique()
            unvote = int(total_units - voted_units)

            # 比例計算：若有比例欄則用該欄加總作為權重，否則以人數比例計算
            if ratio_col_candidate is not None:
                try:
                    # 把 agree/disagree 的比例相加，並除以總持分
                    total_ratio = units_df.iloc[:,1].sum() if units_df.shape[1] >= 2 else total_units
                    agree_ratio_sum = 0
                    disagree_ratio_sum = 0
                    # 若 merged 在比例欄位位置與 units_df 第二欄不同名稱，嘗試使用 index 1
                    if units_df.shape[1] >= 2:
                        # merged may have duplicate columns; safer to use original units_df mapping:
                        # Build dict: 戶號 -> ratio
                        try:
                            ratio_map = {str(row[units_df.columns[0]]): float(row[units_df.columns[1]]) for _, row in units_df.iterrows()}
                        except Exception:
                            ratio_map = {}
                        for _, rr in agree.iterrows():
                            ratio_val = ratio_map.get(str(rr["戶號"]), 1.0)
                            try:
                                agree_ratio_sum += float(ratio_val)
                            except Exception:
                                agree_ratio_sum += 1.0
                        for _, rr in disagree.iterrows():
                            ratio_val = ratio_map.get(str(rr["戶號"]), 1.0)
                            try:
                                disagree_ratio_sum += float(ratio_val)
                            except Exception:
                                disagree_ratio_sum += 1.0
                        if total_ratio == 0:
                            agree_pct = 0.0
                            disagree_pct = 0.0
                        else:
                            agree_pct = agree_ratio_sum / total_ratio * 100
                            disagree_pct = disagree_ratio_sum / total_ratio * 100
                    else:
                        # fallback to simple count ratio
                        agree_pct = (len(agree) / total_units * 100) if total_units>0 else 0
                        disagree_pct = (len(disagree) / total_units * 100) if total_units>0 else 0
                except Exception:
                    agree_pct = (len(agree) / total_units * 100) if total_units>0 else 0
                    disagree_pct = (len(disagree) / total_units * 100) if total_units>0 else 0
            else:
                agree_pct = (len(agree) / total_units * 100) if total_units>0 else 0
                disagree_pct = (len(disagree) / total_units * 100) if total_units>0 else 0

            results.append({
                "議題": issue,
                "同意人數": int(len(agree)),
                "不同意人數": int(len(disagree)),
                "未投票戶數": int(unvote),
                "同意比例(%)": round(float(agree_pct), 2),
                "不同意比例(%)": round(float(disagree_pct), 2)
            })

        stat_df = pd.DataFrame(results)
        st.dataframe(stat_df, use_container_width=True)

        # 長條圖（每題）使用 Plotly
        st.markdown("### 各題比例比較（長條圖）")
        bar_fig = px.bar(stat_df, x="議題", y=["同意比例(%)", "不同意比例(%)"],
                         barmode="group", title="各議題投票比例 (%)")
        st.plotly_chart(bar_fig, use_container_width=True)

        # 同時顯示每題的人數長條圖
        st.markdown("### 各題人數比較（長條圖）")
        count_fig = px.bar(stat_df, x="議題", y=["同意人數", "不同意人數"],
                           barmode="group", title="各議題投票人數")
        st.plotly_chart(count_fig, use_container_width=True)

        # 匯出（CSV/Excel）
        csv_bytes = stat_df.to_csv(index=False).encode("utf-8-sig")
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
            stat_df.to_excel(writer, index=False, sheet_name="投票結果")
            votes_df.to_excel(writer, index=False, sheet_name="raw_votes")
        excel_buf.seek(0)

        st.download_button("📄 匯出 CSV（投票結果）", data=csv_bytes, file_name="投票結果.csv", mime="text/csv")
        st.download_button("📘 匯出 Excel（投票結果 + raw）", data=excel_buf, file_name="投票結果.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("尚無投票資料或未上傳議題/戶號清單。")

    # 管理員可查看原始投票資料（含戶號）
    st.markdown("---")
    st.subheader("📋 投票明細（僅管理員）")
    raw = fetch_votes_df()
    if not raw.empty:
        st.dataframe(raw, use_container_width=True)
    else:
        st.info("尚無投票明細。")
