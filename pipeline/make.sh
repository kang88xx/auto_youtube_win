#!/usr/bin/env bash
# 주제 한 줄 → 영상 한 편. 사용: pipeline/make.sh "<주제>" [job-id]
# 공정: 01 리서치 → 02 대본(초안 2개 + 심사) → 02b 검수 → 03 음성 → 음성 검수 → 04 소스(후보 2장 + 고르기) → 04 렌더
# 환경변수: SKIP_RESEARCH=1  SKIP_REVIEW=1  SCRIPT_ARGS="--no-web"  TTS_ENGINE=edge|voicebox  QA_RETRY=0  CANDIDATES=2  ASSET_ARGS=""
#           PRESET=3d-render (화풍+자막+목소리 묶음, pipeline/preset.py --list)
# 각 공정은 산출물이 있으면 건너뛴다(재실행 안전). 다시 하려면 해당 파일을 지우거나 공정을 --force 로 따로 돌린다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/tools/bin:$PATH"
TOPIC="$1"
if [ -n "${2:-}" ]; then ID="$2"; else
  n=1; while [ -e "$ROOT/jobs/$(date +%Y-%m-%d)-$(printf '%03d' $n)" ]; do n=$((n+1)); done
  ID="$(date +%Y-%m-%d)-$(printf '%03d' $n)"
fi
JOB="$ROOT/jobs/$ID"
if [ -f "$JOB/research/research.json" ]; then
  OLD=$("$ROOT/.venv/bin/python" -c "import json,sys;print(json.load(open(sys.argv[1])).get('topic',''))" "$JOB/research/research.json")
  [ "$OLD" = "$TOPIC" ] || echo "!! 주의: $ID 는 다른 주제('$OLD')로 만든 잡입니다. 산출물이 있으면 건너뜁니다."
fi
PY="$ROOT/.venv/bin/python"
mkdir -p "$JOB"
echo "== $ID  $TOPIC"
[ "${SKIP_RESEARCH:-0}" = 1 ] || "$PY" "$ROOT/pipeline/research.py" "$JOB" "$TOPIC" || echo "!! 리서치 실패 → 대본은 웹 검색 모드로 진행"
[ -f "$JOB/script.json" ] || "$PY" "$ROOT/pipeline/script.py" "$JOB" "$TOPIC" ${SCRIPT_ARGS:-}
[ -z "${PRESET:-}" ] || "$PY" "$ROOT/pipeline/preset.py" "$JOB" "$PRESET"
[ "${SKIP_REVIEW:-0}" = 1 ] || "$PY" "$ROOT/pipeline/review.py" "$JOB"
"$PY" "$ROOT/pipeline/tts.py" "$JOB" --engine "${TTS_ENGINE:-edge}"
"$PY" "$ROOT/pipeline/qa_audio.py" "$JOB" --retry "${QA_RETRY:-0}" --engine "${TTS_ENGINE:-edge}" || true
"$PY" "$ROOT/pipeline/assets.py" "$JOB" --candidates "${CANDIDATES:-2}" ${ASSET_ARGS:-}
"$ROOT/pipeline/render.sh" "$JOB"
echo "== 완료: $JOB/render/final.mp4"
