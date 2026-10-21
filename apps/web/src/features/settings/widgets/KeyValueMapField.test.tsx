import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KeyValueMapField } from "./KeyValueMapField";

afterEach(cleanup);

describe("KeyValueMapField: 키 입력의 IME Enter", () => {
  function setup() {
    const onChange = vi.fn();
    const props = { id: "kv", value: {}, onChange, label: "맵", options: {} } as unknown as Parameters<typeof KeyValueMapField>[0];
    render(<KeyValueMapField {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "규칙 추가" }));
    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "키하나" } });
    return { input, onChange };
  }

  it("조합 확정 Enter(isComposing, keyCode 229, 확정 직후)에는 커밋하지 않는다", () => {
    const { input, onChange } = setup();
    fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("조합이 아닌 Enter는 커밋한다", async () => {
    const { input, onChange } = setup();
    await new Promise((r) => setTimeout(r, 5));
    fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });
    expect(onChange).toHaveBeenCalledWith({ "키하나": "" });
  });
});
