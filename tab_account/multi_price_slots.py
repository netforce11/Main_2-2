"""
multi_price_slots.py — MultiPriceGrid 슬롯 UI 빌드 (3개 슬롯 + 스플리터)
════════════════════════════════════════════════════════
포함 내용:
  - MultiPriceSlotsMixin
      _build_slots()           슬롯 3개 수평 스플리터 구성
      _get_extra_settings()    스플리터 비율 저장
      _apply_extra_settings()  스플리터 비율 복원
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QGroupBox, QListWidget,
    QSplitter,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from core import make_table, tbl_set

_SPLITTER_STYLE = (
    "QSplitter::handle:horizontal{background:#5a5a9a;"
    "border-left:1px solid #00aaff;border-right:1px solid #00aaff;margin:4px 0;}"
    "QSplitter::handle:horizontal:hover{background:#5dade2;"
    "border-left:1px solid #00e676;border-right:1px solid #00e676;}"
    "QSplitter::handle:vertical{background:#5a5a9a;"
    "border-top:1px solid #00aaff;border-bottom:1px solid #00aaff;margin:0 4px;}"
    "QSplitter::handle:vertical:hover{background:#5dade2;"
    "border-top:1px solid #00e676;border-bottom:1px solid #00e676;}"
)


class MultiPriceSlotsMixin:
    """슬롯 UI 빌드 Mixin."""

    def _build_watchlist(self):
        """관심종목 위젯 빌드 → [1,0] 배치."""
        gb_w = QGroupBox("관심종목")
        vw   = QVBoxLayout(gb_w)
        self.watch = QListWidget()
        self.watch.addItems([
            "SPX", "SPXW", "NDX", "QQQ", "SPY",
            "AAPL", "TSLA", "NVDA", "AMZN", "MSFT"])
        self.watch.itemClicked.connect(self._on_watch_click)
        vw.addWidget(self.watch)
        wa = QHBoxLayout()
        ba = QPushButton("추가"); bd = QPushButton("삭제")
        ba.setFixedHeight(22);   bd.setFixedHeight(22)
        ba.clicked.connect(self._w_add); bd.clicked.connect(self._w_del)
        wa.addWidget(ba); wa.addWidget(bd)
        vw.addLayout(wa)
        self.add(gb_w, 1, 0, 1, 1)

    def _build_slots(self):
        """슬롯 3개를 수평 스플리터로 묶어 row0 전체에 배치."""
        self.slot_w          = []
        self._slot_splitters = []

        self._slots_hsplit = QSplitter(Qt.Horizontal)
        self._slots_hsplit.setHandleWidth(5)
        self._slots_hsplit.setStyleSheet(_SPLITTER_STYLE)
        self._slots_hsplit.setChildrenCollapsible(False)

        for i in range(self.SLOTS):
            gb    = QGroupBox(f"슬롯 {i+1}")
            v_spl = QSplitter(Qt.Vertical)
            v_spl.setHandleWidth(5)
            v_spl.setStyleSheet(_SPLITTER_STYLE)
            v_spl.setChildrenCollapsible(False)

            top_w = QWidget()
            top_v = QVBoxLayout(top_w)
            top_v.setSpacing(3); top_v.setContentsMargins(4, 4, 4, 4)

            lsym = QLabel("―")
            lsym.setFont(QFont("Arial", 12, QFont.Bold))
            lsym.setStyleSheet("color:#ffd700;border:none;")
            lsym.setAlignment(Qt.AlignCenter)

            lprice = QLabel("현재가: ―")
            lprice.setFont(QFont("Arial", 22, QFont.Bold))
            lprice.setAlignment(Qt.AlignCenter)
            lprice.setStyleSheet(
                "color:#00ff88;background:#07070f;"
                "border-radius:6px;padding:6px;border:1px solid #1e2050;")
            lprice.setMinimumHeight(54)

            sym_in   = QLineEdit()
            sym_in.setPlaceholderText(f"종목 입력 (슬롯{i+1})")
            sym_in.setFixedHeight(24)
            btn_load = QPushButton("조회")
            btn_load.setFixedHeight(24); btn_load.setFixedWidth(48)
            btn_load.clicked.connect(lambda _, idx=i: self._load_from_input(idx))
            sym_in.returnPressed.connect(lambda idx=i: self._load_from_input(idx))
            inp_row = QHBoxLayout(); inp_row.setContentsMargins(0, 0, 0, 0)
            inp_row.addWidget(sym_in); inp_row.addWidget(btn_load)

            top_v.addWidget(lsym); top_v.addWidget(lprice); top_v.addLayout(inp_row)
            v_spl.addWidget(top_w)

            tbl = make_table(["항목", "값"], 0)
            for kk in ["체결가", "거래량", "Delta", "Gamma", "Theta", "전일종가"]:
                r2 = tbl.rowCount(); tbl.insertRow(r2)
                tbl_set(tbl, r2, 0, kk); tbl_set(tbl, r2, 1, "―")
            v_spl.addWidget(tbl)
            v_spl.setSizes([120, 200])

            gb_v = QVBoxLayout(gb); gb_v.setContentsMargins(2, 2, 2, 2)
            gb_v.addWidget(v_spl)
            self._slot_splitters.append(v_spl)
            self.slot_w.append({"sym": lsym, "price": lprice, "tbl": tbl, "input": sym_in})
            self._slots_hsplit.addWidget(gb)

        self._slots_hsplit.setSizes([400, 400, 400])
        self.add(self._slots_hsplit, 0, 0, 1, 12)

    def _get_extra_settings(self) -> dict:
        d = {}
        try:
            d["slots_hsplit"]     = list(self._slots_hsplit.sizes())
            d["bot_hsplit"]       = list(self._bot_hsplit.sizes())
            d["bot_left_vsplit"]  = list(self._bot_left_vsplit.sizes())
            d["bot_right_vsplit"] = list(self._bot_right_vsplit.sizes())
            d["slot_vsplits"]     = [list(v.sizes()) for v in self._slot_splitters]
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s: dict):
        def _restore():
            try:
                if s.get("slots_hsplit"):    self._slots_hsplit.setSizes(s["slots_hsplit"])
                if s.get("bot_hsplit"):       self._bot_hsplit.setSizes(s["bot_hsplit"])
                if s.get("bot_left_vsplit"):  self._bot_left_vsplit.setSizes(s["bot_left_vsplit"])
                if s.get("bot_right_vsplit"): self._bot_right_vsplit.setSizes(s["bot_right_vsplit"])
                if s.get("slot_vsplits"):
                    for i, sz in enumerate(s["slot_vsplits"]):
                        if i < len(self._slot_splitters):
                            self._slot_splitters[i].setSizes(sz)
            except Exception:
                pass
        QTimer.singleShot(100, _restore)
