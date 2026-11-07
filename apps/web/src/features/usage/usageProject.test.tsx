import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { CurrentProjectContext, ProjectScopeReadyContext } from "../../app/projectScope";
import { createFakeClients } from "../../testing/fakes";
import { ShortcutProvider } from "@agent-console/ui";
import { RollupPanel } from "./RollupPanel";
import { usageMessages } from "./messages";
import { UsageScreen } from "./UsageScreen";

afterEach(cleanup);

const emptyReport = { windows: [], rollups: [], generated_at: 1 };

function tree(clients: ReturnType<typeof createFakeClients>["clients"], qc: ReturnType<typeof createAppQueryClient>, project: string | null, ready = true) {
  return (
    <QueryClientProvider client={qc}>
      <ApiProvider clients={clients}>
        <ProjectScopeReadyContext.Provider value={ready}>
          <CurrentProjectContext.Provider value={project}>
            <MemoryRouter><ShortcutProvider defaults={[]}><UsageScreen /></ShortcutProvider></MemoryRouter>
          </CurrentProjectContext.Provider>
        </ProjectScopeReadyContext.Provider>
      </ApiProvider>
    </QueryClientProvider>
  );
}

describe("사용량 화면의 프로젝트 범위 (R15.3)", () => {
  it("현재 프로젝트를 질의에 싣고, 전환하면 다시 받으며, 없으면 생략한다", async () => {
    const getUsage = vi.fn(async () => emptyReport);
    const { clients } = createFakeClients({ getUsage, listUsageSources: async () => [] });
    const qc = createAppQueryClient({ retry: false });
    const view = render(tree(clients, qc, "p1"));
    await waitFor(() => expect(getUsage).toHaveBeenCalledWith(undefined, "p1"));
    view.rerender(tree(clients, qc, "p2"));
    await waitFor(() => expect(getUsage).toHaveBeenCalledWith(undefined, "p2"));
    view.rerender(tree(clients, qc, null));
    await waitFor(() => expect(getUsage.mock.calls.some((c) => c.length === 0)).toBe(true));
  });

  it("프로젝트가 정해지기 전에는 조회하지 않고, 정해지면 실제 id로 한 번만 조회한다", async () => {
    const getUsage = vi.fn(async () => emptyReport);
    const { clients } = createFakeClients({ getUsage, listUsageSources: async () => [] });
    const qc = createAppQueryClient({ retry: false });
    const view = render(tree(clients, qc, null, false));
    await new Promise((r) => setTimeout(r, 50));
    expect(getUsage).not.toHaveBeenCalled();
    view.rerender(tree(clients, qc, "p1", true));
    await waitFor(() => expect(getUsage).toHaveBeenCalledWith(undefined, "p1"));
    expect(getUsage).toHaveBeenCalledTimes(1);
  });

  it("[새로 고침]은 현재 프로젝트 키로 다시 조회한다", async () => {
    const getUsage = vi.fn(async () => emptyReport);
    const { clients } = createFakeClients({ getUsage, listUsageSources: async () => [] });
    const qc = createAppQueryClient({ retry: false });
    render(tree(clients, qc, "p1"));
    await waitFor(() => expect(getUsage).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "새로 고침" }));
    await waitFor(() => expect(getUsage).toHaveBeenCalledTimes(2));
    expect(getUsage).toHaveBeenLastCalledWith(undefined, "p1");
  });

  it("집계 패널은 주어진 제목과 범위 안내(이 프로젝트 / 계정 전체)를 보인다", () => {
    render(
      <RollupPanel
        linesByView={{}}
        views={["agent_id"]}
        view="agent_id"
        onViewChange={() => {}}
        periods={["7d"]}
        period="7d"
        onPeriodChange={() => {}}
        nameOf={(_d, v) => v ?? ""}
        title={usageMessages.rollup.titleProject}
        scopeNote={usageMessages.rollup.scopeProject}
      />,
    );
    expect(screen.getByRole("heading", { name: "이 프로젝트 토큰 집계" })).toBeTruthy();
    expect(screen.getByText(/계정 전체 기준/)).toBeTruthy();
  });
});
