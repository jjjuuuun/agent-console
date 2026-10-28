import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { UsageIndicatorView, type IndicatorStatus } from "./UsageIndicatorView";
import type { IndicatorItem } from "./usageLib";

afterEach(cleanup);

const base = { fields: [], valueMode: "used", layout: "block" as const, nowMs: 0, href: "/usage", ariaLabel: "사용량", host: "sidebar-footer" };
const ratio = {
  window: "w",
  name: "현재 세션",
  observed: true,
  kind: "ratio",
  stale: false,
  reset: "none",
  used: 0.25,
  remaining: 0.75,
} as unknown as IndicatorItem;

function view(status: IndicatorStatus, items: IndicatorItem[], setupHref?: string) {
  return render(<UsageIndicatorView {...base} status={status} items={items} {...(setupHref === undefined ? {} : { setupHref })} />);
}

describe("사이드바 사용량 컨테이너(빈 상자 결함)", () => {
  it("데이터 없음: 컨테이너를 그리지 않는다", () => {
    const { container } = view("empty", []);
    expect(container.firstChild).toBeNull();
  });

  it("로딩 중: 스켈레톤 상자를 남기지 않는다", () => {
    const { container } = view("loading", []);
    expect(container.firstChild).toBeNull();
  });

  it("ready인데 보일 사용률이 없고 연결 안내도 없으면 그리지 않는다", () => {
    const { container } = view("ready", []);
    expect(container.firstChild).toBeNull();
  });

  it("미연결: 사용률 미연결 한 줄을 그리고 연결 안내로 이어진다", () => {
    view("empty", [], "/usage#setup");
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/usage#setup");
    expect(link.textContent).toContain("미연결");
  });

  it("값 있음: 제목과 값을 그린다", () => {
    view("ready", [ratio]);
    expect(screen.getByRole("link").textContent).toContain("현재 세션");
  });
});
