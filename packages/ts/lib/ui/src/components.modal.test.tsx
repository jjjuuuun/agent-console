import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createPortal } from "react-dom";
import { useRef, useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { trapTabKey, useModalBackdrop } from "./index";

afterEach(cleanup);

function Host({ inert }: { inert?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const layer = useRef<HTMLDivElement>(null);
  useModalBackdrop(open, layer, inert === undefined ? {} : { inert });
  return (
    <div>
      <button onClick={() => setOpen(true)}>open</button>
      {open
        ? createPortal(
            <div ref={layer} data-testid="layer">
              <div ref={ref} onKeyDown={(e) => trapTabKey(e, ref.current)}>
                <button>first</button>
                <button onClick={() => setOpen(false)}>last</button>
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

describe("useModalBackdrop / trapTabKey (5R.21)", () => {
  it("배경을 inert로 두고 닫으면 풀고 트리거로 포커스를 돌려준다", () => {
    const { container } = render(<Host />);
    const trigger = screen.getByText("open");
    trigger.focus();
    fireEvent.click(trigger);
    expect(container.hasAttribute("inert")).toBe(true);
    expect(screen.getByTestId("layer").hasAttribute("inert")).toBe(false);
    fireEvent.click(screen.getByText("last"));
    expect(container.hasAttribute("inert")).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });

  it("inert:false면 배경을 막지 않는다", () => {
    const { container } = render(<Host inert={false} />);
    fireEvent.click(screen.getByText("open"));
    expect(container.hasAttribute("inert")).toBe(false);
  });

  it("Tab이 끝에서 처음으로, Shift+Tab이 처음에서 끝으로 순환한다", () => {
    render(<Host />);
    fireEvent.click(screen.getByText("open"));
    screen.getByText("last").focus();
    fireEvent.keyDown(screen.getByText("last"), { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("first"));
    fireEvent.keyDown(screen.getByText("first"), { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText("last"));
  });
});
