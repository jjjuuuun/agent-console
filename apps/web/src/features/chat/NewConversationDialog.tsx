import { useId, useMemo, useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import type { Conversation, GraphSummary } from "@agent-console/contracts";
import { createProjectsText, projectAbilities, statusInfo } from "@agent-console/projects";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { FixButtons } from "../../app/fix";
import { messages as appMessages } from "../../app/messages";
import { useApi } from "../../app/ApiContext";
import { useStorage } from "../../app/StorageContext";
import { formatRelative } from "../../lib/format";
import { useImeGuard } from "../../lib/ime";
import { useGraphLoginGate } from "../backendChoice";
import { DEFINITION_KINDS, ROUTE_ROLES, routePath } from "../library";
import { ProjectTargetPicker, startErrorView, targetPickerMessages as pm, useCopyDialog, useProjects, type StartErrorView, type TargetOption } from "../projects";
import { GraphIssuesPreview, ValidationChip, blocksRun, hasEntry } from "../teams";
import { chatMessages } from "./chatMessages";
import { CONVERSATION_PAGE_SIZE, chatKeys } from "./chatData";
import { LAST_GRAPH_KEY } from "./lib/drafts";
import { lastUsedByGraph } from "./lib/conversations";
import { useConversationActions } from "./useConversationActions";

const text = createProjectsText();
const t = chatMessages.newDialog;

export interface NewConversationDialogProps {
  /** 미리 고를 팀 구성 id(마지막으로 쓴 것 등) */
  preselected?: string | undefined;
  /** 대화상자가 처음 가리킬 프로젝트(없으면 현재 프로젝트) */
  initialProject?: string | undefined;
  nowMs: number;
  onClose: () => void;
  /** 대화가 만들어졌다(대화 화면으로 이동은 호출자가 한다) */
  onCreated: (conversation: Conversation) => void;
}

/**
 * 새 대화 대화상자(screen-projects §5.4): 폴더 줄 + 그 프로젝트의 구성 라디오 + 공용에서 가져오기 + 제목.
 * 대상 프로젝트는 이 대화상자 안에서만 바뀐다(시작하면 현재 프로젝트가 따라간다).
 * 열려 있을 때만 마운트한다. 프로젝트 기능이 꺼져 있으면 쓰지 않는다(호출자가 기존 팀 고르기를 쓴다).
 */
export function NewConversationDialog(props: NewConversationDialogProps) {
  const p = useProjects();
  const { rest, space } = useApi();
  const storage = useStorage();
  const actions = useConversationActions();
  const copy = useCopyDialog();
  const uid = useId();
  const ime = useImeGuard();

  const active = useMemo(() => p.views.filter((v) => v.project.archived !== true), [p.views]);
  const [projectId, setProjectId] = useState<string | null>(() => {
    const wanted = props.initialProject ?? p.current;
    return wanted !== null && wanted !== undefined && active.some((v) => v.project.id === wanted) ? wanted : (active[0]?.project.id ?? null);
  });
  const view = active.find((v) => v.project.id === projectId);
  const [picked, setPicked] = useState<string | undefined>(props.preselected);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ raw: unknown; view: StartErrorView | null } | null>(null);

  const graphs = useQuery({
    queryKey: ["list", "graphs", "space", projectId] as const,
    queryFn: () => space(projectId).listGraphs(),
    enabled: projectId !== null,
    retry: false,
  });
  // 고른 프로젝트의 최근 대화(서버가 `?project=`로 거른 첫 페이지)에서 팀 구성별 마지막 사용 시각을 구한다.
  const recent = useQuery({
    queryKey: [...chatKeys.conversations(projectId), "recent"] as const,
    queryFn: () => rest.conversationsPage({ project: projectId as string, limit: CONVERSATION_PAGE_SIZE }),
    enabled: projectId !== null,
    retry: false,
  });
  const lastUsed = useMemo(() => lastUsedByGraph(recent.data?.items ?? []), [recent.data]);

  const abilities = view === undefined ? undefined : projectAbilities(view, { recordsWritable: view.records_writable !== false });
  const startBlockRef = abilities?.start_chat.allowed === false ? abilities.start_chat.reason : null;
  const info = view === undefined ? undefined : statusInfo(view);

  // 앱 로그인(로그인 개념을 제공하는 백엔드가 있을 때만): 로그인이 필요하면 시작을 막는다.

  const graphPath = routePath(ROUTE_ROLES.graph);
  const options: TargetOption[] = useMemo(
    () =>
      (graphs.data ?? []).map((g: GraphSummary) => {
        const noEntry = hasEntry(g) === false;
        const blocked = noEntry || blocksRun(g.validation);
        const used = lastUsed.get(g.id);
        const meta = [t.nodes(g.node_count), used === undefined ? null : t.lastUsed(formatRelative(used, props.nowMs))].filter((x): x is string => x !== null).join(" · ");
        const hasIssues = g.validation != null && (blocksRun(g.validation) || (g.validation.error_count ?? 0) > 0 || (g.validation.warning_count ?? 0) > 0);
        return {
          id: g.id,
          name: g.name,
          description: g.description,
          meta,
          blocked,
          reason: hasIssues ? <ValidationChip summary={g.validation as NonNullable<GraphSummary["validation"]>} /> : noEntry ? <span>{t.noEntry}</span> : undefined,
          expanded: hasIssues ? <GraphIssuesPreview graph={g} /> : undefined,
          editHref: projectId === null ? undefined : `${graphPath}/${encodeURIComponent(g.id)}?prj=${encodeURIComponent(projectId)}`,
        };
      }),
    [graphs.data, lastUsed, props.nowMs, graphPath, projectId],
  );
  const selected = picked !== undefined && options.some((o) => o.id === picked && o.blocked !== true) ? picked : options.find((o) => o.blocked !== true)?.id;

  // 선택한 구성이 쓰는 백엔드가 로그인을 요구할 때만 시작을 막는다.
  const definition = useQuery({
    queryKey: ["definition", "graph", projectId, selected] as const,
    queryFn: () => space(projectId).getGraph(selected as string),
    enabled: projectId !== null && selected !== undefined,
    retry: false,
  });
  const { signedOut } = useGraphLoginGate(definition.data?.graph, projectId);

  const blockText = startBlockRef !== null && startBlockRef !== undefined ? text(startBlockRef) : signedOut ? pm.blocked.signedOut : selected === undefined ? pm.blocked.noConfig : null;
  const canStart = blockText === null && !busy && projectId !== null;

  const start = async (graphId = selected) => {
    if (graphId === undefined || projectId === null) return;
    setBusy(true);
    setError(null);
    try {
      const created = await actions.create(graphId, title.trim(), projectId);
      storage.set(LAST_GRAPH_KEY, graphId);
      if (projectId !== p.current) p.setCurrent(projectId);
      props.onCreated(created);
    } catch (e) {
      setError({ raw: e, view: startErrorView(e, (_kind, id) => options.find((o) => o.id === id)?.name ?? id ?? "") });
    } finally {
      setBusy(false);
    }
  };

  const importFromLibrary = (items?: { kind: string; id: string }[], runAfter?: string) => {
    if (projectId === null) return;
    copy.open({
      direction: "import",
      project: projectId,
      start: items === undefined ? "pick" : "plan",
      ...(items === undefined ? {} : { items }),
      ...(runAfter === undefined ? {} : { submitStyle: "run" as const }),
      onApplied: (o) => {
        void graphs.refetch();
        if (o.first !== null && o.first.kind === DEFINITION_KINDS.graph) setPicked(o.first.id);
        // 가져와서 실행: 요청 항목이 모두 사용할 수 있게 됐을 때만 원래 시작 요청을 다시 보낸다
        if (runAfter !== undefined && o.allOk && o.first !== null) void start(o.first.id);
      },
    });
  };

  const fix = error?.view;
  const fixButtons = (() => {
    if (fix == null || projectId === null) return null;
    switch (fix.fix) {
      case "pickProject":
        return <Button size="sm" variant="primary" onClick={() => p.setSwitcherOpen(true)}>{pm.error.pickProject}</Button>;
      case "importAndRun": {
        const n = fix.notImported;
        const items: { kind: string; id: string }[] = [{ kind: n?.kind ?? DEFINITION_KINDS.graph ?? "", id: n?.id ?? selected ?? "" }];
        return (
          <>
            <Button size="sm" variant="primary" onClick={() => importFromLibrary(items, items[0]?.id ?? "")}>{pm.error.importAndRun}</Button>
            <Button size="sm" variant="secondary" onClick={() => setError(null)}>{pm.error.dismiss}</Button>
          </>
        );
      }
      case "toLibrary":
        return <Link className="ac-btn" data-variant="secondary" data-size="sm" to={graphPath} onClick={props.onClose}>{pm.error.toLibrary}</Link>;
      case "repath":
        return <Button size="sm" variant="secondary" onClick={() => p.requestRepath(projectId)}>{pm.error.repath}</Button>;
      case "checkInHome":
        return <Button size="sm" variant="secondary" onClick={() => { props.onClose(); p.openHome(projectId); }}>{pm.error.checkInHome}</Button>;
      case "retry":
        return <Button size="sm" variant="secondary" onClick={() => void start()}>{pm.error.retry}</Button>;
      case "openSettings":
        return error?.raw !== undefined && (error.raw as { fix?: unknown }).fix != null ? (
          <FixButtons fix={(error.raw as { fix: Parameters<typeof FixButtons>[0]["fix"] }).fix} onNavigate={props.onClose} />
        ) : (
          <Link className="ac-btn" data-variant="secondary" data-size="sm" to={routePath(ROUTE_ROLES.settings)} onClick={props.onClose}>{pm.error.openSettings}</Link>
        );
      default:
        return null;
    }
  })();

  const onConfirmKey = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && canStart) void start();
  };

  return (
    <>
    <Dialog
      open
      title={pm.start.newChatTitle}
      size="md"
      onClose={props.onClose}
      actions={
        <>
          <Button onClick={props.onClose}>{appMessages.common.cancel}</Button>
          <Button
            variant="primary"
            loading={busy}
            aria-disabled={canStart ? undefined : "true"}
            title={blockText ?? undefined}
            onClick={() => canStart && void start()}
          >
            {pm.start.startChat}
          </Button>
        </>
      }
    >
      <div className="chat-picker" onKeyDown={onConfirmKey}>
        {signedOut ? <Banner tone="warning">{pm.blocked.signedOut}</Banner> : null}
        <ProjectTargetPicker
          project={view === undefined ? undefined : { id: view.project.id, name: view.project.name, dir: view.project.folder ?? "" }}
          projects={active.map((v) => ({ id: v.project.id, name: v.project.name, dir: v.project.folder ?? "" }))}
          onProjectChange={(id) => { setProjectId(id); setPicked(undefined); setError(null); }}
          switchesCurrent={projectId !== null && projectId !== p.current}
          folderProblem={info === undefined || info.plain ? (startBlockRef == null || view === undefined ? undefined : { text: text(startBlockRef), tone: "warning" }) : { text: startBlockRef != null ? text(startBlockRef) : text(info.label), tone: info.tone === "danger" ? "danger" : "warning" }}
          onRepath={projectId === null ? undefined : () => p.requestRepath(projectId)}
          options={options}
          loading={graphs.isLoading}
          error={graphs.isError}
          onRetry={() => void graphs.refetch()}
          value={selected}
          onChange={setPicked}
          onImport={() => importFromLibrary()}
          importBlockedReason={abilities?.copy_in.allowed === false && abilities.copy_in.reason !== null ? text(abilities.copy_in.reason) : undefined}
          createHref={projectId === null ? undefined : `${graphPath}?prj=${encodeURIComponent(projectId)}`}
          onNavigate={props.onClose}
          listLabel={t.teamLabel}
        >
          <div className="app-field">
            <label htmlFor={`${uid}-title`}>{pm.start.titleLabel}</label>
            <input
              id={`${uid}-title`}
              aria-describedby={`${uid}-help`}
              type="text"
              className="ac-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              {...ime.handlers}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !ime.isIme(e)) {
                  e.preventDefault();
                  if (canStart) void start();
                }
              }}
            />
            <span id={`${uid}-help`} className="app-muted">{pm.start.titleHelp}</span>
          </div>
        </ProjectTargetPicker>
        {blockText !== null && !busy ? <p className="app-muted tp-block-reason" role="status">{blockText}</p> : null}
        {error === null ? null : error.view !== null ? (
          <Banner tone={error.view.tone}>
            <span>{error.view.message}</span>
            <div className="app-fix-actions">{fixButtons}</div>
          </Banner>
        ) : (
          <Banner tone="danger">
            {describeError(error.raw, t.createFailed).message}
            <FixButtons fix={describeError(error.raw, t.createFailed).fix} onNavigate={props.onClose} />
          </Banner>
        )}
      </div>
    </Dialog>
    {copy.dialog}
    </>
  );
}
