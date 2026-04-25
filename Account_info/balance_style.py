"""
balance_style.py — BalanceGrid 공통 스타일 상수  v2.0
Clean Card Light 테마. BalanceGrid._CS 로 참조.
"""

CS = dict(
    root="background:#f0f2f5;",

    card=(
        "QGroupBox{"
        "background:#ffffff;"
        "border:1px solid #d1d9e0;"
        "border-radius:12px;"
        "margin-top:22px;"
        "padding-top:10px;"
        "padding-left:10px;"
        "padding-right:10px;"
        "padding-bottom:10px;}"
        "QGroupBox::title{"
        "subcontrol-origin:margin;"
        "subcontrol-position:top left;"
        "top:-2px;"
        "left:14px;"
        "padding:2px 6px;"
        "background:#ffffff;"
        "color:#374151;"
        "font-size:11px;"
        "font-weight:700;"
        "letter-spacing:0.5px;}"
    ),

    tbl=(
        "QTableWidget{"
        "background:#ffffff;"
        "alternate-background-color:#f8fafc;"
        "gridline-color:#e8ecf0;"
        "border:none;"
        "font-size:12px;"
        "font-weight:500;"
        "color:#1e293b;}"
        "QHeaderView::section{"
        "background:#f1f5f9;"
        "color:#475569;"
        "border:none;"
        "border-bottom:1px solid #e2e8f0;"
        "font-size:10px;"
        "font-weight:700;"
        "letter-spacing:0.5px;"
        "padding:5px 8px;}"
        "QTableWidget::item:selected{"
        "background:#dbeafe;"
        "color:#1e40af;}"
    ),

    btn_blue=(
        "background:#dbeafe;"
        "color:#1d4ed8;"
        "border:1px solid #93c5fd;"
        "border-radius:8px;"
        "font-size:12px;"
        "font-weight:700;"
        "padding:7px 16px;"
    ),

    btn_gray=(
        "background:#f1f5f9;"
        "color:#334155;"
        "border:1px solid #cbd5e1;"
        "border-radius:8px;"
        "font-size:12px;"
        "font-weight:600;"
        "padding:7px 14px;"
    ),

    btn_green=(
        "background:#dcfce7;"
        "color:#15803d;"
        "border:1px solid #86efac;"
        "border-radius:6px;"
        "font-size:11px;"
        "font-weight:700;"
        "padding:4px 10px;"
    ),

    # 매매일지 탭 버튼
    jnl_tab=(
        "QPushButton{"
        "background:transparent;"
        "color:#64748b;"
        "border:none;"
        "border-bottom:2px solid transparent;"
        "padding:10px 20px;"
        "font-size:12px;"
        "font-weight:700;}"
        "QPushButton:checked{"
        "color:#1d4ed8;"
        "border-bottom:2px solid #1d4ed8;}"
        "QPushButton:hover{color:#334155;}"
    ),

    # 매매일지 테이블
    jnl_tbl=(
        "QTableWidget{"
        "background:#ffffff;"
        "alternate-background-color:#f8fafc;"
        "gridline-color:#e8ecf0;"
        "border:none;"
        "font-size:12px;"
        "font-weight:500;"
        "color:#1e293b;}"
        "QHeaderView::section{"
        "background:#f1f5f9;"
        "color:#475569;"
        "border:none;"
        "border-bottom:1px solid #e2e8f0;"
        "font-size:10px;"
        "font-weight:700;"
        "letter-spacing:0.5px;"
        "padding:4px 8px;}"
        "QTableWidget::item:selected{"
        "background:#dbeafe;color:#1e40af;}"
    ),
)