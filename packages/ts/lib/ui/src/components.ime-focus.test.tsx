import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommandPalette, TrustBadge, filterCommandGroups, type CommandGroup } from "./index";

afterEach(cleanup);

const messages = { title: "빠른 이동", inputLabel: "검색", empty: "없음", loading: "로딩" };
const groups: CommandGroup[] = [{ id: "g", title: "G", items: [{ id: "a", label: "가", run: () => {} }, { id: "b", label: "나", run: () => {} }] }];

function Host({ open = true }: { open?: boolean }) {
  const [q, setQ] = useState("");
  return <CommandPalette open={open} onClose={() => {}} groups={filterCommandGroups(groups, q)} query={q} onQueryChange={setQ} messages={messages} />;
}

describe("1R.32 QA", () => {
  it("IME 조합 중 방향키는 활성 항목을 바꾸지 않는다", () => {
    render(<Host />);
    const input = screen.getByRole("combobox");
    const before = input.getAttribute("aria-activedescendant");
    fireEvent.keyDown(input, { key: "ArrowDown", isComposing: true });
    fireEvent.keyDown(input, { key: "ArrowDown", keyCode: 229 });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBe(before);
    fireEvent.compositionEnd(input);
  });

  it("닫히면 열기 전 요소로 포커스가 돌아가고 inert가 풀린다", () => {
    const { rerender } = render(
      <>
        <button data-testid="trigger">t</button>
        <Host open={false} />
      </>,
    );
    const trigger = screen.getByTestId("trigger");
    trigger.focus();
    rerender(
      <>
        <button data-testid="trigger">t</button>
        <Host open />
      </>,
    );
    expect(document.activeElement).toBe(screen.getByRole("combobox"));
    rerender(
      <>
        <button data-testid="trigger">t</button>
        <Host open={false} />
      </>,
    );
    expect(document.activeElement).toBe(trigger);
    expect(document.querySelector("[inert]")).toBeNull();
  });

  it("TrustBadge: 모르는 값도 던지지 않고 원문 중립 배지로 표시", () => {
    const fn = vi.fn();
    render(<TrustBadge trust="zzz-unknown-9" />);
    expect(screen.getByText("zzz-unknown-9")).toBeTruthy();
    fn();
  });
});
