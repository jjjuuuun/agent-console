import { useCallback } from "react";
import { folderOf, withFolder } from "@agent-console/list-arrange";
import { useToast } from "@agent-console/ui";
import type { Agent } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { useInvalidateLists } from "../library";
import { loadAgent, saveAgent } from "./agentLogic";
import { agentMessages as t } from "./messages";

/** attributes가 비게 되면 원래 없던 키는 만들지 않는다. */
function withAttributes(agent: Agent, attributes: Record<string, unknown>): Agent {
  const { attributes: _drop, ...rest } = agent;
  void _drop;
  return Object.keys(attributes).length === 0 && agent.attributes === undefined ? (rest as Agent) : { ...rest, attributes };
}

export interface AgentEdits {
  /** 폴더를 옮긴다(`If-Match`로 저장, 다른 속성 보존). 성공하면 되돌리기 토스트. 실패는 오류 토스트. */
  moveToFolder: (id: string, name: string, folder: string | undefined) => Promise<boolean>;
  /** 라벨을 바꿔 저장한다. */
  saveLabels: (id: string, name: string, labels: string[]) => Promise<boolean>;
}

/** 에이전트 목록의 가벼운 편집(폴더 이동·라벨). 저장은 기존 에이전트 저장 경로(읽고 → 바꾸고 → `If-Match` 저장)다. */
export function useAgentEdits(): AgentEdits {
  const { rest } = useApi();
  const toast = useToast();
  const invalidate = useInvalidateLists();

  const edit = useCallback(
    async (id: string, change: (a: Agent) => Agent): Promise<Agent | undefined> => {
      const { value, version_hash } = await loadAgent(rest, id);
      const next = change(value);
      await saveAgent(rest, next, version_hash);
      await invalidate();
      return value;
    },
    [rest, invalidate],
  );

  const moveToFolder = useCallback(
    async (id: string, name: string, folder: string | undefined) => {
      try {
        const before = await edit(id, (a) => withAttributes(a, withFolder(a.attributes, folder)));
        const prev = folderOf(before?.attributes);
        toast({
          tone: "success",
          text: folder === undefined ? t.arrange.move.doneClear(name) : t.arrange.move.done(name, folder),
          action: {
            label: t.arrange.move.undo,
            onClick: () => {
              void edit(id, (a) => withAttributes(a, withFolder(a.attributes, prev)))
                .then(() => toast({ tone: "info", text: t.arrange.move.undone }))
                .catch((e: unknown) => toast({ tone: "danger", text: describeError(e, t.arrange.move.failed).message }));
            },
          },
        });
        return true;
      } catch (e) {
        toast({ tone: "danger", text: describeError(e, t.arrange.move.failed).message });
        return false;
      }
    },
    [edit, toast],
  );

  const saveLabels = useCallback(
    async (id: string, name: string, labels: string[]) => {
      try {
        await edit(id, (a) => {
          const { labels: _l, ...rest } = a;
          void _l;
          return (labels.length === 0 ? rest : { ...rest, labels }) as Agent;
        });
        toast({ tone: "success", text: t.arrange.labels.saved(name) });
        return true;
      } catch (e) {
        toast({ tone: "danger", text: describeError(e, t.arrange.labels.failed).message });
        return false;
      }
    },
    [edit, toast],
  );

  return { moveToFolder, saveLabels };
}
