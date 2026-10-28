import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FolderPicker } from "./FolderPicker";
import { MiddleEllipsisPath } from "./MiddleEllipsisPath";
import { checked, sampleEntries, sampleListing } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function violations(container: HTMLElement) {
  const r = await axe.run(container, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

describe("접근성 (axe)", () => {
  it("입력 + 확인 결과 + 열린 찾아보기 패널에 위반이 없다", async () => {
    const { container } = render(
      <FolderPicker
        id="a"
        value="/srv"
        onValueChange={() => undefined}
        check={async (r) => checked({ path: r.path })}
        list={async (r) => sampleListing(r.path, [...sampleEntries(5, r.path), { name: "x", path: "/srv/x", locked: true, project_id: "p", project_name: "n" }])}
        createFolder={async () => ({ ok: false, code: "x" })}
        roots={[]}
      />,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    fireEvent.click(screen.getByRole("button", { name: /폴더 선택…$/ }));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(await violations(container)).toEqual([]);
  });
  it("모든 버튼에 이름이 있다", async () => {
    render(
      <FolderPicker id="b" value="/n" onValueChange={() => undefined} check={async () => checked({ path: "/n", exists: false, is_dir: false, readable: false, can_create: true })} list={async (r) => sampleListing(r.path, [])} roots={[]} />,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    for (const b of screen.getAllByRole("button")) expect((b.textContent ?? "").trim() || b.getAttribute("aria-label")).toBeTruthy();
  });
});

describe("MiddleEllipsisPath", () => {
  it("측정 전에는 전체 경로(CSS 끝 줄임), 전체 경로는 숨김 텍스트와 title에 남는다", () => {
    const { container } = render(<MiddleEllipsisPath path="/home/me/work/payments/services/api" />);
    const wrap = container.querySelector(".ac-fp-path") as HTMLElement;
    expect(wrap.title).toBe("/home/me/work/payments/services/api");
    expect(wrap.querySelector(".ac-fp-sr")!.textContent).toBe("/home/me/work/payments/services/api");
    expect(wrap.querySelector("[aria-hidden='true']")!.classList.contains("ac-ellipsis")).toBe(true);
  });
  it("ResizeObserver가 폭을 알려 주면 가운데를 줄인다(1칸 7.5px)", () => {
    let cb: ResizeObserverCallback = () => undefined;
    vi.stubGlobal("ResizeObserver", class { constructor(c: ResizeObserverCallback) { cb = c; } observe() { /* noop */ } disconnect() { /* noop */ } unobserve() { /* noop */ } });
    const { container } = render(<MiddleEllipsisPath path="/home/me/work/payments/services/api" />);
    const wrap = container.querySelector(".ac-fp-path") as HTMLElement;
    act(() => cb([{ contentRect: { width: 210 } } as ResizeObserverEntry], {} as ResizeObserver));
    // floor(210/7.5)-1 = 27칸
    expect(wrap.querySelector("[aria-hidden='true']")!.textContent).toBe("/home/me/work…/services/api");
    expect(wrap.querySelector(".ac-fp-sr")!.textContent).toBe("/home/me/work/payments/services/api");
  });
});
