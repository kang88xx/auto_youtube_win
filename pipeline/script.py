#!/usr/bin/env python3
"""02 대본: 주제 한 줄 → jobs/{id}/script.json

사용: python pipeline/script.py jobs/<id> "<주제>" [--seconds 80] [--drafts claude,codex] [--no-web] [--no-judge]

흐름:
  1. research/raw/*.md 가 있으면(01 research.py) 그 자료만 근거로 쓴다. 없으면 claude 가 WebSearch 로 직접 확인(--no-web 이면 검색 없이, 테스트용).
  2. --drafts 에 적힌 엔진이 각각 초안을 쓴다 (claude -p, codex exec 동시 실행) → drafts/{engine}.json
  3. 초안이 둘 이상이면 심사 패스(claude)가 사실 충실도·훅·흐름·문장 규칙 기준으로 고르고 다듬어 최종본을 만든다 → drafts/judge.json
  4. 정규화(id 재부여, emphasis 검증) 후 script.json + brief.json 저장.
출력은 JSON 스키마로 강제. 문장 하나 = 자막 화면 하나.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import claude_json, codex_json, cost_of, have_codex, validate_script  # noqa: E402

SENTENCE = {
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
}

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
        "sentences": {"type": "array", "minItems": 8, "items": SENTENCE},
    },
}

JUDGE_SCHEMA = json.loads(json.dumps(SCHEMA))
JUDGE_SCHEMA["required"] = SCHEMA["required"] + ["notes"]
JUDGE_SCHEMA["properties"]["notes"] = {"type": "string", "description": "어느 초안을 왜 골랐고 무엇을 고쳤는지 3~6문장"}

RULES = """구조 (반드시 이 순서):
1. 훅 (1~2문장): 구체적 장면이나 숫자로 시작. "~냐고요?" "~였습니다" 같은 구어체. 첫 문장이 곧 썸네일 문구다.
2. 질문 (1문장): 시청자가 궁금해할 한 가지 질문.
3. 전개 (문장 대부분): 시간 순서대로, 숫자·고유명사·날짜를 문장마다 하나씩 박는다. 인과를 "그런데", "그래서", "문제는"으로 잇는다.
4. 되돌아오기 (1~2문장): 훅의 장면으로 돌아와 의미를 정리. 마지막 문장은 다음 편을 기대하게 하는 한 줄.

문장 규칙:
- 한 문장 = 자막 화면 하나. 12~28자, 최대 35자. 길면 두 문장으로 쪼갠다.
- 말하듯이. 번역투("~에 대해", "~하는 것으로 알려졌다") 금지. "~거든요", "~였죠", "~입니다" 섞기.
- 직접 인용은 speaker="quote", text는 따옴표 포함, 15자 이내. 근거 자료에 있는 실제 발언만 인용한다. 자료에 발언이 없으면 quote 를 쓰지 않는다.
- emphasis: 그 문장에서 가장 중요한 어절 1개(숫자가 있으면 숫자 포함 어절). text 안에 그대로 있는 문자열이어야 함.
- visual: 그 문장의 배경 이미지를 만들 영어 프롬프트 1줄(20~40단어). 구체적 피사체+장소+조명+분위기. 글자·로고·실존 인물 얼굴은 넣지 않는다. 뉴스 일러스트 톤.
- TTS가 읽는다. 영문 약어·외래어는 읽히는 대로 한글로 쓴다(예: "Mod B"→"모드 비", "VEU"→"브이이유", "TTF"→"티티에프"). 회사명은 "SK하이닉스"처럼 통용 표기 그대로. 기호(%, 조, 억)는 그대로 둔다.
- id는 "s01", "s02", … 순서대로.

메타:
- title: 상단 라벨용 "오늘의 이슈 · {키워드}" 형식, 전체 16자 이내.
- hook: 첫 문장과 동일.
- titles: 유튜브 제목 후보 3개, 각 25자 이내, 숫자나 반전 포함.
- description: 시청자용 2~3문장. 근거 기사가 있으면 그 URL 목록을 뒤에 붙인다(없으면 URL 을 만들지 않는다). 작업 메모는 넣지 않는다.
- tags: 8~12개."""

PROMPT = """당신은 한국 시사 쇼츠 채널의 대본 작가다. 아래 주제로 세로 쇼츠 대본을 JSON으로 쓴다.

주제: {topic}
오늘: {today}
목표 길이: 약 {seconds}초 (한국어 TTS 기준 1문장 ≈ 3.5초 → 문장 {n_min}~{n_max}개)

{source_rule}

{rules}

JSON만 출력한다."""

SOURCE_RESEARCH = """근거 자료 (이 안에 있는 내용만 쓴다. 자료에 없는 숫자·날짜·인용은 절대 만들지 않는다. '미확인' 항목은 넣지 않는다):
-----
{research}
-----"""

SOURCE_WEB = """근거: 먼저 WebSearch로 최신 기사 3~5개를 확인하고, 확인된 숫자·날짜·인용만 쓴다. 확인 안 된 내용은 넣지 않는다. description 끝에 확인한 기사 URL을 적는다."""

SOURCE_NONE = """근거: (테스트 모드) 검색 없이 작성. 일반적으로 알려진 사실만 쓰고, 불확실한 숫자는 '약'을 붙인다. 직접 인용(speaker="quote")과 URL 은 쓰지 않는다."""

JUDGE_PROMPT = """당신은 한국 시사 쇼츠 채널의 편집장이다. 같은 주제로 작가 둘이 쓴 초안을 심사해 최종 대본 하나를 만든다.

주제: {topic}
오늘: {today}
목표 길이: 약 {seconds}초 (문장 {n_min}~{n_max}개)

{source_rule}

심사 기준 (중요한 순):
1. 사실 충실도: 근거 자료에 있는 숫자·날짜·인용만. 자료에 없거나 상충하는 내용은 빼거나 '약'으로 완화한다.
2. 훅: 첫 문장이 3초 안에 멈추게 하는가. 구체적 장면·숫자·반전.
3. 흐름: 질문 → 시간 순 전개 → 되돌아오기. 인과가 끊기지 않는가. 문장마다 새 정보 하나.
4. 문장 규칙(아래)을 지켰는가. 어기면 고친다.
5. visual 프롬프트가 장면을 구체적으로 그리는가.

방법: 더 나은 초안을 뼈대로 삼고, 다른 초안의 더 좋은 문장·훅·숫자를 가져와 합친다. 필요하면 직접 고쳐 쓴다. 합친 뒤 전체를 처음부터 소리 내 읽듯 점검한다.

{rules}

----- 초안 A ({engine_a}) -----
{draft_a}

----- 초안 B ({engine_b}) -----
{draft_b}

최종 대본을 같은 JSON 형식으로 출력하고, notes 에 무엇을 왜 골랐고 고쳤는지 적는다. JSON만 출력한다."""


def load_research(job: Path, research: Path | None) -> str | None:
    d = research or (job / "research" / "raw")
    md = sorted(d.glob("*.md")) if d.exists() else []
    if not md:
        return None
    if len(md) > 24:
        print(f"  리서치 파일 {len(md)}개 중 24개만 사용", file=sys.stderr)
    return "\n\n".join(f"### {p.name}\n{p.read_text(encoding='utf-8')[:8000]}" for p in md[:24])


def normalize(data: dict, topic: str) -> dict:
    for i, s in enumerate(data["sentences"], 1):
        s["id"] = f"s{i:02d}"
        s.setdefault("asset", None)
        s["emphasis"] = [e.strip() for e in s.get("emphasis", []) if e and e.strip() and e.strip() in s["text"]][:1]
    validate_script(data)
    data["hook"] = data["sentences"][0]["text"]
    data["topic"] = topic
    data["created"] = date.today().isoformat()
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("topic")
    ap.add_argument("--seconds", type=int, default=80)
    ap.add_argument("--research", type=Path, default=None)
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--drafts", default=None, help="초안 엔진. 기본: claude,codex (codex 없으면 claude)")
    ap.add_argument("--no-judge", action="store_true", help="심사 없이 첫 엔진 초안을 그대로 쓴다")
    ap.add_argument("--model", default=None, help="claude -p --model (기본: 세션 기본값)")
    ap.add_argument("--force", action="store_true", help="drafts/*.json 이 있어도 초안을 다시 쓴다")
    a = ap.parse_args()

    a.job.mkdir(parents=True, exist_ok=True)
    research = load_research(a.job, a.research)
    if research:
        source_rule, tools = SOURCE_RESEARCH.format(research=research), []
    elif a.no_web:
        source_rule, tools = SOURCE_NONE, []
    else:
        source_rule, tools = SOURCE_WEB, ["WebSearch", "WebFetch"]

    n = a.seconds / 3.5
    fmt = dict(topic=a.topic, today=date.today().isoformat(), seconds=a.seconds,
               n_min=int(n * 0.85), n_max=int(n * 1.15), source_rule=source_rule, rules=RULES)
    prompt = PROMPT.format(**fmt)

    engines = [e for e in (a.drafts or ("claude,codex" if have_codex() else "claude")).split(",") if e]
    if "codex" in engines and tools:  # codex 는 웹 검색이 없다 → 리서치 없이 웹 모드면 claude 만
        print("codex: 리서치 자료 없이 웹 검색 모드라 건너뜀 (research.py 먼저 돌리면 참여)")
        engines = [e for e in engines if e != "codex"]
    if a.no_judge:
        engines = engines[:1]
    if not engines:
        sys.exit("쓸 수 있는 초안 엔진이 없습니다 (--drafts 확인)")

    def run(engine: str):
        if engine == "claude":
            return engine, claude_json(prompt, SCHEMA, cwd=a.job, tools=tools, max_turns=30, model=a.model)
        if engine == "codex":
            return engine, codex_json(prompt, SCHEMA, cwd=a.job)
        raise ValueError(f"모르는 엔진: {engine}")

    drafts: dict[str, dict] = {}
    metas: dict[str, dict] = {}
    ddir = a.job / "drafts"
    ddir.mkdir(exist_ok=True)
    todo = []
    for e in engines:  # 이미 써 둔 초안은 다시 안 쓴다 (심사만 실패했던 경우 등)
        f = ddir / f"{e}.json"
        if f.exists() and not a.force:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                validate_script(d)
                drafts[e] = d
                metas[e] = {"reused": True}
                print(f"  초안 {e}: 기존 {f.name} 사용 (--force 로 다시)")
                continue
            except Exception:
                pass
        todo.append(e)
    if todo:
        with ThreadPoolExecutor(max_workers=len(todo)) as ex:
            for fut in [ex.submit(run, e) for e in todo]:
                try:
                    engine, (data, meta) = fut.result()
                    validate_script(data)
                except Exception as e:  # 한 엔진이 죽어도 다른 초안은 살린다
                    print(f"! 초안 실패: {str(e)[:400]}", file=sys.stderr)
                    continue
                drafts[engine] = data
                metas[engine] = {"duration_ms": meta.get("duration_ms"), "cost_usd": meta.get("total_cost_usd")}
                (ddir / f"{engine}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  초안 {engine}: 문장 {len(data['sentences'])}개  ({(meta.get('duration_ms') or 0) / 1000:.0f}s)")
    if not drafts:
        sys.exit("초안이 하나도 없습니다.")

    judge_meta = None
    final = None
    if len(drafts) >= 2:
        (ea, da), (eb, db) = list(drafts.items())[:2]
        jp = JUDGE_PROMPT.format(**fmt, engine_a=ea, engine_b=eb,
                                 draft_a=json.dumps(da, ensure_ascii=False, indent=1),
                                 draft_b=json.dumps(db, ensure_ascii=False, indent=1))
        try:
            final, env = claude_json(jp, JUDGE_SCHEMA, cwd=a.job, max_turns=10, model=a.model)
            validate_script(final)
            judge_meta = {"engines": [ea, eb], "notes": final.pop("notes", ""),
                          "duration_ms": env.get("duration_ms"), "cost_usd": cost_of(env)}
            (ddir / "judge.json").write_text(json.dumps({**judge_meta, "script": final}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  심사: {judge_meta['notes'][:200]}")
        except Exception as e:  # 심사가 죽으면 첫 초안으로 간다. 초안은 drafts/ 에 남아 있다
            print(f"! 심사 실패, {ea} 초안 사용: {str(e)[:300]}", file=sys.stderr)
            final = None
    if final is None:
        final = next(iter(drafts.values()))

    data = normalize(final, a.topic)
    out = a.job / "script.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    brief_path = a.job / "brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else {}
    brief.update({
        "topic": a.topic, "titles": data["titles"], "description": data["description"], "tags": data["tags"],
        "source": "research" if research else ("none" if a.no_web else "web"),
        "drafts": metas, "judge": judge_meta,
        "cost_usd": round(sum((m.get("cost_usd") or 0) for m in metas.values()) + ((judge_meta or {}).get("cost_usd") or 0), 3),
    })
    brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    n_s = len(data["sentences"])
    chars = sum(len(s["text"]) for s in data["sentences"])
    print(f"→ {out}  문장 {n_s}개, {chars}자, 예상 {n_s * 3.5:.0f}초  (초안 {','.join(drafts)}{' + 심사' if judge_meta else ''})")
    for s in data["sentences"]:
        print(f"  {s['id']} [{s['speaker'][0]}] {s['text']}   ← {','.join(s['emphasis'])}")


if __name__ == "__main__":
    main()
