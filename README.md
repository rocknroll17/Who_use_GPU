# Who_use_GPU

GPU 서버에서 누가 GPU를 쓰고 있는지 Discord 채널에 알려주는 모니터.  

---

## 요구사항

- NVIDIA 드라이버 + `nvidia-smi`
- Python 3.10+
- Discord Webhook URL

---

## 설치

### Common

```Bash
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

Docker, nvidia-container-toolkit 등 패키지 설치 필요.

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

# 완전 제거
sudo systemctl disable --now gpu-monitor
sudo rm /etc/systemd/system/gpu-monitor.service
```

### Docker

```bash
docker compose ps                      # 상태
docker compose logs -f                 # 실시간 로그
docker compose restart                 # 재시작
docker compose down                    # 중지 및 제거
```

---

## 라이선스
MIT License
