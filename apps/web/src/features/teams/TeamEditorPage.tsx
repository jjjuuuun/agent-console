import { useMoveIssueToShared, useProjectScopeFilter } from "../projects";
import { flashElement, useFixTarget } from "../../app/fix";
import { newAttachment } from "../../lib/serialize";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { Graph, Issue, IssueSuggestion, NodeSpec } from "@agent-console/contracts";
import { GraphEditor, MultiLayoutPanel, canHaveResources, createElkEngine, withoutEdges, type DefinitionItem, type GraphEditorHandle, type LayoutPanels, type Selection } from "@agent-console/graph-editor";
import { Banner, Button, ConfirmDialog, Dialog, PageHeader, StatusChip, useShortcuts } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { HintBanner } from "../../app/hints";
import { useStorage } from "../../app/StorageContext";
import { messages as m } from "../../app/messages";
import { useApiQuery, useWorkspaceSettings } from "../../app/queries";
import { ConflictBanner } from "../../definition/ConflictBanner";
import { SaveStatus } from "../../definition/SaveStatus";
import { UnsavedGuard } from "../../definition/unsaved";
import { useDefinitionEditor } from "../../definition/useDefinitionEditor";
import { formatRelative } from "../../lib/format";
import { useNow } from "../../app/useNow";
import { useRegisterCommands } from "../../shell/commands";
import { usePageTitle } from "../../shell/titles";
import { Skeleton, useBackends, useEdgeTypes, useDelegationStrategies, useResourceList, useResourceTypes } from "../settings";
import { ActionMenu, nodeAvatarsOf, useAgentList, useGraphList, useInteractionKinds, useInvalidateLists, useNodeTypes, DeleteDialog, DEFINITION_KINDS, definitionKey, definitionPath, NewDefinitionDialog, libraryMessages as lm, modeLabel, routePath, ROUTE_ROLES, ResourcePicker, useRouteOn, useRoutesOn } from "../library";
import { useProjects, ProjectTag } from "../projects";
import { ConnectedBackendChooserCard, precheckBackends, useSaveDefaultBackend, type UnresolvedBackend } from "../backendChoice";
import { DEFAULT_TEAM_CONVENTIONS, retryFocus } from "../delegation";
import { useTeamPlan } from "./useTeamPlan";
import { useDelegationProps } from "./useDelegationProps";
import { TeamBreadcrumb } from "./TeamBreadcrumb";
import { openedFromState, parentState, readOpenedFrom } from "./openedFrom";
import { BundlePreviewDialog } from "./BundlePreviewDialog";
import { EdgePanel } from "./EdgePanel";
import { IssuesPanel } from "./IssuesPanel";
import { NodePanel } from "./NodePanel";
import { DuplicateTeamDialog, useStartChat } from "./TeamDialogs";
import { useExportAction, exportMessages } from "../exports";
import { DefinitionVersionsTab, versionMessages } from "../versions";
import { TEAM_NAME_INPUT_ID, TeamPanel } from "./TeamPanel";
import { loadGraph, saveGraph } from "./graphIo";
import { teamMessages as t } from "./messages";
import type { TeamPanelContext } from "./panelContext";
import { blockingIssues, definitionKindTitles, edgesOf, nodeLabel, entrySourceNodeTypes, toggleRoleOnGraph, nodesOf, overviewOf, sharedAttachments, usageCounts, withSharedAttachments, type IssueTarget } from "./teamsLogic";
import { useValidation } from "./useValidation";
import { CanvasToastProvider, CanvasToastRegion, useCanvasToast } from "./canvasToast";
import { AddControl, type AddView } from "./AddControl";
import { buildAddMenu } from "./addMenu";
import { CREATABLE_KINDS, CreateDefinitionDrawer, type CreatedDefinition } from "./CreateDefinitionDrawer";
import type { DefinitionPickItem } from "./DefinitionPicker";
import { HintOneLine } from "./HintOneLine";
import { attachResourceToNode } from "./nodeResources";
import "./teams.css";

const NONE: never[] = [];
/** 알림 표시 시간 = 되돌리기 가능 창(`GraphEditor.undoWindowMs`와 같은 값) */
const UNDO_WINDOW_MS = 5000;
/** 레이아웃 규칙(ux-overhaul §4.3): 캔버스는 최소 480px을 보장한다. 팔레트·우측 패널은 자리가 모자라면 오버레이가 된다 */
const CANVAS_MIN_PX = 480;
const PANEL_W_PX = 360;
const PALETTE_W_PX = 240;
const MINIMAP_KEY = "ac.teams.minimap";
const RECENT_KEY = (kind: string) => `ac.teams.recent.${kind}`;
const RECENT_MAX = 8;
const EMPTY_SET: ReadonlySet<string> = new Set();
/** 자동 배치 엔진 목록: 모듈 수준에서 한 번만 만든다(elkjs는 첫 [정리] 때 동적으로 불러온다) */
const LAYOUT_ENGINES = [createElkEngine()];
/** 한도 필드 이름: 약속(TeamConventions) 포인터의 마지막 조각 */
const limitFieldName = () => DEFAULT_TEAM_CONVENTIONS.edgeIterationLimit.split("/").pop() ?? "";

type PageTab = "edit" | "runs" | "versions";
type DialogKind = "delete" | "duplicate" | "json" | "shared-picker" | "start-save" | "save-copy" | null;

/** 팀 구성 편집기 라우트(`/teams/:id`). 목록에서 이동해도 다른 id면 새로 시작한다. */
export function TeamEditorPage({ basePath }: { basePath: string }) {
  const { id } = useParams();
  if (id === undefined) return null;
  return (
    <CanvasToastProvider durationMs={UNDO_WINDOW_MS}>
      <TeamEditor key={id} id={id} basePath={basePath} />
    </CanvasToastProvider>
  );
}

function TeamEditor({ id, basePath }: { id: string; basePath: string }) {
  const toast = useCanvasToast();
  const navigate = useNavigate();
  const location = useLocation();
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const invalidateLists = useInvalidateLists();
  const now = useNow(true, 30_000);
  // 중첩 팀 [열기]로 들어왔으면 부모 정보(브레드크럼·U 키). 주소 직접 입력·새로고침이면 없다.
  const openedFrom = readOpenedFrom(location.state);
  const [nav, setNav] = useState<{ path: string; state?: unknown } | null>(null);
  const [leaving, setLeaving] = useState(false);

  const editor = useDefinitionEditor<Graph>({
    queryKey: definitionKey(DEFINITION_KINDS.graph, id),
    load: (r) => loadGraph(r, id),
    save: (r, value, hash) => saveGraph(r, value, hash),
  });
  const nodeTypes = useNodeTypes();
  const edgeTypes = useEdgeTypes();
  const agents = useAgentList();
  const resources = useResourceList();
  const resourceTypes = useResourceTypes();
  const interactionKinds = useInteractionKinds();
  const strategies = useDelegationStrategies();
  const workspace = useWorkspaceSettings();
  const graphList = useGraphList();
  const nestedRoute = useRouteOn(ROUTE_ROLES.graph);
  const runs = useApiQuery(["list", "graph-runs", id], (r) => r.listRuns({ graph_id: id, limit: 50 }), { refetchInterval: 8000, retry: false });

  const draft = editor.draft;
  // 팔레트는 이 팀의 범위(공용이면 현재 프로젝트)에 맞는 에이전트·리소스만 보인다
  const inScope = useProjectScopeFilter(draft?.project);
  const validation = useValidation(id, draft);
  const moveToShared = useMoveIssueToShared();
  usePageTitle(draft?.name ?? null);

  const [params] = useSearchParams();
  // 해결 버튼으로 열렸으면(`?section=<노드 id>&focus=<필드>`) 그 노드를 골라 [설정] 탭의 그 필드로 간다. 한 번만 적용한다.
  const fixTarget = useFixTarget();
  const [fixFocusPath, setFixFocusPath] = useState<string | null>(null);
  const [fixDone, setFixDone] = useState(false);
  const [pageTab, setPageTab] = useState<PageTab>(() => (params.get("tab") === "versions" ? "versions" : "edit"));
  const [selection, setSelection] = useState<Selection>({ nodeIds: [], edgeIds: [] });
  const [nodeTab, setNodeTab] = useState("role");
  const [teamTab, setTeamTab] = useState("overview");
  const [panelPref, setPanelPref] = useState<boolean | null>(null);
  const [forceTeam, setForceTeam] = useState(false);
  const [issuesOpen, setIssuesOpen] = useState(true);
  const [addView, setAddView] = useState<AddView>(null);
  const [creating, setCreating] = useState<string | null>(null);
  const [attachChoice, setAttachChoice] = useState<"node" | "shared">("node");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const paletteButton = useRef<HTMLButtonElement>(null);
  const [backendCard, setBackendCard] = useState<UnresolvedBackend | null>(null);
  const [backendError, setBackendError] = useState<string | undefined>(undefined);
  const [choosingBackend, setChoosingBackend] = useState(false);
  const storage = useStorage();
  const [minimap, setMinimapState] = useState(() => storage.get(MINIMAP_KEY) === "1");
  const setMinimap = (on: boolean) => {
    storage.set(MINIMAP_KEY, on ? "1" : "0");
    setMinimapState(on);
  };
  const routeOn = useRoutesOn();
  const projects = useProjects();
  const backends = useBackends();
  const saveDefaultBackend = useSaveDefaultBackend();
  // 편집 영역(.team-main) 폭: 팔레트·우측 패널을 인라인으로 둘지 오버레이로 둘지 정한다. 0 = 아직 모름(인라인으로 본다)
  const [mainWidth, setMainWidth] = useState(0);
  const mainObserver = useRef<ResizeObserver | null>(null);
  const mainRef = useCallback((el: HTMLDivElement | null) => {
    mainObserver.current?.disconnect();
    mainObserver.current = null;
    if (el === null) return;
    setMainWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setMainWidth(el.clientWidth));
    ro.observe(el);
    mainObserver.current = ro;
  }, []);
  const widthKnown = mainWidth > 0;
  const panelInline = !widthKnown || mainWidth >= CANVAS_MIN_PX + PANEL_W_PX;
  const panelOpen = panelPref ?? panelInline;
  const setPanelOpen = (open: boolean) => setPanelPref(open);
  // 우측 패널이 열려 있으면(인라인이든 오버레이든) 팔레트와 패널 중 패널이 우선하고, 자리가 모자라면 팔레트는 오버레이가 된다("동시에 둘만")
  const paletteInline = !widthKnown || mainWidth - (panelOpen ? PANEL_W_PX : 0) >= CANVAS_MIN_PX + PALETTE_W_PX;
  const [showResources, setShowResources] = useState(true);
  const [layoutPanels, setLayoutPanels] = useState<LayoutPanels | null>(null);
  const [focus, setFocus] = useState<{ nodeId: string; token: number; edgeId?: string } | undefined>(undefined);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [bundleNode, setBundleNode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const handle = useRef<GraphEditorHandle>(null);
  const fixNodeId = fixTarget.section;
  const fixFocus = fixTarget.focus;
  const draftNodes = draft?.nodes;
  // 렌더 중 상태 조정(한 번): 팀 구성을 읽은 뒤 해당 노드가 있으면 고르고 [설정] 탭으로 간다.
  if (!fixDone && fixNodeId !== null && draftNodes !== undefined) {
    setFixDone(true);
    if (draftNodes.some((n) => n.id === fixNodeId)) {
      setForceTeam(false);
      setPanelOpen(true);
      setNodeTab("settings");
      setFocus((cur) => ({ nodeId: fixNodeId, token: (cur?.token ?? 0) + 1 }));
      if (fixFocus !== null) setFixFocusPath(fixFocus);
    }
  }

  // 화면 배치의 사용자 설정 층: 팀 구성(`settings.editor`) -> 공통(`workspace.editor`). 디스크립터 힌트는 편집기가 노드·연결 종류에서 직접 읽는다
  const editorDirection = draft?.settings?.editor?.default_direction ?? workspace.data?.value.editor?.default_direction;
  const editorEdgeShape = draft?.settings?.editor?.default_edge_shape ?? workspace.data?.value.editor?.default_edge_shape;
  const layoutDefaults = useMemo(
    () => ({ ...(editorDirection ? { direction: editorDirection } : {}), ...(editorEdgeShape ? { edgeShape: editorEdgeShape } : {}) }),
    [editorDirection, editorEdgeShape],
  );

  const nodeTypeList = nodeTypes.data ?? NONE;
  const edgeTypeList = edgeTypes.data ?? NONE;
  const kindTitles = useMemo(() => definitionKindTitles(nodeTypeList), [nodeTypeList]);
  // 다른 팀 구성으로 이동(중첩 [열기]·U 키). 저장하지 않은 변경이 있으면 먼저 묻는다(저장하고 열기 / 저장 안 하고 열기 / 취소).
  const dirtyNow = editor.dirty;
  const teamTitle = draft?.name || id;
  const openNested = useMemo(() => {
    const kind = DEFINITION_KINDS.graph;
    if (!nestedRoute || kind === undefined) return undefined;
    return (childId: string) => {
      const path = definitionPath(kind, childId);
      if (path === undefined) return;
      const state = openedFromState({ definitionKind: kind, id, title: teamTitle }, openedFrom);
      if (dirtyNow) setNav({ path, state });
      else void navigate(path, { state });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- openedFrom은 location.state에서 매번 새로 읽는다(값 비교는 state 객체)
  }, [nestedRoute, id, teamTitle, dirtyNow, navigate, location.state]);
  // 결정(5.2R.7): 서버가 위치·필드 없이 보낸 해결(입구 없음 등)으로 열리면 강조할 곳이 없으므로 캔버스 전체를 잠깐 강조한다.
  const canvasRef = useRef<HTMLDivElement>(null);
  const flashCanvas = fixTarget.arrived && fixTarget.section === null && fixTarget.focus === null;
  const drawn = draft !== undefined && pageTab === "edit";
  useEffect(() => {
    const el = canvasRef.current;
    if (!flashCanvas || !drawn || el === null) return;
    return flashElement(el);
  }, [flashCanvas, drawn]);
  const cancelFocus = useRef<(() => void) | null>(null);
  useEffect(() => () => cancelFocus.current?.(), []);
  const nodeAvatars = useMemo(() => nodeAvatarsOf(draft?.nodes ?? [], nodeTypeList ?? [], agents.data ?? []), [draft, nodeTypeList, agents.data]);
  const delegation = useDelegationProps({
    graphId: id,
    graph: draft,
    nodeTypes: nodeTypeList,
    edgeTypes: edgeTypeList,
    strategies: strategies.data ?? NONE,
    workspace: workspace.data?.value,
    summaries: graphList.data,
    kindTitles,
    openNested,
    onLimitChip: (edgeId) => {
      const edge = (draft?.edges ?? []).find((e) => e.id === edgeId);
      if (edge === undefined) return;
      setForceTeam(false);
      setPanelOpen(true);
      setFocus((cur) => ({ nodeId: edge.source.node, edgeId, token: (cur?.token ?? 0) + 1 }));
      // 연결 패널이 열린 뒤 한도 필드(없으면 설정 폼 첫 입력)로 포커스
      const seg = limitFieldName();
      // 연결 선택·패널 열기·편집기의 선택 포커스가 끝난 뒤 한 번 붙인다(사용자가 다른 곳을 누르면 멈춘다)
      cancelFocus.current?.();
      cancelFocus.current = retryFocus({ find: () => document.querySelector<HTMLElement>(`[data-edge-config] [id$="_${seg}"]`) ?? document.querySelector<HTMLElement>("[data-edge-config] input, [data-edge-config] select") });
    },
  });
  const chat = useStartChat((convId) => void navigate(`${routePath(ROUTE_ROLES.conversations)}/${encodeURIComponent(convId)}`));

  const goParent = () => {
    if (openedFrom === undefined) return;
    const path = definitionPath(openedFrom.definitionKind, openedFrom.id);
    if (path === undefined) return;
    const state = parentState(openedFrom);
    if (dirtyNow) setNav({ path, ...(state === undefined ? {} : { state }) });
    else void navigate(path, state === undefined ? undefined : { state });
  };
  const confirmNav = async (saveFirst: boolean) => {
    const target = nav;
    if (target === null) return;
    setNav(null);
    if (saveFirst && !(await editor.save())) return;
    setLeaving(true);
    // 이탈 확인(UnsavedGuard)이 꺼진 렌더가 반영된 뒤에 이동한다
    setTimeout(() => void navigate(target.path, target.state === undefined ? undefined : { state: target.state }), 0);
  };
  const change = (next: Graph) => editor.setDraft(next);
  const undoable = (next: Graph, text: string) => {
    const prev = draft;
    change(next);
    if (prev !== undefined) toast({ tone: "info", text, action: { label: t.node.undo, onClick: () => editor.setDraft(prev) } });
  };

  // 입구·답변 자동 연결(설정 `editor.auto_connect_io`, 기본 켬): 팀 구성 값 -> 공통 값 순으로 읽는다
  const autoConnectIo = (draft?.settings?.editor?.auto_connect_io ?? workspace.data?.value.editor?.auto_connect_io) !== false;
  /** 자동 연결 알림: 한 줄 + [되돌리기](만든 두 연결만 제거) */
  const announceAutoConnect = (addedEdgeIds: string[]) => {
    toast({
      tone: "info",
      text: t.editor.autoConnected,
      action: { label: t.node.undo, onClick: () => editor.setDraft((cur: Graph) => withoutEdges(cur, addedEdgeIds)) },
    });
  };
  const savedNodeIds = useMemo(() => new Set(nodesOf(editor.base ?? ({} as Graph)).map((n) => n.id)), [editor.base]);
  const overview = useMemo(() => (draft === undefined ? undefined : overviewOf(draft, nodeTypeList, edgeTypeList)), [draft, nodeTypeList, edgeTypeList]);
  const blocking = blockingIssues(validation.issues);
  const plan = useTeamPlan(id, draft, editor.dirty);
  const hasEntry = plan.data !== undefined ? (plan.data.entries ?? []).length > 0 : (overview?.entries.length ?? 0) > 0;
  const saving = editor.savePhase === "saving";

  const save = () => {
    void editor.save().then((ok) => {
      if (!ok) return;
      toast({ tone: "success", text: t.editor.saved });
      void invalidateLists();
    });
  };
  /** 점검을 마친 뒤: 저장하지 않은 변경이 있으면 저장 확인, 아니면 바로 대화를 연다 */
  const proceedStart = () => {
    if (editor.dirty) setDialog("start-save");
    else void chat.start(id);
  };
  const startChat = () => {
    if (!hasEntry) return;
    if (blocking.length > 0) {
      toast({ tone: "warning", text: `${t.editor.startChatBlocked} ${blocking[0]?.message ?? ""}` });
      return;
    }
    // 실행 백엔드를 미리 점검한다(필요한 데이터를 모두 읽은 뒤에만). 비어 있으면 고르는 카드를 먼저 보이고, 고르면 이어서 시작한다(ux-overhaul §1.5-B).
    if (draft !== undefined && agents.data !== undefined && backends.data !== undefined && workspace.data !== undefined) {
      const unresolved = precheckBackends({ graph: draft, nodeTypes: nodeTypeList, agents: agents.data, defaultBackend: workspace.data.value.agent_defaults?.backend, options: backends.data });
      if (unresolved !== undefined) {
        setBackendError(undefined);
        setBackendCard(unresolved);
        return;
      }
    }
    proceedStart();
  };
  const chooseBackend = async (backendId: string) => {
    setChoosingBackend(true);
    setBackendError(undefined);
    try {
      await saveDefaultBackend(backendId);
    } catch (e) {
      setBackendError(describeError(e, t.backend.saveFailed).message);
      setChoosingBackend(false);
      return;
    }
    setChoosingBackend(false);
    setBackendCard(null);
    proceedStart();
  };
  const saveAndStart = async () => {
    setDialog(null);
    if (await editor.save()) {
      void invalidateLists();
      void chat.start(id);
    }
  };

  const exportAction = useExportAction({
    items: DEFINITION_KINDS.graph === undefined ? [] : [{ kind: DEFINITION_KINDS.graph, id }],
    dirty: editor.dirty,
    onSave: save,
  });

  useRegisterCommands([
    { id: "teams.save", titleKey: "palette.actions.libTeamSave", run: save },
    { id: "teams.validate", titleKey: "palette.actions.libTeamValidate", run: () => validation.validateNow() },
    { id: "teams.startChat", titleKey: "palette.actions.libTeamStartChat", run: startChat },
  ]);
  useShortcuts([
    { id: "teams.save", scope: "teams", keys: "Mod+S", titleKey: "shortcuts.save", modifierRequired: true, run: save },
    { id: "teams.validate", scope: "teams", keys: "F8", titleKey: "shortcuts.libValidate", run: () => validation.validateNow() },
    { id: "teams.chat", scope: "teams", keys: "Mod+Enter", titleKey: "shortcuts.libStartChat", run: startChat },
    { id: "teams.add", scope: "teams", keys: "Alt+N", titleKey: "shortcuts.libAddMenu", run: () => { if (pageTab === "edit") setAddView((v) => (v === null ? { op: "menu" } : null)); } },
    { id: "teams.issues", scope: "teams", keys: "Mod+J", titleKey: "shortcuts.libValidate", run: () => setIssuesOpen((v) => !v) },
    ...(["entry", "exit", "interaction"] as const).map((toggle, i) => ({
      id: `teams.toggle.${toggle}`,
      scope: "teams",
      keys: ["i", "o", "a"][i]!,
      titleKey: ["shortcuts.libToggleEntry", "shortcuts.libToggleExit", "shortcuts.libToggleAsk"][i]!,
      run: () => {
        if (draft === undefined || selection.nodeIds.length !== 1 || selection.edgeIds.length > 0) return;
        const res = toggleRoleOnGraph(draft, selection.nodeIds[0]!, toggle, { nodeTypes: nodeTypeList, edgeTypes: edgeTypeList });
        if (res.changed) change(res.graph);
        else if (res.ambiguous) toast({ tone: "warning", text: t.node.toggleAmbiguous });
      },
    })),
    ...(openedFrom === undefined ? [] : [{ id: "teams.up", scope: "teams", keys: "u", titleKey: "shortcuts.libOpenParent", run: goParent }]),
    {
      id: "teams.edgeEdit",
      scope: "teams",
      keys: "e",
      titleKey: "shortcuts.libEditEdge",
      run: () => {
        if (selection.edgeIds.length !== 1 || selection.nodeIds.length > 0) return;
        setForceTeam(false);
        setPanelOpen(true);
        setTimeout(() => document.querySelector<HTMLElement>("[data-edge-config] input, [data-edge-config] select, [data-edge-config] textarea, [data-edge-config] [tabindex='0']")?.focus(), 0);
      },
    },
    { id: "teams.tab1", scope: "teams", keys: "Alt+1", titleKey: "shortcuts.libPanelTab", run: () => { setNodeTab("role"); setTeamTab("overview"); } },
    { id: "teams.tab2", scope: "teams", keys: "Alt+2", titleKey: "shortcuts.libPanelTab", run: () => { setNodeTab("settings"); setTeamTab("settings"); } },
    { id: "teams.tab3", scope: "teams", keys: "Alt+3", titleKey: "shortcuts.libPanelTab", run: () => { setNodeTab("resources"); setTeamTab("shared"); } },
    { id: "teams.tab4", scope: "teams", keys: "Alt+4", titleKey: "shortcuts.libPanelTab", run: () => { setNodeTab("layout"); } },
  ]);

  if (editor.status === "loading") {
    return (
      <div className="app-screen-frame" data-screen="teams">
        <PageHeader title={t.editor.loading} />
        <div className="app-screen-body"><Skeleton rows={6} /></div>
      </div>
    );
  }
  if (editor.status === "error" || draft === undefined) {
    const notFound = editor.error instanceof ApiError && editor.error.status === 404;
    const view = describeError(editor.error, t.editor.loadFailed);
    return (
      <div className="app-screen-frame" data-screen="teams">
        <PageHeader title={m.nav.teams} />
        <div className="app-screen-body">
          <ErrorBlock
            title={notFound ? t.editor.notFound : t.editor.loadFailed}
            {...(notFound ? {} : { message: view.message, retryLabel: lm.retry, onRetry: editor.reload })}
            details={errorDetails(view)}
            detailsLabel={m.common.details}
          >
            {notFound ? <Button onClick={() => void navigate(basePath)}>{t.editor.toList}</Button> : null}
          </ErrorBlock>
        </div>
      </div>
    );
  }

  // ---- 선택 해석(편집기가 지운 노드는 선택에서 빠진 것으로 본다)
  const nodes = nodesOf(draft);
  const edges = edgesOf(draft);
  const selNode = selection.nodeIds.length === 1 && selection.edgeIds.length === 0 ? nodes.find((n) => n.id === selection.nodeIds[0]) : undefined;
  const selEdge = selection.edgeIds.length === 1 && selection.nodeIds.length === 0 ? edges.find((e) => e.id === selection.edgeIds[0]) : undefined;
  const selCount = selection.nodeIds.filter((n) => nodes.some((x) => x.id === n)).length + selection.edgeIds.filter((e) => edges.some((x) => x.id === e)).length;

  // ---- 팔레트 데이터(정의 종류 -> 항목). 종류 이름은 코드에 없다.
  const typeIconByResourceType = new Map((resourceTypes.data ?? []).map((x) => [x.id, x]));
  const counts = usageCounts(draft, nodeTypeList);
  const definitionLists: Record<string, DefinitionItem[]> = {};
  for (const nt of nodeTypeList) {
    if (nt.binds == null || definitionLists[nt.binds.kind] !== undefined) continue;
    const kind = nt.binds.kind;
    if (kind === DEFINITION_KINDS.agent) {
      definitionLists[kind] = inScope(agents.data ?? [], (a) => a.project).map((a) => ({ id: a.id, name: a.name, ...(a.role ? { description: a.role } : {}), usageCount: counts.get(`${kind}:${a.id}`) ?? 0 }));
    } else if (kind === DEFINITION_KINDS.resource) {
      definitionLists[kind] = inScope(resources.data ?? [], (r) => r.project).map((r) => {
        const type = typeIconByResourceType.get(r.type);
        return { id: r.id, name: r.name, description: [type?.title ?? r.type, r.description].filter(Boolean).join(" · "), ...(type?.ui_hints?.icon ? { iconName: type.ui_hints.icon } : {}), usageCount: counts.get(`${kind}:${r.id}`) ?? 0 };
      });
    } else if (kind === DEFINITION_KINDS.graph) {
      // 중첩 팀: 이름 오름차순, 자기 자신은 비활성(디스크립터의 binds.kind가 지금 편집 종류와 같을 때)
      definitionLists[kind] = [...(delegation.nestedList ?? [])];
    } else definitionLists[kind] = [];
  }
  const entrySourceIds = new Set(entrySourceNodeTypes(nodeTypeList, edgeTypeList).map((x) => x.id));
  const executableCount = nodes.filter((n) => !entrySourceIds.has(n.type)).length;
  const agentNodeType = nodeTypeList.find((nt) => nt.binds?.kind === DEFINITION_KINDS.agent);

  const shared = sharedAttachments(draft);
  const sharedChips = shared.map((a, i) => {
    const res = (resources.data ?? []).find((r) => r.id === a.ref);
    const type = res === undefined ? undefined : typeIconByResourceType.get(res.type);
    return { key: `${i}:${a.ref}`, title: res?.name ?? a.ref, ...(type?.ui_hints?.icon ? { iconText: type.ui_hints.icon } : {}), ...(a.mode && a.mode !== "add" ? { modeText: modeLabel(a.mode) } : {}) };
  });
  const commonCount = (workspace.data?.value.agent_defaults?.resources ?? []).length;

  const ctx: TeamPanelContext = {
    graphId: id,
    graph: draft,
    savedNodeIds,
    savedVersion: editor.versionHash,
    dirty: editor.dirty,
    nodeTypes: nodeTypeList,
    edgeTypes: edgeTypeList,
    agents: agents.data ?? [],
    resources: resources.data ?? [],
    resourceTypes: resourceTypes.data ?? [],
    interactionKinds: interactionKinds.data ?? [],
    strategies: strategies.data ?? [],
    workspace: workspace.data?.value,
    issues: validation.issues,
    plan,
    fieldErrors: editor.fieldErrors,
    disabled: false,
    onGraphChange: change,
    onUndoableChange: undoable,
    onApplySuggestion: (issue, suggestion) => applySuggestion(issue, suggestion),
    onPreviewBundle: (nodeId) => setBundleNode(nodeId),
    navigateTo: (path) => void navigate(path),
    nested: delegation.nested,
  };

  function applySuggestion(issue: Issue, suggestion: IssueSuggestion) {
    // 범위 경고의 [공용으로 옮기기]는 그래프 편집이 아니라 프로젝트 이동이다(옮긴 뒤 다시 검증)
    if (moveToShared.handles(suggestion.id)) {
      void moveToShared.run(issue).then((ok) => ok && validation.validateNow());
      return;
    }
    const prev = draft;
    if (handle.current?.applySuggestion(issue, suggestion) === true && prev !== undefined) {
      toast({ tone: "info", text: t.issues.applied, mergeKey: "apply-suggestion", mergeText: t.issues.appliedMany, action: { label: t.issues.undo, onClick: () => editor.setDraft(prev) } });
    }
  }

  const focusTarget = (target: IssueTarget) => {
    if (target.nodeId === undefined) return;
    setForceTeam(false);
    setFocus({ nodeId: target.nodeId, token: (focus?.token ?? 0) + 1 });
  };

  // ---- [+ 추가] 메뉴·정의 고르기·만들기 서랍 (ux-overhaul §6). 항목은 노드 타입 디스크립터와 켜진 정의 모듈에서 나온다.
  const defRole = (kind: string) => `definition:${kind}`;
  /** 정의 종류를 "붙이는 것"(실행되지 않는 노드 타입, 예: 리소스)으로 다루는가 */
  const isAttachKind = (kind: string) => nodeTypeList.some((nt) => nt.binds?.kind === kind && nt.executable === false);
  const nodeTypeOfKind = (kind: string) => nodeTypeList.find((nt) => nt.binds?.kind === kind && nt.executable !== false);
  const addEntries = buildAddMenu({
    nodeTypes: nodeTypeList,
    canPick: (kind) => routeOn(defRole(kind)) && definitionLists[kind] !== undefined,
    canCreate: (kind) => CREATABLE_KINDS.includes(kind) && routeOn(defRole(kind)),
    labels: { pick: t.add.pick, create: t.add.create, node: t.add.node },
  });
  /** 선택한 노드가 리소스를 가질 수 있으면 붙일 곳 후보 */
  const attachNode = selNode !== undefined && canHaveResources(selNode, nodeTypeList, edgeTypeList) ? { id: selNode.id, label: nodeLabel(selNode) } : undefined;
  const attachTarget: "node" | "shared" = attachChoice === "node" && attachNode === undefined ? "shared" : attachChoice;
  const recentOf = (kind: string): string[] => {
    try {
      const raw: unknown = JSON.parse(storage.get(RECENT_KEY(kind)) ?? "[]");
      return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
    } catch {
      return [];
    }
  };
  const remember = (kind: string, defId: string) => storage.set(RECENT_KEY(kind), JSON.stringify([defId, ...recentOf(kind).filter((x) => x !== defId)].slice(0, RECENT_MAX)));
  const scopeOfDefinition = (kind: string, defId: string): string | null | undefined =>
    kind === DEFINITION_KINDS.agent ? (agents.data ?? []).find((a) => a.id === defId)?.project : kind === DEFINITION_KINDS.resource ? (resources.data ?? []).find((r) => r.id === defId)?.project : undefined;
  const pickItemsOf = (kind: string): DefinitionPickItem[] =>
    (definitionLists[kind] ?? []).map((it) => {
      const scope = scopeOfDefinition(kind, it.id);
      const grouped = projects.enabled && projects.current !== null;
      return {
        id: it.id,
        name: it.name,
        description: it.meta ?? it.description,
        usageCount: it.usageCount,
        disabled: it.disabledReason !== undefined,
        ...(grouped ? { group: scope == null ? "shared" : scope === projects.current ? "current" : "other" } : {}),
        ...(projects.enabled && scope !== undefined ? { tag: <ProjectTag scope={scope ?? null} /> } : {}),
      };
    });
  /** 보이는 영역 중앙에 놓는다(시야 이동은 `onChange`의 add-node 처리가 한다: 큰 줌에서 카드가 잘리지 않게 맞춘다) */
  const addCentered = (typeId: string, item?: { id: string; name: string }): string | undefined => handle.current?.addNodeAtCenter(typeId, item);
  /** 만든 노드의 이름 입력으로 포커스를 옮긴다(패널이 열린 뒤) */
  const focusNodeName = () => setTimeout(() => document.querySelector<HTMLElement>("[data-node-label]")?.focus(), 80);
  /** 정의를 팀에 넣는다: 붙이는 종류(리소스)는 대상에 붙이고, 노드가 되는 종류(에이전트·중첩 팀 등)는 보이는 영역 중앙에 노드로 놓는다. */
  const applyDefinition = (kind: string, item: { id: string; name: string }, target: "node" | "shared" | "none"): "node" | "shared" | "added" | "failed" | "none" => {
    if (isAttachKind(kind)) {
      if (target === "none") return "none";
      if (target === "node" && attachNode !== undefined) {
        const next = attachResourceToNode(draft, attachNode.id, item, nodeTypeList, edgeTypeList);
        if (next === undefined) {
          toast({ tone: "warning", text: t.add.nodeLimit });
          return "failed";
        }
        change(next);
        return "node";
      }
      change(withSharedAttachments(draft, [...shared, newAttachment(item.id)]));
      return "shared";
    }
    const type = nodeTypeOfKind(kind);
    if (type === undefined) return "failed";
    return addCentered(type.id, item) === undefined ? "failed" : "added";
  };
  const pickDefinition = (kind: string, item: DefinitionPickItem) => {
    remember(kind, item.id);
    const before = draft;
    const result = applyDefinition(kind, { id: item.id, name: item.name }, attachTarget);
    setAddView(null);
    if (result === "node" && attachNode !== undefined) toast({ tone: "success", text: t.add.attachedNode(item.name, attachNode.label), action: { label: t.node.undo, onClick: () => editor.setDraft(before) } });
    else if (result === "shared") toast({ tone: "success", text: t.add.attachedTeam(item.name), action: { label: t.node.undo, onClick: () => editor.setDraft(before) } });
  };
  const pickerPropsOf = (kind: string) => {
    const attach = isAttachKind(kind);
    return {
      label: kindTitles[kind] ?? kind,
      items: pickItemsOf(kind),
      recentIds: recentOf(kind),
      ...(projects.enabled && projects.current !== null ? { groups: [{ key: "current", label: t.add.groups.current }, { key: "shared", label: t.add.groups.shared }, { key: "other", label: t.add.groups.other }] } : {}),
      onPick: (item: DefinitionPickItem) => pickDefinition(kind, item),
      ...(CREATABLE_KINDS.includes(kind) && routeOn(defRole(kind)) ? { onCreate: () => { setAddView(null); setCreating(kind); } } : {}),
      ...(attach
        ? {
            footer: (
              <fieldset className="team-picker-target">
                <legend className="app-muted">{t.add.attachTo}</legend>
                {attachNode === undefined ? null : (
                  <label className="ac-choice">
                    <input type="radio" name="pick-target" checked={attachTarget === "node"} onChange={() => setAttachChoice("node")} />
                    <span>{t.add.attachNodeLabel(attachNode.label)}</span>
                  </label>
                )}
                <label className="ac-choice">
                  <input type="radio" name="pick-target" checked={attachTarget === "shared"} onChange={() => setAttachChoice("shared")} />
                  <span>{t.add.attachTeamLabel}</span>
                </label>
              </fieldset>
            ),
          }
        : {}),
    };
  };
  const onAddAction = (action: { op: "create"; kind: string } | { op: "node"; typeId: string }) => {
    if (action.op === "create") setCreating(action.kind);
    else {
      addCentered(action.typeId);
    }
  };
  /** 서랍에서 정의를 만들었다: 팀에 넣고(초안만 바뀐다, 저장은 하지 않는다) 서랍을 닫고 새 노드의 이름 입력으로 간다. */
  const onDefinitionCreated = (created: CreatedDefinition) => {
    const before = draft;
    const result = applyDefinition(created.kind, { id: created.id, name: created.name }, created.attach);
    setCreating(null);
    if (created.bodyFailed === true) toast({ tone: "warning", text: t.add.createdBodyFailed(created.name) });
    else if (result === "none") toast({ tone: "success", text: t.add.createdOnly(created.name) });
    else if (result === "node" && attachNode !== undefined) toast({ tone: "success", text: t.add.attachedNode(created.name, attachNode.label), action: { label: t.node.undo, onClick: () => editor.setDraft(before) } });
    else if (result === "shared") toast({ tone: "success", text: t.add.attachedTeam(created.name), action: { label: t.node.undo, onClick: () => editor.setDraft(before) } });
    else if (result === "added") {
      toast({ tone: "success", text: t.add.createdNode(created.name), action: { label: t.node.undo, onClick: () => editor.setDraft(before) } });
      setForceTeam(false);
      setPanelOpen(true);
      setNodeTab("role");
      focusNodeName();
    }
  };

  const runList = runs.data ?? [];
  const running = runList.filter((r) => r.status === "running");
  const waiting = runList.filter((r) => r.status === "waiting");
  const goRun = (runId: string) => void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(runId)}`);
  const openWaiting = () => {
    const run = waiting[0];
    if (run === undefined) return;
    if (run.conversation_id) void navigate(`${routePath(ROUTE_ROLES.conversations)}/${encodeURIComponent(run.conversation_id)}`);
    else goRun(run.id);
  };

  const removeDraftShared = (key: string) => {
    const index = Number(key.split(":", 1)[0]);
    const removed = shared[index];
    if (removed === undefined) return;
    const prev = draft;
    change(withSharedAttachments(draft, shared.filter((_, i) => i !== index)));
    toast({ tone: "info", text: t.shared.removed(sharedChips[index]?.title ?? removed.ref), action: { label: t.shared.undo, onClick: () => editor.setDraft(prev) } });
  };

  const panel = (() => {
    if (!panelOpen) return null;
    if (selCount > 1) {
      const multi = layoutPanels?.multi;
      return <div className="team-panel-body">{multi !== undefined ? <MultiLayoutPanel {...multi.props} /> : <p>{t.panel.multiSelected(selCount)}</p>}</div>;
    }
    if (selNode !== undefined && !forceTeam) return <NodePanel ctx={ctx} node={selNode as NodeSpec} tab={nodeTab} onTab={setNodeTab} layout={layoutPanels?.node?.nodeId === selNode.id ? layoutPanels.node.props : undefined} focusPath={fixFocusPath} />;
    if (selEdge !== undefined && !forceTeam) return <EdgePanel ctx={ctx} edge={selEdge} layout={layoutPanels?.edge?.edgeId === selEdge.id ? layoutPanels.edge.props : undefined} />;
    return (
      <TeamPanel
        ctx={ctx}
        tab={teamTab}
        onTab={setTeamTab}
        onSelectNode={(nodeId) => { setForceTeam(false); setFocus({ nodeId, token: (focus?.token ?? 0) + 1 }); }}
        onSelectEdge={(edgeId, nodeId) => { setForceTeam(false); setFocus({ nodeId, edgeId, token: (focus?.token ?? 0) + 1 }); }}
        workspaceLoading={workspace.isLoading}
        workspaceFailed={workspace.isError}
      />
    );
  })();

  const menuItems = [
    { id: "rename", label: t.editor.renameFocus, onSelect: () => { setForceTeam(true); setTeamTab("overview"); setPanelOpen(true); setTimeout(() => document.getElementById(TEAM_NAME_INPUT_ID)?.focus(), 0); } },
    { id: "duplicate", label: t.editor.duplicate, onSelect: () => { setDialogError(null); setDialog("duplicate"); } },
    { id: "export", label: exportMessages.menu, onSelect: exportAction.open },
    { id: "versions", label: t.editor.versions, onSelect: () => setPageTab("versions") },
    { id: "json", label: t.editor.viewJson, onSelect: () => setDialog("json") },
    { id: "delete", label: t.editor.delete, danger: true, onSelect: () => { setDialogError(null); setDialog("delete"); } },
  ];

  return (
    <div className="app-screen-frame team-editor" data-screen="teams">
      <UnsavedGuard dirty={editor.dirty && !leaving} />
      <PageHeader
        title={draft.name || id}
        status={
          <>
            {openedFrom === undefined ? (
              <Link to={basePath} className="team-back">← {m.nav.teams}</Link>
            ) : (
              <TeamBreadcrumb rootLabel={m.nav.teams} rootHref={basePath} from={openedFrom} current={draft.name || id} hrefOf={(pid) => definitionPath(openedFrom.definitionKind, pid)} />
            )}
            <SaveStatus dirty={editor.dirty} phase={editor.savePhase} onRetry={save} />
          </>
        }
        actions={
          <>
            <Button onClick={() => validation.validateNow()} loading={validation.phase === "running"} title="F8">{t.editor.validate}</Button>
            <Button variant="primary" loading={saving} disabled={!editor.dirty || editor.conflict !== null} title={editor.conflict !== null ? m.definition.conflict.saveDisabled : "Ctrl+S"} onClick={save}>
              {t.editor.save}
            </Button>
            <Button
              variant="primary"
              loading={chat.busy}
              disabled={!hasEntry || blocking.length > 0 || editor.conflict !== null}
              title={!hasEntry ? "입구가 없습니다" : blocking.length > 0 ? t.editor.startChatBlocked : "Ctrl+Enter"}
              onClick={startChat}
            >
              {t.editor.startChat}
            </Button>
            <ActionMenu label={t.editor.menu} size="md" items={menuItems} />
          </>
        }
      />
      <div className="team-subbar">
        <div role="tablist" aria-label={t.editor.tabs} className="team-pagetabs">
          {(["edit", "runs", "versions"] as const).map((tab) => (
            <button key={tab} type="button" role="tab" className="app-tab" aria-selected={pageTab === tab} onClick={() => setPageTab(tab)}>
              {tab === "edit" ? t.editor.tabEdit : tab === "runs" ? t.editor.tabRuns : versionMessages.tab}
            </button>
          ))}
        </div>
        {running.length > 0 ? (
          <span className="team-chip">
            {t.editor.running(running.length)} <button type="button" className="app-link-btn" onClick={() => goRun(running[0]!.id)}>{t.editor.view}</button>
          </span>
        ) : null}
        {waiting.length > 0 ? (
          <span className="team-chip">
            {t.editor.waiting(waiting.length)} <button type="button" className="app-link-btn" onClick={openWaiting}>{t.editor.open}</button>
          </span>
        ) : null}
        <span className="app-spacer" />
        {!panelOpen ? <Button size="sm" onClick={() => setPanelOpen(true)}>{t.panel.label}</Button> : null}
      </div>
      {editor.conflict === null ? null : (
        <ConflictBanner
          details={editor.conflict}
          busy={saving}
          summary={`노드 ${editor.conflict.node_count ?? "?"}개 · 연결 ${editor.conflict.edge_count ?? "?"}개`}
          onLoadServer={() => void editor.loadServerVersion()}
          onSaveCopy={() => { setDialogError(null); setDialog("save-copy"); }}
          onOverwrite={() => void editor.overwrite()}
        />
      )}
      {editor.saveError !== null && editor.fieldErrors.length === 0 ? <Banner tone="danger">{editor.saveError}</Banner> : null}
      {chat.error ? <Banner tone="danger">{chat.error}</Banner> : null}
      <HintBanner id="teams"><HintOneLine short={t.layout.hintShort} full={t.editor.hint} /></HintBanner>

      {pageTab === "versions" ? (
        <div className="app-screen-body">
          <DefinitionVersionsTab
            model="Graph"
            id={id}
            currentHash={editor.versionHash}
            dirty={editor.dirty}
            onRestored={() => {
              editor.revert();
              void queryClient.invalidateQueries({ queryKey: definitionKey(DEFINITION_KINDS.graph, id) });
              void invalidateLists();
            }}
          />
        </div>
      ) : pageTab === "runs" ? (
        <div className="app-screen-body">
          {runs.isError ? (
            <ErrorBlock title={t.editor.runsFailed} message={runs.error.message} retryLabel={lm.retry} onRetry={() => void runs.refetch()} />
          ) : runList.length === 0 ? (
            <p className="app-muted">{t.editor.runsEmpty}</p>
          ) : (
            <table className="lib-grid" aria-label={t.editor.tabRuns}>
              <thead>
                <tr><th>{t.editor.runsId}</th><th>{t.editor.runsStatus}</th><th>{t.editor.runsStarted}</th></tr>
              </thead>
              <tbody>
                {runList.map((r) => (
                  <tr key={r.id}>
                    <td><Link to={`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(r.id)}`} className="lib-mono">{r.id.slice(0, 8)}</Link></td>
                    <td><StatusChip status={r.status} kind="run" label={m.runStatus[r.status] ?? r.status} /></td>
                    <td>{formatRelative(r.created_at, now)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <>
          <div className="team-main" ref={mainRef}>
            <div className="team-canvas" data-palette={paletteInline ? "inline" : "overlay"}>
              <div className="team-canvas-fill" ref={canvasRef}>
                <GraphEditor
                  ref={handle}
                  graph={draft}
                  nodeTypes={nodeTypeList}
                  edgeTypes={edgeTypeList}
                  resolvePorts={(typeId, config) => rest.resolvePorts(typeId, (config ?? {}) as Record<string, unknown>)}
                  onChange={(next, meta) => {
                    change(next);
                    // 팔레트로 새 노드를 놓으면 화면 밖일 수 있어 그 노드로 시야를 옮긴다
                    if (meta.reason === "add-node" || meta.reason === "auto-connect") {
                      // 좁은 화면의 오버레이 팔레트는 하나 놓으면 닫는다(캔버스를 다시 보여 준다)
                      if (!paletteInline) setPaletteOpen(false);
                      const known = new Set(nodesOf(meta.previous).map((n) => n.id));
                      const added = nodesOf(next).find((n) => !known.has(n.id));
                      if (added !== undefined) setFocus({ nodeId: added.id, token: (focus?.token ?? 0) + 1 });
                    }
                  }}
                  autoConnectIo={autoConnectIo}
                  onAutoConnect={({ addedEdgeIds }) => announceAutoConnect(addedEdgeIds)}
                  issues={validation.issues}
                  layoutDefaults={layoutDefaults}
                  layoutEngines={LAYOUT_ENGINES}
                  onLayoutPanelsChange={setLayoutPanels}
                  {...(focus === undefined ? {} : { focusRequest: focus })}
                  definitionLists={definitionLists}
                  definitionKindTitles={kindTitles}
                  edgeExtraChips={delegation.edgeExtraChips}
                  bindSummaries={delegation.bindSummaries}
                  nodeAvatars={nodeAvatars}
                  delegationStrategies={strategies.data ?? NONE}
                  edgeStrategyIds={delegation.edgeStrategyIds}
                  renderIcon={delegation.renderIcon}
                  onConnectRejected={(info) => {
                    // 반복 종류 후보가 없어 순환 연결을 만들 수 없을 때만 이 화면이 안내한다(그 밖의 거절은 편집기 기본 안내)
                    if (info.reason === "cycle") toast({ tone: "warning", text: t.nested.cycleRejected });
                  }}
                  {...(draft.settings?.editor?.default_edge_kind ?? workspace.data?.value.editor?.default_edge_kind ? { defaultEdgeKind: (draft.settings?.editor?.default_edge_kind ?? workspace.data?.value.editor?.default_edge_kind) as string } : {})}
                  showResources={showResources}
                  onShowResourcesChange={setShowResources}
                  showMinimap={minimap}
                  onShowMinimapChange={setMinimap}
                  paletteOverlay={!paletteInline}
                  paletteOpen={paletteOpen}
                  onPaletteClose={() => { setPaletteOpen(false); paletteButton.current?.focus(); }}
                  canvasActions={
                    <>
                      <AddControl
                        entries={addEntries}
                        view={addView}
                        onViewChange={setAddView}
                        onAction={onAddAction}
                        pickerProps={pickerPropsOf}
                      />
                      {paletteInline ? null : (
                        <Button ref={paletteButton} size="sm" aria-pressed={paletteOpen} title={t.layout.paletteTitle} onClick={() => setPaletteOpen((v) => !v)}>
                          {t.layout.palette}
                        </Button>
                      )}
                    </>
                  }
                  onOpenResources={(nodeId) => { setForceTeam(false); setNodeTab("resources"); setFocus({ nodeId, token: (focus?.token ?? 0) + 1 }); }}
                  teamShared={{
                    items: sharedChips,
                    onAdd: () => setDialog("shared-picker"),
                    onRemove: removeDraftShared,
                    onSelect: () => { setForceTeam(true); setTeamTab("shared"); setPanelOpen(true); },
                    inheritedCount: commonCount,
                    onOpenInherited: () => void navigate(routePath(ROUTE_ROLES.settings)),
                  }}
                  onSelectionChange={(sel) => {
                    setSelection(sel);
                    setForceTeam(false);
                    // 우측 패널이 오버레이인 좁은 화면에서는 선택하면 열린다(선택 해제로 닫지는 않는다)
                    if (!panelInline && sel.nodeIds.length + sel.edgeIds.length > 0) setPanelPref(true);
                  }}
                  palette={{
                    loading: nodeTypes.isLoading || agents.isLoading,
                    error: nodeTypes.isError ? nodeTypes.error.message : null,
                    onRetry: () => void nodeTypes.refetch(),
                    onCreateDefinition: (kind) => {
                      if (CREATABLE_KINDS.includes(kind) && routeOn(defRole(kind))) setCreating(kind);
                      else if (kind === DEFINITION_KINDS.graph) void navigate(`${basePath}?new=1`);
                      else void navigate(`${routePath(ROUTE_ROLES.resource)}?new=1`);
                    },
                  }}
                />
                {executableCount === 0 ? (
                  <div className="team-canvas-empty">
                    <div className="team-canvas-empty-card" role="note" data-testid="canvas-empty-card">
                      <h3>{t.editor.emptyCardTitle}</h3>
                      <div className="team-canvas-empty-actions">
                        <Button variant="primary" disabled={agentNodeType === undefined || !addEntries.some((e) => e.id === `pick:${agentNodeType.binds?.kind}`)} onClick={() => setAddView({ op: "pick", kind: agentNodeType?.binds?.kind ?? "" })}>{t.editor.pickAgent}</Button>
                        {agentNodeType?.binds != null && addEntries.some((e) => e.id === `create:${agentNodeType.binds?.kind}`) ? (
                          <Button onClick={() => setCreating(agentNodeType.binds?.kind ?? null)}>{t.palette.createAgent}</Button>
                        ) : null}
                      </div>
                      <p className="app-muted">{t.editor.emptyCardHint}</p>
                    </div>
                  </div>
                ) : null}
                <CanvasToastRegion label={t.editor.canvasToasts} />
              </div>
            </div>
            {panelOpen ? (
              <aside className="team-side" aria-label={t.panel.label} data-overlay={panelInline ? undefined : "true"}>
                <div className="team-side-close">
                  <Button size="sm" variant="ghost" aria-label={t.panel.close} onClick={() => setPanelOpen(false)}>×</Button>
                </div>
                {panel}
              </aside>
            ) : null}
          </div>
          <IssuesPanel
            graph={draft}
            validation={validation}
            open={issuesOpen}
            onToggle={() => setIssuesOpen((v) => !v)}
            onValidate={() => validation.validateNow()}
            onFocus={focusTarget}
            onApplySuggestion={applySuggestion}
          />
        </>
      )}

      {exportAction.dialog}
      {dialog === "duplicate" ? (
        <DuplicateTeamDialog sourceId={id} sourceName={draft.name} existingIds={new Set()} onClose={() => setDialog(null)} onCreated={(newId) => { setDialog(null); void navigate(`${basePath}/${encodeURIComponent(newId)}`); }} />
      ) : null}
      {dialog === "delete" ? (
        <DeleteDialog
          open
          name={draft.name || id}
          busy={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={() => {
            setBusy(true);
            rest
              .deleteGraph(id)
              .then(async () => {
                queryClient.removeQueries({ queryKey: definitionKey(DEFINITION_KINDS.graph, id) });
                await invalidateLists();
                setDialog(null);
                void navigate(basePath);
              })
              .catch((e: unknown) => setDialogError(describeError(e, t.delete.failed).message))
              .finally(() => setBusy(false));
          }}
        />
      ) : null}
      <Dialog open={dialog === "json"} title={t.editor.jsonTitle} onClose={() => setDialog(null)} wide actions={<Button onClick={() => setDialog(null)}>{lm.close}</Button>}>
        <pre className="ac-pre app-json">{JSON.stringify(draft, null, 2)}</pre>
      </Dialog>
      {dialog === "save-copy" ? (
        <NewDefinitionDialog
          open
          title={t.editor.saveCopyTitle}
          submitLabel={t.editor.saveCopySubmit}
          existingIds={new Set()}
          fallbackId={`${id}-copy`}
          initialName={`${draft.name} (내 변경)`}
          showDescription={false}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onSubmit={(v) => {
            setBusy(true);
            setDialogError(null);
            rest
              .createGraph({ ...draft, id: v.id, name: v.name })
              .then(async () => {
                await invalidateLists();
                setDialog(null);
                editor.revert();
                void navigate(`${basePath}/${encodeURIComponent(v.id)}`);
              })
              .catch((e: unknown) => setDialogError(describeError(e, t.duplicate.failed).message))
              .finally(() => setBusy(false));
          }}
        />
      ) : null}
      {creating !== null ? (
        <CreateDefinitionDrawer
          kind={creating}
          kindTitle={kindTitles[creating] ?? creating}
          existingIds={creating === DEFINITION_KINDS.agent ? new Set((agents.data ?? []).map((a) => a.id)) : creating === DEFINITION_KINDS.resource ? new Set((resources.data ?? []).map((r) => r.id)) : EMPTY_SET}
          resourceTypes={resourceTypes.data ?? NONE}
          attachNode={attachNode}
          onCreated={onDefinitionCreated}
          onClose={() => setCreating(null)}
        />
      ) : null}
      <Dialog
        open={backendCard !== null}
        title={t.backend.title}
        onClose={() => { if (!choosingBackend) setBackendCard(null); }}
        actions={<Button onClick={() => setBackendCard(null)} disabled={choosingBackend}>{t.backend.cancel}</Button>}
      >
        {backendCard === null ? null : (
          <ConnectedBackendChooserCard
            options={backendCard.options}
            nodeLabels={backendCard.labels}
            busy={choosingBackend}
            error={backendError}
            explain={t.backend.explain}
            busyLabel={t.backend.busy}
            onConfirm={(b) => void chooseBackend(b)}
          />
        )}
      </Dialog>
      {dialog === "shared-picker" ? (
        <ResourcePicker
          open
          resources={resources.data ?? []}
          types={resourceTypes.data ?? []}
          exclude={new Set(shared.map((a) => a.ref))}
          onPick={(r) => {
            change(withSharedAttachments(draft, [...shared, newAttachment(r.id)]));
            toast({ tone: "success", text: t.shared.added(r.name) });
            setDialog(null);
          }}
          onCreateNew={() => void navigate(`${routePath(ROUTE_ROLES.resource)}?new=1`)}
          onClose={() => setDialog(null)}
        />
      ) : null}
      <ConfirmDialog
        open={dialog === "start-save"}
        title={t.editor.startChatSave}
        confirmLabel={t.editor.startChatSave}
        cancelLabel={lm.cancel}
        onConfirm={() => void saveAndStart()}
        onCancel={() => setDialog(null)}
      >
        <p className="ac-text">{t.editor.startChatSaveBody}</p>
      </ConfirmDialog>
      <Dialog
        open={nav !== null}
        title={t.nested.openUnsavedTitle}
        onClose={() => setNav(null)}
        actions={
          <>
            <Button onClick={() => setNav(null)}>{t.nested.cancel}</Button>
            <Button variant="danger" onClick={() => void confirmNav(false)}>{t.nested.openWithoutSave}</Button>
            <Button variant="primary" loading={saving} onClick={() => void confirmNav(true)}>{t.nested.saveAndOpen}</Button>
          </>
        }
      >
        <p className="ac-text">{t.nested.openUnsavedBody}</p>
      </Dialog>
      {bundleNode !== null ? (
        <BundlePreviewDialog graphId={id} nodeId={bundleNode} nodeLabel={nodes.find((n) => n.id === bundleNode)?.label ?? bundleNode} savedNode={savedNodeIds.has(bundleNode)} draft={editor.dirty ? editor.draft : undefined} onClose={() => setBundleNode(null)} />
      ) : null}
    </div>
  );
}
