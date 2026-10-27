import { describe, expect, it } from "vitest";
import { formatAuthor, groupScopes, parseScopeId, scopeLabel, templateFields, visibleScopes, type ScopeNameResolvers } from "./scopes";
import { renameKinds, sampleAuthor, sampleKinds, sampleScopes } from "./testing";

const kinds = sampleKinds();
const scopes = sampleScopes();

describe("id 틀", () => {
  it("틀의 맥락 필드를 순서대로 뽑는다", () => {
    expect(templateFields("{/graph_id}/{/agent_id}")).toEqual(["graph_id", "agent_id"]);
    expect(templateFields("")).toEqual([]);
    expect(templateFields(null)).toEqual([]);
  });
  it("범위 id를 틀로 거꾸로 푼다", () => {
    expect(parseScopeId("{/graph_id}/{/agent_id}", "g1/a1")).toEqual({ graph_id: "g1", agent_id: "a1" });
    expect(parseScopeId("{/graph_id}/{/agent_id}", "broken")).toBeNull();
    expect(parseScopeId("{/a}", "x/y")).toBeNull();
    expect(parseScopeId("{/a}-{/a}", "q-q")).toEqual({ a: "q" });
    expect(parseScopeId("{/a}-{/a}", "q-r")).toBeNull();
    expect(parseScopeId("", "x")).toBeNull();
    expect(parseScopeId(null, "x")).toBeNull();
  });
});

describe("groupScopes", () => {
  const g = groupScopes(kinds, scopes);
  it("종류는 서버 순서, 켜져 있고 범위가 없는 종류도 행이 있다", () => {
    expect(g.groups.map((x) => x.kind)).toEqual(["ledger", "desk", "cabinet", "pair", "weekly"]);
    expect(g.groups.find((x) => x.kind === "weekly")?.entries).toBe(2);
    const empty = groupScopes(kinds, []);
    expect(empty.groups).toHaveLength(5);
    expect(empty.groups.every((x) => x.entries === 0)).toBe(true);
  });
  it("항목 합계와 전체 합계가 요약과 일치한다", () => {
    expect(g.groups.find((x) => x.kind === "desk")?.entries).toBe(88);
    expect(g.total).toBe(scopes.reduce((n, s) => n + s.entries, 0));
  });
  it("범위 id가 빈 종류는 종류 행이 곧 범위(selfScope)", () => {
    expect(g.groups.find((x) => x.kind === "ledger")?.selfScope).toBe(true);
    expect(g.groups.find((x) => x.kind === "desk")?.selfScope).toBe(false);
    expect(groupScopes(kinds, []).groups.find((x) => x.kind === "ledger")?.selfScope).toBe(true);
  });
  it("알 수 없는 종류·꺼진 종류는 쓸 수 없는 범위로 모은다", () => {
    expect(g.unavailable.map((x) => [x.kind, x.state])).toEqual([["gone", "unknown"]]);
    const off = kinds.map((k) => (k.kind === "desk" ? { ...k, disabled: true } : k));
    const g2 = groupScopes(off, scopes);
    expect(g2.groups.map((x) => x.kind)).not.toContain("desk");
    expect(g2.unavailable.map((x) => [x.kind, x.state])).toEqual([["desk", "disabled"], ["gone", "unknown"]]);
    expect(g2.unavailable[0]?.scopes).toHaveLength(2);
  });
  it("같은 종류 안은 라벨 순(수정 시각이 아님)", () => {
    const list = [
      { ...scopes[1]!, updated_at: 1 },
      { ...scopes[2]!, updated_at: 999 },
    ];
    expect(groupScopes(kinds, list).groups[1]?.scopes.map((s) => s.scope.id)).toEqual(["g1", "g2"]);
    const byName = groupScopes(kinds, list, { labelOf: (s) => (s.scope.id === "g1" ? "나" : "가") });
    expect(byName.groups[1]?.scopes.map((s) => s.scope.id)).toEqual(["g2", "g1"]);
  });
  it("kind_known=false 요약은 목록에 있는 종류여도 알 수 없는 쪽", () => {
    const g3 = groupScopes(kinds, [{ ...scopes[1]!, kind_known: false }]);
    expect(g3.unavailable.map((x) => x.kind)).toEqual(["desk"]);
    expect(g3.groups.find((x) => x.kind === "desk")?.scopes).toHaveLength(0);
  });
});

describe("scopeLabel", () => {
  const desk = kinds[1]!;
  const pair = kinds[3]!;
  const named: ScopeNameResolvers = {
    graph_id: (v) => (v === "g1" ? { status: "named", name: "개발팀" } : { status: "deleted" }),
    agent_id: (v) => (v === "a1" ? { status: "named", name: "리뷰어" } : { status: "unknown" }),
  };
  it("틀의 모든 필드를 이름으로 풀면 ' / '로 잇는다", () => {
    const l = scopeLabel({ kind: "pair", id: "g1/a1" }, pair, named);
    expect(l.text).toBe("개발팀 / 리뷰어");
    expect(l.deleted).toBe(false);
    expect(l.mono).toBe(false);
  });
  it("정의 목록이 있는데 id가 없으면 삭제됨 + id(mono)", () => {
    const l = scopeLabel({ kind: "desk", id: "g9" }, desk, named);
    expect(l).toMatchObject({ text: "g9", deleted: true, mono: true, unknownKind: false });
  });
  it("정의 목록 역할이 없으면(풀이기 없음) id만, 삭제됨이라고 단정하지 않는다", () => {
    const l = scopeLabel({ kind: "desk", id: "g9" }, desk, {});
    expect(l).toMatchObject({ text: "g9", deleted: false, mono: true });
  });
  it("복합 틀 일부만 풀리면 풀린 이름 + 못 푼 id 조각", () => {
    const l = scopeLabel({ kind: "pair", id: "g1/zz" }, pair, named);
    expect(l.text).toBe("개발팀 / zz");
    expect(l.parts.map((p) => p.mono)).toEqual([false, true]);
    expect(l.mono).toBe(false);
  });
  it("id가 빈 범위·틀이 없는 종류는 종류 라벨, 틀과 안 맞는 id는 id 그대로", () => {
    expect(scopeLabel({ kind: "ledger", id: "" }, kinds[0], named).text).toBe("장부");
    expect(scopeLabel({ kind: "pair", id: "broken" }, pair, named)).toMatchObject({ text: "broken", mono: true });
    expect(scopeLabel({ kind: "weekly", id: "2026-W44" }, kinds[4], named)).toMatchObject({ text: "2026-W44", mono: true });
  });
  it("알 수 없는 종류는 종류 id + id(mono) + 표지", () => {
    expect(scopeLabel({ kind: "gone", id: "x" }, undefined, named)).toMatchObject({ text: "gone / x", unknownKind: true, mono: true });
    expect(scopeLabel({ kind: "desk", id: "g1" }, desk, named, false).unknownKind).toBe(true);
  });
  it("꺼진 종류 표지", () => {
    expect(scopeLabel({ kind: "desk", id: "g1" }, { ...desk, disabled: true }, named).disabledKind).toBe(true);
  });
});

/** 보이는 범위의 id 목록(종류 이름과 무관하게 비교하려고 범위 id + 표본 위치로 식별). */
function visibleIds(sc: typeof scopes, kd: typeof kinds, project: string | null, graphs: string[]): number[] {
  const r = visibleScopes(sc, kd, project, graphs);
  return r.visible.map((s) => sc.indexOf(s));
}

describe("visibleScopes (수용 기준 4, 표 테스트)", () => {
  const table: { name: string; project: string | null; graphs: string[]; visible: number[] }[] = [
    { name: "모든 프로젝트는 거르지 않는다", project: null, graphs: [], visible: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] },
    // 0 장부(id ""), 1 desk g1, 2 desk g2, 3 cabinet P1, 4 cabinet P2, 5 pair g1/a1, 6 pair g2/a1, 7 pair broken, 8 weekly, 9 gone(알 수 없음)
    { name: "P1: 빈 id + project_id 일치 + 팀 구성 일치", project: "P1", graphs: ["g1"], visible: [0, 1, 3, 5] },
    { name: "P2: 팀 구성이 다르면 그 범위만", project: "P2", graphs: ["g2"], visible: [0, 2, 4, 6] },
    { name: "팀 구성이 하나도 안 보이면 project_id 범위만", project: "P1", graphs: [], visible: [0, 3] },
    { name: "프로젝트에 맞는 것이 없으면 빈 id만", project: "P9", graphs: [], visible: [0] },
  ];
  const renames: [string, (k: string) => string][] = [
    ["원래 이름", (k) => k],
    ["전혀 다른 이름", (k) => `kind-${[...k].reverse().join("")}-x`],
    ["기본 종류 이름처럼 보이는 이름", (k) => (k === "desk" ? "team" : k === "cabinet" ? "project" : k === "ledger" ? "shared" : k)],
  ];
  for (const t of table) {
    for (const [rn, fn] of renames) {
      it(`${t.name} — ${rn}`, () => {
        const r = renameKinds(kinds, scopes, fn);
        expect(visibleIds(r.scopes, r.kinds, t.project, t.graphs)).toEqual(t.visible);
      });
    }
  }
  it("숨긴 범위 수는 hidden 길이", () => {
    const r = visibleScopes(scopes, kinds, "P1", ["g1"]);
    expect(r.visible).toHaveLength(4);
    expect(r.hidden).toHaveLength(6);
  });
  it("알 수 없는 종류의 범위는 id가 빈 문자열이어도 프로젝트 보기에서 숨는다", () => {
    const s = [{ ...scopes[0]!, scope: { kind: "gone", id: "" }, kind_known: false }];
    expect(visibleScopes(s, kinds, "P1").hidden).toHaveLength(1);
    expect(visibleScopes(s, kinds, null).visible).toHaveLength(1);
  });
  it("맥락 필드 이름은 옵션으로 바꿀 수 있다", () => {
    const k = [{ kind: "x", label: "x", id: "{/proj}", origin: "user", context_fields: ["proj"] }];
    const s = [{ ...scopes[0]!, scope: { kind: "x", id: "P1" } }];
    expect(visibleScopes(s, k, "P1", [], { projectField: "proj" }).visible).toHaveLength(1);
    expect(visibleScopes(s, k, "P1").visible).toHaveLength(0);
  });
});

describe("formatAuthor", () => {
  it("에이전트: label > 정의 이름 > id(mono). 삭제된 에이전트는 id + 표지", () => {
    expect(formatAuthor(sampleAuthor("agent", { label: "PL" })).text).toBe("PL");
    const named = formatAuthor(sampleAuthor("agent"), { resolveAgent: () => ({ status: "named", name: "리뷰어" }) });
    expect(named).toMatchObject({ text: "리뷰어", mono: false, chip: false });
    expect(named.avatar?.initial).toBe("리");
    const gone = formatAuthor(sampleAuthor("agent"), { resolveAgent: () => ({ status: "deleted" }) });
    expect(gone).toMatchObject({ text: "a1", mono: true, deletedAgent: true });
    expect(formatAuthor(sampleAuthor("agent")).deletedAgent).toBe(false);
  });
  it("아바타 색 슬롯은 같은 id면 항상 같다", () => {
    const a = formatAuthor(sampleAuthor("agent")).avatar?.slot;
    expect(a).toBe(formatAuthor(sampleAuthor("agent")).avatar?.slot);
    expect(a).toBeGreaterThanOrEqual(1);
    expect(a).toBeLessThanOrEqual(8);
  });
  it("사용자는 칩, 정리/가져오기는 칩 + 규칙 id", () => {
    expect(formatAuthor(sampleAuthor("user"))).toMatchObject({ text: "사용자", chip: true, avatar: null });
    expect(formatAuthor(sampleAuthor("system"))).toMatchObject({ text: "정리", chip: true, ruleId: "stale-rule" });
    expect(formatAuthor({ kind: "system" })).toMatchObject({ text: "가져오기", ruleId: null });
    expect(formatAuthor({ kind: "system", label: "r" }, { systemCause: "retention" }).text).toBe("정리");
  });
  it("모르는 kind는 원문, 툴팁에 노드 경로와 실행 id", () => {
    expect(formatAuthor({ kind: "robot" })).toMatchObject({ text: "robot", chip: false, avatar: null });
    const t = formatAuthor(sampleAuthor("agent", { node_path: ["a", "b"], run_id: "r-1" })).tooltip;
    expect(t).toContain("a › b");
    expect(t).toContain("r-1");
  });
  it("문구는 messages로 바꾼다", () => {
    expect(formatAuthor(sampleAuthor("user"), { messages: { "author.user": "Human" } }).text).toBe("Human");
  });
});

