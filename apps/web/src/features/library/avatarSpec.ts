import { categoryColorVar, firstGlyph, safeCssColor, safeIconText } from "@agent-console/graph-editor";

/** 화면에 그릴 아바타 한 개(글자 + CSS 배경색). 채팅·노드 카드·패널·실행 상세·진행 줄이 모두 이 결과를 쓴다. */
export interface AvatarSpec {
  text: string;
  color: string;
}

/** 색 후보 이름 토큰: 분류색 팔레트 칸 번호(`1`~`8`). 후보 목록은 여기 한 곳에서 만든다. */
export const AVATAR_COLOR_TOKENS: readonly string[] = Array.from({ length: 8 }, (_, i) => String(i + 1));

/** 에이전트 `attributes.ui`의 `icon`·`color`(문자열이 아니면 없는 것으로 본다). */
export function readAvatarUi(attributes: Readonly<Record<string, unknown>> | null | undefined): { icon: string; color: string } {
  const ui = attributes?.["ui"];
  const rec = typeof ui === "object" && ui !== null && !Array.isArray(ui) ? (ui as Record<string, unknown>) : {};
  return { icon: typeof rec["icon"] === "string" ? rec["icon"] : "", color: typeof rec["color"] === "string" ? rec["color"] : "" };
}

/** 색 값 해석: 토큰 이름(`3`·`cat-3`) → 팔레트 변수, 안전한 CSS 색 → 그대로, 그 밖 → undefined. */
export function resolveAvatarColor(value: string): string | undefined {
  const v = value.trim();
  const m = /^(?:cat-)?([1-8])$/.exec(v);
  if (m) return `var(--ac-cat-${m[1]})`;
  return safeCssColor(v);
}

/**
 * 해석 함수. `attributes.ui.icon`(1~2자) → 없으면 이름 첫 글자, `attributes.ui.color` → 없으면 id 해시 색.
 * `attributes.ui`를 못 읽으면 기본(첫 글자 + 해시 색)으로 돌아간다.
 */
export function resolveAvatar(agent: { id: string; name: string; attributes?: Readonly<Record<string, unknown>> | null | undefined }): AvatarSpec {
  const ui = readAvatarUi(agent.attributes);
  return {
    text: safeIconText(ui.icon) ?? firstGlyph(agent.name || agent.id),
    color: resolveAvatarColor(ui.color) ?? categoryColorVar(agent.id),
  };
}

/** 표시 값을 `attributes.ui`에 쓴다. 둘 다 비면 `ui` 키를 지우고, `ui` 안의 다른 키는 보존한다. */
export function withAvatarUi(attributes: Readonly<Record<string, unknown>> | undefined, patch: Partial<{ icon: string; color: string }>): Record<string, unknown> | undefined {
  const next: Record<string, unknown> = { ...(attributes ?? {}) };
  const old = next["ui"];
  const ui: Record<string, unknown> = typeof old === "object" && old !== null && !Array.isArray(old) ? { ...(old as Record<string, unknown>) } : {};
  for (const [k, v] of Object.entries(patch)) {
    if (v === undefined || v === "") delete ui[k];
    else ui[k] = v;
  }
  if (Object.keys(ui).length === 0) delete next["ui"];
  else next["ui"] = ui;
  return Object.keys(next).length === 0 ? undefined : next;
}

/**
 * 팀 그래프 노드 → 묶인 에이전트의 아바타(노드 카드용). 노드 타입의 `binds`(정의 종류·config 필드)로 에이전트를 찾고,
 * 에이전트에 묶이지 않은 노드는 키를 만들지 않는다(그 노드는 노드 타입 힌트로 그린다).
 */
export function nodeAvatarsOf(
  nodes: readonly { id: string; type: string; config?: Readonly<Record<string, unknown>> | null | undefined }[],
  nodeTypes: readonly { id: string; binds?: { kind: string; field: string } | null | undefined }[],
  agents: readonly { id: string; name: string; kind?: string | undefined; attributes?: Readonly<Record<string, unknown>> | null | undefined }[],
): Record<string, AvatarSpec> {
  const types = new Map(nodeTypes.map((t) => [t.id, t.binds]));
  const byId = new Map(agents.map((a) => [a.id, a]));
  const out: Record<string, AvatarSpec> = {};
  for (const node of nodes) {
    const binds = types.get(node.type);
    if (binds == null) continue;
    const ref = node.config?.[binds.field];
    const agent = typeof ref === "string" ? byId.get(ref) : undefined;
    if (agent !== undefined && (agent.kind === undefined || agent.kind === binds.kind)) out[node.id] = resolveAvatar(agent);
  }
  return out;
}
