import { createRef } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { GraphEditor } from "./index";
import type { ChangeMeta, GraphEditorHandle, GraphEditorProps } from "./index";
import { descriptors, edgeTypes, sampleGraph } from "./testing";

beforeAll(() => {
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
  const handle = createRef<GraphEditorHandle>();
  render(
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor ref={handle} graph={graph} nodeTypes={descriptors} edgeTypes={edgeTypes} onChange={(next, meta) => calls.push({ next, meta })} {...over} />
    </div>,
  );
  return { calls, handle };
}

describe("5.2R.20 캔버스 도구줄 슬롯·미니맵 토글·오버레이 팔레트", () => {
  it("canvasActions 슬롯을 좌상단에 그리고, 읽기 전용에서는 그리지 않는다", () => {
    setup({ showMinimap: false, canvasActions: <button type="button">앱 단추</button> });
    expect(screen.getByRole("button", { name: "앱 단추" }).closest(".ac-ge-actions")).toBeTruthy();
    cleanup();
    setup({ showMinimap: false, readOnly: true, canvasActions: <button type="button">앱 단추</button> });
    expect(screen.queryByRole("button", { name: "앱 단추" })).toBeNull();
  });

  it("onShowMinimapChange가 있으면 토글 단추가 생기고 누른 값의 반대를 알린다(제어형)", () => {
    const onChange = vi.fn();
    setup({ showMinimap: false, onShowMinimapChange: onChange });
    const toggle = screen.getByRole("button", { name: "미니맵 보기" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(document.querySelector(".react-flow__minimap")).toBeNull();
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
    cleanup();
    setup({ showMinimap: true, onShowMinimapChange: onChange });
    expect(screen.getByRole("button", { name: "미니맵 숨기기" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("토글 콜백이 없으면 단추가 없다(기존 동작)", () => {
    setup({ showMinimap: false });
    expect(screen.queryByRole("button", { name: /미니맵/ })).toBeNull();
  });

  it("paletteOverlay면 paletteOpen일 때만 팔레트가 보이고 Esc로 닫기를 요청한다", () => {
    const onClose = vi.fn();
    setup({ showMinimap: false, paletteOverlay: true, paletteOpen: false });
    expect(document.querySelector(".ac-ge-palette-wrap")).toBeNull();
    cleanup();
    setup({ showMinimap: false, paletteOverlay: true, paletteOpen: true, onPaletteClose: onClose });
    const wrap = document.querySelector<HTMLElement>(".ac-ge-palette-wrap")!;
    expect(wrap.getAttribute("data-overlay")).toBe("true");
    // 열리면 포커스가 팔레트 안으로 와서 키보드로 이어 쓰고 Esc로 닫는다
    expect(wrap.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document.activeElement ?? wrap, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("handle.addNodeAtCenter: 노드를 추가·선택하고 새 id를 돌려준다(레이아웃이 없으면 기본 배치로 폴백)", () => {
    const { calls, handle } = setup({ showMinimap: false });
    const before = (sampleGraph().nodes ?? []).length;
    let id: string | undefined;
    act(() => {
      id = handle.current?.addNodeAtCenter("zeta-source");
    });
    expect(id).toBeTruthy();
    const last = calls.at(-1)!;
    expect(last.meta.reason).toBe("add-node");
    expect(last.next.nodes).toHaveLength(before + 1);
    expect(last.next.nodes?.at(-1)).toMatchObject({ id, type: "zeta-source" });
    // 모르는 타입은 undefined
    act(() => {
      id = handle.current?.addNodeAtCenter("no-such-type");
    });
    expect(id).toBeUndefined();
  });
});
