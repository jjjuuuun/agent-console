import { useMemo } from "react";
import type { Agent } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { useDefinitionEdits, arrangeMessages, type DefinitionEdits, type DefinitionStore } from "../library";
import { loadAgent, saveAgent } from "./agentLogic";

export type AgentEdits = DefinitionEdits;

/** 에이전트 목록의 가벼운 편집(폴더 이동·라벨). 저장은 기존 에이전트 저장 경로(읽고 → 바꾸고 → `If-Match` 저장)다. */
export function useAgentEdits(): AgentEdits {
  const { rest } = useApi();
  const store = useMemo<DefinitionStore<Agent>>(() => ({ load: (id) => loadAgent(rest, id), save: (a, hash) => saveAgent(rest, a, hash) }), [rest]);
  return useDefinitionEdits(store, arrangeMessages);
}
