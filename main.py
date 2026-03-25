import pandas as pd

# ===============================
# 1. 엑셀에서 주문 불러오기
# ===============================
df = pd.read_excel("orders.xlsx")

orders = {}

for _, row in df.iterrows():
    barcode = str(row["barcode"])
    store = row["store"]
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
store_processed_qty = {store: 0 for store in store_total_qty}

# ===============================
# 4. 완료된 매장 저장
# ===============================
completed_stores = set()

# ===============================
# 5. 수량 기준 정렬 (많은 순)
# ===============================
sorted_stores = sorted(
    store_total_qty.items(),
    key=lambda x: x[1],
    reverse=True
)

# ===============================
# 6. 슈트 자동 배정 (1매장=1슈트)
# ===============================
store_map = {}

chute_no = 1

for store, total_qty in sorted_stores:
    store_map[store] = chute_no
    chute_no += 1

# ===============================
# 7. 배정 결과 확인
# ===============================
print("\n[매장별 슈트 자동 배정 결과]")
for store, chute in store_map.items():
    print(f"{store} → 슈트 {chute}")

# ===============================
# 8. 상태 저장
# ===============================
processed = set()
error_list = set()

# ===============================
# 9. 메인 실행
# ===============================
while True:
    barcode = input("\n바코드 입력 (exit 입력시 종료): ")

    if barcode.lower() == "exit":
        print("프로그램 종료")
        break

    # 중복 체크
    if barcode in processed:
        print("⚠️ 이미 처리된 바코드입니다")
        continue

    # 주문 확인
    if barcode not in orders:
        print("❌ 주문 없음 → ERROR 처리")
        error_list.add(barcode)
        continue

    stores = orders[barcode]

    print(f"\n[WCS 처리 시작] {barcode}")

    # 매장별 처리
    for item in stores:
        store = item["store"]
        qty = item["qty"]

        if store not in store_map:
            print(f"❌ 매핑 없음 → {store}")
            error_list.add(barcode)
            continue

        chute = store_map[store]

        # 처리 수량 누적
        store_processed_qty[store] += qty

        # 진척률 계산
        total = store_total_qty[store]
        done = store_processed_qty[store]
        progress = (done / total) * 100

        print(f"👉 {barcode} → {store} ({qty}개) → 슈트 {chute} | 진행: {done}/{total} ({progress:.1f}%)")

        # ⭐ 100% 완료 체크
        if done == total:
            completed_stores.add(store)

    # 처리 완료
    processed.add(barcode)

    print(f"[완료] {barcode}")

    # ===============================
    # 10. 완료된 매장만 출력
    # ===============================
    print("\n--- 완료된 매장 목록 (100%) ---")
    
    if not completed_stores:
        print("아직 완료된 매장 없음")
    else:
        for store in completed_stores:
            print(f"{store} ✅ 완료")

    # ===============================
    # 전체 상태
    # ===============================
    print("\n--- 전체 상태 ---")
    print(f"정상 처리: {len(processed)}건")
    print(f"에러: {len(error_list)}건")
