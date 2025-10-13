# app.py - SmartVoteApp 最終穩定修正版 v2（移除歷史紀錄 + Excel防呆）
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

# ==============================
# 基本設定
# ==============================
BASE_URL = os.environ.get("BASE_URL", "https://acidcocco.onrender.com")
DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "votes.db")
os.makedirs(DATA_DIR, exist_ok=True)
TZ = pytz.timezone("Asia/Taipei")

# ==============================
# 初始化資料庫
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
# 資料庫輔助函式
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
                return None, 1
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
            return dt, int(is_active)
    return None, 1

def save_votes_sql(records):
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
# 共用工具
# ==============================
def generate_qr_bytes(url):
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def safe_read_excel(path):
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return pd.read_excel(path)
    except Exception as e:
        st.error(f"❌ 無法讀取檔案 {os.path.basename(path)}：{e}")
    return None

# ==============================
# Streamlit UI
# ==============================
st.set_page_config(page_title="SmartVoteApp", layout="wide")
st.title("🗳️ SmartVoteApp 投票系統（穩定版 v2）")

try:
    qp = st.query_params.to_dict()
except Exception:
    qp = st.experimental_get_query_params()
qp = {k: v[0] if isinstance(v, list) else v for k, v in qp.items()}
is_admin = qp.get("admin", "false").lower() == "true"
unit = qp.get("unit")

# ==============================
# 管理員後台
# ==============================
if is_admin:
    st.header("👨‍💼 管理員後台")

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        uploaded_issues = st.file_uploader("📘 上傳議題清單（Excel，欄位：議題名稱）", type=["xlsx"])
    with col_u2:
        uploaded_units = st.file_uploader("🏠 上傳戶號清單（Excel，欄位：戶號、區分比例）", type=["xlsx"])

    if uploaded_issues:
        path = os.path.join(DATA_DIR, "議題清單.xlsx")
        with open(path, "wb") as f:
            f.write(uploaded_issues.getvalue())
        st.success("✅ 已儲存議題清單")

    if uploaded_units:
        path = os.path.join(DATA_DIR, "戶號清單.xlsx")
        with open(path, "wb") as f:
            f.write(uploaded_units.getvalue())
        st.success("✅ 已儲存戶號清單")

    units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
    units_df = safe_read_excel(units_path)

    if units_df is not None and st.button("🧾 產生戶號專屬 QR Code（ZIP）"):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for _, r in units_df.iterrows():
                params = {"unit": r["戶號"]}
                url = f"{BASE_URL}?{urlencode(params)}"
                qr_b = generate_qr_bytes(url)
                zf.writestr(f"{r['戶號']}.png", qr_b.getvalue())
        zip_buf.seek(0)
        st.download_button("⬇️ 下載 QR Code ZIP", zip_buf, file_name="QRCode_AllUnits.zip", mime="application/zip")

    st.markdown("---")
    now = datetime.now(TZ)
    st.info(f"🕒 現在時間：{now.strftime('%Y-%m-%d %H:%M:%S')}")

    st.subheader("📅 設定截止時間")
    minute = st.selectbox("選擇從現在起多少分鐘後截止", list(range(5, 181, 5)), index=2)
    computed_deadline = now + timedelta(minutes=int(minute))
    st.caption(f"截止時間：{computed_deadline.strftime('%Y-%m-%d %H:%M:%S')}")

    if st.button("✅ 設定截止時間並啟用投票"):
        add_setting(computed_deadline, 1)
        st.success("已啟用投票")

    col_stop, col_start = st.columns(2)
    with col_stop:
        if st.button("🛑 停止投票"):
            update_setting_active(0)
            st.warning("投票已停止")
    with col_start:
        if st.button("▶️ 重新啟用投票"):
            update_setting_active(1)
            st.success("投票已重新啟用")

    latest_end, latest_active = get_latest_setting()
    if latest_end:
        remain = latest_end - datetime.now(TZ)
        if latest_active == 0:
            st.warning(f"目前狀態：停止中（截止：{latest_end.strftime('%Y-%m-%d %H:%M:%S')}）")
        elif remain.total_seconds() > 0:
            st.success(f"開放中，剩餘 {remain.seconds//60} 分鐘")
        else:
            st.warning("已超過截止時間")

    if st.checkbox("✅ 即時更新統計（每5秒）", value=True):
        st_autorefresh(interval=5000, key="auto_refresh")

    st.markdown("---")
    st.subheader("📊 投票統計")

    votes_df = fetch_votes_df()
    issues_df = safe_read_excel(os.path.join(DATA_DIR, "議題清單.xlsx"))
    if units_df is not None and issues_df is not None and not votes_df.empty:
        merged = votes_df.merge(units_df, on="戶號", how="left")
        ratio_col = next((c for c in merged.columns if "比例" in c), None)

        result = []
        for issue in merged["議題"].unique():
            d = merged[merged["議題"] == issue]
            agree = d[d["選項"] == "同意"]
            disagree = d[d["選項"] == "不同意"]
            total = units_df["戶號"].nunique()
            unvote = total - d["戶號"].nunique()
            a_ratio = agree[ratio_col].sum() if ratio_col else len(agree)
            d_ratio = disagree[ratio_col].sum() if ratio_col else len(disagree)
            result.append({
                "議題": issue,
                "同意人數": len(agree),
                "不同意人數": len(disagree),
                "未投票戶數": unvote,
                "同意比例": round(float(a_ratio), 2),
                "不同意比例": round(float(d_ratio), 2)
            })

        stat_df = pd.DataFrame(result)
        st.dataframe(stat_df, use_container_width=True)

        for _, r in stat_df.iterrows():
            fig = px.pie(values=[r["同意人數"], r["不同意人數"]],
                         names=["同意", "不同意"], title=r["議題"], hole=0.35)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("尚無投票資料或 Excel 未上傳")

# ==============================
# 住戶投票頁
# ==============================
elif unit:
    st.header(f"🏠 戶號 {unit} 投票頁")

    issues = safe_read_excel(os.path.join(DATA_DIR, "議題清單.xlsx"))
    units = safe_read_excel(os.path.join(DATA_DIR, "戶號清單.xlsx"))
    if issues is None or units is None:
        st.warning("資料未上傳或損壞，請聯絡管理員")
        st.stop()

    end, active = get_latest_setting()
    if not end or active == 0 or datetime.now(TZ) >= end:
        st.warning("投票已截止或被停止")
        st.stop()

    if has_voted(unit):
        st.success("您已完成投票，感謝參與")
        st.stop()

    st.info(f"截止時間：{end.strftime('%Y-%m-%d %H:%M:%S')}")
    choices = {}
    for idx, row in issues.iterrows():
        issue = row.get("議題名稱") if "議題名稱" in row else row.iloc[0]
        choices[idx] = st.radio(issue, ["同意", "不同意"], horizontal=True)

    if st.button("📤 送出投票"):
        user = units[units["戶號"] == unit]
        if user.empty:
            st.error("查無此戶號")
        else:
            ratio = float(user.iloc[0, 1]) if user.shape[1] > 1 else 1.0
            now_iso = datetime.now(TZ).isoformat()
            recs = [(unit, row.get("議題名稱") if "議題名稱" in row else row.iloc[0],
                     choices[idx], ratio, now_iso) for idx, row in issues.iterrows()]
            save_votes_sql(recs)
            st.success("✅ 投票完成！")
            st.rerun()

# ==============================
# 首頁
# ==============================
else:
    st.info("請使用 QR Code 進入投票頁（?unit=xxx）或 ?admin=true 進入後台。")
