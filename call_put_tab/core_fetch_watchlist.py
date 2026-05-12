"""
core_fetch_watchlist.py — 관심종목 관리 로직
════════════════════════════════════════════════════════
포함 내용:
  - CoreFetchWatchlistMixin
      _is_futures_sym()            선물 심볼 판별
      _active_watchlist()          포커스된 QListWidget 반환
      _w_add() / _w_del()          항목 추가/삭제
      _w_move_up() / _w_move_down() 순서 이동
      _w_save() / _w_load()        JSON 저장/복원
      _apply_watchlist_font()      폰트 적용
      _on_watch_dbl()              2클릭: 종목 변경 + 전체 조회
      _on_watch_single_click()     1클릭: 기초자산 구독만
════════════════════════════════════════════════════════
"""

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QInputDialog, QMessageBox

from core import save_json, load_json, is_market_open
from call_put_tab.core_fetch_table import CoreFetchTableMixin, _DummyLabel
from call_put_tab.core_fetch_contracts import _alive


class CoreFetchWatchlistMixin(CoreFetchTableMixin):
    """관심종목 관리 로직."""

    _WATCH_FILE   = "watchlist.json"
    _FUT_PREFIXES = ("/", "ES", "NQ", "CL", "GC", "SI", "RTY", "YM")

    @staticmethod
    def _is_futures_sym(sym: str) -> bool:
        """심볼이 선물 종목인지 판별."""
        s = sym.strip().upper()
        if s.startswith("/"):
            return True
        return s in {"ES", "NQ", "CL", "GC", "SI", "RTY", "YM",
                     "MES", "MNQ", "MCL"}

    def _active_watchlist(self):
        """현재 포커스가 있는 QListWidget 반환 (선물/일반 구분)."""
        fut = getattr(self, 'watchlist_fut', None)
        if fut and fut.currentRow() >= 0:
            return fut
        return self.watchlist

    def _w_add(self):
        """심볼 입력 후 선물/일반 자동 분류하여 해당 패널에 추가."""
        t, ok = QInputDialog.getText(self, "추가", "심볼:")
        if not ok or not t.strip():
            return
        sym = t.strip().upper()
        fut = getattr(self, 'watchlist_fut', None)
        if fut and self._is_futures_sym(sym):
            fut.addItem(sym)
        else:
            self.watchlist.addItem(sym)
        self._apply_watchlist_font()
        self._w_save()

    def _w_del(self):
        """현재 선택된 패널에서 선택 항목 삭제."""
        lst = self._active_watchlist()
        r   = lst.currentRow()
        if r >= 0:
            lst.takeItem(r)
            self._w_save()

    def _w_move_up(self):
        """선택 항목을 한 칸 위로 이동."""
        lst = self._active_watchlist()
        r   = lst.currentRow()
        if r <= 0:
            return
        item = lst.takeItem(r)
        lst.insertItem(r - 1, item)
        lst.setCurrentRow(r - 1)
        self._w_save()

    def _w_move_down(self):
        """선택 항목을 한 칸 아래로 이동."""
        lst = self._active_watchlist()
        r   = lst.currentRow()
        if r < 0 or r >= lst.count() - 1:
            return
        item = lst.takeItem(r)
        lst.insertItem(r + 1, item)
        lst.setCurrentRow(r + 1)
        self._w_save()

    def _w_save(self):
        """관심종목 전체를 SAVE_DIR/watchlist.json 에 저장.
        v6.5: {"futures": [...], "stocks": [...]} 구조.
        """
        stocks  = [self.watchlist.item(i).text()
                   for i in range(self.watchlist.count())]
        fut_lst = getattr(self, 'watchlist_fut', None)
        futures = ([fut_lst.item(i).text() for i in range(fut_lst.count())]
                   if fut_lst else [])
        try:
            save_json(self._WATCH_FILE, {"futures": futures, "stocks": stocks})
        except Exception as e:
            self._log(f"[watchlist] 저장 실패: {e}")

    def _w_load(self):
        """watchlist.json 읽어 관심종목 복원.
        v6.5: 새 구조(dict) + 구버전(list) 모두 호환.
        v6.6: list 원소가 dict인 경우 방어 처리 추가.
        """
        raw = load_json(self._WATCH_FILE, [])
        if not raw:
            return

        if isinstance(raw, dict):
            futures = raw.get("futures", [])
            stocks  = raw.get("stocks",  [])
        elif isinstance(raw, list) and raw and isinstance(raw[0], dict):
            inner   = raw[0]
            futures = inner.get("futures", [])
            stocks  = inner.get("stocks",  [])
            self._log("[watchlist] ⚠ 잘못된 저장 포맷 감지 — 자동 복구됨")
        else:
            safe    = [s for s in raw if isinstance(s, str)]
            futures = [s for s in safe if self._is_futures_sym(s)]
            stocks  = [s for s in safe if not self._is_futures_sym(s)]

        fut_lst = getattr(self, 'watchlist_fut', None)

        self.watchlist.blockSignals(True)
        self.watchlist.clear()
        for sym in stocks:
            self.watchlist.addItem(sym)
        self.watchlist.blockSignals(False)

        if fut_lst:
            fut_lst.blockSignals(True)
            fut_lst.clear()
            for sym in futures:
                fut_lst.addItem(sym)
            fut_lst.blockSignals(False)
        else:
            self.watchlist.blockSignals(True)
            for sym in futures:
                self.watchlist.addItem(sym)
            self.watchlist.blockSignals(False)

        self._apply_watchlist_font()

    def _apply_watchlist_font(self):
        """관심종목 QListWidget 폰트 +3, 굵은 글씨 적용."""
        from PyQt5.QtGui import QFont
        targets = [self.watchlist]
        fut_lst = getattr(self, 'watchlist_fut', None)
        if fut_lst:
            targets.append(fut_lst)

        for lst in targets:
            f = lst.font()
            if not getattr(self, '_watch_font_applied', False):
                f.setPointSize(f.pointSize() + 3)
            f.setBold(True)
            lst.setFont(f)
            for i in range(lst.count()):
                item = lst.item(i)
                if item:
                    item.setFont(f)

        self._watch_font_applied = True

    def _on_watch_dbl(self, item):
        """2클릭 → 종목 변경 + 기초자산 + 옵션 전체 조회(_fetch 포함).
        v6.5: 선물/일반 두 패널 모두 연결됨.
        """
        if not _alive(self):
            return

        sym = item.text().strip().upper().replace("SPXW", "SPX")

        if getattr(self, '_fetch_busy', False):
            self._log(f"⚠ 구독 진행 중 — {sym} 더블클릭 무시 (완료 후 재시도)")
            return

        self.edit_sym.setText(sym)
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 연결하세요.")
            return

        self._und_timer.stop()
        self._und_is_futures = False

        t_exp = getattr(self, '_next_expiry_timer', None)
        if t_exp is not None:
            t_exp.stop()

        if sym in getattr(self, '_IBKR_EXPIRY_SYMS', set()):
            if hasattr(self, '_refresh_expiry_list'):
                self._refresh_expiry_list()

        if hasattr(self, '_side_und_sym'):
            self._side_und_sym.setText(sym)

        self.und_price = None
        self.lbl_und.setText("조회 중…")
        if hasattr(self, '_pp_switch_to_und'):
            self._pp_switch_to_und()

        self._req_und(sym)

        # _req_und가 재예약한 만기 타이머 즉시 재취소
        t_exp = getattr(self, '_next_expiry_timer', None)
        if t_exp is not None:
            t_exp.stop()

        market_open = is_market_open()
        is_spx      = sym in getattr(self, '_SPX_SYMS', {"SPX", "SPXW"})

        if not market_open and is_spx:
            self._und_is_futures = True

        if market_open:
            if hasattr(self, '_fetch_intraday_with_live'):
                self._fetch_intraday_with_live()
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(2)
        else:
            if hasattr(self, '_fetch_daily'):
                self._fetch_daily()
            if hasattr(self, '_fetch_intraday'):
                self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):
                tab_idx = 2 if is_spx else 1
                self._chart_tabs.setCurrentIndex(tab_idx)

        t = getattr(self, '_watch_dbl_timer', None)
        if t is None:
            self._watch_dbl_timer = QTimer(self)
            self._watch_dbl_timer.setSingleShot(True)
            self._watch_dbl_timer.timeout.connect(self._fetch)
        else:
            self._watch_dbl_timer.stop()
        self._watch_dbl_timer.start(1000)

        self._log(f"관심종목 2클릭: {sym}  → 차트 조회 + 옵션 전체 재조회")

    def _on_watch_single_click(self, item):
        """1클릭 → 기초자산 구독 + 현재가 테이블 출력만.
        v6.5: 선물/일반 두 패널 모두 연결됨.
        _fetch() 호출 없음 → 옵션 테이블 재조회 없음.
        """
        sym = item.text().strip().upper().replace("SPXW", "SPX")

        if hasattr(self, 'edit_sym'):
            self.edit_sym.setText(sym)

        if sym in getattr(self, '_IBKR_EXPIRY_SYMS', set()) and self.mw.connected:
            if hasattr(self, '_refresh_expiry_list'):
                self._refresh_expiry_list()

        if hasattr(self, '_pp_switch_to_und'):
            self._pp_switch_to_und()
        if hasattr(self, '_pp_lbl_sym'):
            self._pp_lbl_sym.setText(sym)
        if hasattr(self, '_pp_bid'):  self._pp_bid = None
        if hasattr(self, '_pp_ask'):  self._pp_ask = None
        if hasattr(self, '_pp_lbl_price'):
            self._pp_lbl_price.setText("조회 중…")
        if hasattr(self, '_pp_tbl_quote'):
            from call_put_tab.tab_options import _mk
            self._pp_tbl_quote.setItem(0, 1, _mk("―", "#ff6666"))
            self._pp_tbl_quote.setItem(1, 1, _mk("―", "#33aaff"))

        if hasattr(self, '_side_und_sym'):
            self._side_und_sym.setText(sym)

        market_open      = is_market_open()
        is_spx           = sym in getattr(self, '_SPX_SYMS', {"SPX", "SPXW"})
        self._und_is_futures = (not market_open and is_spx)

        self._req_und(sym)

        if PG:
            self._und_hist.clear()
            if hasattr(self, '_c_und'):
                self._c_und.setData([])

        self._log(f"관심종목 1클릭: {sym}  → 기초자산 구독 (옵션 미조회)")
