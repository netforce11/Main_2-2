"""
combo_op_worker.py — 백그라운드 탐색 QThread Worker
────────────────────────────────────────────────────
위치: main2/combo_libs/combo_op/combo_op_worker.py
"""

from PyQt5.QtCore import QThread, pyqtSignal


class _SearchWorker(QThread):
    """탐색 로직을 백그라운드 스레드에서 실행. UI 프리징 방지."""
    done  = pyqtSignal(list)   # 탐색 완료 → 결과 리스트
    error = pyqtSignal(str)    # 에러 발생 → 메시지

    def __init__(self, fn, *args):
        super().__init__()
        self._fn   = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))
