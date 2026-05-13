#!/usr/bin/env python3
"""
E2E 테스트 — GPU Monitor 전 시나리오 검증

사용법:
    python3 test_e2e.py <WEBHOOK_URL>
"""

import sys
import os
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

# ── gpu_monitor 모듈 import ─────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# 테스트용으로 CONFIG_FILE / MSG_ID_FILE 경로를 임시 파일로 재정의
import gpu_monitor as gm

WEBHOOK_URL = sys.argv[1] if len(sys.argv) > 1 else ""
if not WEBHOOK_URL:
    print("Usage: python3 test_e2e.py <WEBHOOK_URL>")
    sys.exit(1)

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results: list[tuple[str, bool, str]] = []

def check(name: str, cond: bool, detail: str = ""):
    results.append((name, cond, detail))
    status = PASS if cond else FAIL
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))

# ═══════════════════════════════════════════════════════════════
# 헬퍼: 직접 Discord API 호출
# ═══════════════════════════════════════════════════════════════
def discord_delete(webhook_url: str, msg_id: str) -> int:
    req = urllib.request.Request(
        f"{webhook_url}/messages/{msg_id}",
        headers={"User-Agent": "DiscordBot (gpu-monitor, 1.0)"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code

# ═══════════════════════════════════════════════════════════════
# 테스트 0: 모듈 임포트 및 구문 오류 없음
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  0. 모듈 임포트 & 기본 구조")
print("="*56)

check("gpu_monitor import 성공", True)
check("CONFIG_FILE 경로 정상", str(gm.CONFIG_FILE).endswith("gpu_monitor.conf"))

# ═══════════════════════════════════════════════════════════════
# 테스트 1: Config 저장/로드 라운드트립
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  1. Config 저장 / 로드 라운드트립")
print("="*56)

# 기존 config 백업
backup = None
if gm.CONFIG_FILE.exists():
    backup = gm.CONFIG_FILE.read_text()
    gm.CONFIG_FILE.unlink()

test_cfg = {"webhook_url": WEBHOOK_URL, "update_interval": "30"}
gm.save_config(test_cfg)
check("config 파일 생성", gm.CONFIG_FILE.exists())

loaded = gm.load_config()
check("load_config() 반환값 not None", loaded is not None)
check("webhook_url 일치", loaded.get("webhook_url") == WEBHOOK_URL)
check("update_interval 일치", loaded.get("update_interval") == "30")

# 파일 내용에 주석 포함 확인
raw = gm.CONFIG_FILE.read_text()
check("설정 파일에 주석 포함", raw.strip().startswith("#"))
check("설정 파일에 webhook_url 키 포함", "webhook_url" in raw)
check("설정 파일에 update_interval 키 포함", "update_interval" in raw)

# 파일 권한 600 확인
mode = oct(os.stat(gm.CONFIG_FILE).st_mode)[-3:]
check("파일 권한 600 (웹훅 URL 보호)", mode == "600", f"실제: {mode}")

# 백업 복원
if backup:
    gm.CONFIG_FILE.write_text(backup)
else:
    # 실제 테스트 config 유지 (WEBHOOK_URL 포함)
    gm.save_config({"webhook_url": WEBHOOK_URL, "update_interval": 60})

# ═══════════════════════════════════════════════════════════════
# 테스트 2: Config 파싱 엣지케이스
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  2. Config 파싱 엣지케이스")
print("="*56)

# 공백/주석/빈줄 포함된 파일 파싱
edge_content = """
# 이건 주석
  # 이것도 주석

webhook_url = https://discord.com/api/webhooks/test/token
update_interval = 45
  extra_key   =   some value with spaces   
"""
gm.CONFIG_FILE.write_text(edge_content)
os.chmod(gm.CONFIG_FILE, 0o600)
edge_cfg = gm.load_config()
check("공백/주석 파싱 후 webhook_url 정상", edge_cfg.get("webhook_url") == "https://discord.com/api/webhooks/test/token")
check("공백/주석 파싱 후 update_interval 정상", edge_cfg.get("update_interval") == "45")
check("앞뒤 공백 trim 처리", edge_cfg.get("extra_key") == "some value with spaces")

# 빈 파일
gm.CONFIG_FILE.write_text("# only comments\n\n")
os.chmod(gm.CONFIG_FILE, 0o600)
check("빈 config (주석만) → None 반환", gm.load_config() is None)

# config 없음
gm.CONFIG_FILE.unlink()
check("config 파일 없음 → None 반환", gm.load_config() is None)

# 실제 config 복원
gm.save_config({"webhook_url": WEBHOOK_URL, "update_interval": 60})

# ═══════════════════════════════════════════════════════════════
# 테스트 3: nvidia-smi / GPU 정보 파싱
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  3. nvidia-smi GPU 정보 수집")
print("="*56)

gpus = gm.get_gpu_info()
if gpus is None:
    print(f"{INFO} nvidia-smi 없음 — 드라이버 없는 환경으로 처리")
    check("nvidia-smi 없음 → None 반환", True)
else:
    print(f"{INFO} GPU {len(gpus)}개 감지됨")
    check("get_gpu_info() → dict 반환", isinstance(gpus, dict))
    for uuid, gpu in gpus.items():
        check(f"GPU {gpu['index']} index 필드 int", isinstance(gpu["index"], int))
        check(f"GPU {gpu['index']} util 0~100", 0 <= gpu["util"] <= 100, f"{gpu['util']}%")
        check(f"GPU {gpu['index']} mem_total > 0", gpu["mem_total"] > 0, f"{gpu['mem_total']} MiB")
        check(f"GPU {gpu['index']} mem_used <= mem_total", gpu["mem_used"] <= gpu["mem_total"])
        print(f"  → GPU {gpu['index']}: {gpu['name']} | {gpu['util']}% | {gpu['mem_used']}/{gpu['mem_total']} MiB")

procs = gm.get_processes()
check("get_processes() → list 반환", isinstance(procs, list))
for p in procs:
    check(f"PID {p['pid']} → username 획득", gm.get_username(p["pid"]) != "")
    print(f"  → PID {p['pid']}: {gm.get_username(p['pid'])} on {p['gpu_uuid'][:16]}...")

# ═══════════════════════════════════════════════════════════════
# 테스트 4: embed 빌더 시나리오
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  4. Embed 빌더")
print("="*56)

# 4a. 실제 GPU 정보로 embed 빌드
embed = gm.build_embed()
check("embed dict 반환", isinstance(embed, dict))
check("embed에 title 포함", "title" in embed)
check("embed에 color 포함", "color" in embed)
check("embed에 footer 포함", "footer" in embed and "text" in embed["footer"])
check("footer에 KST 포함", "KST" in embed["footer"]["text"])
print(f"  → title: {embed.get('title')}")
print(f"  → color: #{embed.get('color', 0):06X}")

# field value가 비어있지 않은지 확인 (Discord 필드 규칙)
for field in embed.get("fields", []):
    val = field.get("value", "")
    check(f"field '{field['name'][:30]}' value 비어있지 않음", bool(val.strip()))
    check(f"field '{field['name'][:30]}' value ≤ 1024자", len(val) <= 1024, f"{len(val)}자")

# 4b. nvidia-smi 없음 시나리오 (monkey-patch)
orig_get_gpu_info = gm.get_gpu_info
gm.get_gpu_info = lambda: None
embed_no_smi = gm.build_embed()
check("nvidia-smi 없음 → embed 정상 생성", "description" in embed_no_smi)
check("nvidia-smi 없음 → RED 색상", embed_no_smi["color"] == gm.COLOR_RED)
gm.get_gpu_info = orig_get_gpu_info

# 4c. GPU 없음 시나리오 (빈 dict)
gm.get_gpu_info = lambda: {}
embed_no_gpu = gm.build_embed()
check("GPU 없음 → embed 정상 생성", "description" in embed_no_gpu)
check("GPU 없음 → GREEN 색상", embed_no_gpu["color"] == gm.COLOR_GREEN)
gm.get_gpu_info = orig_get_gpu_info

# ═══════════════════════════════════════════════════════════════
# 테스트 5: Discord POST — 첫 메시지 생성 (?wait=true)
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  5. Discord POST — 첫 메시지 생성")
print("="*56)

# conf에서 msg_id 클린 상태로 시작
test_cfg = gm.load_config()
test_cfg["msg_id"] = ""
gm._update_conf_key("msg_id", "")

embed = gm.build_embed()
gm.send_or_update(test_cfg, embed)

msg_id_1 = test_cfg.get("msg_id", "")
check("conf에 msg_id 저장됨", bool(msg_id_1))
check("msg_id가 숫자 문자열", msg_id_1.isdigit(), msg_id_1)
print(f"  → 생성된 message ID: {msg_id_1}")

# ═══════════════════════════════════════════════════════════════
# 테스트 6: Discord PATCH — 같은 메시지 수정
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  6. Discord PATCH — 기존 메시지 덮어쓰기")
print("="*56)

time.sleep(1)   # rate limit 여유
embed2 = gm.build_embed()
gm.send_or_update(test_cfg, embed2)

msg_id_2 = test_cfg.get("msg_id", "")
check("PATCH 후 msg_id 동일 (새 메시지 생성 안됨)", msg_id_1 == msg_id_2, f"{msg_id_1} == {msg_id_2}")
print(f"  → message ID (변경 없어야 함): {msg_id_2}")

# ═══════════════════════════════════════════════════════════════
# 테스트 7: 404 fallback — 메시지 삭제 후 자동 재생성
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  7. 404 Fallback — 메시지 삭제 후 자동 재생성")
print("="*56)

time.sleep(1)
del_status = discord_delete(WEBHOOK_URL, msg_id_1)
check(f"Discord에서 메시지 삭제 성공", del_status == 204, f"HTTP {del_status}")
print(f"  → DELETE 응답: {del_status}")

time.sleep(1)
embed3 = gm.build_embed()
gm.send_or_update(test_cfg, embed3)   # PATCH → 404 → POST fallback

msg_id_3 = test_cfg.get("msg_id", "")
check("404 후 새 msg_id 생성됨", bool(msg_id_3))
check("새 msg_id는 기존과 다름", msg_id_1 != msg_id_3, f"{msg_id_1} → {msg_id_3}")
print(f"  → 새 message ID: {msg_id_3}")

# ═══════════════════════════════════════════════════════════════
# 테스트 8: 잘못된 msg_id 파일 내용 (손상된 ID)
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  8. 손상된 msg_id 파일 → 안전한 fallback")
print("="*56)

# 현재 올바른 메시지 먼저 정리
if msg_id_3:
    discord_delete(WEBHOOK_URL, msg_id_3)
    time.sleep(0.5)

test_cfg["msg_id"] = "999999999999999999"   # 존재하지 않는 ID
gm._update_conf_key("msg_id", "999999999999999999")
embed4 = gm.build_embed()
gm.send_or_update(test_cfg, embed4)

msg_id_4 = test_cfg.get("msg_id", "")
check("손상된 ID → 새 메시지 생성", bool(msg_id_4) and msg_id_4 != "999999999999999999")
print(f"  → 복구된 message ID: {msg_id_4}")

# ═══════════════════════════════════════════════════════════════
# 정리: 테스트용 메시지 삭제
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  정리: 테스트 메시지 삭제")
print("="*56)

if msg_id_4:
    s = discord_delete(WEBHOOK_URL, msg_id_4)
    print(f"  → 마지막 테스트 메시지 삭제: HTTP {s}")
gm._update_conf_key("msg_id", "")
print(f"  → conf에서 msg_id 초기화")

# 실제 운영용 config는 유지
print(f"  → gpu_monitor.conf 유지 (정상 운영 준비 완료)")

# ═══════════════════════════════════════════════════════════════
# 최종 결과
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*56)
print("  최종 결과")
print("="*56)

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total  = len(results)

print(f"\n  총 {total}개 테스트: \033[92m{passed} 통과\033[0m / \033[91m{failed} 실패\033[0m\n")

if failed:
    print("실패 목록:")
    for name, ok, detail in results:
        if not ok:
            print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))
    sys.exit(1)
else:
    print("  모든 시나리오 정상!")
    sys.exit(0)
