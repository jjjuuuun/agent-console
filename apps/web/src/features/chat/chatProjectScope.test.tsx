import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { AdoptProjectContext, CurrentProjectContext } from "../../app/projectScope";
import { createFakeClients } from "../../testing/fakes";
import { useConversationDetail, useConversationProject, useConversationScope } from "./chatData";
import { conversation } from "./testing/chatFakes";

afterEach(cleanup);

function setup(current: string | null, locate: (id: string) => Promise<unknown> = async () => ({ project_id: null }), adopt?: (id: string) => void) {
  const getConversation = vi.fn(async (id: string) => conversation({ id }));
  // 현재 범위 목록: 프로젝트를 고르면 그 프로젝트 대화(c1), 모든 프로젝트이면 p7의 c1
  const conversationsPage = vi.fn(async (params?: { project?: string }) => ({ items: [conversation({ id: "c1", project_id: params?.project ?? "p7" })], next_cursor: null, source: "project" }));
  const locateConversation = vi.fn(locate);
  const { clients } = createFakeClients({ getConversation, conversationsPage, locateConversation });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>
        <CurrentProjectContext.Provider value={current}>
          <AdoptProjectContext.Provider value={adopt}>{children}</AdoptProjectContext.Provider>
        </CurrentProjectContext.Provider>
      </ApiProvider>
    </QueryClientProvider>
  );
  return { getConversation, locateConversation, wrapper };
}

function useScopedDetail(id: string) {
  const scope = useConversationScope(id);
  return { scope, detail: useConversationDetail(id, scope.project, scope.ready) };
}

describe("대화 상세의 프로젝트 문맥 (요청 11/07)", () => {
  it("현재 프로젝트가 있으면 대화 상세 호출에 그 프로젝트를 넘긴다", async () => {
    const { getConversation, locateConversation, wrapper } = setup("p1");
    const { result } = renderHook(() => useScopedDetail("c1"), { wrapper });
    await waitFor(() => expect(result.current.detail.data?.id).toBe("c1"));
    expect(getConversation).toHaveBeenCalledWith("c1", "p1");
    expect(locateConversation).not.toHaveBeenCalled(); // 목록에 있으면 찾지 않는다
  });

  it("모든 프로젝트 보기에서는 목록 항목의 project_id를 넘긴다", async () => {
    const { getConversation, wrapper } = setup(null);
    const { result } = renderHook(() => useConversationProject("c1"), { wrapper });
    await waitFor(() => expect(result.current).toBe("p7"));
    renderHook(() => useConversationDetail("c1", "p7"), { wrapper });
    await waitFor(() => expect(getConversation).toHaveBeenCalledWith("c1", "p7"));
  });

  it("목록에 없는 대화(주소로 바로 연 다른 프로젝트 대화)는 서버 찾기 결과로 상세를 부른다 (요청 11/07 후속)", async () => {
    let answer: (v: unknown) => void = () => undefined;
    const { getConversation, locateConversation, wrapper } = setup("p1", () => new Promise((resolve) => (answer = resolve)));
    const { result } = renderHook(() => useScopedDetail("c9"), { wrapper });
    await waitFor(() => expect(locateConversation).toHaveBeenCalledWith("c9"));
    expect(result.current.scope).toEqual({ project: "p1", ready: false }); // 찾는 중(없음 표시를 미룬다)
    answer({ project_id: "p3" });
    await waitFor(() => expect(result.current.scope).toEqual({ project: "p3", ready: true }));
    await waitFor(() => expect(getConversation).toHaveBeenLastCalledWith("c9", "p3"));
    await waitFor(() => expect(result.current.detail.data?.id).toBe("c9"));
  });

  it("찾은 프로젝트가 현재와 다르면 현재 프로젝트를 그쪽으로 한 번 바꾼다 (검증 11/08 D4)", async () => {
    const adopt = vi.fn();
    const { wrapper } = setup("p1", async () => ({ project_id: "p3" }), adopt);
    const { rerender } = renderHook(() => useScopedDetail("c9"), { wrapper });
    await waitFor(() => expect(adopt).toHaveBeenCalledWith("p3"));
    rerender();
    expect(adopt).toHaveBeenCalledTimes(1);
  });

  it("목록에 있는 대화나 같은 프로젝트면 바꾸지 않는다", async () => {
    const adopt = vi.fn();
    const { wrapper } = setup("p1", async () => ({ project_id: "p1" }), adopt);
    const { result } = renderHook(() => useScopedDetail("c9"), { wrapper });
    await waitFor(() => expect(result.current.scope.ready).toBe(true));
    expect(adopt).not.toHaveBeenCalled();
  });

  it("찾은 곳이 앱 기록(null)이면 ?project= 없이 부른다", async () => {
    const { getConversation, wrapper } = setup("p1", async () => ({ project_id: null }));
    const { result } = renderHook(() => useScopedDetail("c9"), { wrapper });
    await waitFor(() => expect(result.current.scope).toEqual({ project: null, ready: true }));
    await waitFor(() => expect(getConversation).toHaveBeenLastCalledWith("c9", null));
  });

  it("찾기가 실패하면(없음·옛 서버) 현재 프로젝트로 상세를 불러 그 결과를 보인다", async () => {
    const { getConversation, wrapper } = setup("p1", async () => {
      throw new ApiError(404, { code: "not_found", message: "없음" });
    });
    const { result } = renderHook(() => useScopedDetail("c9"), { wrapper });
    await waitFor(() => expect(result.current.scope).toEqual({ project: "p1", ready: true }));
    expect(getConversation).toHaveBeenLastCalledWith("c9", "p1");
  });
});
