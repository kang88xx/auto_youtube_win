#!/usr/bin/env bash
# 윈도우 .bat 런처 → WSL 진입점. wsl.exe 가 띄우는 셸은 ~/.bashrc 를 안 읽어서(비대화형) nvm·uv PATH가 비어 있다.
# 여기서 PATH를 맞추고, 윈도우식 경로(jobs\_sample)를 리눅스식으로 바꾼 뒤 명령을 실행한다.
# 사용: pipeline/wsl.sh <명령> [인자...]   예) pipeline/wsl.sh pipeline/make.sh "주제"
set -euo pipefail
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
args=()
for a in "$@"; do args+=("${a//\\//}"); done
exec "${args[@]}"
