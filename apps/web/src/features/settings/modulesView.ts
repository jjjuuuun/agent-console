import type { ModuleInfo } from "@agent-console/contracts";
import { enableSnippet, isProblemStatus, MODULE_STATUS, moduleMatchesText } from "../../modules";
import { messages as m } from "../../app/messages";

/** 상태 필터 값: 전체이거나 상태 하나(단일 선택). */
export type StatusFilter = "all" | string;

/** 필터 칩으로 보이는 상태(계약이 고정한 5종). 순서가 칩 순서다. */
export const FILTER_STATUSES: readonly string[] = [MODULE_STATUS.active, MODULE_STATUS.disabled, MODULE_STATUS.unsatisfied, MODULE_STATUS.failed, MODULE_STATUS.conflict];

export interface ModuleCounts {
  total: number;
  /** 상태별 개수(5종, 0도 포함) */
  byStatus: Record<string, number>;
  active: number;
  disabled: number;
  /** 문제(`unsatisfied`·`failed`·`conflict`와 모르는 상태) */
  problems: number;
  /** 문제 중 시작 실패가 있는가(요약 줄·점 색을 danger로) */
  hasFailed: boolean;
}

/** 요약 줄·필터 칩에 쓰는 개수. 문제는 `disabled`를 포함하지 않는다(사용자가 의도해서 끈 것). */
export function countModules(modules: readonly ModuleInfo[]): ModuleCounts {
  const byStatus: Record<string, number> = Object.fromEntries(FILTER_STATUSES.map((s) => [s, 0]));
  for (const m of modules) if (m.status in byStatus) byStatus[m.status] = (byStatus[m.status] ?? 0) + 1;
  return {
    total: modules.length,
    byStatus,
    active: byStatus[MODULE_STATUS.active] ?? 0,
    disabled: byStatus[MODULE_STATUS.disabled] ?? 0,
    problems: modules.filter((m) => isProblemStatus(m.status)).length,
    hasFailed: modules.some((m) => m.status === MODULE_STATUS.failed),
  };
}

export interface ModuleGroup {
  kind: string;
  modules: ModuleInfo[];
}

/** 그룹 안 정렬 순위: 문제(0) -> 꺼짐(1) -> 켜짐(2). 같으면 서버 순서. */
function rank(status: string): number {
  return isProblemStatus(status) ? 0 : status === MODULE_STATUS.disabled ? 1 : 2;
}

/**
 * 필터·검색을 적용해 `kind`별로 묶는다. 그룹 순서는 서버 응답에서 처음 나온 `kind` 순이고,
 * 그룹 안은 문제가 위에 오도록 정렬한다(안정 정렬).
 */
export function groupModules(modules: readonly ModuleInfo[], filter: StatusFilter, text: string): ModuleGroup[] {
  const order: string[] = [];
  const byKind = new Map<string, ModuleInfo[]>();
  for (const m of modules) {
    if (!byKind.has(m.kind)) {
      byKind.set(m.kind, []);
      order.push(m.kind);
    }
    if ((filter === "all" || m.status === filter) && moduleMatchesText(m, text)) byKind.get(m.kind)?.push(m);
  }
  return order
    .map((kind) => ({ kind, modules: (byKind.get(kind) ?? []).map((m, i) => ({ m, i })).sort((a, b) => rank(a.m.status) - rank(b.m.status) || a.i - b.i).map((x) => x.m) }))
    .filter((g) => g.modules.length > 0);
}

/** 문제 행의 이유 한 줄(접힌 상태에서도 보임)이 필요한가. */
export function showsReasonCollapsed(m: ModuleInfo): boolean {
  return isProblemStatus(m.status) && m.reason !== undefined && m.reason !== null && m.reason !== "";
}

/**
 * 모듈 하나를 켜거나 끄는 방법(설치자가 서버 설정 파일 또는 실행 옵션에 붙일 텍스트).
 * 켜져 있으면 끄는 조각, 아니면 켜는 조각이다. 웹은 설정을 바꾸지 않고 복사만 돕는다.
 */
export function moduleCommandSnippet(mod: Pick<ModuleInfo, "id" | "status">): string {
  const c = m.modules.cmd;
  if (mod.status === MODULE_STATUS.active) {
    return [c.comment, "modules:", `  disabled: [${mod.id}]`, c.orCli, `agent-console serve --disable-module ${mod.id}`].join("\n");
  }
  return enableSnippet([mod.id]);
}
