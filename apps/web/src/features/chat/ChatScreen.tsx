import { NEW_PARAM, useProjects } from "../projects";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { Button, ConfirmDialog, Dialog, useShortcuts, useToast } from "@agent-console/ui";
import type { ConversationSummary, Interaction } from "@agent-console/contracts";
import { describeError } from "../../app/errors";
import { messages as appMessages } from "../../app/messages";
import { useApi } from "../../app/ApiContext";
import { useProjectId } from "../../app/projectScope";
import { useNow } from "../../app/useNow";
import { usePendingInteractions } from "../../shell/pending";
import { useRegisterCommands } from "../../shell/commands";
import { ChatHome } from "./ChatHome";
import { ChatPane } from "./ChatPane";
import { useWorkspaceSettings } from "../../app/queries";
import { useDebouncedValue } from "../../app/useDebouncedValue";
import { chatKeys, useAgentList, useConversationList, useChatGraph, useGraphList } from "./chatData";
import { chatMessages } from "./chatMessages";
import { ConversationList } from "./ConversationList";
import { chatPaths } from "./paths";
import { lastUsedByGraph, pendingSinceOf, sortConversations, patchConversationCache } from "./lib/conversations";
import { LAST_GRAPH_KEY } from "./lib/drafts";
import { indexById } from "./lib/team";
import { NewConversationDialog } from "./NewConversationDialog";
import { TeamPickerDialog } from "./TeamPickerDialog";
import { GraphIssuesPreview } from "../teams";
import { useConversationActions } from "./useConversationActions";
import { usePendingNotices } from "./usePendingNotices";
import { useStorage } from "../../app/StorageContext";
import "@agent-console/chat/styles.css";
import "./chat.css";
import { useImeGuard } from "../../lib/ime";

const t = chatMessages;
/** 목록에서 요약을 실시간으로 받을 대화 수(앞쪽 = 정렬 전 서버 순서의 최근 갱신순) */
const WATCH_LIMIT = 30;
/** 대화 갱신 알림 뒤 목록을 다시 읽기까지 모으는 시간(ms) */
const CONVERSATION_REREAD_MS = 300;

/** 채팅 화면(라우트 `/chat`, `/chat/:conversationId`): 대화 목록 + 열린 대화. 데이터는 훅이, 표현은 chat 패키지가 맡는다. */

export function ChatScreen() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const storage = useStorage();
  const actions = useConversationActions();
  const nowMs = useNow(true);
  const [query, setQuery] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const debouncedQuery = useDebouncedValue(query);
  // 보관 여부와 제목 검색은 서버가 거른다(6R.19). 검색어가 바뀌면 첫 페이지부터 다시 읽는다.
  const conversations = useConversationList({ ...(includeArchived ? {} : { archived: false }), q: debouncedQuery });
  const currentProject = useProjectId();
  const graphs = useGraphList(true, currentProject);
  const agents = useAgentList();
  const settings = useWorkspaceSettings();
  const pending = usePendingInteractions();

  const [listOpen, setListOpen] = useState(true);
  const [focusToken, setFocusToken] = useState(0);
  const projects = useProjects();
  const [searchParams, setSearchParams] = useSearchParams();
  // 프로젝트 홈의 [채팅 시작]이 `?new=1`을 붙여 오면 처음부터 새 대화 대화상자가 열려 있다(아래 효과가 질의를 지운다)
  const [newDialog, setNewDialog] = useState<{ preselected?: string; project?: string } | null>(() => {
    if (searchParams.get(NEW_PARAM) !== "1") return null;
    const project = searchParams.get("prj");
    return { preselected: storage.get(LAST_GRAPH_KEY) ?? undefined, ...(project === null ? {} : { project }) };
  });
  // 프로젝트가 하나 이상 등록되어 있으면 새 대화는 프로젝트 대화상자(폴더 줄 + 그 프로젝트의 구성)로 연다
  const projectDialog = projects.enabled && projects.views.some((v) => v.project.archived !== true);
  const projectsPending = projects.enabled && !projects.loaded;
  const [newBusy, setNewBusy] = useState(false);
  const [newError, setNewError] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<ConversationSummary | null>(null);
  const [renameText, setRenameText] = useState("");
  const renameIme = useImeGuard();
  const [deleteTarget, setDeleteTarget] = useState<ConversationSummary | null>(null);

  const agentMap = useMemo(() => indexById(agents.data), [agents.data]);
  const currentConv = (conversations.data ?? []).find((c) => c.id === conversationId);
  const currentGraph = useChatGraph(currentConv?.graph_id, currentConv?.project_id ?? null);
  const nodeLabelOf = useCallback(
    (i: Interaction) => currentGraph.data?.graph.nodes?.find((n) => n.id === (i.node_path?.[0] ?? i.node_id))?.label || undefined,
    [currentGraph.data],
  );
  const live = usePendingNotices({ currentConversationId: conversationId, agents: agentMap, nodeLabelOf, nowSeconds: () => Date.now() / 1000 });

  const since = useMemo(() => pendingSinceOf(pending.items), [pending.items]);

  // 목록 실시간: 보이는 대화(앞쪽 일부)의 요약을 구독하고, 응답 대기 목록이 바뀌면 목록을 다시 읽는다.
  const { ws } = useApi();
  const queryClient = useQueryClient();
  const watched = (conversations.data ?? []).slice(0, WATCH_LIMIT).map((c) => c.id).join(",");
  useEffect(() => {
    // 갱신된 대화는 서버 목록에서 맨 앞으로 옮겨 가므로, 요약을 제자리에 반영한 뒤 짧게 모아 목록을 다시 읽는다.
    let timer: ReturnType<typeof setTimeout> | undefined;
    const subs = (watched === "" ? [] : watched.split(",")).map((id) =>
      ws.subscribeConversation(id, (summary) => {
        queryClient.setQueriesData({ queryKey: chatKeys.conversations() }, (cur: unknown) => (cur ? patchConversationCache(cur, summary) : cur));
        clearTimeout(timer);
        timer = setTimeout(() => void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() }), CONVERSATION_REREAD_MS);
      }),
    );
    return () => {
      clearTimeout(timer);
      subs.forEach((s) => s?.unsubscribe());
    };
  }, [ws, queryClient, watched]);
  const pendingKey = pending.items.map((i) => `${i.id}:${i.status}`).join(",");
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
  }, [queryClient, pendingKey]);
  const sortValue = settings.data?.value.chat?.list_sort;
  const visible = useMemo(
    () => sortConversations(conversations.data ?? [], sortValue, since),
    [conversations.data, sortValue, since],
  );
  const sourceLabel = useCallback((source: string) => appMessages.common.recordSources[source] ?? source, []);
  const teamNames = useMemo(() => new Map((graphs.data ?? []).map((g) => [g.id, g.name])), [graphs.data]);
  const teamName = useCallback((graphId: string) => (graphs.data === undefined ? "…" : teamNames.get(graphId)), [graphs.data, teamNames]);

  const openNew = useCallback((preselected?: string, project?: string) => {
    setNewError(null);
    setNewDialog({ preselected: preselected ?? storage.get(LAST_GRAPH_KEY) ?? undefined, ...(project === undefined ? {} : { project }) });
  }, [storage]);

  // 새 대화 질의는 한 번 읽고 지운다(새로고침해도 다시 열리지 않게)
  const wantsNew = searchParams.get(NEW_PARAM) === "1";
  useEffect(() => {
    if (!wantsNew) return;
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete(NEW_PARAM);
      return next;
    }, { replace: true });
  }, [wantsNew, setSearchParams]);

  useRegisterCommands([{ id: "chat.new", titleKey: "palette.actions.chatNew", run: () => openNew() }]);

  const goTo = (id: string | undefined) => void navigate(id ? chatPaths.conversation(id) : chatPaths.chat());
  const step = (delta: number) => {
    if (visible.length === 0) return;
    const i = visible.findIndex((c) => c.id === conversationId);
    const next = visible[Math.min(visible.length - 1, Math.max(0, (i < 0 ? (delta > 0 ? -1 : visible.length) : i) + delta))];
    if (next) goTo(next.id);
  };
  useShortcuts([
    {
      id: "pending.jump",
      scope: "chat",
      keys: "Alt+J",
      titleKey: "shortcuts.pendingJump",
      modifierRequired: true,
      run: () => {
        if (conversationId !== undefined && pending.items.some((i) => i.conversation_id === conversationId)) {
          setFocusToken((n) => n + 1);
          return;
        }
        const oldest = pending.items.find((i) => i.conversation_id != null);
        if (oldest?.conversation_id) goTo(oldest.conversation_id);
        else toast({ tone: "info", text: appMessages.pending.none });
      },
    },
    { id: "chat.prev", scope: "chat", keys: "Alt+ArrowUp", titleKey: "shortcuts.chatPrev", modifierRequired: true, run: () => step(-1) },
    { id: "chat.next", scope: "chat", keys: "Alt+ArrowDown", titleKey: "shortcuts.chatNext", modifierRequired: true, run: () => step(1) },
  ]);

  // 열린 대화가 요약 목록에 없고 목록이 이미 로드됐다면 그대로 둔다(보관 필터 등으로 숨은 경우). 상세는 ChatPane이 읽는다.
  useEffect(() => {
    if (conversationId !== undefined) document.getElementById("app-main")?.scrollTo?.({ top: 0 });
  }, [conversationId]);

  const guarded = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (e) {
      toast({ tone: "danger", text: describeError(e, appMessages.common.requestFailed).message });
    }
  };

  const startConversation = (graphId: string, title: string) => {
    setNewBusy(true);
    setNewError(null);
    actions
      .create(graphId, title)
      .then((created) => {
        storage.set(LAST_GRAPH_KEY, graphId);
        setNewDialog(null);
        goTo(created.id);
      })
      .catch((e: unknown) => setNewError(describeError(e, t.newDialog.createFailed).message))
      .finally(() => setNewBusy(false));
  };

  // 대화가 하나도 없고 아무 대화도 열지 않았으면 빈 목록 열을 접는다(화면 활용, 5.2R.21). 새 대화는 오른쪽 시작 카드가 맡는다.
  // 목록을 불러오는 동안은 접힘 여부를 모르므로 자리는 두고 보이지 않게 한다(0개면 접히며 깜빡이는 것을 막는다).
  const listLoading = conversationId === undefined && conversations.isLoading;
  const listEmpty = conversationId === undefined && conversations.data !== undefined && conversations.data.length === 0 && debouncedQuery.trim() === "";
  return (
    <div className="chat-screen" data-screen="chat" data-list={listOpen ? "open" : "closed"} data-empty={listEmpty ? "true" : undefined} data-loading={listLoading ? "true" : undefined}>
      <div className="ac-sr-only" role="status" aria-live="polite" aria-label={appMessages.pending.none}>{live}</div>
      {conversationId === undefined ? <h1 className="ac-sr-only">{t.list.label}</h1> : null}
      <aside className="chat-list-pane" aria-label={t.list.label}>
        <ConversationList
          conversations={visible}
          header={projects.enabled && projects.currentProject !== undefined ? <p className="chat-list-project ac-ellipsis app-muted" title={projects.currentProject.folder ?? undefined}>{projects.currentProject.name}</p> : null}
          totalCount={conversations.data?.length ?? 0}
          selectedId={conversationId}
          loading={conversations.isLoading}
          error={conversations.error && conversations.data === undefined ? describeError(conversations.error, t.list.loadFailed).message : null}
          onRetry={() => void conversations.refetch()}
          paging={{ hasMore: conversations.hasMore, loading: conversations.loadingMore, onLoadMore: conversations.loadMore }}
          sourceOf={conversations.sourceOf}
          sourceLabel={sourceLabel}
          query={query}
          onQueryChange={setQuery}
          includeArchived={includeArchived}
          onIncludeArchivedChange={setIncludeArchived}
          teamName={teamName}
          nowMs={nowMs}
          onSelect={(id) => goTo(id)}
          onNew={() => openNew()}
          onRename={(c) => {
            setRenameTarget(c);
            setRenameText(c.title ?? "");
          }}
          onToggleArchive={(c) => void guarded(() => actions.setArchived(c.id, !c.archived, c.project_id))}
          onDelete={setDeleteTarget}
          onOpenTeam={(c) => void navigate(chatPaths.team(c.graph_id))}
        />
      </aside>
      <section className="chat-main" aria-label={t.title}>
        {conversationId === undefined ? (
          <ChatHome onNew={() => openNew()} />
        ) : (
          <ChatPane
            key={conversationId}
            conversationId={conversationId}
            nowMs={nowMs}
            listOpen={listOpen}
            onToggleList={() => setListOpen((v) => !v)}
            focusPendingToken={focusToken}
            onNewWithTeam={(graphId) => openNew(graphId)}
            onGone={() => goTo(undefined)}
          />
        )}
      </section>

      {newDialog !== null && projectDialog && !projectsPending ? (
        <NewConversationDialog
          preselected={newDialog.preselected}
          initialProject={newDialog.project}
          nowMs={nowMs}
          onClose={() => setNewDialog(null)}
          onCreated={(created) => {
            setNewDialog(null);
            goTo(created.id);
          }}
        />
      ) : null}
      <TeamPickerDialog
        open={newDialog !== null && !projectDialog && !projectsPending}
        title={t.newDialog.title}
        confirmLabel={t.newDialog.start}
        graphs={graphs.data ?? []}
        loading={graphs.isLoading}
        loadError={graphs.error && graphs.data === undefined ? t.newDialog.loadFailed : null}
        lastUsed={lastUsedByGraph(conversations.data ?? [])}
        preselectedId={newDialog?.preselected}
        withTitle
        nowMs={nowMs}
        busy={newBusy}
        error={newError}
        teamsPath={chatPaths.teams()}
        renderIssues={(g) => <GraphIssuesPreview graph={g} project={projects.currentProject?.id ?? null} />}
        onClose={() => setNewDialog(null)}
        onConfirm={startConversation}
      />
      <Dialog
        open={renameTarget !== null}
        title={t.rename.title}
        onClose={() => setRenameTarget(null)}
        actions={
          <>
            <Button onClick={() => setRenameTarget(null)}>{appMessages.common.cancel}</Button>
            <Button
              variant="primary"
              onClick={() => {
                const target = renameTarget;
                setRenameTarget(null);
                if (target) void guarded(() => actions.rename(target.id, renameText.trim(), target.project_id));
              }}
            >
              {t.rename.save}
            </Button>
          </>
        }
      >
        <label className="app-field">
          <span>{t.rename.label}</span>
          <input
            type="text"
            className="ac-input"
            value={renameText}
            onChange={(e) => setRenameText(e.target.value)}
            {...renameIme.handlers}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !renameIme.isIme(e)) {
                e.preventDefault();
                const target = renameTarget;
                setRenameTarget(null);
                if (target) void guarded(() => actions.rename(target.id, renameText.trim(), target.project_id));
              }
            }}
          />
        </label>
      </Dialog>
      <ConfirmDialog
        open={deleteTarget !== null}
        danger
        title={t.remove.title}
        confirmLabel={t.remove.confirm}
        cancelLabel={appMessages.common.cancel}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          const target = deleteTarget;
          setDeleteTarget(null);
          if (!target) return;
          void guarded(async () => {
            await actions.remove(target.id, target.project_id);
            if (target.id === conversationId) goTo(undefined);
          });
        }}
      >
        <p className="ac-text">{t.remove.body}</p>
      </ConfirmDialog>
    </div>
  );
}
