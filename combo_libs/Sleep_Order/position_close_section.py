"""
position_close_section.py — 포지션 청산 예약 설정 UI v3.0
════════════════════════════════════════════════════════════════
슬롯 3개, 각 슬롯:
  From / To KST 시간 범위
  선매도 목표가 ($) — 사정권 = 목표가 - 2틱
  최대 정정 횟수
  등록 / 저장 / 취소 버튼
  실시간 상태 라벨
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer

from Sleep_Order.ui_helpers import (
    gb, lbl, btn, dspinbox, time_edit, spinbox, sep,
    update_et_preview, load_kst_time, _is_edt,
)

_N_SLOTS = 3


# ══════════════════════════════════════════════════════════════
# 메인 빌더
# ══════════════════════════════════════════════════════════════

def build_position_close_section(parent) -> QGroupBox:
    g   = gb("🎯  포지션 청산 설정", "#ff6b6b")
    lay = QVBoxLayout(g)
    lay.setContentsMargins(10, 14, 10, 10)
    lay.setSpacing(8)

    tz = "EDT" if _is_edt() else "EST"

    hint = lbl("잔고 탭에서 포지션 선택 후 슬롯에 등록하세요", "#ffd066", 11)
    lay.addWidget(hint)
    lay.addWidget(sep())

    parent._close_slots = []
    for i in range(_N_SLOTS):
        lay.addWidget(_build_slot(parent, i, tz))
        if i < _N_SLOTS - 1:
            lay.addWidget(sep())

    QTimer.singleShot(0, lambda: _connect_watcher(parent))
    _load_all_slots(parent)
    return g


# ══════════════════════════════════════════════════════════════
# 슬롯 1개 빌드
# ══════════════════════════════════════════════════════════════

def _build_slot(parent, idx: int, tz: str) -> QGroupBox:
    colors = ["#ff6b6b", "#ffd700", "#5dade2"]
    color  = colors[idx % len(colors)]

    g = QGroupBox(f"  슬롯 {idx+1}")
    g.setStyleSheet(
        f"QGroupBox{{font-size:13px;color:{color};font-weight:bold;"
        f"border:1px solid {color}55;border-radius:6px;"
        f"margin-top:8px;padding-top:6px;background:#06060e;}}"
        f"QGroupBox::title{{subcontrol-origin:margin;left:10px;}}")
    lay = QGridLayout(g)
    lay.setContentsMargins(10, 12, 10, 8)
    lay.setSpacing(6)
    r = 0

    # ── 등록 포지션 표시 ──────────────────────────────────────
    lay.addWidget(lbl("포지션:", "#aaa", 12), r, 0, Qt.AlignRight)
    pos_lbl = QLabel("― 미등록 ―")
    pos_lbl.setStyleSheet(
        "color:#555577;font-size:12px;border:none;"
        "background:#0a0a18;border-radius:3px;padding:2px 6px;")
    pos_lbl.setWordWrap(True)
    lay.addWidget(pos_lbl, r, 1, 1, 5)
    r += 1

    # ── From / To 시각 ────────────────────────────────────────
    lay.addWidget(lbl(f"From (KST):", "#aaa", 12), r, 0, Qt.AlignRight)
    te_from = time_edit("23:00")
    lay.addWidget(te_from, r, 1)

    lay.addWidget(lbl("To:", "#aaa", 12), r, 2, Qt.AlignRight)
    te_to = time_edit("01:30")
    lay.addWidget(te_to, r, 3)

    # ET 미리보기 (From 기준)
    et_lbl = lbl(f"→ {tz} --:--", "#666", 11)
    te_from.timeChanged.connect(lambda: update_et_preview(te_from, et_lbl))
    lay.addWidget(et_lbl, r, 4, 1, 2)
    r += 1

    # ── 선매도 목표가 + 정정 횟수 ─────────────────────────────
    lay.addWidget(lbl("선매도 목표가:", "#aaa", 12), r, 0, Qt.AlignRight)
    dsb = dspinbox(0.01, 99.99, 1.00, 0.05, prefix="$")
    lay.addWidget(dsb, r, 1)

    # 사정권 미리보기 라벨
    thresh_lbl = lbl("사정권 ≤$0.90", "#888", 11)
    dsb.valueChanged.connect(lambda v: _update_thresh_lbl(thresh_lbl, v))
    lay.addWidget(thresh_lbl, r, 2, 1, 2)

    lay.addWidget(lbl("최대 정정:", "#aaa", 12), r, 4, Qt.AlignRight)
    sb = spinbox(1, 10, 3, "회")
    lay.addWidget(sb, r, 5)
    r += 1

    # ── 버튼 행 ───────────────────────────────────────────────
    btn_row = QHBoxLayout()

    reg_btn = QPushButton(f"📌 슬롯{idx+1} 등록")
    reg_btn.setFixedHeight(24)
    reg_btn.setStyleSheet(
        f"QPushButton{{background:#0a1a0a;color:{color};font-size:12px;"
        f"font-weight:bold;border:1px solid {color}88;"
        f"border-radius:4px;padding:2px 10px;}}"
        f"QPushButton:hover{{background:#1a2a1a;}}"
        f"QPushButton:disabled{{color:#333;border-color:#222;}}")
    btn_row.addWidget(reg_btn)

    save_btn = QPushButton("💾 저장")
    save_btn.setFixedHeight(24)
    save_btn.setStyleSheet(
        "QPushButton{background:#0a0a1a;color:#90caf9;font-size:12px;"
        "border:1px solid #3a3a7a;border-radius:4px;padding:2px 10px;}"
        "QPushButton:hover{background:#1a1a2a;}")
    btn_row.addWidget(save_btn)

    cancel_btn = QPushButton("✕ 취소")
    cancel_btn.setFixedHeight(24)
    cancel_btn.setEnabled(False)
    cancel_btn.setStyleSheet(
        "QPushButton{background:#1a0a0a;color:#ff6666;font-size:12px;"
        "border:1px solid #6a1a1a;border-radius:4px;padding:2px 10px;}"
        "QPushButton:hover{background:#2a0a0a;}"
        "QPushButton:disabled{color:#333;border-color:#222;}")
    btn_row.addWidget(cancel_btn)
    btn_row.addStretch()
    lay.addLayout(btn_row, r, 0, 1, 6)
    r += 1

    # ── 상태 라벨 ─────────────────────────────────────────────
    status_lbl = lbl("⏸ 비활성", "#444466", 11)
    status_lbl.setWordWrap(True)
    lay.addWidget(status_lbl, r, 0, 1, 6)

    # ── refs 저장 ─────────────────────────────────────────────
    slot_refs = {
        "pos_lbl":    pos_lbl,
        "te_from":    te_from,
        "te_to":      te_to,
        "et_lbl":     et_lbl,
        "thresh_lbl": thresh_lbl,
        "dsb":        dsb,
        "sb":         sb,
        "reg_btn":    reg_btn,
        "save_btn":   save_btn,
        "cancel_btn": cancel_btn,
        "status_lbl": status_lbl,
    }
    parent._close_slots.append(slot_refs)

    # ── 시그널 연결 ───────────────────────────────────────────
    reg_btn.clicked.connect(   lambda _, i=idx: _on_register(parent, i))
    save_btn.clicked.connect(  lambda _, i=idx: _save_slot(parent, i))
    cancel_btn.clicked.connect(lambda _, i=idx: _on_cancel(parent, i))

    update_et_preview(te_from, et_lbl)
    _update_thresh_lbl(thresh_lbl, dsb.value())
    return g


def _update_thresh_lbl(lbl_w: QLabel, price: float) -> None:
    """사정권 미리보기: 목표가 - 2틱."""
    tick   = 0.10 if price >= 3.00 else 0.05
    thresh = round(price - 2 * tick, 2)
    lbl_w.setText(f"사정권 ≤${thresh:.2f}")
    lbl_w.setStyleSheet("color:#ffaa44;font-size:11px;border:none;")


# ══════════════════════════════════════════════════════════════
# 이벤트 핸들러
# ══════════════════════════════════════════════════════════════

def _on_register(parent, idx: int) -> None:
    from Sleep_Order.position_close_watcher import PositionCloseWatcher

    ref = _find_ref(parent)
    if ref is None:
        _set_status(parent, idx, "⚠️ ref 탐색 실패")
        return

    panel = getattr(ref, "synthetic_panel", None)
    if panel is None:
        _set_status(parent, idx, "⚠️ synthetic_panel 없음")
        return

    row = getattr(panel, "_selected_pos_row", -1)
    if row < 0 or row >= len(getattr(panel, "_positions", [])):
        _set_status(parent, idx, "⚠️ 잔고에서 포지션을 먼저 선택하세요")
        return

    pos    = panel._positions[row]
    status = pos.get("status", "")
    if status not in ("체결완료", "보유"):
        _set_status(parent, idx, "⚠️ 보유 중인 포지션만 등록 가능")
        return

    # 중복 등록 체크
    oid = pos.get("oid")
    from Sleep_Order.position_close_config import pos_close_cfg
    for i in range(_N_SLOTS):
        if i != idx and pos_close_cfg.get_slot(i).get("oid") == oid:
            _set_status(parent, idx, f"⚠️ 이미 슬롯{i+1}에 등록됨")
            return

    # 설정 저장 후 등록
    _save_slot(parent, idx)
    PositionCloseWatcher.get().register(idx, pos, ref)

    strat = pos.get("strategy", "")
    sl    = parent._close_slots[idx]
    sl["pos_lbl"].setText(f"OID={oid}  {strat}")
    sl["pos_lbl"].setStyleSheet(
        "color:#00ff88;font-size:12px;border:none;"
        "background:#071a0e;border-radius:3px;padding:2px 6px;")
    sl["cancel_btn"].setEnabled(True)
    sl["reg_btn"].setEnabled(False)


def _on_cancel(parent, idx: int) -> None:
    from Sleep_Order.position_close_watcher import PositionCloseWatcher
    from Sleep_Order.position_close_config  import pos_close_cfg
    PositionCloseWatcher.get().cancel(idx)
    pos_close_cfg.clear_slot(idx)
    sl = parent._close_slots[idx]
    sl["pos_lbl"].setText("― 미등록 ―")
    sl["pos_lbl"].setStyleSheet(
        "color:#555577;font-size:12px;border:none;"
        "background:#0a0a18;border-radius:3px;padding:2px 6px;")
    sl["cancel_btn"].setEnabled(False)
    sl["reg_btn"].setEnabled(True)


def _on_slot_status(parent, idx: int, text: str) -> None:
    _set_status(parent, idx, text)
    if text.startswith("✅"):
        QTimer.singleShot(5500, lambda: _reset_slot_ui(parent, idx))


def _reset_slot_ui(parent, idx: int) -> None:
    if not hasattr(parent, "_close_slots"):
        return
    sl = parent._close_slots[idx]
    sl["pos_lbl"].setText("― 미등록 ―")
    sl["pos_lbl"].setStyleSheet(
        "color:#555577;font-size:12px;border:none;"
        "background:#0a0a18;border-radius:3px;padding:2px 6px;")
    sl["cancel_btn"].setEnabled(False)
    sl["reg_btn"].setEnabled(True)
    _set_status(parent, idx, "⏸ 비활성")


def _set_status(parent, idx: int, text: str) -> None:
    if not hasattr(parent, "_close_slots"):
        return
    w = parent._close_slots[idx]["status_lbl"]
    if text.startswith("✅"):
        color = "#00ff88"
    elif text.startswith("⚠️") or text.startswith("🚨"):
        color = "#ff4444"
    elif "감시" in text or "주문" in text or "정정" in text:
        color = "#ffd700"
    elif "대기" in text:
        color = "#90caf9"
    else:
        color = "#444466"
    w.setText(text)
    w.setStyleSheet(f"color:{color};font-size:11px;border:none;")


# ══════════════════════════════════════════════════════════════
# 저장 / 로드
# ══════════════════════════════════════════════════════════════

def _save_slot(parent, idx: int) -> None:
    from Sleep_Order.position_close_config import pos_close_cfg
    sl    = parent._close_slots[idx]
    frm   = sl["te_from"].time().toString("HH:mm")
    to    = sl["te_to"].time().toString("HH:mm")
    price = sl["dsb"].value()
    max_c = sl["sb"].value()
    pos_close_cfg.set_slot(idx, "close_from_kst",        frm)
    pos_close_cfg.set_slot(idx, "close_to_kst",          to)
    pos_close_cfg.set_slot(idx, "close_premium_price",   price)
    pos_close_cfg.set_slot(idx, "close_max_corrections", max_c)
    pos_close_cfg.save()
    _set_status(parent, idx, "✅ 저장됨")
    print(f"[PosCfg] 슬롯{idx+1}: {frm}~{to} KST / ${price:.2f} / {max_c}회")


def _load_all_slots(parent) -> None:
    from Sleep_Order.position_close_config import pos_close_cfg
    for idx in range(_N_SLOTS):
        cfg = pos_close_cfg.get_slot(idx)
        sl  = parent._close_slots[idx]
        load_kst_time(sl["te_from"], cfg["close_from_kst"])
        load_kst_time(sl["te_to"],   cfg["close_to_kst"])
        update_et_preview(sl["te_from"], sl["et_lbl"])
        sl["dsb"].setValue(float(cfg["close_premium_price"]))
        sl["sb"].setValue(int(cfg["close_max_corrections"]))
        _update_thresh_lbl(sl["thresh_lbl"], float(cfg["close_premium_price"]))
        # 이미 등록된 포지션 복원
        oid   = cfg.get("oid")
        strat = cfg.get("strategy", "")
        if oid:
            sl["pos_lbl"].setText(f"OID={oid}  {strat}")
            sl["pos_lbl"].setStyleSheet(
                "color:#ffd700;font-size:12px;border:none;"
                "background:#1a1a0e;border-radius:3px;padding:2px 6px;")
            sl["cancel_btn"].setEnabled(True)
            sl["reg_btn"].setEnabled(False)
            _set_status(parent, idx, "⏳ 재연결 대기 — 등록 버튼으로 재시작")


# ══════════════════════════════════════════════════════════════
# watcher 연결 / ref 탐색
# ══════════════════════════════════════════════════════════════

def _connect_watcher(parent) -> None:
    try:
        from Sleep_Order.position_close_watcher import PositionCloseWatcher
        PositionCloseWatcher.get().slot_status_changed.connect(
            lambda idx, text: _on_slot_status(parent, idx, text))
    except Exception as e:
        print(f"[PosCloseSection] watcher 연결 실패: {e}")


def _find_ref(widget) -> object | None:
    w = widget
    for _ in range(12):
        w = w.parent() if w else None
        if w is None:
            break
        if hasattr(w, "synthetic_panel") and hasattr(w, "_sleep_get_chain"):
            return w
    return None
