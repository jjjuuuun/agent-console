/**
 * 옮기기 계획 다루기(서버가 계산한 `MovePlan`을 화면 선택에 맞게 다듬는 순수 함수).
 * 계산 자체는 서버(`POST /projects/move-plan`)가 한다. 여기서는 합치기·고르기·이슈에서 대상 읽기만 한다.
 */
import { KNOWN_ISSUE_CODES, KNOWN_SUGGESTION_IDS } from "@agent-console/contracts/constants";
import type { DefinitionMove, MovePlan } from "@agent-console/contracts/projects";

/**
 * 프로젝트 범위 이슈 코드. 값은 계약 생성 상수 `KNOWN_ISSUE_CODES`(Python `KnownIssueCodes`)에서 가져온다
 * (손으로 복사하지 않음). 이슈 코드는 열린 문자열이라, 여기 없는 코드도 화면은 `message`로 그린다.
 */
export const SCOPE_ISSUE_CODES = {
  sharedUsesProject: KNOWN_ISSUE_CODES.PROJECT_SHARED_USES_PROJECT,
  crossProject: KNOWN_ISSUE_CODES.PROJECT_CROSS_PROJECT,
  unknown: KNOWN_ISSUE_CODES.PROJECT_UNKNOWN,
  referencesUnavailable: KNOWN_ISSUE_CODES.PROJECT_REFERENCES_UNAVAILABLE,
  definitionsUnavailable: KNOWN_ISSUE_CODES.PROJECT_DEFINITIONS_UNAVAILABLE,
} as const;

/** [공용으로 옮기기] 제안 id(계약 생성 상수 `KNOWN_SUGGESTION_IDS`, Python `KnownSuggestionIds`). */
export const MOVE_TO_SHARED_SUGGESTION_ID = KNOWN_SUGGESTION_IDS.PROJECT_MOVE_TO_SHARED;

const keyOf = (m: { kind: string; id: string }): string => `${m.kind}\u0000${m.id}`;

/**
 * 여러 정의의 계획(다중 선택 "프로젝트로 이동…")을 하나로 합친다.
 * 같은 정의는 한 번만 담고(앞선 것 우선, 단 하나라도 `required`면 required), 경고는 같은 코드·메시지를 한 번만 둔다.
 * @param plans 정의마다 받은 계획(목적지 `to`가 모두 같아야 한다. 합친 계획의 `target`은 첫 계획의 것)
 */
export function mergeMovePlans(plans: readonly MovePlan[]): MovePlan | null {
  const head = plans[0];
  if (head === undefined) return null;
  const moves = new Map<string, DefinitionMove>();
  const warnings = new Map<string, NonNullable<MovePlan["warnings"]>[number]>();
  for (const plan of plans) {
    for (const m of plan.moves ?? []) {
      const k = keyOf(m);
      const prev = moves.get(k);
      if (prev === undefined) moves.set(k, m);
      else if (m.required === true && prev.required !== true) moves.set(k, { ...prev, required: true });
    }
    for (const w of plan.warnings ?? []) warnings.set(`${w.code}\u0000${w.message}\u0000${w.path ?? ""}`, w);
  }
  return { target: head.target, to: head.to ?? null, moves: [...moves.values()], warnings: [...warnings.values()] };
}

/** 이 이동이 사용자가 옮기려던 정의 자신인지(false = 참조 때문에 권하는 정의). `required` 생략은 true. */
export function isRequiredMove(move: DefinitionMove): boolean {
  return move.required !== false;
}

/**
 * 계획에서 실제로 적용할 이동만 골라 `POST /projects/move` 본문을 만든다.
 * 필수 이동은 늘 담고, 권하는 이동(`required: false`)은 `include`에 든 것만 담는다.
 * @param include 함께 옮길 권장 정의의 `kind`/`id` 키 모음(`moveKey`). 생략 = 권장 전부 포함(기본 선택 [함께 옮기기])
 */
export function selectMoves(plan: MovePlan, include?: ReadonlySet<string>): MovePlan {
  const moves = (plan.moves ?? []).filter((m) => isRequiredMove(m) || include === undefined || include.has(keyOf(m)));
  return { ...plan, moves };
}

/** `selectMoves`의 `include`에 넣는 키. */
export function moveKey(move: { kind: string; id: string }): string {
  return keyOf(move);
}

/** 이슈에서 [공용으로 옮기기] 대상을 읽는다. 제안이 없거나 형식이 다르면 null. */
export function moveTargetOfIssue(issue: {
  details?: { [k: string]: unknown } | undefined;
  suggestions?: readonly { id: string }[] | undefined;
}): { kind: string; id: string } | null {
  if (!(issue.suggestions ?? []).some((s) => s.id === MOVE_TO_SHARED_SUGGESTION_ID)) return null;
  const d = issue.details;
  if (d === undefined) return null;
  if (typeof d["kind"] === "string" && typeof d["id"] === "string") return { kind: d["kind"], id: d["id"] };
  const m = d["move"];
  if (typeof m === "object" && m !== null) {
    const { kind, id } = m as Record<string, unknown>;
    if (typeof kind === "string" && typeof id === "string") return { kind, id };
  }
  return null;
}
