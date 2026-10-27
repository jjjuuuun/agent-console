import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BackendDescriptor } from "@agent-console/contracts";
import { BackendChooserCard } from "./BackendChooserCard";

afterEach(cleanup);

const options = [
  { id: "real", title: "실제" },
  { id: "fake-agent", title: "가짜 에이전트(테스트용)", ui_hints: { badge: "테스트용" } },
] as BackendDescriptor[];

describe("BackendChooserCard", () => {
  it("처음엔 아무것도 고르지 않고, 고르기 전엔 확인이 막힌다", () => {
    render(<BackendChooserCard options={options} onConfirm={() => {}} />);
    expect(screen.getByRole("button", { name: /선택하고 계속/ }).hasAttribute("disabled")).toBe(true);
  });
  it("initialId가 목록에 있으면 미리 고른다(백엔드 바꾸기)", () => {
    const onConfirm = vi.fn();
    render(<BackendChooserCard options={options} initialId="fake-agent" onConfirm={onConfirm} />);
    expect((screen.getByRole("radio", { name: /가짜 에이전트/ }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /선택하고 계속/ }));
    expect(onConfirm).toHaveBeenCalledWith("fake-agent");
  });
  it("목록에 없는 initialId는 무시한다", () => {
    render(<BackendChooserCard options={options} initialId="gone" onConfirm={() => {}} />);
    expect(screen.getAllByRole("radio").every((r) => !(r as HTMLInputElement).checked)).toBe(true);
  });
  it("ui_hints.hidden인 백엔드는 선택지에서 뺀다", () => {
    const withHidden = [...options, { id: "secret", title: "숨김", ui_hints: { hidden: true } }] as BackendDescriptor[];
    render(<BackendChooserCard options={withHidden} onConfirm={() => {}} />);
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByRole("radio", { name: /숨김/ })).toBeNull();
  });
  it("문구의 조사가 받침에 맞다", () => {
    render(<BackendChooserCard options={options} nodeLabels={["도우미"]} onConfirm={() => {}} />);
    expect(screen.getByText(/'도우미'를 실행할/)).toBeTruthy();
  });
  it("디스크립터가 하나뿐이면 미리 고른다", () => {
    const onConfirm = vi.fn();
    render(<BackendChooserCard options={[options[0] as BackendDescriptor]} onConfirm={onConfirm} />);
    expect((screen.getByRole("radio") as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /선택하고 계속/ }));
    expect(onConfirm).toHaveBeenCalledWith("real");
  });
  it("고른 뒤 확인하면 고른 id로 한 번 호출한다", () => {
    const onConfirm = vi.fn();
    render(<BackendChooserCard options={options} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("radio", { name: /실제/ }));
    fireEvent.click(screen.getByRole("radio", { name: /가짜 에이전트/ }));
    fireEvent.click(screen.getByRole("button", { name: /선택하고 계속/ }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("fake-agent");
  });
  it("백엔드가 0개면 안내만 보이고 선택·확인이 없다", () => {
    render(<BackendChooserCard options={[]} onConfirm={() => {}} />);
    expect(screen.getByText("사용할 수 있는 백엔드가 없습니다.")).toBeTruthy();
    expect(screen.queryAllByRole("radio").length).toBe(0);
    expect(screen.queryByRole("button")).toBeNull();
  });
  it("배지·비용·설명은 디스크립터 데이터로 그린다", () => {
    const rich = [{ id: "x", title: "엑스", description: "설명문", cost_note: "비용문", ui_hints: { badge: "배지문" } }] as BackendDescriptor[];
    render(<BackendChooserCard options={rich} onConfirm={() => {}} />);
    for (const t of ["엑스", "설명문", "비용문", "배지문"]) expect(screen.getByText(t)).toBeTruthy();
  });
  it("busy면 선택과 확인이 막히고 진행 문구를 보인다", () => {
    render(<BackendChooserCard options={options} initialId="fake-agent" busy onConfirm={() => {}} />);
    expect(screen.getByRole("button", { name: /저장하고 다시 보내는 중/ }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("group", { name: "실행 백엔드" }).hasAttribute("disabled")).toBe(true);
  });
  it("직전 실패 문구를 보인다", () => {
    render(<BackendChooserCard options={options} error="저장 실패 사유" onConfirm={() => {}} />);
    expect(screen.getByText("저장 실패 사유")).toBeTruthy();
  });
  it("mode=change는 값이 있는 상태의 문구로 바꾼다", () => {
    render(<BackendChooserCard options={options} mode="change" initialId="fake-agent" onConfirm={() => {}} />);
    expect(screen.getByText("지금 쓰는 실행 백엔드를 바꿉니다.")).toBeTruthy();
    expect(screen.queryByText(/정해지지 않았습니다/)).toBeNull();
  });
  it("노드 이름이 없거나 여럿이어도 문구가 깨지지 않는다", () => {
    const { unmount } = render(<BackendChooserCard options={options} onConfirm={() => {}} />);
    expect(screen.getByText(/백엔드가 정해지지 않았습니다/)).toBeTruthy();
    unmount();
    render(<BackendChooserCard options={options} nodeLabels={["가", "나"]} onConfirm={() => {}} />);
    expect(screen.getByText(/'가', '나'를 실행할/)).toBeTruthy();
  });
});
