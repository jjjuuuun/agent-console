import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defaultMessages } from "../messages";
import { EdgeWaypointLayer } from "./EdgeWaypointLayer";
import type { EdgeWaypointLayerProps } from "./EdgeWaypointLayer";

afterEach(cleanup);

const SRC = { x: 0, y: 0 };
const TGT = { x: 200, y: 0 };

function setup(over: Partial<EdgeWaypointLayerProps> = {}, outerKey?: () => void) {
  const fns = { onDraft: vi.fn(), onCommit: vi.fn(), onLimit: vi.fn(), onAnnounce: vi.fn(), onExit: vi.fn(), onZoomHint: vi.fn() };
  const props: EdgeWaypointLayerProps = {
    source: SRC,
    target: TGT,
    waypoints: [{ x: 100, y: 80 }],
    segments: [
      { from: SRC, to: { x: 100, y: 80 } },
      { from: { x: 100, y: 80 }, to: TGT },
    ],
    zoom: 1,
    screenToFlow: (p) => p, // 화면 = 플로우 좌표
    snapGrid: 8,
    keyboardMode: false,
    messages: defaultMessages,
    ...fns,
    ...over,
  };
  const r = render(
    <div onKeyDown={outerKey}>
      <EdgeWaypointLayer {...props} />
    </div>,
  );
  const wp = (i: number) => r.container.querySelector<HTMLElement>(`[data-wp="${i}"]`)!;
  const mid = (i: number) => r.container.querySelector<HTMLElement>(`[data-mid="${i}"]`)!;
  return { ...r, ...fns, wp, mid };
}

const down = (el: HTMLElement, x: number, y: number) => fireEvent.pointerDown(el, { clientX: x, clientY: y, button: 0, pointerId: 1 });
const move = (el: HTMLElement, x: number, y: number, extra: object = {}) => fireEvent.pointerMove(el, { clientX: x, clientY: y, pointerId: 1, ...extra });
const up = (el: HTMLElement, x: number, y: number) => fireEvent.pointerUp(el, { clientX: x, clientY: y, pointerId: 1 });
const frame = () => act(async () => { await new Promise((r) => setTimeout(r, 40)); });

describe("EdgeWaypointLayer: 렌더", () => {
  it("경유점 n개와 중점 n+1개를 그리고 접근성 이름을 단다(§6.2)", () => {
    const { wp, mid } = setup();
    expect(wp(0).getAttribute("aria-label")).toBe("경유점 1/1, 위치 x 100 y 80. 화살표 키로 이동, Delete로 삭제");
    expect(wp(0).getAttribute("aria-roledescription")).toBe("경유점");
    expect(wp(0).getAttribute("role")).toBe("button");
    expect(mid(0).getAttribute("aria-label")).toBe("경유점 추가 위치 1");
    expect(mid(1)).toBeTruthy();
    expect(mid(2)).toBeNull();
  });
  it("줌 보정: 화면 크기를 유지하도록 scale(1/zoom)을 건다", () => {
    const { wp } = setup({ zoom: 2 });
    expect(wp(0).style.transform).toContain("scale(0.5)");
  });
  it("줌이 0.5 미만이면 조작 점을 숨기고 안내를 요청한다", () => {
    const { container, onZoomHint } = setup({ zoom: 0.4 });
    expect(container.querySelector("[data-wp]")).toBeNull();
    expect(onZoomHint).toHaveBeenCalled();
  });
  it("탭 순서는 경로 편집 모드에서만 0", () => {
    const a = setup({ keyboardMode: false });
    expect(a.wp(0).tabIndex).toBe(-1);
    cleanup();
    const b = setup({ keyboardMode: true });
    expect(b.wp(0).tabIndex).toBe(0);
    expect(b.mid(0).tabIndex).toBe(0);
    expect(document.activeElement).toBe(b.wp(0)); // 모드 진입 때 첫 조작 점에 포커스
  });
});

describe("EdgeWaypointLayer: 포인터", () => {
  it("경유점 드래그: 중간 값은 onDraft로만, 손을 뗄 때 onCommit 1회(격자 스냅)", async () => {
    const { wp, onDraft, onCommit } = setup();
    down(wp(0), 100, 80);
    move(wp(0), 101, 81); // 임계 3px 미만: 드래그 아님
    await frame();
    expect(onDraft).not.toHaveBeenCalled();
    move(wp(0), 130, 93);
    move(wp(0), 150, 101);
    await frame();
    expect(onDraft).toHaveBeenCalled();
    expect(onCommit).not.toHaveBeenCalled();
    up(wp(0), 150, 101);
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith([{ x: 152, y: 104 }]);
    expect(onDraft).toHaveBeenLastCalledWith(null);
  });
  it("Alt는 스냅 해제, Shift는 축 고정", () => {
    const a = setup();
    down(a.wp(0), 100, 80);
    move(a.wp(0), 133, 97, { altKey: true });
    up(a.wp(0), 133, 97);
    expect(a.onCommit).toHaveBeenCalledWith([{ x: 133, y: 97 }]);
    cleanup();
    const b = setup({ target: { x: 200, y: 100 } });
    down(b.wp(0), 100, 80);
    move(b.wp(0), 160, 90, { shiftKey: true }); // 이전 점 = 소스(0,0): 가로가 크면 y=0
    up(b.wp(0), 160, 90);
    expect(b.onCommit).toHaveBeenCalledWith([{ x: 160, y: 0 }]);
  });
  it("클릭만(이동 없음)은 아무것도 내보내지 않는다", () => {
    const { wp, onCommit, onDraft } = setup();
    down(wp(0), 100, 80);
    up(wp(0), 100, 80);
    expect(onCommit).not.toHaveBeenCalled();
    expect(onDraft).not.toHaveBeenCalled();
  });
  it("앞뒤 점과 일직선(6px 이내)에 놓으면 자동 삭제, 드래그 중에는 흐려진다", () => {
    const { wp, onCommit, container } = setup();
    down(wp(0), 100, 80);
    move(wp(0), 104, 2); // 소스(0,0)~타깃(200,0) 선에서 2px(스냅 후 0)
    expect(container.querySelector('[data-wp="0"]')!.getAttribute("data-dimmed")).toBe("true");
    up(wp(0), 104, 2);
    expect(onCommit).toHaveBeenCalledWith([]);
  });
  it("줌이 2배면 일직선 허용 거리는 캔버스 3px(화면 6px)", () => {
    const { wp, onCommit } = setup({ zoom: 2, snapGrid: false });
    down(wp(0), 100, 80);
    move(wp(0), 100, 4); // 캔버스 4px > 3px
    up(wp(0), 100, 4);
    expect(onCommit).toHaveBeenCalledWith([{ x: 100, y: 4 }]);
  });
  it("중점을 임계 넘게 끌면 그 자리에 경유점을 만들고 이어서 드래그, 커밋은 1회", () => {
    const { mid, onCommit } = setup({ waypoints: [] , segments: [{ from: SRC, to: TGT }] });
    down(mid(0), 100, 0);
    move(mid(0), 101, 0);
    move(mid(0), 104, 40);
    move(mid(0), 104, 56);
    up(mid(0), 104, 56);
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith([{ x: 104, y: 56 }]);
  });
  it("중점을 끌어도 16개 상한이면 만들지 않고 onLimit", () => {
    const wps = Array.from({ length: 16 }, (_, i) => ({ x: 10 * i, y: 50 }));
    const { mid, onCommit, onLimit } = setup({ waypoints: wps, segments: [{ from: SRC, to: TGT }] });
    down(mid(0), 5, 25);
    move(mid(0), 30, 60);
    up(mid(0), 30, 60);
    expect(onLimit).toHaveBeenCalledTimes(1);
    expect(onCommit).not.toHaveBeenCalled();
  });
  it("경유점 더블클릭은 삭제", () => {
    const { wp, onCommit, onAnnounce } = setup();
    fireEvent.doubleClick(wp(0));
    expect(onCommit).toHaveBeenCalledWith([]);
    expect(onAnnounce).toHaveBeenCalledWith("경유점 1 삭제, 남은 경유점 0개");
  });
  it("드래그 중 좌표 칩 x/y를 보인다", () => {
    const { wp, container } = setup();
    down(wp(0), 100, 80);
    move(wp(0), 150, 100);
    expect(container.querySelector(".ac-ge-coord-chip")?.textContent).toBe("x 152 · y 104");
    up(wp(0), 150, 100);
    expect(container.querySelector(".ac-ge-coord-chip")).toBeNull();
  });
});

describe("EdgeWaypointLayer: 키보드(§6.1)", () => {
  it("화살표 8px, Shift 32px, Alt 1px 이동과 라이브 알림", () => {
    const { wp, onCommit, onAnnounce } = setup({ keyboardMode: true });
    fireEvent.keyDown(wp(0), { key: "ArrowRight" });
    expect(onCommit).toHaveBeenLastCalledWith([{ x: 108, y: 80 }]);
    fireEvent.keyDown(wp(0), { key: "ArrowUp", shiftKey: true });
    expect(onCommit).toHaveBeenLastCalledWith([{ x: 100, y: 48 }]);
    fireEvent.keyDown(wp(0), { key: "ArrowLeft", altKey: true });
    expect(onCommit).toHaveBeenLastCalledWith([{ x: 99, y: 80 }]);
    expect(onCommit).toHaveBeenCalledTimes(3);
    expect(onAnnounce).toHaveBeenCalledWith("경유점 1 이동, x 99 y 80");
  });
  it("Delete로 삭제하고 알린다. 이벤트는 위로 번지지 않아 연결 삭제로 이어지지 않는다", () => {
    const outer = vi.fn();
    const { wp, onCommit, onAnnounce } = setup({ keyboardMode: true }, outer);
    fireEvent.keyDown(wp(0), { key: "Delete" });
    expect(onCommit).toHaveBeenCalledWith([]);
    expect(onAnnounce).toHaveBeenCalledWith("경유점 1 삭제, 남은 경유점 0개");
    expect(outer).not.toHaveBeenCalled();
  });
  it("중점에서 Enter/Space/W로 경유점 추가(격자 스냅), 상한이면 onLimit", () => {
    const a = setup({ keyboardMode: true, waypoints: [], segments: [{ from: SRC, to: { x: 203, y: 0 } }] });
    fireEvent.keyDown(a.mid(0), { key: "Enter" });
    expect(a.onCommit).toHaveBeenLastCalledWith([{ x: 104, y: 0 }]);
    fireEvent.keyDown(a.mid(0), { key: "w" });
    fireEvent.keyDown(a.mid(0), { key: " " });
    expect(a.onCommit).toHaveBeenCalledTimes(3);
    cleanup();
    const full = Array.from({ length: 16 }, (_, i) => ({ x: i * 8, y: 40 }));
    const b = setup({ keyboardMode: true, waypoints: full });
    fireEvent.keyDown(b.mid(0), { key: "Enter" });
    expect(b.onLimit).toHaveBeenCalledTimes(1);
    expect(b.onCommit).not.toHaveBeenCalled();
  });
  it("Esc는 경로 편집 모드 종료를 요청한다", () => {
    const { wp, mid, onExit } = setup({ keyboardMode: true });
    fireEvent.keyDown(wp(0), { key: "Escape" });
    fireEvent.keyDown(mid(0), { key: "Escape" });
    expect(onExit).toHaveBeenCalledTimes(2);
  });
});

describe("EdgeWaypointLayer: 키보드로 경유점을 추가하면 포커스가 새 경유점으로 간다(3R.24 QA)", () => {
  it("중점에서 Enter -> 새 경유점이 생기고 그 경유점이 포커스를 받는다", () => {
    const view = setup({ keyboardMode: true, waypoints: [] , segments: [{ from: SRC, to: TGT }] });
    const mid = view.mid(0);
    mid.focus();
    fireEvent.keyDown(mid, { key: "Enter" });
    expect(view.onCommit).toHaveBeenCalledTimes(1);
    const next = view.onCommit.mock.calls[0]![0] as Array<{ x: number; y: number }>;
    expect(next).toHaveLength(1);
    // 부모가 새 경유점을 내려 주면 포커스는 그 경유점으로 간다
    view.rerender(
      <EdgeWaypointLayer
        source={SRC}
        target={TGT}
        waypoints={next}
        segments={[{ from: SRC, to: next[0]! }, { from: next[0]!, to: TGT }]}
        zoom={1}
        screenToFlow={(p) => p}
        snapGrid={8}
        keyboardMode
        messages={defaultMessages}
        onDraft={view.onDraft}
        onCommit={view.onCommit}
        onLimit={view.onLimit}
        onAnnounce={view.onAnnounce}
        onExit={view.onExit}
        onZoomHint={view.onZoomHint}
      />,
    );
    expect(document.activeElement).toBe(view.wp(0));
  });
});
