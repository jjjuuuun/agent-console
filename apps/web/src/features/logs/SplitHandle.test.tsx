import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SplitHandle } from "./SplitHandle";

afterEach(cleanup);

describe("SplitHandle", () => {
  it("vertical: role=separator, 현재 값 노출, ←가 키우고 →가 줄이며 범위로 자른다", () => {
    const onChange = vi.fn();
    render(<SplitHandle size={440} min={320} max={456} onChange={onChange} label="폭" />);
    const sep = screen.getByRole("separator", { name: "폭" });
    expect(sep.getAttribute("aria-orientation")).toBe("vertical");
    expect(sep.getAttribute("aria-valuenow")).toBe("440");
    fireEvent.keyDown(sep, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith(456);
    fireEvent.keyDown(sep, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith(424);
  });

  it("horizontal: ↓가 키우고 ↑가 줄인다, 포인터는 아래로 끌면 커진다", () => {
    const onChange = vi.fn();
    render(<SplitHandle orientation="horizontal" size={240} min={96} max={480} step={20} onChange={onChange} label="높이" />);
    const sep = screen.getByRole("separator", { name: "높이" });
    expect(sep.getAttribute("aria-orientation")).toBe("horizontal");
    fireEvent.keyDown(sep, { key: "ArrowDown" });
    expect(onChange).toHaveBeenLastCalledWith(260);
    fireEvent.keyDown(sep, { key: "ArrowUp" });
    expect(onChange).toHaveBeenLastCalledWith(220);
    fireEvent.pointerDown(sep, { clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(sep, { clientY: 160, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(300);
    fireEvent.pointerMove(sep, { clientY: -1000, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(96);
  });
});
