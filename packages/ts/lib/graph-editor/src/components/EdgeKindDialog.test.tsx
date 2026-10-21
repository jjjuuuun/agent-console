import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EdgeKindDialog, NodeCard } from "../index";
import { edgeTypes } from "../testing";

afterEach(cleanup);

describe("EdgeKindDialog", () => {
  it("첫 항목이 미리 선택되어 있고 확정하면 그 종류를 돌려준다", () => {
    const onConfirm = vi.fn();
    render(<EdgeKindDialog edgeTypes={edgeTypes} preselected={edgeTypes[0]!.id} onConfirm={onConfirm} onCancel={() => {}} />);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.checked)).toEqual([true, false]);
    fireEvent.click(screen.getByRole("button", { name: "연결" }));
    expect(onConfirm).toHaveBeenCalledWith("flow-a");
  });
  it("다른 종류를 고르거나 Esc로 취소할 수 있다", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<EdgeKindDialog edgeTypes={edgeTypes} preselected="flow-a" onConfirm={onConfirm} onCancel={onCancel} />);
    fireEvent.click(screen.getByLabelText("흐름 B"));
    fireEvent.click(screen.getByRole("button", { name: "연결" }));
    expect(onConfirm).toHaveBeenCalledWith("flow-b");
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});

describe("EdgeKindDialog 포트 열(노드 몸체에 놓아 연결, UX-P11)", () => {
  it("info.portsText가 있는 행에만 포트 열을 보인다", () => {
    render(<EdgeKindDialog edgeTypes={edgeTypes} preselected="flow-a" info={{ "flow-a": { portsText: "결과 → 받는 값" } }} onConfirm={() => {}} onCancel={() => {}} />);
    expect(document.querySelector('[data-ports-for="flow-a"]')?.textContent).toBe("결과 → 받는 값");
    expect(document.querySelector('[data-ports-for="flow-b"]')).toBeNull();
  });
});

describe("NodeCard 가장자리 띠 슬롯", () => {
  it("edgeBands 슬롯을 그린다", () => {
    render(<NodeCard label="L" typeTitle="T" accent="red" iconText="L" inputs={[]} outputs={[]} edgeBands={<i data-testid="band" />} />);
    expect(screen.getByTestId("band")).toBeTruthy();
  });
});

describe("NodeCard 단독 사용", () => {
  it("React Flow 없이 렌더되고 data-status만 단다", () => {
    render(<NodeCard label="L" typeTitle="T" accent="red" iconText="L" inputs={[{ id: "i", label: "입력" }]} outputs={[]} state={{ status: "failed", errorSummary: "오류!" }} />);
    expect(document.querySelector('[data-status="failed"]')).toBeTruthy();
    expect(screen.getByText("오류!")).toBeTruthy();
    expect(screen.getByText("실패")).toBeTruthy();
  });
});
