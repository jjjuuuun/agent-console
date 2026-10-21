import { useMemo, useState } from "react";
import type { Agent } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { Disclosure } from "@agent-console/ui";
import { DEFINITION_KINDS, DefinitionIdField, useDefinitionId, type DefinitionId } from "../library";
import { useNewScope } from "../projects";
import { AgentEditorForm, type AgentUpdate } from "./AgentEditorForm";
import { AgentResourcesTab } from "./AgentTabs";
import { agentMessages as t } from "./messages";

/** 새 에이전트 초안 상태: 문서 + id 제안 + 프로젝트 범위. 폼(`AgentCreateForm`)과 제출 로직을 가진 호출자가 함께 쓴다. */
export interface AgentCreateDraft {
  agent: Agent;
  setAgent: (next: AgentUpdate) => void;
  id: DefinitionId;
  scope: ReturnType<typeof useNewScope>;
  /** 이름이 있고 id가 규칙에 맞는가 */
  canSubmit: boolean;
  /** 입력한 것이 있는가(닫기 전 확인에 쓴다) */
  dirty: boolean;
  /** 서버에 보낼 본문(id·범위 포함) */
  toBody: () => Agent;
}

/**
 * 새 에이전트 초안. 필드 목록은 `AgentEditorForm`(에이전트 화면과 같은 폼)이 정하고, 여기서는 id·범위만 더한다.
 * 호출자가 서랍을 열 때마다 새로 마운트한다(초안이 열 때마다 새로 시작).
 * @param existingIds 이미 있는 에이전트 id(중복 즉시 표시)
 * @param fallbackId 이름이 한글뿐일 때 쓸 기본 id
 */
export function useAgentCreateDraft(existingIds: ReadonlySet<string>, fallbackId: string): AgentCreateDraft {
  const [agent, setAgentState] = useState<Agent>({ id: "", name: "" } as Agent);
  const id = useDefinitionId(agent.name, existingIds, fallbackId);
  const scope = useNewScope(DEFINITION_KINDS.agent ?? "");
  const setAgent = (next: AgentUpdate) => setAgentState((cur) => (typeof next === "function" ? next(cur) : next));
  return useMemo(
    () => ({
      agent,
      setAgent,
      id,
      scope,
      canSubmit: agent.name.trim() !== "" && !id.invalid,
      dirty: agent.name !== "" || Object.keys(agent).some((k) => k !== "id" && k !== "name"),
      toBody: () => ({ ...agent, id: id.id, name: agent.name.trim(), ...scope.patch }) as Agent,
    }),
    [agent, id, scope],
  );
}

export interface AgentCreateFormProps {
  draft: AgentCreateDraft;
  /** 서버가 거부한 사유(필드 오류) */
  errors?: FormError[];
  disabled?: boolean;
}

/** 새 에이전트 전체 폼: 에이전트 화면과 같은 `AgentEditorForm` + id + 프로젝트 범위 + 리소스 연결. */
export function AgentCreateForm({ draft, errors = [], disabled = false }: AgentCreateFormProps) {
  return (
    <div className="lib-form">
      <AgentEditorForm
        mode="create"
        agent={draft.agent}
        onChange={draft.setAgent}
        errors={errors}
        disabled={disabled}
        afterName={<DefinitionIdField id={draft.id.id} problem={draft.id.problem} onChange={draft.id.setId} />}
        identityExtra={draft.scope.field}
      />
      <Disclosure summary={t.create.resourcesTitle}>
        <AgentResourcesTab agent={draft.agent} onChange={(next) => draft.setAgent(next)} effective={undefined} errors={errors} disabled={disabled} onCreateResource={null} />
      </Disclosure>
    </div>
  );
}
