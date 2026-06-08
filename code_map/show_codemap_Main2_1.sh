#!/bin/bash
# ============================================================
#  코드맵 출력기 — Main2_1
#  Claude에게 붙여넣기 할 내용을 한번에 출력
# ============================================================

MAP="/home/netforce/trading_terminal/Main2_1/code_map"

cat "$MAP/README_codemap.md"
echo ""
echo "=========================================="
cat "$MAP/dependency_map.txt"
echo ""
echo "=========================================="
cat "$MAP/symbol_map.txt"
