import type { MemoryAuthor, MemoryScopeKindInfo, MemoryScopeRef, MemoryScopeSummary } from "@agent-console/contracts/memory";
import { hashSlot } from "./format";
import { defaultMessages, formatMessage } from "./messages";

/** 이름 풀기 결과: 이름을 알았다 / 정의 목록이 로드됐는데 그 id가 없다(삭제됨) / 모른다(정의 목록이 없거나 안 불러옴). */
export type NameResolution = { status: "named"; name: string } | { status: "deleted" } | { status: "unknown" };

/**
 * 앱이 주는 이름 풀기 표: 맥락 필드 이름(`graph_id` 등 계약 어휘, 범위 종류 이름이 아님) → (값) → 결과.
 * 해당 필드의 풀이기가 표에 없으면 "모른다"로 본다(정의 목록 역할이 없는 경우).
 */
export type ScopeNameResolvers = Readonly<Record<string, (value: string) => NameResolution>>;

/** 범위 id 틀(`{/graph_id}/{/agent_id}`)의 맥락 필드 이름들(순서대로). 틀이 없으면 빈 목록. */
export function templateFields(template: string | null | undefined): string[] {
  if (!template) return [];
  return [...template.matchAll(/\{\/([^{}/]+)[^{}]*\}/g)].map((m) => m[1] as string);
}

/**
 * 범위 id를 id 틀로 거꾸로 푼다: 틀의 `{/필드}`를 `([^/]*)` 캡처로 바꾼 앵커 정규식. 맞지 않으면 null.
 * 같은 필드가 틀에 두 번 나오면 값이 같아야 맞는다.
 */
export function parseScopeId(template: string | null | undefined, id: string): Record<string, string> | null {
  if (template === null || template === undefined || template === "") return null;
  const names: string[] = [];
  let source = "^";
  let last = 0;
  for (const m of template.matchAll(/\{\/([^{}/]+)[^{}]*\}/g)) {
    source += escapeRegExp(template.slice(last, m.index)) + "([^/]*)";
    names.push(m[1] as string);
    last = (m.index ?? 0) + m[0].length;
  }
  source += escapeRegExp(template.slice(last)) + "$";
  if (names.length === 0) return template === id ? {} : null;
  const match = new RegExp(source).exec(id);
  if (!match) return null;
  const out: Record<string, string> = {};
  for (let i = 0; i < names.length; i += 1) {
    const name = names[i] as string;
    const value = match[i + 1] ?? "";
    if (name in out && out[name] !== value) return null;
    out[name] = value;
  }
  return out;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** 범위의 문자열 표기 `<종류>:<id>`(계약 `MEMORY_SCOPE_SEPARATOR`, 질의 인자 `scope`). */
export function scopeKey(scope: MemoryScopeRef): string {
  return `${scope.kind}:${scope.id ?? ""}`;
}

export function sameScope(a: MemoryScopeRef | null | undefined, b: MemoryScopeRef | null | undefined): boolean {
  if (!a || !b) return a === b;
  return a.kind === b.kind && (a.id ?? "") === (b.id ?? "");
}

// ---------------------------------------------------------------------------------------------
// scopeLabel

export interface ScopeLabelPart {
  text: string;
  /** id 문자열을 그대로 보이는 조각(mono). */
  mono: boolean;
  /** 정의 목록에서 지워진 id. */
  deleted: boolean;
}

export interface ScopeLabel {
  /** 접근 이름·툴팁·정렬에 쓰는 한 줄 글. */
  text: string;
  parts: ScopeLabelPart[];
  /** 조각 중 하나라도 정의에서 지워졌다(칩 "삭제됨"). */
  deleted: boolean;
  /** 범위 종류 정의가 없다(알 수 없는 범위 종류). */
  unknownKind: boolean;
  /** 사용자가 끈 종류. */
  disabledKind: boolean;
  /** 전부 id 문자열이다(mono로 보임). */
  mono: boolean;
}

/**
 * 범위 하나의 사람이 읽는 이름.
 * - 알 수 없는 종류: `종류 id / 범위 id`(mono) + `unknownKind`
 * - id가 빈 문자열이거나 틀이 없다: 종류 라벨
 * - 틀을 맥락 필드로 풀어 필드마다 `resolvers`로 이름을 찾아 " / "로 잇는다. 못 풀면 id 조각(mono), 정의에서 지워졌으면 `deleted`.
 */
export function scopeLabel(scope: MemoryScopeRef, kind: MemoryScopeKindInfo | undefined, resolvers: ScopeNameResolvers = {}, knownKind = true): ScopeLabel {
  const id = scope.id ?? "";
  if (!kind || !knownKind) {
    const text = id === "" ? scope.kind : `${scope.kind} / ${id}`;
    return { text, parts: [{ text, mono: true, deleted: false }], deleted: false, unknownKind: true, disabledKind: false, mono: true };
  }
  const disabledKind = kind.disabled === true;
  const plain = (text: string, mono: boolean): ScopeLabel => ({
    text,
    parts: [{ text, mono, deleted: false }],
    deleted: false,
    unknownKind: false,
    disabledKind,
    mono,
  });
  if (id === "") return plain(kind.label, false);
  const fields = parseScopeId(kind.id, id);
  const names = templateFields(kind.id);
  if (!fields || names.length === 0) return plain(id, true);
  // 틀의 필드 순서대로 값을 풀고, 같은 필드가 반복되면 한 번만 쓴다.
  const parts: ScopeLabelPart[] = [];
  for (const name of [...new Set(names)]) {
    const value = fields[name] ?? "";
    const resolved = resolvers[name]?.(value) ?? ({ status: "unknown" } as const);
    if (resolved.status === "named") parts.push({ text: resolved.name, mono: false, deleted: false });
    else parts.push({ text: value, mono: true, deleted: resolved.status === "deleted" });
  }
  return {
    text: parts.map((p) => p.text).join(" / "),
    parts,
    deleted: parts.some((p) => p.deleted),
    unknownKind: false,
    disabledKind,
    mono: parts.every((p) => p.mono),
  };
}

// ---------------------------------------------------------------------------------------------
// groupScopes

export type ScopeGroupState = "ok" | "disabled" | "unknown";

export interface ScopeGroup {
  /** 범위 종류 id(서버가 준 문자열). */
  kind: string;
  info: MemoryScopeKindInfo | undefined;
  state: ScopeGroupState;
  /** 이 종류의 범위들(라벨 순). 종류 행 자체가 범위인 종류(`selfScope`)는 0~1개. */
  scopes: MemoryScopeSummary[];
  /** 항목 수 합계(보관 포함, 지운 항목 제외). */
  entries: number;
  /** 범위 id가 항상 빈 문자열인 종류: 종류 행이 곧 범위(자식 없음). */
  selfScope: boolean;
}

export interface ScopeGroups {
  /** 켜져 있고 알려진 종류, 서버가 준 순서. 범위가 하나도 없어도 행이 있다. */
  groups: ScopeGroup[];
  /** 알 수 없는 종류·꺼진 종류(나무 맨 아래 "쓸 수 없는 범위"). */
  unavailable: ScopeGroup[];
  /** 모든 범위 항목 수 합계. */
  total: number;
}

export interface GroupScopesOptions {
  /** 한 범위의 정렬 라벨. 없으면 범위 id를 한국어 로케일로 비교. */
  labelOf?: (scope: MemoryScopeSummary, kind: MemoryScopeKindInfo | undefined) => string;
}

const collator = new Intl.Collator("ko");

/**
 * 범위 요약을 종류별로 묶는다(나무의 층: 종류 → 범위). 범위 종류 이름은 어디에서도 비교하지 않는다.
 * 종류 순서는 `kinds`(서버 병합 순서)를 따르고, 같은 종류 안은 라벨 순(최근 수정순이 아님 — 실시간 갱신 때 행이 뛰지 않게).
 */
export function groupScopes(kinds: readonly MemoryScopeKindInfo[], scopes: readonly MemoryScopeSummary[], options: GroupScopesOptions = {}): ScopeGroups {
  const byKind = new Map<string, MemoryScopeKindInfo>();
  for (const k of kinds) byKind.set(k.kind, k);
  const labelOf = options.labelOf ?? ((s: MemoryScopeSummary) => s.scope.id ?? "");
  const known = new Map<string, MemoryScopeSummary[]>();
  const orphan = new Map<string, MemoryScopeSummary[]>();
  for (const s of scopes) {
    const isKnown = byKind.has(s.scope.kind) && s.kind_known !== false;
    const bucket = isKnown ? known : orphan;
    const list = bucket.get(s.scope.kind);
    if (list) list.push(s);
    else bucket.set(s.scope.kind, [s]);
  }
  const make = (kind: string, info: MemoryScopeKindInfo | undefined, state: ScopeGroupState, source: ReadonlyMap<string, MemoryScopeSummary[]>): ScopeGroup => {
    const list = [...(source.get(kind) ?? [])].sort((a, b) => collator.compare(labelOf(a, info), labelOf(b, info)));
    const selfScope = info?.id === "" || (info?.id !== undefined && list.length > 0 && list.every((s) => (s.scope.id ?? "") === ""));
    return { kind, info, state, scopes: list, entries: list.reduce((n, s) => n + s.entries, 0), selfScope };
  };
  const groups: ScopeGroup[] = [];
  const unavailable: ScopeGroup[] = [];
  for (const k of kinds) {
    if (k.disabled === true) unavailable.push(make(k.kind, k, "disabled", known));
    else groups.push(make(k.kind, k, "ok", known));
  }
  for (const kind of orphan.keys()) unavailable.push(make(kind, undefined, "unknown", orphan));
  const total = scopes.reduce((n, s) => n + s.entries, 0);
  return { groups, unavailable, total };
}

// ---------------------------------------------------------------------------------------------
// visibleScopes

export interface VisibleScopesOptions {
  /** 프로젝트 id를 담는 맥락 필드 이름(계약 `KNOWN_MEMORY_CONTEXT_FIELDS.PROJECT_ID`). 기본 `project_id`. */
  projectField?: string;
  /** 팀 구성 id를 담는 맥락 필드 이름(계약 `GRAPH_ID`). 기본 `graph_id`. */
  graphField?: string;
}

export interface VisibleScopes {
  visible: MemoryScopeSummary[];
  /** 프로젝트 거르기로 숨긴 범위(나무 맨 아래 "다른 프로젝트 범위 n개 숨김"의 n = 길이). */
  hidden: MemoryScopeSummary[];
}

/**
 * 프로젝트 전환기 규칙(docs/design/screen-memory.md §3.4)으로 보일 범위를 거른다. 범위 종류 이름은 쓰지 않고
 * 종류의 `context_fields`(틀이 읽는 맥락 필드)와 id 틀로만 판단한다.
 *
 * `project`가 null이면(모든 프로젝트) 거르지 않는다. 프로젝트 P일 때:
 * 1. 범위 id가 ""인 범위(알려진 종류)는 보인다.
 * 2. 틀이 `project_id`를 읽고 그 값이 P인 범위는 보인다.
 * 3. 틀이 `graph_id`를 읽고 그 값이 `graphs`(P에서 보이는 팀 구성 id)에 있는 범위는 보인다.
 * 4. 그 밖(틀이 두 필드를 모른다, 알 수 없는 종류, 틀과 id가 안 맞음)은 숨긴다 — "모든 프로젝트"에서만 보인다.
 * 복합 틀은 틀 전체가 id와 맞아야 하고, 2·3 중 하나만 만족해도 보인다.
 */
export function visibleScopes(
  scopes: readonly MemoryScopeSummary[],
  kinds: readonly MemoryScopeKindInfo[],
  project: string | null,
  graphs: Iterable<string> = [],
  options: VisibleScopesOptions = {},
): VisibleScopes {
  if (project === null) return { visible: [...scopes], hidden: [] };
  const { projectField = "project_id", graphField = "graph_id" } = options;
  const graphSet = new Set(graphs);
  const byKind = new Map(kinds.map((k) => [k.kind, k] as const));
  const visible: MemoryScopeSummary[] = [];
  const hidden: MemoryScopeSummary[] = [];
  for (const s of scopes) {
    const kind = byKind.get(s.scope.kind);
    let show = false;
    if (kind && s.kind_known !== false) {
      const id = s.scope.id ?? "";
      if (id === "") show = true;
      else {
        const fields = kind.context_fields ?? [];
        const parsed = parseScopeId(kind.id, id);
        if (parsed) {
          if (fields.includes(projectField) && parsed[projectField] === project) show = true;
          if (fields.includes(graphField) && graphSet.has(parsed[graphField] ?? "\u0000")) show = true;
        }
      }
    }
    (show ? visible : hidden).push(s);
  }
  return { visible, hidden };
}

// ---------------------------------------------------------------------------------------------
// formatAuthor

export interface FormatAuthorOptions {
  /** 에이전트 id → 이름 풀기(정의 목록). 없으면 모른다. */
  resolveAgent?: (agentId: string) => NameResolution;
  /** 문구 표(없으면 기본). */
  messages?: Readonly<Record<string, string>>;
  /** 쓴 주체가 `system`일 때 원인. 생략하면 `label`(규칙 id)이 있으면 정리, 없으면 가져오기. */
  systemCause?: "retention" | "import";
  /** `--ac-cat-N` 슬롯 수. 기본 8. */
  colorSlots?: number;
}

export interface FormattedAuthor {
  /** 계약 어휘면 그 값, 모르면 원문. */
  kind: string;
  /** 칸에 보이는 이름 글자(칩이면 칩 글자). */
  text: string;
  /** 글자를 mono로(풀지 못한 에이전트 id·규칙 id). */
  mono: boolean;
  /** 칩으로 보인다(사용자·정리·가져오기). */
  chip: boolean;
  /** 에이전트 아바타 첫 글자와 색 슬롯(1..n). 에이전트가 아니면 null. */
  avatar: { initial: string; slot: number } | null;
  /** 정의에서 지워진 에이전트(이름 뒤 툴팁만). */
  deletedAgent: boolean;
  /** 정리 규칙 id(칩 뒤 mono). */
  ruleId: string | null;
  /** 풀 이름 + 노드 경로 + 실행 id를 줄로 이은 툴팁. */
  tooltip: string;
}

/** 쓴 주체를 칸에 맞게 정리한다(docs/design/screen-memory.md §4.3). 모르는 `kind`는 원문. */
export function formatAuthor(author: MemoryAuthor, options: FormatAuthorOptions = {}): FormattedAuthor {
  const m = { ...defaultMessages, ...options.messages } as Readonly<Record<string, string>>;
  const lines: string[] = [];
  const path = (author.node_path ?? []).join(" › ");
  const finish = (base: Omit<FormattedAuthor, "tooltip" | "kind">): FormattedAuthor => {
    if (path) lines.push(path);
    if (author.run_id) lines.push(author.run_id);
    return { kind: author.kind, ...base, tooltip: lines.join("\n") };
  };
  if (author.kind === "agent") {
    const id = author.agent_id ?? "";
    const resolved = id ? options.resolveAgent?.(id) : undefined;
    let name: string;
    let mono = false;
    let deletedAgent = false;
    if (author.label) name = author.label;
    else if (resolved?.status === "named") name = resolved.name;
    else {
      name = id || (m["author.deletedAgent"] as string);
      mono = id !== "";
      deletedAgent = resolved?.status === "deleted";
    }
    lines.push(formatMessage(m["author.agent"] as string, { name }) + (deletedAgent ? ` ${m["author.deletedAgent"]}` : ""));
    return finish({ text: name, mono, chip: false, avatar: { initial: [...name][0] ?? "?", slot: hashSlot(id || name, options.colorSlots ?? 8) }, deletedAgent, ruleId: null });
  }
  if (author.kind === "user") {
    const text = author.label ?? (m["author.user"] as string);
    lines.push(text);
    return finish({ text, mono: false, chip: true, avatar: null, deletedAgent: false, ruleId: null });
  }
  if (author.kind === "system") {
    const cause = options.systemCause ?? (author.label ? "retention" : "import");
    const text = m[`author.system.${cause}`] as string;
    lines.push(author.label ? `${text} ${author.label}` : text);
    return finish({ text, mono: false, chip: true, avatar: null, deletedAgent: false, ruleId: author.label ?? null });
  }
  lines.push(author.kind);
  return finish({ text: author.label ?? author.kind, mono: false, chip: false, avatar: null, deletedAgent: false, ruleId: null });
}
