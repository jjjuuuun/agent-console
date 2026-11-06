import type { StepGuideStep } from "@agent-console/ui";
import { folderHomeMessages } from "./folderHomeMessages";

/** 시작하기 단계를 판단하는 개수(앱 상태에서 센 값, 저장된 플래그 없음). 아직 모르면 undefined(완료로 치지 않는다). */
export interface ProjectStartCounts {
  /** 등록한 프로젝트(보관 제외) */
  projects: number | undefined;
  /** 공용 팀 구성 */
  libraryTeams: number | undefined;
  /** 현재 프로젝트 공간의 팀 구성 */
  projectTeams: number | undefined;
  /** 현재 프로젝트의 대화 */
  projectConversations: number | undefined;
}

/** 단계 한 개(데이터). `needs`는 이 단계의 버튼이 열리기 전에 끝나 있어야 하는 단계 id, `role`은 이 단계가 필요로 하는 화면 역할(꺼지면 단계가 빠진다). */
export interface ProjectStartStepDef {
  id: string;
  done: (c: ProjectStartCounts) => boolean;
  needs: readonly string[];
  /** 이 역할의 화면이 꺼져 있으면 단계를 뺀다 */
  role?: string | undefined;
  /** 단계가 건너뛸 수 있는지: 처음부터 끝나 있으면 "건너뜀" 문구 */
  doneHint?: string;
}

/**
 * 시작하기 4단계(screen-projects §5.6). 단계 순서·완료 조건·전제는 이 표가 전부이고 문구는 `folderHomeMessages.steps`다.
 * 단계 id와 화면 역할은 호출한 쪽이 라우트 데이터로 풀어 준다(`actions`).
 */
export const PROJECT_START_STEPS: readonly ProjectStartStepDef[] = [
  { id: "folder", done: (c) => (c.projects ?? 0) > 0, needs: [] },
  { id: "library", done: (c) => (c.libraryTeams ?? 0) > 0, needs: [], doneHint: folderHomeMessages.steps.library.done },
  { id: "import", done: (c) => (c.projectTeams ?? 0) > 0, needs: ["folder"] },
  { id: "chat", done: (c) => (c.projectConversations ?? 0) > 0, needs: ["folder", "import"] },
];

/** 단계 하나의 버튼 동작: 경로 이동(`to`)이나 콜백(`onAction`). 없으면 버튼을 그리지 않는다. */
export interface ProjectStartAction {
  to?: string;
  onAction?: () => void;
}

/**
 * 시작하기 `StepGuide` 단계를 만든다.
 * - 완료 조건은 개수로 계산한다(모르면 미완료).
 * - 전제 단계가 끝나지 않은 단계는 버튼 없이 이유 문구를 보인다(`needFolder`·`needConfig`).
 * - ②가 이미 끝나 있으면 "공용 구성이 있습니다"를 보인다. ③의 전제는 ①뿐이다(②는 건너뛸 수 있다).
 * - `actions`에 없는 단계(해당 화면이 꺼짐)는 뺀다.
 */
export function buildProjectStartSteps(args: {
  counts: ProjectStartCounts;
  actions: Readonly<Record<string, ProjectStartAction | undefined>>;
  defs?: readonly ProjectStartStepDef[];
  text?: typeof folderHomeMessages.steps;
}): StepGuideStep[] {
  const text = args.text ?? folderHomeMessages.steps;
  const defs = args.defs ?? PROJECT_START_STEPS;
  const doneById = new Map(defs.map((d) => [d.id, d.done(args.counts)]));
  const labels = text as unknown as Record<string, { label: string; hint?: string; action?: string; done?: string } | undefined>;
  return defs
    .filter((d) => Object.hasOwn(args.actions, d.id))
    .map((d): StepGuideStep => {
      const t = labels[d.id];
      const done = doneById.get(d.id) ?? false;
      const unmet = d.needs.find((n) => doneById.get(n) !== true);
      const ready = unmet === undefined;
      const action = args.actions[d.id];
      const hint = done && d.doneHint !== undefined ? d.doneHint : unmet === "folder" ? text.needFolder : unmet !== undefined ? text.needConfig : t?.hint;
      return {
        id: d.id,
        label: t?.label ?? d.id,
        done,
        ...(hint === undefined ? {} : { hint }),
        ...(!done && ready && action !== undefined ? { ...(action.to === undefined ? {} : { to: action.to }), ...(action.onAction === undefined ? {} : { onAction: action.onAction }) } : {}),
        ...(t?.action === undefined ? {} : { actionLabel: t.action }),
      };
    });
}
