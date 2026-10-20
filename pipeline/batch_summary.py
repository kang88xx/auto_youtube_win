#!/usr/bin/env python3
"""배치 결과 요약표(markdown). 사용: python pipeline/batch_summary.py plan.json"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FFPROBE = ROOT / "tools/bin/ffprobe"


def dur(p: Path) -> str:
    if not p.exists():
        return "-"
    try:
        out = subprocess.run([str(FFPROBE), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                             capture_output=True, text=True, check=True).stdout.strip()
        return f"{float(out):.0f}s"
    except Exception:
        return "?"


def main() -> None:
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print("# 스타일 비교 배치\n")
    print("| # | 잡 | 프리셋 | 화풍(모델) | 자막 | 목소리 | 길이 | 문장 | 검수점수 | 주제 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, p in enumerate(plan, 1):
        job = ROOT / "jobs" / p["id"]
        sp = job / "script.json"
        s = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
        r = s.get("render") or {}
        qa = job / "qa" / "script.json"
        score = json.loads(qa.read_text(encoding="utf-8")).get("score", "-") if qa.exists() else "-"
        v = r.get("voice", {})
        voice = f"{v.get('main', '').replace('ko-KR-', '').replace('Neural', '')} {v.get('rate', '')}"
        print(f"| {i} | `jobs/{p['id']}` | {p['preset']} | {r.get('image', {}).get('model', '-')} | {r.get('caption', '-')} | {voice} | "
              f"{dur(job / 'render' / 'final.mp4')} | {len(s.get('sentences', []))} | {score} | {p['topic']} |")
    print("\n각 잡 폴더: `render/final.mp4`(영상), `render/thumb.png`(썸네일), `assets/cand/`(탈락 후보 포함 전체 이미지), "
          "`drafts/`(claude·codex 초안과 심사 메모), `qa/script.json`(검수 지적), `research/raw/`(근거 기사).")


if __name__ == "__main__":
    main()
