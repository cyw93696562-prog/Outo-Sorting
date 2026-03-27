import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit.components.v1 import html
import base64

st.set_page_config(page_title="DLL Sorting System", layout="wide")

# ===============================
# 로고 base64 변환
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
# 화면 스타일 + 고정 헤더
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
    font-size: 36px;
    font-weight: 900;
    padding: 22px 26px;
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
    font-size: 26px;
    font-weight: 800;
    padding: 14px 18px;
    border-radius: 12px;
    margin-bottom: 10px;
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
    font-size: 26px;
    font-weight: 800;
    margin-bottom: 12px;
    padding: 16px 18px;
    border-radius: 14px;
    background-color: #f5f7fb;
    color: #1f3b5c;
    border: 1px solid #e6ebf2;
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
# 세션 상태
# ===============================
if "store_processed_qty" not in st.session_state:
    st.session_state.store_processed_qty = {store: 0 for store in store_total_qty}

if "completed_stores" not in st.session_state:
    st.session_state.completed_stores = set()

if "processed" not in st.session_state:
    st.session_state.processed = set()

if "error_count" not in st.session_state:
    st.session_state.error_count = 0

if "last_messages" not in st.session_state:
    st.session_state.last_messages = []

if "last_main_message" not in st.session_state:
    st.session_state.last_main_message = ("info", "대기 중")

if "last_scan_plan" not in st.session_state:
    st.session_state.last_scan_plan = []

if "last_scan_product" not in st.session_state:
    st.session_state.last_scan_product = ""

if "play_success_sound" not in st.session_state:
    st.session_state.play_success_sound = False

if "barcode_input" not in st.session_state:
    st.session_state.barcode_input = ""

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
    else:
        items = orders[barcode]
        first_product = items[0]["product"] if items else barcode
        st.session_state.last_scan_product = first_product

        for item in items:
            store = item["store"]
            qty = item["qty"]
            product = item["product"]

            if store not in store_map:
                st.session_state.last_main_message = ("error", f"❌ 매핑 없음 → {store}")
                messages.append(("error", f"❌ 매핑 없음 → {store}"))
                st.session_state.error_count += 1
                continue

            chute = store_map[store]
            st.session_state.store_processed_qty[store] += qty
            messages.append(("info", f"👉 {product} → {store} {qty}개 (슈트 {chute})"))

            current_plan.append({
                "store": store,
                "qty": qty,
                "chute": chute
            })

            total = store_total_qty[store]
            done = st.session_state.store_processed_qty[store]
            if done >= total:
                st.session_state.completed_stores.add(store)

        st.session_state.last_scan_plan = current_plan
        st.session_state.processed.add(barcode)
        st.session_state.last_main_message = ("success", f"✅ {first_product} 처리 완료")
        st.session_state.play_success_sound = True

    existing = st.session_state.last_messages.copy()
    existing.extend(messages)
    st.session_state.last_messages = existing[-8:]
    st.session_state.barcode_input = ""

# ===============================
# 전체 진척율 원형 그래프
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
# 모드 선택
# ===============================
st.markdown('<p class="section-title">🔐 화면 모드</p>', unsafe_allow_html=True)
view_mode = st.radio(
    "화면 모드 선택",
    ["작업자 모드", "관리자 모드"],
    horizontal=True,
    label_visibility="collapsed"
)

# ===============================
# 좌우 레이아웃
# ===============================
left_col, right_col = st.columns([1.2, 1])

with left_col:
    st.markdown('<p class="section-title">📥 스캔 입력</p>', unsafe_allow_html=True)

    st.text_input(
        "바코드 입력",
        key="barcode_input",
        on_change=process_barcode,
        placeholder="스캐너로 바코드를 찍으면 자동 처리됩니다"
    )

    st.markdown(
        '<p class="small-caption">스캐너가 엔터를 보내면 자동 처리됩니다.</p>',
        unsafe_allow_html=True
    )

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
    if view_mode == "작업자 모드":
        st.markdown('<p class="section-title">📦 방금 스캔한 제품 배분 내역</p>', unsafe_allow_html=True)

        if not st.session_state.last_scan_plan:
            st.info("아직 스캔된 제품이 없습니다.")
        else:
            product_name = st.session_state.last_scan_product
            st.markdown(
                f'<div class="big-banner banner-success">📌 {product_name}</div>',
                unsafe_allow_html=True
            )

            for plan in st.session_state.last_scan_plan:
                st.markdown(
                    f'<div class="plan-card">{plan["store"]} | {plan["qty"]}개 | 슈트 {plan["chute"]}</div>',
                    unsafe_allow_html=True
                )

    else:
        st.markdown('<p class="section-title">📦 매장별 배분 예정 내역</p>', unsafe_allow_html=True)

        for store, total_qty in sorted_stores:
            chute = store_map.get(store, "-")
            done = st.session_state.store_processed_qty.get(store, 0)
            remain = max(total_qty - done, 0)
            st.markdown(
                f'<div class="plan-card">{store} (슈트 {chute}) | 총 {total_qty}개 | 잔여 {remain}개</div>',
                unsafe_allow_html=True
            )

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
# 관리자 모드 전용
# ===============================
if view_mode == "관리자 모드":
    st.markdown('<p class="section-title">📊 관리자 진척율</p>', unsafe_allow_html=True)

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
