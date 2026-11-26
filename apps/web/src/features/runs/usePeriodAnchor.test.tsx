import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isAnchorStale, usePeriodAnchor } from "./usePeriodAnchor";
import { periodSince } from "./runsLib";
import { PERIOD_OPTIONS } from "./runsConfig";

const HOUR = 3600_000;

describe("isAnchorStale", () => {
  it("간격이 지났을 때만 낡았다", () => {
    expect(isAnchorStale(0, 999, 1000)).toBe(false);
    expect(isAnchorStale(0, 1000, 1000)).toBe(true);
  });
});

describe("usePeriodAnchor (가짜 시계)", () => {
  let clock = 0;
  const now = () => clock;
  beforeEach(() => {
    vi.useFakeTimers();
    clock = 1_000_000;
  });
  afterEach(() => vi.useRealTimers());
  const advance = (ms: number) => {
    clock += ms;
    act(() => {
      vi.advanceTimersByTime(ms);
    });
  };

  it("간격 전에는 그대로, 타이머가 간격을 넘기면 기준을 다시 잡아 하한이 앞으로 간다", () => {
    const { result } = renderHook(() => usePeriodAnchor({ intervalMs: HOUR, now }));
    const first = result.current.anchorMs;
    advance(HOUR / 2);
    expect(result.current.anchorMs).toBe(first);
    advance(HOUR / 2);
    expect(result.current.anchorMs).toBe(first + HOUR);
    const day = PERIOD_OPTIONS.find((p) => p.id === "24h")!;
    expect(periodSince("24h", result.current.anchorMs / 1000, PERIOD_OPTIONS)! - periodSince("24h", first / 1000, PERIOD_OPTIONS)!).toBe(HOUR / 1000);
    expect(day.seconds).toBe(86400);
  });

  it("창 포커스는 간격이 지났을 때만 다시 잡고, refresh는 늘 다시 잡는다", () => {
    const { result } = renderHook(() => usePeriodAnchor({ intervalMs: HOUR, now }));
    const first = result.current.anchorMs;
    clock += HOUR / 4;
    act(() => void window.dispatchEvent(new Event("focus")));
    expect(result.current.anchorMs).toBe(first);
    act(() => result.current.refresh());
    expect(result.current.anchorMs).toBe(first + HOUR / 4);
    clock += HOUR * 2;
    act(() => void window.dispatchEvent(new Event("focus")));
    expect(result.current.anchorMs).toBe(clock);
  });

  it("간격이 0이면 자동 갱신이 없다", () => {
    const { result } = renderHook(() => usePeriodAnchor({ intervalMs: 0, now }));
    const first = result.current.anchorMs;
    advance(HOUR * 5);
    act(() => void window.dispatchEvent(new Event("focus")));
    expect(result.current.anchorMs).toBe(first);
  });
});
