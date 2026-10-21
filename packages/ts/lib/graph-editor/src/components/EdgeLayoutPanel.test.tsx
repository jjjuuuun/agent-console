import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EdgeLayout } from "@agent-console/contracts";
import { defaultMessages } from "../messages";
import { BUILTIN_EDGE_SHAPES } from "../shapes/registry";
import type { EdgeShapeDescriptor } from "../shapes/types";
import { EdgeLayoutPanel } from "./EdgeLayoutPanel";
import type { EdgeLayoutPanelProps } from "./EdgeLayoutPanel";

afterEach(cleanup);

const shape = (id: string) => BUILTIN_EDGE_SHAPES.find((s) => s.id === id) as EdgeShapeDescriptor;

function setup(layout: EdgeLayout | null, over: Partial<EdgeLayoutPanelProps> = {}) {
  const onChange = vi.fn();
  const r = render(<EdgeLayoutPanel layout={layout} shapes={BUILTIN_EDGE_SHAPES} inheritedShape={shape("smoothstep")} onChange={onChange} {...over} />);
  return { onChange, ...r };
}

describe("EdgeLayoutPanel", () => {
  it("모양이 상속이면 '상속 (현재: 이름)' 행이 선택돼 있고 입력은 상속 배지를 단다", () => {
    setup(null);
    const select = screen.getByLabelText("모양") as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(within(select).getByRole("option", { name: "상속 (현재: 직각(둥근 모서리))" })).toBeTruthy();
    // 모양 목록은 레지스트리에서: 내장 5종이 모두 나온다
    expect(within(select).getAllByRole("option")).toHaveLength(1 + BUILTIN_EDGE_SHAPES.length);
    // 상속 모양 smoothstep: 둥글기·꺾임·경유점 보임, 상속 배지
    expect((screen.getByLabelText("모서리 둥글기(px)") as HTMLInputElement).placeholder).toBe("8");
    expect(screen.getAllByText("상속").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("경유점 0/16")).toBeTruthy();
  });

  it("모양을 고르면 shape만 담은 layout을, 상속을 고르면 layout 전체 삭제(null)를 내보낸다", () => {
    const { onChange } = setup(null);
    fireEvent.change(screen.getByLabelText("모양"), { target: { value: "straight" } });
    expect(onChange).toHaveBeenLastCalledWith({ shape: "straight" });
    cleanup();
    const second = setup({ shape: "straight" });
    fireEvent.change(screen.getByLabelText("모양"), { target: { value: "" } });
    expect(second.onChange).toHaveBeenLastCalledWith(null);
  });

  it("supportsX=false인 항목은 숨긴다(비활성이 아니라 숨김)", () => {
    setup({ shape: "straight" });
    expect(screen.queryByLabelText("모서리 둥글기(px)")).toBeNull();
    expect(screen.queryByLabelText("꺾임 위치(%)")).toBeNull();
    expect(screen.getByText("경유점 0/16")).toBeTruthy();
  });

  it("경유점이 있으면 꺾임 위치는 숨기고, 경유점을 안 쓰는 모양이면 보존 안내를 보인다", () => {
    setup({ shape: "smoothstep", waypoints: [{ x: 1, y: 2 }] });
    expect(screen.queryByLabelText("꺾임 위치(%)")).toBeNull();
    cleanup();
    const custom: EdgeShapeDescriptor = { ...shape("straight"), id: "plain", title: "민자", supportsWaypoints: false };
    setup({ shape: "plain", waypoints: [{ x: 1, y: 2 }, { x: 3, y: 4 }] }, { shapes: [custom] });
    expect(screen.getByText("이 모양은 경유점을 쓰지 않습니다(저장된 2개 보존)")).toBeTruthy();
    expect(screen.queryByText("+ 추가")).toBeNull();
  });

  it("알 수 없는 모양 id는 aria-invalid 행으로 보이고 값은 보존된다", () => {
    const { onChange } = setup({ shape: "gone" });
    const select = screen.getByLabelText("모양") as HTMLSelectElement;
    expect(select.getAttribute("aria-invalid")).toBe("true");
    expect(select.value).toBe("gone");
    expect(within(select).getByRole("option", { name: "알 수 없음: gone" })).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("경유점 x 입력은 blur에서 1회 확정하고, Enter도 확정한다", () => {
    const { onChange } = setup({ shape: "smoothstep", waypoints: [{ x: 320, y: 144 }, { x: 320, y: 288 }] });
    const x1 = screen.getByLabelText("경유점 1 x") as HTMLInputElement;
    fireEvent.change(x1, { target: { value: "400" } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.blur(x1);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenLastCalledWith({ shape: "smoothstep", waypoints: [{ x: 400, y: 144 }, { x: 320, y: 288 }] });
    const y2 = screen.getByLabelText("경유점 2 y");
    fireEvent.change(y2, { target: { value: "300" } });
    fireEvent.keyDown(y2, { key: "Enter" });
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it("Shift+↑는 32, 위/아래/삭제/추가 버튼과 16개 상한", () => {
    const { onChange } = setup({ waypoints: [{ x: 8, y: 8 }, { x: 16, y: 16 }] }, { newWaypoint: { x: 100, y: 200 } });
    const y1 = screen.getByLabelText("경유점 1 y") as HTMLInputElement;
    fireEvent.keyDown(y1, { key: "ArrowUp", shiftKey: true });
    expect(y1.value).toBe("40");
    fireEvent.click(screen.getByLabelText("경유점 1 아래로"));
    expect(onChange).toHaveBeenLastCalledWith({ waypoints: [{ x: 16, y: 16 }, { x: 8, y: 8 }] });
    fireEvent.click(screen.getByLabelText("경유점 2 삭제"));
    expect(onChange).toHaveBeenLastCalledWith({ waypoints: [{ x: 8, y: 8 }] });
    fireEvent.click(screen.getByText("+ 추가"));
    expect(onChange).toHaveBeenLastCalledWith({ waypoints: [{ x: 8, y: 8 }, { x: 16, y: 16 }, { x: 100, y: 200 }] });
    expect((screen.getByLabelText("경유점 1 위로") as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    setup({ waypoints: Array.from({ length: 16 }, (_, i) => ({ x: i, y: i })) });
    expect((screen.getByText("+ 추가") as HTMLButtonElement).disabled).toBe(true);
  });

  it("라벨 위치·경로 초기화·전부 기본으로·바뀐 항목 요약", () => {
    const layout: EdgeLayout = { shape: "step", waypoints: [{ x: 1, y: 1 }, { x: 2, y: 2 }], label_t: 0.3, label_offset: { x: 4, y: 4 }, keep: 1 };
    const { onChange } = setup(layout);
    expect(screen.getByText("기본값에서 바뀐 항목: 모양, 경유점 2, 라벨 위치")).toBeTruthy();
    fireEvent.click(screen.getByText("라벨 초기화"));
    expect(onChange).toHaveBeenLastCalledWith({ shape: "step", waypoints: [{ x: 1, y: 1 }, { x: 2, y: 2 }], keep: 1 });
    fireEvent.click(screen.getByText("경로 초기화"));
    expect(onChange).toHaveBeenLastCalledWith({ shape: "step", keep: 1 }); // 모양과 모르는 키는 유지
    fireEvent.click(screen.getByText("전부 기본으로"));
    expect(onChange).toHaveBeenLastCalledWith(null);
    const pct = screen.getByLabelText("라벨 위치(%)") as HTMLInputElement;
    expect(pct.value).toBe("30");
    fireEvent.change(pct, { target: { value: "1000" } });
    fireEvent.blur(pct);
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ label_t: 0.9 })); // 범위 보정
  });

  it("빈 칸으로 확정하면 상속으로 돌아간다(키 삭제)", () => {
    const { onChange } = setup({ shape: "smoothstep", radius: 4 });
    const r = screen.getByLabelText("모서리 둥글기(px)");
    fireEvent.change(r, { target: { value: "" } });
    fireEvent.blur(r);
    expect(onChange).toHaveBeenLastCalledWith({ shape: "smoothstep" });
  });

  it("readOnly면 모든 조작이 비활성이다", () => {
    setup({ waypoints: [{ x: 1, y: 1 }] }, { readOnly: true });
    expect((screen.getByLabelText("모양") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByText("전부 기본으로") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("경유점 1 삭제") as HTMLButtonElement).disabled).toBe(true);
  });

  it("문구는 messages로 바꿀 수 있다", () => {
    setup(null, { messages: { ...(defaultMessages), edgeLayoutTitle: "Shape & path" } });
    expect(screen.getByText(/Shape & path/)).toBeTruthy();
  });
});
