"""
sleep_order_config_condition_b.py — 조건 B (AND 동시 체결) 설정 기본값
════════════════════════════════════════════════════════════════════════
sleep_order_config.py 의 _DEFAULTS 딕셔너리에 업데이트로 병합됨.
직접 사용하지 말 것 — sleep_cfg 를 통해 접근.

조건 B 동작 규칙:
  · primary_direction == "put" 일 때:
      풋이 target_price_1(엄격) 통과
        → 콜이 secondary_target_price(느슨) 통과 시에만 동시 발사
        → 콜 조건 미달이면 이번 틱 대기 (다음 틱 재시도)

  · primary_direction == "call" 일 때:
      콜이 call_target_price(엄격) 통과
        → 풋이 secondary_target_price(느슨) 통과 시에만 동시 발사
        → 풋 조건 미달이면 이번 틱 대기 (다음 틱 재시도)
"""

CONDITION_B_DEFAULTS: dict = {
    # 주력 방향: "put" | "call"
    # · 이쪽 목표가를 엄격하게 적용 (target_price_1 또는 call_target_price)
    # · 반대쪽은 secondary_target_price(느슨)로 평가
    "primary_direction":        "put",

    # 보조 방향 목표가 상한 (느슨한 조건, 고정값)
    # · primary 가 조건 통과 시 보조 방향에 적용되는 진입가 상한
    # · 예: 주력 $0.50, 보조 $0.65 → 보조가 $0.65 이하면 함께 발사
    "secondary_target_price":   0.65,
}
