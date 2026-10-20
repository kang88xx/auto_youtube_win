#!/usr/bin/env python3
"""02 대본: 주제 한 줄 → jobs/{id}/script.json  (claude -p 헤드리스, 구독 요금 안에서)

사용: python pipeline/script.py jobs/2026-10-20-001 "미국 반도체 수출 규제와 삼성·하이닉스"
       [--seconds 80] [--research jobs/.../research/raw] [--no-web]

- research 폴더(.md)가 있으면 그 내용만 근거로 씀("조사한 것만 써").
- 없으면 claude가 WebSearch로 직접 확인(--no-web 이면 검색 없이 작성, 테스트용).
- 출력은 JSON 스키마로 강제. 문장 하나 = 자막 화면 하나.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "hook", "titles", "description", "tags", "sentences"],
    "properties": {
        "title": {"type": "string", "description": "영상 상단 라벨용 짧은 주제. 예: '오늘의 이슈 · 반도체'"},
        "hook": {"type": "string"},
        "titles": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "sentences": {
            "type": "array",
            "minItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text", "speaker", "emphasis", "visual"],
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "speaker": {"type": "string", "enum": ["main", "quote"]},
                    "emphasis": {"type": "array", "items": {"type": "string"}},
                    "visual": {"type": "string"},
                },
            },
        },
    },
}

PROMPT = """당신은 한국 시사 쇼츠 채널의 대본 작가다. 아래 주제로 세로 쇼츠 대본을 JSON으로 쓴다.

주제: {topic}
오늘: {today}
목표 길이: 약 {seconds}초 (한국어 TTS 기준 1문장 ≈ 3.5초 → 문장 {n_min}~{n_max}개)

{source_rule}

구조 (반드시 이 순서):
1. 훅 (1~2문장): 구체적 장면이나 숫자로 시작. "~냐고요?" "~였습니다" 같은 구어체. 첫 문장이 곧 썸네일 문구다.
2. 질문 (1문장): 시청자가 궁금해할 한 가지 질문.
3. 전개 (문장 대부분): 시간 순서대로, 숫자·고유명사·날짜를 문장마다 하나씩 박는다. 인과를 "그런데", "그래서", "문제는"으로 잇는다.
4. 되돌아오기 (1~2문장): 훅의 장면으로 돌아와 의미를 정리. 마지막 문장은 다음 편을 기대하게 하는 한 줄.

문장 규칙:
- 한 문장 = 자막 화면 하나. 12~28자, 최대 35자. 길면 두 문장으로 쪼갠다.
- 말하듯이. 번역투("~에 대해", "~하는 것으로 알려졌다") 금지. "~거든요", "~였죠", "~입니다" 섞기.
- 직접 인용은 speaker="quote", text는 따옴표 포함, 15자 이내.
- emphasis: 그 문장에서 가장 중요한 어절 1개(숫자가 있으면 숫자 포함 어절). text 안에 그대로 있는 문자열이어야 함.
- visual: 그 문장의 배경 이미지를 만들 영어 프롬프트 1줄(20~40단어). 구체적 피사체+장소+조명+분위기. 글자·로고·실존 인물 얼굴은 넣지 않는다. 뉴스 일러스트 톤.
- id는 "s01", "s02", … 순서대로.

메타:
- title: 상단 라벨용 "오늘의 이슈 · {{키워드}}" 형식, 12자 이내.
- hook: 첫 문장과 동일.
- titles: 유튜브 제목 후보 3개, 각 25자 이내, 숫자나 반전 포함.
- description: 2~3문장 + 출처 URL 목록.
- tags: 8~12개.

JSON만 출력한다."""

SOURCE_RESEARCH = """근거 자료 (이 안에 있는 내용만 쓴다. 자료에 없는 숫자·날짜·인용은 절대 만들지 않는다):
-----
{research}
-----"""

SOURCE_WEB = """근거: 먼저 WebSearch로 최신 기사 3~5개를 확인하고, 확인된 숫자·날짜·인용만 쓴다. 확인 안 된 내용은 넣지 않는다. description 끝에 확인한 기사 URL을 적는다."""

SOURCE_NONE = """근거: (테스트 모드) 검색 없이 작성. 일반적으로 알려진 사실만 쓰고, 불확실한 숫자는 '약'을 붙인다."""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("topic")
    ap.add_argument("--seconds", type=int, default=80)
    ap.add_argument("--research", type=Path, default=None)
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--model", default=None, help="claude -p --model (기본: 세션 기본값)")
    a = ap.parse_args()

    a.job.mkdir(parents=True, exist_ok=True)
    research_dir = a.research or (a.job / "research" / "raw")
    md = sorted(research_dir.glob("*.md")) if research_dir.exists() else []
    if md:
        text = "\n\n".join(f"### {p.name}\n{p.read_text()[:6000]}" for p in md[:12])
        source_rule = SOURCE_RESEARCH.format(research=text)
        tools = []
    elif a.no_web:
        source_rule = SOURCE_NONE
        tools = []
    else:
        source_rule = SOURCE_WEB
        tools = ["WebSearch", "WebFetch"]

    n = a.seconds / 3.5
    prompt = PROMPT.format(topic=a.topic, today=date.today().isoformat(), seconds=a.seconds,
                           n_min=int(n * 0.85), n_max=int(n * 1.15), source_rule=source_rule)

    # MCP 서버(Figma·Gmail·Drive·Docs·OMC 등)의 도구 스키마가 호출마다 약 9만 토큰씩 붙어서 비용의 대부분을 차지한다.
    # 대본 작성엔 필요 없으니 MCP·설정(CLAUDE.md, 훅)을 끈다: 컨텍스트 91k → 3k 미만.
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--json-schema", json.dumps(SCHEMA, ensure_ascii=False),
           "--max-turns", "20", "--system-prompt", "You write Korean short-form video scripts. Output only what is asked.",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", ""]
    if tools:
        cmd += ["--allowedTools", *tools]
    else:
        cmd += ["--tools", ""]
    if a.model:
        cmd += ["--model", a.model]

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(a.job))
    if r.returncode != 0:
        sys.exit(f"claude -p 실패 ({r.returncode}):\n{r.stderr[-2000:]}\n{r.stdout[-2000:]}")
    env = json.loads(r.stdout)
    data = env.get("structured_output")
    if data is None:
        # 구조화 출력이 없으면 result 텍스트에서 JSON 추출 시도
        txt = env.get("result", "")
        try:
            data = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
        except Exception:
            sys.exit(f"JSON 추출 실패. raw:\n{txt[:1500]}")

    # 정규화: asset 필드, id 재부여, emphasis가 text 안에 없으면 제거
    for i, s in enumerate(data["sentences"], 1):
        s["id"] = f"s{i:02d}"
        s["asset"] = None
        s["emphasis"] = [e for e in s.get("emphasis", []) if e and e in s["text"]]
    data["hook"] = data["sentences"][0]["text"]
    data["topic"] = a.topic
    data["created"] = date.today().isoformat()

    out = a.job / "script.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    (a.job / "brief.json").write_text(json.dumps({
        "topic": a.topic, "titles": data["titles"], "description": data["description"], "tags": data["tags"],
        "cost_usd": env.get("total_cost_usd"), "duration_ms": env.get("duration_ms"),
    }, ensure_ascii=False, indent=2))
    n_s = len(data["sentences"])
    chars = sum(len(s["text"]) for s in data["sentences"])
    print(f"→ {out}  문장 {n_s}개, {chars}자, 예상 {n_s*3.5:.0f}초  (claude {env.get('duration_ms',0)/1000:.0f}s)")
    for s in data["sentences"]:
        print(f"  {s['id']} [{s['speaker'][0]}] {s['text']}   ← {','.join(s['emphasis'])}")


if __name__ == "__main__":
    main()
