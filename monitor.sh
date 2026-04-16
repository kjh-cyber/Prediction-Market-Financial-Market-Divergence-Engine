#!/bin/bash
# Divergence Engine 실시간 모니터
# 엔진에 영향 없이 DB에서 읽기만 합니다

cd "$(dirname "$0")"
source .venv/bin/activate

INTERVAL=${1:-300}  # 기본 5분, 인자로 변경 가능

while true; do
    clear
    echo "══════════════════════════════════════════════════════════"
    echo "  Divergence Engine Monitor  |  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "══════════════════════════════════════════════════════════"
    echo ""
    divergence-engine top -n 20
    echo ""
    echo "  다음 새로고침: ${INTERVAL}초 후  |  Ctrl+C 종료"
    sleep "$INTERVAL"
done
