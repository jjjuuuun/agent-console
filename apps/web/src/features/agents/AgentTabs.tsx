import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import type { Agent, EffectiveSettings, ResourceAttachment } from "@agent-console/contracts";
import { Banner, Button, EmptyState } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useApiQuery, useWorkspaceSettings } from "../../app/queries";
import { formatDateTime, shortId } from "../../lib/format";
import { Skeleton, useResourceList, useResourceTypes } from "../settings";
import { ATTACHMENT_MODES, toUiLayers, LayeredAttachments, libraryMessages, definitionPath, routePath, ROUTE_ROLES } from "../library";
import { attachmentErrorsAt } from "../../lib/attachmentProblems";
import { groupActivity } from "./agentLogic";
import { agentMessages as t } from "./messages";

export interface ResourcesTabProps {
  agent: Agent;
  onChange: (next: Agent) => void;
  effective: EffectiveSettings | undefined;
  /** 저장이 거부된 사유(필드 오류). `/resources/<i>/…` 경로가 첨부 줄에 표시된다 */
  errors?: readonly { path: string; message: string }[];
  disabled: boolean;
  /** 선택 팝업의 [새 리소스 만들기 →]. 생략하면 리소스 화면(`?new=1`)으로 이동한다. `null`이면 단추를 숨긴다(서랍 안처럼 화면을 떠나면 안 될 때) */
  onCreateResource?: (() => void) | null;
}

/** 에이전트 층 첨부 편집 + 공통 층 상속(읽기 전용) 표시. */
export function AgentResourcesTab({ agent, onChange, effective, disabled, errors, onCreateResource }: ResourcesTabProps) {
  const navigate = useNavigate();
  const resources = useResourceList();
  const types = useResourceTypes();
  const common = useWorkspaceSettings();
  const modes = ATTACHMENT_MODES;
  const formLayers = toUiLayers(effective);
  const own = formLayers[formLayers.length - 1] ?? { id: "layer-own", label: t.resources.layerFallback, index: 1 };
  const inherited = formLayers[0] !== undefined && formLayers.length > 1 ? formLayers[0] : undefined;
  const commonAttachments = (common.data?.value.agent_defaults?.resources ?? []) as ResourceAttachment[];
  const layers = [
    ...(inherited === undefined ? [] : [{ layer: inherited, attachments: commonAttachments, editable: false }]),
    { layer: own, attachments: (agent.resources ?? []) as ResourceAttachment[], editable: !disabled, errors: attachmentErrorsAt(errors, "/resources") },
  ];
  return (
    <div className="lib-form">
      {common.isError ? <Banner tone="warning">{t.resources.commonFailed}</Banner> : null}
      <LayeredAttachments
        layers={layers}
        resources={resources.data ?? []}
        types={types.data ?? []}
        modes={modes}
        footer={t.resources.footer}
        {...(onCreateResource === null ? {} : { onCreateResource: onCreateResource ?? (() => void navigate(`${routePath(ROUTE_ROLES.resource)}?new=1`)) })}
        onChange={(layerId, next) => {
          if (layerId !== own.id) return;
          const draft = { ...agent } as Record<string, unknown>;
          if (next.length === 0) delete draft["resources"];
          else draft["resources"] = next;
          onChange(draft as unknown as Agent);
        }}
      />
    </div>
  );
}

/** 이 에이전트를 노드로 쓰는 팀 구성 목록. */
export function AgentUsagesTab({ agentId }: { agentId: string }) {
  const usages = useApiQuery(["list", "agent-usages", agentId], (rest) => rest.listAgentUsages(agentId));
  if (usages.isLoading) return <Skeleton rows={3} />;
  if (usages.isError) return <ErrorBlock title={t.usages.failed} message={usages.error.message} retryLabel={libraryMessages.retry} onRetry={() => void usages.refetch()} />;
  const rows = usages.data ?? [];
  if (rows.length === 0) {
    return <EmptyState title={t.usages.empty} action={<Link to={routePath(ROUTE_ROLES.graph)}>{t.usages.toTeams}</Link>} />;
  }
  return (
    <table className="lib-grid" aria-label={t.tabs.usages}>
      <thead>
        <tr>
          <th>{t.usages.team}</th>
          <th>{t.usages.nodes}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const to = definitionPath(r.kind, r.id);
          return (
            <tr key={`${r.kind}:${r.id}`}>
              <td>{to === undefined ? (r.name ?? r.id) : <Link to={to}>{r.name ?? r.id}</Link>}</td>
              <td className="app-wrap">{t.usages.nodeIds(r.node_ids ?? [])}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const PAGE = 100;

/** 이 에이전트가 낸 최근 이벤트를 실행별로 묶어 보여 준다. */
export function AgentActivityTab({ agentId }: { agentId: string }) {
  const [limit, setLimit] = useState(PAGE);
  const q = useApiQuery(["list", "agent-activity", agentId, limit], (rest) => rest.getAgentActivity(agentId, limit));
  const groups = useMemo(() => groupActivity(q.data ?? []), [q.data]);
  if (q.isLoading) return <Skeleton rows={4} />;
  if (q.isError) return <ErrorBlock title={t.activity.failed} message={q.error.message} retryLabel={libraryMessages.retry} onRetry={() => void q.refetch()} />;
  if (groups.length === 0) return <p className="app-muted">{t.activity.empty}</p>;
  return (
    <>
      <table className="lib-grid" aria-label={t.tabs.activity}>
        <thead>
          <tr>
            <th>{t.activity.started}</th>
            <th>{t.activity.run}</th>
            <th>{t.activity.events}</th>
            <th>{t.activity.last}</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.runId}>
              <td title={formatDateTime(g.firstTs)}>{formatDateTime(g.firstTs)}</td>
              <td>
                <Link to={`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(g.runId)}?tab=agents&actor=${encodeURIComponent(agentId)}`} aria-label={`${t.activity.open} ${shortId(g.runId)}`}>
                  {shortId(g.runId)}
                </Link>
              </td>
              <td className="ac-num">{g.count}</td>
              <td className="lib-mono">{g.lastType}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(q.data ?? []).length >= limit ? (
        <Button onClick={() => setLimit(limit + PAGE)}>{t.activity.more}</Button>
      ) : null}
    </>
  );
}
