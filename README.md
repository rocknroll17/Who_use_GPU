# Who_use_GPU

GPU 서버에서 누가 GPU를 쓰고 있는지 Discord 채널에 알려주는 모니터.  

---

## 요구사항

공통:
- NVIDIA 드라이버 + `nvidia-smi`
- Discord Webhook URL

A. systemd 방식 추가:
- Python 3.10+

B. Docker 방식 추가:
- Docker 20.10+
- nvidia-container-toolkit

---

## 설치

```bash
git clone https://github.com/rocknroll1397/Who_use_GPU.git
cd Who_use_GPU
```

### A. systemd

```bash
sudo bash install.sh
```

### B. Docker

```bash
bash install_docker.sh
```

docker 그룹에 속하지 않은 경우 `sudo bash install_docker.sh`로 실행.  
스크립트가 권한 및 compose 버전을 자동 감지함.

---

## 설정 변경

설정은 `gpu_monitor.conf` 파일 하나에서 관리.

```
webhook_url     = https://discord.com/api/webhooks/...
update_interval = 60
```

수정 후 재시작:

```bash
# systemd
sudo systemctl restart gpu-monitor

# Docker
docker compose restart
```

---

## 명령어

### systemd

```bash
sudo systemctl status gpu-monitor      # 상태
sudo journalctl -u gpu-monitor -f      # 실시간 로그
sudo systemctl restart gpu-monitor     # 재시작
sudo systemctl stop gpu-monitor        # 중지
sudo bash uninstall.sh                 # 완전 제거
```

### Docker

```bash
docker compose ps                      # 상태
docker compose logs -f                 # 실시간 로그
docker compose restart                 # 재시작
docker compose down                    # 중지 및 제거
bash uninstall_docker.sh               # 완전 제거 (이미지 포함)
```

sudo로 설치한 경우 앞에 `sudo` 붙여서 실행.

---

## 라이선스
MIT License
