#!/usr/bin/env python3
"""01 리서치: 주제 한 줄 → jobs/{id}/research/raw/*.md (+ research.json)

사용: python pipeline/research.py jobs/<id> "<주제>" [--articles 8] [--force]

claude -p 가 WebSearch/WebFetch 로 최신 기사를 찾아 읽고, 기사별 사실·숫자·인용을 구조화해 돌려준다.
raw/00-brief.md  : 타임라인 + 핵심 사실 + 상충/미확인 항목 (대본이 가장 먼저 읽는 요약)
raw/NN-<매체>.md : 기사 하나 = 파일 하나
script.py 는 raw/*.md 가 있으면 그 안의 내용만 근거로 대본을 쓴다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import claude_json, cost_of  # noqa: E402

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["queries", "articles", "timeline", "key_facts", "conflicts", "open_questions"],
    "properties": {
        "queries": {"type": "array", "items": {"type": "string"}},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "outlet", "date", "url", "summary", "facts", "numbers", "quotes"],
                "properties": {
                    "title": {"type": "string"},
                    "outlet": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD, 모르면 빈 문자열"},
                    "url": {"type": "string"},
                    "summary": {"type": "string", "description": "3~5문장 요약"},
                    "facts": {"type": "array", "items": {"type": "string"}, "description": "기사에서 확인된 사실 (한 줄씩, 날짜·주체 포함)"},
                    "numbers": {"type": "array", "items": {"type": "string"}, "description": "숫자가 든 사실. 예: '삼성 시안 공장 낸드 생산 비중 약 40% (2024년 기준)'"},
                    "quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["who", "text"],
                            "properties": {"who": {"type": "string"}, "text": {"type": "string"}},
                        },
                    },
                },
            },
        },
        "timeline": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["date", "event"],
                "properties": {"date": {"type": "string"}, "event": {"type": "string"}},
            },
        },
        "key_facts": {"type": "array", "items": {"type": "string"}, "description": "두 매체 이상에서 교차 확인된 핵심 사실 5~12개"},
        "conflicts": {"type": "array", "items": {"type": "string"}, "description": "매체끼리 숫자·날짜가 다른 항목"},
        "open_questions": {"type": "array", "items": {"type": "string"}, "description": "확인 못 한 것, 대본에 넣으면 안 되는 것"},
    },
}

PROMPT = """당신은 한국 시사 쇼츠 채널의 리서처다. 아래 주제로 대본을 쓰기 전에 사실 자료를 모은다.

주제: {topic}
오늘: {today}

할 일:
1. WebSearch 로 한국어·영어 검색어를 각각 2~4개 만들어 검색한다. 최근 2주 기사를 우선하되, 배경이 되는 과거 기사도 1~2개 포함한다.
2. 유력 매체(연합뉴스, 한국경제, 조선·중앙·동아, 매일경제, Reuters, Bloomberg, FT, WSJ, 정부·기관 공식 발표) 위주로 기사 {n}개 안팎을 WebFetch 로 실제로 읽는다. 검색 결과 스니펫만 보고 쓰지 않는다.
3. 기사마다 확인된 사실, 숫자(단위·기준 시점 포함), 직접 인용(발언자 명시)을 뽑는다.
4. 매체 두 곳 이상에서 교차 확인된 것만 key_facts 에 넣는다. 매체마다 숫자가 다르면 conflicts 에 적는다.
5. 날짜 순 timeline 을 만든다. 모르는 것은 open_questions 에 적고 지어내지 않는다.

주의: 숫자·날짜·인용은 기사 본문에 있는 그대로. 추정이면 '약'을 붙이고 출처 기사를 facts 에 함께 적는다.
JSON만 출력한다."""


def slug(s: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", s).strip("-")
    return s[:30] or "article"


def write_md(job: Path, data: dict, topic: str) -> list[Path]:
    raw = job / "research" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for old in raw.glob("*.md"):
        old.unlink()
    out = []
    b = [f"# 리서치 요약: {topic}", f"조사일: {date.today().isoformat()}", ""]
    b += ["## 타임라인"] + [f"- {t['date']}: {t['event']}" for t in data["timeline"]] + [""]
    b += ["## 교차 확인된 핵심 사실"] + [f"- {f}" for f in data["key_facts"]] + [""]
    if data["conflicts"]:
        b += ["## 매체 간 상충 (쓸 때 주의)"] + [f"- {c}" for c in data["conflicts"]] + [""]
    if data["open_questions"]:
        b += ["## 미확인 (대본에 넣지 말 것)"] + [f"- {q}" for q in data["open_questions"]] + [""]
    b += ["## 기사 목록"] + [f"- [{a['outlet']}] {a['title']} ({a['date']}) {a['url']}" for a in data["articles"]]
    p = raw / "00-brief.md"
    p.write_text("\n".join(b), encoding="utf-8")
    out.append(p)
    for i, a in enumerate(data["articles"], 1):
        lines = [f"# {a['title']}", f"매체: {a['outlet']}  날짜: {a['date']}  URL: {a['url']}", "", "## 요약", a["summary"], ""]
        if a["facts"]:
            lines += ["## 사실"] + [f"- {f}" for f in a["facts"]] + [""]
        if a["numbers"]:
            lines += ["## 숫자"] + [f"- {n}" for n in a["numbers"]] + [""]
        if a["quotes"]:
            lines += ["## 인용"] + [f"- {q['who']}: \"{q['text']}\"" for q in a["quotes"]] + [""]
        p = raw / f"{i:02d}-{slug(a['outlet'])}.md"
        p.write_text("\n".join(lines), encoding="utf-8")
        out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("topic")
    ap.add_argument("--articles", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()

    rj = a.job / "research" / "research.json"
    if rj.exists() and not a.force:
        print(f"→ {rj} 있음 (건너뜀, --force 로 다시)")
        return
    a.job.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT.format(topic=a.topic, today=date.today().isoformat(), n=a.articles)
    data, env = claude_json(prompt, SCHEMA, cwd=a.job, tools=["WebSearch", "WebFetch"], max_turns=80, model=a.model)
    if len(data.get("articles", [])) < 2 or not data.get("key_facts"):
        sys.exit(f"리서치 결과가 빈약해 저장하지 않음 (기사 {len(data.get('articles', []))}개, 핵심사실 {len(data.get('key_facts', []))}개). "
                 f"미확인: {data.get('open_questions', [])[:3]}")
    data["topic"] = a.topic
    data["created"] = date.today().isoformat()
    data["cost_usd"] = cost_of(env)
    data["duration_ms"] = env.get("duration_ms")
    files = write_md(a.job, data, a.topic)  # md 먼저, json 은 마지막 (json 이 있으면 '완료'로 본다)
    rj.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {rj}  기사 {len(data['articles'])}개, 핵심사실 {len(data['key_facts'])}개, "
          f"상충 {len(data['conflicts'])}개, 미확인 {len(data['open_questions'])}개  "
          f"(claude {env.get('duration_ms', 0) / 1000:.0f}s, 환산 ${cost_of(env) or 0:.2f})")
    for a_ in data["articles"]:
        print(f"  [{a_['outlet']}] {a_['date']} {a_['title'][:50]}")
    for q in data["open_questions"]:
        print(f"  ? {q}")
    print(f"  raw/*.md {len(files)}개")


if __name__ == "__main__":
    main()
