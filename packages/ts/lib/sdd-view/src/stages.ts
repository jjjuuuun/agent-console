import type { ParsedStage, ParsedTask, StageRef } from "@agent-console/contracts/sdd";

/** 단계 묶음. `stage`가 null이면 단계 없는 작업 묶음이다. */
export interface StageGroup {
  /** 묶음 키(단계 id, 단계 없음은 빈 문자열) */
  key: string;
  stage: StageRef | null;
  tasks: ParsedTask[];
  done: number;
  total: number;
}

/**
 * 작업을 단계별로 묶는다. 순서는 `stages`(문서 순서)가 있으면 그 순서, 아니면 처음 나온 순서다.
 * 단계 없는 작업은 처음 나온 자리에 한 묶음으로 모은다. 작업 순서(문서 순서)는 묶음 안에서 그대로다.
 * `isDone`은 상태 id가 끝난 상태인지 알려 준다(상태 이름을 모르는 호출자 주입).
 */
export function groupByStage(
  tasks: readonly ParsedTask[],
  isDone: (status: string) => boolean = () => false,
  stages: readonly ParsedStage[] = [],
): StageGroup[] {
  const groups = new Map<string, StageGroup>();
  const ensure = (key: string, stage: StageRef | null): StageGroup => {
    let group = groups.get(key);
    if (!group) {
      group = { key, stage, tasks: [], done: 0, total: 0 };
      groups.set(key, group);
    }
    return group;
  };
  for (const s of stages) ensure(s.id, { id: s.id, title: s.title ?? s.id });
  for (const task of tasks) {
    const stage = task.stage ?? null;
    const group = ensure(stage ? stage.id : "", stage);
    group.tasks.push(task);
    group.total += 1;
    if (isDone(task.status)) group.done += 1;
  }
  return [...groups.values()].filter((g) => g.total > 0 || g.key !== "");
}

/** 표 한 줄(가상 목록 단위). */
export type TaskRow =
  | { type: "stage"; key: string; group: StageGroup }
  | { type: "task"; key: string; task: ParsedTask; group: StageGroup };

/** 묶음 → 표 줄. 접힌 단계의 작업 줄은 뺀다. 단계가 하나뿐이고 단계 없음이면 머리 줄도 뺀다. */
export function flattenTaskRows(groups: readonly StageGroup[], collapsed: ReadonlySet<string> = new Set()): TaskRow[] {
  const bare = groups.length === 1 && groups[0]?.key === "";
  const rows: TaskRow[] = [];
  for (const group of groups) {
    if (!bare) rows.push({ type: "stage", key: `stage:${group.key}`, group });
    if (collapsed.has(group.key)) continue;
    for (const task of group.tasks) rows.push({ type: "task", key: `task:${task.key}`, task, group });
  }
  return rows;
}

/** 끝난 작업 비율(0~1). 총합 0이면 0. */
export function progressRatio(done: number, total: number): number {
  return total > 0 ? Math.min(1, Math.max(0, done / total)) : 0;
}
