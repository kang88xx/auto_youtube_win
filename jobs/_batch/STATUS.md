# 작업 상태 (2026-10-21 05:20 저장)

## 끝난 것
- 전 공정 파이프라인: 리서치 → claude+codex 초안 → 심사 → 검수 → 음성 → 음성검수 → 이미지 2장 중 선택 → 렌더. `pipeline/make.sh "<주제>"` 또는 윈도우 `make.bat "<주제>"`.
- 프리셋 10종(화풍+자막+테마+목소리): `pipeline/preset.py --list`
- 스타일 비교 영상 10편: `jobs/v01-… ~ v10-…/render/final.mp4`, 비교표 `jobs/_batch/summary.md`
- 전부 GitHub `kang88xx/auto_youtube_win` main 에 푸시됨 (영상·이미지 산출물은 git 제외, 이 PC에만 있음)

## 보는 법
- 영상: 각 잡 `render/final.mp4`, 썸네일 `render/thumb.png`
- 이미지 후보 전체(탈락 포함): `assets/cand/`, 선택 이유: `script.json` 의 `asset_pick`
- 대본 초안 둘과 심사 메모: `drafts/claude.json`, `drafts/codex.json`, `drafts/judge.json`
- 검수 지적: `qa/script.json`, 근거 기사: `research/raw/`

## 다음에 할 수 있는 것
- 마음에 드는 조합을 고르면 `pipeline/preset.py` 에 house 프리셋으로 고정 → `make.bat` 한 줄로 같은 컨셉 반복
- 자막만 바꿔 보기: `.venv/bin/python pipeline/preset.py jobs/<id> <프리셋>` 후 `pipeline/render.sh jobs/<id>`
- 이미지까지 바꾸기: 위에 더해 `.venv/bin/python pipeline/assets.py jobs/<id> --force` 후 렌더
- 목소리 폭 넓히기: 녹음 파일 → Voicebox 클로닝 (아직 프로필 없음)

## 관찰 메모
- 주제-화풍 궁합: 아이소메트릭=도시/건물, 클레이=캐릭터/소품, 콜라주=스포츠, 사진=숫자 카드
- 밝은 배경 화풍(스케치·망점)은 외곽선/바 자막 필요. 스케치는 간판 글자가 자주 생김
- 3D·클레이가 편 안에서 톤이 가장 안정적, 수채화는 장면마다 색이 조금 흔들림
