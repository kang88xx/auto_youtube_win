#!/usr/bin/env python3
"""04 소스: 문장별 이미지 생성 (Magnific Mystic) → assets/{id}.jpg

사용: python pipeline/assets.py jobs/<id> [--candidates 2] [--no-refine] [--no-pick] [--only s01,s02] [--force]
환경: MAGNIFIC_API_KEY (프로젝트 루트 .env 또는 환경변수)

흐름:
  1. 프롬프트 다듬기(claude): 대본 전체를 보고 화풍 한 줄(style)과 문장별 최종 프롬프트(visual_final)를 만든다.
     장면마다 피사체가 다르고, 색·조명은 영상 전체가 한 톤이 되게. 글자·로고·실존 인물은 금지.
  2. 생성: 문장마다 --candidates 장을 동시에 만든다 → assets/cand/{id}_{k}.jpg   (Magnific 1K = 50크레딧/장)
  3. 고르기(claude, 이미지 Read): 문장 뜻·깨진 글자/손/얼굴·세로 구도·자막 자리(하단) 기준으로 1장 선택 → assets/{id}.jpg
script.json 에 style, 문장별 visual_final / asset / asset_pick 을 기록한다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import claude_json, cost_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.magnific.com/v1/ai/mystic"

STYLE_SUFFIX = ", vertical 9:16 composition, no text, no watermark, no letters, no logos"

REFINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["style", "prompts"],
    "properties": {
        "style": {"type": "string", "description": "영상 전체에 공통으로 붙일 화풍 한 줄(영어, 15~30단어): 색감·조명·렌즈·질감"},
        "prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "prompt"],
                "properties": {"id": {"type": "string"}, "prompt": {"type": "string", "description": "영어 25~50단어, 피사체+행동+장소+구도"}},
            },
        },
    },
}

REFINE_PROMPT = """You are the art director for a Korean current-affairs vertical short (1080x1920). Below is the script: one sentence = one full-screen background image, with a large Korean caption in the lower 35% of the frame.

Title: {title}
Topic: {topic}
{style_direction}
Write:
1. style — one line (15-30 words) applied to every image so the video feels like one piece: palette (2-3 colors), lighting, lens/texture, mood. {style_rule}
2. prompts — for every sentence id, a final English prompt (25-50 words): a concrete subject doing something in a concrete place, camera angle, foreground/background. Keep the lower third of the frame visually calm (caption goes there). Each scene must differ in subject or location from its neighbours; do not repeat the same chip/factory/flag three times in a row. When the sentence is abstract (policy, percentages), show a physical stand-in (cargo cranes, a sealed gate, stacked containers, a trading floor screen without readable text).

Hard rules: no text, letters, numbers, logos, flags with text, readable screens; no real people's faces; no gore. Do not mention company names as logos; show objects instead.

Sentences (id | caption | writer's draft visual):
{rows}

Output JSON only."""

PICK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["picks"],
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "choice", "reason"],
                "properties": {"id": {"type": "string"}, "choice": {"type": "integer"}, "reason": {"type": "string"}},
            },
        }
    },
}

PICK_PROMPT = """You are the picture editor for a Korean vertical news short. For each sentence below, open every candidate image with the Read tool, then choose the single best one.

Judge in this order:
1. Reject images with garbled text, fake letters, broken logos, distorted hands/faces, or obvious AI artifacts.
2. Does the picture say what the caption says? A viewer should get the idea before reading.
3. Vertical framing: main subject in the upper/middle area; lower third calm enough for a large caption.
4. Lighting and colour consistent with the other scenes.

{rows}

Return one pick per sentence id (choice = candidate index, 0-based) with a short reason. JSON only."""


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def api(method: str, url: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "x-magnific-api-key": key,
        "x-freepik-api-key": key,  # 구 헤더 이름 호환
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url} → HTTP {e.code}: {e.read().decode()[:500]}")


def generate(prompt: str, key: str, resolution: str, model: str) -> str:
    task = api("POST", API, key, {
        "prompt": prompt,
        "resolution": resolution,
        "aspect_ratio": "social_story_9_16",
        "model": model,
    })["data"]
    tid = task["task_id"]
    for _ in range(120):  # 최대 ~10분
        if task["status"] == "COMPLETED" and task.get("generated"):
            return task["generated"][0]
        if task["status"] == "FAILED":
            raise RuntimeError(f"Magnific task {tid} FAILED: {task}")
        time.sleep(5)
        task = api("GET", f"{API}/{tid}", key)["data"]
    raise TimeoutError(f"Magnific task {tid} 시간 초과")


def gen_to_file(prompt: str, key: str, resolution: str, model: str, out: Path) -> Path:
    """생성 1회 재시도, 내려받기 2회 재시도. 완성된 파일만 out 이름으로 남긴다(.part → os.replace)."""
    part = out.with_suffix(".part")
    last = None
    for _ in range(2):
        try:
            url = generate(prompt, key, resolution, model)  # 50크레딧
        except Exception as e:
            last = e
            time.sleep(3)
            continue
        for _ in range(3):
            try:
                urllib.request.urlretrieve(url, part)  # 링크는 30분 뒤 만료 → 즉시 저장
                if part.stat().st_size < 10_000:
                    raise RuntimeError("내려받은 파일이 너무 작음")
                os.replace(part, out)
                return out
            except Exception as e:
                last = e
                part.unlink(missing_ok=True)
                time.sleep(3)
    raise RuntimeError(f"{out.name}: {last}")


def refine(script: dict, job: Path, model: str | None) -> dict:
    rows = "\n".join(f"{s['id']} | {s['text']} | {s.get('visual', '')}" for s in script["sentences"])
    preset_style = ((script.get("render") or {}).get("image") or {}).get("style")
    if preset_style:
        direction = f"\nArt direction (mandatory, this is the chosen look for the whole video):\n{preset_style}\n"
        rule = "Restate the art direction above as the style line, keeping its medium, palette and lighting; do not switch to another medium. Every prompt must describe the subject in that medium (e.g. 'clay model of…', 'ink sketch of…')."
    else:
        direction, rule = "", "Editorial news-illustration or cinematic photo-real; pick one and keep it."
    data, env = claude_json(REFINE_PROMPT.format(title=script.get("title", ""), topic=script.get("topic", ""), rows=rows,
                                                 style_direction=direction, style_rule=rule),
                            REFINE_SCHEMA, cwd=job, max_turns=6, model=model)
    by_id = {p["id"]: p["prompt"] for p in data["prompts"]}
    script["style"] = preset_style or data["style"]
    script["style_llm"] = data["style"]
    for s in script["sentences"]:
        if s["id"] in by_id:
            s["visual_final"] = by_id[s["id"]]
    print(f"  화풍: {data['style']}  ({(env.get('duration_ms') or 0) / 1000:.0f}s, 환산 ${cost_of(env) or 0:.2f})")
    return script


def pick(script: dict, targets: list[dict], cands: dict[str, list[Path]], job: Path, model: str | None,
         save, batch: int = 6) -> None:
    for i in range(0, len(targets), batch):
        chunk = targets[i:i + batch]
        rows = "\n\n".join(
            f"{s['id']} — caption: {s['text']}\n" + "\n".join(f"  candidate {k}: {p.relative_to(job).as_posix()}" for k, p in enumerate(cands[s['id']]))
            for s in chunk)
        n_img = sum(len(cands[s["id"]]) for s in chunk)
        try:
            data, env = claude_json(PICK_PROMPT.format(rows=rows), PICK_SCHEMA, cwd=job, tools=["Read"],
                                    max_turns=n_img + len(chunk) + 6, model=model)
            picks = {p["id"]: p for p in data["picks"]}
        except Exception as e:  # 고르기 실패 → 첫 장. 크레딧은 이미 썼으니 멈추지 않는다
            print(f"  ! 고르기 실패, 첫 후보 사용: {str(e)[:200]}", file=sys.stderr)
            picks, env = {}, {}
        for s in chunk:
            p = picks.get(s["id"])
            choice = p["choice"] if p and 0 <= p["choice"] < len(cands[s["id"]]) else 0
            shutil.copyfile(cands[s["id"]][choice], job / "assets" / f"{s['id']}.jpg")
            s["asset"] = f"assets/{s['id']}.jpg"
            s["asset_pick"] = {"choice": choice, "of": len(cands[s["id"]]), "reason": (p or {}).get("reason", "")}
            print(f"  {s['id']} ← cand {choice}  {s['asset_pick']['reason'][:70]}")
        save()
        print(f"  (고르기 {len(chunk)}문장 {(env.get('duration_ms') or 0) / 1000:.0f}s, 환산 ${cost_of(env) or 0:.2f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("--force", action="store_true", help="이미지 있어도 다시 생성")
    ap.add_argument("--only", default="")
    ap.add_argument("--candidates", type=int, default=2, help="문장당 후보 수 (1이면 고르기 생략)")
    ap.add_argument("--no-refine", action="store_true", help="프롬프트 다듬기 생략 (visual 그대로)")
    ap.add_argument("--no-pick", action="store_true", help="후보 중 첫 장 사용")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--resolution", default="1k", help="1k | 2k | 4k (1k면 충분)")
    ap.add_argument("--model", default=None, help="realism | fluid | zen | flexible | super_real (기본: script.render.image.model 또는 realism)")
    ap.add_argument("--llm-model", default=None, help="claude -p --model")
    a = ap.parse_args()

    load_env()
    key = os.environ.get("MAGNIFIC_API_KEY")
    if not key:
        sys.exit("MAGNIFIC_API_KEY 가 없습니다. 프로젝트 루트 .env 에 MAGNIFIC_API_KEY=... 추가")

    sp = a.job / "script.json"
    script = json.loads(sp.read_text(encoding="utf-8"))
    if not a.model:
        a.model = ((script.get("render") or {}).get("image") or {}).get("model") or "realism"
    assets = a.job / "assets"
    cand_dir = assets / "cand"
    cand_dir.mkdir(parents=True, exist_ok=True)
    only = {x for x in a.only.split(",") if x}
    save = lambda: sp.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")  # noqa: E731

    targets = [s for s in script["sentences"] if (not only or s["id"] in only) and s.get("visual")]
    todo = [s for s in targets if a.force or not (assets / f"{s['id']}.jpg").exists()]
    for s in targets:
        if s not in todo:
            s["asset"] = f"assets/{s['id']}.jpg"
    if not todo:
        save()
        print(f"→ {sp}  이미지 전부 있음 (다시 만들려면 --force)")
        return

    if not a.no_refine and (a.force or any("visual_final" not in s for s in todo)):
        script = refine(script, a.job, a.llm_model)
        save()

    jobs = []
    for s in todo:
        base = (s.get("visual_final") or s["visual"]) + ", " + script.get("style", "cinematic editorial news illustration, dramatic lighting, high contrast, dark background") + STYLE_SUFFIX
        for k in range(a.candidates):
            out = cand_dir / f"{s['id']}_{k}.jpg"
            if out.exists() and not a.force:
                continue
            jobs.append((s["id"], k, base, out))
    t0 = time.time()
    failed = []
    ex = ThreadPoolExecutor(max_workers=a.workers)
    try:
        futs = {ex.submit(gen_to_file, p, key, a.resolution, a.model, out): (sid, k, out) for sid, k, p, out in jobs}
        for fut in futs:
            sid, k, out = futs[fut]
            try:
                fut.result()
                print(f"  {sid}_{k}  {out.stat().st_size // 1024}KB")
            except Exception as e:
                failed.append(sid)
                print(f"  ! {sid}_{k} 실패: {str(e)[:120]}", file=sys.stderr)
    except KeyboardInterrupt:  # Ctrl-C: 대기 중인 생성(크레딧)은 취소
        ex.shutdown(wait=False, cancel_futures=True)
        raise
    ex.shutdown(wait=True)
    print(f"  생성 {len(jobs)}장 {time.time() - t0:.0f}s  (크레딧 약 {len(jobs) * 50})")

    cands = {s["id"]: sorted(cand_dir.glob(f"{s['id']}_*.jpg")) for s in todo}
    pickable = [s for s in todo if cands[s["id"]]]
    for s in todo:  # 후보가 하나도 없으면 옛 경로를 남기지 않는다 (렌더가 없는 파일을 찾다 죽음)
        if not cands[s["id"]]:
            s["asset"] = None
    if a.candidates > 1 and not a.no_pick:
        pick(script, pickable, cands, a.job, a.llm_model, save)
    else:
        for s in pickable:
            shutil.copyfile(cands[s["id"]][0], assets / f"{s['id']}.jpg")
            s["asset"] = f"assets/{s['id']}.jpg"
    for s in script["sentences"]:  # 최종 계약: asset 은 실제 있는 파일만
        if s.get("asset") and not (a.job / s["asset"]).exists():
            s["asset"] = None
    save()
    n = sum(1 for s in script["sentences"] if s.get("asset"))
    print(f"→ {sp}  소스 있는 문장 {n}/{len(script['sentences'])}" + (f"  실패 {sorted(set(failed))}" if failed else ""))


if __name__ == "__main__":
    main()
