#!/usr/bin/env bash
# 여러 편을 연속 생성. 사용: pipeline/batch.sh <plan.json>
# plan.json: [{"id":"2026-10-21-3d","topic":"...","preset":"3d-render","seconds":85}, ...]
# 한 편이 실패해도 다음 편으로 넘어간다. 로그: jobs/_batch/<id>.log, 요약: jobs/_batch/summary.md
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PLAN="$1"
LOGD="$ROOT/jobs/_batch"; mkdir -p "$LOGD"
N=$("$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))))" "$PLAN")
echo "== 배치 $N편  $(date '+%F %T')" | tee -a "$LOGD/batch.log"
for ((i=0; i<N; i++)); do
  read -r ID PRESET SECONDS_ < <("$PY" -c "import json,sys;p=json.load(open(sys.argv[1]))[int(sys.argv[2])];print(p['id'],p['preset'],p.get('seconds',85))" "$PLAN" "$i")
  TOPIC=$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[int(sys.argv[2])]['topic'])" "$PLAN" "$i")
  echo "-- [$((i+1))/$N] $ID  preset=$PRESET  $TOPIC  $(date '+%T')" | tee -a "$LOGD/batch.log"
  T0=$(date +%s)
  if PRESET="$PRESET" SCRIPT_ARGS="--seconds $SECONDS_" "$ROOT/pipeline/make.sh" "$TOPIC" "$ID" > "$LOGD/$ID.log" 2>&1; then
    DUR=$("$ROOT/tools/bin/ffprobe" -v error -show_entries format=duration -of csv=p=0 "$ROOT/jobs/$ID/render/final.mp4" 2>/dev/null || echo "?")
    echo "   완료 ${DUR}s  ($(( $(date +%s) - T0 ))s 걸림)" | tee -a "$LOGD/batch.log"
  else
    echo "   !! 실패 (로그: jobs/_batch/$ID.log)" | tee -a "$LOGD/batch.log"; tail -5 "$LOGD/$ID.log" | sed 's/^/      /' | tee -a "$LOGD/batch.log"
  fi
done
"$PY" "$ROOT/pipeline/batch_summary.py" "$PLAN" > "$LOGD/summary.md"
echo "== 배치 끝 $(date '+%F %T')  → jobs/_batch/summary.md" | tee -a "$LOGD/batch.log"
