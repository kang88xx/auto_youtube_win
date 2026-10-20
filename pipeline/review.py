#!/usr/bin/env python3
"""02b 대본 검수: script.json 을 다른 호출이 사실·문장 규칙·훅·emphasis 기준으로 검사하고 고친다.

사용: python pipeline/review.py jobs/<id> [--force]
- 근거: research/raw/*.md (있으면). 자료에 없는 숫자·인용은 지적하고 고친다.
- 결과: script.json 덮어씀 (원본은 drafts/pre-review.json), 보고서는 qa/script.json
- 이미 qa/script.json 이 있으면 건너뜀 (--force 로 다시).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import claude_json, cost_of, validate_script  # noqa: E402
from script import RULES, SCHEMA, load_research, normalize  # noqa: E402

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "verdict", "issues", "script"],
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100, "description": "고치기 전 대본 점수"},
        "verdict": {"type": "string", "description": "한 줄 총평"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "kind", "before", "after", "reason"],
                "properties": {
                    "id": {"type": "string", "description": "문장 id 또는 'meta'"},
                    "kind": {"type": "string", "enum": ["fact", "length", "tone", "hook", "flow", "emphasis", "visual", "quote", "meta"]},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "script": SCHEMA,
    },
}

PROMPT = """당신은 한국 시사 쇼츠 채널의 데스크(최종 검수자)다. 아래 대본을 검수하고 고친 완성본을 돌려준다.

주제: {topic}
오늘: {today}

{source_rule}

검수 항목 (발견하면 issues 에 하나씩 적고 script 에 반영):
- fact: 근거 자료와 다르거나 자료에 없는 숫자·날짜·주체·인용. 자료에 없으면 빼거나 자료에 있는 사실로 바꾼다. 절대 새 숫자를 만들지 않는다.
- quote: speaker="quote" 인데 실제 발언이 아니거나 15자를 넘는 것.
- length: 35자 초과, 또는 12자 미만으로 정보가 빈 문장. 쪼개거나 합친다.
- tone: 번역투·문어체("~에 대해", "~것으로 알려졌다", "~하였다"). 말하듯이 고친다.
- hook: 첫 문장이 장면·숫자·반전 없이 밋밋하면 다시 쓴다. hook 필드도 같이 바꾼다.
- flow: 시간 순서가 꼬이거나 인과 접속("그런데/그래서/문제는")이 빠져 끊기는 곳. 같은 정보가 두 번 나오는 곳.
- emphasis: text 안에 없는 문자열, 또는 가장 중요한 어절(숫자 있으면 숫자 어절)이 아닌 것.
- visual: 글자·로고·실존 인물 얼굴을 요구하거나, 장면이 모호한 프롬프트.
- meta: titles(25자 이내, 숫자·반전), description(출처 URL 포함), tags(8~12개), title(12자 이내).

문제가 없는 문장은 그대로 둔다. 고칠 땐 아래 규칙을 지킨다.

{rules}

----- 대본 -----
{script}

score 는 고치기 전 대본의 점수(0~100). JSON만 출력한다."""

SOURCE_RESEARCH = """근거 자료 (사실 판단의 유일한 기준):
-----
{research}
-----"""
SOURCE_NONE = """근거 자료 없음. 일반 상식과 어긋나는 숫자·날짜만 fact 로 지적하고, 확신이 없으면 '약'을 붙이거나 숫자를 뺀다."""
SOURCE_WEB = """근거 자료: 이 대본은 작가가 WebSearch 로 기사를 확인하며 썼다(자료 파일 없음). 숫자·날짜·인용이 의심스러우면 WebSearch/WebFetch 로 직접 확인하고, 확인되면 그대로 두고 틀렸을 때만 fact 로 고친다. 확인 못 한 것은 '약'을 붙인다. 확인한 URL 은 description 에 남긴다."""


def _sha(path: Path) -> str:
    """대본 본문(스키마 키)만의 해시. render/style 같은 뒤 공정 키가 바뀌어도 다시 검수하지 않는다."""
    d = json.loads(path.read_text(encoding="utf-8"))
    body = {k: d.get(k) for k in SCHEMA["properties"]}
    body["sentences"] = [{k: v for k, v in s.items() if k in ("id", "text", "speaker", "emphasis", "visual")}
                         for s in (body.get("sentences") or []) if isinstance(s, dict)]
    return hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def relink(job: Path, old: list[dict], new: list[dict]) -> None:
    """검수로 문장이 쪼개지거나 합쳐져 id 가 밀리면, 본문이 그대로인 문장의 이미지·후보·음성을 새 id 로 옮기고
    본문이 바뀐 문장의 옛 파일은 지운다. (tts·assets 는 '파일이 있으면 건너뜀'이라 이걸 안 하면 엉뚱한 음성·그림이 붙는다)"""
    assets, cand, audio = job / "assets", job / "assets" / "cand", job / "audio"
    dur_p = audio / "durations.json"
    durations = json.loads(dur_p.read_text(encoding="utf-8")) if dur_p.exists() else {}
    old_by_text = {s["text"]: s for s in old}
    moves = []  # (old_id, new_id)
    for s in new:
        o = old_by_text.get(s["text"])
        if o:
            moves.append((o["id"], s["id"]))
    kept_old = {o for o, _ in moves}

    def files_of(sid: str) -> list[Path]:
        return [p for p in [assets / f"{sid}.jpg", audio / f"{sid}.wav"] if p.exists()] + sorted(cand.glob(f"{sid}_*.jpg")) if cand.exists() else \
               [p for p in [assets / f"{sid}.jpg", audio / f"{sid}.wav"] if p.exists()]

    # 1) 본문이 바뀐 옛 문장의 파일 삭제
    new_durations = {}
    for o in old:
        if o["id"] not in kept_old:
            for f in files_of(o["id"]):
                f.unlink()
    # 2) 두 단계 이동 (s05→s06, s06→s07 같은 연쇄 충돌 방지)
    staged = []
    for o_id, n_id in moves:
        for f in files_of(o_id):
            tmp = f.with_name("__mv__" + f.name)
            f.rename(tmp)
            staged.append((tmp, f.name.replace(o_id, n_id, 1)))
        if o_id in durations:
            new_durations[n_id] = durations[o_id]
    for tmp, name in staged:
        tmp.rename(tmp.with_name(name))
    if dur_p.exists() or new_durations:
        audio.mkdir(exist_ok=True)
        dur_p.write_text(json.dumps(new_durations, ensure_ascii=False, indent=2), encoding="utf-8")
    qa = job / "qa" / "audio.json"
    if qa.exists() and moves != [(s["id"], s["id"]) for s in new]:
        qa.unlink()  # 음성 검수 결과는 id 기준이라 다시 받아야 한다


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()

    sp = a.job / "script.json"
    report_path = a.job / "qa" / "script.json"
    cur_sha = _sha(sp)
    if report_path.exists() and not a.force:
        try:
            if json.loads(report_path.read_text(encoding="utf-8")).get("sha_after") == cur_sha:
                print(f"→ {report_path} 있음, script.json 변동 없음 (건너뜀, --force 로 다시)")
                return
        except Exception:
            pass
    script = json.loads(sp.read_text(encoding="utf-8"))
    topic = script.get("topic", "")
    research = load_research(a.job, None)
    bp = a.job / "brief.json"
    brief = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else {}
    tools: list[str] = []
    if research:
        source_rule = SOURCE_RESEARCH.format(research=research)
    elif brief.get("source") == "web":
        source_rule, tools = SOURCE_WEB, ["WebSearch", "WebFetch"]
    else:
        source_rule = SOURCE_NONE
    body = copy.deepcopy({k: v for k, v in script.items() if k in SCHEMA["properties"]})
    for s in body["sentences"]:
        s.pop("asset", None)
    prompt = PROMPT.format(topic=topic, today=date.today().isoformat(), source_rule=source_rule, rules=RULES,
                           script=json.dumps(body, ensure_ascii=False, indent=1))
    data, env = claude_json(prompt, REVIEW_SCHEMA, cwd=a.job, tools=tools, max_turns=30 if tools else 10, model=a.model)

    fixed = normalize(data["script"], topic)  # validate 포함
    pre = a.job / "drafts" / "pre-review.json"
    pre.parent.mkdir(exist_ok=True)
    if not pre.exists():  # 원본은 한 번만 보관
        pre.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    # 뒤 공정이 붙인 것 보존: render(프리셋)·style·created 등 스키마 밖 최상위 키 전부, 그리고
    # 본문·visual 이 그대로인 문장의 다듬은 프롬프트·선택 기록·이미지
    for k, v in script.items():
        if k not in SCHEMA["properties"] and k not in fixed:
            fixed[k] = v
    if "created" in script:
        fixed["created"] = script["created"]
    old_by_text = {s["text"]: s for s in script["sentences"]}
    for s in fixed["sentences"]:
        o = old_by_text.get(s["text"])
        if o and o.get("visual") == s.get("visual"):
            for k in ("visual_final", "asset_pick"):
                if k in o:
                    s[k] = o[k]
        s["asset"] = f"assets/{s['id']}.jpg" if (o and o.get("asset")) else None
    relink(a.job, script["sentences"], fixed["sentences"])
    for s in fixed["sentences"]:
        if s["asset"] and not (a.job / s["asset"]).exists():
            s["asset"] = None
    sp.write_text(json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {"score": data["score"], "verdict": data["verdict"], "issues": data["issues"],
              "n_before": len(script["sentences"]), "n_after": len(fixed["sentences"]),
              "sha_before": cur_sha, "sha_after": _sha(sp),
              "cost_usd": cost_of(env), "duration_ms": env.get("duration_ms")}
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if bp.exists():
        brief.update({"titles": fixed["titles"], "description": fixed["description"], "tags": fixed["tags"],
                      "review": {"score": data["score"], "issues": len(data["issues"]), "cost_usd": cost_of(env)}})
        bp.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"→ {report_path}  점수 {data['score']}/100, 지적 {len(data['issues'])}건, "
          f"문장 {report['n_before']}→{report['n_after']}개  ({(env.get('duration_ms') or 0) / 1000:.0f}s)")
    print(f"  총평: {data['verdict']}")
    for i in data["issues"]:
        print(f"  [{i['kind']}] {i['id']}: {i['before'][:40]} → {i['after'][:40]}  ({i['reason'][:60]})")


if __name__ == "__main__":
    main()
