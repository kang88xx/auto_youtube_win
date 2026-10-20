// 자막 스타일 10종. script.json render.caption 으로 고른다 (preset.py). 기본은 "kinetic".
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { F } from "./fonts";
import { Sentence, Theme } from "./types";

export type CaptionStyle =
  | "kinetic" // 단어가 하나씩 튀어오름 (기본)
  | "boxed" // 줄마다 단색 박스
  | "karaoke" // 문장 전체 흐리게 → 말하는 단어부터 밝아짐
  | "typewriter" // 글자 타이핑 + 커서
  | "lowerthird" // 뉴스 하단 바 + 태그
  | "outline" // 큰 제목체 + 두꺼운 외곽선
  | "glass" // 반투명 유리 카드
  | "stack" // 단어를 줄줄이 쌓는 포스터형
  | "minimal" // 작고 깔끔, 밑줄 하나
  | "ticker"; // 상단 헤드라인 바 + 하단 마커 하이라이트

export const CAPTION_STYLES: CaptionStyle[] = [
  "kinetic", "boxed", "karaoke", "typewriter", "lowerthird", "outline", "glass", "stack", "minimal", "ticker",
];

// 숫자·키워드 카드를 띄울지 (일부 스타일은 자막 자체가 크거나 바가 있어 겹침)
export const showsCards = (s: CaptionStyle) => !["minimal", "lowerthird", "ticker", "stack"].includes(s);

const W = 1080;
const hasDigit = (w: string) => /\d/.test(w);

type P = { sentence: Sentence; durFrames: number; theme: Theme; isHook: boolean; title: string };

const useWords = (sentence: Sentence, durFrames: number) => {
  const words = sentence.text.split(/\s+/).filter(Boolean);
  const emph = sentence.emphasis ?? [];
  const speakFrames = durFrames * 0.85;
  const perWord = speakFrames / Math.max(words.length, 1);
  const isEmph = (w: string) => emph.some((e) => w.includes(e) || e.includes(w));
  return { words, perWord, isEmph };
};

const useExit = (durFrames: number) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [durFrames - 5, durFrames + 2], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
};

const Box: React.FC<{ top: number; height: number; children: React.ReactNode; opacity: number; align?: "center" | "flex-start" }> = ({
  top, height, children, opacity, align = "center",
}) => (
  <div style={{ position: "absolute", top, left: 72, width: W - 144, height, display: "flex", alignItems: "center", justifyContent: align, opacity }}>
    {children}
  </div>
);

const QuoteMark: React.FC<{ theme: Theme }> = ({ theme }) => (
  <div style={{ position: "absolute", top: -40, left: 0, fontFamily: F.blackHan, fontSize: 220, color: theme.accent, opacity: 0.8, lineHeight: 1 }}>“</div>
);

// ---------- 1. kinetic (기존) ----------
const Kinetic: React.FC<P> = ({ sentence, durFrames, theme, isHook }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { words, perWord, isEmph } = useWords(sentence, durFrames);
  const isQuote = sentence.speaker === "quote";
  const fontSize = isHook ? 88 : 74;
  return (
    <Box top={1120} height={560} opacity={useExit(durFrames)}>
      {isQuote ? <QuoteMark theme={theme} /> : null}
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "6px 18px", textAlign: "center", fontFamily: isHook ? F.blackHan : F.pretendard, fontWeight: 900, fontStyle: isQuote ? "italic" : "normal", fontSize, lineHeight: 1.3, color: isQuote ? "#ffe9ec" : theme.text, textShadow: "0 4px 24px rgba(0,0,0,0.9), 0 0 2px rgba(0,0,0,0.9)", wordBreak: "keep-all" }}>
        {words.map((w, i) => {
          const s = spring({ frame: frame - i * perWord, fps, config: { damping: 14, stiffness: 160, mass: 0.6 }, durationInFrames: 14 });
          const num = hasDigit(w);
          return (
            <span key={i} style={{ display: "inline-block", color: isEmph(w) || num ? theme.accent : undefined, opacity: s, transform: `translateY(${(1 - s) * 30}px) scale(${0.8 + 0.2 * s})`, fontFamily: num ? F.blackHan : undefined, fontSize: num ? fontSize * 1.1 : undefined }}>{w}</span>
          );
        })}
      </div>
    </Box>
  );
};

// ---------- 2. boxed: 줄마다 단색 박스 ----------
const Boxed: React.FC<P> = ({ sentence, durFrames, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { words, isEmph } = useWords(sentence, durFrames);
  // 3~4어절씩 줄 나누기
  const lines: string[][] = [];
  words.forEach((w, i) => { if (i % 3 === 0) lines.push([]); lines[lines.length - 1].push(w); });
  return (
    <Box top={1160} height={520} opacity={useExit(durFrames)}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
        {lines.map((ln, li) => {
          const s = spring({ frame: frame - li * 5, fps, config: { damping: 18, stiffness: 180 }, durationInFrames: 14 });
          const accent = ln.some(isEmph);
          return (
            <div key={li} style={{ transform: `scaleX(${s})`, transformOrigin: "left center", opacity: s, background: accent ? theme.accent : theme.dark === false ? "#1d1d1d" : "#ffffff", color: accent ? "#ffffff" : theme.dark === false ? "#ffffff" : "#111111", fontFamily: F.gothicA1, fontWeight: 900, fontSize: 68, lineHeight: 1.15, padding: "10px 28px 14px", borderRadius: 6, whiteSpace: "nowrap" }}>
              {ln.join(" ")}
            </div>
          );
        })}
      </div>
    </Box>
  );
};

// ---------- 3. karaoke: 전체 흐리게 → 말하는 단어부터 밝게 ----------
const Karaoke: React.FC<P> = ({ sentence, durFrames, theme }) => {
  const frame = useCurrentFrame();
  const { words, perWord, isEmph } = useWords(sentence, durFrames);
  const enter = interpolate(frame, [0, 6], [0, 1], { extrapolateRight: "clamp" });
  return (
    <Box top={1140} height={540} opacity={useExit(durFrames) * enter}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "4px 20px", textAlign: "center", fontFamily: F.doHyeon, fontSize: 80, lineHeight: 1.25, wordBreak: "keep-all", textShadow: "0 6px 30px rgba(0,0,0,0.8)" }}>
        {words.map((w, i) => {
          const lit = interpolate(frame, [i * perWord, i * perWord + perWord * 0.6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const base = theme.dark === false ? "rgba(20,20,20,0.35)" : "rgba(255,255,255,0.35)";
          const on = isEmph(w) || hasDigit(w) ? theme.accent : theme.text;
          return (
            <span key={i} style={{ display: "inline-block", color: lit > 0.5 ? on : base, transform: `translateY(${(1 - lit) * 6}px)`, textShadow: lit > 0.5 ? `0 0 24px ${theme.accent}66, 0 6px 30px rgba(0,0,0,0.8)` : undefined }}>{w}</span>
          );
        })}
      </div>
    </Box>
  );
};

// ---------- 4. typewriter: 글자 타이핑 + 커서 ----------
const Typewriter: React.FC<P> = ({ sentence, durFrames, theme }) => {
  const frame = useCurrentFrame();
  const chars = Array.from(sentence.text);
  const perChar = (durFrames * 0.7) / Math.max(chars.length, 1);
  const n = Math.min(chars.length, Math.floor(frame / perChar) + 1);
  const shown = chars.slice(0, n).join("");
  const cursorOn = Math.floor(frame / 8) % 2 === 0;
  const emph = sentence.emphasis?.[0];
  const idx = emph ? shown.indexOf(emph) : -1;
  const parts = idx >= 0 ? [shown.slice(0, idx), shown.slice(idx, idx + emph!.length), shown.slice(idx + emph!.length)] : [shown, "", ""];
  return (
    <Box top={1180} height={480} opacity={useExit(durFrames)} align="flex-start">
      <div style={{ background: theme.dark === false ? "rgba(255,250,240,0.92)" : "rgba(10,10,14,0.78)", border: `2px solid ${theme.accent}`, padding: "28px 36px", borderRadius: 4, fontFamily: F.gothicA1, fontWeight: 500, fontSize: 62, lineHeight: 1.45, color: theme.text, wordBreak: "keep-all", width: "100%", boxSizing: "border-box", minHeight: 200 }}>
        <span style={{ color: theme.accent, fontWeight: 900, marginRight: 16 }}>›</span>
        {parts[0]}<span style={{ color: theme.accent, fontWeight: 900 }}>{parts[1]}</span>{parts[2]}
        <span style={{ display: "inline-block", width: 6, height: 58, background: theme.accent, marginLeft: 6, verticalAlign: "-8px", opacity: cursorOn ? 1 : 0 }} />
      </div>
    </Box>
  );
};

// ---------- 5. lowerthird: 뉴스 하단 바 + 태그 ----------
const LowerThird: React.FC<P> = ({ sentence, durFrames, theme, title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 20, stiffness: 160 }, durationInFrames: 16 });
  const emph = sentence.emphasis?.[0];
  const t = sentence.text;
  const idx = emph ? t.indexOf(emph) : -1;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: 1300, opacity: useExit(durFrames), transform: `translateX(${(1 - s) * -120}px)` }}>
      <div style={{ display: "inline-block", marginLeft: 60, background: theme.accent, color: "#fff", fontFamily: F.pretendard, fontWeight: 700, fontSize: 30, letterSpacing: 2, padding: "8px 22px 10px", borderRadius: "6px 6px 0 0" }}>{title || "오늘의 이슈"}</div>
      <div style={{ marginLeft: 60, marginRight: 60, background: theme.dark === false ? "rgba(255,255,255,0.94)" : "rgba(8,10,16,0.88)", borderLeft: `14px solid ${theme.accent}`, padding: "26px 34px 30px", fontFamily: F.pretendard, fontWeight: 700, fontSize: 60, lineHeight: 1.35, color: theme.text, wordBreak: "keep-all", borderRadius: "0 8px 8px 8px", boxShadow: "0 20px 60px rgba(0,0,0,0.35)" }}>
        {idx >= 0 ? (<>{t.slice(0, idx)}<span style={{ color: theme.accent, fontWeight: 900 }}>{emph}</span>{t.slice(idx + emph!.length)}</>) : t}
      </div>
    </div>
  );
};

// ---------- 6. outline: 큰 제목체 + 두꺼운 외곽선 ----------
const Outline: React.FC<P> = ({ sentence, durFrames, theme, isHook }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { words, perWord, isEmph } = useWords(sentence, durFrames);
  const fontSize = isHook ? 104 : 90;
  const stroke = theme.dark === false ? "#17120e" : "#000000";
  return (
    <Box top={1080} height={620} opacity={useExit(durFrames)}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0px 22px", textAlign: "center", fontFamily: F.blackHan, fontSize, lineHeight: 1.2, wordBreak: "keep-all" }}>
        {words.map((w, i) => {
          const s = spring({ frame: frame - i * perWord, fps, config: { damping: 12, stiffness: 200, mass: 0.5 }, durationInFrames: 12 });
          const color = isEmph(w) || hasDigit(w) ? theme.accent : theme.dark === false ? "#fffdf7" : "#ffffff";
          return (
            <span key={i} style={{ display: "inline-block", color, WebkitTextStroke: `${theme.dark === false ? 10 : 8}px ${stroke}`, paintOrder: "stroke fill", opacity: s, transform: `scale(${0.6 + 0.4 * s}) rotate(${(1 - s) * -8}deg)`, filter: `drop-shadow(0 10px 0 ${stroke}) drop-shadow(0 16px 30px rgba(0,0,0,0.4))` }}>{w}</span>
          );
        })}
      </div>
    </Box>
  );
};

// ---------- 7. glass: 반투명 유리 카드 ----------
const Glass: React.FC<P> = ({ sentence, durFrames, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 18, stiffness: 120 }, durationInFrames: 18 });
  const { words, perWord, isEmph } = useWords(sentence, durFrames);
  return (
    <Box top={1180} height={480} opacity={useExit(durFrames)}>
      <div style={{ transform: `translateY(${(1 - s) * 40}px)`, opacity: s, width: "100%", background: theme.dark === false ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.12)", backdropFilter: "blur(22px)", WebkitBackdropFilter: "blur(22px)", border: "1.5px solid rgba(255,255,255,0.35)", borderRadius: 28, padding: "34px 40px", boxShadow: "0 30px 80px rgba(0,0,0,0.35)", textAlign: "center", fontFamily: F.pretendard, fontWeight: 700, fontSize: 64, lineHeight: 1.4, color: theme.text, wordBreak: "keep-all" }}>
        {words.map((w, i) => {
          const lit = interpolate(frame, [i * perWord, i * perWord + 4], [0.45, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return <span key={i} style={{ opacity: lit, color: isEmph(w) || hasDigit(w) ? theme.accent : undefined, marginRight: 16, display: "inline-block" }}>{w}</span>;
        })}
      </div>
    </Box>
  );
};

// ---------- 8. stack: 단어를 쌓는 포스터형 ----------
const Stack: React.FC<P> = ({ sentence, durFrames, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { words, isEmph } = useWords(sentence, durFrames);
  const rows: string[][] = [];
  words.forEach((w, i) => { if (i % 2 === 0) rows.push([]); rows[rows.length - 1].push(w); });
  const total = rows.length;
  const size = total <= 3 ? 110 : total <= 4 ? 96 : 84;
  return (
    <div style={{ position: "absolute", top: 760, left: 72, width: W - 144, height: 900, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "flex-start", gap: 6, opacity: useExit(durFrames) }}>
      {rows.map((r, ri) => {
        const s = spring({ frame: frame - ri * 6, fps, config: { damping: 13, stiffness: 190, mass: 0.7 }, durationInFrames: 14 });
        const accent = r.some(isEmph) || r.some(hasDigit);
        return (
          <div key={ri} style={{ transform: `translateX(${(1 - s) * -200}px) rotate(${ri % 2 ? 1.5 : -1.5}deg)`, opacity: s, background: accent ? theme.accent : theme.dark === false ? "#17120e" : "#ffffff", color: accent ? "#ffffff" : theme.dark === false ? "#ffffff" : "#101010", fontFamily: F.jua, fontSize: size, lineHeight: 1.05, padding: "8px 30px 16px", boxShadow: "8px 10px 0 rgba(0,0,0,0.45)", whiteSpace: "nowrap", marginLeft: ri * 26 }}>
            {r.join(" ")}
          </div>
        );
      })}
    </div>
  );
};

// ---------- 9. minimal: 작고 깔끔 ----------
const Minimal: React.FC<P> = ({ sentence, durFrames, theme }) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  const emph = sentence.emphasis?.[0];
  const t = sentence.text;
  const idx = emph ? t.indexOf(emph) : -1;
  const under = interpolate(frame, [4, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <Box top={1320} height={360} opacity={useExit(durFrames) * enter}>
      <div style={{ textAlign: "center", fontFamily: F.pretendard, fontWeight: 700, fontSize: 56, lineHeight: 1.5, color: theme.text, wordBreak: "keep-all", textShadow: theme.dark === false ? "0 0 18px rgba(255,255,255,0.9), 0 2px 6px rgba(255,255,255,0.9)" : "0 4px 20px rgba(0,0,0,0.9)", letterSpacing: -0.5 }}>
        {idx >= 0 ? (<>{t.slice(0, idx)}<span style={{ color: theme.accent, fontWeight: 900, backgroundImage: `linear-gradient(${theme.accent},${theme.accent})`, backgroundRepeat: "no-repeat", backgroundSize: `${under * 100}% 6px`, backgroundPosition: "0 100%", paddingBottom: 4 }}>{emph}</span>{t.slice(idx + emph!.length)}</>) : t}
      </div>
    </Box>
  );
};

// ---------- 10. ticker: 상단 헤드라인 바 + 하단 마커 하이라이트 ----------
const Ticker: React.FC<P> = ({ sentence, durFrames, theme, title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { words, perWord, isEmph } = useWords(sentence, durFrames);
  const bar = spring({ frame, fps, config: { damping: 20, stiffness: 150 }, durationInFrames: 14 });
  const light = theme.dark === false;
  return (
    <>
      <div style={{ position: "absolute", top: 236, left: 0, right: 0, display: "flex", justifyContent: "center", opacity: useExit(durFrames) }}>
        <div style={{ background: theme.accent, color: "#fff", fontFamily: F.doHyeon, fontSize: 36, letterSpacing: 3, padding: "8px 28px 10px", transform: `scaleX(${bar})` }}>{title || "속보"}</div>
      </div>
      <Box top={1150} height={520} opacity={useExit(durFrames)}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "10px 14px", textAlign: "center", fontFamily: F.doHyeon, fontSize: 76, lineHeight: 1.2, wordBreak: "keep-all" }}>
          {words.map((w, i) => {
            const on = interpolate(frame, [i * perWord, i * perWord + 5], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            const key = isEmph(w) || hasDigit(w);
            return (
              <span key={i} style={{ display: "inline-block", padding: "2px 14px 8px", color: key ? "#ffffff" : light ? "#1d2a4a" : "#ffffff", background: key ? theme.accent : light ? "rgba(255,255,255,0.9)" : "rgba(0,0,0,0.72)", opacity: on, transform: `skewX(-6deg) translateY(${(1 - on) * 14}px)`, boxShadow: key ? `6px 6px 0 ${light ? "#1d2a4a" : "#000"}` : undefined }}>{w}</span>
            );
          })}
        </div>
      </Box>
    </>
  );
};

const STYLES: Record<CaptionStyle, React.FC<P>> = {
  kinetic: Kinetic, boxed: Boxed, karaoke: Karaoke, typewriter: Typewriter, lowerthird: LowerThird,
  outline: Outline, glass: Glass, stack: Stack, minimal: Minimal, ticker: Ticker,
};

export const Caption: React.FC<P & { style: CaptionStyle }> = ({ style, ...p }) => {
  const C = STYLES[style] ?? Kinetic;
  return <C {...p} />;
};
