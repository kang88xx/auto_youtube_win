import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Caption, CaptionStyle, showsCards } from "./captions";
import { F, fontsReady } from "./fonts";
import { ShortsProps, Theme, buildTimeline, defaultTheme } from "./types";

const displayFont = F.blackHan;
const bodyFont = F.pretendard;

const W = 1080;

// ---------- 숫자 파싱: "5조", "70%", "1년짜리", "3%" ----------
const NUM_RE = /(\d+(?:[.,]\d+)?)\s*(조|억|만|천|%|년|개월|개|월|일|달러|원|배|명|위|시간|분|포인트|p)?/;
// 강조 어절에 숫자가 있으면 그것을, 없으면 문장의 첫 숫자를 카드로 띄운다 ("19일까지 28% 빠졌고" + 강조 "28%" → 28%)
const parseNumber = (text: string, emphasis?: string[]) => {
  const e = (emphasis ?? []).find((x) => /\d/.test(x));
  const m = (e ? e.match(NUM_RE) : null) ?? text.match(NUM_RE);
  if (!m) return null;
  // 단위가 없는 숫자는 강조 어절에 든 것만 카드로 ("19세기", "s01" 같은 건 통계가 아니다)
  if (!m[2] && !e) return null;
  const value = parseFloat(m[1].replace(/,/g, ""));
  if (Number.isNaN(value)) return null;
  return { value, unit: m[2] ?? "", raw: m[1] };
};

// ---------- 배경 (소스 없을 때) ----------
const ShapesBackground: React.FC<{ theme: Theme }> = ({ theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${theme.bg2} 0%, ${theme.bg1} 70%)` }}>
      {[0, 1, 2, 3].map((i) => {
        const size = 420 + i * 160;
        const x = 200 + Math.sin(t / (4 + i) + i) * 260 + i * 120;
        const y = 500 + Math.cos(t / (5 + i) + i * 2) * 300 + i * 220;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              width: size,
              height: size,
              left: x - size / 2,
              top: y - size / 2,
              borderRadius: "50%",
              border: `2px solid ${theme.accent}`,
              opacity: 0.12 - i * 0.02,
              transform: `rotate(${t * (6 + i * 3)}deg)`,
            }}
          />
        );
      })}
      <div
        style={{
          position: "absolute",
          width: 1400,
          height: 1400,
          borderRadius: "50%",
          left: -300 + Math.sin(t / 6) * 80,
          top: 600,
          background: `radial-gradient(circle, ${theme.accent}40 0%, transparent 60%)`,
          filter: "blur(40px)",
        }}
      />
    </AbsoluteFill>
  );
};

// ---------- 전체 배경 소스 (이미지/영상) + 어둡게 ----------
const isVideo = (p: string) => /\.(mp4|mov|webm|m4v)$/i.test(p);

const MediaBackground: React.FC<{ src: string; durFrames: number; idx: number; light: boolean }> = ({
  src,
  durFrames,
  idx,
  light,
}) => {
  const frame = useCurrentFrame();
  const fade = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  const scale = interpolate(frame, [0, durFrames], idx % 2 ? [1.12, 1.0] : [1.0, 1.12]);
  const pan = interpolate(frame, [0, durFrames], [0, idx % 2 ? -30 : 30]);
  return (
    <AbsoluteFill style={{ opacity: fade, background: light ? "#f4efe6" : "#000" }}>
      <AbsoluteFill style={{ transform: `scale(${scale}) translateX(${pan}px)` }}>
        {isVideo(src) ? (
          <OffthreadVideo src={src} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <Img src={src} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        )}
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          background: light
            ? "linear-gradient(180deg, rgba(255,250,240,0.35) 0%, rgba(255,250,240,0.0) 25%, rgba(255,250,240,0.05) 50%, rgba(255,250,240,0.55) 78%, rgba(255,250,240,0.7) 100%)"
            : "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.05) 25%, rgba(0,0,0,0.15) 50%, rgba(0,0,0,0.82) 78%, rgba(0,0,0,0.9) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

// ---------- 상단: 로고 자리(엑스박스) + 채널 이름 자리(박스) + 진행바 ----------
// 테스트 단계: 실제 로고·채널명이 정해지면 이 두 자리만 교체한다.
const TopBar: React.FC<{ theme: Theme }> = ({ theme }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const p = frame / durationInFrames;
  const logo = 88;
  const c = theme.dark === false ? "rgba(20,16,12,0.7)" : "rgba(255,255,255,0.75)";
  return (
    <>
      <div style={{ position: "absolute", top: 0, left: 0, height: 10, width: W * p, background: theme.accent }} />
      <div
        style={{
          position: "absolute",
          top: 96,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: 20,
        }}
      >
        <svg width={logo} height={logo} viewBox={`0 0 ${logo} ${logo}`}>
          <rect x={2} y={2} width={logo - 4} height={logo - 4} rx={14} fill="none" stroke={c} strokeWidth={3} strokeDasharray="10 8" />
          <line x1={16} y1={16} x2={logo - 16} y2={logo - 16} stroke={c} strokeWidth={3} />
          <line x1={logo - 16} y1={16} x2={16} y2={logo - 16} stroke={c} strokeWidth={3} />
        </svg>
        <div
          style={{
            height: logo,
            minWidth: 360,
            padding: "0 36px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: `3px dashed ${c}`,
            borderRadius: 14,
            fontFamily: bodyFont,
            fontWeight: 700,
            fontSize: 34,
            letterSpacing: 2,
            color: c,
          }}
        >
          채널 이름
        </div>
      </div>
    </>
  );
};

// ---------- 숫자 카운터 카드 ----------
const NumberCard: React.FC<{ value: number; unit: string; raw: string; theme: Theme }> = ({
  value,
  unit,
  raw,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 120 }, durationInFrames: 24 });
  const count = spring({ frame, fps, config: { damping: 30, stiffness: 60, mass: 1.2 }, durationInFrames: 36 });
  const decimals = raw.includes(".") ? raw.split(".")[1].length : 0;
  const isDate = ["년", "월", "일", "시간", "분"].includes(unit) || value >= 1000;
  const shown = isDate ? raw : (value * count).toFixed(decimals);
  return (
    <div
      style={{
        position: "absolute",
        top: 560,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity: enter,
        transform: `translateY(${(1 - enter) * 60}px) scale(${0.85 + 0.15 * enter})`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 10,
          padding: "10px 56px 24px",
          borderRadius: 32,
          background: "rgba(0,0,0,0.45)",
          backdropFilter: "blur(10px)",
          border: `3px solid ${theme.accent}`,
          boxShadow: `0 0 80px ${theme.accent}66`,
        }}
      >
        <span style={{ fontFamily: displayFont, fontSize: 230, lineHeight: 1, color: theme.accent, letterSpacing: -4 }}>
          {shown}
        </span>
        {unit ? (
          <span style={{ fontFamily: displayFont, fontSize: 120, lineHeight: 1, color: "#fff" }}>{unit}</span>
        ) : null}
      </div>
    </div>
  );
};

// ---------- 키워드 카드 (숫자 없는 문장) ----------
// "업그레이드가" → "업그레이드" : 카드에 띄울 때만 끝 조사 제거
const stripParticle = (w: string) =>
  w.replace(/[,.!?"'”’)]+$/g, "").replace(/(이었죠|였죠|입니다|이에요|에요|으로|에서|까지|부터|처럼|조차|마저|은|는|이|가|을|를|의|도|에|로|과|와|만)$/, "");

const KeywordCard: React.FC<{ word: string; theme: Theme }> = ({ word: rawWord, theme }) => {
  const word = stripParticle(rawWord) || rawWord;
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 6, fps, config: { damping: 14, stiffness: 140 }, durationInFrames: 22 });
  return (
    <div
      style={{
        position: "absolute",
        top: 640,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity: enter,
        transform: `translateX(${(1 - enter) * -80}px) rotate(-3deg)`,
      }}
    >
      <div
        style={{
          padding: "14px 48px 22px",
          background: theme.accent,
          color: "#fff",
          fontFamily: displayFont,
          fontSize: 104,
          lineHeight: 1.1,
          borderRadius: 18,
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          wordBreak: "keep-all",
          maxWidth: W - 160,
          textAlign: "center",
        }}
      >
        {word}
      </div>
    </div>
  );
};

// ---------- 본체 ----------
export const Shorts: React.FC<ShortsProps> = ({ jobId, script, durations, theme: themeOverride, caption }) => {
  const { fps } = useVideoConfig();
  const [fontHandle] = React.useState(() => delayRender("fonts"));
  React.useEffect(() => {
    fontsReady.then(() => continueRender(fontHandle));
  }, [fontHandle]);
  const theme: Theme = { ...defaultTheme, ...(script?.render?.theme ?? {}), ...(themeOverride ?? {}) };
  const captionStyle: CaptionStyle = caption ?? script?.render?.caption ?? "kinetic";
  const cards = showsCards(captionStyle);
  const light = theme.dark === false;
  if (!script || !durations) {
    return (
      <AbsoluteFill style={{ background: "#000", color: "#fff", fontSize: 40, padding: 80 }}>
        script.json / durations.json 없음: jobs/{jobId}
      </AbsoluteFill>
    );
  }
  const tl = buildTimeline(script, durations, fps, theme.gapSec);
  const base = `jobs/${jobId}`;

  return (
    <AbsoluteFill style={{ background: theme.bg1 }}>
      {tl.map((item, idx) => {
        const s = item.sentence;
        const assetSrc = s.asset ? staticFile(`${base}/${s.asset}`) : null;
        const num = cards ? parseNumber(s.text, s.emphasis) : null;
        const keyword = cards && !num && s.emphasis && s.emphasis.length > 0 ? s.emphasis[0] : null;
        return (
          <Sequence
            key={item.id}
            from={item.startFrame}
            durationInFrames={item.durFrames + Math.round(theme.gapSec * fps)}
            name={`${item.id} ${s.text.slice(0, 18)}`}
          >
            {assetSrc ? (
              <MediaBackground src={assetSrc} durFrames={item.durFrames} idx={idx} light={light} />
            ) : (
              <ShapesBackground theme={theme} />
            )}
            <Audio src={staticFile(`${base}/audio/${item.id}.wav`)} />
            {num ? <NumberCard value={num.value} unit={num.unit} raw={num.raw} theme={theme} /> : null}
            {keyword ? <KeywordCard word={keyword} theme={theme} /> : null}
            <Caption style={captionStyle} sentence={s} durFrames={item.durFrames} theme={theme} isHook={idx === 0} title={script.title} />
          </Sequence>
        );
      })}
      <TopBar theme={theme} />
    </AbsoluteFill>
  );
};
