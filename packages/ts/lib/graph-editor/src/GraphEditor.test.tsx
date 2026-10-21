import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { GraphEditor } from "./index";
import type { ChangeMeta, GraphEditorProps } from "./index";
import { descriptors, edgeTypes, sampleGraph } from "./testing";

beforeAll(() => {
  // happy-dom은 ResizeObserver를 제공한다(레이아웃 값은 0). DOMMatrixReadOnly만 없을 때 최소 폴리필.
  if (typeof globalThis.DOMMatrixReadOnly === "undefined") {
    globalThis.DOMMatrixReadOnly = class {
      m22 = 1;
      constructor() {}
    } as unknown as typeof DOMMatrixReadOnly;
  }
});
afterEach(cleanup);

function setup(over: Partial<GraphEditorProps> = {}, graph: Graph = sampleGraph()) {
  const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
  const view = (g: Graph, p: Partial<GraphEditorProps> = {}) => (
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor
        graph={g}
        nodeTypes={descriptors}
        edgeTypes={edgeTypes}
        showMinimap={false}
        onChange={(next, meta) => calls.push({ next, meta })}
        {...over}
        {...p}
      />
    </div>
  );
  const r = render(view(graph));
  return { ...r, calls, rerender: (g: Graph, p?: Partial<GraphEditorProps>) => r.rerender(view(g, p)) };
}

describe("GraphEditor 렌더 (디스크립터만으로, 타입별 분기 없음)", () => {
  it("임의 이름의 노드 타입 3종 + 모르는 타입을 모두 그린다", () => {
    setup();
    for (const label of ["시작", "분기", "끝", "유령"]) expect(screen.getByText(label)).toBeTruthy();
    // 타입 제목(정적 포트 노드의 입력 포트 라벨 포함)
    const canvas = within(document.querySelector<HTMLElement>(".ac-ge-canvas")!);
    expect(canvas.getByText("원천 노드")).toBeTruthy();
    expect(canvas.getByText("갈래 나누기")).toBeTruthy();
    expect(canvas.getByText("입력")).toBeTruthy();
    // 모르는 타입: 부제와 data-unknown-type, 엣지에서 복원된 포트
    expect(canvas.getByText("알 수 없는 타입: ghost-type-not-registered")).toBeTruthy();
    expect(document.querySelectorAll('[data-unknown-type="true"]').length).toBe(1);
    expect(document.querySelector('[data-port="ghost-out"]')).toBeTruthy();
  });

  it("ui_hints가 있으면 쓰고, 없거나 해석 불가하면 제목 첫 글자 + 분류색 폴백", () => {
    setup();
    const avatars = [...document.querySelectorAll(".ac-ge-node .ac-ge-avatar")].map((a) => a.textContent);
    expect(avatars).toContain("Z"); // 유효한 icon
    expect(avatars).toContain("갈"); // 너무 긴 icon → 제목 첫 글자
    expect(avatars).toContain("S"); // hints 없음 → 영문 대문자
    const nodes = [...document.querySelectorAll<HTMLElement>(".ac-ge-node")];
    const accents = nodes.map((n) => n.style.getPropertyValue("--ac-ge-accent"));
    expect(accents).toContain("#3b82f6");
    expect(accents.filter((a) => a.startsWith("var(--ac-cat-")).length).toBeGreaterThanOrEqual(2); // 해석 불가 color는 무시
    expect(accents.some((a) => a.includes("javascript"))).toBe(false);
  });

  it("상태 오버레이는 data-status 속성과 messages 라벨만 쓴다(모르는 상태는 원문)", () => {
    setup({
      nodeStates: {
        n1: { status: "succeeded", summary: "1.2초 · 340 토큰" },
        n2: { status: "running", attempt: 2 },
        n3: { status: "some-future-status" },
      },
      messages: { statusLabels: { running: "RUN!" } },
    });
    const statuses = [...document.querySelectorAll(".ac-ge-node[data-status]")].map((n) => n.getAttribute("data-status"));
    expect(statuses.sort()).toEqual(["running", "some-future-status", "succeeded"]);
    expect(screen.getByText("RUN!")).toBeTruthy();
    expect(screen.getByText("성공")).toBeTruthy();
    expect(screen.getByText("some-future-status")).toBeTruthy();
    expect(screen.getByText("1.2초 · 340 토큰")).toBeTruthy();
    expect(screen.getByText("×2")).toBeTruthy();
  });

  it("동적 포트는 resolvePorts 결과로 그리고, 응답 전에는 포트 없이 표시", async () => {
    vi.useFakeTimers();
    try {
      const resolvePorts = vi.fn(async (_t: string, cfg: unknown) => {
        const branches = ((cfg as { branches?: string[] }).branches ?? []).map((b) => ({ name: b, label: `갈래 ${b}` }));
        return { inputs: [{ name: "in" }], outputs: branches };
      });
      setup({ resolvePorts });
      expect(document.querySelector('[data-port="b"]')).toBeNull(); // 아직 계산 전
      await act(async () => {
        await vi.advanceTimersByTimeAsync(350);
      });
      expect(resolvePorts).toHaveBeenCalledTimes(1);
      expect(resolvePorts).toHaveBeenCalledWith("omega-splitter", { branches: ["a", "b"] });
      expect(screen.getByText("갈래 a")).toBeTruthy();
      expect(screen.getByText("갈래 b")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("포트 계산 실패 시 경고 문구를 표시한다", async () => {
    vi.useFakeTimers();
    try {
      setup({ resolvePorts: () => Promise.reject(new Error("boom")) });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(350);
      });
      expect(screen.getByText("포트를 계산하지 못했습니다")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("노드 접근성 이름에 라벨·타입·상태가 들어간다", () => {
    setup({ nodeStates: { n1: { status: "failed" } } });
    expect(screen.getByLabelText("노드 시작, 타입 원천 노드, 상태 실패")).toBeTruthy();
  });

  it("긴 제목은 title 속성에 전체가 있고 말줄임 클래스를 쓴다", () => {
    setup();
    const long = document.querySelector('.ac-ge-node-type[title^="Sink with"]');
    expect(long).toBeTruthy();
    expect(long?.classList.contains("ac-ellipsis")).toBe(true);
  });
});

describe("편집 동작", () => {
  it("팔레트: 그룹은 category 문자열 그대로, 더블클릭/Enter로 노드 추가 → onChange(add-node)", () => {
    const { calls } = setup();
    const palette = screen.getByRole("navigation", { name: "노드 팔레트" });
    expect(within(palette).getByRole("region", { name: "분기" })).toBeTruthy();
    expect(within(palette).getByRole("region", { name: "흐름-가" })).toBeTruthy();
    expect(within(palette).getByRole("region", { name: "기타" })).toBeTruthy(); // 빈 category
    fireEvent.doubleClick(within(palette).getByText("원천 노드"));
    expect(calls).toHaveLength(1);
    const first = calls[0]!;
    expect(first.meta.reason).toBe("add-node");
    const added = first.next.nodes!.at(-1)!;
    expect(added).toMatchObject({ id: "n5", type: "zeta-source", label: "원천 노드" });
    // 모르는 필드 보존
    expect(first.next["custom_field"]).toEqual({ keep: "me" });
    expect(first.next.groups).toEqual([{ id: "grp" }]);
    fireEvent.keyDown(within(palette).getByText("갈래 나누기").closest("button")!, { key: "Enter" });
    expect(calls[1]!.meta.reason).toBe("add-node");
  });

  it("팔레트 검색", () => {
    setup();
    const palette = screen.getByRole("navigation", { name: "노드 팔레트" });
    fireEvent.change(within(palette).getByRole("searchbox"), { target: { value: "갈래" } });
    expect(within(palette).queryByText("원천 노드")).toBeNull();
    fireEvent.change(within(palette).getByRole("searchbox"), { target: { value: "zzz-none" } });
    expect(within(palette).getByText("일치하는 노드 타입이 없습니다")).toBeTruthy();
  });

  it("삭제 → 5초 되돌리기 토스트 → 되돌리기는 이전 그래프를 onChange로 돌려준다", () => {
    vi.useFakeTimers();
    try {
      const g = sampleGraph();
      const { calls, rerender } = setup({}, g);
      const node = screen.getByLabelText(/^노드 시작/);
      fireEvent.click(node);
      fireEvent.keyDown(node, { key: "Delete" });
      expect(calls).toHaveLength(1);
      const del = calls[0]!;
      expect(del.meta.reason).toBe("remove");
      expect(del.next.nodes!.map((n) => n.id)).toEqual(["n2", "n3", "n4"]);
      expect(del.next.edges!.map((e) => e.id)).toEqual(["e2", "e3"]); // 붙은 엣지 e1 함께 삭제
      rerender(del.next);
      const undo = screen.getByRole("button", { name: "되돌리기" });
      fireEvent.click(undo);
      expect(calls[1]!.meta.reason).toBe("undo");
      expect(calls[1]!.next).toBe(g);
    } finally {
      vi.useRealTimers();
    }
  });

  it("되돌리기 토스트는 5초 뒤 사라진다", () => {
    vi.useFakeTimers();
    try {
      const { calls, rerender } = setup();
      const node = screen.getByLabelText(/^노드 끝/);
      fireEvent.click(node);
      fireEvent.keyDown(node, { key: "Backspace" });
      rerender(calls[0]!.next);
      expect(screen.getByRole("button", { name: "되돌리기" })).toBeTruthy();
      act(() => {
        vi.advanceTimersByTime(5001);
      });
      expect(screen.queryByRole("button", { name: "되돌리기" })).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("Ctrl+D 복제: 새 id, 위치 오프셋, 선택 노드 사이 엣지도 복제", () => {
    const { calls } = setup();
    const a = screen.getByLabelText(/^노드 시작/);
    fireEvent.click(a);
    fireEvent.keyDown(a, { key: "d", ctrlKey: true });
    expect(calls[0]!.meta.reason).toBe("duplicate");
    const copy = calls[0]!.next.nodes!.at(-1)!;
    expect(copy).toMatchObject({ id: "n5", label: "시작 2", position: { x: 24, y: 24 }, extra_node_field: 1 });
  });

  it("readOnly: 팔레트·편집 버튼 없음, 삭제 키 무시, 설정 패널 슬롯은 동작", () => {
    const render_ = vi.fn(() => <div>패널 내용</div>);
    const { calls } = setup({ readOnly: true, renderConfigPanel: render_ });
    expect(screen.queryByRole("navigation", { name: "노드 팔레트" })).toBeNull();
    const node = screen.getByLabelText(/^노드 시작/);
    fireEvent.click(node);
    fireEvent.keyDown(node, { key: "Delete" });
    expect(calls).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "삭제" })).toBeNull();
    expect(screen.getByText("패널 내용")).toBeTruthy();
    const ctx = (render_.mock.calls.at(-1) as unknown as [{ node?: { id: string }; descriptor?: { id: string }; multi: number }])[0];
    expect(ctx.node?.id).toBe("n1");
    expect(ctx.descriptor?.id).toBe("zeta-source");
    expect(ctx.multi).toBe(1);
  });

  it("설정 패널에서 label/config 수정 → edit-label / edit-config", () => {
    const { calls } = setup({
      renderConfigPanel: (ctx) => (
        <div>
          <button onClick={() => ctx.onChangeNode({ label: "새 이름" })}>이름</button>
          <button onClick={() => ctx.onChangeNode({ config: { x: 1 } })}>설정</button>
        </div>
      ),
    });
    fireEvent.click(screen.getByLabelText(/^노드 시작/));
    fireEvent.click(screen.getByRole("button", { name: "이름" }));
    fireEvent.click(screen.getByRole("button", { name: "설정" }));
    expect(calls.map((c) => c.meta.reason)).toEqual(["edit-label", "edit-config"]);
    expect(calls[0]!.next.nodes![0]!.label).toBe("새 이름");
  });

  it("이슈 배지: 오류 ✕와 경고 ▲를 개수와 함께, 접근성 이름 포함. 노드 aria에 반영", () => {
    setup({
      issues: [
        { severity: "error", code: "a", message: "x", node_id: "n1" },
        { severity: "error", code: "a", message: "x", node_id: "n1" },
        { severity: "warning", code: "b", message: "y", node_id: "n1" },
        { severity: "warning", code: "b", message: "y", node_id: "n3" },
        { severity: "error", code: "e", message: "z", edge_id: "e1" },
      ],
    });
    const badge = screen.getByRole("img", { name: "검증 오류 2건, 경고 1건" });
    expect(badge.textContent).toBe("✕2▲1");
    expect(screen.getByRole("img", { name: "경고 1건" }).textContent).toBe("▲1");
    expect(screen.getByLabelText(/^노드 시작.*검증 오류 2건, 경고 1건$/)).toBeTruthy();
  });

  it("focusRequest에 edgeId가 있으면 노드가 아니라 그 연결을 선택한다(없는 연결이면 nodeId 노드)", () => {
    const panel = vi.fn(() => <div>패널</div>);
    setup({ focusRequest: { nodeId: "n3", token: 1, edgeId: "e1" }, renderConfigPanel: panel });
    const ctx = () => (panel.mock.calls.at(-1) as unknown as [{ node?: { id: string }; edge?: { id: string } }])[0];
    expect(ctx().edge?.id).toBe("e1");
    expect(ctx().node).toBeUndefined();
  });

  it("focusRequest: 선택하고, 같은 nodeId라도 token이 바뀌면 다시 포커스", () => {
    const panel = vi.fn(() => <div>패널</div>);
    const { rerender } = setup({ focusRequest: { nodeId: "n3", token: 1 }, renderConfigPanel: panel });
    const last = () => (panel.mock.calls.at(-1) as unknown as [{ node?: { id: string } }])[0].node?.id;
    expect(last()).toBe("n3");
    fireEvent.click(screen.getByLabelText(/^노드 시작/)); // 사용자가 다른 노드를 선택
    expect(last()).toBe("n1");
    rerender(sampleGraph(), { focusRequest: { nodeId: "n3", token: 1 }, renderConfigPanel: panel }); // 같은 token: 무반응
    expect(last()).toBe("n1");
    rerender(sampleGraph(), { focusRequest: { nodeId: "n3", token: 2 }, renderConfigPanel: panel });
    expect(last()).toBe("n3");
  });
});

/** 레이아웃이 없는 환경에서 React Flow가 노드/핸들 치수를 측정하게 하고(관찰 시작 즉시 콜백), 끝나면 되돌린다. */
async function withLayout(run: () => Promise<void>): Promise<void> {
  const original = globalThis.ResizeObserver;
  const proto = HTMLElement.prototype;
  const offW = Object.getOwnPropertyDescriptor(proto, "offsetWidth");
  const offH = Object.getOwnPropertyDescriptor(proto, "offsetHeight");
  Object.defineProperty(proto, "offsetWidth", { configurable: true, get: () => 160 });
  Object.defineProperty(proto, "offsetHeight", { configurable: true, get: () => 80 });
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

describe("연결선이 선택된 상태에서 노드 클릭 (연결 직후 첫 클릭 미선택 회귀)", () => {
  it("연결선 선택 -> 노드 클릭 한 번으로 노드가 선택되고 연결선 선택은 풀린다", () =>
    withLayout(async () => {
    const panel = vi.fn(() => <div>패널</div>);
    const onSel = vi.fn();
    setup({ renderConfigPanel: panel, onSelectionChange: onSel });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    const edge = document.querySelector<HTMLElement>(".react-flow__edge");
    expect(edge).toBeTruthy();
    fireEvent.click(edge!);
    expect(onSel.mock.calls.at(-1)![0].edgeIds.length).toBe(1);
    fireEvent.click(screen.getByLabelText(/^노드 시작/));
    expect(onSel.mock.calls.at(-1)![0]).toEqual({ nodeIds: ["n1"], edgeIds: [] });
    const last = (panel.mock.calls.at(-1) as unknown as [{ node?: { id: string } }])[0];
    expect(last.node?.id).toBe("n1");
    }));
});

describe("연결 드래그 중 auto 포트 라벨", () => {
  it("연결을 끌기 시작하면 data-connecting이 켜지고, 놓으면 꺼진다", () =>
    withLayout(async () => {
      const { container } = setup();
      const root = container.querySelector<HTMLElement>(".ac-ge-root")!;
      expect(root.getAttribute("data-connecting")).toBeNull();
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });
      const handle = container.querySelector<HTMLElement>(".ac-ge-handle.source")!;
      act(() => {
        fireEvent.mouseDown(handle, { clientX: 10, clientY: 10, button: 0 });
        fireEvent.mouseMove(document, { clientX: 60, clientY: 60 });
      });
      expect(root.getAttribute("data-connecting")).toBe("true");
      act(() => {
        fireEvent.mouseUp(document, { clientX: 500, clientY: 500 });
      });
      expect(root.getAttribute("data-connecting")).toBeNull();
    }));
});
