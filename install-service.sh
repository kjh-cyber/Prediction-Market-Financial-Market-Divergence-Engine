#!/bin/bash
set -e

SERVICE_FILE="divergence-engine.service"
SERVICE_NAME="divergence-engine"

echo "=== Divergence Engine 서비스 설치 ==="

# 서비스 파일 복사
sudo cp "$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload

# 서비스 활성화 (부팅 시 자동 시작)
sudo systemctl enable "$SERVICE_NAME"

# 서비스 시작
sudo systemctl start "$SERVICE_NAME"

echo ""
echo "설치 완료!"
echo ""
echo "  상태 확인:  sudo systemctl status $SERVICE_NAME"
echo "  로그 확인:  sudo journalctl -u $SERVICE_NAME -f"
echo "  중지:       sudo systemctl stop $SERVICE_NAME"
echo "  재시작:     sudo systemctl restart $SERVICE_NAME"
echo "  제거:       sudo systemctl disable $SERVICE_NAME && sudo rm /etc/systemd/system/$SERVICE_FILE"
