import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShortcutProvider, useShortcutRegistry, type ShortcutDef } from "./index";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
const mk = (id: string, keys: string, run = () => {}, scope = "global"): ShortcutDef => ({ id, scope, keys, titleKey: `t.${id}`, run });
const key = (k: string, init: KeyboardEventInit = {}, el: Element | Window = window) => fireEvent.keyDown(el, { key: k, ...init });

describe("shortcuts 추가 검증(QA)", () => {
  it("select 안에서도 단일 문자 키는 막힌다", () => {
    const q = vi.fn();
    const { container } = render(
      <ShortcutProvider defaults={[mk("q", "/", q)]}>
        <select aria-label="s" />
      </ShortcutProvider>,
    );
    key("/", {}, container.querySelector("select") as Element);
    expect(q).not.toHaveBeenCalled();
  });

  it("시퀀스 중간의 IME 이벤트는 시퀀스를 깨지 않고 무시된다", () => {
    vi.useFakeTimers();
    const c = vi.fn();
    render(<ShortcutProvider defaults={[mk("c", "g c", c)]} />);
    key("g");
    key("c", { isComposing: true });
    expect(c).not.toHaveBeenCalled();
    key("c");
    expect(c).toHaveBeenCalledTimes(1);
  });

  it("e.repeat(키 누르고 있기)는 무시한다", () => {
    const k = vi.fn();
    render(<ShortcutProvider defaults={[mk("k", "Mod+K", k)]} />);
    key("k", { ctrlKey: true, repeat: true });
    expect(k).not.toHaveBeenCalled();
    key("k", { ctrlKey: true });
    expect(k).toHaveBeenCalledTimes(1);
  });

  it("단일 `g`와 시퀀스 `g c`가 함께 있으면 시퀀스가 우선, 시간이 지나거나 다른 키면 단일이 실행된다", () => {
    vi.useFakeTimers();
    const g = vi.fn();
    const c = vi.fn();
    render(<ShortcutProvider defaults={[mk("c", "g c", c), mk("g", "g", g)]} onWarn={null} />);
    key("g");
    key("c");
    expect(c).toHaveBeenCalledTimes(1);
    expect(g).not.toHaveBeenCalled();
    key("g");
    expect(g).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1100);
    });
    expect(g).toHaveBeenCalledTimes(1);
    key("g");
    key("x");
    expect(g).toHaveBeenCalledTimes(2);
    expect(c).toHaveBeenCalledTimes(1);
  });

  it("enabled=false면 아무것도 실행하지 않는다", () => {
    const k = vi.fn();
    render(<ShortcutProvider defaults={[mk("k", "Mod+K", k)]} enabled={false} />);
    key("k", { ctrlKey: true });
    expect(k).not.toHaveBeenCalled();
  });

  it("global과 화면 범위는 충돌, getEffectiveKeys에 conflict가 나온다", () => {
    let got: { id: string; conflict?: string }[] = [];
    function Probe() {
      got = useShortcutRegistry().getEffectiveKeys();
      return null;
    }
    render(
      <ShortcutProvider defaults={[mk("a", "/", () => {}, "global"), mk("b", "/", () => {}, "s1")]} onWarn={null}>
        <Probe />
      </ShortcutProvider>,
    );
    expect(got.find((x) => x.id === "a")?.conflict).toBe("b");
  });

  it("언마운트 시 리스너 해제 및 대기 타이머 정리", () => {
    vi.useFakeTimers();
    const c = vi.fn();
    const { unmount } = render(<ShortcutProvider defaults={[mk("c", "g c", c)]} />);
    key("g");
    unmount();
    act(() => void vi.advanceTimersByTime(2000));
    key("c");
    expect(c).not.toHaveBeenCalled();
  });
});
