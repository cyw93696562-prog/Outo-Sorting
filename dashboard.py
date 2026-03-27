import streamlit as st
import pandas as pd

st.set_page_config(page_title="WCS 웹", layout="wide")
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

orders = {}

for _, row in df.iterrows():
    barcode = str(row["barcode"])
    store = str(row["store"])
    qty = int(row["qty"])

    if barcode not in orders:
        orders[barcode] = []

    orders[barcode].append({
        "store": store,
        "qty": qty
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
# 3. 매장별 처리 수량 (진척)
# ===============================
if "store_processed_qty" not in st.session_state:
    st.session_state.store_processed_qty = {store: 0 for store in store_total_qty}

if "completed_stores" not in st.session_state:
    st.session_state.completed_stores = set()

if "processed" not in st.session_state:
    st.session_state.processed = set()

if "error_count" not in st.session_state:
    st.session_state.error_count = 0

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

for store, total_qty in sorted_stores:
    store_map[store] = chute_no
    chute_no += 1

# ===============================
# 6. 슈트 배정 결과 표시
# ===============================
with st.expander("매장별 슈트 자동 배정 결과", expanded=False):
    for store, chute in store_map.items():
        st.write(f"{store} → 슈트 {chute}")

# ===============================
# 7. 바코드 입력
# ===============================
barcode = st.text_input("바코드 입력")

if st.button("처리 실행"):
    if not barcode:
        st.warning("바코드를 입력하세요.")
    elif barcode in st.session_state.processed:
        st.warning("이미 처리된 바코드입니다.")
    elif barcode not in orders:
        st.error("주문 없음 → ERROR 처리")
        st.session_state.error_count += 1
    else:
        st.success(f"[WCS 처리 시작] {barcode}")

        stores = orders[barcode]

        for item in stores:
            store = item["store"]
            qty = item["qty"]

            if store not in store_map:
                st.error(f"매핑 없음 → {store}")
                st.session_state.error_count += 1
                continue

            chute = store_map[store]

            st.session_state.store_processed_qty[store] += qty

            total = store_total_qty[store]
            done = st.session_state.store_processed_qty[store]
            progress = (done / total) * 100

            st.write(
                f"👉 {barcode} → {store} ({qty}개) → 슈트 {chute} | 진행: {done}/{total} ({progress:.1f}%)"
            )

            if done == total:
                st.session_state.completed_stores.add(store)

        st.session_state.processed.add(barcode)
        st.success(f"[완료] {barcode}")

# ===============================
# 8. 완료된 매장만 출력
# ===============================
st.subheader("✅ 완료된 매장 목록 (100%)")

if not st.session_state.completed_stores:
    st.write("아직 완료된 매장 없음")
else:
    for store in sorted(st.session_state.completed_stores):
        st.write(f"{store} ✅ 완료")

# ===============================
# 9. 전체 상태
# ===============================
st.subheader("📊 전체 상태")
col1, col2 = st.columns(2)
col1.metric("정상 처리", len(st.session_state.processed))
col2.metric("에러", st.session_state.error_count)
