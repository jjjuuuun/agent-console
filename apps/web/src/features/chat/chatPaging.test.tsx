import { cleanup, renderHook, waitFor, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationSummary } from "@agent-console/contracts";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { CurrentProjectContext } from "../../app/projectScope";
import { createFakeClients } from "../../testing/fakes";
import { useConversationList } from "./chatData";
import { patchConversationCache } from "./lib/conversations";
import { conversation } from "./testing/chatFakes";

afterEach(cleanup);

describe("대화 목록 서버 페이지", () => {
  function setup() {
    const conversationsPage = vi.fn(async (p: { project?: string; cursor?: string }) => {
      if (p.project === "p2") return { items: [conversation({ id: "z1" })], next_cursor: null, source: "project" };
      return p.cursor === undefined
        ? { items: [conversation({ id: "a1" }), conversation({ id: "a2" })], next_cursor: "project.2", source: "project" }
        : { items: [conversation({ id: "a3" })], next_cursor: null, source: "project" };
    });
    const { clients } = createFakeClients({ conversationsPage });
    const queryClient = createAppQueryClient({ retry: false });
    let project: string | null = "p1";
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <ApiProvider clients={clients}>
          <CurrentProjectContext.Provider value={project}>{children}</CurrentProjectContext.Provider>
        </ApiProvider>
      </QueryClientProvider>
    );
    return { conversationsPage, wrapper, setProject: (p: string | null) => (project = p) };
  }

  it("?project=를 서버에 보내고 다음 페이지를 이어 붙인다", async () => {
    const { conversationsPage, wrapper } = setup();
    const { result } = renderHook(() => useConversationList({ archived: false }), { wrapper });
    await waitFor(() => expect(result.current.data?.map((c) => c.id)).toEqual(["a1", "a2"]));
    expect(conversationsPage.mock.calls[0]![0]).toMatchObject({ project: "p1", archived: false });
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.data?.map((c) => c.id)).toEqual(["a1", "a2", "a3"]));
    expect(conversationsPage.mock.calls[1]![0]).toMatchObject({ project: "p1", cursor: "project.2" });
  });

  it("프로젝트를 바꾸면 이어 붙인 목록을 버리고 첫 페이지부터 읽는다", async () => {
    const { conversationsPage, wrapper, setProject } = setup();
    const { result, rerender } = renderHook(() => useConversationList(), { wrapper });
    await waitFor(() => expect(result.current.data?.length).toBe(2));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.data?.length).toBe(3));
    setProject("p2");
    rerender();
    await waitFor(() => expect(result.current.data?.map((c) => c.id)).toEqual(["z1"]));
    const last = conversationsPage.mock.calls[conversationsPage.mock.calls.length - 1]![0];
    expect(last).toMatchObject({ project: "p2" });
    expect(last).not.toHaveProperty("cursor");
  });
});

describe("patchConversationCache", () => {
  const next = conversation({ id: "a2", title: "바뀜" }) as ConversationSummary;
  it("배열 목록과 페이지 목록 모두 제자리에서 바꾸고, 없으면 첫 페이지 앞에 넣는다", () => {
    expect(patchConversationCache([conversation({ id: "a2" })], next)[0]?.title).toBe("바뀜");
    const data = { pages: [{ items: [conversation({ id: "a1" })] }, { items: [conversation({ id: "a2" })] }] };
    expect(patchConversationCache(data, next).pages[1]!.items![0]!.title).toBe("바뀜");
    const fresh = patchConversationCache({ pages: [{ items: [conversation({ id: "a1" })] }] }, next);
    expect(fresh.pages[0]!.items!.map((c) => c.id)).toEqual(["a2", "a1"]);
  });
  it("모르는 모양은 그대로 둔다", () => {
    expect(patchConversationCache({ x: 1 }, next)).toEqual({ x: 1 });
  });
});
