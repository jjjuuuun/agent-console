import type { EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { decideEdgeKind } from "./ops";
import type { Connection } from "./ops";
import { closesFlowLoop } from "./loops";
import { rankEdgeKinds } from "./autoConnect";

/** 후보 한 줄의 추가 정보. 연결 종류 선택 UI(`EdgeKindDialog`)가 그대로 받는다. */
export interface ConnectCandidateInfo {
  disabledReason?: string;
  preferred?: boolean;
}

export type ConnectPlan =
  | { mode: "none" }
  /** 고를 수 있는 종류가 없다(모든 후보가 순환을 닫는 흐름 종류) */
  | { mode: "cycle-rejected" }
  | { mode: "auto"; kind: string }
  | { mode: "ask"; candidates: EdgeTypeDescriptor[]; preselected: string; info: Record<string, ConnectCandidateInfo> };

export interface PlanConnectionInput {
  graph: Graph;
  connection: Connection;
  /** `connects`로 걸러진 후보(최신 버전) */
  candidates: readonly EdgeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  /** 직전에 쓴 종류·기본 종류(후보에 있을 때만 미리 선택) */
  preferredKind?: string | undefined;
  /** 두 끝 노드 타입의 `role`. 있으면 `connects`가 두 역할을 모두 명시한 종류가 기본 선택에서 앞선다 */
  sourceRole?: string | undefined;
  targetRole?: string | undefined;
  /** 순환을 닫는 흐름 종류 행의 비활성 사유 문구 */
  cycleNeededText: string;
}

/**
 * 새 연결의 종류 결정(순수 함수). 새 연결이 흐름 순환을 닫으면(`closesFlowLoop`) 디스크립터 `cycle`이 있는 종류는 정상 행이고
 * 기본 선택이 되며, 없는 흐름 종류는 비활성 행(사유 포함)이 된다. 모든 후보가 비활성이면 `cycle-rejected`.
 * `scheduling`이 `none`/`entry`/`exit`인 종류는 순환 검사 대상이 아니라 평소대로 고를 수 있다.
 * 순환이 아니면 기존 규칙(`decideEdgeKind`: 후보 하나면 자동, 둘 이상이면 선택).
 */
export function planConnection(i: PlanConnectionInput): ConnectPlan {
  const decision = decideEdgeKind(
    i.candidates.map((t) => t.id),
    i.preferredKind,
  );
  if (decision.mode === "none") return { mode: "none" };
  const info: Record<string, ConnectCandidateInfo> = {};
  for (const t of i.candidates) {
    if (!closesFlowLoop(i.graph, { kind: t.id, source: i.connection.source, target: i.connection.target }, i.edgeTypes)) continue;
    info[t.id] = t.cycle !== null && t.cycle !== undefined ? { preferred: true } : { disabledReason: i.cycleNeededText };
  }
  const blocked = i.candidates.filter((t) => info[t.id]?.disabledReason !== undefined);
  if (blocked.length === i.candidates.length) return { mode: "cycle-rejected" };
  // 기본 선택은 목록 첫 항목이 아니라 관련도 순: 두 역할 명시 -> 기본·마지막 종류 -> 목록 순서
  const ranked = rankEdgeKinds(i.candidates.filter((t) => info[t.id]?.disabledReason === undefined), { sourceRole: i.sourceRole, targetRole: i.targetRole }, i.preferredKind);
  if (blocked.length > 0) {
    // 비활성 행이 있으면 후보가 하나만 남아도 이유를 보이기 위해 선택 UI를 띄운다
    const pick = i.candidates.find((t) => info[t.id]?.preferred === true) ?? (ranked[0] as EdgeTypeDescriptor);
    return { mode: "ask", candidates: [...i.candidates], preselected: pick.id, info };
  }
  if (decision.mode === "auto") return { mode: "auto", kind: decision.kind };
  const preferred = i.candidates.find((t) => info[t.id]?.preferred === true);
  return { mode: "ask", candidates: [...i.candidates], preselected: preferred?.id ?? ranked[0]?.id ?? decision.preselected, info };
}
