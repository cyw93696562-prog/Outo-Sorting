import base64
import json
import time
from datetime import datetime

import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from streamlit.components.v1 import html

st.set_page_config(page_title="DLL Sorting System", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
VALID_STATUS = ["작업전", "진행중", "작업완료"]
VIEW_MODES = ["차수선택", "작업화면", "내역확인", "진척율"]
VIEW_MODE_KEY = "view_mode_radio"


# ===============================
# 공통 유틸
# ===============================
def make_work_key(order_date: str, wave: str, status: str) -> str:
    return f"{order_date}||{wave}||{status}"


def make_processed_barcode_key(work_key: str, barcode: str) -> str:
    return f"{work_key}||{barcode}"


def make_processed_pair_key(work_key: str, barcode: str, store: str) -> str:
    return f"{work_key}||{barcode}||{store}"


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


# ===============================
# Google Sheets 연결
# ===============================
@st.cache_resource

def get_gspread_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


@st.cache_resource

def get_spreadsheet():
    return get_gspread_client().open_by_key(st.secrets["google_sheet"]["spreadsheet_key"])


@st.cache_resource

def get_state_logs_worksheets():
    sh = get_spreadsheet()
    return (
        sh.worksheet(st.secrets["google_sheet"]["state_worksheet"]),
        sh.worksheet(st.secrets["google_sheet"]["logs_worksheet"]),
    )


def get_orders_ws():
    return get_spreadsheet().worksheet(st.secrets["google_sheet"]["orders_worksheet"])



def retry_gsheet(func, *args, max_retries=4, **kwargs):
    last_error = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            last_error = e
            if "429" in str(e) or "Quota" in str(e):
                time.sleep(2 ** attempt)
            else:
                raise
    raise last_error


@st.cache_data(ttl=60)
def load_orders_from_gsheet():
    ws_orders = get_orders_ws()
    all_values = retry_gsheet(ws_orders.get_all_values)

    if not all_values or len(all_values) < 2:
        raise ValueError("orders 탭에 데이터가 없습니다.")

    header = [str(x).strip() for x in all_values[0]]
    required_cols = ["order_date", "wave", "status", "barcode", "product", "store", "qty"]
    header_index = {}

    for col in required_cols:
        if col not in header:
            raise ValueError(f"orders 탭 컬럼 누락: {col}")
        header_index[col] = header.index(col)

    rows = []
    for raw_row in all_values[1:]:
        if not any(str(cell).strip() for cell in raw_row):
            continue

        row_dict = {}
        for col in required_cols:
            idx = header_index[col]
            value = raw_row[idx] if idx < len(raw_row) else ""
            row_dict[col] = str(value).strip()
        rows.append(row_dict)

    df = pd.DataFrame(rows)
    df["barcode"] = df["barcode"].astype(str).str.strip()
    df["product"] = df["product"].astype(str).str.strip()
    df.loc[df["product"] == "", "product"] = df["barcode"]
    df["order_date"] = df["order_date"].astype(str).str.strip()
    df["wave"] = df["wave"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip()
    df["store"] = df["store"].astype(str).str.strip()
    df["qty"] = df["qty"].apply(safe_int)

    return df



def clear_orders_cache():
    load_orders_from_gsheet.clear()


# ===============================
# 저장/복구
# ===============================
def ensure_sheet_headers_once():
    ws_state, ws_logs = get_state_logs_worksheets()

    state_row = retry_gsheet(ws_state.get, "A1:C2")
    if not state_row or len(state_row) == 0:
        retry_gsheet(ws_state.update, "A1:C2", [
            ["key", "value_json", "saved_at"],
            ["current_state", "{}", ""],
        ])
    else:
        row1 = state_row[0] if len(state_row) >= 1 else []
        if row1[:3] != ["key", "value_json", "saved_at"]:
            retry_gsheet(ws_state.update, "A1:C1", [["key", "value_json", "saved_at"]])
        if len(state_row) < 2 or not state_row[1] or state_row[1][0] != "current_state":
            retry_gsheet(ws_state.update, "A2:C2", [["current_state", "{}", ""]])

    logs_row = retry_gsheet(ws_logs.get, "A1:G1")
    expected = ["saved_at", "work_key", "barcode", "product", "store", "qty", "chute"]
    if not logs_row or len(logs_row) == 0 or logs_row[0][:7] != expected:
        retry_gsheet(ws_logs.update, "A1:G1", [expected])



def get_default_runtime_state(store_total_qty=None):
    store_total_qty = store_total_qty or {}
    return {
        "selected_order_date": "",
        "selected_wave": "",
        "selected_status": "",
        "selected_work_key": "",
        "pending_work_key": "",
        "view_mode": "차수선택",
        VIEW_MODE_KEY: "차수선택",
        "store_processed_qty": {store: 0 for store in store_total_qty},
        "completed_stores": set(),
        "processed": set(),
        "processed_pairs": set(),
        "error_count": 0,
        "last_messages": [],
        "last_main_message": ("info", "대기 중"),
        "last_scan_plan": [],
        "last_scan_product": "",
        "play_success_sound": False,
        "barcode_input": "",
    }



def apply_default_state_once(store_total_qty=None):
    defaults = get_default_runtime_state(store_total_qty)
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value



def save_state_to_gsheet():
    ws_state, _ = get_state_logs_worksheets()

    state_data = {
        "selected_order_date": st.session_state.selected_order_date,
        "selected_wave": st.session_state.selected_wave,
        "selected_status": st.session_state.selected_status,
        "selected_work_key": st.session_state.selected_work_key,
        "pending_work_key": st.session_state.pending_work_key,
        "view_mode": st.session_state.view_mode,
        "store_processed_qty": st.session_state.store_processed_qty,
        "completed_stores": list(st.session_state.completed_stores),
        "processed": list(st.session_state.processed),
        "processed_pairs": list(st.session_state.processed_pairs),
        "error_count": st.session_state.error_count,
        "last_messages": st.session_state.last_messages,
        "last_main_message": list(st.session_state.last_main_message),
        "last_scan_plan": st.session_state.last_scan_plan,
        "last_scan_product": st.session_state.last_scan_product,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    payload = json.dumps(state_data, ensure_ascii=False)
    retry_gsheet(ws_state.update, "A2:C2", [["current_state", payload, state_data["saved_at"]]])



def load_state_from_gsheet():
    ws_state, _ = get_state_logs_worksheets()
    row = retry_gsheet(ws_state.get, "A2:C2")
    if not row or len(row) == 0:
        return None

    values = row[0]
    if len(values) < 2 or values[0] != "current_state":
        return None

    raw_json = values[1].strip() if len(values) >= 2 else ""
    if not raw_json:
        return None

    try:
        return json.loads(raw_json)
    except Exception:
        return None



def append_log_rows(rows):
    if rows:
        _, ws_logs = get_state_logs_worksheets()
        retry_gsheet(ws_logs.append_rows, rows)



def reset_progress(store_total_qty):
    st.session_state.store_processed_qty = {store: 0 for store in store_total_qty}
    st.session_state.completed_stores = set()
    st.session_state.processed = set()
    st.session_state.processed_pairs = set()
    st.session_state.error_count = 0
    st.session_state.last_messages = []
    st.session_state.last_main_message = ("info", "대기 중")
    st.session_state.last_scan_plan = []
    st.session_state.last_scan_product = ""
    st.session_state.play_success_sound = False
    st.session_state.barcode_input = ""



def restore_runtime_state(loaded_state, store_total_qty):
    if not loaded_state:
        reset_progress(store_total_qty)
        return

    st.session_state.selected_order_date = loaded_state.get("selected_order_date", "")
    st.session_state.selected_wave = loaded_state.get("selected_wave", "")
    st.session_state.selected_status = loaded_state.get("selected_status", "")
    st.session_state.selected_work_key = loaded_state.get("selected_work_key", "")
    st.session_state.pending_work_key = loaded_state.get("pending_work_key", st.session_state.selected_work_key)
    st.session_state.view_mode = loaded_state.get("view_mode", "차수선택")
    st.session_state[VIEW_MODE_KEY] = st.session_state.view_mode
    st.session_state.store_processed_qty = loaded_state.get("store_processed_qty", {store: 0 for store in store_total_qty})
    st.session_state.completed_stores = set(loaded_state.get("completed_stores", []))
    st.session_state.processed = set(loaded_state.get("processed", []))
    st.session_state.processed_pairs = set(loaded_state.get("processed_pairs", []))
    st.session_state.error_count = loaded_state.get("error_count", 0)
    st.session_state.last_messages = loaded_state.get("last_messages", [])
    st.session_state.last_main_message = tuple(loaded_state.get("last_main_message", ["info", "대기 중"]))
    st.session_state.last_scan_plan = loaded_state.get("last_scan_plan", [])
    st.session_state.last_scan_product = loaded_state.get("last_scan_product", "")
    st.session_state.play_success_sound = False
    st.session_state.barcode_input = ""


# ===============================
# 데이터 가공
# ===============================
def build_work_options(df: pd.DataFrame):
    work_groups = (
        df[["order_date", "wave", "status"]]
        .drop_duplicates()
        .sort_values(by=["order_date", "wave", "status"])
        .reset_index(drop=True)
    )

    options = []
    for _, row in work_groups.iterrows():
        label = f'{row["order_date"]} | Wave {row["wave"]} | {row["status"]}'
        options.append({
            "label": label,
            "order_date": row["order_date"],
            "wave": row["wave"],
            "status": row["status"],
            "work_key": make_work_key(row["order_date"], row["wave"], row["status"]),
        })
    return options



def find_option_by_work_key(work_options, work_key):
    return next((x for x in work_options if x["work_key"] == work_key), None)



def get_filtered_df(df: pd.DataFrame, work_key: str):
    if not work_key:
        return df.iloc[0:0].copy()

    order_date, wave, status = work_key.split("||")
    return df[
        (df["order_date"] == order_date)
        & (df["wave"] == wave)
        & (df["status"] == status)
    ].copy()



def build_orders_and_store_map(filtered_df: pd.DataFrame):
    orders = {}
    for _, row in filtered_df.iterrows():
        barcode = str(row["barcode"]).strip()
        store = str(row["store"]).strip()
        qty = safe_int(row["qty"])
        product = str(row["product"]).strip() if str(row["product"]).strip() else barcode

        orders.setdefault(barcode, []).append({
            "store": store,
            "qty": qty,
            "product": product,
        })

    store_total_qty = {}
    for items in orders.values():
        for item in items:
            store_total_qty[item["store"]] = store_total_qty.get(item["store"], 0) + item["qty"]

    sorted_stores = sorted(store_total_qty.items(), key=lambda x: x[1], reverse=True)
    store_map = {store: idx + 1 for idx, (store, _) in enumerate(sorted_stores)}
    return orders, store_total_qty, sorted_stores, store_map



def sync_progress_keys(store_total_qty):
    for store in store_total_qty:
        if store not in st.session_state.store_processed_qty:
            st.session_state.store_processed_qty[store] = 0


# ===============================
# orders 상태 변경
# ===============================
def mark_selected_group_status(order_date: str, wave: str, current_status: str, new_status: str):
    ws_orders = get_orders_ws()
    all_values = retry_gsheet(ws_orders.get_all_values)
    if not all_values or len(all_values) < 2:
        return

    headers = all_values[0]
    col_idx = {name: idx for idx, name in enumerate(headers)}
    for col in ["order_date", "wave", "status"]:
        if col not in col_idx:
            raise ValueError(f"orders 탭 컬럼 누락: {col}")

    status_col_letter = gspread.utils.rowcol_to_a1(1, col_idx["status"] + 1)[:-1]
    updates = []

    for row_num, row in enumerate(all_values[1:], start=2):
        row_order_date = str(row[col_idx["order_date"]]).strip() if len(row) > col_idx["order_date"] else ""
        row_wave = str(row[col_idx["wave"]]).strip() if len(row) > col_idx["wave"] else ""
        row_status = str(row[col_idx["status"]]).strip() if len(row) > col_idx["status"] else ""

        if row_order_date == order_date and row_wave == wave and row_status == current_status:
            updates.append({"range": f"{status_col_letter}{row_num}", "values": [[new_status]]})

    if updates:
        retry_gsheet(ws_orders.batch_update, updates)


# ===============================
# 스타일 / 헤더
# ===============================
def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


logo_base64 = ""
try:
    logo_base64 = get_base64_image("dllogis_logo.gif")
except Exception:
    logo_base64 = ""

st.markdown(
    f"""
<style>
html, body, [class*="css"] {{
    font-family: Arial, Helvetica, sans-serif;
}}
.block-container {{
    padding-top: 150px;
    padding-bottom: 1.2rem;
    max-width: 100%;
    padding-left: 20px;
    padding-right: 20px;
}}
.fixed-header {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 170px;
    background-color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 28px;
    border-bottom: 2px solid #e6ebf2;
    z-index: 99999;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
.logo-wrap {{
    display: flex;
    align-items: center;
    height: 80px;
    width: 320px;
    flex-shrink: 0;
}}
.logo-wrap img {{
    max-height: 100%;
    max-width: 100%;
    width: auto;
    height: auto;
    object-fit: contain;
    object-position: left center;
    display: block;
}}
.header-title-only {{
    font-size: 42px;
    font-weight: 900;
    color: #1d2f5f;
    line-height: 1;
    text-align: right;
    margin-right: 10px;
}}
.section-title {{
    font-size: 26px;
    font-weight: 800;
    color: #1d2f5f;
    margin-top: 10px;
    margin-bottom: 10px;
}}
.mode-box, .select-box-area, .summary-card {{
    background: #f8fafc;
    border: 1px solid #e6ebf2;
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 14px;
}}
.big-banner {{
    font-size: 30px;
    font-weight: 900;
    padding: 18px 20px;
    border-radius: 16px;
    margin-bottom: 14px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.10);
}}
.banner-success {{ background-color: #e8f5e9; color: #1b5e20; }}
.banner-error {{ background-color: #ffebee; color: #b71c1c; }}
.banner-warning {{ background-color: #fff8e1; color: #8d6e00; }}
.big-message {{
    font-size: 20px;
    font-weight: 800;
    padding: 12px 14px;
    border-radius: 12px;
    margin-bottom: 8px;
}}
.msg-success {{ background-color: #e8f5e9; color: #1b5e20; }}
.msg-warning {{ background-color: #fff8e1; color: #8d6e00; }}
.msg-error {{ background-color: #ffebee; color: #b71c1c; }}
.msg-info {{ background-color: #f3f6fb; color: #1f3b5c; }}
.plan-card {{
    font-size: 22px;
    font-weight: 800;
    padding: 16px 18px;
    border-radius: 14px;
    background-color: #f5f7fb;
    color: #1f3b5c;
    border: 1px solid #e6ebf2;
    min-height: 120px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    margin-bottom: 10px;
}}
.plan-store {{ font-size: 26px; font-weight: 900; margin-bottom: 8px; }}
.plan-sub {{ font-size: 18px; font-weight: 700; }}
.item-card {{
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 8px;
    padding: 10px 14px;
    border-radius: 10px;
    background-color: #f7f8fb;
    color: #1f3b5c;
    border: 1px solid #e6ebf2;
}}
.item-card-done {{
    background-color: #e8f5e9;
    color: #1b5e20;
    border: 1px solid #b7dfb9;
}}
.store-done {{
    font-size: 20px;
    font-weight: 800;
    margin-bottom: 10px;
    padding: 12px 16px;
    border-radius: 12px;
    background-color: #eef7ee;
    color: #1b5e20;
}}
.summary-label {{ font-size: 18px; font-weight: 700; color: #4d5b7c; margin-bottom: 8px; }}
.summary-value {{ font-size: 34px; font-weight: 900; color: #1d2f5f; }}
.small-caption {{ font-size: 18px !important; color: #5d6b89; }}
.stTextInput label {{ font-size: 24px !important; font-weight: 800 !important; }}
.stTextInput input {{ font-size: 32px !important; height: 72px !important; font-weight: 700 !important; }}
</style>
<div class="fixed-header">
    <div class="logo-wrap">
        {"<img src='data:image/gif;base64," + logo_base64 + "'>" if logo_base64 else ""}
    </div>
    <div class="header-title-only">Sorting System</div>
</div>
""",
    unsafe_allow_html=True,
)


# ===============================
# 초기 로딩
# ===============================
if "sheet_initialized" not in st.session_state:
    try:
        ensure_sheet_headers_once()
        st.session_state.sheet_initialized = True
    except Exception as e:
        st.error(f"Google Sheets 연결 오류: {e}")
        st.stop()

try:
    df = load_orders_from_gsheet()
except Exception as e:
    st.error(f"orders 탭 읽기 오류: {e}")
    st.stop()

work_options = build_work_options(df)
base_store_total_qty = {}
apply_default_state_once(base_store_total_qty)

if not st.session_state.selected_work_key and work_options:
    first = work_options[0]
    st.session_state.selected_order_date = first["order_date"]
    st.session_state.selected_wave = first["wave"]
    st.session_state.selected_status = first["status"]
    st.session_state.selected_work_key = first["work_key"]
    st.session_state.pending_work_key = first["work_key"]

if "state_loaded" not in st.session_state:
    try:
        loaded_state = load_state_from_gsheet()
        restore_runtime_state(loaded_state, base_store_total_qty)
        st.session_state.state_loaded = True
    except Exception as e:
        st.error(f"저장 데이터 읽기 오류: {e}")
        st.stop()

# saved state가 현재 orders 목록과 안 맞을 때 보정
if st.session_state.selected_work_key and not find_option_by_work_key(work_options, st.session_state.selected_work_key):
    if work_options:
        first = work_options[0]
        st.session_state.selected_order_date = first["order_date"]
        st.session_state.selected_wave = first["wave"]
        st.session_state.selected_status = first["status"]
        st.session_state.selected_work_key = first["work_key"]
        st.session_state.pending_work_key = first["work_key"]
    else:
        st.session_state.selected_order_date = ""
        st.session_state.selected_wave = ""
        st.session_state.selected_status = ""
        st.session_state.selected_work_key = ""
        st.session_state.pending_work_key = ""

active_work_key = st.session_state.selected_work_key
filtered_df = get_filtered_df(df, active_work_key)
orders, store_total_qty, sorted_stores, store_map = build_orders_and_store_map(filtered_df)
sync_progress_keys(store_total_qty)


# ===============================
# 액션 함수
# ===============================
def apply_selected_work():
    selected_item = find_option_by_work_key(work_options, st.session_state.pending_work_key)
    if not selected_item:
        st.warning("적용할 차수를 찾을 수 없습니다.")
        return

    st.session_state.selected_order_date = selected_item["order_date"]
    st.session_state.selected_wave = selected_item["wave"]
    st.session_state.selected_status = selected_item["status"]
    st.session_state.selected_work_key = selected_item["work_key"]

    new_filtered_df = get_filtered_df(df, selected_item["work_key"])
    _, new_store_total_qty, _, _ = build_orders_and_store_map(new_filtered_df)
    reset_progress(new_store_total_qty)
    st.session_state.last_main_message = ("info", "차수를 적용했습니다.")
    st.session_state.view_mode = "작업화면"
    st.session_state[VIEW_MODE_KEY] = "작업화면"
    save_state_to_gsheet()
    st.rerun()



def recover_saved_state():
    recovered = load_state_from_gsheet()
    if recovered:
        restore_runtime_state(recovered, store_total_qty)
        st.success("저장 데이터 복구 완료")
        st.rerun()
    st.warning("복구할 저장 데이터가 없습니다.")



def refresh_orders():
    clear_orders_cache()
    st.success("orders 탭 새로고침 완료")
    st.rerun()



def reset_current_work():
    reset_progress(store_total_qty)
    save_state_to_gsheet()
    st.success("작업 데이터 초기화 완료")
    st.rerun()



def complete_current_work():
    if not st.session_state.selected_work_key:
        st.warning("먼저 작업 차수를 선택해주세요.")
        return

    order_date = st.session_state.selected_order_date
    wave = st.session_state.selected_wave
    current_status = st.session_state.selected_status

    if current_status != "진행중":
        st.warning("진행중 차수만 작업완료 처리할 수 있습니다.")
        return

    mark_selected_group_status(order_date, wave, current_status, "작업완료")
    clear_orders_cache()
    st.session_state.selected_status = "작업완료"
    st.session_state.selected_work_key = make_work_key(order_date, wave, "작업완료")
    st.session_state.last_main_message = ("success", "현재 차수를 작업완료로 변경했습니다.")
    save_state_to_gsheet()
    st.rerun()



def play_beep():
    st.markdown(
        """
        <audio autoplay>
            <source src="data:audio/wav;base64,UklGRlQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YTAAAAAA/////wAAAP///wAAAP///wAAAP///wAAAP///wAAAP///w==" type="audio/wav">
        </audio>
        """,
        unsafe_allow_html=True,
    )



def process_barcode():
    barcode = st.session_state.barcode_input.strip()
    if not barcode:
        return

    messages = []
    current_plan = []
    log_rows = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    work_key = st.session_state.selected_work_key

    processed_barcode_key = make_processed_barcode_key(work_key, barcode)

    if not work_key:
        st.session_state.last_main_message = ("warning", "⚠️ 먼저 차수를 선택해주세요.")
        st.session_state.last_scan_plan = []
        messages.append(("warning", "⚠️ 먼저 차수를 선택해주세요."))
    elif st.session_state.selected_status == "작업완료":
        st.session_state.last_main_message = ("warning", "⚠️ 작업완료 차수에서는 스캔할 수 없습니다.")
        st.session_state.last_scan_plan = []
        messages.append(("warning", "⚠️ 작업완료 차수에서는 스캔할 수 없습니다."))
    elif processed_barcode_key in st.session_state.processed:
        st.session_state.last_main_message = ("warning", "⚠️ 현재 차수에서 이미 처리된 바코드입니다.")
        st.session_state.last_scan_plan = []
        messages.append(("warning", "⚠️ 현재 차수에서 이미 처리된 바코드입니다."))
    elif barcode not in orders:
        st.session_state.last_main_message = ("error", "❌ 선택한 차수에 주문 없음")
        st.session_state.last_scan_plan = []
        messages.append(("error", "❌ 선택한 차수에 주문 없음"))
        st.session_state.error_count += 1
    else:
        items = orders[barcode]
        first_product = items[0]["product"] if items else barcode
        st.session_state.last_scan_product = first_product

        for item in items:
            store = item["store"]
            qty = item["qty"]
            product = item["product"] or barcode

            if store not in store_map:
                st.session_state.last_main_message = ("error", f"❌ 매핑 없음 → {store}")
                messages.append(("error", f"❌ 매핑 없음 → {store}"))
                st.session_state.error_count += 1
                continue

            chute = store_map[store]
            st.session_state.store_processed_qty[store] = st.session_state.store_processed_qty.get(store, 0) + qty
            messages.append(("info", f"👉 {product} → {store} {qty}개 (슈트 {chute})"))

            pair_key = make_processed_pair_key(work_key, barcode, store)
            st.session_state.processed_pairs.add(pair_key)
            current_plan.append({"store": store, "qty": qty, "chute": chute, "product": product})
            log_rows.append([now_str, work_key, barcode, product, store, qty, chute])

            total = store_total_qty.get(store, 0)
            done = st.session_state.store_processed_qty.get(store, 0)
            if total > 0 and done >= total:
                st.session_state.completed_stores.add(store)

        current_plan = sorted(current_plan, key=lambda x: x["chute"])
        st.session_state.last_scan_plan = current_plan
        st.session_state.processed.add(processed_barcode_key)
        st.session_state.last_main_message = ("success", f"✅ {first_product} 처리 완료")
        st.session_state.play_success_sound = True

        if st.session_state.selected_status == "작업전":
            try:
                mark_selected_group_status(
                    st.session_state.selected_order_date,
                    st.session_state.selected_wave,
                    "작업전",
                    "진행중",
                )
                clear_orders_cache()
                st.session_state.selected_status = "진행중"
                st.session_state.selected_work_key = make_work_key(
                    st.session_state.selected_order_date,
                    st.session_state.selected_wave,
                    "진행중",
                )
            except Exception:
                pass

    existing = st.session_state.last_messages.copy()
    existing.extend(messages)
    st.session_state.last_messages = existing[-8:]
    st.session_state.barcode_input = ""

    try:
        save_state_to_gsheet()
        append_log_rows(log_rows)
    except Exception as e:
        st.session_state.last_main_message = ("error", f"저장 실패: {e}")



def make_total_donut(done, total):
    remain = max(total - done, 0)
    percent = 0 if total == 0 else round((done / total) * 100, 1)

    fig = go.Figure(data=[
        go.Pie(labels=["완료", "잔여"], values=[done, remain], hole=0.76, textinfo="none", sort=False)
    ])
    fig.update_layout(
        title={"text": "전체 진척율", "x": 0.5, "xanchor": "center", "font": {"size": 28}},
        showlegend=True,
        height=460,
        margin=dict(t=70, b=20, l=20, r=20),
        annotations=[
            dict(
                text=f"<b style='font-size:36px'>{percent}%</b><br><span style='font-size:22px'>{done}/{total}</span>",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
        ],
    )
    return fig


# ===============================
# 상단 모드 전환
# ===============================
st.markdown('<p class="section-title">🖥️ 화면 모드</p>', unsafe_allow_html=True)
st.markdown('<div class="mode-box">', unsafe_allow_html=True)
selected_view_mode = st.radio(
    "화면 모드",
    VIEW_MODES,
    index=VIEW_MODES.index(st.session_state.get("view_mode", "차수선택")) if st.session_state.get("view_mode", "차수선택") in VIEW_MODES else 0,
    key=VIEW_MODE_KEY,
    horizontal=True,
    label_visibility="collapsed",
)
st.session_state.view_mode = selected_view_mode
st.markdown('</div>', unsafe_allow_html=True)


# ===============================
# 화면 1: 차수선택
# ===============================
if st.session_state.view_mode == "차수선택":
    st.markdown('<p class="section-title">📦 작업 차수 선택</p>', unsafe_allow_html=True)
    st.markdown('<div class="select-box-area">', unsafe_allow_html=True)

    c1, c2 = st.columns([3, 1])
    labels = [x["label"] for x in work_options]

    current_pending = find_option_by_work_key(work_options, st.session_state.pending_work_key)
    current_label = current_pending["label"] if current_pending else (labels[0] if labels else "")

    with c1:
        selected_label = st.selectbox(
            "작업 차수",
            labels,
            index=labels.index(current_label) if current_label in labels else 0,
        ) if labels else st.selectbox("작업 차수", ["차수 없음"], index=0)

        if labels:
            selected_item = next((x for x in work_options if x["label"] == selected_label), None)
            if selected_item:
                st.session_state.pending_work_key = selected_item["work_key"]

    with c2:
        st.markdown("")
        st.markdown("")
        if st.button("선택 차수 적용", use_container_width=True, disabled=not work_options):
            apply_selected_work()

    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.selected_work_key:
        st.info(
            f"현재 적용 차수: {st.session_state.selected_order_date} / Wave {st.session_state.selected_wave} / {st.session_state.selected_status}"
        )
    else:
        st.warning("현재 적용된 차수가 없습니다.")

    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("저장 데이터 복구", use_container_width=True):
            recover_saved_state()
    with a2:
        if st.button("오더 새로고침", use_container_width=True):
            refresh_orders()
    with a3:
        if st.button("작업 데이터 초기화", use_container_width=True):
            reset_current_work()


# ===============================
# 화면 2: 작업화면
# ===============================
elif st.session_state.view_mode == "작업화면":
    st.info(
        f"현재 작업 차수: {st.session_state.selected_order_date} / Wave {st.session_state.selected_wave} / {st.session_state.selected_status}"
        if st.session_state.selected_work_key else "현재 적용된 차수가 없습니다."
    )

    if st.session_state.selected_status == "진행중":
        if st.button("현재 차수 작업완료 처리"):
            complete_current_work()

    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown('<p class="section-title">📥 스캔 입력</p>', unsafe_allow_html=True)
        st.text_input(
            "바코드 입력",
            key="barcode_input",
            on_change=process_barcode,
            placeholder="스캐너로 바코드를 찍으면 자동 처리됩니다",
            disabled=not st.session_state.selected_work_key,
        )
        st.markdown('<p class="small-caption">스캐너가 엔터를 보내면 자동 처리됩니다.</p>', unsafe_allow_html=True)

        html(
            """
            <script>
            const focusInput = () => {
                const inputs = window.parent.document.querySelectorAll('input[type="text"]');
                if (inputs.length > 0) {
                    inputs[0].focus();
                    inputs[0].select();
                }
            };
            setTimeout(focusInput, 150);
            setTimeout(focusInput, 500);
            setTimeout(focusInput, 1000);
            setTimeout(focusInput, 1800);
            </script>
            """,
            height=0,
        )

        if st.session_state.play_success_sound:
            play_beep()
            st.session_state.play_success_sound = False

        st.markdown('<p class="section-title">🚨 최근 처리 상태</p>', unsafe_allow_html=True)
        main_level, main_msg = st.session_state.last_main_message
        if main_level == "success":
            st.markdown(f'<div class="big-banner banner-success">{main_msg}</div>', unsafe_allow_html=True)
        elif main_level == "error":
            st.markdown(f'<div class="big-banner banner-error">{main_msg}</div>', unsafe_allow_html=True)
        elif main_level == "warning":
            st.markdown(f'<div class="big-banner banner-warning">{main_msg}</div>', unsafe_allow_html=True)
        else:
            st.info(main_msg)

    with right_col:
        st.markdown('<p class="section-title">📦 방금 스캔한 제품 배분 내역</p>', unsafe_allow_html=True)
        if not st.session_state.last_scan_plan:
            st.info("아직 스캔된 제품이 없습니다.")
        else:
            st.markdown(
                f'<div class="big-banner banner-success">📌 {st.session_state.last_scan_product}</div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(3)
            for idx, plan in enumerate(st.session_state.last_scan_plan):
                with cols[idx % 3]:
                    st.markdown(
                        f'''
                        <div class="plan-card">
                            <div class="plan-store">슈트 {plan["chute"]}</div>
                            <div class="plan-sub">{plan["store"]}</div>
                            <div class="plan-sub">{plan["qty"]}개</div>
                        </div>
                        ''',
                        unsafe_allow_html=True,
                    )

    st.markdown('<p class="section-title">📋 최근 처리 내역</p>', unsafe_allow_html=True)
    if not st.session_state.last_messages:
        st.info("아직 처리 내역이 없습니다.")
    else:
        for level, msg in reversed(st.session_state.last_messages):
            cls = {
                "success": "msg-success",
                "warning": "msg-warning",
                "error": "msg-error",
            }.get(level, "msg-info")
            st.markdown(f'<div class="big-message {cls}">{msg}</div>', unsafe_allow_html=True)


# ===============================
# 화면 3: 내역확인
# ===============================
elif st.session_state.view_mode == "내역확인":
    st.info(
        f"현재 조회 차수: {st.session_state.selected_order_date} / Wave {st.session_state.selected_wave} / {st.session_state.selected_status}"
        if st.session_state.selected_work_key else "현재 적용된 차수가 없습니다."
    )

    left_col, right_col = st.columns([1, 1.2])

    with left_col:
        st.markdown('<p class="section-title">📦 매장별 배분 예정 내역</p>', unsafe_allow_html=True)
        for store, total_qty in sorted_stores:
            chute = store_map.get(store, "-")
            done = st.session_state.store_processed_qty.get(store, 0)
            remain = max(total_qty - done, 0)
            with st.expander(f"{store} (슈트 {chute}) | 총 {total_qty}개 | 잔여 {remain}개", expanded=False):
                store_items = []
                for barcode, items in orders.items():
                    for item in items:
                        if item["store"] == store:
                            store_items.append({
                                "product": item["product"] or barcode,
                                "qty": item["qty"],
                                "barcode": barcode,
                                "pair_key": make_processed_pair_key(st.session_state.selected_work_key, barcode, store),
                            })

                for item in store_items:
                    is_done = item["pair_key"] in st.session_state.processed_pairs
                    card_class = "item-card item-card-done" if is_done else "item-card"
                    status_text = "✅ 완료" if is_done else "⏳ 대기"
                    st.markdown(
                        f'<div class="{card_class}">{item["product"]} | {item["qty"]}개 | {status_text}</div>',
                        unsafe_allow_html=True,
                    )

    with right_col:
        st.markdown('<p class="section-title">✅ 완료된 매장 목록 (100%)</p>', unsafe_allow_html=True)
        if not st.session_state.completed_stores:
            st.write("아직 완료된 매장 없음")
        else:
            for store in sorted(st.session_state.completed_stores):
                chute = store_map.get(store, "-")
                st.markdown(f'<div class="store-done">{store} (슈트 {chute}) ✅ 완료</div>', unsafe_allow_html=True)


# ===============================
# 화면 4: 진척율
# ===============================
else:
    st.info(
        f"현재 조회 차수: {st.session_state.selected_order_date} / Wave {st.session_state.selected_wave} / {st.session_state.selected_status}"
        if st.session_state.selected_work_key else "현재 적용된 차수가 없습니다."
    )

    total_qty_all = sum(store_total_qty.values())
    done_qty_all = sum(st.session_state.store_processed_qty.get(store, 0) for store in store_total_qty.keys())

    st.markdown('<p class="section-title">📊 전체 진척율</p>', unsafe_allow_html=True)
    col1, col2 = st.columns([2, 1])

    with col1:
        st.plotly_chart(make_total_donut(done_qty_all, total_qty_all), use_container_width=True)

    with col2:
        metrics = [
            ("정상 처리 바코드", len(st.session_state.processed)),
            ("에러", st.session_state.error_count),
            ("전체 투입수량", done_qty_all),
            ("전체 총수량", total_qty_all),
        ]
        for label, value in metrics:
            st.markdown(
                f'''
                <div class="summary-card">
                    <div class="summary-label">{label}</div>
                    <div class="summary-value">{value}</div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
