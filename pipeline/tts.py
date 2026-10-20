#!/usr/bin/env python3
"""03 음성: script.json → audio/{id}.wav + audio/durations.json

엔진 선택 (--engine):
  edge     edge-tts (기본값, 네트워크 필요, 즉시 사용 가능)
  voicebox 로컬 Voicebox 서버 (http://127.0.0.1:17493) — 내 목소리 클로닝

사용: python pipeline/tts.py jobs/_sample [--engine edge] [--force]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

VOICES_EDGE = {"main": "ko-KR-InJoonNeural", "quote": "ko-KR-SunHiNeural"}
ROOT = Path(__file__).resolve().parent.parent
# ffmpeg: 프로젝트 tools/bin (setup.sh가 받아 둔 정적 빌드) 우선, 없으면 PATH
FFMPEG = str(ROOT / "tools/bin/ffmpeg") if (ROOT / "tools/bin/ffmpeg").exists() else "ffmpeg"
FFPROBE = str(ROOT / "tools/bin/ffprobe") if (ROOT / "tools/bin/ffprobe").exists() else "ffprobe"


def _voicebox_url() -> str:
    """VOICEBOX_URL 환경변수 > 127.0.0.1 > WSL 호스트(윈도우) IP 순으로 살아있는 서버를 고른다."""
    import urllib.request
    if os.environ.get("VOICEBOX_URL"):
        return os.environ["VOICEBOX_URL"].rstrip("/")
    hosts = ["127.0.0.1"]
    try:  # WSL2 NAT 모드: 윈도우 호스트는 resolv.conf 의 nameserver
        for line in Path("/etc/resolv.conf").read_text().splitlines():
            if line.startswith("nameserver"):
                hosts.append(line.split()[1])
    except OSError:
        pass
    for h in hosts:
        url = f"http://{h}:17493"
        try:
            urllib.request.urlopen(url + "/health", timeout=2)
            return url
        except Exception:
            continue
    return "http://127.0.0.1:17493"



def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return round(float(out), 3)


def to_wav(src: Path, dst: Path) -> None:
    # 앞뒤 무음 제거 + 44.1kHz 모노 wav
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
         "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
                "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse",
         "-ar", "44100", "-ac", "1", str(dst)],
        check=True,
    )


async def edge_one(text: str, voice: str, out_mp3: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="+5%").save(str(out_mp3))


def voicebox_one(text: str, speaker: str, out: Path) -> None:
    import urllib.request
    VOICEBOX_URL = _voicebox_url()
    profile = os.environ.get(f"VOICEBOX_PROFILE_{speaker.upper()}") or os.environ.get("VOICEBOX_PROFILE")
    if not profile:
        sys.exit("VOICEBOX_PROFILE 환경변수(프로필 id)가 필요합니다. GET /profiles 로 확인.")
    body = json.dumps({"text": text, "profile_id": profile, "language": "ko"}).encode()
    req = urllib.request.Request(f"{VOICEBOX_URL}/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
    if ctype.startswith("application/json"):
        # 서버가 파일 경로/URL을 돌려주는 경우를 대비
        info = json.loads(data)
        url = info.get("audio_url") or info.get("url")
        if not url:
            raise RuntimeError(f"Voicebox 응답 해석 실패: {info}")
        if url.startswith("/"):
            url = VOICEBOX_URL + url
        data = urllib.request.urlopen(url, timeout=600).read()
    out.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("--engine", choices=["edge", "voicebox"], default="edge")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default="", help="쉼표로 구분한 문장 id (예: s03,s07)")
    a = ap.parse_args()
    only = {x for x in a.only.split(",") if x}

    script = json.loads((a.job / "script.json").read_text())
    audio_dir = a.job / "audio"
    audio_dir.mkdir(exist_ok=True)
    dur_path = audio_dir / "durations.json"
    durations = json.loads(dur_path.read_text()) if dur_path.exists() else {}

    for s in script["sentences"]:
        if only and s["id"] not in only:
            continue
        wav = audio_dir / f"{s['id']}.wav"
        if wav.exists() and not a.force and s["id"] in durations:
            continue
        raw = audio_dir / f"{s['id']}.raw"
        if a.engine == "edge":
            asyncio.run(edge_one(s["text"], VOICES_EDGE[s.get("speaker", "main")], raw))
        else:
            voicebox_one(s["text"], s.get("speaker", "main"), raw)
        to_wav(raw, wav)
        raw.unlink()
        durations[s["id"]] = ffprobe_duration(wav)
        print(f"{s['id']}  {durations[s['id']]:5.2f}s  {s['text'][:40]}")

    dur_path.write_text(json.dumps(durations, ensure_ascii=False, indent=2))
    total = sum(durations.values())
    print(f"→ {dur_path}  문장 {len(durations)}개, 발화 합계 {total:.1f}s")


if __name__ == "__main__":
    main()
