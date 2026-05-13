#!/usr/bin/env bash
# install_docker.sh — GPU Monitor Docker 설치 스크립트
# 사전 조건 검증 → 이미지 빌드 → GPU 접근 테스트 → 컨테이너 시작
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  GPU Monitor — Docker 설치"
echo "========================================"
echo ""

# ── Docker 명령어 자동 감지 ──────────────────────────────────────────────
# sudo 필요 여부 감지
if docker info &>/dev/null 2>&1; then
    DOCKER_BIN="docker"
elif sudo -n docker info &>/dev/null 2>&1; then
    DOCKER_BIN="sudo docker"
else
    echo "[!] Docker에 접근할 수 없습니다."
    echo "    sudo로 실행하거나 docker 그룹에 추가 후 다시 시도하세요:"
    echo "      sudo bash $(basename "$0")"
    echo "      sudo usermod -aG docker \$USER && newgrp docker"
    exit 1
fi

# docker compose v2 vs docker-compose v1
if $DOCKER_BIN compose version &>/dev/null 2>&1; then
    COMPOSE="$DOCKER_BIN compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
    [[ "$DOCKER_BIN" == "sudo docker" ]] && COMPOSE="sudo docker-compose"
else
    echo "[!] docker compose v2 또는 docker-compose가 없습니다."
    echo "    설치: https://docs.docker.com/compose/install/"
    exit 1
fi

# ── 1. 사전 조건 검증 ────────────────────────────────────────────────────
echo "[1/5] 사전 조건 확인 중..."
FAIL=0

echo "  [✓] Docker $($DOCKER_BIN --version | awk '{print $3}' | tr -d ',')"
echo "  [✓] $($COMPOSE version)"

# NVIDIA container runtime (toolkit 설치 + Docker에 연결됐는지)
HAS_RUNTIME=0
command -v nvidia-container-runtime &>/dev/null              && HAS_RUNTIME=1
$DOCKER_BIN info 2>/dev/null | grep -qi "nvidia"             && HAS_RUNTIME=1
[ -f /etc/docker/daemon.json ] && \
    grep -qi "nvidia" /etc/docker/daemon.json                && HAS_RUNTIME=1

if [ "$HAS_RUNTIME" -eq 1 ]; then
    echo "  [✓] NVIDIA container runtime 감지됨"
else
    echo "  [✗] nvidia-container-toolkit이 설치되지 않았거나 Docker에 등록되지 않았습니다."
    echo "       설치:"
    echo "         sudo apt install nvidia-container-toolkit"
    echo "         sudo nvidia-ctk runtime configure --runtime=docker"
    echo "         sudo systemctl restart docker"
    FAIL=1
fi

# nvidia-smi (호스트에 드라이버 있는지)
if command -v nvidia-smi &>/dev/null; then
    echo "  [✓] nvidia-smi 감지됨"
else
    echo "  [✗] nvidia-smi가 없습니다. NVIDIA 드라이버를 설치하세요."
    FAIL=1
fi

if [ "$FAIL" -eq 1 ]; then
    echo ""
    echo "[!] 위 항목을 해결한 후 다시 실행하세요."
    exit 1
fi

echo ""

# ── 2. 설정 파일 초기화 ──────────────────────────────────────────────────
echo "[2/5] 설정 파일 확인 중..."
CONFIG_FILE="$SCRIPT_DIR/gpu_monitor.conf"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo ""
    echo "  Discord 웹훅 URL을 입력하세요."
    echo "  (채널 설정 → 연동 → 웹훅 → URL 복사)"
    echo ""

    while true; do
        read -rp "  Webhook URL: " WEBHOOK_URL
        if [[ "$WEBHOOK_URL" =~ ^https://discord(app)?\.com/api/webhooks/ ]]; then
            break
        fi
        echo "  [!] 올바른 Discord 웹훅 URL 형식이 아닙니다. 다시 입력해주세요."
    done

    echo "  [*] 웹훅 연결 테스트 중..."
    export WEBHOOK_URL
    python3 - << 'PYEOF' || { echo "  [!] URL을 확인하고 다시 시도하세요."; exit 1; }
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
    print("  [✓] 연결 성공!")
except Exception as e:
    print(f"  [!] 연결 실패: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

    read -rp "  업데이트 주기(초, 기본 60): " INTERVAL
    INTERVAL="${INTERVAL:-60}"

    cat > "$CONFIG_FILE" << EOF
# GPU Monitor 설정 파일
# 직접 수정 후: docker compose restart

webhook_url = $WEBHOOK_URL
update_interval = $INTERVAL
EOF
    chmod 600 "$CONFIG_FILE"
    echo "  [✓] 설정 파일 생성됨 → $CONFIG_FILE"
fi
echo ""

# ── 3. 이미지 빌드 ──────────────────────────────────────────────────────
echo "[3/5] Docker 이미지 빌드 중..."
$COMPOSE build
echo ""

# ── 4. GPU 접근 테스트 (빌드된 이미지로) ────────────────────────────────
echo "[4/5] Docker 컨테이너에서 GPU 접근 테스트 중..."
IMAGE_NAME=$($DOCKER_BIN images --format "{{.Repository}}" | grep "gpu-monitor$" | head -1)
if $DOCKER_BIN run --rm --gpus all \
       -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
       "$IMAGE_NAME" nvidia-smi -L 2>/dev/null; then
    echo "  [✓] GPU 접근 확인됨"
else
    echo "  [✗] Docker 컨테이너에서 GPU를 볼 수 없습니다."
    echo "       'sudo systemctl restart docker' 후 재시도하세요."
    exit 1
fi
echo ""

# ── 5. 컨테이너 시작 ─────────────────────────────────────────────────────
echo "[5/5] 컨테이너 시작 중..."
$COMPOSE up -d

echo ""
echo "========================================"
echo "  설치 완료!"
echo "========================================"
echo ""
echo "상태 확인  : docker compose ps"
echo "실시간 로그: docker compose logs -f"
echo "설정 수정  : nano gpu_monitor.conf"
echo "             (수정 후 → docker compose restart)"
echo "중지       : docker compose down"
echo ""
