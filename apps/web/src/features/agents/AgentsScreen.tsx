import { useState } from "react";
import type { Agent } from "@agent-console/contracts";
import { useNavigate, useParams } from "react-router";
import { EmptyState, Icon, PageHeader } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { messages as m } from "../../app/messages";
import { useRegisterCommands } from "../../shell/commands";
import { useAgentList, useInvalidateLists, NewDefinitionDialog, DEFINITION_KINDS, type DetailRequest } from "../library";
import { useNewScope, useScopedList } from "../projects";
import { useApi } from "../../app/ApiContext";
import { AgentDetail } from "./AgentDetail";
import { AgentList } from "./AgentList";
import { agentMessages as t } from "./messages";
const scopeOfAgent = (a: Agent) => a.project;
const idOfAgent = (a: Agent) => a.id;
const nameOfAgent = (a: Agent) => a.name;

export interface AgentsScreenProps {
  /** 이 화면의 경로(라우트 설정 데이터). 상세는 `{basePath}/{id}` */
  basePath: string;
}

/** 에이전트 화면(`/agents`, `/agents/:id`): 목록 + 상세. 목록 선택은 URL이다. */
export function AgentsScreen({ basePath }: AgentsScreenProps) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { rest } = useApi();
  const agents = useAgentList();
  const invalidate = useInvalidateLists();
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [request, setRequest] = useState<DetailRequest | undefined>(undefined);
  const scoped = useScopedList(agents.data, { scopeOf: scopeOfAgent, kind: DEFINITION_KINDS.agent, idOf: idOfAgent, nameOf: nameOfAgent });

  useRegisterCommands([{ id: "agents.new", titleKey: "palette.actions.libAgentNew", run: () => { setError(null); setCreating(true); } }]);
  const go = (agentId: string) => void navigate(`${basePath}/${encodeURIComponent(agentId)}`);
  const existing = new Set((agents.data ?? []).map((a) => a.id));
  const ask = (target: string, action: DetailRequest["action"]) => {
    setRequest({ id: target, action, token: (request?.token ?? 0) + 1 });
    if (target !== id) go(target);
  };

  const create = async (v: { name: string; id: string; description: string }, role: string, scope: { project?: string }) => {
    setBusy(true);
    setError(null);
    try {
      await rest.createAgent({ id: v.id, name: v.name, ...(role.trim() ? { role: role.trim() } : {}), ...(v.description ? { description: v.description } : {}), ...scope });
      await invalidate();
      setCreating(false);
      go(v.id);
    } catch (e) {
      setError(describeError(e, t.create.failed).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-screen-frame" data-screen="agents">
      <PageHeader title={m.nav.agents} />
      <div className="lib-split">
        <AgentList
          agents={scoped.items}
          scopeBar={scoped.parts.filter}
          selectTool={scoped.parts.select}
          rowExtra={scoped.rowExtra}
          loading={agents.isLoading}
          error={agents.isError ? agents.error : null}
          onRetry={() => void agents.refetch()}
          selectedId={id}
          onSelect={(target) => { if (!scoped.intercept(target)) go(target); }}
          onNew={() => { setError(null); setCreating(true); }}
          onRename={(target) => ask(target, "rename")}
          onDelete={(target) => ask(target, "delete")}
        />
        <div className="lib-split-detail">
          {id === undefined ? (
            <EmptyState icon={<Icon name="agents" size={24} />} title={t.pick.title} description={t.pick.body} />
          ) : (
            <AgentDetail key={id} id={id} basePath={basePath} {...(request?.id === id ? { request } : {})} />
          )}
        </div>
      </div>
      {creating ? <CreateAgent existing={existing} busy={busy} error={error} onClose={() => setCreating(false)} onCreate={(v, role, scope) => void create(v, role, scope)} /> : null}
      {scoped.dialog}
    </div>
  );
}

function CreateAgent({ existing, busy, error, onClose, onCreate }: { existing: ReadonlySet<string>; busy: boolean; error: string | null; onClose: () => void; onCreate: (v: { name: string; id: string; description: string }, role: string, scope: { project?: string }) => void }) {
  const [role, setRole] = useState("");
  const scope = useNewScope(DEFINITION_KINDS.agent ?? "");
  return (
    <NewDefinitionDialog
      open
      title={t.create.title}
      submitLabel={t.create.submit}
      existingIds={existing}
      fallbackId={t.create.fallbackId}
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={(v) => onCreate(v, role, scope.patch)}
      extra={
        <>
          <label className="lib-field">
            <span>{t.create.role}</span>
            <input className="ac-input" value={role} onChange={(e) => setRole(e.target.value)} placeholder={t.create.roleHint} />
          </label>
          {scope.field}
        </>
      }
    />
  );
}
