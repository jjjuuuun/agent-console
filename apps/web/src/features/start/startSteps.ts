import type { StepGuideStep } from "@agent-console/ui";
import { ROUTE_ROLES } from "../library";
import { startMessages } from "./messages";

/** 서버 데이터에서 센 값. 아직 모르면 undefined(완료로 치지 않는다). */
export interface StartCounts {
  /** 입구가 있어 대화를 시작할 수 있는 팀 구성 수 */
  usableTeams: number | undefined;
  conversations: number | undefined;
  runs: number | undefined;
}

export interface StartStepDef {
  id: string;
  /** 이동할 화면의 역할(라우트 id가 아니라 역할로 푼다) */
  role: string;
  done: (c: StartCounts) => boolean;
}

/** 기본 단계(데이터). 문구는 `startMessages.steps[id]`. 단계를 바꾸려면 이 표와 문구 표만 고친다. */
export const START_STEP_DEFS: readonly StartStepDef[] = [
  { id: "create", role: ROUTE_ROLES.graph, done: (c) => (c.usableTeams ?? 0) > 0 },
  { id: "talk", role: ROUTE_ROLES.conversations, done: (c) => (c.conversations ?? 0) > 0 },
  { id: "review", role: ROUTE_ROLES.runs, done: (c) => (c.runs ?? 0) > 0 },
];

/**
 * 단계 표 + 개수 + 이동 해석기로 `StepGuide` 단계를 만든다. 꺼진 화면(`isOn`이 false)으로 가는 단계는 뺀다.
 * 모든 단계의 이동은 `to`(경로)이며 새 대화 같은 대화상자를 열지 않는다.
 */
export function buildStartSteps(args: {
  defs?: readonly StartStepDef[];
  counts: StartCounts;
  pathOf: (role: string) => string;
  isOn: (role: string) => boolean;
  text?: typeof startMessages.steps;
}): StepGuideStep[] {
  const text = args.text ?? startMessages.steps;
  return (args.defs ?? START_STEP_DEFS)
    .filter((d) => args.isOn(d.role))
    .map((d) => {
      const t = text[d.id];
      return { id: d.id, label: t?.label ?? d.id, ...(t?.hint ? { hint: t.hint } : {}), ...(t?.action ? { actionLabel: t.action } : {}), done: d.done(args.counts), to: args.pathOf(d.role) };
    });
}
