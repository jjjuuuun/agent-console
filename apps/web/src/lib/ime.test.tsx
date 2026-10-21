import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { isImeKeyEvent, useImeGuard } from "./ime";

describe("IME Enter 가드", () => {
  it("isComposing·keyCode 229를 조합 중으로 본다", () => {
    expect(isImeKeyEvent({ nativeEvent: { isComposing: true } })).toBe(true);
    expect(isImeKeyEvent({ keyCode: 229 })).toBe(true);
    expect(isImeKeyEvent({ keyCode: 13, nativeEvent: { isComposing: false } })).toBe(false);
  });

  it("조합 중과 확정 직후 한 틱까지 막고 그 뒤에는 푼다", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useImeGuard());
    const enter = { keyCode: 13, nativeEvent: { isComposing: false } };
    expect(result.current.isIme(enter)).toBe(false);
    act(() => result.current.handlers.onCompositionStart({} as never));
    expect(result.current.isIme(enter)).toBe(true);
    act(() => result.current.handlers.onCompositionEnd({} as never));
    expect(result.current.isIme(enter)).toBe(true);
    act(() => void vi.runAllTimers());
    expect(result.current.isIme(enter)).toBe(false);
    vi.useRealTimers();
  });
});
