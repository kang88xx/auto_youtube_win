#!/usr/bin/env bash
# 04 렌더: jobs/{id}/ (script.json + audio/ + assets/) → jobs/{id}/render/final.mp4 + thumb.png
# 사용: pipeline/render.sh jobs/_sample
set -euo pipefail
JOB="$(cd "$1" && pwd)"
ID="$(basename "$JOB")"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/tools/bin:$PATH"
R="$ROOT/render"

# Remotion은 public/ 아래 파일만 staticFile로 읽는다. 심볼릭 링크는 번들러가 멈춰서 복사한다.
rm -rf "$R/public/jobs/$ID"
mkdir -p "$R/public/jobs"
cp -R "$JOB" "$R/public/jobs/$ID"
rm -rf "$R/public/jobs/$ID/render"
mkdir -p "$JOB/render"

cd "$R"
npx remotion render src/index.ts Shorts "$JOB/render/final.mp4" --props="{\"jobId\":\"$ID\"}" --log=error
npx remotion still src/index.ts Shorts "$JOB/render/thumb.png" --props="{\"jobId\":\"$ID\"}" --frame=20 --log=error
rm -rf "$R/public/jobs/$ID"

ffprobe -v error -show_entries format=duration -of csv=p=0 "$JOB/render/final.mp4" | xargs printf "→ %s/render/final.mp4  (%ss)\n" "$JOB"
