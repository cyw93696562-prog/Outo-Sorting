import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit.components.v1 import html
import base64
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="DLL Sorting System", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ===============================
# Google Sheets 연결
# ===============================
def get_gspread_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)

def get_worksheets():
    gc = get_gspread_client()
    sh = gc.open(st.secrets["google_sheet"]["spreadsheet_name"])
    ws_state = sh.worksheet(st.secrets["google_sheet"]["state_worksheet"])
    ws_logs = sh.worksheet(st.secrets["google_sheet"]["logs_worksheet"])
    return ws_state, ws_logs

def ensure_sheet_headers():
    ws_state, ws_logs = get_worksheets()

    state_values = ws_state.get_all_values()
    if not state_values:
        ws_state.append_row(["key", "value_json", "saved_at"])

    logs_values = ws_logs.get_all_values()
    if not logs_values:
        ws_logs.append_row(["saved_at", "barcode", "product", "store", "qty", "chute", "status"])

def save_state_to_gsheet():
    ws_state, _ = get_worksheets()

    state_data = {
        "store_processed_qty": st.session_state.store_processed_qty,
        "completed_stores": list(st.session_state.completed_stores),
        "processed": list(st.session_state.processed),
        "processed_products": list(st.session_state.processed_products),
        "error_count": st.session_state.error_count,
        "last_messages": st.session_state.last_messages,
        "last_main_message": list(st.session_state.last_main_message),
        "last_scan_plan": st.session_state.last_scan_plan,
        "last_scan_product": st.session_state.last_scan_product,
    }

    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps(state_data, ensure_ascii=False)

    values = ws_state.get_all_values()
    row_index = None

    for i, row in enumerate(values, start=1):
        if len(row) > 0 and row[0] == "current_state":
            row_index = i
            break

    if row_index:
        ws_state.update(f"A{row_index}:C{row_index}", [["current_state", payload, saved_at]])
    else:
        ws_state.append_row(["current_state", payload, saved_at])

def load_state_from_gsheet():
    ws_state, _ = get_worksheets()
    values = ws_state.get_all_values()

    for row in values[1:]:
        if len(row) >= 2 and row[0] == "current_state":
            try:
                return json.loads(row[1])
            except Exception:
                return None
    return None

def append_log_rows(rows):
    if not rows:
        return
    _, ws_logs = get_worksheets()
    ws_logs.append_rows(rows)

# ===============================
# 상태 초기화
# ===============================
def reset_state(store_total_qty):
    st.session_state.store_processed_qty = {store: 0 for store in store_total_qty}
    st.session_state.completed_stores = set()
    st.session_state.processed = set()
    st.session_state.processed_products = set()
    st.session_state.error_count = 0
    st.session_state.last_messages = []
    st.session_state.last_main_message = ("info", "대기 중")
    st.session_state.last_scan_plan = []
    st.session_state.last_scan_product = ""
    st.session_state.play_success_sound = False
    save_state_to_gsheet()

# ===============================
# 로고 base64
# ===============================
def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_base64 = ""
try:
    logo_base64 = get_base64_image("dllogis_logo.gif")
except Exception:
    logo_base64 = ""

# ===============================
# 스타일
# ===============================
st.markdown(f"""
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
    height: 200px;
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
    font-size: 30px;
    font-weight: 800;
    color: #1d2f5f;
    margin-top: 10px;
    margin-bottom: 10px;
}}

.stTextInput label {{
    font-size: 24px !important;
    font-weight: 800 !important;
}}

.stTextInput input {{
    font-size: 32px !important;
    height: 72px !important;
    font-weight: 700 !important;
}}

.small-caption {{
    font-size: 18px !important;
    color: #5d6b89;
}}

.big-banner {{
    font-size: 34px;
    font-weight: 900;
    padding: 20px 22px;
    border-radius: 16px;
    margin-bottom: 14px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.10);
}}

.banner-success {{
    background-color: #e8f5e9;
    color: #1b5e20;
}}

.banner-error {{
    background-color: #ffebee;
    color: #b71c1c;
}}

.banner-warning {{
    background-color: #fff8e1;
    color: #8d6e00;
}}

.big-message {{
    font-size: 22px;
    font-weight: 800;
    padding: 12px 14px;
    border-radius: 12px;
    margin-bottom: 8px;
}}

.msg-success {{
    background-color: #e8f5e9;
    color: #1b5e20;
}}

.msg-warning {{
    background-color: #fff8e1;
    color: #8d6e00;
}}

.msg-error {{
    background-color: #ffebee;
    color: #b71c1c;
}}

.msg-info {{
    background-color: #f3f6fb;
    color: #1f3b5c;
}}

.store-done {{
    font-size: 24px;
    font-weight: 800;
    margin-bottom: 10px;
    padding: 12px 16px;
    border-radius: 12px;
    background-color: #eef7ee;
    color: #1b5e20;
}}

.plan-card {{
    font-size: 24px;
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

.plan-store {{
    font-size: 28px;
    font-weight: 900;
    margin-bottom: 8px;
}}

.plan-sub {{
    font-size: 20px;
    font-weight: 700;
}}

.item-card {{
    font-size: 20px;
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

.summary-card {{
    background: #f8fafc;
    border-radius: 14px;
    padding: 18px 18px;
    margin-bottom: 14px;
    border: 1px solid #e6ebf2;
}}

.summary-label {{
    font-size: 22px;
    font-weight: 700;
    color: #4d5b7c;
    margin-bottom: 8px;
}}

.summary-value {{
    font-size: 42px;
    font-weight: 900;
    color: #1d2f5f;
}}
</style>

<div class="fixed-header">
    <div class="logo-wrap">
        {"<img src='data:image/gif;base64," + logo_base64 + "'>" if logo_base64 else ""}
    </div>
    <div class="header-title-only">Sorting System</div>
</div>
""", unsafe_allow_html=True)

# ===============================
# 엑셀 로드
# ===============================
try:
    df = pd.read_excel("orders.xlsx")
except Exception as e:
    st.error(f"orders.xlsx 불러오기 실패: {e}")
    st.stop()

required_cols = ["barcode", "store", "qty"]
missing_cols = [c for c in required_cols if c not in df.columns]
if missing_cols:
    st.error(f"엑셀 컬럼 누락: {missing_cols}")
    st.stop()

has_product_col = "product" in df.columns

orders = {}
for _, row in df.iterrows():
    barcode = str(row["barcode"]).strip()
    store = str(row["store"]).strip()
    qty = int(row["qty"])
    product = str(row["product"]).strip() if has_product_col else barcode

    if barcode not in orders:
        orders[barcode] = []

    orders[barcode].append({
        "store": store,
        "qty": qty,
        "product": product
    })

# ===============================
# 매장 총수량
# ===============================
store_total_qty = {}
for items in orders.values():
    for item in items:
        store = item["store"]
        qty = item["qty"]
        store_total_qty[store] = store_total_qty.get(store, 0) + qty

# ===============================
# 슈트 자동 배정
# ===============================
sorted_stores = sorted(
    store_total_qty.items(),
    key=lambda x: x[1],
    reverse=True
)

store_map = {}
chute_no = 1
for store, _ in sorted_stores:
    store_map[store] = chute_no
    chute_no += 1

# ===============================
# 시트 초기화
# ===============================
try:
    ensure_sheet_headers()
except Exception as e:
    st.error(f"Google Sheets 연결 오류: {e}")
    st.stop()

# ===============================
# 세션 상태 로드
# ===============================
loaded_state = load_state_from_gsheet()

if "store_processed_qty" not in st.session_state:
    st.session_state.store_processed_qty = loaded_state.get("store_processed_qty", {store: 0 for store in store_total_qty}) if loaded_state else {store: 0 for store in store_total_qty}

if "completed_stores" not in st.session_state:
    st.session_state.completed_stores = set(loaded_state.get("completed_stores", [])) if loaded_state else set()

if "processed" not in st.session_state:
    st.session_state.processed = set(loaded_state.get("processed", [])) if loaded_state else set()

if "processed_products" not in st.session_state:
    st.session_state.processed_products = set(loaded_state.get("processed_products", [])) if loaded_state else set()

if "error_count" not in st.session_state:
    st.session_state.error_count = loaded_state.get("error_count", 0) if loaded_state else 0

if "last_messages" not in st.session_state:
    st.session_state.last_messages = loaded_state.get("last_messages", []) if loaded_state else []

if "last_main_message" not in st.session_state:
    last_main = loaded_state.get("last_main_message", ["info", "대기 중"]) if loaded_state else ["info", "대기 중"]
    st.session_state.last_main_message = tuple(last_main)

if "last_scan_plan" not in st.session_state:
    st.session_state.last_scan_plan = loaded_state.get("last_scan_plan", []) if loaded_state else []

if "last_scan_product" not in st.session_state:
    st.session_state.last_scan_product = loaded_state.get("last_scan_product", "") if loaded_state else ""

if "play_success_sound" not in st.session_state:
    st.session_state.play_success_sound = False

if "barcode_input" not in st.session_state:
    st.session_state.barcode_input = ""

# ===============================
# 효과음
# ===============================
def play_beep():
    st.markdown(
        """
        <audio autoplay>
            <source src="data:audio/wav;base64,UklGRlQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YTAAAAAA/////wAAAP///wAAAP///wAAAP///wAAAP///wAAAP///w=="
            type="audio/wav">
        </audio>
        """,
        unsafe_allow_html=True
    )

# ===============================
# 처리 함수
# ===============================
def process_barcode():
    barcode = st.session_state.barcode_input.strip()
    messages = []
    current_plan = []
    log_rows = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not barcode:
        return

    if barcode in st.session_state.processed:
        st.session_state.last_main_message = ("warning", "⚠️ 이미 처리된 바코드입니다.")
        st.session_state.last_scan_plan = []
        messages.append(("warning", "⚠️ 이미 처리된 바코드입니다."))
    elif barcode not in orders:
        st.session_state.last_main_message = ("error", "❌ 주문 없음")
        st.session_state.last_scan_plan = []
        messages.append(("error", "❌ 주문 없음"))
        st.session_state.error_count += 1
        log_rows.append([now_str, barcode, "", "", "", "", "ERROR_NO_ORDER"])
    else:
        items = orders[barcode]
        first_product = items[0]["product"] if items else barcode
        st.session_state.last_scan_product = first_product
        st.session_state.processed_products.add(first_product)

        for item in items:
            store = item["store"]
            qty = item["qty"]
            product = item["product"]

            if store not in store_map:
                st.session_state.last_main_message = ("error", f"❌ 매핑 없음 → {store}")
                messages.append(("error", f"❌ 매핑 없음 → {store}"))
                st.session_state.error_count += 1
                log_rows.append([now_str, barcode, product, store, qty, "", "ERROR_NO_MAPPING"])
                continue

            chute = store_map[store]
            st.session_state.store_processed_qty[store] += qty
            messages.append(("info", f"👉 {product} → {store} {qty}개 (슈트 {chute})"))

            current_plan.append({
                "store": store,
                "qty": qty,
                "chute": chute,
                "product": product
            })

            log_rows.append([now_str, barcode, product, store, qty, chute, "DONE"])

            total = store_total_qty[store]
            done = st.session_state.store_processed_qty[store]
            if done >= total:
                st.session_state.completed_stores.add(store)

        current_plan = sorted(current_plan, key=lambda x: x["chute"])
        st.session_state.last_scan_plan = current_plan
        st.session_state.processed.add(barcode)
        st.session_state.last_main_message = ("success", f"✅ {first_product} 처리 완료")
        st.session_state.play_success_sound = True

    existing = st.session_state.last_messages.copy()
    existing.extend(messages)
    st.session_state.last_messages = existing[-8:]
    st.session_state.barcode_input = ""

    save_state_to_gsheet()
    append_log_rows(log_rows)

# ===============================
# 원형 그래프
# ===============================
def make_total_donut(done, total):
    remain = max(total - done, 0)
    percent = 0 if total == 0 else round((done / total) * 100, 1)

    fig = go.Figure(data=[
        go.Pie(
            labels=["완료", "잔여"],
            values=[done, remain],
            hole=0.76,
            textinfo="none",
            sort=False
        )
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
                showarrow=False
            )
        ]
    )
    return fig

# ===============================
# 상단 제어
# ===============================
top1, top2, top3 = st.columns([3, 1, 1])

with top1:
    st.markdown('<p class="section-title">🔐 화면 모드</p>', unsafe_allow_html=True)
    view_mode = st.radio(
        "화면 모드 선택",
        ["작업자 모드", "관리자 모드", "진척율"],
        horizontal=True,
        label_visibility="collapsed"
    )

with top2:
    st.markdown('<p class="section-title">🔄 복구</p>', unsafe_allow_html=True)
    if st.button("저장 데이터 복구", use_container_width=True):
        recovered = load_state_from_gsheet()
        if recovered:
            st.session_state.store_processed_qty = recovered.get("store_processed_qty", {store: 0 for store in store_total_qty})
            st.session_state.completed_stores = set(recovered.get("completed_stores", []))
            st.session_state.processed = set(recovered.get("processed", []))
            st.session_state.processed_products = set(recovered.get("processed_products", []))
            st.session_state.error_count = recovered.get("error_count", 0)
            st.session_state.last_messages = recovered.get("last_messages", [])
            st.session_state.last_main_message = tuple(recovered.get("last_main_message", ["info", "대기 중"]))
            st.session_state.last_scan_plan = recovered.get("last_scan_plan", [])
            st.session_state.last_scan_product = recovered.get("last_scan_product", "")
            st.success("저장 데이터 복구 완료")
            st.rerun()
        else:
            st.warning("복구할 저장 데이터가 없습니다.")

with top3:
    st.markdown('<p class="section-title">🧹 초기화</p>', unsafe_allow_html=True)
    if st.button("작업 데이터 초기화", use_container_width=True):
        reset_state(store_total_qty)
        st.success("작업 데이터 초기화 완료")
        st.rerun()

# ===============================
# 작업자 모드
# ===============================
if view_mode == "작업자 모드":
    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown('<p class="section-title">📥 스캔 입력</p>', unsafe_allow_html=True)

        st.text_input(
            "바코드 입력",
            key="barcode_input",
            on_change=process_barcode,
            placeholder="스캐너로 바코드를 찍으면 자동 처리됩니다"
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

        st.markdown('<p class="section-title">📋 최근 처리 내역</p>', unsafe_allow_html=True)

        if not st.session_state.last_messages:
            st.info("아직 처리 내역이 없습니다.")
        else:
            for level, msg in reversed(st.session_state.last_messages):
                if level == "success":
                    st.markdown(f'<div class="big-message msg-success">{msg}</div>', unsafe_allow_html=True)
                elif level == "warning":
                    st.markdown(f'<div class="big-message msg-warning">{msg}</div>', unsafe_allow_html=True)
                elif level == "error":
                    st.markdown(f'<div class="big-message msg-error">{msg}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="big-message msg-info">{msg}</div>', unsafe_allow_html=True)

    with right_col:
        st.markdown('<p class="section-title">📦 방금 스캔한 제품 배분 내역</p>', unsafe_allow_html=True)

        if not st.session_state.last_scan_plan:
            st.info("아직 스캔된 제품이 없습니다.")
        else:
            product_name = st.session_state.last_scan_product
            st.markdown(f'<div class="big-banner banner-success">📌 {product_name}</div>', unsafe_allow_html=True)

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
                        unsafe_allow_html=True
                    )

# ===============================
# 관리자 모드
# ===============================
elif view_mode == "관리자 모드":
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
                                "product": item["product"],
                                "qty": item["qty"],
                                "barcode": barcode
                            })

                for item in store_items:
                    is_done = item["product"] in st.session_state.processed_products
                    card_class = "item-card item-card-done" if is_done else "item-card"
                    status_text = "✅ 완료" if is_done else "⏳ 대기"
                    st.markdown(
                        f'<div class="{card_class}">{item["product"]} | {item["qty"]}개 | {status_text}</div>',
                        unsafe_allow_html=True
                    )

    with right_col:
        st.markdown('<p class="section-title">✅ 완료된 매장 목록 (100%)</p>', unsafe_allow_html=True)

        if not st.session_state.completed_stores:
            st.write("아직 완료된 매장 없음")
        else:
            for store in sorted(st.session_state.completed_stores):
                chute = store_map.get(store, "-")
                st.markdown(
                    f'<div class="store-done">{store} (슈트 {chute}) ✅ 완료</div>',
                    unsafe_allow_html=True
                )

# ===============================
# 진척율
# ===============================
else:
    st.markdown('<p class="section-title">📊 전체 진척율</p>', unsafe_allow_html=True)

    total_qty_all = sum(store_total_qty.values())
    done_qty_all = sum(st.session_state.store_processed_qty.values())

    col1, col2 = st.columns([2, 1])

    with col1:
        fig = make_total_donut(done_qty_all, total_qty_all)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown(
            f'''
            <div class="summary-card">
                <div class="summary-label">정상 처리 바코드</div>
                <div class="summary-value">{len(st.session_state.processed)}</div>
            </div>
            ''',
            unsafe_allow_html=True
        )
        st.markdown(
            f'''
            <div class="summary-card">
                <div class="summary-label">에러</div>
                <div class="summary-value">{st.session_state.error_count}</div>
            </div>
            ''',
            unsafe_allow_html=True
        )
        st.markdown(
            f'''
            <div class="summary-card">
                <div class="summary-label">전체 투입수량</div>
                <div class="summary-value">{done_qty_all}</div>
            </div>
            ''',
            unsafe_allow_html=True
        )
        st.markdown(
            f'''
            <div class="summary-card">
                <div class="summary-label">전체 총수량</div>
                <div class="summary-value">{total_qty_all}</div>
            </div>
            ''',
            unsafe_allow_html=True
        )
