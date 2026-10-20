#!/usr/bin/env python3
"""음성 검수: audio/{id}.wav 를 faster-whisper로 받아써서 script.json 문장과 대조 → qa/audio.json

사용: python pipeline/qa_audio.py jobs/<id> [--threshold 0.75] [--retry 2] [--engine edge|voicebox]
                                           [--model large-v3-turbo] [--device auto|cuda|cpu]
- 유사도(difflib) < threshold 인 문장은 실패. --retry N 이면 tts.py --force --only 로 재생성 후 재검사.
- edge-tts는 같은 입력이면 거의 같은 결과라 재시도 효과가 작다. 실패해도 표시만 하고 진행.
- 장치: --device auto 면 CUDA(float16) 먼저, 안 되면 CPU(int8). 모델은 첫 실행 때 ~/.cache/huggingface 에 받는다.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "large-v3-turbo"

NUM_WORDS = {"%": "퍼센트", "$": "달러"}
_model = None


def norm(s: str) -> str:
    s = s.lower()
    for k, v in NUM_WORDS.items():
        s = s.replace(k, v)
    s = re.sub(r"[^\w가-힣]", "", s)  # 구두점·공백 제거
    return s


def _preload_cuda_libs() -> None:
    """pip로 깐 nvidia-cublas/cudnn 을 ctranslate2 가 찾도록 미리 dlopen (LD_LIBRARY_PATH 없이)."""
    import ctypes
    import site
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        for so in sorted(Path(sp).glob("nvidia/*/lib/*.so*")):
            try:
                ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def load_model(name: str, device: str):
    global _model
    if _model is not None:
        return _model
    if device in ("auto", "cuda"):
        _preload_cuda_libs()
    from faster_whisper import WhisperModel
    tries = [("cuda", "float16"), ("cpu", "int8")] if device == "auto" else \
            [(device, "float16" if device == "cuda" else "int8")]
    last = None
    for dev, ct in tries:
        try:
            _model = WhisperModel(name, device=dev, compute_type=ct)
            print(f"whisper: {name} on {dev}/{ct}", file=sys.stderr)
            return _model
        except Exception as e:  # CUDA 라이브러리 없음 등 → 다음 후보
            last = e
    sys.exit(f"whisper 모델 로드 실패: {last}")


def transcribe(wav: Path, name: str, device: str) -> str:
    m = load_model(name, device)
    segs, _ = m.transcribe(str(wav), language="ko", beam_size=5, temperature=0, vad_filter=False)
    return "".join(s.text for s in segs).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("--threshold", type=float, default=0.75)
    ap.add_argument("--retry", type=int, default=0)
    ap.add_argument("--engine", default="edge")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    a = ap.parse_args()

    script = json.loads((a.job / "script.json").read_text())
    qa_dir = a.job / "qa"
    qa_dir.mkdir(exist_ok=True)
    results: dict[str, dict] = {}

    for s in script["sentences"]:
        wav = a.job / "audio" / f"{s['id']}.wav"
        best = None
        for attempt in range(a.retry + 1):
            if attempt > 0:
                subprocess.run([sys.executable, str(ROOT / "pipeline" / "tts.py"), str(a.job),
                                "--engine", a.engine, "--force", "--only", s["id"]], check=True,
                               capture_output=True)
            heard = transcribe(wav, a.model, a.device)
            score = difflib.SequenceMatcher(None, norm(s["text"]), norm(heard)).ratio()
            if best is None or score > best["score"]:
                best = {"score": round(score, 3), "heard": heard, "attempts": attempt + 1}
            if score >= a.threshold:
                break
        best["pass"] = best["score"] >= a.threshold
        results[s["id"]] = best
        mark = "ok " if best["pass"] else "FAIL"
        print(f"{mark} {s['id']} {best['score']:.2f}  {s['text'][:28]}  |  {best['heard'][:28]}")

    passed = sum(1 for r in results.values() if r["pass"])
    summary = {"pass": passed == len(results), "passed": passed, "total": len(results),
               "threshold": a.threshold, "sentences": results}
    (qa_dir / "audio.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"→ {qa_dir/'audio.json'}  {passed}/{len(results)} 통과")


if __name__ == "__main__":
    main()
