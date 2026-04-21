"""
kr_chart_theme.py — 다크/라이트 팔레트 + 테마 적용
"""
try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

_THEME = {
    True: dict(
        widget_bg="#1e1e1e", panel_bg="#2b2b2b", fg="#e8e8e8",
        border="#444444",    accent="#90caf9",
        tbl_bg="#1a1a2a",    tbl_sel="#1c3a6a",
        hdr_bg="#141430",    hdr_fg="#5dade2",
        chart_bg=(30, 30, 30),
        candle_up="#3c78ff", candle_dn="#ff3c3c",
        row_hi="#7f1f1f",    row_mid="#7f4f1f",  row_lo="#5f5f10",
        scrollbar="#444",
    ),
    False: dict(
        widget_bg="#f5f5f5", panel_bg="#ffffff",  fg="#111111",
        border="#cccccc",    accent="#1565c0",
        tbl_bg="#ffffff",    tbl_sel="#bbdefb",
        hdr_bg="#e3f2fd",    hdr_fg="#1565c0",
        chart_bg=(245, 245, 245),
        candle_up="#3c78ff", candle_dn="#ff3c3c",
        row_hi="#ffcccc",    row_mid="#ffe0b2",   row_lo="#fff9c4",
        scrollbar="#bbb",
    ),
}


def apply_theme(self):
    C = _THEME[self.dark_mode]
    self.setStyleSheet(f"""
        QWidget      {{ background:{C['widget_bg']}; color:{C['fg']}; }}
        QGroupBox    {{ border:1px solid {C['border']}; border-radius:4px;
                       margin-top:8px; padding-top:6px; font-weight:bold; }}
        QGroupBox::title {{ subcontrol-origin:margin; left:6px; color:{C['accent']}; }}
        QLineEdit, QSpinBox, QListWidget, QCalendarWidget
                     {{ background:{C['panel_bg']}; color:{C['fg']};
                        border:1px solid {C['border']}; border-radius:3px; }}
        QPushButton  {{ background:{C['panel_bg']}; color:{C['fg']};
                        border:1px solid {C['border']}; border-radius:3px; padding:2px 6px; }}
        QPushButton:hover {{ background:{C['accent']}; color:#ffffff; }}
        QComboBox    {{ background:{C['panel_bg']}; color:{C['fg']};
                        border:1px solid {C['border']}; border-radius:3px; }}
        QTableWidget {{ background:{C['tbl_bg']}; color:{C['fg']};
                        gridline-color:{C['border']}; border:1px solid {C['border']}; }}
        QTableWidget::item:selected {{ background:{C['tbl_sel']}; }}
        QHeaderView::section {{ background:{C['hdr_bg']}; color:{C['hdr_fg']};
                                border:1px solid {C['border']}; padding:3px; }}
        QCheckBox, QRadioButton {{ color:{C['fg']}; background:transparent; }}
        QLabel       {{ color:{C['fg']}; background:transparent; }}
        QScrollArea  {{ border:none; background:{C['widget_bg']}; }}
        QScrollBar:vertical {{ background:{C['widget_bg']}; width:8px; }}
        QScrollBar::handle:vertical {{ background:{C['scrollbar']};
                                      border-radius:4px; min-height:20px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
    """)
    if PG and hasattr(self, 'gfx'):
        self.gfx.setBackground(C['chart_bg'])
        for pl in (self.p1, self.p2):
            pl.getAxis('bottom').setPen(pg.mkPen(C['fg']))
            pl.getAxis('left').setPen(pg.mkPen(C['fg']))
            pl.getAxis('bottom').setTextPen(pg.mkPen(C['fg']))
            pl.getAxis('left').setTextPen(pg.mkPen(C['fg']))
    if self.is_rt:
        self.btn_rt.setStyleSheet(
            "background:#8b0000;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")
    else:
        self.btn_rt.setStyleSheet(
            "background:#1a6b3c;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")


def c_up(self) -> str:
    return _THEME[self.dark_mode]['candle_up']


def c_dn(self) -> str:
    return _THEME[self.dark_mode]['candle_dn']
