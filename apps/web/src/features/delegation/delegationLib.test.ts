import { describe, expect, it } from "vitest";
import type { EdgeSpec, EdgeTypeDescriptor, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import { buildBindSummary, deriveBindSummaries, nestedDefinitionList } from "./bindSummary";
import { actualPreview, conditionShape, formatConditionValue, mapConditionOutcome, summarizeConditions, switchMode, valueKindOf, withItems, withNegate, type ConditionSpec } from "./conditions";
import { DEFAULT_TEAM_CONVENTIONS } from "./conventions";
import { resolveCycleLimit } from "./cycleLimit";
import { deriveEdgeChips, edgeStrategyIds } from "./edgeChips";
import { isChildRunNotice, parseDelegationEvent, summarizeDelegationEvent } from "./eventSummaryMap";
import { displayNumber, formatRunOrdinal } from "./ordinal";
import { bridgeWidgetUi, chipsFromWidgets, widgetFieldsOf, UNKNOWN_WIDGET_FIELD, type WidgetRegistry } from "./widgetRegistry";

// 임의의 가짜 이름만 쓴다: 실제 종류·연산자·위젯 이름에 기대면 안 된다.
const ops = [
  { id: "op-aa", title: "포함" },
  { id: "op-bb", title: "같음" },
];

describe("formatRunOrdinal: 화면 번호는 값 + 1 (D1)", () => {
  it("회차·호출을 1부터 센다", () => {
    expect(formatRunOrdinal(0, "iteration")).toBe("1회차");
    expect(formatRunOrdinal(2, "iteration")).toBe("3회차");
    expect(formatRunOrdinal(0, "call")).toBe("호출 1");
    expect(displayNumber(4)).toBe(5);
  });
  it("음수·소수는 0으로 맞춘다", () => {
    expect(formatRunOrdinal(-3, "iteration")).toBe("1회차");
    expect(formatRunOrdinal(1.9, "call")).toBe("호출 2");
  });
});

describe("resolveCycleLimit: 연결 → 팀 → 공통 → 종류 기본", () => {
  const c = DEFAULT_TEAM_CONVENTIONS;
  it("처음 유효한 층의 값과 출처를 돌려준다", () => {
    expect(resolveCycleLimit({ edgeConfig: { max_iterations: 5 }, teamSettings: { flow: { max_iterations: 4 } }, kindDefault: 3 })).toEqual({ value: 5, source: "edge" });
    expect(resolveCycleLimit({ edgeConfig: {}, teamSettings: { flow: { max_iterations: 4 } }, commonSettings: { flow: { max_iterations: 6 } }, kindDefault: 3 })).toEqual({ value: 4, source: "teamSettings" });
    expect(resolveCycleLimit({ commonSettings: { flow: { max_iterations: 6 } }, kindDefault: 3 })).toEqual({ value: 6, source: "commonSettings" });
    expect(resolveCycleLimit({ kindDefault: 3 })).toEqual({ value: 3, source: "kindDefault" });
  });
  it("1 미만·비정수·없음은 건너뛰고 끝까지 없으면 값이 없다", () => {
    expect(resolveCycleLimit({ edgeConfig: { max_iterations: 0 }, kindDefault: 3 })).toEqual({ value: 3, source: "kindDefault" });
    expect(resolveCycleLimit({ edgeConfig: { max_iterations: 2.5 }, kindDefault: 0 })).toEqual({ value: undefined, source: undefined });
    expect(resolveCycleLimit({})).toEqual({ value: undefined, source: undefined });
  });
  it("키 위치는 TeamConventions 데이터가 정한다", () => {
    const other = { ...c, edgeIterationLimit: "/limit/n" };
    expect(resolveCycleLimit({ edgeConfig: { limit: { n: 7 } }, kindDefault: 3, conventions: other })).toEqual({ value: 7, source: "edge" });
  });
});

describe("summarizeConditions", () => {
  const it1 = { path: "/a", op: "op-aa", value: "PASS" };
  const it2 = { path: "/b", op: "op-bb", value: 3 };
  const it3 = { path: "/c", op: "op-zz", value: ["x", "y", "z", "w"] };
  it("두 항목까지는 접속사로 잇는다(모두 = 그리고, 하나라도 = 또는)", () => {
    expect(summarizeConditions({ all: [it1, it2] }, ops, undefined).text).toBe("/a 포함 ‘PASS’ 그리고 /b 같음 3");
    expect(summarizeConditions({ any: [it1, it2] }, ops, undefined).text).toBe("/a 포함 ‘PASS’ 또는 /b 같음 3");
  });
  it("세 항목 이상이면 첫 두 개 + 외 N개, full은 전문", () => {
    const s = summarizeConditions({ all: [it1, it2, it3] }, ops, undefined);
    expect(s.text.endsWith(" 외 1개")).toBe(true);
    expect(s.full).toContain("/c op-zz [x, y, z, 외 1개]");
    expect(s.empty).toBe(false);
  });
  it("negate는 앞에 붙는다", () => {
    expect(summarizeConditions({ all: [it1], negate: true }, ops, undefined).text.startsWith("아닌 경우: ")).toBe(true);
  });
  it("빈 조건·모르는 연산자·경로 제목·36자 말줄임", () => {
    expect(summarizeConditions({}, ops, undefined)).toEqual({ text: "조건 없음", full: "조건 없음", empty: true });
    expect(summarizeConditions(undefined, null, undefined).empty).toBe(true);
    expect(summarizeConditions({ all: [{ path: "/a", op: "op-zz" }] }, ops, { "/a": "출력" }).text).toBe("출력 op-zz");
    const long = summarizeConditions({ all: [{ path: "/a", op: "op-aa", value: "가".repeat(60) }] }, ops, undefined);
    expect(long.text.length).toBeLessThanOrEqual(37);
    expect(long.text.endsWith("…")).toBe(true);
    expect(long.full).toContain("가".repeat(60));
  });
  it("값 표시: 문자열·숫자·불리언·배열·객체·없음", () => {
    expect(formatConditionValue("a")).toBe("‘a’");
    expect(formatConditionValue(3)).toBe("3");
    expect(formatConditionValue(false)).toBe("false");
    expect(formatConditionValue({ k: 1 })).toBe('{"k":1}');
    expect(formatConditionValue(undefined)).toBe("");
  });
});

describe("조건 묶음 편집 규칙", () => {
  it("모양: all+any 동시에 항목이 있으면 both", () => {
    expect(conditionShape({ all: [{ path: "/a", op: "x" }], any: [{ path: "/b", op: "y" }] })).toBe("both");
    expect(conditionShape({ any: [{ path: "/b", op: "y" }] })).toBe("any");
    expect(conditionShape({})).toBe("none");
    expect(conditionShape(undefined)).toBe("none");
  });
  it("모드 전환은 항목을 그대로 두고 키만 옮기며 모르는 키를 보존한다", () => {
    const spec = { all: [{ path: "/a", op: "x" }], negate: true, extra: 1 } as ConditionSpec;
    expect(switchMode(spec, "any")).toEqual({ any: [{ path: "/a", op: "x" }], negate: true, extra: 1 });
  });
  it("뒤집기는 켜면 true, 끄면 키를 지운다", () => {
    expect(withNegate({ all: [] }, true)).toEqual({ all: [], negate: true });
    expect(withNegate({ all: [], negate: true }, false)).toEqual({ all: [] });
  });
  it("항목이 0개가 돼도 모드 키는 남는다", () => {
    expect(withItems({ all: [{ path: "/a", op: "x" }] }, "all", [])).toEqual({ all: [] });
  });
  it("값 입력 모양은 value_schema의 type으로 정한다", () => {
    expect(valueKindOf({ type: "string" })).toBe("string");
    expect(valueKindOf({ type: ["integer", "null"] })).toBe("number");
    expect(valueKindOf({ type: "boolean" })).toBe("boolean");
    expect(valueKindOf({ type: "array", items: { type: "string" } })).toBe("array");
    expect(valueKindOf({ type: "object" })).toBe("json");
    expect(valueKindOf({})).toBeUndefined();
    expect(valueKindOf({ not: {} })).toBe("none");
    expect(valueKindOf(false)).toBe("none");
  });
});

describe("mapConditionOutcome: 판정 근거 어댑터(S1)", () => {
  it("정해진 모양을 푼다", () => {
    const out = mapConditionOutcome({ result: true, combinator: "all", negate: false, items: [{ path: "/a", op: "op-aa", value: "x", actual: "xyz", result: true }, { path: "/b", op: "op-bb", result: false, reason: "missing" }] });
    expect(out?.result).toBe(true);
    expect(out?.items?.[0]).toMatchObject({ path: "/a", op: "op-aa", value: "x", actual: "xyz", hasActual: true, result: true });
    expect(out?.items?.[1]).toMatchObject({ hasActual: false, reason: "missing" });
  });
  it("키가 없으면 그 부분만 생략한다", () => {
    expect(mapConditionOutcome({ result: false })).toEqual({ result: false });
  });
  it("해석할 수 없으면 null", () => {
    expect(mapConditionOutcome("x")).toBeNull();
    expect(mapConditionOutcome({ result: "yes" })).toBeNull();
    expect(mapConditionOutcome({ result: true, items: [{ path: 1 }] })).toBeNull();
    expect(mapConditionOutcome({ result: true, items: "no" })).toBeNull();
  });
  it("실제 값은 180자에서 말줄임", () => {
    const p = actualPreview("가".repeat(300));
    expect(p.truncated).toBe(true);
    expect(p.text.length).toBe(180);
    expect(p.full.length).toBe(300);
    expect(actualPreview({ a: 1 }).text).toBe('{"a":1}');
  });
});

describe("이벤트 매핑 표 (eventSummaryMap)", () => {
  const ctx = { nodeLabel: (id: string) => `N-${id}`, edgeLabel: () => "칩", teamName: (id: string) => (id === "c1" ? "팀가" : undefined), statusLabel: (s: string) => `상태:${s}`, shortId: (id: string) => id.slice(0, 4) };
  it("반복 시작은 서버 값 + 1 회차로 보인다", () => {
    const s = summarizeDelegationEvent({ type: "loop.iteration", payload: { edge_id: "e", iteration: 1, nodes: ["a", "b"] } }, ctx);
    expect(s?.text).toBe("↻ 반복 2회차 시작 · N-a, N-b");
  });
  it("반복 한도 도달은 max_iterations만 쓰고 iteration은 쓰지 않는다", () => {
    const s = summarizeDelegationEvent({ type: "loop.exhausted", payload: { edge_id: "e", iteration: 9, max_iterations: 3 } }, ctx);
    expect(s).toMatchObject({ text: "↻ 반복 한도 도달 (한도 3회) · 칩", tone: "warning" });
    expect(s?.text).not.toContain("9");
  });
  it("자식 실행 시작·끝: 이름이 없으면 이름 칸을 뺀다", () => {
    expect(summarizeDelegationEvent({ type: "run.child_started", payload: { child_run_id: "c1", node_id: "n" } }, ctx)?.text).toBe("▣ 자식 실행 시작 · 팀가 · c1");
    expect(summarizeDelegationEvent({ type: "run.child_finished", payload: { child_run_id: "c2xxxx", node_id: "n", status: "failed" } }, ctx)).toMatchObject({ text: "▣ 자식 실행 상태:failed · c2xx", tone: "status", status: "failed", childRunId: "c2xxxx" });
  });
  it("모르는 타입·필수 값 없음은 null, 자식 알림 판별", () => {
    expect(parseDelegationEvent({ type: "x.y", payload: {} })).toBeNull();
    expect(parseDelegationEvent({ type: "loop.iteration", payload: {} })).toBeNull();
    expect(isChildRunNotice({ type: "run.child_started" })).toBe(true);
    expect(isChildRunNotice({ type: "run.completed" })).toBe(false);
  });
});

describe("위젯 레지스트리", () => {
  const Dummy = () => null;
  const registry: WidgetRegistry = { "w-one": { Component: Dummy, summary: (v) => ({ title: `값:${JSON.stringify(v)}`, iconName: "ic" }) }, "w-plain": { Component: Dummy } };
  const ui = { alpha: { "ui:widget": "w-one", "ui:options": { k: 1 } }, beta: { inner: { "ui:widget": "w-plain" } }, gamma: { "ui:widget": "unregistered" } };
  it("ui_schema에서 레지스트리 위젯이 지정된 필드를 찾는다(summary 필터)", () => {
    expect(widgetFieldsOf(ui, registry).map((f) => f.pointer)).toEqual(["/alpha", "/beta/inner"]);
    expect(widgetFieldsOf(ui, registry, true).map((f) => f.pointer)).toEqual(["/alpha"]);
  });
  it("summary가 있는 위젯이 쓰인 필드 값으로 칩이 생긴다", () => {
    const chips = chipsFromWidgets(ui, { alpha: { q: 1 } }, registry, (f) => ({ operators: null, options: f.options }));
    expect(chips).toEqual([{ key: "w:/alpha", title: '값:{"q":1}', iconName: "ic" }]);
  });
  it("레지스트리 이름은 ui:field로 옮기고, 구조화 필드의 모르는 이름은 JSON 폴백으로 바꾼다", () => {
    const schema = { type: "object", properties: { alpha: { type: "object" }, beta: { type: "object", properties: { inner: { type: "object" } } }, gamma: { type: "object", properties: {} }, delta: { type: "string" } } };
    const bridged = bridgeWidgetUi({ ...ui, delta: { "ui:widget": "plainwidget" } }, schema, registry);
    const out = bridged.uiSchema as Record<string, Record<string, unknown>>;
    expect(out["alpha"]!["ui:field"]).toBe("w-one");
    expect(out["alpha"]!["ui:widget"]).toBeUndefined();
    expect((out["alpha"]!["ui:options"] as Record<string, unknown>)["$pointer"]).toBe("/alpha");
    expect(out["gamma"]!["ui:field"]).toBe(UNKNOWN_WIDGET_FIELD);
    expect(out["delta"]!["ui:widget"]).toBe("plainwidget");
    expect(bridged.unknown).toEqual([{ pointer: "/gamma", name: "unregistered" }]);
  });
  it("입력을 바꾸지 않는다", () => {
    const copy = JSON.stringify(ui);
    bridgeWidgetUi(ui, { type: "object", properties: { gamma: { type: "object" } } }, registry);
    expect(JSON.stringify(ui)).toBe(copy);
  });
});

describe("연결 칩 (deriveEdgeChips)", () => {
  const edge = (config?: Record<string, unknown>): EdgeSpec => ({ id: "e1", kind: "k-x", source: { node: "a", port: "o" }, target: { node: "b", port: "i" }, ...(config ? { config } : {}) });
  const registry: WidgetRegistry = { "w-one": { Component: () => null, summary: () => ({ title: "요약", tone: "neutral" }) } };
  it("cycle 속성이 있으면 한도 칩, 상속이면 점선·전문에 출처", () => {
    const type = { id: "k-x", title: "T", cycle: { max_iterations: 3 } } as EdgeTypeDescriptor;
    expect(deriveEdgeChips(edge(), type)[0]).toMatchObject({ key: "cycle-limit", title: "최대 3회", dashed: true });
    expect(deriveEdgeChips(edge(), type)[0]?.fullTitle).toContain("연결 종류 기본값에서 옴");
    expect(deriveEdgeChips(edge({ max_iterations: 2 }), type)[0]).toMatchObject({ title: "최대 2회" });
    expect(deriveEdgeChips(edge({ max_iterations: 2 }), type)[0]?.dashed).toBeUndefined();
  });
  it("반복 한도 칩은 콜백이 있을 때만 단추(onActivate)이고 연결 id를 넘긴다", () => {
    const type = { id: "k-x", title: "T", cycle: { max_iterations: 3 } } as EdgeTypeDescriptor;
    expect(deriveEdgeChips(edge(), type)[0]?.onActivate).toBeUndefined();
    const seen: string[] = [];
    const chip = deriveEdgeChips(edge(), type, { onLimitChipActivate: (id) => seen.push(id) })[0];
    chip?.onActivate?.();
    expect(seen).toEqual(["e1"]);
  });
  it("한도를 알 수 없으면 한도 없음 danger 칩", () => {
    const type = { id: "k-x", title: "T", cycle: { max_iterations: 0 } } as EdgeTypeDescriptor;
    expect(deriveEdgeChips(edge(), type)[0]).toMatchObject({ title: "한도 없음 ▲", tone: "danger" });
  });
  it("위임 방식 칩은 종류 기본과 다를 때만", () => {
    const type = { id: "k-x", title: "T", invocation: { strategy: "s1" } } as EdgeTypeDescriptor;
    const strategies = [{ id: "s1", title: "방식1" }, { id: "s2", title: "방식2" }];
    expect(deriveEdgeChips(edge(), type, { strategies })).toEqual([]);
    expect(deriveEdgeChips(edge({ strategy: "s2" }), type, { strategies })[0]).toMatchObject({ key: "strategy", title: "방식: 방식2" });
    expect(edgeStrategyIds({ edges: [edge({ strategy: "s2" })] }, [type])).toEqual({ e1: "s2" });
  });
  it("위젯 summary가 있는 필드는 칩을 만들고 종류 id는 쓰지 않는다", () => {
    const type = { id: "k-x", title: "T", ui_schema: { cfg: { "ui:widget": "w-one" } } } as EdgeTypeDescriptor;
    expect(deriveEdgeChips(edge(), type, { widgets: registry })).toEqual([{ key: "w:/cfg", title: "요약", tone: "neutral" }]);
    expect(deriveEdgeChips(edge(), type, {})).toEqual([]);
    expect(deriveEdgeChips(edge(), undefined, { widgets: registry })).toEqual([]);
  });
});

describe("중첩 노드 요약 (buildBindSummary)", () => {
  const nodeType = (kind: string) => ({ id: "t-n", title: "T", binds: { kind, field: "ref" } }) as NodeTypeDescriptor;
  const node = (config: Record<string, unknown>): NodeSpec => ({ id: "n1", type: "t-n", label: "검토", config }) as NodeSpec;
  const infos = [{ id: "g2", name: "검토 파이프라인", nodeCount: 5, entries: ["입구"] }];
  const base = { currentKind: "kind-q", currentId: "g1", infos, kindTitle: "팀 구성", open: () => {} };
  it("현재 정의 종류와 같은 binds.kind만 요약한다", () => {
    expect(buildBindSummary(node({ ref: "g2" }), nodeType("kind-other"), base)).toBeUndefined();
    expect(buildBindSummary(node({ ref: "g2" }), undefined, base)).toBeUndefined();
    const s = buildBindSummary(node({ ref: "g2" }), nodeType("kind-q"), base);
    expect(s).toMatchObject({ title: "검토 파이프라인", subtitle: "팀 구성", meta: "노드 5개 · 입구 1" });
    expect(s?.open?.label).toBe("열기");
  });
  it("버전 고정·자기 자신·정의 없음 세 상태", () => {
    const pinned = buildBindSummary(node({ ref: "g2", version: "3fa9c1b2deadbeef" }), nodeType("kind-q"), base);
    expect(pinned?.badges?.[0]).toMatchObject({ key: "pin", title: "고정 3fa9c1b" });
    const self = buildBindSummary(node({ ref: "g1" }), nodeType("kind-q"), base);
    expect(self?.badges?.some((b) => b.key === "self" && b.tone === "danger")).toBe(true);
    const missing = buildBindSummary(node({ ref: "zz" }), nodeType("kind-q"), base);
    expect(missing).toMatchObject({ missing: true, subtitle: "팀 구성을 찾을 수 없음: zz" });
    expect(missing?.open).toBeUndefined();
  });
  it("이름 로딩 중(infos 없음)에는 id를 이름으로 쓰고 없음 판정을 하지 않는다", () => {
    const s = buildBindSummary(node({ ref: "g2" }), nodeType("kind-q"), { ...base, infos: undefined, open: undefined });
    expect(s?.title).toBe("g2");
    expect(s?.missing).toBeUndefined();
    expect(s?.open).toBeUndefined();
  });
  it("라우트가 없으면(open 없음) 열기 단추가 없다", () => {
    expect(buildBindSummary(node({ ref: "g2" }), nodeType("kind-q"), { ...base, open: undefined })?.open).toBeUndefined();
  });
  it("전체 표와 팔레트 목록: 이름 오름차순, 자기 자신 비활성", () => {
    const all = deriveBindSummaries([node({ ref: "g2" }), { id: "n2", type: "other" } as NodeSpec], [nodeType("kind-q")], base);
    expect(Object.keys(all)).toEqual(["n1"]);
    const list = nestedDefinitionList([{ id: "g1", name: "나" }, { id: "g2", name: "가" }], "g1");
    expect(list.map((i) => i.id)).toEqual(["g2", "g1"]);
    expect(list[1]?.disabledReason).toBe("자기 자신은 넣을 수 없습니다");
    expect(list[0]?.disabledReason).toBeUndefined();
  });
});
