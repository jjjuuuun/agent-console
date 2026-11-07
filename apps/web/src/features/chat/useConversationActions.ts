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
      if (conversation) queryClient.setQueryData(chatKeys.conversation(conversation.id, conversation.project_id ?? null), conversation);
      void queryClient.invalidateQueries({ queryKey: ["list"] });
      void queryClient.invalidateQueries({ queryKey: ["chat"] });
    },
    [queryClient],
  );

  return useMemo(
    () => ({
      /** @param project 대화상자에서 고른 프로젝트(생략하면 현재 프로젝트) */
      create: async (graphId: string, title: string, project?: string | null): Promise<Conversation> => {
        const created = await rest.createConversation({ graph_id: graphId, ...(title === "" ? {} : { title }), ...projectBody(project === undefined ? projectId : project) });
        settle(created);
        return created;
      },
      /** 아래 `project`는 대화가 있는 프로젝트(기록 DB). 서버가 `?project=`를 요구한다. */
      rename: async (id: string, title: string, project?: string | null): Promise<void> => settle(await rest.updateConversation(id, { title }, project)),
      setArchived: async (id: string, archived: boolean, project?: string | null): Promise<void> => settle(await rest.updateConversation(id, { archived }, project)),
      switchTeam: async (id: string, graphId: string, project?: string | null): Promise<void> => settle(await rest.updateConversation(id, { graph_id: graphId }, project)),
      remove: async (id: string, project?: string | null): Promise<void> => {
        await rest.deleteConversation(id, project);
        queryClient.removeQueries({ queryKey: chatKeys.conversation(id) });
        settle();
      },
    }),
    [rest, queryClient, settle, projectId],
  );
}
