import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { LogEventTableHandle } from "@agent-console/log-view";
import type { LogDetailPanelHandle } from "./LogDetailPanel";
import { useDetailLink } from "./useDetailLink";

describe("useDetailLink (5R.21: 표 Enter 재입력·근거 클릭 스크롤)", () => {
  it("이미 선택된 행에 Enter를 다시 누르면 패널 탭 줄로 포커스한다", () => {
    const { result } = renderHook(() => useDetailLink("u1"));
    const focusTabs = vi.fn(() => true);
    result.current.panelRef.current = { focusTabs } as LogDetailPanelHandle;
    result.current.onActivate("u2");
    expect(focusTabs).not.toHaveBeenCalled();
    result.current.onActivate("u1");
    expect(focusTabs).toHaveBeenCalledTimes(1);
  });

  it("선택이 없거나 패널이 아직 없으면 아무 일도 없다", () => {
    const { result } = renderHook(() => useDetailLink(null));
    expect(() => result.current.onActivate("u1")).not.toThrow();
    expect(() => result.current.reveal("u1")).not.toThrow();
  });

  it("reveal은 표의 scrollToUid를 가운데 맞춤으로 부른다", () => {
    const { result } = renderHook(() => useDetailLink("u1"));
    const scrollToUid = vi.fn(() => true);
    result.current.tableRef.current = { scrollToUid, focus: () => undefined } as LogEventTableHandle;
    result.current.reveal("u9");
    expect(scrollToUid).toHaveBeenCalledWith("u9", { align: "center" });
  });
});
