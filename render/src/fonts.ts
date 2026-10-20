// 로컬 폰트 (public/fonts). 구글폰트 한글 서브셋은 청크가 많아 로딩 타임아웃이 나서 로컬로 고정.
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

export const F = {
  blackHan: "Black Han Sans", // 굵은 제목체
  pretendard: "Pretendard", // 본문 고딕 (700/900)
  jua: "Jua", // 둥근 포스터체
  doHyeon: "Do Hyeon", // 각진 헤드라인체
  gothicA1: "Gothic A1", // 고딕 (500/900)
  nanumPen: "Nanum Pen Script", // 손글씨
  nanumBrush: "Nanum Brush Script", // 붓글씨
} as const;

export const fontsReady = Promise.all([
  loadFont({ family: F.blackHan, url: staticFile("fonts/BlackHanSans-Regular.ttf"), weight: "400" }),
  loadFont({ family: F.pretendard, url: staticFile("fonts/Pretendard-Bold.woff2"), weight: "700" }),
  loadFont({ family: F.pretendard, url: staticFile("fonts/Pretendard-Black.woff2"), weight: "900" }),
  loadFont({ family: F.jua, url: staticFile("fonts/Jua-Regular.ttf"), weight: "400" }),
  loadFont({ family: F.doHyeon, url: staticFile("fonts/DoHyeon-Regular.ttf"), weight: "400" }),
  loadFont({ family: F.gothicA1, url: staticFile("fonts/GothicA1-Medium.ttf"), weight: "500" }),
  loadFont({ family: F.gothicA1, url: staticFile("fonts/GothicA1-Black.ttf"), weight: "900" }),
  loadFont({ family: F.nanumPen, url: staticFile("fonts/NanumPenScript-Regular.ttf"), weight: "400" }),
  loadFont({ family: F.nanumBrush, url: staticFile("fonts/NanumBrushScript-Regular.ttf"), weight: "400" }),
]);
