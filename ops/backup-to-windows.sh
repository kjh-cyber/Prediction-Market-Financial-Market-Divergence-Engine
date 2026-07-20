#!/bin/bash
# Divergence Engine — 크기 임계값 기반 Windows 백업 (백업 복사 방식)
#
# 동작:
#   - 라이브 DB 는 ext4 에 그대로 두고(성능·락 안정성), 크기가 마일스톤을 넘을 때마다
#     온라인 .backup(무중단 안전 복사) → gzip → Windows(/mnt/c) 로 복사.
#   - 최근 KEEP 개만 보관(로테이션). 데이터 손실 없음.
#   - systemd timer 가 주기적으로 이 스크립트를 호출하고, 실제 백업 여부는 크기로 판단.
#
# 크기 임계값:
#   - DB < START_MB            → 아무것도 안 함
#   - DB >= 직전백업크기+STEP_MB → 새 백업 수행(첫 실행은 START_MB 넘으면 즉시)
set -euo pipefail

# ---- 설정 (환경변수로 덮어쓰기 가능) ----
PROJ="/home/user/Prediction-Market-Financial-Market-Divergence-Engine"
DB="${DIV_DB:-$PROJ/data/divergence.db}"
DEST="${DIV_BACKUP_DEST:-/mnt/c/Users/user/DivergenceEngineBackups}"
PY="${DIV_PY:-$PROJ/.venv/bin/python}"
START_MB="${DIV_BACKUP_START_MB:-300}"   # 이 크기 넘어야 백업 시작
STEP_MB="${DIV_BACKUP_STEP_MB:-250}"     # 직전 백업 대비 이만큼 커지면 재백업
KEEP="${DIV_BACKUP_KEEP:-10}"            # 보관 개수
STATE="$PROJ/ops/.last_backup_size_mb"
LOG="$PROJ/ops/backup.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

[ -f "$DB" ] || { log "ERROR: DB 없음: $DB"; exit 1; }

size_mb=$(( $(stat -c '%s' "$DB") / 1024 / 1024 ))
last_mb=0; [ -f "$STATE" ] && last_mb=$(cat "$STATE" 2>/dev/null || echo 0)

# 백업 필요 여부 판단 (크기 임계값)
if [ "$size_mb" -lt "$START_MB" ]; then
    log "skip: DB ${size_mb}MB < START ${START_MB}MB"; exit 0
fi
if [ "$size_mb" -lt "$(( last_mb + STEP_MB ))" ]; then
    log "skip: DB ${size_mb}MB < 직전백업 ${last_mb}MB + STEP ${STEP_MB}MB"; exit 0
fi

# Windows 대상 접근성 확인 (WSL 마운트 해제/이동 대비)
if ! mkdir -p "$DEST" 2>/dev/null; then
    log "ERROR: Windows 대상 접근 불가(마운트 확인): $DEST"; exit 1
fi

ts=$(date '+%Y%m%d-%H%M%S')
tmp="$PROJ/data/.backup-$ts.db"
out="$DEST/divergence-$ts.db.gz"

log "백업 시작: DB ${size_mb}MB -> $out"

# 1) 온라인 안전 복사 (라이브 writer 중에도 무결성 보장)
"$PY" - "$DB" "$tmp" <<'PYEOF'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(src); d = sqlite3.connect(dst)
with d:
    s.backup(d)
d.close(); s.close()
PYEOF

# 2) 압축하여 Windows 로 (drvfs 는 write-once 라 락 문제 없음)
gzip -c "$tmp" > "$out"
rm -f "$tmp"

gz_mb=$(( $(stat -c '%s' "$out") / 1024 / 1024 ))
log "완료: $out (${gz_mb}MB 압축)"

echo "$size_mb" > "$STATE"

# 3) 로테이션 — 최근 KEEP 개만 유지
mapfile -t old < <(ls -1t "$DEST"/divergence-*.db.gz 2>/dev/null | tail -n +"$(( KEEP + 1 ))")
for f in "${old[@]:-}"; do [ -n "$f" ] && rm -f "$f" && log "로테이션 삭제: $f"; done

log "현재 보관본: $(ls -1 "$DEST"/divergence-*.db.gz 2>/dev/null | wc -l)개"
