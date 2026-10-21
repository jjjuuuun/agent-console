import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Drawer } from "./index";

afterEach(cleanup);

describe("Drawer", () => {
  it("dialog 역할·제목 이름·안내 줄·하단 버튼을 그린다", () => {
    render(
      <Drawer open title="새 에이전트" description="안내 한 줄" closeLabel="닫기" onClose={() => {}} actions={<button type="button">만들기</button>}>
        <input aria-label="이름" />
      </Drawer>,
    );
    const dialog = screen.getByRole("dialog", { name: "새 에이전트" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByText("안내 한 줄")).toBeTruthy();
    expect(screen.getByRole("button", { name: "만들기" })).toBeTruthy();
  });

  it("열면 본문 첫 입력에 포커스, Esc와 닫기 버튼이 onClose를 부른다", () => {
    const onClose = vi.fn();
    render(
      <Drawer open title="t" closeLabel="닫기" onClose={onClose}>
        <input aria-label="이름" />
      </Drawer>,
    );
    expect(document.activeElement).toBe(screen.getByLabelText("이름"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("닫혀 있으면 아무것도 그리지 않는다", () => {
    render(
      <Drawer open={false} title="t" closeLabel="닫기" onClose={() => {}} />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
