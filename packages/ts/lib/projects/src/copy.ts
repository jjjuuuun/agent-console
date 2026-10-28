/**
 * 복사 계획 도우미(공간 사이 정의 복사, design §PI.4.2·screen-projects §5.1). 화면을 그리지 않는 순수 함수다.
 *
 * 흐름: 서버가 준 `CopyPlan`에서 `initialSelections`로 항목별 동작을 정하고, 사용자가 고친 선택을 `canSubmit`·
 * `skipWarnings`·`summarizeSelections`로 검사한 뒤 `buildApplyRequest`로 적용 요청을 만든다. 결과는 `summarizeResult`.
 * 동작·상태 값은 열린 문자열이다(`KNOWN_COPY_*`는 문서 상수): 모르는 `target_state`는 `different`처럼 사용자 선택을 요구하고,
 * 모르는 결과 상태는 오류 행으로 본다. 종류 이름·프로젝트 이름을 코드에 두지 않는다.
 */
import { KNOWN_COPY_ACTIONS, KNOWN_COPY_STATUSES, KNOWN_COPY_TARGET_STATES } from "@agent-console/contracts/constants";
import type {
  CopyApplyItem,
  CopyApplyItemResult,
  CopyApplyRequest,
  CopyApplyResult,
  CopyPlan,
  CopyPlanItem,
} from "@agent-console/contracts/projects";
import type { SpaceRef } from "@agent-console/contracts";

import type { MessageRef } from "./messages";

const A = KNOWN_COPY_ACTIONS;
const S = KNOWN_COPY_TARGET_STATES;
const R = KNOWN_COPY_STATUSES;

/** 항목 이유: 사용자가 고른 것. 그 밖(`referenced` 등)은 함께 가져오는 연결 항목. */
export const COPY_REASON_REQUESTED = "requested";

/** 계획·결과의 항목 목록(계약상 선택 필드라 없으면 빈 목록). */
function itemsOf<T>(holder: { items?: T[] | undefined }): T[] {
  return holder.items ?? [];
}

/** 정의 하나를 가리키는 키(종류 + id). 선택 표의 열쇠. */
export function copyItemKey(item: { kind: string; id: string }): string {
  return `${item.kind}\u0000${item.id}`;
}

/** 계획 행 하나에 대한 사용자 선택. `action`이 null이면 아직 고르지 않았다. */
export interface CopySelection {
  action: string | null;
  /** `rename`일 때 새 id. */
  newId?: string;
}

export type CopySelections = ReadonlyMap<string, CopySelection>;

/** 동작 선택지 하나(드롭다운 항목). */
export interface CopyActionChoice {
  action: string;
  /** 문구 키(`copy.action.…`). */
  label: MessageRef;
}

/** 대상 상태 → 선택지(§5.1 표). 바꾸려면 이 표만 고친다. */
export const COPY_ACTION_CHOICES: Readonly<Record<string, readonly CopyActionChoice[]>> = {
  [S.ABSENT]: [
    { action: A.COPY, label: { key: "copy.action.copy" } },
    { action: A.SKIP, label: { key: "copy.action.skip" } },
  ],
  [S.IDENTICAL]: [
    { action: A.REUSE, label: { key: "copy.action.reuse" } },
    { action: A.RENAME, label: { key: "copy.action.rename" } },
    { action: A.SKIP, label: { key: "copy.action.skip" } },
  ],
  [S.DIFFERENT]: [
    { action: A.OVERWRITE, label: { key: "copy.action.overwrite" } },
    { action: A.RENAME, label: { key: "copy.action.rename" } },
    { action: A.SKIP, label: { key: "copy.action.skip_keep" } },
  ],
};

/** 대상 상태 표시(`copy.state.…`). 모르는 값은 `different`처럼(사용자 선택 필요) 보인다. */
export function targetStateLabel(state: string): MessageRef {
  return { key: `copy.state.${state in COPY_ACTION_CHOICES ? state : S.DIFFERENT}` };
}

/** 이 항목에서 고를 수 있는 동작. 모르는 `target_state`는 `different`의 선택지. */
export function actionChoicesFor(item: Pick<CopyPlanItem, "target_state">): readonly CopyActionChoice[] {
  return COPY_ACTION_CHOICES[item.target_state] ?? COPY_ACTION_CHOICES[S.DIFFERENT] ?? [];
}

/**
 * 항목의 기본 동작. 서버 `default_action`이 선택지에 있으면 그것, 없으면 상태별 기본
 * (없음 → 복사, 같은 내용 → 그대로 쓰기, 내용이 다름·모르는 값 → null = 고를 때까지 막힘).
 */
export function defaultActionFor(item: Pick<CopyPlanItem, "target_state" | "default_action">): string | null {
  const choices = actionChoicesFor(item);
  const given = item.default_action;
  if (given !== undefined && given !== null && choices.some((c) => c.action === given)) return given;
  if (item.target_state === S.ABSENT) return A.COPY;
  if (item.target_state === S.IDENTICAL) return A.REUSE;
  return null;
}

/** 계획 전체의 초기 선택(항목마다 `defaultActionFor`). */
export function initialSelections(plan: Pick<CopyPlan, "items">): Map<string, CopySelection> {
  const out = new Map<string, CopySelection>();
  for (const item of itemsOf(plan)) out.set(copyItemKey(item), { action: defaultActionFor(item) });
  return out;
}

/** 선택을 바꾼 새 표를 돌려준다(원본 유지). `rename`을 처음 고르면 `taken`을 피한 제안 id를 채운다. */
export function selectAction(
  selections: CopySelections,
  item: Pick<CopyPlanItem, "kind" | "id">,
  action: string | null,
  taken: Iterable<string> = [],
): Map<string, CopySelection> {
  const next = new Map(selections);
  const key = copyItemKey(item);
  const prev = next.get(key);
  if (action === A.RENAME) {
    const used = [...taken, ...[...next.values()].flatMap((s) => (s.newId === undefined ? [] : [s.newId]))];
    next.set(key, { action, newId: prev?.newId ?? suggestRename(item.id, used) });
  } else {
    next.set(key, { action });
  }
  return next;
}

/** 새 이름 id의 문법(서버 `Slug`와 같은 규칙). */
export const SLUG_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

/** `{id}-2`, `-3` … 중 `taken`에 없는 첫 번째. */
export function suggestRename(id: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  for (let n = 2; ; n += 1) {
    const candidate = `${id}-${n}`;
    if (!used.has(candidate)) return candidate;
  }
}

export type NewIdProblem = "empty" | "invalid" | "taken";

/** 새 이름 검사. `taken` = 대상에 이미 있는 id + 같은 묶음의 다른 새 이름. 문제 없으면 null. */
export function validateNewId(newId: string | undefined, taken: Iterable<string>): NewIdProblem | null {
  const v = (newId ?? "").trim();
  if (v === "") return "empty";
  if (!SLUG_PATTERN.test(v)) return "invalid";
  for (const t of taken) if (t === v) return "taken";
  return null;
}

/** 아직 동작을 고르지 않은 항목(내용이 다름 등). 제출 전에 사용자가 골라야 한다. */
export function itemsNeedingChoice(plan: Pick<CopyPlan, "items">, selections: CopySelections): CopyPlanItem[] {
  return itemsOf(plan).filter((i) => (selections.get(copyItemKey(i))?.action ?? null) === null);
}

export interface SkipWarning {
  item: CopyPlanItem;
  /** 문구 키 `copy.skip_warn` + `{by, id}`. */
  message: MessageRef;
}

/**
 * 연결로 따라온 항목(`reason != requested`)을 가져오지 않기로 했을 때의 경고. 요청한 항목을 건너뛰는 것은 경고가 아니다.
 * 대상에 이미 있어 `reuse`로 쓰는 항목은 건너뛰는 것이 아니므로 경고하지 않는다.
 */
export function skipWarnings(plan: Pick<CopyPlan, "items">, selections: CopySelections): SkipWarning[] {
  const out: SkipWarning[] = [];
  for (const item of itemsOf(plan)) {
    if (item.reason === COPY_REASON_REQUESTED) continue;
    if (selections.get(copyItemKey(item))?.action !== A.SKIP) continue;
    const by = (item.referenced_by ?? []).map((r) => (r.name !== undefined && r.name !== "" ? r.name : r.id)).join(", ");
    out.push({ item, message: { key: "copy.skip_warn", params: { by, id: item.id } } });
  }
  return out;
}

export interface SelectionSummary {
  copy: number;
  reuse: number;
  overwrite: number;
  rename: number;
  skip: number;
  /** 아직 고르지 않은 항목. */
  unset: number;
  /** 실제로 쓰는 것(복사 + 덮어쓰기 + 새 이름) — 제출 버튼의 (N). */
  writes: number;
}

/** 동작별 개수. 모르는 동작은 건너뜀으로 센다. */
export function summarizeSelections(plan: Pick<CopyPlan, "items">, selections: CopySelections): SelectionSummary {
  const s: SelectionSummary = { copy: 0, reuse: 0, overwrite: 0, rename: 0, skip: 0, unset: 0, writes: 0 };
  for (const item of itemsOf(plan)) {
    const action = selections.get(copyItemKey(item))?.action ?? null;
    if (action === null) s.unset += 1;
    else if (action === A.COPY) s.copy += 1;
    else if (action === A.REUSE) s.reuse += 1;
    else if (action === A.OVERWRITE) s.overwrite += 1;
    else if (action === A.RENAME) s.rename += 1;
    else s.skip += 1;
  }
  s.writes = s.copy + s.overwrite + s.rename;
  return s;
}

/** 요약 줄 문구(`copy.summary`)의 값. */
export function summaryMessage(summary: SelectionSummary): MessageRef {
  const { copy, reuse, overwrite, rename, skip } = summary;
  return { key: "copy.summary", params: { copy, reuse, overwrite, rename, skip } };
}

export interface SubmitState {
  allowed: boolean;
  /** 막힌 이유(화면이 문구를 정한다): 고르지 않음 / 새 이름 문제 / 전부 제외. */
  reason: "need_choice" | "bad_new_id" | "all_skipped" | "empty" | null;
}

/**
 * 제출할 수 있는가. 고르지 않은 항목이 있거나, 새 이름이 올바르지 않거나, 전부 건너뛰면 안 된다.
 * @param targetIds 대상 공간에 이미 있는 정의 id(`kind` 구분 없이 종류별로 묶고 싶으면 호출자가 `takenIds`로 나눠 준다)
 */
export function canSubmit(
  plan: Pick<CopyPlan, "items">,
  selections: CopySelections,
  takenIds: (item: Pick<CopyPlanItem, "kind" | "id">) => Iterable<string> = () => [],
): SubmitState {
  if (itemsOf(plan).length === 0) return { allowed: false, reason: "empty" };
  if (itemsNeedingChoice(plan, selections).length > 0) return { allowed: false, reason: "need_choice" };
  const newIds = new Map<string, string[]>();
  for (const item of itemsOf(plan)) {
    const sel = selections.get(copyItemKey(item));
    if (sel?.action !== A.RENAME) continue;
    const others = [...(newIds.get(item.kind) ?? [])];
    if (validateNewId(sel.newId, [...takenIds(item), ...others]) !== null) return { allowed: false, reason: "bad_new_id" };
    newIds.set(item.kind, [...others, (sel.newId ?? "").trim()]);
  }
  const allSkipped = itemsOf(plan).every((i) => selections.get(copyItemKey(i))?.action === A.SKIP);
  return allSkipped ? { allowed: false, reason: "all_skipped" } : { allowed: true, reason: null };
}

export interface BuildApplyOptions {
  source: SpaceRef;
  target: SpaceRef;
  /** 복사한 뒤 원본에서 지운다(옛 프로젝트 전용 구성을 옮길 때). 기본 false. */
  removeSource?: boolean;
}

/**
 * 선택을 적용 요청으로 만든다. 계획의 `source_version`·`target_version`을 그대로 실어 계획 뒤에 바뀐 항목을 서버가 `conflict`로 돌려주게 한다.
 * 건너뛰는 항목도 `skip`으로 보낸다(서버가 결과에 `skipped`로 기록).
 * 고르지 않은 항목이 있으면 던진다(`canSubmit`으로 먼저 막는다).
 */
export function buildApplyRequest(plan: Pick<CopyPlan, "items">, selections: CopySelections, options: BuildApplyOptions): CopyApplyRequest {
  const items: CopyApplyItem[] = itemsOf(plan).map((item) => {
    const sel = selections.get(copyItemKey(item));
    if (sel === undefined || sel.action === null) throw new Error(`복사 동작을 고르지 않은 항목이 있습니다: ${item.kind}/${item.id}`);
    const out: CopyApplyItem = { kind: item.kind, id: item.id, action: sel.action, source_version: item.source_version };
    if (sel.action === A.RENAME && sel.newId !== undefined) out.new_id = sel.newId.trim();
    if (item.target_version !== undefined && item.target_version !== null) out.target_version = item.target_version;
    return out;
  });
  return { source: options.source, target: options.target, items, remove_source: options.removeSource === true };
}

export type ResultRowKind = "ok" | "skipped" | "conflict" | "error";

export interface ResultRow {
  kind: string;
  id: string;
  newId: string | null;
  status: string;
  rowKind: ResultRowKind;
  /** 상태 문구(`copy.status.…`, 오류는 키 없이 `issue` 메시지를 보인다). */
  label: MessageRef | null;
  /** 서버 이슈 메시지(문구를 화면이 만들지 않는다). */
  issueMessage: string | null;
}

const OK_STATUSES: ReadonlySet<string> = new Set([R.COPIED, R.REUSED, R.OVERWRITTEN, R.RENAMED]);

/** 결과 행 하나의 표시 데이터. 모르는 상태나 `issue`가 있는 행은 오류. */
export function resultRow(item: CopyApplyItemResult): ResultRow {
  const issueMessage = item.issue?.message ?? null;
  const newId = item.new_id ?? null;
  const base = { kind: item.kind, id: item.id, newId, status: item.status, issueMessage };
  if (OK_STATUSES.has(item.status) && issueMessage === null) {
    return { ...base, rowKind: "ok", label: { key: `copy.status.${item.status}`, params: { id: newId ?? item.id } } };
  }
  if (item.status === R.SKIPPED && issueMessage === null) return { ...base, rowKind: "skipped", label: { key: "copy.status.skipped" } };
  if (item.status === R.CONFLICT) return { ...base, rowKind: "conflict", label: { key: "copy.status.conflict" } };
  return { ...base, rowKind: "error", label: null };
}

export interface ResultSummary {
  rows: ResultRow[];
  total: number;
  /** 가져온 것(복사·그대로 씀·덮어씀·새 이름). */
  ok: number;
  skipped: number;
  conflicts: number;
  errors: number;
  /** 충돌·오류가 없다 — 대화상자를 닫고 토스트로 알려도 되는가. */
  allOk: boolean;
  /** `conflict` 행(그 행만 다시 계획할 대상). */
  conflictKeys: { kind: string; id: string }[];
}

/** 적용 결과 요약. */
export function summarizeResult(result: Pick<CopyApplyResult, "items">): ResultSummary {
  const rows = itemsOf(result).map(resultRow);
  const count = (k: ResultRowKind) => rows.filter((r) => r.rowKind === k).length;
  const conflicts = count("conflict");
  const errors = count("error");
  return {
    rows,
    total: rows.length,
    ok: count("ok"),
    skipped: count("skipped"),
    conflicts,
    errors,
    allOk: conflicts === 0 && errors === 0,
    conflictKeys: rows.filter((r) => r.rowKind === "conflict").map((r) => ({ kind: r.kind, id: r.id })),
  };
}

/**
 * 요청한 항목(`reason == requested`) 중 사용할 수 있게 된 첫 번째의 종류·id(새 이름이면 새 id).
 * 새 대화·실행 대화상자가 닫힌 뒤 구성 목록에서 자동 선택할 항목이다. 없으면 null.
 */
export function firstUsableRequested(
  plan: Pick<CopyPlan, "items">,
  result: Pick<CopyApplyResult, "items">,
): { kind: string; id: string } | null {
  const rows = new Map(itemsOf(result).map((i) => [copyItemKey(i), resultRow(i)] as const));
  for (const item of itemsOf(plan)) {
    if (item.reason !== COPY_REASON_REQUESTED) continue;
    const row = rows.get(copyItemKey(item));
    if (row?.rowKind === "ok") return { kind: item.kind, id: row.newId ?? item.id };
  }
  return null;
}

/**
 * 한 행만 다시 계획한 새 계획을 합친다(`conflict` 행 다시 계획). 같은 키의 행은 새 계획 것으로 바꾸고 순서는 유지한다.
 */
export function mergeReplan(plan: CopyPlan, replanned: Pick<CopyPlan, "items">): CopyPlan {
  const fresh = new Map(itemsOf(replanned).map((i) => [copyItemKey(i), i] as const));
  return { ...plan, items: itemsOf(plan).map((i) => fresh.get(copyItemKey(i)) ?? i) };
}
