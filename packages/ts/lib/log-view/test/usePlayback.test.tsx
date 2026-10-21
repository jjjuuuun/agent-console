import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePlayback, type PlaybackClock } from "../src";

function fakeClock() {
  let id = 0;
  const timers = new Map<number, { fn: () => void; ms: number }>();
  const clock: PlaybackClock = {
    now: () => 0,
    setTimeout: (fn, ms) => {
      timers.set(++id, { fn, ms });
      return id;
    },
    clearTimeout: (h) => void timers.delete(h as number),
  };
  return {
    clock,
    pending: () => [...timers.values()],
    fire: () => {
      const entry = [...timers.entries()][0];
      if (!entry) throw new Error("대기 중인 타이머가 없다");
      timers.delete(entry[0]);
      act(() => entry[1].fn());
    },
  };
}

const events = [
  { seq: 1, time: 0 },
  { seq: 2, time: 1 },
  { seq: 3, time: 100 },
];

describe("usePlayback", () => {
  it("끝에서 재생하면 처음부터 시작하고 간격·속도·공백 건너뛰기로 대기하다가 끝에서 자동 정지", () => {
    const t = fakeClock();
    const { result } = renderHook(() => usePlayback({ events, clock: t.clock, subscribeHidden: () => () => undefined }));
    expect(result.current.index).toBe(2); // 처음 진입 = 끝
    act(() => result.current.play());
    expect(result.current.index).toBe(-1);
    expect(result.current.playing).toBe(true);
    expect(t.pending()[0]?.ms).toBe(16); // 시작 전 -> 첫 이벤트: 간격 0이면 하한
    t.fire();
    expect(result.current.index).toBe(0);
    expect(t.pending()[0]?.ms).toBe(1000); // 1초 간격, 1x
    t.fire();
    expect(result.current.index).toBe(1);
    expect(t.pending()[0]?.ms).toBe(2000); // 99초 간격 -> 공백 건너뛰기로 2초
    t.fire();
    expect(result.current.index).toBe(2);
    expect(result.current.playing).toBe(false);
    expect(result.current.ended).toBe(true);
    expect(t.pending()).toHaveLength(0);
  });

  it("속도를 바꾸면 대기 시간이 바뀌고 공백 건너뛰기를 끄면 상한이 30초", () => {
    const t = fakeClock();
    const { result } = renderHook(() => usePlayback({ events, clock: t.clock, subscribeHidden: () => () => undefined }));
    act(() => result.current.seek(0));
    act(() => result.current.setSpeed(10));
    act(() => result.current.play());
    expect(t.pending()).toHaveLength(1);
    expect(t.pending()[0]?.ms).toBe(100); // 1초 / 10
    act(() => result.current.pause());
    expect(t.pending()).toHaveLength(0);
    act(() => result.current.seek(1));
    act(() => result.current.setSkipGaps(false));
    act(() => result.current.setSpeed(1));
    act(() => result.current.play());
    expect(t.pending()[0]?.ms).toBe(30_000);
  });

  it("탭이 숨겨지면 일시정지하고 step은 정지시킨다", () => {
    const t = fakeClock();
    let hide: () => void = () => undefined;
    const { result } = renderHook(() => usePlayback({ events, clock: t.clock, subscribeHidden: (cb) => { hide = cb; return () => undefined; } }));
    act(() => result.current.play());
    expect(result.current.playing).toBe(true);
    act(() => hide());
    expect(result.current.playing).toBe(false);
    act(() => result.current.play());
    act(() => result.current.step(1));
    expect(result.current.playing).toBe(false);
  });

  it("바깥에서 위치를 제어하면(URL) 그 값을 따른다", () => {
    const t = fakeClock();
    const seen: number[] = [];
    const { result, rerender } = renderHook(({ index }) => usePlayback({ events, clock: t.clock, index, onIndexChange: (i) => seen.push(i), subscribeHidden: () => () => undefined }), { initialProps: { index: 0 } });
    expect(result.current.index).toBe(0);
    act(() => result.current.step(1));
    expect(seen).toEqual([1]);
    expect(result.current.index).toBe(0); // 부모가 바꾸기 전에는 그대로
    rerender({ index: 1 });
    expect(result.current.index).toBe(1);
  });
});
