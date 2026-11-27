import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { COLLAPSE_BELOW_PX, ModelCatalogLine } from "./ModelCatalogLine";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mountAtWidth(width: number, onCheck = vi.fn()) {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width, height: 18, top: 0, left: 0, right: width, bottom: 18, x: 0, y: 0, toJSON: () => ({}) });
  render(<ModelCatalogLine state="failed" text="실패" refreshLabel="새로 고침" onRefresh={() => undefined} checkLabel="연결 확인…" moreLabel="더 보기" onCheck={onCheck} />);
  return onCheck;
}

describe("모델 줄: 칸 폭이 280px 미만이면 [연결 확인…]을 더 보기 메뉴로 접는다", () => {
  it("280px 이상이면 단추가 그대로 보인다", () => {
    mountAtWidth(COLLAPSE_BELOW_PX);
    expect(screen.getByRole("button", { name: "연결 확인…" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull();
  });
  it("279px이면 아이콘 단추 하나로 접히고, 메뉴 항목이 같은 동작을 한다", async () => {
    const onCheck = mountAtWidth(COLLAPSE_BELOW_PX - 1);
    expect(screen.queryByRole("button", { name: "연결 확인…" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "더 보기" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "연결 확인…" }));
    expect(onCheck).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "새로 고침" })).toBeTruthy();
  });
  it("레이아웃을 읽을 수 없으면(폭 0) 접지 않는다", () => {
    mountAtWidth(0);
    expect(screen.getByRole("button", { name: "연결 확인…" })).toBeTruthy();
  });
});
