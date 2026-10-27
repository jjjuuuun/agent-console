/**
 * 테스트·예제용 표본 데이터. 범위 종류 이름은 일부러 기본 종류와 무관한 낱말로 지었다(코드가 이름을 모른다는 시험용).
 * 계약 모양(`@agent-console/contracts/memory`)을 그대로 따른다.
 */
import type {
  MemoryAuthor, MemoryEntrySummary, MemoryRetentionPlan, MemoryScopeKindInfo, MemoryScopeRef, MemoryScopeSummary, MemoryVersionSummary,
} from "@agent-console/contracts/memory";

export const SAMPLE_NOW = 1_795_000_000;

/** 범위 종류 5개: 범위 id 없음 / 팀 구성 id / 프로젝트 id / 복합 틀 / 계산 범위(틀 없음). */
export function sampleKinds(): MemoryScopeKindInfo[] {
  return [
    { kind: "ledger", label: "장부", id: "", origin: "user", context_fields: [] },
    { kind: "desk", label: "책상", id: "{/graph_id}", origin: "user", context_fields: ["graph_id"] },
    { kind: "cabinet", label: "서랍", id: "{/project_id}", origin: "user", context_fields: ["project_id"] },
    { kind: "pair", label: "짝", id: "{/graph_id}/{/agent_id}", origin: "plugin:example", context_fields: ["graph_id", "agent_id"] },
    { kind: "weekly", label: "주간", id: null, origin: "plugin:example", context_fields: [] },
  ];
}

/** 종류 id를 다른 낱말로 바꾼 사본(종류 목록과 범위 요약 둘 다). 결과가 같아야 하는 시험에 쓴다. */
export function renameKinds(
  kinds: readonly MemoryScopeKindInfo[], scopes: readonly MemoryScopeSummary[], rename: (kind: string) => string,
): { kinds: MemoryScopeKindInfo[]; scopes: MemoryScopeSummary[] } {
  return {
    kinds: kinds.map((k) => ({ ...k, kind: rename(k.kind), label: `${rename(k.kind)}-label` })),
    scopes: scopes.map((s) => ({ ...s, scope: { ...s.scope, kind: rename(s.scope.kind) } })),
  };
}

function summary(scope: MemoryScopeRef, entries: number, extra: Partial<MemoryScopeSummary> = {}): MemoryScopeSummary {
  return { scope, entries, archived: 0, bytes: entries * 100, updated_at: SAMPLE_NOW - 60, kind_known: true, ...extra };
}

/** 범위 요약 표본: 프로젝트 P1·P2, 팀 구성 g1(P1)·g2(P2), 모르는 틀, 알 수 없는 종류 하나. */
export function sampleScopes(): MemoryScopeSummary[] {
  return [
    summary({ kind: "ledger", id: "" }, 12),
    summary({ kind: "desk", id: "g1" }, 60),
    summary({ kind: "desk", id: "g2" }, 28),
    summary({ kind: "cabinet", id: "P1" }, 31),
    summary({ kind: "cabinet", id: "P2" }, 9),
    summary({ kind: "pair", id: "g1/a1" }, 4),
    summary({ kind: "pair", id: "g2/a1" }, 5),
    summary({ kind: "pair", id: "broken" }, 1),
    summary({ kind: "weekly", id: "2026-W44" }, 2),
    summary({ kind: "gone", id: "x" }, 3, { kind_known: false }),
  ];
}

export function sampleAuthor(kind: "agent" | "user" | "system" = "agent", extra: Partial<MemoryAuthor> = {}): MemoryAuthor {
  if (kind === "agent") return { kind, agent_id: "a1", run_id: "run-1234567890", node_path: [], ...extra };
  if (kind === "system") return { kind, label: "stale-rule", ...extra };
  return { kind, ...extra };
}

/** 항목 요약 n개(키는 `a/b/entry-<i>`, 최근 수정순). */
export function makeEntries(n: number, base: Partial<MemoryEntrySummary> = {}): MemoryEntrySummary[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `e${i}`,
    scope: { kind: "desk", id: "g1" },
    key: `a/b/entry-${i}`,
    content_type: "text/markdown",
    tags: i % 3 === 0 ? ["t1", "t2", "t3"] : [],
    pinned: i === 0,
    archived: false,
    version: (i % 5) + 1,
    bytes: 100 + i,
    sha256: "0123456789abcdef".repeat(4),
    created_at: SAMPLE_NOW - 86_400,
    created_by: sampleAuthor("user"),
    updated_at: SAMPLE_NOW - i * 60,
    updated_by: sampleAuthor("agent"),
    preview: `본문 앞부분 ${i}`,
    ...base,
  }));
}

/** 버전 요약 표본(오래된 순으로 만든 뒤 호출자가 섞어도 목록이 최신순으로 보인다). */
export function sampleVersions(): MemoryVersionSummary[] {
  const common = { entry_id: "e1", scope: { kind: "desk", id: "g1" }, key: "a/b", sha256: "f".repeat(64) };
  return [
    { ...common, version: 1, op: "create", bytes: 100, author: sampleAuthor("agent"), at: SAMPLE_NOW - 5 * 86_400 },
    { ...common, version: 2, op: "update", bytes: 140, author: sampleAuthor("user"), at: SAMPLE_NOW - 3600 },
    { ...common, version: 3, op: "archive", bytes: 140, author: sampleAuthor("system"), at: SAMPLE_NOW - 600 },
    { ...common, version: 4, op: "move", key: "a/c", bytes: 128, author: sampleAuthor("user"), at: SAMPLE_NOW - 60 },
    { ...common, version: 5, op: "future-op" as MemoryVersionSummary["op"], bytes: 128, author: { kind: "robot", label: "r2" }, at: SAMPLE_NOW - 10 },
  ];
}

/** 정리 계획 표본. */
export function samplePlan(n = 3): MemoryRetentionPlan {
  return {
    count: n,
    truncated: false,
    items: Array.from({ length: n }, (_, i) => ({
      entry_id: `e${i}`, scope: { kind: "desk", id: "g1" }, key: `tmp/item-${i}`, version: 1, rule: "stale", action: i % 2 === 0 ? "archive" : "delete",
    })),
  };
}
