import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { EdgeKindDialog, GraphEditor, TeamPalette } from "./index";
import type { BindSummary, GraphEditorProps } from "./index";

afterEach(cleanup);

/**
 * 레이아웃이 없는 환경에서 React Flow가 노드/핸들 치수를 측정하게 한다(EdgeEdit.test.tsx와 같은 방식).
 * 캔버스(`.react-flow`)는 1000x600, 그 밖의 요소는 160x80으로 보여 모든 노드가 화면 안에 들어오고 연결이 그려진다.
 */
async function withLayout(run: () => Promise<void>): Promise<void> {
  const original = globalThis.ResizeObserver;
  const proto = HTMLElement.prototype;
  const offW = Object.getOwnPropertyDescriptor(proto, "offsetWidth");
  const offH = Object.getOwnPropertyDescriptor(proto, "offsetHeight");
  Object.defineProperty(proto, "offsetWidth", { configurable: true, get(this: HTMLElement) { return this.classList.contains("react-flow") ? 1000 : 160; } });
  Object.defineProperty(proto, "offsetHeight", { configurable: true, get(this: HTMLElement) { return this.classList.contains("react-flow") ? 600 : 80; } });
  globalThis.ResizeObserver = class {
    constructor(private cb: ResizeObserverCallback) {}
    observe(target: Element) {
      this.cb([{ target, contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  try {
    await run();
  } finally {
    globalThis.ResizeObserver = original;
    if (offW) Object.defineProperty(proto, "offsetWidth", offW);
    else delete (proto as unknown as Record<string, unknown>).offsetWidth;
    if (offH) Object.defineProperty(proto, "offsetHeight", offH);
    else delete (proto as unknown as Record<string, unknown>).offsetHeight;
  }
}
/** 측정 목 없이 실행: 모든 노드가 DOM에 있고(연결은 없음) 카드 표현을 검사하기 쉽다. */
const plain = (run: () => Promise<void>): Promise<void> => run();
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 50)); });

/** 임의 이름만 쓴다. 속성(cycle·handles_failure·invocation·binds·ui_hints.shape)이 동작을 정한다. */
const nodeTypes: NodeTypeDescriptor[] = [
  { id: "q-plain", version: 1, title: "보통 노드", category: "c", static_ports: { inputs: [{ name: "in", label: "받기" }], outputs: [{ name: "out", label: "내기" }] } },
  {
    id: "q-bound",
    version: 1,
    title: "묶인 노드",
    category: "c",
    binds: { kind: "def-kind", field: "ref" },
    static_ports: { inputs: [{ name: "in", label: "받기" }], outputs: [{ name: "out", label: "내기" }] },
    ui_hints: { shape: "stacked" },
  },
  { id: "q-odd-shape", version: 1, title: "다른 모양", category: "c", static_ports: { inputs: [{ name: "in" }], outputs: [{ name: "out" }] }, ui_hints: { shape: "weird-unknown" } },
];
const edgeTypes: EdgeTypeDescriptor[] = [
  { id: "k-flow", version: 1, title: "흐름", scheduling: "flow" },
  { id: "k-back", version: 1, title: "되풀이", scheduling: "flow", cycle: { max_iterations: 3 } },
  { id: "k-fail", version: 1, title: "실패 때", scheduling: "flow", handles_failure: true },
  { id: "k-deleg", version: 1, title: "맡김", scheduling: "none", invocation: { strategy: "s2" } },
  { id: "k-hinted", version: 1, title: "힌트 종류", scheduling: "flow", cycle: { max_iterations: 2 }, ui_hints: { color: "#22aa88", icon: "★" } },
];
const graph = (): Graph => ({
  id: "g",
  name: "g",
  nodes: [
    { id: "w", type: "q-plain", label: "작성자", position: { x: 0, y: 0 } },
    { id: "r", type: "q-plain", label: "검토", position: { x: 20, y: 10 } },
    { id: "a", type: "q-plain", label: "답변", position: { x: 40, y: 20 } },
  ],
  edges: [
    { id: "f1", kind: "k-flow", source: { node: "w", port: "out" }, target: { node: "r", port: "in" } },
    { id: "f2", kind: "k-flow", source: { node: "r", port: "out" }, target: { node: "a", port: "in" } },
    { id: "b1", kind: "k-back", source: { node: "r", port: "out" }, target: { node: "w", port: "in" } },
  ],
});

function setup(over: Partial<GraphEditorProps> = {}, g: Graph = graph()) {
  return render(
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor graph={g} nodeTypes={nodeTypes} edgeTypes={edgeTypes} showMinimap={false} {...over} />
    </div>,
  );
}
const edgeEl = (id: string) => document.querySelector<HTMLElement>(`.react-flow__edge[data-id="${id}"]`)!;
const nodeEl = (id: string) => document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
const live = () => document.querySelector(".ac-ge-sr-only[role='status']")!.textContent;
const chipOf = (id: string) => document.querySelector<HTMLElement>(`.ac-ge-edge-chip[data-edge-id="${id}"]`);

describe("연결선: 속성 기반 스타일", () => {
  it("반복 속성: 반복 색·아이콘이 붙고 칩이 항상 보인다. 일반 흐름 연결은 변화 없음", () =>
    withLayout(async () => {
      setup();
      await settle();
      const back = edgeEl("b1");
      expect(back.querySelector<SVGPathElement>(".react-flow__edge-path")!.getAttribute("style")).toContain("--ac-edge-loop");
      expect(back.className).not.toContain("ac-ge-edge--patterned"); // 반복은 실선
      const plain = edgeEl("f1");
      expect(plain.querySelector(".react-flow__edge-path")!.getAttribute("style") ?? "").not.toContain("--ac-ge-edge-color");
      expect(plain.className).not.toContain("patterned");
      expect(document.querySelectorAll("[data-edge-icon]")).toHaveLength(1); // 반복 연결 하나뿐
      expect(document.querySelector("[data-edge-icon]")!.getAttribute("data-edge-icon")).toBe("repeat");
      // 속성 아이콘이 있는 칩은 선택하지 않아도 보인다, 일반 연결 칩은 숨김 규칙 그대로
      expect(document.querySelector('.ac-ge-edge-chip[data-badged="true"]')).toBeTruthy();
    }));

  it("실패 처리 속성: 점선 패턴(토큰 참조)과 둥근 끝", () =>
    withLayout(async () => {
      const g = graph();
      g.edges!.push({ id: "x", kind: "k-fail", source: { node: "w", port: "out" }, target: { node: "a", port: "in" } });
      setup({}, g);
      await settle();
      const el = edgeEl("x");
      expect(el.className).toContain("ac-ge-edge--patterned");
      const style = el.querySelector(".react-flow__edge-path")!.getAttribute("style")!;
      expect(style).toContain("--ac-ge-edge-dash: var(--ac-edge-pattern-2)");
      expect(style).toContain("--ac-edge-failure");
      expect(style).toContain("stroke-linecap: round");
    }));

  it("위임 연결: 위임 방식 id 정렬 순서로 패턴을 정하고 연결별 방식이 우선한다", () =>
    withLayout(async () => {
      const g = graph();
      g.edges!.push({ id: "d", kind: "k-deleg", source: { node: "w", port: "out" }, target: { node: "a", port: "in" } });
      setup({ delegationStrategies: [{ id: "s3" }, { id: "s1" }, { id: "s2" }] }, g);
      await settle();
      // s2는 정렬 순서 1번 → 패턴 1
      expect(edgeEl("d").querySelector(".react-flow__edge-path")!.getAttribute("style")).toContain("var(--ac-edge-pattern-1)");
      cleanup();
      setup({ delegationStrategies: [{ id: "s3" }, { id: "s1" }, { id: "s2" }], edgeStrategyIds: { d: "s3" } }, g);
      await settle();
      expect(edgeEl("d").querySelector(".react-flow__edge-path")!.getAttribute("style")).toContain("var(--ac-edge-pattern-2)");
    }));

  it("ui_hints가 이긴다: 힌트 색·아이콘 글자", () =>
    withLayout(async () => {
      const g = graph();
      g.edges!.push({ id: "h", kind: "k-hinted", source: { node: "w", port: "out" }, target: { node: "a", port: "in" } });
      setup({}, g);
      await settle();
      expect(edgeEl("h").querySelector(".react-flow__edge-path")!.getAttribute("style")).toContain("#22aa88");
      expect(document.querySelector('[data-edge-icon="★"]')!.textContent).toBe("★");
    }));

  it("renderIcon이 아이콘 이름을 그리고, 못 그리면 글자로 폴백한다", () =>
    withLayout(async () => {
      const renderIcon = (n: string): ReactNode => (n === "repeat" ? <svg data-testid="rep" /> : null);
      setup({ renderIcon });
      await settle();
      expect(screen.getByTestId("rep")).toBeTruthy();
      cleanup();
      setup({ renderIcon: () => null });
      await settle();
      expect(document.querySelector("[data-edge-icon]")!.textContent).toBe("되"); // 종류 제목 첫 글자
    }));

  it("알 수 없는 연결 종류에는 속성 기본값을 적용하지 않는다", () =>
    withLayout(async () => {
      const g = graph();
      g.edges!.push({ id: "u", kind: "k-ghost", source: { node: "w", port: "out" }, target: { node: "a", port: "in" } });
      setup({}, g);
      await settle();
      expect(edgeEl("u").className).not.toContain("patterned");
      expect(edgeEl("u").querySelector("[data-edge-icon]")).toBeNull();
    }));
});

describe("연결선: 추가 칩·배지", () => {
  const chips = Array.from({ length: 6 }, (_, i) => ({ key: `c${i}`, title: `칩${i}`, fullTitle: `칩 전문 ${i}`, tone: i === 1 ? ("warning" as const) : undefined, dashed: i === 2, iconName: i === 0 ? "filter" : undefined }));

  it("onActivate가 있는 칩은 단추가 되어 클릭·Enter로 콜백을 부른다", () =>
    withLayout(async () => {
      const onActivate = vi.fn();
      setup({ edgeExtraChips: { f1: [{ key: "a", title: "최대 3회", onActivate }, { key: "b", title: "읽기 전용" }] } });
      await settle();
      const btn = within(chipOf("f1")!).getByRole("button", { name: "최대 3회" });
      fireEvent.click(btn);
      expect(onActivate).toHaveBeenCalledTimes(1);
      expect(within(chipOf("f1")!).queryByRole("button", { name: "읽기 전용" })).toBeNull();
    }));

  it("4개까지 보이고 나머지는 +N(툴팁에 전체), 접근성 이름에 전문이 들어간다", () =>
    withLayout(async () => {
      setup({ edgeExtraChips: { f1: chips }, renderIcon: (n) => <i data-testid={`icon-${n}`} /> });
      await settle();
      const chip = chipOf("f1")!;
      expect(chip.querySelectorAll(".ac-ge-hint-chip:not([data-more])")).toHaveLength(4);
      const more = chip.querySelector<HTMLElement>('[data-more="true"]')!;
      expect(more.textContent).toBe("+2");
      expect(more.title).toBe("칩 전문 4, 칩 전문 5");
      expect(chip.querySelector('[data-tone="warning"]')).toBeTruthy();
      expect(chip.querySelector('[data-dashed="true"]')).toBeTruthy();
      expect(chip.getAttribute("data-wide")).toBe("true");
      expect(within(chip).getByTestId("icon-filter")).toBeTruthy();
      const aria = edgeEl("f1").getAttribute("aria-label")!;
      expect(aria).toContain("종류 흐름");
      expect(aria).toContain("칩 전문 0; 칩 전문 1");
      expect(aria).toContain("칩 전문 5");
    }));

  it("연결 배지(실행 상세)와 칩 접근성 이름", () =>
    withLayout(async () => {
      setup({ edgeBadges: { b1: [{ text: "↻×2", ariaLabel: "2번 되돌아감", tone: "neutral" }, { text: "한도", ariaLabel: "한도 도달", tone: "warning" }] }, readOnly: true });
      await settle();
      const badges = chipOf("b1")!.querySelectorAll(".ac-ge-run-badge");
      expect([...badges].map((b) => b.textContent)).toEqual(["↻×2", "한도"]);
      expect(badges[1]!.getAttribute("data-tone")).toBe("warning");
      expect(edgeEl("b1").getAttribute("aria-label")).toContain("한도 도달");
    }));

  it("추가 정보가 없으면 칩 DOM이 이전과 같다(아이콘·배지·더보기 없음)", () =>
    withLayout(async () => {
      setup();
      await settle();
      const chip = [...document.querySelectorAll<HTMLElement>(".ac-ge-edge-chip")].find((c) => c.textContent === "흐름")!;
      expect(chip).toBeTruthy();
      expect(chip.querySelector(".ac-ge-edge-icon,.ac-ge-run-badge,[data-more],.ac-ge-chip-text")).toBeNull();
      expect(chip.getAttribute("data-wide")).toBeNull();
      expect(chip.getAttribute("data-edge-id")).toBeNull(); // 새 데이터가 없으면 이전과 같은 DOM
      expect(edgeEl("f1").getAttribute("aria-label")).not.toContain("종류");
    }));
});

describe("반복 영역 강조", () => {
  it("반복 연결을 선택하면 영역 노드에 윤곽과 안내가 나오고, 해제하면 사라진다", () =>
    withLayout(async () => {
      setup();
      await settle();
      expect(document.querySelector("[data-loop-region]")).toBeNull();
      fireEvent.click(edgeEl("b1"));
      expect(nodeEl("w").querySelector('[data-loop-region="true"]')).toBeTruthy();
      expect(nodeEl("r").querySelector('[data-loop-region="true"]')).toBeTruthy();
      expect(nodeEl("a").querySelector('[data-loop-region="true"]')).toBeNull();
      expect(live()).toBe("반복 영역: 노드 2개 — 작성자, 검토");
      fireEvent.click(document.querySelector(".react-flow__pane")!);
      fireEvent.click(edgeEl("f1"));
      expect(document.querySelector("[data-loop-region]")).toBeNull();
    }));

  it("읽기 전용에서도 동작한다", () =>
    withLayout(async () => {
      setup({ readOnly: true });
      await settle();
      fireEvent.click(edgeEl("b1"));
      expect(document.querySelectorAll('[data-loop-region="true"]')).toHaveLength(2);
    }));

  it("이름이 5개를 넘으면 외 N개", () =>
    withLayout(async () => {
      const g: Graph = {
        id: "g",
        name: "g",
        nodes: Array.from({ length: 7 }, (_, i) => ({ id: `n${i}`, type: "q-plain", label: `노드${i}`, position: { x: i * 200, y: 0 } })),
        edges: [
          ...Array.from({ length: 6 }, (_, i) => ({ id: `e${i}`, kind: "k-flow", source: { node: `n${i}`, port: "out" }, target: { node: `n${i + 1}`, port: "in" } })),
          { id: "back", kind: "k-back", source: { node: "n6", port: "out" }, target: { node: "n0", port: "in" } },
        ],
      };
      setup({}, g);
      await settle();
      fireEvent.click(edgeEl("back"));
      expect(live()).toBe("반복 영역: 노드 7개 — 노드0, 노드1, 노드2, 노드3, 노드4 외 2개");
    }));
});

describe("노드 카드: 겹친 카드·정의 바인딩·회차 배지", () => {
  const withBound = (): Graph => ({
    ...graph(),
    nodes: [...graph().nodes!, { id: "p", type: "q-bound", label: "검토 파이프라인", position: { x: 300, y: 200 } }, { id: "o", type: "q-odd-shape", label: "모양 모름", position: { x: 0, y: 200 } }],
  });
  const summary = (over: Partial<BindSummary> = {}): BindSummary => ({ title: "자식 구성", subtitle: "구성 종류", meta: "노드 5개", badges: [{ key: "v", title: "고정 3fa9c1b", fullTitle: "이 해시로 고정됨" }], open: { label: "열기", onOpen: () => {} }, ...over });

  it("ui_hints.shape가 stacked일 때만 겹친 카드, 모르는 값은 일반 카드", () =>
    plain(async () => {
      setup({}, withBound());
      await settle();
      expect(nodeEl("p").querySelector('[data-stacked="true"]')).toBeTruthy();
      expect(nodeEl("o").querySelector("[data-stacked]")).toBeNull();
      expect(nodeEl("w").querySelector("[data-stacked]")).toBeNull();
    }));

  it("바인딩 요약: 부제가 타입 제목을 대신하고 본문·배지·[열기]·접근성 이름", () =>
    plain(async () => {
      const onOpen = vi.fn();
      setup({ bindSummaries: { p: summary({ open: { label: "열기", onOpen } }) } }, withBound());
      await settle();
      const card = nodeEl("p");
      expect(card.querySelector(".ac-ge-node-type")!.textContent).toBe("구성 종류");
      expect(card.querySelector(".ac-ge-bind-meta")!.textContent).toBe("노드 5개");
      expect(card.querySelector(".ac-ge-bind .ac-ge-hint-chip")!.textContent).toBe("고정 3fa9c1b");
      expect(card.getAttribute("aria-label")).toBe("노드 검토 파이프라인, 타입 묶인 노드, 구성 종류 자식 구성, 노드 5개, 이 해시로 고정됨");
      fireEvent.click(within(card).getByRole("button", { name: /열기/ }));
      expect(onOpen).toHaveBeenCalledTimes(1);
    }));

  it("nodeAvatars: 지정한 노드만 아바타 글자·색이 바뀌고 나머지는 노드 타입 힌트", () =>
    plain(async () => {
      setup({ nodeAvatars: { p: { text: "Z", color: "#123456" } } }, withBound());
      await settle();
      const av = nodeEl("p").querySelector<HTMLElement>(".ac-ge-avatar")!;
      expect(av.textContent).toBe("Z");
      expect(av.style.getPropertyValue("--ac-ge-avatar")).toBe("#123456");
      expect(nodeEl("o").querySelector<HTMLElement>(".ac-ge-avatar")!.style.getPropertyValue("--ac-ge-avatar")).toBe("");
    }));

  it("[열기] 단추는 노드를 끌거나 선택하지 않는다(nodrag)", () =>
    plain(async () => {
      const onSelectionChange = vi.fn();
      setup({ bindSummaries: { p: summary() }, onSelectionChange }, withBound());
      await settle();
      fireEvent.click(within(nodeEl("p")).getByRole("button", { name: /열기/ }));
      expect(onSelectionChange).not.toHaveBeenCalled();
      expect(within(nodeEl("p")).getByRole("button", { name: /열기/ }).className).toContain("nodrag");
    }));

  it("Alt+Enter는 선택·포커스한 바인딩 노드의 [열기]를 부르고, 사유가 있으면 부르지 않는다", () =>
    plain(async () => {
      const onOpen = vi.fn();
      const view = setup({ bindSummaries: { p: summary({ open: { label: "열기", onOpen } }) } }, withBound());
      await settle();
      fireEvent.click(nodeEl("p"));
      fireEvent.keyDown(document.querySelector(".ac-ge-canvas")!, { key: "Enter", altKey: true });
      expect(onOpen).toHaveBeenCalledTimes(1);
      expect(live()).toContain("검토 파이프라인");
      view.unmount();
      const blocked = vi.fn();
      setup({ bindSummaries: { p: summary({ open: { label: "열기", onOpen: blocked, disabledReason: "저장 필요" } }) } }, withBound());
      await settle();
      fireEvent.click(nodeEl("p"));
      fireEvent.keyDown(document.querySelector(".ac-ge-canvas")!, { key: "Enter", altKey: true });
      expect(blocked).not.toHaveBeenCalled();
      const btn = within(nodeEl("p")).getByRole("button", { name: /열기/ });
      expect(btn.getAttribute("aria-disabled")).toBe("true");
      fireEvent.click(btn);
      expect(blocked).not.toHaveBeenCalled();
    }));

  it("읽기 전용에서도 Alt+Enter로 연다", () =>
    plain(async () => {
      const onOpen = vi.fn();
      setup({ readOnly: true, bindSummaries: { p: summary({ open: { label: "열기", onOpen } }) } }, withBound());
      await settle();
      fireEvent.click(nodeEl("p"));
      fireEvent.keyDown(document.querySelector(".ac-ge-canvas")!, { key: "Enter", altKey: true });
      expect(onOpen).toHaveBeenCalledTimes(1);
    }));

  it("정의 없음: 위험 점선 표시와 접근성 문구, [열기] 없음", () =>
    plain(async () => {
      setup({ bindSummaries: { p: { title: "ghost-id", subtitle: "구성 종류", missing: true, badges: [{ key: "m", title: "찾을 수 없음", tone: "danger" }] } } }, withBound());
      await settle();
      const card = nodeEl("p");
      expect(card.querySelector('[data-missing="true"]')).toBeTruthy();
      expect(card.querySelector(".ac-ge-bind-open")).toBeNull();
      expect(card.getAttribute("aria-label")).toContain("찾을 수 없음");
      expect(card.querySelector('.ac-ge-hint-chip[data-tone="danger"]')).toBeTruthy();
    }));

  it("회차 배지: 텍스트·접근성 이름·고른 표시·클릭, 노드 접근성 이름에도 포함", () =>
    plain(async () => {
      const onClick = vi.fn();
      setup({ readOnly: true, nodeRunBadges: { w: { text: "#3", ariaLabel: "작성자, 3회차, 완료. 실행 5개 중 3번째", picked: true, onClick }, r: { text: "×2", ariaLabel: "호출 2번" } } });
      await settle();
      const badge = within(nodeEl("w")).getByRole("button", { name: /3회차/ });
      expect(badge.textContent).toBe("#3");
      expect(badge.getAttribute("data-picked")).toBe("true");
      fireEvent.click(badge);
      expect(onClick).toHaveBeenCalledTimes(1);
      expect(nodeEl("w").getAttribute("aria-label")).toContain("3회차");
      // 클릭 콜백이 없으면 단추가 아니다
      const plain = within(nodeEl("r")).getByRole("img", { name: "호출 2번" });
      expect(plain.textContent).toBe("×2");
      expect(plain.getAttribute("data-picked")).toBeNull();
    }));

  it("배지가 없는 노드에는 아무것도 붙지 않는다", () =>
    plain(async () => {
      setup();
      await settle();
      expect(document.querySelector(".ac-ge-run-badge,.ac-ge-bind,.ac-ge-bind-actions")).toBeNull();
    }));
});

describe("팔레트: 정의 항목 부제와 비활성", () => {
  const lists = { "def-kind": [{ id: "d1", name: "가 구성", meta: "노드 5개" }, { id: "d2", name: "나 자신", meta: "노드 2개 · 입구 있음", disabledReason: "자기 자신은 넣을 수 없습니다" }] };
  it("부제 한 줄, 비활성 항목은 추가를 무시한다(정렬은 앱이 준 순서 그대로)", () => {
    const onAdd = vi.fn();
    render(<TeamPalette nodeTypes={nodeTypes} definitionLists={lists} definitionKindTitles={{ "def-kind": "구성" }} onAdd={onAdd} />);
    const items = screen.getAllByRole("button").filter((b) => b.classList.contains("ac-ge-palette-item"));
    expect(items[0]!.textContent).toContain("가 구성");
    expect(items[0]!.textContent).toContain("노드 5개");
    const blocked = items[1]!;
    expect(blocked.getAttribute("aria-disabled")).toBe("true");
    expect(blocked.getAttribute("draggable")).toBe("false");
    expect(blocked.title).toContain("자기 자신은 넣을 수 없습니다");
    fireEvent.doubleClick(blocked);
    fireEvent.keyDown(blocked, { key: "Enter" });
    expect(onAdd).not.toHaveBeenCalled();
    fireEvent.doubleClick(items[0]!);
    expect(onAdd).toHaveBeenCalledWith({ typeId: "q-bound", definition: { id: "d1", name: "가 구성" } });
  });
  it("구역의 항목이 모두 비활성(자기 자신뿐)이면 안내와 만들기 단추를 더한다", () => {
    const onCreate = vi.fn();
    const only = { "def-kind": [{ id: "d2", name: "나 자신", disabledReason: "자기 자신은 넣을 수 없습니다" }] };
    render(<TeamPalette nodeTypes={nodeTypes} definitionLists={only} definitionKindTitles={{ "def-kind": "구성" }} onAdd={() => {}} onCreateDefinition={onCreate} />);
    expect(screen.getByText("넣을 다른 구성이(가) 없습니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "구성 만들기" }));
    expect(onCreate).toHaveBeenCalledWith("def-kind");
  });
  it("비활성이 아닌 항목이 하나라도 있으면 안내가 없다", () => {
    render(<TeamPalette nodeTypes={nodeTypes} definitionLists={lists} definitionKindTitles={{ "def-kind": "구성" }} onAdd={() => {}} onCreateDefinition={() => {}} />);
    expect(screen.queryByText(/넣을 다른/)).toBeNull();
  });
  it("검색에는 비활성 항목도 나온다", () => {
    render(<TeamPalette nodeTypes={nodeTypes} definitionLists={lists} onAdd={() => {}} searchValue="나 자신" />);
    expect(screen.getByText("나 자신")).toBeTruthy();
  });
});

describe("연결 종류 선택(EdgeKindDialog): 비활성 행·기본 선택·배지", () => {
  const cands = edgeTypes.filter((t) => ["k-flow", "k-back", "k-fail"].includes(t.id));
  const render3 = (over: Partial<Parameters<typeof EdgeKindDialog>[0]> = {}) => {
    const onConfirm = vi.fn();
    render(
      <EdgeKindDialog
        edgeTypes={cands}
        preselected="k-flow"
        info={{ "k-flow": { disabledReason: "순환이 됩니다 — 반복 연결이 필요합니다" }, "k-back": { preferred: true } }}
        onConfirm={onConfirm}
        onCancel={() => {}}
        {...over}
      />,
    );
    return onConfirm;
  };
  it("preferred가 기본 선택이고 비활성 행에 사유가 보이며 종류 속성 배지가 붙는다", () => {
    render3();
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.find((r) => r.checked)!.value).toBe("k-back");
    const row = document.querySelector('[data-kind-row="k-flow"]')!;
    expect(row.getAttribute("aria-disabled")).toBe("true");
    expect(row.textContent).toContain("순환이 됩니다 — 반복 연결이 필요합니다");
    // 칩 나열은 없다: 제목 + 한 줄 설명만
    expect(document.querySelector("[data-kind-row] .ac-ge-badge, [data-kind-row] [data-badge]")).toBeNull();
  });
  it("비활성 행은 클릭·숫자키로 고를 수 없고 라이브 영역에 사유가 나온다", () => {
    const onConfirm = render3();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(screen.getAllByRole("radio")[0]!);
    expect((screen.getAllByRole("radio")[1] as HTMLInputElement).checked).toBe(true);
    fireEvent.keyDown(dialog, { key: "1" });
    expect((screen.getAllByRole("radio")[0] as HTMLInputElement).checked).toBe(false);
    expect(within(dialog).getByRole("status").textContent).toBe("순환이 됩니다 — 반복 연결이 필요합니다");
    fireEvent.keyDown(dialog, { key: "3" });
    expect((screen.getAllByRole("radio")[2] as HTMLInputElement).checked).toBe(true);
    expect(within(dialog).getByRole("status").textContent).toBe("");
    fireEvent.submit(dialog);
    expect(onConfirm).toHaveBeenCalledWith("k-fail");
  });
  it("Enter(제출)는 기본 선택(반복 종류)으로 확정된다", () => {
    const onConfirm = render3();
    fireEvent.submit(screen.getByRole("dialog"));
    expect(onConfirm).toHaveBeenCalledWith("k-back");
  });
  it("info가 없으면 이전 동작 그대로", () => {
    const onConfirm = render3({ info: undefined, preselected: "k-flow" });
    expect((screen.getAllByRole("radio")[0] as HTMLInputElement).checked).toBe(true);
    fireEvent.submit(screen.getByRole("dialog"));
    expect(onConfirm).toHaveBeenCalledWith("k-flow");
  });
});

describe("팔레트로 추가한 새 노드가 화면 밖이면 화면을 옮긴다", () => {
  function Stateful({ initial, ...rest }: { initial: Graph } & Partial<GraphEditorProps>) {
    const [g, setG] = useState(initial);
    return (
      <div style={{ width: 1000, height: 600 }}>
        <GraphEditor graph={g} nodeTypes={nodeTypes} edgeTypes={edgeTypes} showMinimap={false} onChange={(next) => setG(next)} {...rest} />
      </div>
    );
  }
  const rectOf = (w: number, h: number) => ({ width: w, height: h, left: 0, top: 0, right: w, bottom: h, x: 0, y: 0, toJSON() {} }) as DOMRect;
  const mockRects = () =>
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      return this.classList.contains("react-flow") ? rectOf(1000, 600) : rectOf(0, 0);
    });
  const lists = { "def-kind": [{ id: "d1", name: "새 구성" }] };

  it("뷰포트 밖에 놓이면 이동 안내가 나온다", () =>
    plain(async () => {
      const rect = mockRects();
      try {
        const g = graph();
        g.nodes![2]!.position = { x: 3000, y: 0 }; // 새 노드는 가장 오른쪽 노드의 오른쪽(+300)
        render(<Stateful initial={g} definitionLists={lists} definitionKindTitles={{ "def-kind": "구성" }} />);
        await settle();
        fireEvent.doubleClick(screen.getByText("새 구성"));
        await act(async () => {
          await new Promise((r) => setTimeout(r, 400));
        });
        expect(live()).toBe("새 구성을(를) 추가하고 화면을 옮겼습니다.");
      } finally {
        rect.mockRestore();
      }
    }));

  it("이미 화면 안이면 조용하다", () =>
    plain(async () => {
      const rect = mockRects();
      try {
        render(<Stateful initial={graph()} definitionLists={lists} definitionKindTitles={{ "def-kind": "구성" }} />);
        await settle();
        fireEvent.doubleClick(screen.getByText("새 구성"));
        await act(async () => {
          await new Promise((r) => setTimeout(r, 400));
        });
        expect(live()).toBe("새 구성 노드를 추가했습니다.");
      } finally {
        rect.mockRestore();
      }
    }));
});

describe("연결 종류 바꾸기(T)", () => {
  it("선택한 연결에서 T → 같은 선택 UI, 비활성 행 없이 고르면 onChange(edit-edge)로 종류만 바뀌고 설정은 비워진다", () =>
    withLayout(async () => {
      const g = graph();
      g.edges![0] = { ...g.edges![0]!, config: { stale: 1 } };
      const calls: Array<{ next: Graph; reason: string }> = [];
      setup({ onChange: (next, meta) => calls.push({ next, reason: meta.reason }) }, g);
      await settle();
      fireEvent.click(edgeEl("f1"));
      fireEvent.keyDown(document.querySelector(".ac-ge-canvas")!, { key: "t" });
      const dialog = screen.getByRole("dialog");
      expect((within(dialog).getAllByRole("radio").find((r) => (r as HTMLInputElement).checked) as HTMLInputElement).value).toBe("k-flow"); // 현재 종류가 미리 선택
      fireEvent.keyDown(dialog, { key: "3" });
      fireEvent.submit(dialog);
      expect(calls).toHaveLength(1);
      expect(calls[0]!.reason).toBe("edit-edge");
      const changed = calls[0]!.next.edges!.find((e) => e.id === "f1")!;
      expect(changed.kind).toBe("k-fail");
      expect(changed).not.toHaveProperty("config");
      expect(calls[0]!.next.edges!.find((e) => e.id === "f2")!.kind).toBe("k-flow"); // 다른 연결은 그대로
    }));

  it("순환을 닫는 흐름 종류로는 바꿀 수 없다(비활성), 같은 종류를 고르면 아무것도 바뀌지 않는다", () =>
    withLayout(async () => {
      const g = graph();
      // 반복 연결 b1(r→w)을 흐름 종류로 바꾸려 하면 w→r→… 경로가 닫혀 순환이 된다
      const calls: Graph[] = [];
      setup({ onChange: (next) => calls.push(next) }, g);
      await settle();
      fireEvent.click(edgeEl("b1"));
      fireEvent.keyDown(document.querySelector(".ac-ge-canvas")!, { key: "T" });
      const dialog = screen.getByRole("dialog");
      expect(dialog.querySelector('[data-kind-row="k-flow"]')!.getAttribute("aria-disabled")).toBe("true");
      expect(dialog.querySelector('[data-kind-row="k-back"]')!.getAttribute("aria-disabled")).toBeNull();
      fireEvent.submit(dialog); // 현재 종류(k-back) 그대로 확정
      expect(calls).toHaveLength(0);
    }));
});
