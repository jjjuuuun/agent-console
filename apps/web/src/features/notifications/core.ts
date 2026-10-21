/**
 * 브라우저 알림 판정·문구·이동 대상 계산(순수 함수, 외부 의존 없음. design §2R.11, screens-v3 §7.2).
 * 이벤트 이름·필드 경로는 코드에 고정하지 않는다: 이름은 설정(`ui.notifications.events`) 데이터이고,
 * 이동 대상은 payload의 데이터 필드(`ROUTING_FIELDS`)가 있는지로만 정한다.
 */

export type PermissionState = "unsupported" | "default" | "granted" | "denied";

/** 계약 `NotificationSettings`를 기본값으로 채운 값. */
export interface NotifySettings {
  enabled: boolean;
  sound: boolean;
  events: readonly string[];
  onlyWhenHidden: boolean;
}

export interface NotifyEvent {
  /** 설정 `events`와 정확히 일치를 비교하는 이름 */
  name: string;
  data: Record<string, unknown>;
  /** 이벤트 시각(밀리초). 없으면 모름 */
  ts?: number;
}

/** 서버 메시지 하나를 알림 후보 이름으로 바꾸는 별칭 규칙(데이터). 조건(when 필드)이 없으면 그 type이면 항상 적용. */
export interface EventAlias {
  type: string;
  when?: { path: string; equals: unknown };
  as: string;
}

/** payload에서 이동 대상을 찾는 필드 경로(점 표기). 앞에 있는 것이 우선. 데이터이며 이름 접두어로 판별하지 않는다. */
export interface RoutingFields {
  interactionId: readonly string[];
  conversationId: readonly string[];
  runId: readonly string[];
  /** 요청한 에이전트 id */
  actor: readonly string[];
  /** 요청 시점 노드 표시 이름 */
  nodeLabel: readonly string[];
}

export const ROUTING_FIELDS: RoutingFields = {
  interactionId: ["interaction_id", "interaction.id"],
  conversationId: ["conversation_id", "interaction.conversation_id"],
  runId: ["run_id", "interaction.run_id"],
  actor: ["actor", "interaction.actor"],
  nodeLabel: ["node_label", "interaction.node_label"],
};

/** 점 표기 경로로 중첩 값을 읽는다. */
export function readPath(data: unknown, path: string): unknown {
  let cur: unknown = data;
  for (const key of path.split(".")) {
    if (typeof cur !== "object" || cur === null) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur;
}

/** 경로 목록 중 처음으로 비어 있지 않은 문자열이 나오는 값. */
export function firstString(data: unknown, paths: readonly string[]): string | undefined {
  for (const p of paths) {
    const v = readPath(data, p);
    if (typeof v === "string" && v !== "") return v;
  }
  return undefined;
}

/** 메시지 한 건을 알림 후보로. `run.event`는 안쪽 이벤트의 type을 이름으로 쓰고, 그 밖에는 메시지 type이 이름이다. */
export function toNotifyEvents(message: { type: string; payload?: unknown }, aliases: readonly EventAlias[] = []): NotifyEvent[] {
  const payload = (typeof message.payload === "object" && message.payload !== null ? message.payload : {}) as Record<string, unknown>;
  let base: NotifyEvent;
  if (message.type === "run.event" && typeof payload["type"] === "string") {
    const inner = (typeof payload["payload"] === "object" && payload["payload"] !== null ? payload["payload"] : {}) as Record<string, unknown>;
    const ts = typeof payload["ts"] === "number" ? payload["ts"] * 1000 : undefined;
    base = { name: payload["type"], data: { ...inner, run_id: payload["run_id"], actor: payload["actor"] ?? inner["actor"] }, ...(ts === undefined ? {} : { ts }) };
  } else {
    const created = readPath(payload, "interaction.created_at");
    base = { name: message.type, data: payload, ...(typeof created === "number" ? { ts: created * 1000 } : {}) };
  }
  const out = [base];
  for (const a of aliases) {
    if (a.type !== message.type) continue;
    if (a.when !== undefined && readPath(payload, a.when.path) !== a.when.equals) continue;
    if (a.as !== base.name) out.push({ ...base, name: a.as });
  }
  return out;
}

export interface ShouldNotifyInput {
  settings: NotifySettings;
  eventName: string;
  permission: PermissionState;
  /** `document.visibilityState === "hidden"` */
  hidden: boolean;
  /** 사용자가 지금 보고 있는 대화/실행의 이벤트인가 */
  viewing: boolean;
}

/** 시스템 알림(소리 포함)을 낼지. */
export function shouldNotify({ settings, eventName, permission, hidden, viewing }: ShouldNotifyInput): boolean {
  if (!settings.enabled || permission !== "granted") return false;
  if (!settings.events.includes(eventName)) return false;
  if (settings.onlyWhenHidden) return hidden;
  return hidden || !viewing;
}

export type NotifyTarget =
  | { kind: "conversation"; conversationId: string; interactionId?: string }
  | { kind: "run"; runId: string }
  | { kind: "none" };

/** 이동 대상: 상호작용·대화 id가 있으면 대화, 아니면 실행 id가 있으면 실행, 그 외는 없음. */
export function resolveTarget(data: Record<string, unknown>, fields: RoutingFields = ROUTING_FIELDS): NotifyTarget {
  const conversationId = firstString(data, fields.conversationId);
  const interactionId = firstString(data, fields.interactionId);
  if (conversationId !== undefined) return { kind: "conversation", conversationId, ...(interactionId === undefined ? {} : { interactionId }) };
  const runId = firstString(data, fields.runId);
  if (runId !== undefined) return { kind: "run", runId };
  return { kind: "none" };
}

/** 같은 대화/실행 + 같은 이벤트는 같은 tag(새 알림이 이전 것을 대체). */
export function notificationTag(name: string, target: NotifyTarget): string {
  const scope = target.kind === "conversation" ? `c:${target.conversationId}` : target.kind === "run" ? `r:${target.runId}` : "-";
  return `${scope}|${name}`;
}

export interface NameLookups {
  /** 에이전트 id -> 표시 이름 */
  actorName?: (id: string) => string | undefined;
  /** 이동 대상 -> 대화/실행 제목 */
  titleOf?: (target: NotifyTarget) => string | undefined;
}

/** 요청자 이름: actor 표시 이름 -> node_label -> 대화/실행 제목 -> 없음. */
export function requesterName(data: Record<string, unknown>, target: NotifyTarget, lookups: NameLookups = {}, fields: RoutingFields = ROUTING_FIELDS): string | undefined {
  const actor = firstString(data, fields.actor);
  const actorLabel = actor === undefined ? undefined : lookups.actorName?.(actor);
  return actorLabel ?? firstString(data, fields.nodeLabel) ?? lookups.titleOf?.(target);
}

export const BODY_MAX = 120;

export function truncate(text: string, max: number = BODY_MAX): string {
  const chars = Array.from(text);
  return chars.length <= max ? text : `${chars.slice(0, max - 1).join("")}…`;
}

/**
 * 알림 본문. 이벤트 이름에 맞는 템플릿이 있으면 그것을, 없으면 `{이름} · {요청자}`(요청자 없으면 이름만).
 * 템플릿은 `{requester}` 조각을 쓸 수 있으며 값이 없으면 그 조각과 앞뒤 구분자를 지운다.
 */
export function buildBody(name: string, requester: string | undefined, templates: Readonly<Record<string, string>> = {}): string {
  const template = templates[name];
  if (template !== undefined) {
    const filled = requester === undefined ? template.replace(/\s*[·:,-]?\s*\{requester\}/g, "").replace(/\{requester\}\s*[·:,-]?\s*/g, "") : template.replaceAll("{requester}", requester);
    return truncate(filled.trim());
  }
  return truncate(requester === undefined ? name : `${name} · ${requester}`);
}
