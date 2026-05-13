#!/usr/bin/env bash
# uninstall_docker.sh — GPU Monitor Docker 제거 스크립트
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  GPU Monitor — Docker 제거"
echo "========================================"
echo ""

# ── Docker 명령어 자동 감지 ──────────────────────────────────────────────
if docker info &>/dev/null 2>&1; then
    DOCKER_BIN="docker"
elif sudo -n docker info &>/dev/null 2>&1; then
    DOCKER_BIN="sudo docker"
else
    echo "[!] Docker에 접근할 수 없습니다."
    echo "    sudo로 실행하거나 docker 그룹에 추가 후 다시 시도하세요:"
    echo "      sudo bash $(basename "$0")"
    exit 1
fi

if $DOCKER_BIN compose version &>/dev/null 2>&1; then
    COMPOSE="$DOCKER_BIN compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
    [[ "$DOCKER_BIN" == "sudo docker" ]] && COMPOSE="sudo docker-compose"
else
    COMPOSE="$DOCKER_BIN compose"  # best effort
fi

# ── 1. 컨테이너 중지 및 제거 ────────────────────────────────────────────
echo "[1/3] 컨테이너 중지 중..."
if $COMPOSE ps -q 2>/dev/null | grep -q .; then
    $COMPOSE down
    echo "  [✓] 컨테이너 중지 및 제거 완료"
else
    $COMPOSE down 2>/dev/null || true
    echo "  [✓] 실행 중인 컨테이너 없음"
fi
echo ""

# ── 2. 이미지 제거 ──────────────────────────────────────────────────────
echo "[2/3] Docker 이미지 제거 중..."
IMAGE_NAME=$($DOCKER_BIN images --format "{{.Repository}}" | grep "gpu-monitor$" | head -1)
if [[ -n "$IMAGE_NAME" ]]; then
    $DOCKER_BIN rmi "$IMAGE_NAME"
    echo "  [✓] 이미지 '$IMAGE_NAME' 제거 완료"
else
    echo "  [✓] 제거할 이미지 없음"
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
