import { useMemo } from "react";
import type { Graph, NodeSpec } from "@agent-console/contracts";
import { Banner, Button, ChipRow, Tabs } from "@agent-console/ui";
import { Skeleton, UserSettingsForm, useEdgeTypes, useMergeStrategies } from "../settings";
import { getContractSchema } from "@agent-console/contracts";
import { AgentSettingsForm, ATTACHMENT_MODES, Field, LayeredAttachments, routePath, ROUTE_ROLES } from "../library";
import { attachmentErrorsAt } from "../../lib/attachmentProblems";
import type { SchemaNode } from "../../lib/schemaTools";
import { DelegationOverview } from "./DelegationOverview";
import { DraftNotice } from "./DraftNotice";
import { useCanvasToast } from "./canvasToast";
import { teamMessages as t } from "./messages";
import type { TeamPanelContext } from "./panelContext";
import { nodeLabel, overviewOf, pickKeys, replaceKeys, sharedAttachments, teamSettingKeys, withSettings, withSharedAttachments } from "./teamsLogic";

const tp = t.plan;
const TEAM_KEYS = teamSettingKeys();
export const TEAM_NAME_INPUT_ID = "team-name-input";
const TEAM_LAYERS = [
  { id: "common", label: t.team.layerCommon },
  { id: "team", label: t.team.layerTeam },
];

function NodeList({ nodes, onSelect }: { nodes: readonly { node: NodeSpec; chip?: string }[]; onSelect: (id: string) => void }) {
  if (nodes.length === 0) return <span className="app-sev" data-severity="warning">▲ {t.team.none}</span>;
  return (
    <ChipRow
      ariaLabel={t.team.nodeListLabel}
      moreLabel={t.team.nodeListMore}
      chips={nodes.map(({ node, chip: c }) => ({ id: node.id, label: c ? `${nodeLabel(node)} · ${c}` : nodeLabel(node), onSelect }))}
    />
  );
}

function Overview({ ctx, onSelectNode, onSelectEdge }: { ctx: TeamPanelContext; onSelectNode: (id: string) => void; onSelectEdge?: ((edgeId: string, sourceNodeId: string) => void) | undefined }) {
  const toast = useCanvasToast();
  const g = ctx.graph;
  const overview = useMemo(() => overviewOf(g, ctx.nodeTypes, ctx.edgeTypes), [g, ctx.nodeTypes, ctx.edgeTypes]);
  const set = (patch: Partial<Graph>) => ctx.onGraphChange({ ...g, ...patch });
  const plan = ctx.plan;
  // 계획 요약의 노드 id -> 그래프의 노드(없는 id는 건너뜀). 같은 노드는 한 번만 보이고 chip은 하나라도 중간이면 중간
  const nodesFor = (items: readonly { id: string; chip?: string }[] | undefined) => {
    const byId = new Map(g.nodes?.map((n) => [n.id, n]));
    const out = new Map<string, { node: NodeSpec; chip?: string }>();
    for (const { id, chip } of items ?? []) {
      const node = byId.get(id);
      if (node === undefined) continue;
      const prev = out.get(id);
      out.set(id, { node, ...(chip === undefined ? {} : { chip: prev?.chip === t.team.interimChip ? prev.chip : chip }) });
    }
    return [...out.values()];
  };
  return (
    <div className="lib-form">
      <div className="lib-field">
        <label htmlFor={TEAM_NAME_INPUT_ID}>{t.team.name}</label>
        <input id={TEAM_NAME_INPUT_ID} className="ac-input" value={g.name} disabled={ctx.disabled} maxLength={120} onChange={(e) => set({ name: e.target.value })} />
      </div>
      <div className="lib-field">
        <span>{t.team.id}</span>
        <span className="lib-row-main">
          <span className="lib-mono">{g.id}</span>
          <button type="button" className="app-link-btn" onClick={() => void navigator.clipboard?.writeText(g.id).then(() => toast({ tone: "success", text: t.team.copied }))}>
            {t.team.copy}
          </button>
        </span>
      </div>
      <Field label={t.team.description}>
        {(a) => (
        <textarea
          {...a}
          className="ac-input"
          rows={3}
          value={g.description ?? ""}
          disabled={ctx.disabled}
          onChange={(e) => {
            const next = { ...g };
            if (e.target.value === "") delete next.description;
            else next.description = e.target.value;
            ctx.onGraphChange(next);
          }}
        />
        )}
      </Field>
      <p className="app-muted">{t.team.counts((g.nodes ?? []).length, (g.edges ?? []).length)}</p>
      <DraftNotice isDraft={plan.isDraft} updating={plan.updating} error={plan.isDraft && plan.isError && plan.data !== undefined ? plan.error : null} onRetry={plan.refetch} />
      {plan.data === undefined ? (
        plan.isError ? (
          <p role="alert" className="app-sev" data-severity="error">
            {tp.failed} <Button size="sm" onClick={plan.refetch}>{tp.retry}</Button>
          </p>
        ) : (
          <div role="status" aria-label={tp.loading}><Skeleton rows={3} /></div>
        )
      ) : (
        <>
          <section aria-label={t.team.entries}>
            <span className="lib-field-label">{t.team.entries}</span>
            <NodeList nodes={nodesFor(plan.data.entries?.map((e) => ({ id: e.node_id })))} onSelect={onSelectNode} />
          </section>
          <section aria-label={t.team.exits}>
            <span className="lib-field-label">{t.team.exits}</span>
            <NodeList nodes={nodesFor(plan.data.answers?.map((a) => ({ id: a.node_id, chip: a.final === false ? t.team.interimChip : t.team.finalChip })))} onSelect={onSelectNode} />
          </section>
          <section aria-label={t.team.asks}>
            <span className="lib-field-label">{t.team.asks}</span>
            {Object.keys(plan.data.grants ?? {}).length === 0 ? <span className="app-muted">{t.team.none}</span> : <NodeList nodes={nodesFor(Object.keys(plan.data.grants ?? {}).map((id) => ({ id })))} onSelect={onSelectNode} />}
          </section>
        </>
      )}
      <DelegationOverview graph={g} nodeTypes={ctx.nodeTypes} edgeTypes={ctx.edgeTypes} workspace={ctx.workspace} nested={ctx.nested} onSelectEdge={onSelectEdge ?? ((_edge, source) => onSelectNode(source))} onSelectNode={onSelectNode} />
      {[...overview.declared].map(([label, nodes]) => (
        <section key={label} aria-label={label}>
          <span className="lib-field-label">{label}</span>
          <NodeList nodes={nodes.map((node) => ({ node }))} onSelect={onSelectNode} />
        </section>
      ))}
    </div>
  );
}

function SettingsTab({ ctx }: { ctx: TeamPanelContext }) {
  const keys = TEAM_KEYS;
  const edgeTypes = useEdgeTypes();
  const strategies = useMergeStrategies();
  const settings = (ctx.graph.settings ?? {}) as Record<string, unknown>;
  const common = (ctx.workspace ?? {}) as Record<string, unknown>;
  // 공통 값은 "이 층 아래 층"이라 상속으로 보인다. 출처는 모두 공통 층.
  const commonAgent = (ctx.workspace?.agent_defaults ?? {}) as Record<string, unknown>;
  const commonUser = pickKeys(common, keys.user);
  const provenance = (obj: Record<string, unknown>, prefix = ""): Record<string, string> => {
    const out: Record<string, string> = {};
    const walk = (v: unknown, path: string) => {
      if (v !== null && typeof v === "object" && !Array.isArray(v)) for (const [k, x] of Object.entries(v)) walk(x, `${path}/${k}`);
      else if (path !== "") out[path] = "common";
    };
    walk(obj, prefix);
    return out;
  };
  const backendId = typeof settings["backend"] === "string" ? (settings["backend"] as string) : typeof commonAgent["backend"] === "string" ? (commonAgent["backend"] as string) : null;
  const mergeOptions = useMemo(
    () => ({
      edgeKinds: (edgeTypes.data ?? []).map((e) => ({ value: e.id, label: e.title })),
      mergeStrategies: strategies.data ?? [],
      mergeSchema: getContractSchema("AgentSettings") as SchemaNode,
    }),
    [edgeTypes.data, strategies.data],
  );
  const setAgent = (next: Record<string, unknown>) => ctx.onGraphChange(withSettings(ctx.graph, replaceKeys(ctx.graph.settings, keys.agent, next)));
  const setUser = (next: Record<string, unknown>) => ctx.onGraphChange(withSettings(ctx.graph, replaceKeys(ctx.graph.settings, keys.user, pickKeys(next, keys.user))));
  return (
    <div className="lib-form">
      <p className="app-muted lib-field-note">
        {t.team.editingLayer}: <strong>{t.team.layerTeam}</strong>
      </p>
      <section aria-label={t.team.settingsAgent}>
        <h3 className="app-block-subtitle">{t.team.settingsAgent}</h3>
        <AgentSettingsForm
          value={pickKeys(settings, keys.agent)}
          onChange={setAgent}
          layers={TEAM_LAYERS}
          editLayerId="team"
          baseValue={commonAgent}
          provenance={provenance(commonAgent)}
          backendId={backendId}
          hideKeys={["resources"]}
          disabled={ctx.disabled}
          idPrefix="team-agent-settings"
          onOpenLayer={(id) => id === "common" && ctx.navigateTo(routePath(ROUTE_ROLES.settings))}
        />
      </section>
      <section aria-label={t.team.settingsUser}>
        <h3 className="app-block-subtitle">{t.team.settingsUser}</h3>
        <UserSettingsForm
          sections={keys.user}
          value={pickKeys(settings, keys.user)}
          onChange={setUser}
          layers={TEAM_LAYERS}
          editLayerId="team"
          baseValue={commonUser}
          provenance={provenance(commonUser)}
          options={mergeOptions}
          {...(ctx.disabled ? { disabled: true } : {})}
          idPrefix="team-user-settings"
        />
      </section>
    </div>
  );
}

function SharedTab({ ctx }: { ctx: TeamPanelContext }) {
  const modes = ATTACHMENT_MODES;
  const common = (ctx.workspace?.agent_defaults?.resources ?? []) as never[];
  const layers = [
    { layer: { id: "common", label: t.team.layerCommon, index: 0 }, attachments: common, editable: false },
    { layer: { id: "team", label: t.team.layerTeam, index: 1 }, attachments: sharedAttachments(ctx.graph), editable: !ctx.disabled, errors: attachmentErrorsAt(ctx.fieldErrors, "/settings/resources") },
  ];
  return (
    <div className="lib-form">
      <p className="app-muted lib-field-note">{t.team.sharedHint}</p>
      <LayeredAttachments
        layers={layers}
        resources={ctx.resources}
        types={ctx.resourceTypes}
        modes={modes}
        onCreateResource={() => ctx.navigateTo(`${routePath(ROUTE_ROLES.resource)}?new=1`)}
        onChange={(id, next) => id === "team" && ctx.onGraphChange(withSharedAttachments(ctx.graph, next))}
      />
    </div>
  );
}

export interface TeamPanelProps {
  ctx: TeamPanelContext;
  tab: string;
  onTab: (tab: string) => void;
  onSelectNode: (id: string) => void;
  /** 반복 연결 목록을 눌렀을 때(연결 선택·이동). 없으면 출발 노드를 선택한다 */
  onSelectEdge?: ((edgeId: string, sourceNodeId: string) => void) | undefined;
  workspaceLoading: boolean;
  workspaceFailed: boolean;
}

/** 팀 패널(선택 없음): [개요][설정][공용 리소스]. 개요는 그래프에서 계산하고 설정은 팀 층 출처 표시 폼이다. */
export function TeamPanel({ ctx, tab, onTab, onSelectNode, onSelectEdge, workspaceLoading, workspaceFailed }: TeamPanelProps) {
  const items = [
    { id: "overview", label: t.team.tabs.overview, content: <Overview ctx={ctx} onSelectNode={onSelectNode} onSelectEdge={onSelectEdge} /> },
    { id: "settings", label: t.team.tabs.settings, content: workspaceLoading ? <Skeleton rows={6} /> : <SettingsTab ctx={ctx} /> },
    { id: "shared", label: t.team.tabs.shared, content: <SharedTab ctx={ctx} /> },
  ];
  return (
    <div className="team-panel-body">
      {workspaceFailed ? <Banner tone="warning">{t.team.commonFailed}</Banner> : null}
      <Tabs lazy tabs={items} activeId={["overview", "settings", "shared"].includes(tab) ? tab : "overview"} onChange={onTab} ariaLabel={t.team.tabsLabel} />
    </div>
  );
}
