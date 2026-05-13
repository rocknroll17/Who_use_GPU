#!/usr/bin/env bash
# install.sh — GPU Monitor 원클릭 설치 스크립트
set -euo pipefail

SERVICE_NAME="gpu-monitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="$(logname 2>/dev/null || echo "$SUDO_USER")"

# root로 실행됐는지 확인
if [[ "$EUID" -ne 0 ]]; then
    echo "[!] 이 스크립트는 sudo로 실행해야 합니다."
    echo "    sudo bash install.sh"
    exit 1
fi

echo "========================================"
echo "  GPU Monitor 설치"
echo "========================================"
echo "  스크립트 위치: $SCRIPT_DIR"
echo "  실행 유저    : $CURRENT_USER"
echo "========================================"
echo ""

# ── 1. 설정 파일 초기화 ──────────────────────────────────────────────────
CONFIG_FILE="$SCRIPT_DIR/gpu_monitor.conf"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "[*] 설정을 진행합니다."
    echo ""
    echo "Discord 웹훅 URL을 입력하세요."
    echo "(채널 설정 → 연동 → 웹훅 → URL 복사)"
    echo ""

    while true; do
        read -rp "Webhook URL: " WEBHOOK_URL
        if [[ "$WEBHOOK_URL" =~ ^https://discord(app)?\.com/api/webhooks/ ]]; then
            break
        fi
        echo "[!] 올바른 Discord 웹훅 URL 형식이 아닙니다. 다시 입력해주세요."
    done

    echo "[*] 웹훅 연결 테스트 중..."
    export WEBHOOK_URL
    python3 - << 'PYEOF' || { echo "[!] URL을 확인하고 다시 시도하세요."; exit 1; }
import json, urllib.request, sys, os
url = os.environ["WEBHOOK_URL"]
data = json.dumps({"content": "\U0001f527 GPU Monitor 연결 테스트 중..."}).encode()
req = urllib.request.Request(url + "?wait=true", data=data,
    headers={"Content-Type": "application/json", "User-Agent": "DiscordBot (gpu-monitor, 1.0)"},
    method="POST")
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        msg = json.loads(r.read())
    del_req = urllib.request.Request(url + "/messages/" + msg["id"],
        headers={"User-Agent": "DiscordBot (gpu-monitor, 1.0)"}, method="DELETE")
    try: urllib.request.urlopen(del_req, timeout=10)
    except: pass
    print("[✓] 연결 성공!")
except Exception as e:
    print(f"[!] 연결 실패: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

    read -rp "업데이트 주기(초, 기본 60): " INTERVAL
    INTERVAL="${INTERVAL:-60}"

    cat > "$CONFIG_FILE" << EOF
# GPU Monitor 설정 파일
# 직접 수정 후 서비스를 재시작하세요: sudo systemctl restart gpu-monitor

webhook_url = $WEBHOOK_URL
update_interval = $INTERVAL
EOF
    chmod 600 "$CONFIG_FILE"
    chown "$CURRENT_USER:" "$CONFIG_FILE"
    echo "[✓] 설정 파일 생성됨 → $CONFIG_FILE"
    echo ""
fi

# ── 2. systemd 서비스 파일 생성 ──────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "[*] systemd 서비스 파일 생성 중..."
sed \
    -e "s|__USER__|$CURRENT_USER|g" \
    -e "s|__WORKDIR__|$SCRIPT_DIR|g" \
    "$SCRIPT_DIR/gpu-monitor.service" \
    > "$SERVICE_FILE"

echo "    → $SERVICE_FILE"
echo ""

# ── 3. 서비스 등록 및 시작 ───────────────────────────────────────────────
echo "[*] systemd 데몬 리로드 및 서비스 등록..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "========================================"
echo "  설치 완료!"
echo "========================================"
echo ""
echo "  상태 확인  : sudo systemctl status $SERVICE_NAME"
echo "  실시간 로그: sudo journalctl -u $SERVICE_NAME -f"
echo "  설정 수정  : nano $CONFIG_FILE"
echo "             (수정 후 → sudo systemctl restart $SERVICE_NAME)"
echo "  서비스 중지: sudo systemctl stop $SERVICE_NAME"
echo "  서비스 제거: sudo systemctl disable $SERVICE_NAME"
echo ""
