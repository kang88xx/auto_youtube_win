#!/usr/bin/env bash
# WSL2(Ubuntu) 환경 구축. 여러 번 실행해도 안전. sudo 불필요.
#   bash setup.sh            # 전체
#   bash setup.sh --check    # 점검만
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
ok(){ printf '  \033[32m✓\033[0m %s\n' "$*"; }; bad(){ printf '  \033[31m✗\033[0m %s\n' "$*"; }

if [ "${1:-}" = "--check" ]; then
  echo "== 점검"
  command -v node >/dev/null && ok "node $(node -v)" || bad "node 없음 (nvm install 24)"
  command -v claude >/dev/null && ok "claude $(claude --version 2>/dev/null | head -1)" || bad "claude CLI 없음"
  command -v uv >/dev/null && ok "uv" || bad "uv 없음 (curl -LsSf https://astral.sh/uv/install.sh | sh)"
  [ -x .venv/bin/python ] && ok "venv $(.venv/bin/python -V)" || bad "venv 없음 → bash setup.sh"
  .venv/bin/python -c 'import edge_tts, faster_whisper, yt_dlp' 2>/dev/null && ok "python 패키지" || bad "python 패키지 부족"
  [ -x tools/bin/ffmpeg ] && ok "ffmpeg $(tools/bin/ffmpeg -version | head -1 | cut -d' ' -f3)" || bad "tools/bin/ffmpeg 없음"
  [ -d render/node_modules/remotion ] && ok "remotion node_modules" || bad "render/node_modules 없음"
  command -v nvidia-smi >/dev/null && ok "GPU $(nvidia-smi --query-gpu=name --format=csv,noheader)" || bad "GPU 없음 → whisper CPU"
  [ -f .env ] && grep -q MAGNIFIC_API_KEY .env && ok ".env MAGNIFIC_API_KEY" || bad ".env 에 MAGNIFIC_API_KEY 없음"
  for h in 127.0.0.1 "$(awk '/nameserver/{print $2; exit}' /etc/resolv.conf)"; do
    curl -fs -m 2 "http://$h:17493/health" >/dev/null 2>&1 && { ok "Voicebox http://$h:17493"; break; }
  done || true
  exit 0
fi

echo "== 1/4 Python venv (uv)"
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
[ -x .venv/bin/python ] || uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -q edge-tts yt-dlp faster-whisper "av<16" nvidia-cublas-cu12 nvidia-cudnn-cu12
ok "venv"

echo "== 2/4 ffmpeg (정적 빌드 → tools/bin)"
if [ ! -x tools/bin/ffmpeg ]; then
  mkdir -p tools/dl tools/bin && cd tools/dl
  curl -sSL -o ff.tar.xz https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz
  tar -xJf ff.tar.xz && D=$(ls -d ffmpeg-*/ | head -1)
  cp "$D/bin/ffmpeg" "$D/bin/ffprobe" ../bin/ && chmod +x ../bin/ffmpeg ../bin/ffprobe
  cd "$ROOT" && rm -rf tools/dl
fi
ok "ffmpeg"

echo "== 3/4 Remotion (npm install + 헤드리스 크롬)"
cd render && npm install --no-audit --no-fund --silent && npx remotion browser ensure --log=error && cd "$ROOT"
ok "remotion"

echo "== 4/4 whisper 모델 미리 받기 (large-v3-turbo, ~1.6GB)"
.venv/bin/python - <<'PY'
from faster_whisper import WhisperModel
try:
    WhisperModel("large-v3-turbo", device="cuda", compute_type="float16"); print("  ✓ whisper on cuda")
except Exception as e:
    print("  ! cuda 실패, cpu 로 확인:", str(e)[:120]); WhisperModel("large-v3-turbo", device="cpu", compute_type="int8"); print("  ✓ whisper on cpu")
PY
echo; echo "완료. 점검: bash setup.sh --check"
