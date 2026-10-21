import { useMemo, useState } from "react";
import type { Agent, EdgeTypeDescriptor, EffectiveSettings, Graph, NodeSpec, NodeTypeDescriptor, ResourceAttachment } from "@agent-console/contracts";
import { NodeLayoutPanel, RoleToggleRow, IssueSuggestionButtons, canHaveResources, defaultMessages, getRoleToggleInfo, type NodeLayoutPanelProps, type RoleToggle } from "@agent-console/graph-editor";
import { Banner, Button, Dialog, Tabs } from "@agent-console/ui";
import { messages as appMessages } from "../../app/messages";
import { issueMessage, splitNodeIssues } from "../../lib/issues";
import { Skeleton, useDelegationStrategies } from "../settings";
import { AgentSettingsForm, ATTACHMENT_MODES, Avatar, DescriptorIcon, Field, editLayerOf, inheritedProvenance, inheritedValue, toFormLayers, toUiLayers, DEFINITION_KINDS, LayeredAttachments, layerSourcePath, routePath, ROUTE_ROLES } from "../library";
import { DelegationSettings, stringAt, delegationMessages } from "../delegation";
import { NodeConfigForm } from "./forms";
import { DraftNotice } from "./DraftNotice";
import { useDraftPreview } from "./useDraftPreview";
import { useCanvasToast } from "./canvasToast";
import { teamMessages as t } from "./messages";
import { attachmentErrorsAt } from "../../lib/attachmentProblems";
import { diffNodeLayer, nodeLayerAttachments, ownAttachments, reorderLinkEdges, replaceNode, withLinkMode, withNodeOwnAttachments } from "./nodeResources";
import type { TeamPanelContext } from "./panelContext";
import { toggleRoleOnGraph, addCounterpartAndToggle, attachResource, configText, descriptorOf, detachResource, edgesOf, freshId, incomingInvocations, issuesOfNode, nodesOf, resourceEdgeKinds, resourceLinks, resourceNodeType, sharedAttachments, strategyOfInvocation, withConfigText, withNode, withNodeConfig } from "./teamsLogic";

const TOGGLES: readonly RoleToggle[] = ["entry", "exit", "interaction"];
const HIDDEN_IN_SETTINGS: readonly string[] = ["resources"];

type NodeTab = "role" | "settings" | "resources" | "layout";

/**
 * 노드의 유효 설정. 저장 전 변경이 있으면 초안 기준으로 서버에 묻고(저장하지 않음), 아니면 저장본을 읽는다.
 * 서버가 초안 경로를 모르면 저장본으로 폴백한다(`useDraftPreview`).
 */
export function useNodeEffective(ctx: TeamPanelContext, nodeId: string, skip = false) {
  return useDraftPreview<EffectiveSettings, Graph>({
    keyBase: ["node-effective", ctx.graphId, nodeId],
    savedKeyExtra: ctx.savedVersion ?? "",
    // 중첩 노드는 에이전트용 유효 설정 계산이 없다(skip): 요청하지 않는다
    savedEnabled: !skip && ctx.savedNodeIds.has(nodeId),
    draftInput: ctx.dirty && !skip ? ctx.graph : undefined,
    loadSaved: (rest) => rest.getNodeEffectiveSettings(ctx.graphId, nodeId),
    loadDraft: (rest, graph) => rest.previewDraftEffectiveSettings({ graph, node_id: nodeId }),
  });
}

/** 노드가 정의(에이전트 등)에 묶여 실행되는가: `binds`가 있고 `executable`이 아님이 아니다. */
const isBoundExecutable = (d: NodeTypeDescriptor | undefined) => d?.binds != null && d.executable !== false;

/** 중첩 노드: `binds.kind`가 지금 편집 중인 정의 종류와 같다(종류 이름은 모르고 비교만 한다). 유효 설정 계산(A)을 쓰지 않고 일반 폼(B)으로 그린다. */
const isNestedNode = (d: NodeTypeDescriptor | undefined, currentKind: string | undefined) => d?.binds != null && currentKind !== undefined && d.binds.kind === currentKind;

function agentOf(ctx: TeamPanelContext, node: NodeSpec): Agent | undefined {
  const d = descriptorOf(node, ctx.nodeTypes);
  if (d?.binds == null || d.binds.kind !== DEFINITION_KINDS.agent) return undefined;
  const ref = node.config?.[d.binds.field];
  return typeof ref === "string" ? ctx.agents.find((a) => a.id === ref) : undefined;
}

// ---------------------------------------------------------------- 역할 탭

function RoleTab({ ctx, node }: { ctx: TeamPanelContext; node: NodeSpec }) {
  const toast = useCanvasToast();
  const d = descriptorOf(node, ctx.nodeTypes);
  const nestedCtx = ctx.nested;
  const nested = nestedCtx !== undefined && isNestedNode(d, nestedCtx.currentKind);
  const eff = useNodeEffective(ctx, node.id, nested);
  const props = ((d?.config_schema as { properties?: Record<string, unknown> } | undefined)?.properties ?? {}) as Record<string, unknown>;
  const agent = agentOf(ctx, node);
  const delegated = incomingInvocations(node.id, ctx.graph, ctx.edgeTypes).length > 0;
  const showRole = "role" in props;
  const showWhen = "delegate_when" in props && delegated;
  const toggleCtx = { nodeTypes: ctx.nodeTypes, edgeTypes: ctx.edgeTypes };
  const mine = issuesOfNode(ctx.issues, node.id, ctx.graph);
  const bindsLink = agent === undefined ? undefined : `${routePath(ROUTE_ROLES.agent)}/${encodeURIComponent(agent.id)}`;
  const layers = toFormLayers(eff.data);
  const nestedId = nested && d?.binds != null ? stringAt(node.config, `/${d.binds.field}`) : undefined;
  const nestedInfo = nestedId === undefined ? undefined : nestedCtx?.infos?.find((x) => x.id === nestedId);
  const openNested = nested && nestedId !== undefined && nestedInfo !== undefined ? nestedCtx?.open : undefined;

  const onToggle = (toggle: RoleToggle, on: boolean, options?: { kindId?: string; userNodeId?: string }) => {
    const res = toggleRoleOnGraph(ctx.graph, node.id, toggle, toggleCtx, on, options);
    if (!res.changed) {
      if (res.ambiguous) toast({ tone: "warning", text: t.node.toggleAmbiguous });
      return;
    }
    if (!on && res.removed >= 2) ctx.onUndoableChange(res.graph, t.node.toggleRemoved(res.removed));
    else ctx.onGraphChange(res.graph);
  };

  const summary = (path: string) => {
    const v = eff.data?.value as Record<string, unknown> | undefined;
    const value = v?.[path];
    const layer = layers.find((l) => l.id === eff.data?.provenance?.[`/${path}`]);
    return typeof value === "string" && value !== "" ? `${value}${layer ? ` (${layer.label})` : ""}` : undefined;
  };

  return (
    <div className="lib-form">
      <Field label={t.node.label} hint={t.node.labelMax}>
        {(a) => <input {...a} data-node-label="" className="ac-input" value={node.label ?? ""} maxLength={120} disabled={ctx.disabled} onChange={(e) => ctx.onGraphChange(withNode(ctx.graph, node.id, { label: e.target.value }))} />}
      </Field>
      {showRole ? (
        <Field label={t.node.role} hint={t.node.roleHint}>
          {(a) => <input {...a} className="ac-input" value={configText(node, "role") ?? ""} placeholder={agent?.role ?? ""} disabled={ctx.disabled} onChange={(e) => ctx.onGraphChange({ ...ctx.graph, nodes: nodesOf(ctx.graph).map((n) => (n.id === node.id ? withConfigText(n, "role", e.target.value) : n)) })} />}
        </Field>
      ) : null}
      {showWhen ? (
        <Field label={t.node.delegateWhen} hint={t.node.delegateWhenHint}>
          {(a) => <textarea {...a} className="ac-input" rows={3} value={configText(node, "delegate_when") ?? ""} placeholder={agent?.description ?? ""} disabled={ctx.disabled} onChange={(e) => ctx.onGraphChange({ ...ctx.graph, nodes: nodesOf(ctx.graph).map((n) => (n.id === node.id ? withConfigText(n, "delegate_when", e.target.value) : n)) })} />}
        </Field>
      ) : null}
      {nested && nestedId !== undefined ? (
        <section className="lib-fieldset" aria-label={t.nested.definitionInfo}>
          <span className="lib-field-label">{t.nested.definitionInfo}</span>
          <span className="lib-row-main">
            <span>{delegationMessages.nested.infoLine(nestedCtx?.kindTitle ?? d?.title ?? "", nestedInfo?.name ?? nestedId)}</span>
            {openNested === undefined ? null : (
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  openNested(nestedId);
                }}
              >
                {delegationMessages.nested.open} →
              </a>
            )}
          </span>
          {nestedInfo?.nodeCount === undefined ? null : (
            <span className="app-muted lib-field-note">{delegationMessages.nested.infoMeta(nestedInfo.nodeCount, nestedInfo.entries?.join(", ") ?? "")}</span>
          )}
        </section>
      ) : null}
      {agent !== undefined && bindsLink !== undefined ? (
        <section className="lib-fieldset" aria-label={t.node.agentInfo}>
          <span className="lib-field-label">{t.node.agentInfo}</span>
          <a href={bindsLink} onClick={(e) => { e.preventDefault(); ctx.navigateTo(bindsLink); }}>{t.node.editAgent}</a>
          <span className="app-muted lib-field-note">{[summary("backend"), summary("model")].filter(Boolean).join(" · ") || agent.name}</span>
        </section>
      ) : null}
      <section className="lib-fieldset" aria-label={t.node.quickToggles}>
        <span className="lib-field-label">{t.node.quickToggles}</span>
        <span className="app-muted lib-field-note">{t.node.toggleHelp}</span>
        {TOGGLES.map((toggle) => {
          const info = getRoleToggleInfo(node.id, toggle, ctx.graph, toggleCtx);
          if (info.kinds.length === 0 && !info.on) return null;
          return (
            <div key={toggle}>
              <RoleToggleRow info={info} label={defaultMessages.toggleLabels[toggle] ?? toggle} onToggle={(on, options) => onToggle(toggle, on, options)} />
              {info.reasonIfUnavailable === "no-counterpart" && info.kinds[0] !== undefined && !ctx.disabled ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const res = addCounterpartAndToggle(ctx.graph, node.id, toggle, info.kinds[0]!.id, toggleCtx);
                    if (res !== undefined) ctx.onUndoableChange(res.graph, t.node.toggleAddedUser);
                  }}
                >
                  {t.node.addUserAndToggle}
                </Button>
              ) : null}
            </div>
          );
        })}
      </section>
      <section aria-label={t.node.problems}>
        <span className="lib-field-label">{t.node.problems}</span>
        {mine.length === 0 ? <p className="app-muted lib-field-note">{t.node.noProblems}</p> : null}
        <ul className="team-problem-list">
          {mine.map((issue, i) => (
            <li key={`${i}:${issue.code}`} data-severity={issue.severity}>
              <span className="app-sev" data-severity={issue.severity}>{issue.severity === "error" ? "✕" : "▲"}</span> {issueMessage(issue)}
              <div>
                <IssueSuggestionButtons issue={issue} onApply={ctx.onApplySuggestion} />
                {openNested === undefined || d?.binds == null || !(issue.path ?? "").includes(`/config/${d.binds.field}`) ? null : (
                  <Button size="sm" variant="ghost" onClick={() => openNested(nestedId!)}>{t.nested.issueOpen}</Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- 설정 탭

/** 필드 경고 요약 줄: 서버가 필드(path)에 붙인 경고 개수 + 첫 경고 필드로 이동. 경고의 의미(코드)는 해석하지 않는다. */
function FieldWarningSummary({ count }: { count: number }) {
  return (
    <p className="app-sev" data-severity="warning" role="status">
      <span aria-hidden="true">▲ </span>
      {t.settings.fieldWarnings(count)}{" "}
      <button
        type="button"
        className="app-link-btn"
        onClick={(e) => {
          const form = e.currentTarget.closest(".lib-form");
          const first = form?.querySelector<HTMLElement>(".ac-sf-warning");
          if (first === null || first === undefined) return;
          first.scrollIntoView({ block: "center" });
          const field = first.parentElement?.querySelector<HTMLElement>("input, select, textarea, button");
          field?.focus();
        }}
      >
        {t.settings.goFirstWarning}
      </button>
    </p>
  );
}

function BoundSettings({ ctx, node, focusPath }: { ctx: TeamPanelContext; node: NodeSpec; focusPath?: string | null | undefined }) {
  const eff = useNodeEffective(ctx, node.id);
  const strategies = useDelegationStrategies();
  const saved = ctx.savedNodeIds.has(node.id);
  const own = (node.config?.["settings"] ?? {}) as Record<string, unknown>;
  const layers = toFormLayers(eff.data);
  const fallbackLayer = { id: "node", label: t.resources.layerNode };
  const formLayers = layers.length > 0 ? layers : [fallbackLayer];
  const editLayerId = layers.length > 0 ? (editLayerOf(eff.data) ?? fallbackLayer.id) : fallbackLayer.id;
  const effBackend = typeof eff.data?.value.backend === "string" ? eff.data.value.backend : null;
  const backendId = typeof own["backend"] === "string" ? (own["backend"] as string) : effBackend;
  const sourceByLayer = useMemo(() => new Map((eff.data?.layers ?? []).map((l) => [l.id, l.source])), [eff.data]);

  const disabledPaths = useMemo(() => {
    const incoming = incomingInvocations(node.id, ctx.graph, ctx.edgeTypes);
    const first = incoming[0];
    const strategy = first === undefined ? undefined : ctx.strategies.find((s) => s.id === strategyOfInvocation(first.edge, first.kind)) ?? strategies.data?.find((s) => s.id === strategyOfInvocation(first.edge, first.kind));
    const reason = strategy === undefined ? t.settings.inapplicableGeneric : t.settings.inapplicable(strategy.title);
    return Object.fromEntries((eff.data?.inapplicable ?? []).map((p) => [p, reason]));
  }, [eff.data, node.id, ctx.graph, ctx.edgeTypes, ctx.strategies, strategies.data]);

  const fieldWarnings = useMemo(() => Object.fromEntries((eff.data?.warnings ?? []).filter((w) => typeof w.path === "string").map((w) => [w.path as string, `${w.message} (${w.code})`])), [eff.data]);
  const mergeNotes = useMemo(() => {
    const rules = { ...(ctx.workspace?.settings_merge ?? {}), ...((ctx.graph.settings?.settings_merge ?? {}) as Record<string, string>) };
    return Object.fromEntries(Object.entries(rules).map(([path, strategy]) => [path, `${strategy}`]));
  }, [ctx.workspace, ctx.graph.settings]);

  if ((saved || eff.isDraft) && eff.isLoading) return <Skeleton rows={6} />;
  const limited = Object.keys(fieldWarnings).length;
  return (
    <div className="lib-form">
      <p className="app-muted lib-field-note">
        {t.settings.editingLayer}: <strong>{formLayers.find((l) => l.id === editLayerId)?.label ?? t.resources.layerNode}</strong> — {t.settings.nodeLayerNote}
      </p>
      <DraftNotice isDraft={eff.isDraft} updating={eff.updating} error={eff.isDraft && eff.isError ? eff.error : null} onRetry={eff.refetch} />
      {!saved && !eff.isDraft ? <Banner tone="info">{t.settings.unsavedNode}</Banner> : null}
      {!eff.isDraft && saved && eff.isError ? <Banner tone="warning">{t.settings.effectiveFailed}</Banner> : null}
      {eff.isDraft && eff.isError && eff.data === undefined ? <Banner tone="warning">{t.settings.effectiveFailed}</Banner> : null}
      {!eff.isDraft && saved && ctx.dirty ? <p className="app-muted lib-field-note">{t.settings.staleNote}</p> : null}
      {limited > 0 ? <FieldWarningSummary count={limited} /> : null}
      <AgentSettingsForm
        value={own}
        onChange={(next) => {
          const config = { ...(node.config ?? {}) };
          if (Object.keys(next).length === 0) delete config["settings"];
          else config["settings"] = next;
          ctx.onGraphChange(withNodeConfig(ctx.graph, node.id, config));
        }}
        layers={formLayers}
        editLayerId={editLayerId}
        baseValue={inheritedValue(eff.data, editLayerId)}
        provenance={inheritedProvenance(eff.data, editLayerId)}
        backendId={backendId}
        hideKeys={HIDDEN_IN_SETTINGS}
        disabled={ctx.disabled}
        idPrefix={`node-${node.id}-settings`}
        {...(focusPath ? { focusPath } : {})}
        disabledPaths={disabledPaths}
        fieldWarnings={fieldWarnings}
        mergeNotes={Object.fromEntries(Object.entries(mergeNotes).map(([k, v]) => [k, `병합: ${v}`]))}
        onOpenLayer={(layerId) => {
          const to = layerSourcePath(sourceByLayer.get(layerId));
          if (to !== undefined && layerId !== editLayerId) ctx.navigateTo(to);
        }}
      />
    </div>
  );
}

function SettingsTab({ ctx, node, focusPath }: { ctx: TeamPanelContext; node: NodeSpec; focusPath?: string | null | undefined }) {
  const d = descriptorOf(node, ctx.nodeTypes);
  if (d === undefined) return <pre className="ac-pre app-json">{JSON.stringify(node, null, 2)}</pre>;
  if (isBoundExecutable(d) && !isNestedNode(d, ctx.nested?.currentKind)) {
    return (
      <>
        <BoundSettings ctx={ctx} node={node} focusPath={focusPath} />
        <DelegationSettings node={node} graph={ctx.graph} edgeTypes={ctx.edgeTypes} strategies={ctx.strategies} onChange={(config) => ctx.onGraphChange(withNodeConfig(ctx.graph, node.id, config))} disabled={ctx.disabled} />
      </>
    );
  }
  return (
    <NodeConfigForm
      descriptor={d}
      config={(node.config ?? {}) as Record<string, unknown>}
      onChange={(config) => ctx.onGraphChange(withNodeConfig(ctx.graph, node.id, config))}
      interactionKinds={ctx.interactionKinds}
      errors={splitNodeIssues(ctx.issues as never, node.id).fieldErrors}
      disabled={ctx.disabled}
    />
  );
}

// ---------------------------------------------------------------- 리소스 탭

function ResourcesTab({ ctx, node }: { ctx: TeamPanelContext; node: NodeSpec }) {
  const toast = useCanvasToast();
  const eff = useNodeEffective(ctx, node.id);
  const modes = ATTACHMENT_MODES;
  const defaultMode = modes[0] ?? "add";
  const agent = agentOf(ctx, node);
  const links = resourceLinks(node.id, ctx.graph, ctx.nodeTypes, defaultMode);
  const own = ownAttachments(node);
  const ui = toUiLayers(eff.data);
  // 층 id는 서버 데이터(있으면), 이 탭의 구역 이름은 화면 문구("팀 공용" 등)를 쓴다
  const layer = (index: number, id: string, label: string) => ({ id: ui.length === 4 ? (ui[index]?.id ?? id) : id, label, index });
  const commonAtt = (ctx.workspace?.agent_defaults?.resources ?? []) as ResourceAttachment[];
  const teamAtt = sharedAttachments(ctx.graph);
  const agentAtt = (agent?.resources ?? []) as ResourceAttachment[];
  const nodeLayer = layer(3, "layer-3", t.resources.layerNode);
  const teamLayer = layer(1, "layer-1", t.resources.layerTeam);
  // 서버 오류 경로: 노드 설정 첨부 `/nodes/<n>/config/settings/resources/<i>/…`, 연결 첨부 `/edges/<k>/config/config_override/…`
  const nodeAttachmentErrors = (() => {
    const out: Record<number, string[]> = {};
    const nodeIndex = nodesOf(ctx.graph).findIndex((n) => n.id === node.id);
    const ownErrors = attachmentErrorsAt(ctx.fieldErrors, `/nodes/${nodeIndex}/config/settings/resources`);
    for (const [i, msgs] of Object.entries(ownErrors)) out[links.length + Number(i)] = msgs;
    const edges = edgesOf(ctx.graph);
    links.forEach((l, li) => {
      const k = edges.findIndex((e) => e.id === l.edge.id);
      const msgs = (ctx.fieldErrors ?? []).filter((e) => e.path.startsWith(`/edges/${k}/config/config_override`)).map((e) => e.message);
      if (msgs.length > 0) out[li] = msgs;
    });
    return out;
  })();
  const layers = [
    { layer: layer(0, "layer-0", t.resources.layerCommon), attachments: commonAtt, editable: false },
    { layer: teamLayer, attachments: teamAtt, editable: !ctx.disabled },
    { layer: layer(2, "layer-2", t.resources.layerAgent), attachments: agentAtt, editable: false },
    { layer: nodeLayer, attachments: nodeLayerAttachments(links, own), editable: !ctx.disabled, errors: nodeAttachmentErrors },
  ];
  const rtype = resourceNodeType(ctx.nodeTypes);

  const [choosing, setChoosing] = useState<{ attachment: ResourceAttachment; kinds: EdgeTypeDescriptor[]; picked: string } | null>(null);

  const attachWith = (att: ResourceAttachment, kind: EdgeTypeDescriptor) => {
    const res = ctx.resources.find((r) => r.id === att.ref);
    if (rtype === undefined || res === undefined) return;
    const result = attachResource(ctx.graph, node, res, rtype, kind, ctx.nodeTypes, {
      node: freshId(rtype.id, nodesOf(ctx.graph).map((n) => n.id)),
      edge: freshId("e", edgesOf(ctx.graph).map((e) => e.id)),
    });
    if (result === undefined) {
      toast({ tone: "warning", text: t.resources.noConnectKind });
      return;
    }
    ctx.onGraphChange(att.mode !== undefined && att.mode !== defaultMode ? withLinkMode(result.graph, result.edgeId, att.mode, defaultMode) : result.graph);
  };

  // 연결 종류 후보가 하나면 바로 잇고, 여럿이면 사용자가 고른다
  const addToNode = (att: ResourceAttachment) => {
    const res = ctx.resources.find((r) => r.id === att.ref);
    if (rtype === undefined || res === undefined) return;
    const kinds = resourceEdgeKinds(node, rtype, ctx.nodeTypes, ctx.edgeTypes);
    const first = kinds[0];
    if (first === undefined) {
      toast({ tone: "warning", text: t.resources.noConnectKind });
      return;
    }
    if (kinds.length === 1) attachWith(att, first);
    else setChoosing({ attachment: att, kinds, picked: first.id });
  };

  const onChange = (layerId: string, next: ResourceAttachment[]) => {
    if (layerId !== nodeLayer.id) return;
    const op = diffNodeLayer(nodeLayerAttachments(links, own), next, links);
    switch (op.kind) {
      case "add":
        addToNode(op.attachment);
        break;
      case "remove-link":
        ctx.onGraphChange(detachResource(ctx.graph, op.edgeId));
        break;
      case "remove-own":
        ctx.onGraphChange(replaceNode(ctx.graph, withNodeOwnAttachments(node, own.filter((_, i) => i !== op.index))));
        break;
      case "mode-link":
        ctx.onGraphChange(withLinkMode(ctx.graph, op.edgeId, op.mode, defaultMode));
        break;
      case "mode-own":
        ctx.onGraphChange(replaceNode(ctx.graph, withNodeOwnAttachments(node, own.map((a, i) => (i === op.index ? { ...a, mode: op.mode as ResourceAttachment["mode"] } : a)))));
        break;
      case "reorder-links":
        ctx.onGraphChange(reorderLinkEdges(ctx.graph, op.edgeIds));
        break;
      case "reorder-own":
        ctx.onGraphChange(replaceNode(ctx.graph, withNodeOwnAttachments(node, op.order.map((i) => own[i]!))));
        break;
      default:
        break;
    }
  };

  return (
    <div className="lib-form">
      {eff.isError ? <Banner tone="warning">{t.resources.loadFailed}</Banner> : null}
      <LayeredAttachments
        layers={layers}
        resources={ctx.resources}
        types={ctx.resourceTypes}
        modes={modes}
        footer={t.resources.order}
        excludeLabel={t.resources.exclude}
        onExclude={(layerId, index) => {
          const source = layers.find((l) => l.layer.id === layerId)?.attachments[index];
          if (source === undefined || own.some((a) => a.ref === source.ref && a.mode === "remove")) return;
          ctx.onGraphChange(replaceNode(ctx.graph, withNodeOwnAttachments(node, [...own, { ref: source.ref, mode: "remove" as ResourceAttachment["mode"] }])));
        }}
        onCreateResource={() => ctx.navigateTo(`${routePath(ROUTE_ROLES.resource)}?new=1`)}
        onChange={(id, next) => {
          if (id === teamLayer.id) ctx.onGraphChange(applyTeamAttachments(ctx, next));
          else onChange(id, next);
        }}
      />
      {agent !== undefined ? (
        <a href={`${routePath(ROUTE_ROLES.agent)}/${encodeURIComponent(agent.id)}`} onClick={(e) => { e.preventDefault(); ctx.navigateTo(`${routePath(ROUTE_ROLES.agent)}/${encodeURIComponent(agent.id)}`); }}>
          {t.resources.agentEdit}
        </a>
      ) : null}
      <div>
        <Button onClick={() => ctx.onPreviewBundle(node.id)}>{t.resources.preview}</Button>
      </div>
      {choosing === null ? null : (
        <Dialog
          open
          title={t.resources.chooseKindTitle(ctx.resources.find((r) => r.id === choosing.attachment.ref)?.name ?? choosing.attachment.ref)}
          onClose={() => setChoosing(null)}
          actions={
            <>
              <Button onClick={() => setChoosing(null)}>{appMessages.common.cancel}</Button>
              <Button
                variant="primary"
                onClick={() => {
                  const kind = choosing.kinds.find((k) => k.id === choosing.picked);
                  setChoosing(null);
                  if (kind !== undefined) attachWith(choosing.attachment, kind);
                }}
              >
                {t.resources.chooseKindSubmit}
              </Button>
            </>
          }
        >
          <fieldset className="app-fieldset">
            <legend>{t.resources.chooseKindBody}</legend>
            {choosing.kinds.map((k) => (
              <label key={k.id} className="app-check">
                <input type="radio" name="attach-kind" value={k.id} checked={choosing.picked === k.id} onChange={() => setChoosing({ ...choosing, picked: k.id })} />
                {k.title}
                {k.description ? <span className="app-muted"> {k.description}</span> : null}
              </label>
            ))}
          </fieldset>
        </Dialog>
      )}
    </div>
  );
}

function applyTeamAttachments(ctx: TeamPanelContext, next: ResourceAttachment[]) {
  const kept = { ...(ctx.graph.settings ?? {}) } as Record<string, unknown>;
  if (next.length === 0) delete kept["resources"];
  else kept["resources"] = next;
  const graph = { ...ctx.graph };
  if (Object.keys(kept).length === 0) delete graph.settings;
  else graph.settings = kept as never;
  return graph;
}

// ---------------------------------------------------------------- 패널

export interface NodePanelProps {
  ctx: TeamPanelContext;
  node: NodeSpec;
  tab: string;
  onTab: (tab: string) => void;
  /** [배치] 탭에 그릴 값(편집기가 `onLayoutPanelsChange`로 알려 준 이 노드의 값). 아직 안 왔으면 생략 */
  layout?: NodeLayoutPanelProps | undefined;
  /** [설정] 탭에서 포커스할 필드(JSON Pointer, 해결 버튼) */
  focusPath?: string | null | undefined;
}

/** 노드 패널: 탭 [역할][설정][리소스][배치]. 리소스 탭은 이 노드가 리소스를 받을 수 있을 때만(디스크립터 `connects`·`executable`로 판단). */
export function NodePanel({ ctx, node, tab, onTab, layout, focusPath }: NodePanelProps) {
  const d = descriptorOf(node, ctx.nodeTypes);
  const hasResources = canHaveResources(node, ctx.nodeTypes, ctx.edgeTypes);
  const active: NodeTab = (["role", "settings", "resources", "layout"] as const).find((x) => x === tab && (x !== "resources" || hasResources)) ?? "role";
  const items = [
    { id: "role", label: t.node.tabs.role, content: <RoleTab ctx={ctx} node={node} /> },
    { id: "settings", label: t.node.tabs.settings, content: <SettingsTab ctx={ctx} node={node} focusPath={focusPath} /> },
    ...(hasResources ? [{ id: "resources", label: t.node.tabs.resources, content: <ResourcesTab ctx={ctx} node={node} /> }] : []),
    { id: "layout", label: t.node.tabs.layout, content: layout === undefined ? <p className="app-muted lib-field-note">{t.node.layoutPending}</p> : <NodeLayoutPanel {...layout} readOnly={ctx.disabled || layout.readOnly === true} /> },
  ];
  return (
    <div className="team-panel-body">
      <header className="team-panel-head">
        {(() => {
          const bound = agentOf(ctx, node);
          return bound !== undefined ? <Avatar id={bound.id} name={bound.name} attributes={bound.attributes} size={22} /> : <DescriptorIcon hint={d?.ui_hints?.icon} title={d?.title ?? node.type} size={18} />;
        })()}
        <span className="ac-ellipsis" title={node.label ?? node.id}><strong>{node.label ?? node.id}</strong></span>
        <span className="app-muted ac-ellipsis">{d?.title ?? t.panel.unknownType(node.type)}</span>
      </header>
      {d === undefined ? <Banner tone="warning">{t.panel.unknownType(node.type)}</Banner> : null}
      <Tabs lazy tabs={items} activeId={active} onChange={onTab} ariaLabel={t.node.tabsLabel} />
    </div>
  );
}

