import type { GraphSummary, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import type { BindSummary, ChipView, DefinitionItem } from "@agent-console/graph-editor";
import { DEFAULT_TEAM_CONVENTIONS, stringAt, type TeamConventions } from "./conventions";
import { delegationMessages as t } from "./messages";

/** 중첩 후보 정의 한 건(정의 요약 목록에서). 입구 수·노드 수를 모르면 생략한다(카드 부제는 이름만). */
export interface NestedInfo {
  id: string;
  name: string;
  nodeCount?: number | undefined;
  /** 입구 이름들 */
  entries?: readonly string[] | undefined;
}

/** 팀 구성 요약(`GET /graphs`)에서 중첩 후보 정보를 만든다. */
export function nestedInfoOf(summaries: readonly Pick<GraphSummary, "id" | "name" | "node_count" | "entry_labels">[]): NestedInfo[] {
  return summaries.map((s) => ({ id: s.id, name: s.name, nodeCount: s.node_count, ...(s.entry_labels != null ? { entries: s.entry_labels } : {}) }));
}

/** 팔레트 "정의에서 만드는 노드"의 중첩 정의 목록: 이름 오름차순(한글 로케일), 자기 자신은 비활성 사유. */
export function nestedDefinitionList(infos: readonly NestedInfo[], currentId: string, counts: ReadonlyMap<string, number> | ((id: string) => number) = new Map()): DefinitionItem[] {
  const countOf = typeof counts === "function" ? counts : (id: string) => counts.get(id) ?? 0;
  return [...infos]
    .sort((a, b) => a.name.localeCompare(b.name, "ko"))
    .map((info) => {
      const meta = info.nodeCount === undefined ? undefined : t.nested.infoMeta(info.nodeCount, info.entries && info.entries.length > 0 ? `${info.entries.length}` : "");
      return {
        id: info.id,
        name: info.name,
        ...(meta !== undefined ? { meta } : {}),
        usageCount: countOf(info.id),
        ...(info.id === currentId ? { disabledReason: t.nested.notAllowedSelf } : {}),
      };
    });
}

export interface BindSummaryContext {
  /** 지금 편집 중인 정의 종류(`binds.kind`와 비교만 한다) */
  currentKind: string | undefined;
  /** 지금 편집 중인 정의 id(자기 참조 판정) */
  currentId: string;
  /** 중첩 후보 정보. 아직 못 읽었으면 undefined(이름 로딩 중) */
  infos: readonly NestedInfo[] | undefined;
  /** 정의 종류 표시 이름(부제, 예: 정의 종류 제목 표) */
  kindTitle: string | undefined;
  conventions?: TeamConventions;
  /** [열기]. 정의 종류 라우트를 찾지 못하면 undefined(버튼 없음) */
  open?: ((id: string) => void) | undefined;
}

/**
 * 중첩 노드(`binds.kind`가 지금 편집 중인 정의 종류와 같은 노드)의 카드 요약. 그 밖의 노드는 undefined.
 * 정의 id는 `binds.field` 위치의 config 값이고, 버전 고정은 `TeamConventions.nodePinVersion` 위치다.
 */
export function buildBindSummary(node: NodeSpec, nodeType: Pick<NodeTypeDescriptor, "binds"> | undefined, ctx: BindSummaryContext): BindSummary | undefined {
  const binds = nodeType?.binds;
  if (binds == null || ctx.currentKind === undefined || binds.kind !== ctx.currentKind) return undefined;
  const conventions = ctx.conventions ?? DEFAULT_TEAM_CONVENTIONS;
  const id = stringAt(node.config, `/${binds.field.replace(/~/g, "~0").replace(/\//g, "~1")}`);
  if (id === undefined) return { title: node.label ?? node.id, ...(ctx.kindTitle ? { subtitle: ctx.kindTitle } : {}), missing: true };
  const info = ctx.infos?.find((x) => x.id === id);
  const loaded = ctx.infos !== undefined;
  const self = id === ctx.currentId;
  const pin = stringAt(node.config, conventions.nodePinVersion);
  const badges: ChipView[] = [];
  if (pin !== undefined) badges.push({ key: "pin", title: t.nested.pinned(pin.slice(0, 7)), fullTitle: t.nested.pinnedHint, tone: "neutral" });
  if (self) badges.push({ key: "self", title: `⚠ ${t.nested.self}`, tone: "danger" });
  const missing = loaded && info === undefined && !self;
  if (missing) badges.push({ key: "missing", title: `⚠ ${t.nested.missing}`, tone: "danger" });
  const name = info?.name ?? id;
  const meta = info?.nodeCount === undefined ? undefined : t.nested.infoMeta(info.nodeCount, info.entries && info.entries.length > 0 ? `${info.entries.length}` : "");
  return {
    title: name,
    ...(missing ? { subtitle: t.nested.missingSubtitle(id) } : ctx.kindTitle ? { subtitle: ctx.kindTitle } : {}),
    ...(meta !== undefined && !missing ? { meta } : {}),
    ...(badges.length > 0 ? { badges } : {}),
    ...(missing ? { missing: true } : {}),
    ...((info !== undefined || self) && ctx.open !== undefined ? { open: { label: t.nested.open, onOpen: () => ctx.open?.(id) } } : {}),
  };
}

/** 그래프 전체 노드의 요약 표(편집기 `bindSummaries`). 요약이 없는 노드는 키를 만들지 않는다. */
export function deriveBindSummaries(nodes: readonly NodeSpec[], nodeTypes: readonly NodeTypeDescriptor[], ctx: BindSummaryContext): Record<string, BindSummary> {
  const types = new Map(nodeTypes.map((n) => [n.id, n]));
  const out: Record<string, BindSummary> = {};
  for (const node of nodes) {
    const s = buildBindSummary(node, types.get(node.type), ctx);
    if (s !== undefined) out[node.id] = s;
  }
  return out;
}
