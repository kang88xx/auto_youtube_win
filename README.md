# auto_youtube_win — 시사 쇼츠 자동화 (윈도우 · WSL2 실행본)

설계 문서: https://claude.ai/artifact/2rn2daXpenK3wkdmyZMREF
맥 원본(`/Users/henry/Desktop/auto_youtube`)과 공정·폴더 계약은 같다. 맥 전용 부품만 교체했다.

| 부품 | 맥 | 여기(WSL2 Ubuntu 24.04, RTX 4070 Ti SUPER) |
|---|---|---|
| 음성 검수 | mlx-whisper | **faster-whisper** (CUDA float16, 실패 시 CPU int8) |
| ffmpeg | Homebrew | **tools/bin/** 정적 빌드 (sudo 없이 setup.sh가 받음) |
| Python | python -m venv | **uv venv** (.venv, Python 3.12) |
| Voicebox | 맥 앱 | 윈도우 Voicebox 앱. WSL에서 호스트 IP 자동 탐색 |

## 윈도우에서 바로 실행 (.bat)
WSL을 직접 열 필요 없이 탐색기 더블클릭이나 cmd/PowerShell에서 돌린다. 안에서는 WSL2 Ubuntu가 실행된다.
```bat
setup.bat --check                                 :: 환경 점검 (처음엔 setup.bat 으로 전체 설치)
make.bat "미국 반도체 수출 규제와 삼성·하이닉스"   :: 주제 한 줄 → jobs\YYYY-MM-DD-001\render\final.mp4
make.bat "<주제>" my-job-id                        :: 잡 id 지정
render.bat jobs\_sample                           :: 렌더만 (음성·이미지가 이미 있을 때)
studio.bat                                        :: 미리보기 스튜디오, 브라우저가 http://localhost:3000 을 자동으로 연다
```
환경변수는 cmd에서 `set SCRIPT_ARGS=--no-web` 처럼 먼저 잡고 `make.bat`을 부르면 된다 (`TTS_ENGINE`, `QA_RETRY` 도 같은 방식).
더블클릭으로 띄우면 끝나고 창이 안 닫히게 멈춘다(아무 키). 경로는 `jobs\_sample` 처럼 윈도우식으로 써도 된다.
내부 진입점은 `pipeline/wsl.sh` — wsl.exe가 띄우는 셸은 `.bashrc`를 안 읽어서 nvm·uv PATH를 여기서 맞춘다.

## 처음 한 번 (WSL 터미널에서)
```bash
bash setup.sh            # venv · ffmpeg · npm install · 헤드리스 크롬 · whisper 모델 (10분 내외)
bash setup.sh --check    # 뭐가 빠졌는지 점검
```
`.env` 에 `MAGNIFIC_API_KEY=...` 필요(맥에서 복사해 옴).

## 폴더
```
pipeline/   공정 스크립트 (research.py, script.py, review.py, tts.py, qa_audio.py, assets.py, render.sh, make.sh, llm.py)
render/     Remotion 템플릿 (1080×1920, 30fps) — src/Shorts.tsx
jobs/{id}/  잡 하나 = 영상 하나 (script.json이 중심 계약)
tools/bin/  ffmpeg · ffprobe (git 제외)
*.bat       윈도우 런처 (setup · make · render · studio) → pipeline/wsl.sh 경유
.venv/      Python 3.12 (edge-tts, yt-dlp, faster-whisper)
```

## 한 편 만들기 (P3 상태: 주제 한 줄이면 끝, 품질 우선)
```bash
pipeline/make.sh "미국 반도체 수출 규제와 삼성·하이닉스"      # jobs/YYYY-MM-DD-001/ 생성 → final.mp4 (15~25분)
pipeline/make.sh "<주제>" my-job-id                              # 잡 id 지정
SKIP_RESEARCH=1 SCRIPT_ARGS="--no-web" pipeline/make.sh "<주제>" # 리서치·검색 없이(테스트)
```
공정 순서와 산출물 (각 공정은 산출물이 있으면 건너뛴다 → 중간에 끊겨도 다시 `make.sh`):

| 공정 | 스크립트 | 하는 일 | 산출물 |
|---|---|---|---|
| 01 리서치 | `research.py` | claude가 WebSearch·WebFetch로 기사 8개 안팎을 실제로 읽고 사실·숫자·인용 정리 | `research/raw/00-brief.md`, `NN-매체.md`, `research.json` |
| 02 대본 | `script.py` | **claude와 codex가 동시에 초안**을 쓰고, 심사 패스(claude)가 사실 충실도·훅·흐름 기준으로 합쳐 최종본 | `drafts/claude.json`, `codex.json`, `judge.json`, `script.json` |
| 02b 검수 | `review.py` | 다른 호출이 근거 자료와 대조해 사실·문장 길이·번역투·emphasis·visual을 고침 | `qa/script.json`(보고서), `drafts/pre-review.json` |
| 03 음성 | `tts.py` | edge-tts 또는 Voicebox | `audio/*.wav`, `durations.json` |
| 음성 검수 | `qa_audio.py` | faster-whisper(CUDA)로 받아써서 대조 | `qa/audio.json` |
| 04 소스 | `assets.py` | claude가 화풍 한 줄 + 문장별 프롬프트를 다듬고, **문장당 2장 생성**, claude가 이미지를 직접 보고 1장 선택 | `assets/cand/{id}_{k}.jpg`, `assets/{id}.jpg` |
| 04 렌더 | `render.sh` | Remotion | `render/final.mp4`, `thumb.png` |

공정별로 따로 돌릴 때:
```bash
.venv/bin/python pipeline/research.py jobs/<id> "<주제>" [--articles 8] [--force]
.venv/bin/python pipeline/script.py jobs/<id> "<주제>" [--seconds 80] [--drafts claude,codex] [--no-judge] [--no-web]
.venv/bin/python pipeline/review.py jobs/<id> [--force]
.venv/bin/python pipeline/tts.py jobs/<id> [--engine voicebox] [--only s03]
.venv/bin/python pipeline/qa_audio.py jobs/<id> [--retry 2] [--device cuda|cpu]
.venv/bin/python pipeline/assets.py jobs/<id> [--candidates 2] [--no-refine] [--no-pick] [--only s01,s02] [--force]
pipeline/render.sh jobs/<id>
cd render && npm run dev                      # 미리보기 스튜디오 (브라우저: http://localhost:3000)
```
script.json 문장 필드: `id, text, speaker(main|quote), emphasis[], visual(작가 초안 프롬프트), visual_final(다듬은 프롬프트), asset, asset_pick`. 최상위에 `style`(화풍).
숫자가 있는 문장은 카운터 카드, 없으면 emphasis[0]이 키워드 카드로 자동 표시.

LLM 호출은 전부 `pipeline/llm.py` 를 거친다. claude는 `claude -p`(Max 구독), codex는 `codex exec`(ChatGPT 구독) — 둘 다 JSON 스키마로 출력을 강제. `CODEX_MODEL`, `CODEX_EFFORT` 환경변수로 코덱스 모델을 바꾼다.

테스트 픽스처: `jobs/_sample`(8문장), `jobs/_p2test`(21문장), `jobs/_p3test`(리서치→초안 2개→심사→검수→후보 2장 선택까지 전 공정). 음성·이미지가 들어 있어 `pipeline/render.sh jobs/_sample` 만으로 렌더를 확인할 수 있다.

## 비용
- 대본: `claude -p` (편당 약 2분). Claude Max 구독으로 로그인돼 있으면 구독 한도 안에서 쓰이고 따로 청구되지 않는다.
  `brief.json`의 `cost_usd`는 API 요금 환산값일 뿐이다(참고용). 단, 구독 설정에서 "추가 사용(extra usage)"이 켜져 있으면 한도를 넘긴 뒤부터 API 요금으로 청구된다.
  script.py는 MCP 서버·CLAUDE.md를 끄고 호출한다 — 안 끄면 Figma·Gmail·Drive 도구 스키마가 호출마다 약 9만 토큰 붙어 편당 환산비용이 3배쯤 된다.
- 이미지: Magnific Mystic 1K = 50크레딧/장. 문장당 2장 후보라 편당 약 25문장 × 2 = 2,500크레딧 (Premium 월 240K → 약 95편/월). 아끼려면 `CANDIDATES=1`.
- codex: ChatGPT 구독 안에서. 대본 초안 1개(편당 1~3분).
- 음성: edge-tts 무료. Voicebox 로컬 무료.

## Voicebox (윈도우 쪽에서 실행)
윈도우용 Voicebox 앱을 설치하고 서버를 켠다 (포트 17493). WSL에서는 `tts.py --engine voicebox`가
`VOICEBOX_URL` 환경변수 → `127.0.0.1` → 윈도우 호스트 IP(`/etc/resolv.conf`의 nameserver) 순으로 살아있는 서버를 찾는다.
안 잡히면 직접 지정: `VOICEBOX_URL=http://<윈도우IP>:17493`. 윈도우 방화벽이 WSL 서브넷을 막으면 허용 규칙 추가.
프로필(`POST /profiles`)은 아직 없음 — 녹음 파일이 오면 클로닝 프로필 생성. 프로필 id는 `VOICEBOX_PROFILE_MAIN`, `VOICEBOX_PROFILE_QUOTE`.

## 음성 검수 단독 실행
```bash
.venv/bin/python -c "from faster_whisper import WhisperModel as W; m=W('large-v3-turbo',device='cuda',compute_type='float16'); print(''.join(s.text for s in m.transcribe('jobs/_sample/audio/s01.wav',language='ko')[0]))"
```

## 걸리면 그때
| 신호 | 대응 |
|---|---|
| `/mnt/c` 에서 npm·렌더가 느림 | WSL이 윈도우 디스크를 9p로 읽어서 그렇다. 참을 수 없으면 프로젝트를 `~/auto_youtube_win`(ext4)으로 옮기고 윈도우에서는 `\\wsl$\Ubuntu\home\...` 로 연다 |
| whisper가 `libcudnn` / `libcublas` 못 찾음 | `uv pip install --python .venv/bin/python nvidia-cublas-cu12 nvidia-cudnn-cu12` 재설치. 그래도 안 되면 `--device cpu` (16코어라 문장당 1~2초) |
| 렌더가 크롬을 못 띄움 | `cd render && npx remotion browser ensure`. 라이브러리 부족 메시지면 `sudo apt install libnss3 libatk-bridge2.0-0 libgbm1 libasound2t64` |
| `sudo apt install ffmpeg` 가 가능해지면 | tools/bin 을 지워도 된다. 스크립트는 PATH의 ffmpeg로 자동 전환 |
| 구글 폰트 로딩 타임아웃 | 이미 로컬 폰트(render/public/fonts)로 고정. 폰트 추가 시 같은 방식 |
| public/jobs 심볼릭 링크 | 번들러가 멈춤. render.sh처럼 복사해서 쓴다 |
| 맥 원본과 코드 동기화 | 이 폴더가 git 루트. 맥에도 같은 저장소를 두고 코드만 push/pull. jobs 산출물·venv·node_modules는 각자 |
