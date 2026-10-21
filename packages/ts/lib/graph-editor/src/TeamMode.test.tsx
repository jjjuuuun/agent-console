import { createRef } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Graph, Issue } from "@agent-console/contracts";
import { GraphEditor, IssueSuggestionButtons, RoleToggleRow, getRoleToggleInfo } from "./index";
import type { ChangeMeta, GraphEditorHandle, GraphEditorProps } from "./index";
import { teamEdgeTypes, teamGraph, teamNodeTypes } from "./testing";

beforeAll(() => {
  if (typeof globalThis.DOMMatrixReadOnly === "undefined") {
    globalThis.DOMMatrixReadOnly = class {
      m22 = 1;
      constructor() {}
    } as unknown as typeof DOMMatrixReadOnly;
  }
});
afterEach(cleanup);

function setup(over: Partial<GraphEditorProps> = {}, graph: Graph = teamGraph()) {
  const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
  const element = (g: Graph, p: Partial<GraphEditorProps> = {}) => (
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor
        graph={g}
        nodeTypes={teamNodeTypes}
        edgeTypes={teamEdgeTypes}
        showMinimap={false}
        resolvePorts={async () => ({ inputs: [{ name: "hears" }, { name: "asks" }], outputs: [{ name: "says" }] })}
        onChange={(next, meta) => calls.push({ next, meta })}
        {...over}
        {...p}
      />
    </div>
  );
  const r = render(element(graph));
  return { ...r, calls, rerender: (g: Graph, p?: Partial<GraphEditorProps>) => r.rerender(element(g, p)) };
}

const lists = { things: [{ id: "t1", name: "정의 하나", usageCount: 3 }, { id: "t2", name: "정의 둘" }] };

describe("팔레트 (정의 구역 + 기본 노드)", () => {
  it("binds 타입 × 정의 목록과 binds 없는 타입을 구역으로 보이고, 숨김 타입은 없다", () => {
    const { calls } = setup({ definitionLists: lists, definitionKindTitles: { things: "에이전트" } });
    const palette = screen.getByRole("navigation", { name: "노드 팔레트" });
    const defs = within(palette).getByRole("region", { name: "에이전트" });
    expect(within(defs).getByText("정의 하나")).toBeTruthy();
    expect(within(defs).getByText("3회 사용")).toBeTruthy();
    expect(within(palette).getByRole("region", { name: "기본 노드" })).toBeTruthy();
    expect(within(palette).queryByText("숨김 타입")).toBeNull();
    fireEvent.doubleClick(within(defs).getByText("정의 둘"));
    expect(calls[0]!.meta.reason).toBe("add-node");
    expect(calls[0]!.next.nodes!.at(-1)).toMatchObject({ type: "alpha-actor", label: "정의 둘", config: { thing_ref: "t2" } });
  });
  it("정의가 없는 구역은 안내와 [만들기] 콜백", () => {
    const onCreateDefinition = vi.fn();
    setup({ palette: { onCreateDefinition } });
    const palette = screen.getByRole("navigation", { name: "노드 팔레트" });
    fireEvent.click(within(palette).getAllByRole("button", { name: /만들기/ })[0]!);
    expect(onCreateDefinition).toHaveBeenCalledTimes(1);
  });
});

describe("노드 표현", () => {
  it("실행되지 않는 노드는 칩 카드, 상황 배지는 연결 속성에서", () => {
    const g = teamGraph();
    g.edges = [{ id: "s", kind: "e-start", source: { node: "h1", port: "says" }, target: { node: "a1", port: "in" } }];
    setup({}, g);
    expect(document.querySelectorAll('.ac-ge-node[data-compact="true"]')).toHaveLength(1);
    const a1 = screen.getByLabelText(/^노드 일꾼 하나/).querySelector(".ac-ge-badge");
    expect(a1?.textContent).toBe("입구");
  });
  it("waiting 노드: 상태 라벨과 경과 줄", () => {
    setup({ nodeStates: { h1: { status: "waiting" } }, waitingNodes: { h1: { since: "2026-01-01T00:00:00Z" } }, nowMs: Date.parse("2026-01-01T00:01:05Z") });
    expect(screen.getByText("대기 중(입력·승인)")).toBeTruthy();
    expect(screen.getByText("응답 대기 1분 5초")).toBeTruthy();
  });
  it("동적 포트(사용자 노드): resolvePorts 결과를 그린다", async () => {
    setup();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    expect(document.querySelector('[data-port="says"]')).toBeTruthy();
    expect(document.querySelector('[data-port="asks"]')).toBeTruthy();
  });
});

describe("리소스 보기", () => {
  it("끄면 리소스 노드·연결이 사라지고 도착 카드에 칩 줄이 생긴다(데이터 불변)", () => {
    const onOpen = vi.fn();
    const { calls } = setup({ showResources: false, onOpenResources: onOpen });
    expect(screen.queryByLabelText(/^노드 지침/)).toBeNull();
    expect(document.querySelectorAll(".ac-ge-edge-chip")).toHaveLength(0);
    const group = screen.getByLabelText(/^노드 일꾼 하나/).querySelector("button.ac-ge-rchips") as HTMLElement;
    expect(group.textContent).toContain("M1");
    fireEvent.click(group);
    expect(onOpen).toHaveBeenCalledWith("a1");
    expect(calls).toHaveLength(0);
  });
  it("토글 체크박스는 제어형 콜백을 부르고, V 키도 같은 동작", () => {
    const onShow = vi.fn();
    setup({ showResources: true, onShowResourcesChange: onShow });
    fireEvent.click(screen.getByRole("checkbox", { name: "리소스 보기" }));
    expect(onShow).toHaveBeenLastCalledWith(false);
    fireEvent.keyDown(document.querySelector(".ac-ge-canvas")!, { key: "v" });
    expect(onShow).toHaveBeenCalledTimes(2);
  });
  it("readonly-run: 팔레트 없음, 리소스 보기 기본 끔", () => {
    setup({ mode: "readonly-run" });
    expect(screen.queryByRole("navigation", { name: "노드 팔레트" })).toBeNull();
    expect(screen.queryByLabelText(/^노드 지침/)).toBeNull();
  });
});

describe("입구/답변/묻기 단축 조작", () => {
  it("캔버스 툴바 토글 → onChange(role-toggle)로 엣지 생성, 다시 누르면 삭제", () => {
    const onRoleToggle = vi.fn();
    const { calls, rerender } = setup({ onRoleToggle });
    fireEvent.click(screen.getByLabelText(/^노드 일꾼 하나/));
    const entry = screen.getByRole("button", { name: "입구" });
    expect(entry.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(entry);
    expect(calls[0]!.meta.reason).toBe("role-toggle");
    expect(calls[0]!.next.edges!.at(-1)).toMatchObject({ kind: "e-start", source: { node: "h1", port: "says" }, target: { node: "a1", port: "in" } });
    expect(onRoleToggle).toHaveBeenCalledWith("a1", "entry", true, undefined);
    rerender(calls[0]!.next);
    const on = screen.getByRole("button", { name: "입구" });
    expect(on.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(on);
    expect(calls[1]!.next.edges!.map((e) => e.id)).toEqual(["x1"]);
  });
  it("상대 사용자 노드 후보가 여럿이면 툴바가 고르게 한다(첫 후보 자동 선택 없음)", () => {
    const g = teamGraph();
    g.nodes = [...g.nodes!, { id: "h2", type: "beta-human", label: "둘째 사용자", config: {} }];
    const { calls } = setup({}, g);
    fireEvent.click(screen.getByLabelText(/^노드 일꾼 하나/));
    fireEvent.click(screen.getByRole("button", { name: "입구" }));
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole("menuitem", { name: "둘째 사용자" }));
    expect(calls[0]!.meta.reason).toBe("role-toggle");
    expect(calls[0]!.next.edges!.at(-1)).toMatchObject({ source: { node: "h2" }, target: { node: "a1" } });
  });
  function openChoiceMenu() {
    const g = teamGraph();
    g.nodes = [...g.nodes!, { id: "h2", type: "beta-human", label: "둘째 사용자", config: {} }];
    const r = setup({}, g);
    fireEvent.click(screen.getByLabelText(/^노드 일꾼 하나/));
    const toggle = screen.getByRole("button", { name: "입구" });
    toggle.focus();
    fireEvent.click(toggle);
    return { ...r, toggle, items: screen.getAllByRole("menuitem") };
  }
  it("후보 메뉴: 열리면 첫 항목에 포커스, 방향키/Home/End로 이동", () => {
    const { items } = openChoiceMenu();
    expect(items.length).toBeGreaterThan(1);
    expect(document.activeElement).toBe(items[0]);
    const menu = screen.getByRole("menu");
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    expect(document.activeElement).toBe(items.at(-1));
    fireEvent.keyDown(menu, { key: "Home" });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(menu, { key: "End" });
    expect(document.activeElement).toBe(items.at(-1));
  });
  it("후보 메뉴: Enter/Space(버튼 기본 동작=click)로 선택", () => {
    const { calls, items } = openChoiceMenu();
    // 브라우저는 버튼에서 Enter/Space를 click으로 바꾼다. 항목이 실제 button이라 그 경로를 그대로 탄다.
    expect(items.every((i) => i.tagName === "BUTTON")).toBe(true);
    fireEvent.click(items[0]!);
    expect(calls[0]!.meta.reason).toBe("role-toggle");
    expect(screen.queryByRole("menu")).toBeNull();
  });
  it("후보 메뉴: Escape로 닫히고 포커스가 토글 버튼으로 돌아간다", () => {
    const { toggle, calls } = openChoiceMenu();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(toggle);
    expect(calls).toHaveLength(0);
  });
  it("후보 메뉴: 선택 노드가 바뀌면 닫히고, 원래 노드로 돌아와도 다시 열리지 않는다", () => {
    openChoiceMenu();
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/^노드 지침/));
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(screen.getByLabelText(/^노드 일꾼 하나/));
    expect(screen.queryByRole("menu")).toBeNull();
  });
  it("적용할 수 없는 노드(리소스 칩 카드)에는 토글 버튼이 없다", () => {
    setup();
    fireEvent.click(screen.getByLabelText(/^노드 지침/));
    expect(screen.queryByRole("button", { name: "입구" })).toBeNull();
    expect(screen.queryByRole("button", { name: "답변" })).toBeNull();
  });
  it("패널 슬롯 ctx와 ref 핸들로도 같은 동작", () => {
    const ref = createRef<GraphEditorHandle>();
    let ctxSeen: { askOn?: boolean; canRes?: boolean } = {};
    const { calls } = setup({
      ref,
      renderConfigPanel: (c) => {
        ctxSeen = { askOn: c.roleToggles?.interaction.available, canRes: c.canHaveResources };
        return <button onClick={() => c.onToggleRole?.("interaction", true)}>묻기 켜기</button>;
      },
    });
    fireEvent.click(screen.getByLabelText(/^노드 일꾼 둘/));
    expect(ctxSeen).toEqual({ askOn: true, canRes: true });
    fireEvent.click(screen.getByRole("button", { name: "묻기 켜기" }));
    expect(calls[0]!.next.edges!.at(-1)).toMatchObject({ kind: "e-ask" });
    expect(ref.current!.getRoleToggleInfo("a1").exit.available).toBe(true);
    expect(ref.current!.canHaveResources("h1")).toBe(false);
    act(() => {
      expect(ref.current!.toggleRole("a2", "exit", true)).toBe(true);
    });
    expect(calls[1]!.meta.reason).toBe("role-toggle");
  });
  it("readOnly에서는 변경하지 않는다", () => {
    const ref = createRef<GraphEditorHandle>();
    const { calls } = setup({ ref, mode: "readonly-run" });
    expect(ref.current!.toggleRole("a1", "entry", true)).toBe(false);
    expect(calls).toHaveLength(0);
  });
});

describe("이슈 제안 적용", () => {
  const issue: Issue = {
    severity: "error",
    code: "any.code",
    message: "입구가 없습니다",
    suggestions: [
      { id: "s1", label: "사용자 → 일꾼 하나 입구로 연결", patch: { add_edges: [{ id: "ne", kind: "e-start", source: { node: "h1", port: "says" }, target: { node: "a1", port: "in" } }] } },
      { id: "s2", label: "둘째 제안" },
      { id: "s3", label: "셋째" },
      { id: "s4", label: "넷째" },
    ],
  };
  it("applySuggestion: patch를 적용해 onChange(apply-suggestion)로 낸다", () => {
    const ref = createRef<GraphEditorHandle>();
    const onApplySuggestion = vi.fn();
    const { calls } = setup({ ref, onApplySuggestion });
    act(() => {
      expect(ref.current!.applySuggestion(issue, issue.suggestions![0]!)).toBe(true);
    });
    expect(calls[0]!.meta.reason).toBe("apply-suggestion");
    expect(calls[0]!.next.edges!.map((e) => e.id)).toEqual(["x1", "ne"]);
    expect(onApplySuggestion).toHaveBeenCalledWith(issue, issue.suggestions![0]);
    act(() => {
      expect(ref.current!.applySuggestion(issue, issue.suggestions![1]!)).toBe(false); // patch 없음
    });
    expect(onApplySuggestion).toHaveBeenCalledTimes(1); // 적용되지 않은 제안은 알리지 않는다
  });
  it("버튼: 최대 3개 인라인 + 더 보기 메뉴, 제안이 없으면 아무것도 그리지 않는다", () => {
    const onApply = vi.fn();
    const { container, rerender } = render(<IssueSuggestionButtons issue={issue} onApply={onApply} />);
    expect(screen.getAllByRole("button")).toHaveLength(4); // 3 + 더 보기
    fireEvent.click(screen.getByRole("button", { name: "더 보기" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "넷째" }));
    expect(onApply).toHaveBeenCalledWith(issue, issue.suggestions![3]);
    rerender(<IssueSuggestionButtons issue={{ ...issue, suggestions: [] }} onApply={onApply} />);
    expect(container.textContent).toBe("");
  });
});

describe("RoleToggleRow", () => {
  it("info로만 그리고, 켤 수 없으면 이유를 보인다", () => {
    const onToggle = vi.fn();
    const g = teamGraph();
    const ctx = { nodeTypes: teamNodeTypes, edgeTypes: teamEdgeTypes };
    const { rerender } = render(<RoleToggleRow info={getRoleToggleInfo("a1", "entry", g, ctx)} label="입구" onToggle={onToggle} />);
    fireEvent.click(screen.getByRole("switch", { name: "입구" }));
    expect(onToggle).toHaveBeenCalledWith(true, undefined);
    rerender(<RoleToggleRow info={getRoleToggleInfo("m1", "entry", g, ctx)} label="입구" onToggle={onToggle} />);
    expect((screen.getByRole("switch") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("이 노드에 쓸 수 있는 연결 종류가 없습니다")).toBeTruthy();
  });
});
