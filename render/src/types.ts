// script.json / durations.json / assets 계약. 파이프라인 전체의 공통 키는 Sentence.id.

export type Speaker = "main" | "quote";

export type Sentence = {
  id: string; // "s01"
  text: string;
  speaker: Speaker;
  asset: string | null; // 잡 폴더 기준 상대경로, 예: "assets/s07.mp4"
  emphasis?: string[]; // 강조할 어절(text 안에 그대로 포함되는 문자열)
};

export type RenderConfig = {
  preset?: string;
  caption?: import("./captions").CaptionStyle; // 자막 스타일 (captions.tsx)
  theme?: Partial<Theme>;
};

export type Script = {
  title: string; // 영상 상단에 작게 노출되는 주제/채널 라벨
  hook?: string; // 첫 1초 훅 (없으면 첫 문장 사용)
  sentences: Sentence[];
  render?: RenderConfig; // preset.py 가 씀
};

// durations.json: { "s01": 3.21, ... } (초)
export type Durations = Record<string, number>;

export type ShortsProps = {
  jobId: string;
  // calculateMetadata가 채움
  script?: Script;
  durations?: Durations;
  // 스타일 노브 (props로 열어 둠; script.render 보다 우선)
  theme?: Partial<Theme>;
  caption?: import("./captions").CaptionStyle;
};

export type Theme = {
  bg1: string;
  bg2: string;
  accent: string;
  text: string;
  muted: string;
  dark?: boolean; // false 면 밝은 배경(잉크 스케치·신문 느낌) 기준으로 자막·오버레이 색을 잡는다
  gapSec: number; // 문장 사이 무음
  assetHeightRatio: number; // 소스가 있을 때 상단 미디어 영역 비율
};

export const defaultTheme: Theme = {
  bg1: "#0b0d12",
  bg2: "#1b2130",
  accent: "#ff3b57",
  text: "#ffffff",
  muted: "#9aa3b2",
  gapSec: 0.18,
  assetHeightRatio: 0.52,
};

export type Timeline = {
  id: string;
  startSec: number;
  durSec: number;
  startFrame: number;
  durFrames: number;
  sentence: Sentence;
}[];

export const buildTimeline = (
  script: Script,
  durations: Durations,
  fps: number,
  gapSec: number,
): Timeline => {
  let t = 0.4; // 첫 문장 앞 짧은 여백
  return script.sentences.map((s) => {
    const dur = durations[s.id] ?? 2.5;
    const item = {
      id: s.id,
      startSec: t,
      durSec: dur,
      startFrame: Math.round(t * fps),
      durFrames: Math.max(1, Math.round(dur * fps)),
      sentence: s,
    };
    t += dur + gapSec;
    return item;
  });
};

export const totalSeconds = (tl: Timeline, gapSec: number) => {
  if (tl.length === 0) return 3;
  const last = tl[tl.length - 1];
  return last.startSec + last.durSec + gapSec + 0.8; // 끝 여백
};
