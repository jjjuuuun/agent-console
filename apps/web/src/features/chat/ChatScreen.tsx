import { useScopedList } from "../projects";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router";
import { Button, ConfirmDialog, Dialog, useShortcuts, useToast } from "@agent-console/ui";
import type { ConversationSummary, Interaction } from "@agent-console/contracts";
import { describeError } from "../../app/errors";
import { messages as appMessages } from "../../app/messages";
import { useApi } from "../../app/ApiContext";
import { useNow } from "../../app/useNow";
import { usePendingInteractions } from "../../shell/pending";
import { useRegisterCommands } from "../../shell/commands";
import { ChatHome } from "./ChatHome";
import { ChatPane } from "./ChatPane";
import { useWorkspaceSettings } from "../../app/queries";
import { chatKeys, useAgentList, useConversationList, useChatGraph, useGraphList } from "./chatData";
import { chatMessages } from "./chatMessages";
import { ConversationList } from "./ConversationList";
import { chatPaths } from "./paths";
import { filterConversations, lastUsedByGraph, pendingSinceOf, sortConversations, upsertConversation } from "./lib/conversations";
import { LAST_GRAPH_KEY } from "./lib/drafts";
import { indexById } from "./lib/team";
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

/** 채팅 화면(라우트 `/chat`, `/chat/:conversationId`): 대화 목록 + 열린 대화. 데이터는 훅이, 표현은 chat 패키지가 맡는다. */
const scopeOfConversation = (c: ConversationSummary) => c.project_id;
const idOfConversation = (c: ConversationSummary) => c.id;

export function ChatScreen() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const storage = useStorage();
  const actions = useConversationActions();
  const nowMs = useNow(true);
  const conversations = useConversationList();
  const scoped = useScopedList(conversations.data, { scopeOf: scopeOfConversation, idOf: idOfConversation, nameOf: idOfConversation });
  const graphs = useGraphList();
  const agents = useAgentList();
  const settings = useWorkspaceSettings();
  const pending = usePendingInteractions();

  const [query, setQuery] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [listOpen, setListOpen] = useState(true);
  const [focusToken, setFocusToken] = useState(0);
  const [newDialog, setNewDialog] = useState<{ preselected?: string } | null>(null);
  const [newBusy, setNewBusy] = useState(false);
  const [newError, setNewError] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<ConversationSummary | null>(null);
  const [renameText, setRenameText] = useState("");
  const renameIme = useImeGuard();
  const [deleteTarget, setDeleteTarget] = useState<ConversationSummary | null>(null);

  const agentMap = useMemo(() => indexById(agents.data), [agents.data]);
  const currentGraph = useChatGraph((conversations.data ?? []).find((c) => c.id === conversationId)?.graph_id);
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
    const subs = (watched === "" ? [] : watched.split(",")).map((id) =>
      ws.subscribeConversation(id, (summary) => queryClient.setQueryData<ConversationSummary[]>(chatKeys.conversations(), (cur) => (cur ? upsertConversation(cur, summary) : cur))),
    );
    return () => subs.forEach((s) => s?.unsubscribe());
  }, [ws, queryClient, watched]);
  const pendingKey = pending.items.map((i) => `${i.id}:${i.status}`).join(",");
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
  }, [queryClient, pendingKey]);
  const sortValue = settings.data?.value.chat?.list_sort;
  const visible = useMemo(
    () => sortConversations(filterConversations(scoped.items ?? [], { query, includeArchived }), sortValue, since),
    [scoped.items, query, includeArchived, sortValue, since],
  );
  const teamNames = useMemo(() => new Map((graphs.data ?? []).map((g) => [g.id, g.name])), [graphs.data]);
  const teamName = useCallback((graphId: string) => (graphs.data === undefined ? "…" : teamNames.get(graphId)), [graphs.data, teamNames]);

  const openNew = useCallback((preselected?: string) => {
    setNewError(null);
    setNewDialog({ preselected: preselected ?? storage.get(LAST_GRAPH_KEY) ?? undefined });
  }, [storage]);

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
  const listEmpty = conversationId === undefined && conversations.data !== undefined && conversations.data.length === 0;
  return (
    <div className="chat-screen" data-screen="chat" data-list={listOpen ? "open" : "closed"} data-empty={listEmpty ? "true" : undefined} data-loading={listLoading ? "true" : undefined}>
      <div className="ac-sr-only" role="status" aria-live="polite" aria-label={appMessages.pending.none}>{live}</div>
      <aside className="chat-list-pane" aria-label={t.list.label}>
        <ConversationList
          conversations={visible}
          header={scoped.bar}
          totalCount={conversations.data?.length ?? 0}
          selectedId={conversationId}
          loading={conversations.isLoading}
          error={conversations.error && conversations.data === undefined ? describeError(conversations.error, t.list.loadFailed).message : null}
          onRetry={() => void conversations.refetch()}
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
          onToggleArchive={(c) => void guarded(() => actions.setArchived(c.id, !c.archived))}
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

      <TeamPickerDialog
        open={newDialog !== null}
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
        renderIssues={(g) => <GraphIssuesPreview graph={g} />}
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
                if (target) void guarded(() => actions.rename(target.id, renameText.trim()));
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
                if (target) void guarded(() => actions.rename(target.id, renameText.trim()));
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
            await actions.remove(target.id);
            if (target.id === conversationId) goTo(undefined);
          });
        }}
      >
        <p className="ac-text">{t.remove.body}</p>
      </ConfirmDialog>
    </div>
  );
}
