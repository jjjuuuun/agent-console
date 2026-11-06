import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LONG, setup } from "./sddTestSetup";

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

const RULES = "/specs/sp1?prj=p1&tab=rules";

describe("규칙 탭: 편집 중 자동 검사(600ms 디바운스)", () => {
  it("연속 입력에는 검사가 한 번만 가고, 이슈는 해당 필드 위치에 붙는다", async () => {
    const check = vi.fn(async () => ({ issues: [{ severity: "error" as const, code: "x", message: "이름 쪽 서버 문장", path: "/name" }] }));
    const { sdd } = setup(RULES, { sdd: { checkSpec: check } });
    const name = (await screen.findByLabelText("이름", {}, LONG)) as HTMLInputElement;
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    fireEvent.change(name, { target: { value: "가" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    fireEvent.change(name, { target: { value: "가나" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    fireEvent.change(name, { target: { value: "가나다" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(599); });
    expect(sdd.checkSpec).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(2); });
    expect(sdd.checkSpec).toHaveBeenCalledTimes(1);
    const body = sdd.checkSpec.mock.calls[0]?.[1] as { rules: unknown; documents: unknown[] };
    expect(Array.isArray(body.documents)).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(screen.getAllByText("이름 쪽 서버 문장").length).toBeGreaterThan(0);
  });

  it("편집하지 않으면 자동 검사를 하지 않는다", async () => {
    const { sdd } = setup(RULES);
    await screen.findByLabelText("이름", {}, LONG);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(sdd.checkSpec).not.toHaveBeenCalled();
  });
});

describe("규칙 탭: 자동 진행 켜기 확인", () => {
  const openAutomation = async () => {
    const navEl = await screen.findByRole("navigation", { name: "섹션" }, LONG);
    fireEvent.click(within(navEl).getByRole("button", { name: /자동 진행/ }));
    return screen.findByRole("checkbox", { name: "켜기" }, LONG);
  };

  it("켜는 순간 확인 대화상자가 나오고, 취소하면 값이 그대로(저장 안 됨 아님)다", async () => {
    setup(RULES);
    const toggle = (await openAutomation()) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    fireEvent.click(toggle);
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect(within(dialog).getByText("자동 진행을 켭니다")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect((screen.getByRole("checkbox", { name: "켜기" }) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText("저장됨")).toBeTruthy();
  });

  it("확인하면 켜지고 저장 안 됨이 된다", async () => {
    setup(RULES);
    fireEvent.click(await openAutomation());
    const dialog = await screen.findByRole("dialog", {}, LONG);
    fireEvent.click(within(dialog).getByRole("button", { name: "켜기" }));
    expect(await screen.findByText("저장 안 됨", {}, LONG)).toBeTruthy();
    expect((screen.getByRole("checkbox", { name: "켜기" }) as HTMLInputElement).checked).toBe(true);
  });
});
