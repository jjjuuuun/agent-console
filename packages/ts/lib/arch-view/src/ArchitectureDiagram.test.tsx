import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import type { ArchitectureView } from "@agent-console/contracts/architecture";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArchitectureDiagram } from "./index";
import type { ArchitectureDiagramProps, ArchSelection } from "./index";
import { defaultProfileView, notCollected, sampleCell, sampleEdge } from "./testing";

afterEach(cleanup);

const SIZE = { width: 1200, height: 700 };
function renderDiagram(v: ArchitectureView | null, props: Partial<ArchitectureDiagramProps> = {}) {
  return render(<ArchitectureDiagram view={v} containerSize={SIZE} {...props} />);
}
const cell = (c: HTMLElement, id: string) => c.querySelector<HTMLElement>(`button.ac-arch-cell[data-cell-id="${id}"]`)!;
const chip = (c: HTMLElement, id: string) => c.querySelector<HTMLElement>(`button.ac-arch-chip[data-edge-id="${id}"]`)!;
const nodeWrap = (c: HTMLElement, id: string) => c.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;

/** 임의의 가짜 뷰: 칸·연결·영역의 id, 라벨, tone, style을 모두 바꿨다. */
function fakeView(): ArchitectureView {
  return {
    profile: "zz",
    title: "가짜",
    canvas: { width: 800, height: 400 },
    zones: [{ id: "q", label: "구역Q", x: 0, y: 0, w: 800, h: 400, style: "my-zone" }],
    cells: [
      sampleCell("k1", { label: "첫째", x: 100, y: 100, tone: "no-such-tone", metrics: { count: { status: "observed", value: 0 } } }),
      sampleCell("k2", { label: "둘째", x: 500, y: 100, tone: "blue" }),
    ],
    edges: [sampleEdge("w1", "k1", "k2", { style: "no-such-style", label: "잇기", points: [[196, 100], [404, 100]], label_at: [300, 100] })],
    event_total: 0,
  };
}

describe("그리기가 데이터에서만 나온다 (수용 §13-1)", () => {
  it("칸·연결·영역 id/라벨/tone/style을 모두 바꾼 뷰도 같은 수가 그려지고 모르는 값은 중립 모양", () => {
    const { container } = renderDiagram(fakeView());
    expect(container.querySelectorAll("button.ac-arch-cell")).toHaveLength(2);
    expect(container.querySelectorAll(".ac-arch-chip")).toHaveLength(1);
    expect(container.querySelectorAll("path.ac-arch-edge-line")).toHaveLength(1);
    expect(cell(container, "k1").style.getPropertyValue("--cell-tone")).toBe("var(--ac-cat-neutral)");
    expect(cell(container, "k2").style.getPropertyValue("--cell-tone")).toBe("var(--ac-cat-1)");
    const line = container.querySelector<SVGPathElement>("path.ac-arch-edge-line")!;
    expect(line.style.strokeDasharray).toBe("var(--ac-edge-pattern-1)");
    expect(container.querySelector(".ac-arch-zone")!.getAttribute("data-zone-style")).toBe("my-zone");
  });
  it("칸이 0개인 뷰도 예외 없이 그린다", () => {
    expect(() => renderDiagram({ profile: "p", event_total: 0, cells: [], edges: [] })).not.toThrow();
  });
  it("view가 없으면 불러오는 중", () => {
    renderDiagram(null);
    expect(screen.getByRole("status").getAttribute("aria-busy")).toBe("true");
  });
  it("임의 색(데이터·prop)은 받지 않는다", () => {
    const v = fakeView();
    (v.cells![0] as { tone: string }).tone = "#ff0000";
    const { container } = renderDiagram(v, { tones: { "#ff0000": "red", blue: "#00f" } });
    expect(cell(container, "k1").getAttribute("style")).not.toMatch(/#|red/);
    expect(cell(container, "k2").style.getPropertyValue("--cell-tone")).toBe("var(--ac-cat-neutral)");
  });
});

describe("좌표와 레이어 (수용 §13-2·3)", () => {
  const v = defaultProfileView();
  it("칸은 중심 좌표 → 왼쪽 위, 영역은 왼쪽 위 그대로", () => {
    const { container } = renderDiagram(v);
    expect(nodeWrap(container, "cell:input").style.transform).toBe("translate(40px,96px)");
    expect(nodeWrap(container, "cell:llm").style.transform).toBe("translate(1310px,246px)");
    expect(nodeWrap(container, "zone:remote").style.transform).toBe("translate(1290px,16px)");
    expect(cell(container, "input").closest<HTMLElement>(".react-flow__node")!.style.width).toBe("180px");
  });
  it("기본 프로필: 칸 16·연결 21·영역 3이 모두 그려지고 points는 6px을 더하지 않은 채 그대로", () => {
    const { container } = renderDiagram(v);
    expect(container.querySelectorAll("button.ac-arch-cell")).toHaveLength(16);
    expect(container.querySelectorAll(".ac-arch-zone")).toHaveLength(3);
    expect(container.querySelectorAll("path.ac-arch-edge-line")).toHaveLength(21);
    expect(container.querySelectorAll("button.ac-arch-chip")).toHaveLength(21);
    const tool = container.querySelector('g[data-edge-id="tool_call"] path.ac-arch-edge-line')!;
    expect(tool.getAttribute("d")).toBe("M1110 620 L1110 655 L440 655 L440 620");
    const c = chip(container, "tool_call");
    expect(c.style.left).toBe("775px");
    expect(c.style.top).toBe("655px");
  });
  it("points가 없는 연결은 두 칸 경계 사이 직선(6px 바깥)", () => {
    const v2 = fakeView();
    delete (v2.edges![0] as { points?: unknown }).points;
    delete (v2.edges![0] as { label_at?: unknown }).label_at;
    const { container } = renderDiagram(v2);
    // k1: x 10~190, k2: x 410~590 (y=100) -> 196 ~ 404
    expect(container.querySelector('g[data-edge-id="w1"] path.ac-arch-edge-line')!.getAttribute("d")).toBe("M196 100 L404 100");
    expect(chip(container, "w1").style.left).toBe("300px");
  });
  it("좌표 없는 칸은 gridLayout 순서대로 겹치지 않게 놓인다", () => {
    const v2 = { profile: "p", event_total: 0, cells: ["a", "b", "c"].map((i) => sampleCell(i)), edges: [] } as ArchitectureView;
    const { container } = renderDiagram(v2);
    const pos = ["a", "b", "c"].map((i) => nodeWrap(container, `cell:${i}`).style.transform);
    expect(new Set(pos).size).toBe(3);
  });
  it("레이어 순서: 영역 < 칸 < 연결 선 < 칩 (DOM 순서와 z-index)", () => {
    const { container } = renderDiagram(v);
    const all = Array.from(container.querySelectorAll("*"));
    const idx = (el: Element) => all.indexOf(el);
    const lastZone = Array.from(container.querySelectorAll(".ac-arch-zone")).pop()!;
    const firstCell = container.querySelector("button.ac-arch-cell")!;
    const svg = container.querySelector("svg.ac-arch-edges")!;
    const firstChip = container.querySelector(".ac-arch-chip")!;
    expect(idx(lastZone)).toBeLessThan(idx(firstCell));
    expect(idx(firstCell)).toBeLessThan(idx(svg));
    expect(idx(svg)).toBeLessThan(idx(firstChip));
    expect(container.querySelector<HTMLElement>(".ac-arch-layer")).not.toBeNull();
  });
  it("화살촉 marker 채움은 선 색과 같다", () => {
    const { container } = renderDiagram(v);
    const line = container.querySelector<SVGPathElement>('g[data-edge-id="task_submit"] path.ac-arch-edge-line')!;
    const id = /url\(#(.+)\)/.exec(line.getAttribute("marker-end")!)![1]!;
    const markerPath = container.querySelector<SVGPathElement>(`marker[id="${id}"] path`)!;
    expect(line.style.stroke).toBe("var(--ac-cat-7)");
    expect(markerPath.style.fill).toBe("var(--ac-cat-7)");
    expect(container.querySelector(`marker[id="${id}"]`)!.getAttribute("markerUnits")).toBe("userSpaceOnUse");
  });
});

describe("지표 세 상태 (수용 §13-4)", () => {
  it("관측 0은 '0회', 수집 안 됨은 '–'/'수집 안 됨'이며 0이 아니다", () => {
    const v = fakeView();
    v.cells = [
      sampleCell("a", { x: 100, y: 100, metrics: { count: { status: "observed", value: 0 }, tokens: notCollected() } }),
      sampleCell("b", { x: 400, y: 100, status: "not_collected", metrics: { count: notCollected() } }),
    ];
    const { container } = renderDiagram(v);
    const a = cell(container, "a");
    expect(a.textContent).toContain("0회");
    expect(a.querySelector('[data-status="not_collected"]')!.textContent).toBe("–");
    expect(a.getAttribute("aria-label")).toBe("a, 0회, 토큰 수집 안 됨");
    const b = cell(container, "b");
    expect(b.getAttribute("data-status")).toBe("not_collected");
    expect(b.textContent).toContain("수집 안 됨");
    expect(b.textContent).not.toMatch(/0회/);
    expect(b.getAttribute("aria-label")).toBe("b, 수집 안 됨");
  });
  it("추정은 '추정' 글자 + 점선 밑줄 표식", () => {
    const { container } = renderDiagram(defaultProfileView());
    const piece = cell(container, "llm").querySelector('.ac-arch-metric[data-inferred]')!;
    expect(piece.textContent).toContain("추정");
    expect(cell(container, "llm").getAttribute("aria-label")).toBe("LLM, 12회, 오류 0, 토큰 41.2k, 소요 1.2초 추정");
  });
  it("접근 이름 문법: 이름, 지표 조각, 상태 조각(부분 사유·강조)", () => {
    const { container } = renderDiagram(defaultProfileView(), { highlight: { profile: "p", cells: ["rules"] } });
    expect(cell(container, "rules").getAttribute("aria-label")).toBe("Rules, 12회, 부분: 도구로 연 문서만 보임(자동 로드는 기록 없음), 선택한 이벤트가 지나감");
    expect(cell(container, "hook").getAttribute("aria-label")).toBe("Hook, 수집 안 됨");
  });
});

describe("칸 상태 (수용 §13-5)", () => {
  it("부분 배지(글자 + 툴팁 이유), 오류 막대 + '오류 n' + 아이콘, 선택(aria-pressed), 강조(이벤트 배지)", () => {
    const v = defaultProfileView();
    (v.cells!.find((c) => c.id === "sdk")!.metrics as Record<string, unknown>).errors = { status: "observed", value: 2 };
    const { container } = renderDiagram(v, { selection: { kind: "cell", id: "sdk" }, highlight: { profile: "p", cells: ["input"] } });
    const rules = cell(container, "rules");
    const badge = rules.querySelector('.ac-arch-badge[data-kind="partial"]')!;
    expect(badge.textContent).toBe("부분");
    expect(badge.getAttribute("title")).toContain("도구로 연 문서만");
    const sdk = cell(container, "sdk");
    expect(sdk.hasAttribute("data-errors")).toBe(true);
    expect(sdk.textContent).toContain("오류 2");
    expect(sdk.querySelector('.ac-arch-icon[data-icon="failed"]')).not.toBeNull();
    expect(sdk.getAttribute("aria-pressed")).toBe("true");
    expect(cell(container, "api").getAttribute("aria-pressed")).toBe("false");
    const input = cell(container, "input");
    expect(input.hasAttribute("data-highlighted")).toBe(true);
    expect(input.querySelector('.ac-arch-badge[data-kind="event"]')!.textContent).toBe("이벤트");
  });
  it("highlight를 비우면 강조가 사라진다", () => {
    const v = defaultProfileView();
    const { container, rerender } = renderDiagram(v, { highlight: { profile: "p", cells: ["input"], edges: ["task_submit"] } });
    expect(container.querySelectorAll("[data-highlighted]").length).toBeGreaterThan(0);
    rerender(<ArchitectureDiagram view={v} containerSize={SIZE} highlight={null} />);
    expect(container.querySelectorAll("[data-highlighted]")).toHaveLength(0);
  });
  it("묶음 강조도 칸을 강조한다", () => {
    const { container } = renderDiagram(defaultProfileView(), { highlight: { profile: "p", groups: [{ cell: "mcp", key: "서버A" }] } });
    expect(cell(container, "mcp").hasAttribute("data-highlighted")).toBe(true);
  });
  it("layout 모드는 지표·상태 표기를 숨기고 배치만 그린다", () => {
    const { container } = renderDiagram(defaultProfileView(), { mode: "layout" });
    const c = cell(container, "hook");
    expect(c.textContent).not.toContain("수집 안 됨");
    expect(c.getAttribute("data-status")).toBe("observed");
    expect(container.querySelector(".ac-arch-info")).toBeNull();
    expect(container.querySelector(".ac-arch-note")!.textContent).toContain("배치 미리보기");
  });
  it("cellRenderers: 칸의 view 키로 안쪽을 바꾸고 모르는 키는 기본 모양", () => {
    const v = fakeView();
    (v.cells![0] as { view: string }).view = "mine";
    (v.cells![1] as { view: string }).view = "unknown-view";
    const { container } = renderDiagram(v, { cellRenderers: { mine: ({ cell: c, defaultBody }) => <><em data-testid="custom">{c.label}!</em>{defaultBody}</> } });
    expect(within(cell(container, "k1")).getByTestId("custom").textContent).toBe("첫째!");
    expect(cell(container, "k2").querySelector("em")).toBeNull();
    expect(cell(container, "k2").textContent).toContain("둘째");
  });
  it("edgeStyles: 이름을 더하면 그 모양, 임의 색은 중립", () => {
    const v = fakeView();
    (v.edges![0] as { style: string }).style = "mine";
    const { container } = renderDiagram(v, { edgeStyles: { mine: { stroke: "--ac-cat-3", dash: "--ac-edge-pattern-3" } } });
    const line = container.querySelector<SVGPathElement>("path.ac-arch-edge-line")!;
    expect(line.style.stroke).toBe("var(--ac-cat-3)");
    expect(line.style.strokeDasharray).toBe("var(--ac-edge-pattern-3)");
  });
});

describe("연결 상태 (수용 §13-6)", () => {
  const v = defaultProfileView();
  it("구조 연결: 점선, 칩에 횟수 없음, 접근 이름에 '구조 연결'", () => {
    const { container } = renderDiagram(v);
    const line = container.querySelector<SVGPathElement>('g[data-edge-id="model_request"] path.ac-arch-edge-line')!;
    expect(line.style.strokeDasharray).toBe("var(--ac-edge-pattern-1)");
    const c = chip(container, "next_context");
    expect(c.querySelector(".ac-arch-chip-count")).toBeNull();
    expect(c.getAttribute("aria-label")).toBe("다음 요청에 반영, Tool result에서 Context builder로, 구조 연결");
  });
  it("관측 연결: 칩 = 라벨 + 굵은 횟수, 접근 이름", () => {
    const { container } = renderDiagram(v);
    const c = chip(container, "task_submit");
    expect(c.querySelector(".ac-arch-chip-label")!.textContent).toBe("과제 전달");
    expect(c.querySelector(".ac-arch-chip-count")!.textContent).toBe("12");
    expect(c.getAttribute("aria-label")).toBe("과제 전달, Task input에서 SDK / CLI로, 12회");
  });
  it("오류 연결은 danger 선·칩에 아이콘, 수집 안 됨 연결은 점 모양 + '–'", () => {
    const w = defaultProfileView();
    const e = w.edges!;
    e.find((x) => x.id === "tool_call")!.metrics = { count: { status: "observed", value: 20 }, errors: { status: "observed", value: 3 } };
    const dead = e.find((x) => x.id === "mcp_call")!;
    dead.status = "not_collected";
    dead.metrics = { count: notCollected() };
    const { container } = renderDiagram(w);
    expect(container.querySelector<SVGPathElement>('g[data-edge-id="tool_call"] path.ac-arch-edge-line')!.style.stroke).toBe("var(--ac-danger)");
    expect(chip(container, "tool_call").querySelector('.ac-arch-icon[data-icon="failed"]')).not.toBeNull();
    expect(chip(container, "tool_call").getAttribute("data-state")).toBe("error");
    const line = container.querySelector<SVGPathElement>('g[data-edge-id="mcp_call"] path.ac-arch-edge-line')!;
    expect(line.style.stroke).toBe("var(--ac-edge-dead)");
    expect(line.style.strokeDasharray).toBe("var(--ac-edge-pattern-2)");
    expect(chip(container, "mcp_call").querySelector(".ac-arch-chip-count")!.textContent).toBe("–");
    expect(chip(container, "mcp_call").getAttribute("aria-label")).toBe("MCP 호출, Dispatcher에서 MCP 서버로, 수집 안 됨");
  });
  it("선택·강조 연결은 선 색이 바뀌고 화살촉 색도 같다", () => {
    const { container } = renderDiagram(v, { selection: { kind: "edge", id: "task_submit" }, highlight: { profile: "p", edges: ["work_result"] } });
    const sel = container.querySelector<SVGPathElement>('g[data-edge-id="task_submit"] path.ac-arch-edge-line')!;
    expect(sel.style.stroke).toBe("var(--ac-edge-selected)");
    expect(chip(container, "task_submit").getAttribute("aria-pressed")).toBe("true");
    const hi = container.querySelector<SVGPathElement>('g[data-edge-id="work_result"] path.ac-arch-edge-line')!;
    expect(hi.style.stroke).toBe("var(--ac-edge-active)");
    expect(chip(container, "work_result").querySelector(".ac-arch-chip-dot")).not.toBeNull();
    const id = /url\(#(.+)\)/.exec(hi.getAttribute("marker-end")!)![1]!;
    expect(container.querySelector<SVGPathElement>(`marker[id="${id}"] path`)!.style.fill).toBe("var(--ac-edge-active)");
  });
  it("칩이 좁은 선분에서는 최대 폭이 label_max_w·선분 길이로 제한되고 라벨이 말줄임 대상", () => {
    const { container } = renderDiagram(v);
    expect(chip(container, "delegate").style.maxWidth).toBe("92px");
    expect(chip(container, "task_submit").style.maxWidth).toBe("120px");
  });
});

describe("요약 표시 (수용 §13-8)", () => {
  const v = defaultProfileView();
  it("배율 0.6 이상은 전체, 미만은 숫자만이며 이름·접근 이름·클릭은 같다", () => {
    const onSelect = vi.fn();
    const { container, rerender } = renderDiagram(v, { scale: 0.6, fitMode: "none", onSelect });
    expect(container.querySelector(".ac-arch-root")!.getAttribute("data-level")).toBe("full");
    const full = cell(container, "llm").getAttribute("aria-label");
    expect(cell(container, "llm").querySelector(".ac-arch-cell-name")).not.toBeNull();
    rerender(<ArchitectureDiagram view={v} containerSize={SIZE} scale={0.59} fitMode="none" onSelect={onSelect} />);
    expect(container.querySelector(".ac-arch-root")!.getAttribute("data-level")).toBe("summary");
    const llm = cell(container, "llm");
    expect(llm.getAttribute("data-level")).toBe("summary");
    expect(llm.querySelector(".ac-arch-cell-name")).toBeNull();
    expect(llm.querySelector(".ac-arch-cell-sum")!.textContent).toBe("12");
    expect(llm.getAttribute("aria-label")).toBe(full);
    expect(cell(container, "hook").querySelector(".ac-arch-cell-sum")!.textContent).toBe("–");
    // 연결 칩은 글자 없이 점이 되지만 접근 이름과 클릭은 같다.
    const c = chip(container, "task_submit");
    expect(c.textContent).toBe("");
    expect(c.getAttribute("aria-label")).toContain("과제 전달");
    fireEvent.click(llm);
    expect(onSelect).toHaveBeenCalledWith({ kind: "cell", id: "llm" });
    fireEvent.click(c);
    expect(onSelect).toHaveBeenLastCalledWith({ kind: "edge", id: "task_submit" });
  });
  it("요약 표시의 숫자 크기는 배율의 역수(--arch-inv)로 상쇄한다", () => {
    const { container } = renderDiagram(v, { scale: 0.4, fitMode: "none" });
    expect(parseFloat((container.querySelector(".ac-arch-root") as HTMLElement).style.getPropertyValue("--arch-inv"))).toBeCloseTo(2.5);
  });
  it("fullScaleMin을 바꿀 수 있다", () => {
    const { container } = renderDiagram(v, { scale: 0.7, fitMode: "none", fullScaleMin: 0.8 });
    expect(container.querySelector(".ac-arch-root")!.getAttribute("data-level")).toBe("summary");
  });
});

describe("칸 설명 툴팁 (§2.1·§9.3)", () => {
  it("설명이 칸 줄에서 잘려도 title에 칸 이름과 전체 설명이 들어 있다", () => {
    const long = "아주 긴 설명이 한 줄에 다 들어가지 않아서 말줄임으로 잘리는 칸의 전체 설명입니다";
    const { container } = renderDiagram({ profile: "p", event_total: 0, cells: [sampleCell("t1", { label: "임의 칸", description: long, x: 100, y: 100 })], edges: [] });
    expect(cell(container, "t1").getAttribute("title")).toBe(`임의 칸 — ${long}`);
  });
});

describe("맞춤·배율 (수용 §13-9)", () => {
  const v = defaultProfileView();
  it("폭 맞춤은 하한 0.6, 전체 맞춤은 하한 없음, 확대하면 none이 된다", () => {
    const onFit = vi.fn();
    const onScale = vi.fn();
    const { container } = renderDiagram(v, { containerSize: { width: 756, height: 400 }, onFitModeChange: onFit, onScaleChange: onScale });
    expect(container.querySelector<HTMLElement>(".react-flow__viewport")!.style.transform).toContain("scale(0.6)");
    fireEvent.click(screen.getByRole("button", { name: "확대" }));
    expect(onFit).toHaveBeenCalledWith("none");
    expect(onScale).toHaveBeenCalledTimes(1);
    expect(onScale.mock.calls[0]![0]).toBeCloseTo(0.75);
    expect(container.querySelector<HTMLElement>(".react-flow__viewport")!.style.transform).toContain("scale(0.75)");
  });
  it("전체 맞춤(contain)은 작은 칸에서도 요약 표시로 내려간다", () => {
    const { container } = renderDiagram(v, { containerSize: { width: 420, height: 240 }, defaultFitMode: "contain" });
    expect(container.querySelector(".ac-arch-root")!.getAttribute("data-level")).toBe("summary");
  });
  it("자동 맞춤: 높이가 들어가면 폭 맞춤, 모자라도 0.55 이상이면 전체 맞춤, 미만이면 폭 맞춤 + 잘림 표시", () => {
    const canvasOf = (c: HTMLElement) => c.querySelector<HTMLElement>("[data-arch-canvas]")!;
    const a = renderDiagram(v, { containerSize: { width: 1200, height: 700 } });
    expect(canvasOf(a.container).dataset.fitResolved).toBe("width");
    expect(canvasOf(a.container).dataset.clipped).toBeUndefined();
    a.unmount();
    const b = renderDiagram(v, { containerSize: { width: 1172, height: 500 } });
    expect(canvasOf(b.container).dataset.fitResolved).toBe("contain");
    expect(canvasOf(b.container).dataset.clipped).toBeUndefined();
    expect(screen.queryByRole("button", { name: /아래 칸/ })).toBeNull();
    b.unmount();
    const c = renderDiagram(v, { containerSize: { width: 1172, height: 256 } });
    expect(canvasOf(c.container).dataset.fitResolved).toBe("width");
    expect(canvasOf(c.container).dataset.clipped).toBe("");
    const more = screen.getByRole("button", { name: /아래 칸 \d+개/ });
    const before = c.container.querySelector<HTMLElement>(".react-flow__viewport")!.style.transform;
    fireEvent.click(more);
    expect(c.container.querySelector<HTMLElement>(".react-flow__viewport")!.style.transform).not.toBe(before);
    expect(c.container.querySelector(".ac-arch-scrollbar")).not.toBeNull();
  });
  it("자동 맞춤 기준(autoContainMin)을 바꿀 수 있다", () => {
    const { container } = renderDiagram(v, { containerSize: { width: 1172, height: 256 }, autoContainMin: 0.2 });
    expect(container.querySelector<HTMLElement>("[data-arch-canvas]")!.dataset.fitResolved).toBe("contain");
  });
  it("[맞춤] 메뉴의 100%는 배율을 1로", () => {
    const onScale = vi.fn();
    renderDiagram(v, { onScaleChange: onScale });
    fireEvent.change(screen.getByRole("combobox", { name: "맞춤" }), { target: { value: "100" } });
    expect(onScale).toHaveBeenCalledWith(1);
    expect(screen.getByRole("button", { name: "100%로 되돌리기" }).textContent).toBe("100%");
  });
});

function Harness({ initial = null, ...props }: { initial?: ArchSelection | null } & Partial<ArchitectureDiagramProps>) {
  const [sel, setSel] = useState<ArchSelection | null>(initial);
  return <ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} selection={sel} onSelect={setSel} {...props} />;
}

describe("선택·키보드 (수용 §13-11·24)", () => {
  it("칸·연결을 누르면 선택, 같은 대상을 다시 누르면 해제(onSelect null)", () => {
    const onSelect = vi.fn();
    const { container } = render(<Harness onSelect={onSelect} />);
    fireEvent.click(cell(container, "llm"));
    expect(onSelect).toHaveBeenLastCalledWith({ kind: "cell", id: "llm" });
  });
  it("제어 선택: 같은 대상을 다시 누르면 null", () => {
    const calls: Array<ArchSelection | null> = [];
    function Inner() {
      const [sel, setSel] = useState<ArchSelection | null>(null);
      return <ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} selection={sel} onSelect={(s) => { calls.push(s); setSel(s); }} />;
    }
    const { container } = render(<Inner />);
    fireEvent.click(chip(container, "tool_call"));
    expect(cell(container, "llm").getAttribute("aria-pressed")).toBe("false");
    expect(chip(container, "tool_call").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(chip(container, "tool_call"));
    expect(calls).toEqual([{ kind: "edge", id: "tool_call" }, null]);
    fireEvent.click(cell(container, "llm"));
    fireEvent.click(cell(container, "input"));
    expect(calls.at(-1)).toEqual({ kind: "cell", id: "input" });
  });
  it("수집 안 됨 칸·구조 연결·횟수가 추정인 칸은 선택하지 않고 onBlocked만 부른다", () => {
    const onSelect = vi.fn();
    const onBlocked = vi.fn();
    const w = defaultProfileView();
    w.cells!.find((c) => c.id === "response")!.metrics = { count: { status: "inferred", value: 3 } };
    const { container } = render(<ArchitectureDiagram view={w} containerSize={SIZE} onSelect={onSelect} onBlocked={onBlocked} />);
    fireEvent.click(cell(container, "hook"));
    expect(onBlocked).toHaveBeenLastCalledWith({ kind: "cell", id: "hook" }, "not_collected");
    fireEvent.click(chip(container, "model_request"));
    expect(onBlocked).toHaveBeenLastCalledWith({ kind: "edge", id: "model_request" }, "structural");
    fireEvent.click(cell(container, "response"));
    expect(onBlocked).toHaveBeenLastCalledWith({ kind: "cell", id: "response" }, "not_collected");
    expect(onSelect).not.toHaveBeenCalled();
    // 선(투명 클릭 영역)도 같은 규칙
    fireEvent.click(container.querySelector('g[data-edge-id="task_submit"] path.ac-arch-edge-hit')!);
    expect(onSelect).toHaveBeenCalledWith({ kind: "edge", id: "task_submit" });
  });
  it("방향키는 가장 가까운 칸으로, 없으면 이동 없음. Home/End는 첫/마지막 칸", () => {
    const { container } = render(<Harness />);
    cell(container, "input").focus();
    fireEvent.keyDown(cell(container, "input"), { key: "ArrowRight" });
    expect(document.activeElement).toBe(cell(container, "sdk"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(cell(container, "instructions"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(cell(container, "sdk"));
    cell(container, "input").focus();
    fireEvent.keyDown(cell(container, "input"), { key: "ArrowLeft" });
    expect(document.activeElement).toBe(cell(container, "input"));
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement).toBe(cell(container, "response"));
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement).toBe(cell(container, "input"));
  });
  it("Tab 순서의 근거: 칸은 선언 순서, 연결 칩은 칸 뒤에 선언 순서로 DOM에 있다", () => {
    const { container } = render(<Harness />);
    const order = Array.from(container.querySelectorAll<HTMLElement>("button.ac-arch-cell, button.ac-arch-chip")).map((e) => e.dataset.cellId ?? e.dataset.edgeId);
    const v = defaultProfileView();
    expect(order).toEqual([...v.cells!.map((c) => c.id), ...v.edges!.map((e) => e.id)]);
  });
  it("Shift+Enter·더블클릭은 drill이 있는 칸에서만 onDrill", () => {
    const onDrill = vi.fn();
    const { container } = render(<Harness onDrill={onDrill} />);
    fireEvent.keyDown(cell(container, "subagents"), { key: "Enter", shiftKey: true });
    expect(onDrill).toHaveBeenLastCalledWith("subagents");
    fireEvent.keyDown(cell(container, "llm"), { key: "Enter", shiftKey: true });
    fireEvent.doubleClick(cell(container, "llm"));
    expect(onDrill).toHaveBeenCalledTimes(1);
    fireEvent.doubleClick(cell(container, "subagents"));
    expect(onDrill).toHaveBeenCalledTimes(2);
  });
  it("Esc는 선택을 해제하고, Backspace는 onBack", () => {
    const onBack = vi.fn();
    const { container } = render(<Harness initial={{ kind: "cell", id: "llm" }} onBack={onBack} />);
    expect(cell(container, "llm").getAttribute("aria-pressed")).toBe("true");
    fireEvent.keyDown(cell(container, "llm"), { key: "Escape" });
    expect(cell(container, "llm").getAttribute("aria-pressed")).toBe("false");
    fireEvent.keyDown(cell(container, "llm"), { key: "Backspace" });
    expect(onBack).toHaveBeenCalledTimes(1);
  });
  it("+/-는 배율을 바꾸고 0은 맞춤으로 돌아간다", () => {
    const onScale = vi.fn();
    const onFit = vi.fn();
    const { container } = render(<Harness onScaleChange={onScale} onFitModeChange={onFit} />);
    fireEvent.keyDown(cell(container, "input"), { key: "+" });
    expect(onFit).toHaveBeenLastCalledWith("none");
    expect(onScale.mock.calls[0]![0]).toBeGreaterThan(0.768);
    fireEvent.keyDown(cell(container, "input"), { key: "0" });
    expect(onFit).toHaveBeenLastCalledWith("auto");
  });
  it("건너뛰기 링크는 onSkip이 있을 때만", () => {
    const onSkip = vi.fn();
    const { rerender } = render(<Harness onSkip={onSkip} />);
    fireEvent.click(screen.getByRole("button", { name: "구조도를 건너뛰고 이벤트 표로 가기" }));
    expect(onSkip).toHaveBeenCalled();
    rerender(<Harness />);
    expect(screen.queryByRole("button", { name: /건너뛰고/ })).toBeNull();
  });
});

describe("선택 정보 줄", () => {
  it("선택이 없으면 안내 문구, 포커스하면 미리보기", () => {
    const { container } = render(<Harness />);
    expect(screen.getByRole("status").textContent).toContain("칸이나 연결을 누르면");
    act(() => cell(container, "llm").focus());
    expect(screen.getByRole("status").textContent).toContain("미리보기");
    expect(screen.getByRole("status").textContent).toContain("토큰 41,203");
    act(() => cell(container, "llm").blur());
    expect(screen.getByRole("status").textContent).not.toContain("미리보기");
  });
  it("선택한 칸의 묶음 칩·하위 구조도 단추·수집 불가 항목", () => {
    const w = defaultProfileView();
    const sub = w.cells!.find((c) => c.id === "subagents")!;
    sub.groups = [
      { key: "t1", label: "서브에이전트 A", metrics: { count: { status: "observed", value: 5 } }, selector: { arch: "p:cell:subagents", arch_group: "t1" }, drill: { filter: "thread", value: "t1" } },
      { key: null, metrics: { count: { status: "observed", value: 1 } }, selector: { arch: "p:cell:subagents", arch_group: "" } },
    ];
    sub.groups_rest = { groups: 3 };
    const onSelect = vi.fn();
    const onDrill = vi.fn();
    const { container } = render(<ArchitectureDiagram view={w} containerSize={SIZE} selection={{ kind: "cell", id: "subagents" }} onSelect={onSelect} onDrill={onDrill} />);
    const info = container.querySelector(".ac-arch-info")!;
    fireEvent.click(within(info as HTMLElement).getByRole("button", { name: /서브에이전트 A/ }));
    expect(onSelect).toHaveBeenLastCalledWith({ kind: "group", id: "subagents", group: "t1" });
    expect(within(info as HTMLElement).getByRole("button", { name: /\(이름 없음\)/ })).toBeTruthy();
    expect(info.textContent).toContain("그 밖 3");
    fireEvent.click(within(info as HTMLElement).getByRole("button", { name: "하위 구조도" }));
    expect(onDrill).toHaveBeenCalledWith("subagents");
    // LLM의 수집 불가 항목
    const { container: c2 } = render(<ArchitectureDiagram view={w} containerSize={SIZE} selection={{ kind: "cell", id: "llm" }} />);
    expect(c2.querySelector(".ac-arch-info-unavail")!.textContent).toContain("수집 안 됨: LLM 요청 본문 — 로그에 남지 않음");
  });
  it("연결을 풀어 쓴다: 라벨, 출발 → 도착, 종류", () => {
    const { container } = renderDiagram(defaultProfileView(), { selection: { kind: "edge", id: "control_request" } });
    const t = container.querySelector(".ac-arch-info")!.textContent!;
    expect(t).toContain("제어 요청");
    expect(t).toContain("SDK / CLI → 에이전트 제어");
    expect(t).toContain("관측");
  });
  it("소요 지표의 평균·최대·표본을 보인다", () => {
    const { container } = renderDiagram(defaultProfileView(), { selection: { kind: "cell", id: "tools" } });
    expect(container.querySelector(".ac-arch-info")!.textContent).toContain("평균 1.2s · 최대 2.1s · 표본 4개");
  });
});

describe("그림 | 목록 (수용 §13-10)", () => {
  it("목록 전환: 칸 행 수 = 칸 수, 연결 행 수 = 연결 수, 같은 선택 상태", () => {
    const onMode = vi.fn();
    const { container } = render(<Harness initial={{ kind: "cell", id: "llm" }} onViewModeChange={onMode} />);
    fireEvent.click(screen.getByRole("button", { name: "목록" }));
    expect(onMode).toHaveBeenCalledWith("list");
    const lists = container.querySelectorAll("ul.ac-arch-list-rows");
    expect(lists[0]!.querySelectorAll("button.ac-arch-row")).toHaveLength(16);
    expect(lists[1]!.querySelectorAll("button.ac-arch-row")).toHaveLength(21);
    expect(container.querySelector('button.ac-arch-row[data-cell-id="llm"]')!.getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector(".ac-arch-canvas")).toBeNull();
    expect(container.querySelector('button.ac-arch-row[data-cell-id="hook"]')!.textContent).toContain("수집 안 됨");
  });
  it("목록 행 클릭도 같은 콜백, 막힌 대상은 onBlocked", () => {
    const onSelect = vi.fn();
    const onBlocked = vi.fn();
    const { container } = renderDiagram(defaultProfileView(), { defaultViewMode: "list", onSelect, onBlocked });
    fireEvent.click(container.querySelector('button.ac-arch-row[data-cell-id="input"]')!);
    expect(onSelect).toHaveBeenCalledWith({ kind: "cell", id: "input" });
    fireEvent.click(container.querySelector('button.ac-arch-row[data-edge-id="rule_load"]')!);
    expect(onBlocked).toHaveBeenCalledWith({ kind: "edge", id: "rule_load" }, "structural");
  });
  it("분류 안 됨·수집 불가 항목 행이 목록 끝에 붙는다", () => {
    const w = { ...defaultProfileView(), unassigned: { metrics: { count: { status: "observed" as const, value: 12 } }, selector: { arch: "p:unassigned:" } } };
    const onSelect = vi.fn();
    renderDiagram(w, { defaultViewMode: "list", onSelect });
    fireEvent.click(screen.getByRole("button", { name: /분류 안 됨/ }));
    expect(onSelect).toHaveBeenCalledWith({ kind: "unassigned", id: "" });
    expect(screen.getByText(/LLM 요청 본문/)).toBeTruthy();
  });
});

describe("범례", () => {
  it("버튼으로 열고 Esc로 닫으면 포커스가 버튼으로 돌아간다", () => {
    const { container } = renderDiagram(defaultProfileView());
    const btn = screen.getByRole("button", { name: "범례" });
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    const items = container.querySelectorAll(".ac-arch-legend > li");
    expect(items.length).toBe(10);
    fireEvent.keyDown(items[0]!, { key: "Escape" });
    expect(container.querySelector(".ac-arch-legend")).toBeNull();
    expect(document.activeElement).toBe(btn);
  });
  it("새 연결 style 견본은 edgeLegend로 글자를 준다", () => {
    const { container } = renderDiagram(defaultProfileView(), { edgeStyles: { mine: { stroke: "--ac-cat-2" } }, edgeLegend: { mine: "내 연결" } });
    fireEvent.click(screen.getByRole("button", { name: "범례" }));
    expect(container.querySelector('[data-legend="edge:mine"]')!.textContent).toBe("내 연결");
  });
});

describe("도구줄 구성", () => {
  it("toolbar=false면 도구줄이 없고, 부분 끄기·앱 컨트롤 덧붙이기", () => {
    const { container, rerender } = renderDiagram(defaultProfileView(), { toolbar: false });
    expect(container.querySelector(".ac-arch-toolbar")).toBeNull();
    rerender(<ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} toolbar={{ zoom: false, legend: false }} toolbarExtra={<button type="button">크게 보기</button>} />);
    expect(screen.queryByRole("button", { name: "확대" })).toBeNull();
    expect(screen.queryByRole("button", { name: "범례" })).toBeNull();
    expect(screen.getByRole("button", { name: "크게 보기" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "목록" })).toBeTruthy();
  });
  it("문구는 messages로 바꾼다", () => {
    renderDiagram(defaultProfileView(), { messages: { zoomIn: "Zoom in", metricCount: "{n}x" } });
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeTruthy();
  });

  it("toolbarLead는 도구줄 맨 앞, afterToolbar는 도구줄과 그림 사이에 놓인다", () => {
    const { container } = renderDiagram(defaultProfileView(), { toolbarLead: <span data-testid="lead">앞</span>, afterToolbar: <p data-testid="after">상태</p>, toolbarExtra: <span data-testid="extra">뒤</span> });
    const toolbar = container.querySelector(".ac-arch-toolbar")!;
    expect(toolbar.firstElementChild).toBe(screen.getByTestId("lead"));
    expect(toolbar.contains(screen.getByTestId("extra"))).toBe(true);
    const after = screen.getByTestId("after");
    expect(toolbar.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(after.compareDocumentPosition(container.querySelector(".ac-arch-canvas")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
