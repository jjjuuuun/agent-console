import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../start/useStartGuide", () => ({
  useStartGuide: () => ({
    ready: true,
    allDone: false,
    steps: [
      { id: "folder", label: "폴더", done: true },
      { id: "chat", label: "대화 시작", actionLabel: "새 대화", done: false, to: "/chat" },
    ],
  }),
}));

import { StartCard } from "./EmptyViews";

afterEach(cleanup);

describe("시작하기 카드의 대화 시작 (요청 11/07)", () => {
  it("chat 단계 버튼은 자기 자신으로 가는 링크가 아니라 새 대화 열기를 부른다", () => {
    const onNew = vi.fn();
    render(<MemoryRouter><StartCard onNew={onNew} onDismiss={() => undefined} /></MemoryRouter>);
    expect(screen.queryByRole("link", { name: "새 대화" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "새 대화" }));
    expect(onNew).toHaveBeenCalledTimes(1);
  });
});
