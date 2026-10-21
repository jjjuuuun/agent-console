import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { NodeLayout } from "@agent-console/contracts";
import { BUILTIN_DIRECTIONS } from "../logic/layout";
import { NodeLayoutPanel } from "./NodeLayoutPanel";
import type { NodeLayoutPanelProps, NodeLayoutPortRow } from "./NodeLayoutPanel";

afterEach(cleanup);

const ports: NodeLayoutPortRow[] = [
  { key: "in:in", io: "in", id: "in", label: "받는 값", inheritedSide: "left" },
  { key: "out:result", io: "out", id: "result", label: "결과", inheritedSide: "right" },
];

function setup(layout: NodeLayout | null, over: Partial<NodeLayoutPanelProps> = {}) {
  const onChange = vi.fn();
  const view = render(
    <NodeLayoutPanel layout={layout} directions={BUILTIN_DIRECTIONS} inheritedDirection={{ id: "lr", source: "graph" }} ports={ports} onChange={onChange} {...over} />,
  );
  return { onChange, ...view };
}

describe("NodeLayoutPanel (§3.4)", () => {
  it("방향 버튼은 방향 어휘 표에서 만들고 상속 중이면 출처와 결정된 값을 보인다", () => {
    setup(null);
    expect(screen.getAllByRole("button", { pressed: false }).map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual(expect.arrayContaining(["오른쪽", "아래", "왼쪽", "위"]));
    expect(screen.getByRole("button", { name: /^상속/, pressed: true })).toBeTruthy();
    expect(screen.getByText("상속 중: 그래프 방향 → 오른쪽")).toBeTruthy();
  });

  it("[자동] 버튼은 direction을 auto로 쓰고, 눌린 상태로 보이며, 상속으로 돌릴 수 있다 (4R.20)", () => {
    const { onChange, rerender } = setup(null);
    fireEvent.click(screen.getByRole("button", { name: "자동" }));
    expect(onChange).toHaveBeenLastCalledWith({ direction: "auto" });
    rerender(<NodeLayoutPanel layout={{ direction: "auto" }} directions={BUILTIN_DIRECTIONS} inheritedDirection={{ id: "lr", source: "graph" }} ports={ports} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "자동", pressed: true })).toBeTruthy();
    expect(screen.queryByText(/알 수 없음/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^상속/ }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("방향을 고르면 direction만 바꾼 layout을, 상속을 누르면 키를 지운다", () => {
    const { onChange, rerender } = setup({ ports: { "in:in": "top" } });
    fireEvent.click(screen.getByRole("button", { name: "아래" }));
    expect(onChange).toHaveBeenLastCalledWith({ direction: "tb", ports: { "in:in": "top" } });
    rerender(<NodeLayoutPanel layout={{ direction: "tb" }} directions={BUILTIN_DIRECTIONS} inheritedDirection={{ id: "lr", source: "graph" }} ports={ports} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "아래", pressed: true })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^상속/ }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("포트 표: 상속 행에 결정된 면을 괄호로 보이고, 면을 고르면 그 포트 키만 기록한다", () => {
    const { onChange } = setup(null);
    const sel = screen.getByRole("combobox", { name: "입력 받는 값의 면" }) as HTMLSelectElement;
    expect(Array.from(sel.options).map((o) => o.textContent)).toEqual(["상속 (왼쪽)", "왼쪽", "오른쪽", "위", "아래", "자동"]);
    fireEvent.change(sel, { target: { value: "top" } });
    expect(onChange).toHaveBeenLastCalledWith({ ports: { "in:in": "top" } });
    fireEvent.change(sel, { target: { value: "auto" } });
    expect(onChange).toHaveBeenLastCalledWith({ ports: { "in:in": "auto" } });
  });

  it("바꾼 포트에는 표시가 붙고, 상속으로 되돌리면 ports 키째 사라진다", () => {
    const { onChange } = setup({ ports: { "out:result": "bottom" } });
    expect(screen.getAllByRole("img", { name: "이 노드에서 바꾼 값" })).toHaveLength(1);
    fireEvent.change(screen.getByRole("combobox", { name: "출력 결과의 면" }), { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("사라진 포트의 값은 보존하고 행과 [삭제]를 보인다, 알 수 없는 면 값도 보존", () => {
    const { onChange } = setup({ ports: { "out:gone": "left", "in:in": "diagonal" } });
    expect(screen.getByText("사라진 포트 out:gone")).toBeTruthy();
    const sel = screen.getByRole("combobox", { name: "입력 받는 값의 면" }) as HTMLSelectElement;
    expect(sel.value).toBe("diagonal");
    expect(sel.getAttribute("aria-invalid")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "삭제" }));
    expect(onChange).toHaveBeenLastCalledWith({ ports: { "in:in": "diagonal" } });
  });

  it("알 수 없는 방향 값은 상속으로 그리되 안내하고 보존한다", () => {
    setup({ direction: "zigzag" });
    expect(screen.getByText("알 수 없음: zigzag")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^상속/, pressed: true })).toBeTruthy();
  });

  it("[이 방향을 그래프 기본으로]는 콜백이 있을 때만 보이고 결정된 방향을 넘긴다", () => {
    const onMake = vi.fn();
    setup({ direction: "bt" }, { onMakeGraphDefault: onMake });
    fireEvent.click(screen.getByRole("button", { name: "이 방향을 그래프 기본으로" }));
    expect(onMake).toHaveBeenCalledWith("bt");
    cleanup();
    setup(null);
    expect(screen.queryByRole("button", { name: "이 방향을 그래프 기본으로" })).toBeNull();
  });

  it("[배치 초기화]는 layout 전체를 지우고, 값이 없으면 비활성", () => {
    const { onChange } = setup({ direction: "tb" });
    fireEvent.click(screen.getByRole("button", { name: "배치 초기화" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
    cleanup();
    setup(null);
    expect((screen.getByRole("button", { name: "배치 초기화" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("읽기 전용에서는 모든 조작이 비활성이다", () => {
    setup({ direction: "tb" }, { readOnly: true });
    for (const b of screen.getAllByRole("button")) expect((b as HTMLButtonElement).disabled).toBe(true);
    for (const s of screen.getAllByRole("combobox")) expect((s as HTMLSelectElement).disabled).toBe(true);
  });

  it("새 방향 어휘를 표에 더하면 코드 수정 없이 버튼이 생긴다", () => {
    setup(null, { directions: { ...BUILTIN_DIRECTIONS, diag: { in: "top", out: "right" } } });
    expect(screen.getByRole("button", { name: "diag" })).toBeTruthy();
  });
});
