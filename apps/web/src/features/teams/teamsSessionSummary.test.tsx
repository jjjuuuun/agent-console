import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { summaryFromServer } from "./sessionView";

afterEach(() => cleanup());

const row = (o: Record<string, unknown>) => ({ labels: [], version_hash: "h1", saved_at: Math.floor(Date.now() / 1000) - 120, node_count: 3, edge_count: 1, entry_labels: ["x"], ...o });

describe("팀 목록 행 세션 요약 (6R.20l)", () => {
  it("summaryFromServer: 같은 세션 수를 빼 별도 세션 수를 구한다, null이면 undefined", () => {
    expect(summaryFromServer({ nodes: 5, delegated: { same: 2, other: 9 } })).toEqual({ separate: 3, same: 2 });
    expect(summaryFromServer({ nodes: 4 })).toEqual({ separate: 4, same: 0 });
    expect(summaryFromServer(null)).toBeUndefined();
    expect(summaryFromServer(undefined)).toBeUndefined();
  });

  it("값이 있으면 행에 요약이 보이고 null이면 숨긴다", async () => {
    const { clients } = createFakeClients({
      listGraphs: vi.fn(async () => [row({ id: "a", name: "가", session_summary: { nodes: 3, delegated: { same: 1 } } }), row({ id: "b", name: "나", session_summary: null })]),
      listRuns: vi.fn(async () => []),
    });
    mountApp(clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    const rows = within(grid).getAllByRole("row");
    expect(within(rows[1]!).getByText("별도 세션 2 · 같은 세션 안 1")).toBeTruthy();
    expect(within(rows[2]!).queryByText(/별도 세션/)).toBeNull();
  });
});
