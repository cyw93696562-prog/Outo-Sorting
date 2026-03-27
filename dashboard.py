import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit.components.v1 import html

st.set_page_config(page_title="WCS 웹", layout="wide")

# ===============================
# 화면 스타일
# ===============================
st.markdown("""
<style>
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 1.2rem;
    max-width: 1400px;
}
h1 {
    font-size: 48px !important;
}
h2, h3 {
    font-size: 34px !important;
}
.stTextInput label {
    font-size: 24px !important;
    font-weight: 700 !important;
}
.stTextInput input {
    font-size: 30px !important;
    height: 68px !important;
}
.big-message {
    font-size: 28px;
    font-weight: 700;
    padding: 14px 18px;
    border-radius: 10px;
    margin-bottom: 12px;
}
.msg-success {
    background-color: #e8f5e9;
    color: #1b5e20;
}
.msg-warning {
    background-color: #fff8e1;
    color: #8d6e00;
}
.msg-error {
    background-color: #ffebee;
    color: #b71c1c;
}
.msg-info {
    background-color: #f3f6fb;
    color: #1f3b5c;
}
.store-done {
    font-size: 26px;
    font-weight: 700;
    margin-bottom: 10px;
}
.small-caption {
    font-size: 18px !important;
}
</style>
""", unsafe_allow_html=True)

st.title("📦 WCS 자동 소터 시스템")

# ===============================
# 1. 엑셀에서 주문 불러오기
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

# product 컬럼이 없으면 barcode를 대신 사용
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
# 2. 매장별 총 수량 계산
# ===============================
store_total_qty = {}

for items in orders.values():
    for item in items:
        store = item["store"]
        qty = item["qty"]
        store_total_qty[store] = store_total_qty.get(store, 0) + qty

# ===============================
# 3. 세션 상태
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

if "barcode_input" not in st.session_state:
    st.session_state.barcode_input = ""

# ===============================
# 4. 수량 기준 정렬 (많은 순)
# ===============================
sorted_stores = sorted(
    store_total_qty.items(),
    key=lambda x: x[1],
    reverse=True
)

# ===============================
# 5. 슈트 자동 배정 (1매장=1슈트)
# ===============================
store_map = {}
chute_no = 1

for store, _ in sorted_stores:
    store_map[store] = chute_no
    chute_no += 1

# ===============================
# 6. 처리 함수
# ===============================
def process_barcode():
    barcode = st.session_state.barcode_input.strip()
    messages = []

    if not barcode:
        return

    if barcode in st.session_state.processed:
        messages.append(("warning", "⚠️ 이미 처리된 바코드입니다."))
    elif barcode not in orders:
        messages.append(("error", "❌ 주문 없음"))
        st.session_state.error_count += 1
    else:
        items = orders[barcode]

        for item in items:
            store = item["store"]
            qty = item["qty"]
            product = item["product"]

            if store not in store_map:
                messages.append(("error", f"❌ 매핑 없음 → {store}"))
                st.session_state.error_count += 1
                continue

            chute = store_map[store]
            st.session_state.store_processed_qty[store] += qty

            total = store_total_qty[store]
            done = st.session_state.store_processed_qty[store]

            # 요청하신 표시 형식: 제품명 -> 매장명 1개
            messages.append((
                "info",
                f"👉 {product} → {store} {qty}개 (슈트 {chute})"
            ))

            if done >= total:
                st.session_state.completed_stores.add(store)

        st.session_state.processed.add(barcode)
        messages.append(("success", "✅ 처리 완료"))

    st.session_state.last_messages = messages
    st.session_state.barcode_input = ""

# ===============================
# 7. 전체 진척율 원형 그래프 함수
# ===============================
def make_total_donut(done, total):
    remain = max(total - done, 0)
    percent = 0 if total == 0 else round((done / total) * 100, 1)

    fig = go.Figure(data=[
        go.Pie(
            labels=["완료", "잔여"],
            values=[done, remain],
            hole=0.74,
            textinfo="none",
            sort=False
        )
    ])

    fig.update_layout(
        title={"text": "전체 진척율", "x": 0.5, "xanchor": "center", "font": {"size": 28}},
        showlegend=True,
        height=480,
        margin=dict(t=70, b=20, l=20, r=20),
        annotations=[
            dict(
                text=f"<b style='font-size:34px'>{percent}%</b><br><span style='font-size:22px'>{done}/{total}</span>",
                x=0.5,
                y=0.5,
                showarrow=False
            )
        ]
    )
    return fig

# ===============================
# 8. 입력창
# ===============================
st.text_input(
    "바코드 입력",
    key="barcode_input",
    on_change=process_barcode,
    placeholder="스캐너로 바코드를 찍으면 자동 처리됩니다"
)

st.markdown('<p class="small-caption">스캐너가 엔터를 보내면 자동 처리됩니다.</p>', unsafe_allow_html=True)

# 입력창 자동 포커스
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
    </script>
    """,
    height=0,
)

# ===============================
# 9. 최근 처리 결과 표시
# ===============================
for level, msg in st.session_state.last_messages:
    if level == "success":
        st.markdown(f'<div class="big-message msg-success">{msg}</div>', unsafe_allow_html=True)
    elif level == "warning":
        st.markdown(f'<div class="big-message msg-warning">{msg}</div>', unsafe_allow_html=True)
    elif level == "error":
        st.markdown(f'<div class="big-message msg-error">{msg}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="big-message msg-info">{msg}</div>', unsafe_allow_html=True)

# ===============================
# 10. 완료된 매장 목록
# ===============================
st.subheader("✅ 완료된 매장 목록 (100%)")

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
# 11. 전체 상태
# ===============================
st.subheader("📊 전체 상태")

total_qty_all = sum(store_total_qty.values())
done_qty_all = sum(st.session_state.store_processed_qty.values())

col1, col2 = st.columns([2, 1])

with col1:
    fig = make_total_donut(done_qty_all, total_qty_all)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.metric("정상 처리 바코드", len(st.session_state.processed))
    st.metric("에러", st.session_state.error_count)
    st.metric("전체 투입수량", done_qty_all)
    st.metric("전체 총수량", total_qty_all)
