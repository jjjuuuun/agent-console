/**
 * 선언형 배지·칩: 노드/엣지 타입 디스크립터의 `ui_hints.badges` / `ui_hints.chips`를 해석한다.
 * 형식은 design.md "선언형 배지·칩". 노드 타입·config 키 이름을 코드에 두지 않고 디스크립터 데이터만 읽는다.
 */
import type { GraphEditorMessages } from "../messages";

/** 조건 하나. 한 객체 안의 키는 모두 만족해야 한다(AND). 모르는 키가 있으면 불만족. */
export interface DeclaredCondition {
  /** 점으로 이은 config 경로(예: "a.b"). 값 검사 키(exists/equals/not_equals/in)와 함께 쓴다 */
  config_path?: string;
  /** config_path에 값이 있는가(기본: 값 검사 키가 없으면 true = 존재) */
  exists?: boolean;
  equals?: unknown;
  not_equals?: unknown;
  in?: unknown[];
  /** 이 노드로 들어오는 엣지 중 이 `scheduling` 값을 가진 것이 있다(노드 전용) */
  incoming_scheduling?: string;
  /** 이 노드에서 나가는 엣지 중 이 `scheduling` 값을 가진 것이 있다(노드 전용) */
  outgoing_scheduling?: string;
}

export interface DeclaredItem {
  /** `messages.hintLabels[label_key]`로 찾는 문구 키 */
  label_key?: string;
  /** 문구 직접 지정(label_key를 못 찾았을 때 폴백) */
  label?: string;
  /** 노드·엣지 `config` 안의 값을 문구로 쓴다(RFC 6901 포인터, 예 "/label"). 문자열·숫자만, 비거나 없으면 그리지 않는다 */
  value_pointer?: string;
  /** 놓이는 자리. `title` = 엣지 라벨 칩 안에서 종류 title 뒤. 생략·모르는 값 = 작은 칩 */
  placement?: string;
  /** 생략 = 항상 표시. 배열 = 하나라도 만족(OR) */
  when?: DeclaredCondition | DeclaredCondition[];
}

export interface DeclaredContext {
  config?: Record<string, unknown> | undefined;
  /** 이 노드로 들어오는 엣지들의 scheduling 값(엣지 타입에는 쓰지 않음) */
  incomingScheduling?: readonly string[];
  outgoingScheduling?: readonly string[];
}

const KNOWN = new Set(["config_path", "exists", "equals", "not_equals", "in", "incoming_scheduling", "outgoing_scheduling"]);

function getPath(root: unknown, path: string): unknown {
  let cur: unknown = root;
  for (const key of path.split(".")) {
    if (cur === null || typeof cur !== "object" || !(key in (cur as object))) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur;
}

const sameValue = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b);

/** 조건 한 객체 평가. */
export function evaluateCondition(c: DeclaredCondition, ctx: DeclaredContext): boolean {
  if (c === null || typeof c !== "object") return false;
  if (Object.keys(c).some((k) => !KNOWN.has(k))) return false;
  if (c.config_path !== undefined) {
    const v = getPath(ctx.config, c.config_path);
    const present = v !== undefined && v !== null;
    const hasValueTest = c.equals !== undefined || c.not_equals !== undefined || c.in !== undefined;
    if (c.exists !== undefined) {
      if (present !== c.exists) return false;
    } else if (!hasValueTest && !present) return false;
    if (c.equals !== undefined && !sameValue(v, c.equals)) return false;
    if (c.not_equals !== undefined && sameValue(v, c.not_equals)) return false;
    if (c.in !== undefined && !(Array.isArray(c.in) && c.in.some((x) => sameValue(x, v)))) return false;
  } else if (c.exists !== undefined || c.equals !== undefined || c.not_equals !== undefined || c.in !== undefined) {
    return false; // 값 검사에는 config_path가 필요
  }
  if (c.incoming_scheduling !== undefined && !(ctx.incomingScheduling ?? []).includes(c.incoming_scheduling)) return false;
  if (c.outgoing_scheduling !== undefined && !(ctx.outgoingScheduling ?? []).includes(c.outgoing_scheduling)) return false;
  return true;
}

/** `when` 평가: 없으면 true, 배열은 OR. */
export function evaluateWhen(when: DeclaredItem["when"], ctx: DeclaredContext): boolean {
  if (when === undefined) return true;
  if (Array.isArray(when)) return when.some((c) => evaluateCondition(c, ctx));
  return evaluateCondition(when, ctx);
}

/** RFC 6901 포인터로 값을 읽는다. 문자열·숫자만 문구가 되고 그 밖(없음·빈 문자열·객체)은 undefined. */
export function readValuePointer(root: unknown, pointer: string): string | undefined {
  if (pointer === "" || !pointer.startsWith("/")) return undefined;
  let cur: unknown = root;
  for (const raw of pointer.slice(1).split("/")) {
    const key = raw.replace(/~1/g, "/").replace(/~0/g, "~");
    if (cur === null || typeof cur !== "object" || !Object.hasOwn(cur, key)) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  if (typeof cur === "string") return cur === "" ? undefined : cur;
  if (typeof cur === "number" && Number.isFinite(cur)) return String(cur);
  return undefined;
}

/** 선언 항목 하나를 평가한 결과. */
export interface DeclaredText {
  text: string;
  /** 선언의 `placement`(없으면 undefined) */
  placement?: string;
}

/**
 * `ui_hints[key]`(badges 또는 chips) 항목을 평가해 보일 문구와 자리를 돌려준다.
 * 형식이 틀린 항목은 건너뛴다. 문구: `value_pointer`의 값 → `messages.hintLabels[label_key]` → `label` → `label_key` 순.
 */
export function declaredTexts(
  hints: { [k: string]: unknown } | null | undefined,
  key: "badges" | "chips",
  ctx: DeclaredContext,
  messages: Pick<GraphEditorMessages, "hintLabels">,
): DeclaredText[] {
  const raw = hints?.[key];
  if (!Array.isArray(raw)) return [];
  const out: DeclaredText[] = [];
  for (const item of raw as unknown[]) {
    if (item === null || typeof item !== "object") continue;
    const it = item as DeclaredItem;
    const text =
      typeof it.value_pointer === "string"
        ? readValuePointer(ctx.config, it.value_pointer)
        : (typeof it.label_key === "string" ? messages.hintLabels[it.label_key] : undefined) ??
          (typeof it.label === "string" ? it.label : undefined) ??
          (typeof it.label_key === "string" ? it.label_key : undefined);
    if (text === undefined || text === "") continue;
    if (!evaluateWhen(it.when, ctx)) continue;
    const placement = typeof it.placement === "string" ? it.placement : undefined;
    if (out.some((o) => o.text === text && o.placement === placement)) continue;
    out.push(placement === undefined ? { text } : { text, placement });
  }
  return out;
}

/** `declaredTexts`의 문구만(자리 무시, 같은 문구 한 번). 노드 배지·칩처럼 자리 구분이 없는 곳에 쓴다. */
export function declaredLabels(
  hints: { [k: string]: unknown } | null | undefined,
  key: "badges" | "chips",
  ctx: DeclaredContext,
  messages: Pick<GraphEditorMessages, "hintLabels">,
): string[] {
  const out: string[] = [];
  for (const t of declaredTexts(hints, key, ctx, messages)) if (!out.includes(t.text)) out.push(t.text);
  return out;
}
