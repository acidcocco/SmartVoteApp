# app.py - SmartVoteApp 最終穩定版（支援 Plotly、SQLite、設定歷史、匯出）
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
# 基本設定（請視需要修改 BASE_URL）
# ==============================
BASE_URL = os.environ.get("BASE_URL", "https://acidcocco.onrender.com")
DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "votes.db")
os.makedirs(DATA_DIR, exist_ok=True)
TZ = pytz.timezone("Asia/Taipei")

# ==============================
# 初始化資料庫（votes, settings）
# settings 支援歷史紀錄：每次設定或狀態變更都會新增一筆
# ==============================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 投票表（主鍵避免同一戶同一議題重複）
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
    # 設定表（支援歷史紀錄）
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
    """
    新增一筆 settings（保留歷史）
    end_time_dt: datetime (tz-aware preferred)
    """
    conn = get_conn()
    c = conn.cursor()
    created = datetime.now(TZ).isoformat()
    iso = end_time_dt.isoformat() if end_time_dt is not None else None
    c.execute("INSERT INTO settings (end_time, is_active, note, created_at) VALUES (?, ?, ?, ?)",
              (iso, int(is_active), note, created))
    conn.commit()
    conn.close()

def update_setting_active(new_active, note=None):
    """
    將目前的設定複製並新增一筆 active 更新（保留歷史）
    """
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
    row = c.execute("SELECT end_time, is_active, created_at FROM settings ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        end_time_iso, is_active, created = row
        if end_time_iso:
            try:
                dt = datetime.fromisoformat(end_time_iso)
            except Exception:
                # 若非嚴格 iso 格式，嘗試解析
                dt = datetime.fromisoformat(end_time_iso)
            # 若 dt 沒有 tzinfo，視為台北時區
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
        else:
            dt = None
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
# 共用工具：QR 產生
# ==============================
def generate_qr_bytes(url):
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================
# Streamlit UI
# ==============================
st.set_page_config(page_title="SmartVoteApp", layout="wide")
st.title("🗳️ SmartVoteApp 投票系統（最終穩定版）")

# 讀取 query params
try:
    qp = st.query_params.to_dict()
except Exception:
    qp = st.experimental_get_query_params()
qp = {k: v[0] if isinstance(v, list) else v for k, v in qp.items()}
is_admin = qp.get("admin", "false").lower() == "true"
unit = qp.get("unit")

# ==============================
# 管理頁面
# ==============================
if is_admin:
    st.header("👨‍💼 管理員後台")
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        uploaded_issues = st.file_uploader("📘 上傳議題清單（Excel，欄位：議題名稱）", type=["xlsx"])
    with col_u2:
        uploaded_units = st.file_uploader("🏠 上傳戶號清單（Excel，欄位：戶號、區分比例）", type=["xlsx"])

    # 若上傳則儲存至 data/
    issues_df = None
    units_df = None
    if uploaded_issues:
        issues_path = os.path.join(DATA_DIR, "議題清單.xlsx")
        with open(issues_path, "wb") as f:
            f.write(uploaded_issues.getvalue())
        issues_df = pd.read_excel(issues_path)
        st.success("已儲存議題清單（data/議題清單.xlsx）")
    if uploaded_units:
        units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
        with open(units_path, "wb") as f:
            f.write(uploaded_units.getvalue())
        units_df = pd.read_excel(units_path)
        st.success("已儲存戶號清單（data/戶號清單.xlsx）")

    # 產生 QR Code ZIP（若已上傳戶號）
    if units_df is not None:
        if st.button("🧾 產生戶號專屬 QR Code（ZIP）"):
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
    # 顯示台北現在時間
    now = datetime.now(TZ)
    st.info(f"🕒 現在時間（台北）：{now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 截止時間下拉（從現在起每 5 分鐘，最大 180 分鐘）
    st.subheader("📅 設定截止時間（從現在起）")
    minute_options = list(range(5, 181, 5))  # 5,10,...,180
    selected_min = st.selectbox("選擇從現在起多少分鐘後截止（分鐘）", minute_options, index=2)
    computed_deadline = now + timedelta(minutes=int(selected_min))
    st.caption(f"計算後截止時間（台北）：{computed_deadline.strftime('%Y-%m-%d %H:%M:%S')}")

    if st.button("✅ 設定截止時間並啟用投票"):
        add_setting(computed_deadline, is_active=1)
        st.success("已新增設定並啟用投票（設定會保留為歷史紀錄）。")

    # 停止 / 啟用（新增一筆 setting，保留歷史）
    col_stop, col_start = st.columns(2)
    with col_stop:
        if st.button("🛑 停止投票（管理員）"):
            update_setting_active(0)
            st.warning("管理員已停止投票（新增紀錄）。")
    with col_start:
        if st.button("▶️ 啟用投票（保留最新截止時間）"):
            # 如果沒有任何設定，提醒需先設定
            latest_end, latest_active = get_latest_setting()
            if latest_end is None:
                st.error("尚未設定截止時間，請先設定截止時間。")
            else:
                update_setting_active(1)
                st.success("已啟用投票（新增紀錄）。")

    st.markdown("---")
    # 顯示目前最新設定
    latest_end, latest_active = get_latest_setting()
    if latest_end:
        # 轉顯示至台北
        if latest_end.tzinfo is None:
            latest_end = TZ.localize(latest_end)
        latest_end_local = latest_end.astimezone(TZ)
        remain = latest_end_local - datetime.now(TZ)
        if latest_active == 0:
            st.warning(f"目前狀態：已停止（管理員）。 最近設定截止時間：{latest_end_local.strftime('%Y-%m-%d %H:%M:%S')}")
        elif remain.total_seconds() > 0:
            st.success(f"投票開放中，距離截止還有 {remain.days} 天 {remain.seconds//3600} 小時 {(remain.seconds%3600)//60} 分鐘（截止：{latest_end_local.strftime('%Y-%m-%d %H:%M:%S')}）")
        else:
            st.warning(f"目前設定截止時間已過（{latest_end_local.strftime('%Y-%m-%d %H:%M:%S')}）。")

    # 自動刷新選項（若有設定且 active）
    refresh_toggle = st.checkbox("✅ 即時更新投票結果（每 5 秒）", value=True)
    if refresh_toggle:
        latest_end2, latest_active2 = get_latest_setting()
        if latest_end2 and latest_active2 == 1:
            try:
                # 若尚未截止則自動刷新
                if latest_end2.tzinfo is None:
                    latest_end2 = TZ.localize(latest_end2)
                if datetime.now(TZ) < latest_end2:
                    st_autorefresh(interval=5000, key="auto_refresh")
            except Exception:
                pass

    st.markdown("---")
    # 統計與圖表、匯出
    st.subheader("📊 投票統計與圖表")

    # 讀取 DB 與戶號清單（若存在）
    votes_df = fetch_votes_df()
    units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
    if os.path.exists(units_path) and not votes_df.empty:
        units_df = pd.read_excel(units_path)
        merged = votes_df.merge(units_df, on="戶號", how="left")
        # 自動偵測比例欄
        ratio_col = next((c for c in merged.columns if "比例" in c or "比率" in c or "持分" in c), None)

        results = []
        for issue in merged["議題"].unique():
            d = merged[merged["議題"] == issue]
            agree = d[d["選項"] == "同意"]
            disagree = d[d["選項"] == "不同意"]
            total_units = units_df["戶號"].nunique()
            unvote = total_units - d["戶號"].nunique()
            if ratio_col:
                agree_ratio = agree[ratio_col].sum()
                disagree_ratio = disagree[ratio_col].sum()
            else:
                agree_ratio = len(agree)
                disagree_ratio = len(disagree)
            results.append({
                "議題": issue,
                "同意人數": int(len(agree)),
                "不同意人數": int(len(disagree)),
                "未投票戶數": int(unvote),
                "同意比例": round(float(agree_ratio), 6),
                "不同意比例": round(float(disagree_ratio), 6)
            })
        stat_df = pd.DataFrame(results)
        st.dataframe(stat_df, use_container_width=True)

        # Plotly 圓餅圖（每題）與長條圖（群組）
        st.markdown("### 圓餅圖（每題）")
        for _, r in stat_df.iterrows():
            fig_pie = px.pie(values=[r["同意人數"], r["不同意人數"]],
                             names=["同意", "不同意"],
                             title=r["議題"],
                             hole=0.35)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("### 各題比例比較（長條圖）")
        bar_fig = px.bar(stat_df, x="議題", y=["同意比例", "不同意比例"],
                         barmode="group", title="各議題投票比例")
        st.plotly_chart(bar_fig, use_container_width=True)

        # 匯出按鈕（CSV / Excel）
        csv_bytes = stat_df.to_csv(index=False).encode("utf-8-sig")
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
            stat_df.to_excel(writer, index=False, sheet_name="投票結果")
            # optional: 可以再匯出 raw votes sheet
            votes_df.to_excel(writer, index=False, sheet_name="raw_votes")
        excel_buf.seek(0)

        st.download_button("📄 匯出 CSV（投票結果）", data=csv_bytes, file_name="投票結果.csv", mime="text/csv")
        st.download_button("📘 匯出 Excel（投票結果 + raw）", data=excel_buf, file_name="投票結果.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("尚無投票資料或未上傳戶號清單。")

    # 顯示設定歷史（簡短）
    st.markdown("---")
    st.subheader("🕘 設定歷史（最近 10 筆）")
    conn = get_conn()
    hist_df = pd.read_sql("SELECT id, end_time, is_active, note, created_at FROM settings ORDER BY id DESC LIMIT 10", conn)
    conn.close()
    if not hist_df.empty:
        # 顯示時間轉台北（若可能）
        def conv(t):
            if pd.isna(t):
                return None
            try:
                dt = datetime.fromisoformat(t)
            except Exception:
                return t
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
            return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")
        hist_df["end_time_local"] = hist_df["end_time"].apply(conv)
        st.dataframe(hist_df[["id", "end_time_local", "is_active", "note", "created_at"]], use_container_width=True)
    else:
        st.info("尚無設定紀錄。")

# ==============================
# 住戶投票頁
# ==============================
elif unit:
    st.header(f"🏠 戶號 {unit} 投票頁面")

    issues_path = os.path.join(DATA_DIR, "議題清單.xlsx")
    units_path = os.path.join(DATA_DIR, "戶號清單.xlsx")
    if not os.path.exists(issues_path) or not os.path.exists(units_path):
        st.warning("尚未由管理員上傳議題或戶號清單（請聯絡管理員）。")
        st.stop()

    issues_df = pd.read_excel(issues_path)
    units_df = pd.read_excel(units_path)

    latest_end, latest_active = get_latest_setting()
    if latest_end is None:
        st.warning("尚未設定截止時間，請聯絡管理員。")
        st.stop()
    # normalize tz
    if latest_end.tzinfo is None:
        latest_end = TZ.localize(latest_end)
    latest_end_local = latest_end.astimezone(TZ)
    now_local = datetime.now(TZ)

    if latest_active == 0 or now_local >= latest_end_local:
        st.warning("投票已截止或被管理員停止，感謝您的參與。")
        st.stop()

    # 若已投過任一題，視為已完成（你也可以改成逐題檢查）
    if has_voted(unit):
        st.success("您已完成投票，感謝您的參與。")
        st.stop()

    st.info(f"投票截止時間（台北）：{latest_end_local.strftime('%Y-%m-%d %H:%M:%S')}")
    st.write("請為下列議題選擇意見（同一戶一次送出）：")

    # 用 radio 收集每題
    choices = {}
    for idx, row in issues_df.iterrows():
        issue = row.get("議題名稱") if "議題名稱" in row else row.iloc[0]
        choices[f"q_{idx}"] = st.radio(issue, ["同意", "不同意"], horizontal=True, key=f"q_{idx}")

    if st.button("📤 送出投票"):
        user_row = units_df[units_df["戶號"] == unit]
        if user_row.empty:
            st.error("查無此戶號，請確認 QR Code 或聯絡管理員。")
        else:
            ratio = float(user_row.iloc[0, 1]) if user_row.shape[1] >= 2 else 1.0
            iso_time = datetime.now(TZ).isoformat()
            recs = []
            for idx, row in issues_df.iterrows():
                issue = row.get("議題名稱") if "議題名稱" in row else row.iloc[0]
                choice = choices.get(f"q_{idx}")
                recs.append((unit, issue, choice, ratio, iso_time))
            save_votes_sql(recs)
            st.success("✅ 投票已送出，謝謝您的參與！")
            st.experimental_rerun()

# ==============================
# 首頁
# ==============================
else:
    st.info("請透過 QR Code 進入投票頁面（網址包含 ?unit=xxx），或於網址後加上 '?admin=true' 進入管理後台。")
