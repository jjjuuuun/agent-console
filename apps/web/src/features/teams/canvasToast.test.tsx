import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Graph, Issue } from "@agent-console/contracts";
import { CanvasToastProvider, CanvasToastRegion, useCanvasToast } from "./canvasToast";
import { IssuesPanel } from "./IssuesPanel";
import { VALIDATION_DEBOUNCE_MS } from "./useValidation";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function Trigger() {
  const toast = useCanvasToast();
  return (
    <>
      <button type="button" onClick={() => toast({ text: "하나", mergeKey: "k", mergeText: (n) => `${n}개 적용`, action: { label: "되돌리기", onClick: () => undefined } })}>합칠 알림</button>
      <button type="button" onClick={() => toast({ text: "다른 알림" })}>다른 알림 띄우기</button>
    </>
  );
}

function mount() {
  return render(
    <CanvasToastProvider durationMs={5000}>
      <Trigger />
      <CanvasToastRegion label="편집기 알림" />
    </CanvasToastProvider>,
  );
}

describe("캔버스 알림", () => {
  it("같은 종류는 한 개로 합치고, 다른 알림은 앞 것을 대체해 동시에 1개만 보인다", () => {
    mount();
    fireEvent.click(screen.getByText("합칠 알림"));
    fireEvent.click(screen.getByText("합칠 알림"));
    expect(screen.getAllByRole("status").filter((e) => e.classList.contains("ac-toast"))).toHaveLength(1);
    expect(screen.getByText("2개 적용")).toBeTruthy();
    fireEvent.click(screen.getByText("다른 알림 띄우기"));
    expect(screen.queryByText("2개 적용")).toBeNull();
    expect(screen.getByText("다른 알림")).toBeTruthy();
  });

  it("5초 뒤 사라진다", () => {
    vi.useFakeTimers();
    mount();
    fireEvent.click(screen.getByText("다른 알림 띄우기"));
    expect(screen.getByText("다른 알림")).toBeTruthy();
    act(() => void vi.advanceTimersByTime(5001));
    expect(screen.queryByText("다른 알림")).toBeNull();
  });
});

describe("검증 줄", () => {
  const issue: Issue = { code: "x.no_entry", severity: "error", message: "입구가 없습니다", blocks_run: true, suggestions: [{ id: "s1", label: "'안내원'을 입구로 연결", patch: [] }] } as unknown as Issue;
  const graph = { id: "g", name: "g", nodes: [], edges: [] } as unknown as Graph;
  const validation = { phase: "idle" as const, issues: [issue], validated: true };

  it("접힌 줄에 첫 오류와 주 제안 버튼이 한 줄로 보이고, 누르면 제안이 적용된다", () => {
    const apply = vi.fn();
    render(<IssuesPanel graph={graph} validation={validation} open={false} onToggle={() => undefined} onValidate={() => undefined} onFocus={() => undefined} onApplySuggestion={apply} />);
    expect(screen.getByText(/입구가 없습니다/)).toBeTruthy();
    const btn = screen.getByRole("button", { name: "'안내원'을 입구로 연결" });
    expect(btn.className).toContain("ac-ge-btn--primary");
    fireEvent.click(btn);
    expect(apply).toHaveBeenCalledWith(expect.objectContaining({ code: "x.no_entry" }), expect.objectContaining({ id: "s1" }));
  });

  it("펼친 표에는 '제안' 열 머리가 없고 행 제안은 주 버튼이다", () => {
    render(<IssuesPanel graph={graph} validation={validation} open onToggle={() => undefined} onValidate={() => undefined} onFocus={() => undefined} onApplySuggestion={() => undefined} />);
    expect(screen.queryByRole("columnheader", { name: "제안" })).toBeNull();
    expect(screen.getByRole("button", { name: "'안내원'을 입구로 연결" }).className).toContain("ac-ge-btn--primary");
  });

  it("자동 검증 디바운스는 400ms다", () => {
    expect(VALIDATION_DEBOUNCE_MS).toBe(400);
  });
});
