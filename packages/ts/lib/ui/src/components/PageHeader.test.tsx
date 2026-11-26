import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PageHeader } from "./PageHeader";

// happy-dom은 레이아웃을 계산하지 않으므로 측정 값을 직접 정한다.
let width = 900;
let titleWidth = 300;
let secondaryWidth = 260;
let observer: (() => void) | undefined;
let restore: (() => void)[] = [];

function define(proto: object, name: string, get: (el: HTMLElement) => number) {
  const original = Object.getOwnPropertyDescriptor(proto, name);
  Object.defineProperty(proto, name, { configurable: true, get() { return get(this as HTMLElement); } });
  restore.push(() => (original ? Object.defineProperty(proto, name, original) : Reflect.deleteProperty(proto, name)));
}

beforeEach(() => {
  width = 900;
  titleWidth = 300;
  secondaryWidth = 260;
  vi.stubGlobal("ResizeObserver", class { constructor(cb: () => void) { observer = cb; } observe() {} disconnect() {} });
  define(HTMLElement.prototype, "clientWidth", (el) => (el.tagName === "HEADER" ? width : el.tagName === "H1" ? titleWidth : 0));
  define(HTMLElement.prototype, "scrollWidth", (el) => (el.tagName === "H1" ? 400 : 0));
  define(HTMLElement.prototype, "offsetWidth", (el) => (el.classList.contains("ac-pageheader-secondary") && el.closest("[data-collapsed='true']") === null ? secondaryWidth : 0));
});
afterEach(() => {
  cleanup();
  restore.forEach((r) => r());
  restore = [];
  vi.unstubAllGlobals();
});

const actions = [{ id: "a", label: "Export as a very long English label", onSelect: () => undefined }];
const header = (c: HTMLElement) => c.querySelector("header")!;

describe("PageHeader 측정 기반 접기", () => {
  it("제목에 120px 이상 남으면 접지 않는다", () => {
    const { container } = render(<PageHeader title="A title" secondaryActions={actions} />);
    expect(header(container).getAttribute("data-collapsed")).toBeNull();
  });

  it("보조 액션 때문에 제목이 120px보다 좁아지면 more 메뉴로 접고, 접을 때 잰 폭만큼 넓어지면 다시 편다", () => {
    titleWidth = 80;
    const { container } = render(<PageHeader title="A long page title" secondaryActions={actions} />);
    expect(header(container).getAttribute("data-collapsed")).toBe("true");
    width = 1000; // 접은 폭(900) + 보조 액션 폭(260)에 못 미침
    act(() => observer?.());
    expect(header(container).getAttribute("data-collapsed")).toBe("true");
    titleWidth = 300;
    width = 1170;
    act(() => observer?.());
    expect(header(container).getAttribute("data-collapsed")).toBeNull();
  });

  it("보조 액션이 없으면 아무것도 하지 않는다", () => {
    titleWidth = 80;
    const { container } = render(<PageHeader title="A long page title" />);
    expect(header(container).getAttribute("data-collapsed")).toBeNull();
  });
});
