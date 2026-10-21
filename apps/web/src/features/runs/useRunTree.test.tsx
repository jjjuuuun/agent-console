import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Run, RunEvent } from "@agent-console/contracts";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { createFakeClients } from "../../testing/fakes";
import { CHILD_REFRESH_DEBOUNCE_MS, CHILD_SUBSCRIBE_LIMIT, useRunTree } from "./useRunTree";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const run = (id: string, extra: Partial<Run> = {}): Run => ({ id, graph_id: "g", graph_version: "v", status: "running", input: {}, origin: "chat", created_at: 1, ...extra });

function setup(kids: Run[], opts: { onActivity?: () => void } = {}) {
  const handlers = new Map<string, (e: RunEvent) => void>();
  const unsub = vi.fn();
  const { clients } = createFakeClients({ listRuns: vi.fn(async () => kids), getRun: vi.fn(async (id: string) => ({ run: run(id), node_runs: [], last_seq: 0, children: [] })) });
  clients.ws.subscribeRun = ((id: string, h: (e: RunEvent) => void) => {
    handlers.set(id, h);
    return { topic: `run:${id}`, unsubscribe: () => unsub(id) };
  }) as never;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>{children}</ApiProvider>
    </QueryClientProvider>
  );
  const root = run("root");
  const view = renderHook(() => useRunTree(root, kids, opts.onActivity ?? (() => {})), { wrapper });
  return { handlers, unsub, ...view };
}

describe("useRunTree: 활성 자식 구독 상한", () => {
  const kids = (n: number, status: Run["status"] = "running") => Array.from({ length: n }, (_, i) => run(`k${i}`, { parent_run_id: "root", root_run_id: "root", parent_node_id: "t", status, created_at: 10 + i }));

  it("활성 자식을 상한(5)까지만 구독하고 나머지는 폴링 대상이다", async () => {
    const { result, handlers } = setup(kids(7));
    await waitFor(() => expect(result.current.active).toHaveLength(7));
    expect(result.current.subscribed).toHaveLength(CHILD_SUBSCRIBE_LIMIT);
    expect(result.current.polled).toEqual(["k5", "k6"]);
    expect([...handlers.keys()].sort()).toEqual(["k0", "k1", "k2", "k3", "k4"]);
  });

  it("끝난 자식은 구독하지 않고, 직접 자식 목록은 서버가 준 것을 쓴다", async () => {
    const { result, handlers } = setup(kids(2, "completed"));
    await waitFor(() => expect(result.current.descendants).toHaveLength(2));
    expect(handlers.size).toBe(0);
    expect(result.current.children.map((r) => r.id)).toEqual(["k0", "k1"]);
    expect(result.current.isChild).toBe(false);
  });

  it("자식 이벤트가 오면 500ms 디바운스로 한 번만 활동 콜백을 부르고, 떠나면 구독을 해제한다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onActivity = vi.fn();
    const { result, handlers, unsub, unmount } = setup(kids(2), { onActivity });
    await waitFor(() => expect(result.current.subscribed).toHaveLength(2));
    const ev = { event_id: "e", run_id: "k0", seq: 1, ts: 1, node_path: [], type: "x" } as RunEvent;
    act(() => {
      handlers.get("k0")!(ev);
      handlers.get("k1")!(ev);
      handlers.get("k0")!(ev);
    });
    expect(onActivity).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CHILD_REFRESH_DEBOUNCE_MS + 10);
    });
    expect(onActivity).toHaveBeenCalledTimes(1);
    unmount();
    expect(unsub.mock.calls.map((c) => c[0]).sort()).toEqual(["k0", "k1"]);
  });
});
