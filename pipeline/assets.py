#!/usr/bin/env python3
"""04 소스: script.json의 문장별 visual 프롬프트로 Magnific(Mystic) 이미지 생성 → assets/{id}.jpg

사용: python pipeline/assets.py jobs/_sample [--force] [--only s01,s02]
환경: MAGNIFIC_API_KEY (프로젝트 루트 .env 또는 환경변수)

script.json 문장 필드:
  "visual": "영어 프롬프트"   → 이 문장에 이미지 생성. 없으면 건너뜀(텍스트 전용 장면).
생성 후 script.json의 "asset" 을 "assets/{id}.jpg" 로 채운다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.magnific.com/v1/ai/mystic"

STYLE_SUFFIX = (
    ", cinematic editorial news illustration, dramatic lighting, high contrast, "
    "dark background, vertical composition, no text, no watermark, no letters"
)


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
        sys.exit(f"{method} {url} → HTTP {e.code}: {e.read().decode()[:500]}")


def generate(prompt: str, key: str, resolution: str, model: str) -> str:
    task = api("POST", API, key, {
        "prompt": prompt + STYLE_SUFFIX,
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--resolution", default="1k", help="1k | 2k | 4k (1k면 충분, 비용 최소)")
    ap.add_argument("--model", default="realism", help="realism | fluid | zen | flexible | super_real")
    a = ap.parse_args()

    load_env()
    key = os.environ.get("MAGNIFIC_API_KEY")
    if not key:
        sys.exit("MAGNIFIC_API_KEY 가 없습니다. 프로젝트 루트 .env 에 MAGNIFIC_API_KEY=... 추가")

    sp = a.job / "script.json"
    script = json.loads(sp.read_text())
    assets = a.job / "assets"
    assets.mkdir(exist_ok=True)
    only = {x for x in a.only.split(",") if x}

    for s in script["sentences"]:
        if only and s["id"] not in only:
            continue
        prompt = s.get("visual")
        if not prompt:
            continue
        out = assets / f"{s['id']}.jpg"
        if out.exists() and not a.force:
            s["asset"] = f"assets/{out.name}"
            continue
        t0 = time.time()
        url = generate(prompt, key, a.resolution, a.model)
        urllib.request.urlretrieve(url, out)  # 링크는 30분 뒤 만료 → 즉시 저장
        s["asset"] = f"assets/{out.name}"
        print(f"{s['id']}  {time.time()-t0:4.0f}s  {out.stat().st_size//1024}KB  {prompt[:50]}")
        sp.write_text(json.dumps(script, ensure_ascii=False, indent=2))  # 중간 저장

    sp.write_text(json.dumps(script, ensure_ascii=False, indent=2))
    n = sum(1 for s in script["sentences"] if s.get("asset"))
    print(f"→ {sp}  소스 있는 문장 {n}/{len(script['sentences'])}")


if __name__ == "__main__":
    main()
