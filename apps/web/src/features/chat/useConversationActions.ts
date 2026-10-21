import { useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Conversation } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { projectBody, useProjectId } from "../../app/projectScope";
import { chatKeys } from "./chatData";

/** 대화 쓰기 동작 모음(이름 바꾸기·보관·삭제·팀 구성 전환·만들기). 성공하면 목록 캐시를 무효화한다. 실패는 호출자가 처리한다. */
export function useConversationActions() {
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const projectId = useProjectId();

  const settle = useCallback(
    (conversation?: Conversation) => {
      if (conversation) queryClient.setQueryData(chatKeys.conversation(conversation.id), conversation);
      void queryClient.invalidateQueries({ queryKey: ["list"] });
      void queryClient.invalidateQueries({ queryKey: ["chat"] });
    },
    [queryClient],
  );

  return useMemo(
    () => ({
      create: async (graphId: string, title: string): Promise<Conversation> => {
        const created = await rest.createConversation({ graph_id: graphId, ...(title === "" ? {} : { title }), ...projectBody(projectId) });
        settle(created);
        return created;
      },
      rename: async (id: string, title: string): Promise<void> => settle(await rest.updateConversation(id, { title })),
      setArchived: async (id: string, archived: boolean): Promise<void> => settle(await rest.updateConversation(id, { archived })),
      switchTeam: async (id: string, graphId: string): Promise<void> => settle(await rest.updateConversation(id, { graph_id: graphId })),
      remove: async (id: string): Promise<void> => {
        await rest.deleteConversation(id);
        queryClient.removeQueries({ queryKey: chatKeys.conversation(id) });
        settle();
      },
    }),
    [rest, queryClient, settle, projectId],
  );
}
