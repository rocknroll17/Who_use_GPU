#!/usr/bin/env python3
"""
GPU Discord Monitor
- 첫 실행 시 웹훅 URL을 대화형으로 입력받아 설정 저장
- 이후 실행부터는 저장된 설정으로 바로 시작
- 매 60초마다 같은 Discord 메시지를 PATCH로 업데이트
"""

import os
import sys
import json
import time
import signal
import subprocess
import socket
import pwd
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
import urllib.error

# ── 경로 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent.resolve()
CONFIG_FILE = SCRIPT_DIR / "gpu_monitor.conf"   # 설정 + msg_id 통합 저장

# ── 색상 (hex → int) ───────────────────────────────────────────────────────
COLOR_GREEN  = 0x2ECC71   # idle
COLOR_ORANGE = 0xE67E22   # some usage
COLOR_RED    = 0xE74C3C   # heavy

KST = timezone(timedelta(hours=9))

# ── Graceful shutdown ──────────────────────────────────────────────────────
running = True

def _handle_signal(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


# ══════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════

def load_config() -> dict | None:
    """key = value 형식 파싱. 없으면 None 반환."""
    if not CONFIG_FILE.exists():
        return None
    cfg: dict = {}
    with open(CONFIG_FILE) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                cfg[key.strip()] = val.strip()
    return cfg if cfg else None


def save_config(cfg: dict):
    """사람이 읽고 수정하기 쉬운 key = value 형식으로 저장."""
    lines = [
        "# GPU Monitor 설정 파일",
        "# 직접 수정 후 재시작하세요:",
        "#   systemd → sudo systemctl restart gpu-monitor",
        "#   docker  → docker compose restart",
        "",
        f"webhook_url = {cfg.get('webhook_url', '')}",
        f"update_interval = {cfg.get('update_interval', 60)}",
    ]
    with open(CONFIG_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(CONFIG_FILE, 0o600)


def _update_conf_key(key: str, value: str):
    """conf 파일의 특정 키를 in-place 업데이트 (없으면 마지막 줄에 추가)."""
    if not CONFIG_FILE.exists():
        return
    lines = CONFIG_FILE.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        k, _, _ = stripped.partition("=")
        if k.strip() == key:
            lines[i] = f"{key} = {value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key} = {value}")
    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    os.chmod(CONFIG_FILE, 0o600)


# ══════════════════════════════════════════════════════════════════════════
# nvidia-smi
# ══════════════════════════════════════════════════════════════════════════

def get_gpu_info() -> dict | None:
    """
    Returns:
        None   → nvidia-smi 없음
        {}     → GPU 없거나 파싱 실패
        {uuid: {...}} → 정상
    """
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,gpu_uuid,name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        gpus: dict = {}
        for line in r.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = [x.strip() for x in line.split(",")]
            if len(parts) < 6:
                continue
            idx, uuid, name, util, mem_used, mem_total = parts
            try:
                gpus[uuid] = {
                    "index":     int(idx),
                    "name":      name,
                    # nvidia-smi 일부 GPU/드라이버에서 float 또는
                    # '[Not Supported]' 반환 → 안전하게 변환
                    "util":      int(float(util)) if util.replace(".", "", 1).lstrip("-").isdigit() else 0,
                    "mem_used":  int(float(mem_used)) if mem_used.replace(".", "", 1).lstrip("-").isdigit() else 0,
                    "mem_total": int(float(mem_total)) if mem_total.replace(".", "", 1).lstrip("-").isdigit() else 1,
                }
            except (ValueError, TypeError):
                continue   # 파싱 실패한 GPU 행은 건너뜀
        return gpus
    except FileNotFoundError:
        return None
    except Exception:
        return {}


def get_processes() -> list[dict]:
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        procs = []
        for line in r.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = [x.strip() for x in line.split(",")]
            if len(parts) < 3:
                continue
            uuid, pid_str, mem_str = parts
            try:
                procs.append({"gpu_uuid": uuid, "pid": int(pid_str), "mem_used": int(mem_str)})
            except ValueError:
                continue
        return procs
    except Exception:
        return []


def get_username(pid: int) -> str:
    try:
        uid = os.stat(f"/proc/{pid}").st_uid
        return pwd.getpwuid(uid).pw_name
    except Exception:
        return "unknown"


# ══════════════════════════════════════════════════════════════════════════
# Embed 빌더
# ══════════════════════════════════════════════════════════════════════════

def build_embed() -> dict:
    server_name = socket.gethostname()
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    gpus = get_gpu_info()

    # nvidia-smi 자체가 없는 경우
    if gpus is None:
        return {
            "title": f"🖥️ GPU Monitor — {server_name}",
            "description": "⚠️ `nvidia-smi` 를 찾을 수 없습니다.\nNVIDIA 드라이버가 설치되어 있는지 확인하세요.",
            "color": COLOR_RED,
            "footer": {"text": f"Last updated: {now_kst}"},
        }

    # GPU가 한 장도 없는 경우
    if not gpus:
        return {
            "title": f"🖥️ GPU Monitor — {server_name}",
            "description": "ℹ️ 감지된 GPU가 없습니다.",
            "color": COLOR_GREEN,
            "footer": {"text": f"Last updated: {now_kst}"},
        }

    procs = get_processes()

    # gpu_uuid → 프로세스 목록
    proc_map: dict[str, list] = {}
    for p in procs:
        proc_map.setdefault(p["gpu_uuid"], []).append(p)

    fields = []
    max_util = 0
    multi_gpu = len(gpus) > 1

    for uuid, gpu in sorted(gpus.items(), key=lambda x: x[1]["index"]):
        if multi_gpu and fields:
            fields.append({"name": "\u200b", "value": "\u200b", "inline": False})

        util      = gpu["util"]
        mem_used  = gpu["mem_used"]
        mem_total = gpu["mem_total"]
        max_util  = max(max_util, util)

        gpu_procs = proc_map.get(uuid, [])
        if gpu_procs:
            lines = []
            for p in gpu_procs:
                user = get_username(p["pid"])
                lines.append(f"• `{user}` (PID {p['pid']}) — {p['mem_used']} MiB")
            proc_text = "\n".join(lines)
        else:
            proc_text = "—"

        mem_width = len(str(mem_total))
        parts = [f"Util: `{util:3d}%` | Mem: `{mem_used:{mem_width}d}` / `{mem_total}` MiB"]
        parts.append("**Processes**")
        parts.append(proc_text)
        value = "\n".join(parts)
        fields.append({
            "name":   f"GPU {gpu['index']} — {gpu['name']}" if multi_gpu else gpu["name"],
            "value":  value,
            "inline": False,
        })

    if max_util >= 70:
        color = COLOR_RED
    elif max_util >= 10:
        color = COLOR_ORANGE
    else:
        color = COLOR_GREEN

    return {
        "title":  f"🖥️ GPU Monitor — {server_name}",
        "color":  color,
        "fields": fields,
        "footer": {"text": f"Last updated: {now_kst}"},
    }


# ══════════════════════════════════════════════════════════════════════════
# Discord API
# ══════════════════════════════════════════════════════════════════════════

def _discord_request(method: str, url: str, payload: dict | None = None) -> tuple[int, dict | None]:
    data = json.dumps(payload).encode() if payload else None
    headers = {
        "User-Agent": "DiscordBot (gpu-monitor, 1.0)",
    }
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None


def send_or_update(cfg: dict, embed: dict):
    webhook_url = cfg["webhook_url"]
    payload     = {"embeds": [embed]}
    msg_id      = cfg.get("msg_id", "").strip() or None

    if msg_id:
        status, _ = _discord_request("PATCH", f"{webhook_url}/messages/{msg_id}", payload)
        if status == 200:
            return
        # 404: 메시지가 수동 삭제됨 → 새로 POST
        print(f"[discord] PATCH failed ({status}), creating new message...")
        cfg["msg_id"] = ""
        _update_conf_key("msg_id", "")
        msg_id = None

    # POST 새 메시지
    status, resp = _discord_request("POST", f"{webhook_url}?wait=true", payload)
    if status == 200 and resp:
        new_id = resp["id"]
        cfg["msg_id"] = new_id
        _update_conf_key("msg_id", new_id)
        print(f"[discord] New message created: {new_id}")
    else:
        print(f"[discord] POST failed: {status} {resp}", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════

def main():
    cfg = load_config()
    if cfg is None:
        print(
            "[error] gpu_monitor.conf 없음. install.sh (또는 install_docker.sh) 를 먼저 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not cfg.get("webhook_url"):
        print("[error] gpu_monitor.conf 에 webhook_url 이 없습니다.", file=sys.stderr)
        sys.exit(1)

    interval = int(cfg.get("update_interval", 60))
    print(f"[*] GPU Monitor started  (host: {socket.gethostname()})")
    print(f"[*] Update interval: {interval}s | Ctrl+C or SIGTERM to stop")
    print()

    while running:
        try:
            embed = build_embed()
            send_or_update(cfg, embed)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)

        # interval을 1초 단위로 나눠서 SIGTERM에 즉시 반응
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    print("[*] GPU Monitor stopped.")


if __name__ == "__main__":
    main()
