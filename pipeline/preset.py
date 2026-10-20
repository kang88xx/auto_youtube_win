#!/usr/bin/env python3
"""프리셋: 이미지 화풍 + 자막 스타일 + 색 테마 + 목소리를 한 묶음으로. script.json 의 "render" 키에 써 넣는다.

사용: python pipeline/preset.py jobs/<id> <프리셋 이름>      # script.json 에 적용
      python pipeline/preset.py --list                       # 목록
tts.py 는 render.voice, assets.py 는 render.image, Remotion(Root.tsx) 은 render.caption / render.theme 을 읽는다.
프리셋 없이 만든 잡은 전부 기본값(photo-cinematic 화풍, kinetic 자막, InJoon 목소리)으로 돈다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Magnific Mystic model: realism | fluid | zen | flexible | super_real
PRESETS: dict[str, dict] = {
    "photo-cinematic": {
        "image": {"model": "realism", "style": (
            "Cinematic photo-real editorial photography, cool steel-blue and charcoal palette with a single amber accent, "
            "low-key rim lighting, 35mm shallow depth of field, fine film grain, serious documentary mood")},
        "caption": "kinetic",
        "theme": {"accent": "#ff3b57", "bg1": "#0b0d12", "bg2": "#1b2130", "text": "#ffffff"},
        "voice": {"main": "ko-KR-InJoonNeural", "quote": "ko-KR-SunHiNeural", "rate": "+5%", "pitch": "+0Hz"},
    },
    "3d-render": {
        "image": {"model": "fluid", "style": (
            "Glossy stylized 3D render in the style of a modern animated feature, Octane-like soft studio lighting, subsurface "
            "scattering, rounded forms, rich saturated palette of teal, coral and cream, clean backgrounds, slight depth of field")},
        "caption": "boxed",
        "theme": {"accent": "#ff6b4a", "bg1": "#0f1a24", "bg2": "#1d3345", "text": "#fff6ec"},
        "voice": {"main": "ko-KR-SunHiNeural", "quote": "ko-KR-InJoonNeural", "rate": "+8%", "pitch": "+0Hz"},
    },
    "blender-clay": {
        "image": {"model": "fluid", "style": (
            "Low-poly clay diorama rendered in Blender, matte plasticine materials, tiny tilt-shift miniature scenes on a round base, "
            "soft overhead key light with pastel ambient fill, pastel mint, mustard and dusty pink palette, playful but tidy")},
        "caption": "stack",
        "theme": {"accent": "#f2b134", "bg1": "#1a1f2b", "bg2": "#2b3447", "text": "#ffffff"},
        "voice": {"main": "ko-KR-HyunsuMultilingualNeural", "quote": "ko-KR-SunHiNeural", "rate": "+6%", "pitch": "-2Hz"},
    },
    "flat-illustration": {
        "image": {"model": "zen", "style": (
            "Flat vector editorial illustration, bold geometric shapes, no outlines, limited palette of navy, mustard, off-white and "
            "brick red, grain texture overlay, generous negative space, magazine infographic feel")},
        "caption": "minimal",
        "theme": {"accent": "#e8b43a", "bg1": "#101828", "bg2": "#1c2a44", "text": "#fbf7ef"},
        "voice": {"main": "ko-KR-InJoonNeural", "quote": "ko-KR-SunHiNeural", "rate": "+0%", "pitch": "-3Hz"},
    },
    "ink-sketch": {
        "image": {"model": "flexible", "style": (
            "Black ink pen editorial sketch on warm off-white paper, loose cross-hatching, a single red accent wash, visible pen "
            "strokes and ink splatter, newspaper political-cartoon energy, hand-drawn imperfections")},
        "caption": "outline",
        "theme": {"accent": "#d7263d", "bg1": "#f4efe6", "bg2": "#e6dfd2", "text": "#17120e", "dark": False},
        "voice": {"main": "ko-KR-SunHiNeural", "quote": "ko-KR-HyunsuMultilingualNeural", "rate": "+10%", "pitch": "+2Hz"},
    },
    "watercolor": {
        "image": {"model": "flexible", "style": (
            "Loose watercolor painting with fine ink line work, wet-on-wet bleeding edges, cold-press paper texture, muted indigo, "
            "ochre and sage palette with white paper showing through, contemplative editorial mood")},
        "caption": "glass",
        "theme": {"accent": "#2f6f8f", "bg1": "#0e1620", "bg2": "#1a2836", "text": "#f6f1e7"},
        "voice": {"main": "ko-KR-HyunsuMultilingualNeural", "quote": "ko-KR-SunHiNeural", "rate": "+2%", "pitch": "+0Hz"},
    },
    "isometric": {
        "image": {"model": "fluid", "style": (
            "Isometric miniature world, 30-degree isometric camera, clean 3D infographic look, crisp edges, soft ambient occlusion, "
            "palette of slate blue, lime and white, tiny vehicles and buildings, explanatory diagram feel without any labels")},
        "caption": "lowerthird",
        "theme": {"accent": "#9ee037", "bg1": "#0d1320", "bg2": "#18233a", "text": "#ffffff"},
        "voice": {"main": "ko-KR-InJoonNeural", "quote": "ko-KR-SunHiNeural", "rate": "+12%", "pitch": "+0Hz"},
    },
    "neon-cyber": {
        "image": {"model": "realism", "style": (
            "Neon cyberpunk night scene, rain-wet surfaces reflecting magenta and cyan light, volumetric fog, holographic glows "
            "without readable symbols, anamorphic lens flares, deep black shadows, high contrast")},
        "caption": "karaoke",
        "theme": {"accent": "#ff2fd2", "bg1": "#05030c", "bg2": "#160b2e", "text": "#e9fbff"},
        "voice": {"main": "ko-KR-SunHiNeural", "quote": "ko-KR-InJoonNeural", "rate": "+6%", "pitch": "-2Hz"},
    },
    "paper-cutout": {
        "image": {"model": "zen", "style": (
            "Layered paper-cut collage, stacked colored card stock with soft drop shadows between layers, visible paper fibre texture, "
            "warm palette of terracotta, cream, forest green and sky blue, handcrafted diorama depth")},
        "caption": "typewriter",
        "theme": {"accent": "#c9502b", "bg1": "#1b1714", "bg2": "#2e2722", "text": "#fff3e3"},
        "voice": {"main": "ko-KR-HyunsuMultilingualNeural", "quote": "ko-KR-SunHiNeural", "rate": "+0%", "pitch": "+3Hz"},
    },
    "retro-halftone": {
        "image": {"model": "zen", "style": (
            "1960s newsprint halftone poster, two-colour risograph print in navy and vermilion on cream paper, coarse dot screens, "
            "slight misregistration, mid-century editorial graphic style, bold silhouettes")},
        "caption": "ticker",
        "theme": {"accent": "#e3452b", "bg1": "#f3ead8", "bg2": "#e4d8bf", "text": "#1d2a4a", "dark": False},
        "voice": {"main": "ko-KR-InJoonNeural", "quote": "ko-KR-SunHiNeural", "rate": "+4%", "pitch": "-4Hz"},
    },
}


def apply(job: Path, name: str) -> dict:
    if name not in PRESETS:
        sys.exit(f"모르는 프리셋: {name}. 목록: {', '.join(PRESETS)}")
    sp = job / "script.json"
    script = json.loads(sp.read_text(encoding="utf-8"))
    script["render"] = {"preset": name, **json.loads(json.dumps(PRESETS[name]))}
    sp.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    return script["render"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path, nargs="?")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.job:
        for k, v in PRESETS.items():
            print(f"{k:18} 자막 {v['caption']:10} 모델 {v['image']['model']:8} 목소리 {v['voice']['main'].split('-')[2][:-6]} {v['voice']['rate']}")
        return
    r = apply(a.job, a.name)
    print(f"→ {a.job / 'script.json'}  render.preset={a.name}  자막 {r['caption']}, 모델 {r['image']['model']}, 목소리 {r['voice']['main']}")


if __name__ == "__main__":
    main()
