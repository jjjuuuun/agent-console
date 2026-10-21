import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { retryFocus } from "./focusRetry";

const mk = (tag: string, parent: HTMLElement = document.body) => {
  const el = document.createElement(tag);
  el.tabIndex = 0;
  parent.appendChild(el);
  return el;
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("retryFocus", () => {
  it("포커스가 body나 캔버스에 있으면 요소로 옮기고, 유지되면 멈춘다", () => {
    const field = mk("input");
    const canvas = mk("div");
    canvas.className = "react-flow";
    mk("button", canvas).focus();
    retryFocus({ find: () => field });
    vi.advanceTimersByTime(130);
    expect(document.activeElement).toBe(field);
    vi.advanceTimersByTime(2000);
    expect(document.activeElement).toBe(field);
    expect(vi.getTimerCount()).toBe(0);
  });
  it("사용자가 다른 요소를 눌러 포커스가 옮겨지면 되돌리지 않고 멈춘다", () => {
    const field = mk("input");
    const other = mk("button");
    const cancel = retryFocus({ find: () => field });
    other.focus();
    vi.advanceTimersByTime(130);
    expect(document.activeElement).toBe(other);
    expect(vi.getTimerCount()).toBe(0);
    cancel();
  });
  it("pointerdown·keydown이 일어나면 즉시 멈춘다", () => {
    const field = mk("input");
    retryFocus({ find: () => field });
    document.dispatchEvent(new Event("pointerdown"));
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(500);
    expect(document.activeElement).not.toBe(field);
  });
  it("취소(언마운트)하면 타이머가 남지 않고 포커스를 주지 않는다", () => {
    const field = mk("input");
    const cancel = retryFocus({ find: () => field });
    expect(vi.getTimerCount()).toBe(1);
    cancel();
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(500);
    expect(document.activeElement).not.toBe(field);
  });
});
