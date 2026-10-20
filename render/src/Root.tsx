import { CalculateMetadataFunction, Composition, staticFile } from "remotion";
import { Shorts } from "./Shorts";
import {
  Durations,
  Script,
  ShortsProps,
  buildTimeline,
  defaultTheme,
  totalSeconds,
} from "./types";

const FPS = 30;

// jobs/{jobId}/script.json + audio/durations.json 을 읽어 길이를 계산하고 props에 채운다.
const calculateMetadata: CalculateMetadataFunction<ShortsProps> = async ({
  props,
}) => {
  const base = `jobs/${props.jobId}`;
  const [script, durations] = await Promise.all([
    fetch(staticFile(`${base}/script.json`)).then((r) => r.json() as Promise<Script>),
    fetch(staticFile(`${base}/audio/durations.json`)).then(
      (r) => r.json() as Promise<Durations>,
    ),
  ]);
  const gap = props.theme?.gapSec ?? defaultTheme.gapSec;
  const tl = buildTimeline(script, durations, FPS, gap);
  return {
    durationInFrames: Math.ceil(totalSeconds(tl, gap) * FPS),
    props: { ...props, script, durations },
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Shorts"
      component={Shorts}
      durationInFrames={30 * 30}
      fps={FPS}
      width={1080}
      height={1920}
      defaultProps={{ jobId: "_sample" } as ShortsProps}
      calculateMetadata={calculateMetadata}
    />
  );
};
