import { DEFAULT_TEAM_CONVENTIONS, numberAt, type TeamConventions } from "./conventions";

/** 한도가 어느 층에서 왔는가. 연결 자신이 아니면 상속이다. */
export type CycleLimitSource = "edge" | "teamSettings" | "commonSettings" | "kindDefault";

export interface CycleLimit {
  /** 유효 한도(정수 ≥ 1). 없으면 undefined */
  value: number | undefined;
  /** 값을 준 층. 값이 없으면 undefined */
  source: CycleLimitSource | undefined;
}

export interface ResolveCycleLimitInput {
  /** 연결 config */
  edgeConfig?: unknown;
  /** 팀 구성 사용자 설정 묶음 */
  teamSettings?: unknown;
  /** 공통(워크스페이스) 사용자 설정 묶음 */
  commonSettings?: unknown;
  /** 연결 종류 디스크립터 `cycle.max_iterations` */
  kindDefault?: number | null | undefined;
  conventions?: TeamConventions;
}

const valid = (v: number | undefined | null): v is number => typeof v === "number" && Number.isInteger(v) && v >= 1;

/**
 * 반복 연결 회차 한도 해석: 연결 → 팀 → 공통 → 연결 종류 기본 순으로 처음 유효한 값(정수 ≥ 1)과 그 층.
 * 순수 함수. config 키 위치는 `TeamConventions` 데이터에서 온다.
 */
export function resolveCycleLimit(input: ResolveCycleLimitInput): CycleLimit {
  const c = input.conventions ?? DEFAULT_TEAM_CONVENTIONS;
  const layers: [CycleLimitSource, number | undefined | null][] = [
    ["edge", numberAt(input.edgeConfig, c.edgeIterationLimit)],
    ["teamSettings", numberAt(input.teamSettings, c.settingsFlowMaxIterations)],
    ["commonSettings", numberAt(input.commonSettings, c.settingsFlowMaxIterations)],
    ["kindDefault", input.kindDefault],
  ];
  for (const [source, value] of layers) if (valid(value)) return { value, source };
  return { value: undefined, source: undefined };
}
