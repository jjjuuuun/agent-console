import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EscapeProvider, useEscapeLayer } from "./escapeStack";

afterEach(cleanup);

function Layer({ active, onEscape }: { active: boolean; onEscape: () => void }) {
  useEscapeLayer(active, onEscape);
  return null;
}

describe("Esc 레이어 스택", () => {
  it("한 번의 Esc는 가장 위(나중에 연) 레이어 하나만 닫는다", () => {
    const lower = vi.fn();
    const upper = vi.fn();
    const { rerender } = render(
      <EscapeProvider>
        <Layer active onEscape={lower} />
        <Layer active={false} onEscape={upper} />
      </EscapeProvider>,
    );
    rerender(
      <EscapeProvider>
        <Layer active onEscape={lower} />
        <Layer active onEscape={upper} />
      </EscapeProvider>,
    );
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(upper).toHaveBeenCalledTimes(1);
    expect(lower).not.toHaveBeenCalled();
    rerender(
      <EscapeProvider>
        <Layer active onEscape={lower} />
        <Layer active={false} onEscape={upper} />
      </EscapeProvider>,
    );
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(lower).toHaveBeenCalledTimes(1);
  });
});
