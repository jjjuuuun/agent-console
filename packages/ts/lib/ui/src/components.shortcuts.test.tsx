import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShortcutProvider, computeEffectiveKeys, useEffectiveShortcuts, useShortcuts, type ShortcutDef } from "./index";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const mk = (id: string, keys: string, run = () => {}, scope = "global"): ShortcutDef => ({ id, scope, keys, titleKey: `t.${id}`, run });
const key = (k: string, init: KeyboardEventInit = {}, el: Element | Window = window) => fireEvent.keyDown(el, { key: k, ...init });

describe("computeEffectiveKeys", () => {
  it("설정이 기본을 덮어쓰고 isDefault·conflict를 채운다", () => {
    const r = computeEffectiveKeys([mk("a", "Mod+K"), mk("b", "?"), mk("c", "g c")], { b: "Mod+K", c: "" });
    expect(r.find((x) => x.id === "b")).toMatchObject({ keys: "Mod+K", isDefault: false, conflict: "a" });
    expect(r.find((x) => x.id === "a")?.conflict).toBe("b");
    expect(r.find((x) => x.id === "c")?.keys).toBe("");
  });
  it("범위가 다른 화면끼리는 충돌이 아니다", () => {
    const r = computeEffectiveKeys([mk("a", "/", () => {}, "s1"), mk("b", "/", () => {}, "s2")]);
    expect(r.every((x) => x.conflict === undefined)).toBe(true);
  });
});

describe("ShortcutProvider", () => {
  it("Delete·Backspace 단일 키는 입력창에서 글자를 지우는 키라 동작하지 않고, 입력창 밖에서는 동작한다 (5.2R.26)", () => {
    const d = vi.fn();
    const f2 = vi.fn();
    const { container } = render(
      <ShortcutProvider defaults={[mk("d", "Delete", d), mk("f", "F2", f2)]}>
        <input aria-label="i" />
      </ShortcutProvider>,
    );
    const input = container.querySelector("input") as HTMLElement;
    key("Delete", {}, input);
    key("Backspace", {}, input);
    expect(d).not.toHaveBeenCalled();
    key("F2", {}, input);
    expect(f2).toHaveBeenCalledTimes(1);
    key("Delete", {}, document.body);
    expect(d).toHaveBeenCalledTimes(1);
  });
  it("수식키 조합은 입력창에서도, 단일 문자 키는 입력창에서 동작하지 않는다", () => {
    const k = vi.fn();
    const q = vi.fn();
    const { container } = render(
      <ShortcutProvider defaults={[mk("k", "Mod+K", k), mk("q", "?", q)]}>
        <input aria-label="i" />
        <div data-ac-editable="">
          <span tabIndex={0} data-testid="ed" />
        </div>
        <div contentEditable suppressContentEditableWarning data-testid="ce" />
      </ShortcutProvider>,
    );
    const input = container.querySelector("input") as HTMLElement;
    key("k", { ctrlKey: true }, input);
    expect(k).toHaveBeenCalledTimes(1);
    key("?", { shiftKey: true }, input);
    key("?", { shiftKey: true }, container.querySelector("[data-testid=ed]") as Element);
    key("?", { shiftKey: true }, container.querySelector("[data-testid=ce]") as Element);
    expect(q).not.toHaveBeenCalled();
    key("?", { shiftKey: true }, document.body);
    expect(q).toHaveBeenCalledTimes(1);
  });

  it("platform mac이면 Mod = Meta", () => {
    const k = vi.fn();
    render(<ShortcutProvider defaults={[mk("k", "Mod+K", k)]} platform="mac" />);
    key("k", { ctrlKey: true });
    expect(k).not.toHaveBeenCalled();
    key("k", { metaKey: true });
    expect(k).toHaveBeenCalled();
  });

  it("g 시퀀스: 1초 안의 두 번째 키만 실행, 늦거나 틀리면 취소", () => {
    vi.useFakeTimers();
    const c = vi.fn();
    const t = vi.fn();
    render(<ShortcutProvider defaults={[mk("c", "g c", c), mk("t", "g t", t)]} />);
    key("g");
    key("c");
    expect(c).toHaveBeenCalledTimes(1);
    key("g");
    act(() => void vi.advanceTimersByTime(1001));
    key("c");
    expect(c).toHaveBeenCalledTimes(1);
    key("g");
    key("x");
    key("t");
    expect(t).not.toHaveBeenCalled();
    key("g");
    act(() => void vi.advanceTimersByTime(900));
    key("t");
    expect(t).toHaveBeenCalledTimes(1);
  });

  it("시퀀스 첫 키는 입력창에서 시작되지 않는다", () => {
    const c = vi.fn();
    const { container } = render(
      <ShortcutProvider defaults={[mk("c", "g c", c)]}>
        <textarea />
      </ShortcutProvider>,
    );
    const ta = container.querySelector("textarea") as Element;
    key("g", {}, ta);
    key("c", {}, ta);
    expect(c).not.toHaveBeenCalled();
  });

  it("IME 조합 중에는 모두 무시", () => {
    const k = vi.fn();
    const q = vi.fn();
    render(<ShortcutProvider defaults={[mk("k", "Mod+K", k), mk("q", "/", q)]} />);
    key("k", { ctrlKey: true, isComposing: true });
    key("/", { keyCode: 229 });
    expect(k).not.toHaveBeenCalled();
    expect(q).not.toHaveBeenCalled();
  });

  it("overrides가 이기고 빈 값은 끈다", () => {
    const a = vi.fn();
    const b = vi.fn();
    render(<ShortcutProvider defaults={[mk("a", "Alt+J", a), mk("b", "Mod+B", b)]} overrides={{ a: "Alt+M", b: "" }} />);
    key("j", { altKey: true });
    key("m", { altKey: true });
    key("b", { ctrlKey: true });
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).not.toHaveBeenCalled();
  });

  it("중복 키를 경고한다", () => {
    const warn = vi.fn();
    render(<ShortcutProvider defaults={[mk("a", "Mod+K"), mk("b", "Mod+K")]} onWarn={warn} />);
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("useShortcuts는 마운트에 등록, 언마운트에 해제하고 최신 핸들러를 부른다", () => {
    const seen: string[] = [];
    function Screen({ tag }: { tag: string }) {
      useShortcuts([mk("s", "Mod+S", () => seen.push(tag), "screen")]);
      return null;
    }
    function Table() {
      return <output>{useEffectiveShortcuts().map((e) => e.id).join(",")}</output>;
    }
    const ui = (el: React.ReactNode) => (
      <ShortcutProvider defaults={[mk("k", "Mod+K")]}>
        <Table />
        {el}
      </ShortcutProvider>
    );
    const { rerender, container } = render(ui(<Screen tag="1" />));
    expect(container.querySelector("output")?.textContent).toBe("k,s");
    rerender(ui(<Screen tag="2" />));
    key("s", { ctrlKey: true });
    expect(seen).toEqual(["2"]);
    rerender(ui(null));
    expect(container.querySelector("output")?.textContent).toBe("k");
    key("s", { ctrlKey: true });
    expect(seen).toEqual(["2"]);
  });
});
