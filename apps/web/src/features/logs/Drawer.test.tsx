import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { Drawer } from "./Drawer";

afterEach(cleanup);

// 공용 모달 훅(ui `useModalBackdrop`·`trapTabKey`)을 쓰는 오른쪽 드로어: 첫 입력 포커스, Tab 순환, Esc, 배경 inert, 포커스 복귀.
function Host({ modal = true }: { modal?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="app">
      <button onClick={() => setOpen(true)}>트리거</button>
      <Drawer open={open} title="패널" onClose={() => setOpen(false)} modal={modal}>
        <button>앞</button>
        <input aria-label="이름" />
        <button>뒤</button>
      </Drawer>
    </div>
  );
}

describe("logs Drawer", () => {
  it("열면 첫 입력에 포커스하고 배경을 inert로 두며 닫으면 트리거로 돌려준다", () => {
    const { container } = render(<Host />);
    const trigger = screen.getByText("트리거");
    trigger.focus();
    fireEvent.click(trigger);
    expect(document.activeElement).toBe(screen.getByLabelText("이름"));
    expect(container.hasAttribute("inert")).toBe(true);
    expect(screen.getByRole("dialog", { name: "패널" }).getAttribute("aria-modal")).toBe("true");
    fireEvent.keyDown(screen.getByLabelText("이름"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(container.hasAttribute("inert")).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });

  it("Tab이 마지막에서 처음으로, Shift+Tab이 처음에서 마지막으로 순환한다(닫기 버튼 포함)", () => {
    render(<Host />);
    fireEvent.click(screen.getByText("트리거"));
    const dialog = screen.getByRole("dialog");
    const items = Array.from(dialog.querySelectorAll<HTMLElement>("button, input"));
    const first = items[0]!;
    const last = items[items.length - 1]!;
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("비모달이면 배경을 막지 않고 Tab을 가두지 않지만 Esc로 닫으면 트리거로 복귀한다", () => {
    const { container } = render(<Host modal={false} />);
    const trigger = screen.getByText("트리거");
    trigger.focus();
    fireEvent.click(trigger);
    expect(container.hasAttribute("inert")).toBe(false);
    expect(screen.getByRole("dialog").hasAttribute("aria-modal")).toBe(false);
    const dialog = screen.getByRole("dialog");
    const last = Array.from(dialog.querySelectorAll<HTMLElement>("button, input")).pop()!;
    last.focus();
    const notPrevented = fireEvent.keyDown(last, { key: "Tab" });
    expect(notPrevented).toBe(true);
    fireEvent.keyDown(last, { key: "Escape" });
    expect(document.activeElement).toBe(trigger);
  });
});
