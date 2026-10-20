#!/usr/bin/env bash
# 주제 한 줄 → 영상 한 편. 사용: pipeline/make.sh "<주제>" [job-id]
# 공정: 02 대본 → 03 음성 → 음성 검수 → 04 소스(이미지) → 04 렌더
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/tools/bin:$PATH"
TOPIC="$1"
ID="${2:-$(date +%Y-%m-%d)-$(printf '%03d' $(( $(ls -d "$ROOT"/jobs/$(date +%Y-%m-%d)-* 2>/dev/null | wc -l) + 1 )))}"
JOB="$ROOT/jobs/$ID"
PY="$ROOT/.venv/bin/python"
mkdir -p "$JOB"
echo "== $ID  $TOPIC"
[ -f "$JOB/script.json" ] || "$PY" "$ROOT/pipeline/script.py" "$JOB" "$TOPIC" ${SCRIPT_ARGS:-}
"$PY" "$ROOT/pipeline/tts.py" "$JOB" --engine "${TTS_ENGINE:-edge}"
"$PY" "$ROOT/pipeline/qa_audio.py" "$JOB" --retry "${QA_RETRY:-0}" --engine "${TTS_ENGINE:-edge}" || true
"$PY" "$ROOT/pipeline/assets.py" "$JOB"
"$ROOT/pipeline/render.sh" "$JOB"
echo "== 완료: $JOB/render/final.mp4"
