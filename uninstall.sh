#!/usr/bin/env bash
# uninstall.sh — GPU Monitor systemd 제거 스크립트
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "  GPU Monitor — systemd 제거"
echo "========================================"
echo ""

# root 확인
if [[ "$EUID" -ne 0 ]]; then
    echo "[!] root 권한이 필요합니다: sudo bash uninstall.sh"
    exit 1
fi

# ── 1. 서비스 중지 및 비활성화 ─────────────────────────────────────────
echo "[1/3] systemd 서비스 중지 중..."
if systemctl is-active --quiet gpu-monitor 2>/dev/null || \
   systemctl is-enabled --quiet gpu-monitor 2>/dev/null; then
    systemctl disable --now gpu-monitor
    echo "  [✓] 서비스 중지 및 비활성화 완료"
else
    echo "  [✓] 실행 중인 서비스 없음"
fi
echo ""

# ── 2. 서비스 파일 제거 ─────────────────────────────────────────────────
echo "[2/3] 서비스 파일 제거 중..."
if [[ -f /etc/systemd/system/gpu-monitor.service ]]; then
    rm -f /etc/systemd/system/gpu-monitor.service
    systemctl daemon-reload
    echo "  [✓] /etc/systemd/system/gpu-monitor.service 제거 완료"
else
    echo "  [✓] 서비스 파일 없음"
fi
echo ""

# ── 3. 설정 파일 제거 ───────────────────────────────────────────────────
echo "[3/3] 설정 파일 제거 중..."
if [[ -f "$SCRIPT_DIR/gpu_monitor.conf" ]]; then
    rm -f "$SCRIPT_DIR/gpu_monitor.conf"
    echo "  [✓] gpu_monitor.conf 제거 완료"
else
    echo "  [✓] 설정 파일 없음"
fi
echo ""

echo "========================================"
echo "  제거 완료!"
echo "========================================"
echo ""
