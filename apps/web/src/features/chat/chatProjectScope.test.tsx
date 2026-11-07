import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { CurrentProjectContext } from "../../app/projectScope";
import { createFakeClients } from "../../testing/fakes";
import { useConversationDetail, useConversationProject } from "./chatData";
import { conversation } from "./testing/chatFakes";

afterEach(cleanup);

function setup(current: string | null) {
  const getConversation = vi.fn(async (id: string) => conversation({ id }));
  const conversationsPage = vi.fn(async () => ({ items: [conversation({ id: "c1", project_id: "p7" })], next_cursor: null, source: "project" }));
  const { clients } = createFakeClients({ getConversation, conversationsPage });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>
        <CurrentProjectContext.Provider value={current}>{children}</CurrentProjectContext.Provider>
      </ApiProvider>
    </QueryClientProvider>
  );
  return { getConversation, wrapper };
}

describe("대화 상세의 프로젝트 문맥 (요청 11/07)", () => {
  it("현재 프로젝트가 있으면 대화 상세 호출에 그 프로젝트를 넘긴다", async () => {
    const { getConversation, wrapper } = setup("p1");
    const { result } = renderHook(() => useConversationDetail("c1", useConversationProject("c1")), { wrapper });
    await waitFor(() => expect(result.current.data?.id).toBe("c1"));
    expect(getConversation).toHaveBeenCalledWith("c1", "p1");
  });

  it("모든 프로젝트 보기에서는 목록 항목의 project_id를 넘긴다", async () => {
    const { getConversation, wrapper } = setup(null);
    const { result } = renderHook(() => useConversationProject("c1"), { wrapper });
    await waitFor(() => expect(result.current).toBe("p7"));
    renderHook(() => useConversationDetail("c1", "p7"), { wrapper });
    await waitFor(() => expect(getConversation).toHaveBeenCalledWith("c1", "p7"));
  });
});
