import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError } from "@agent-console/api-client";
import { ANSWER_MODES, Composer, MessageList, type AnswerMode, type ComposerHandle, type QueuedRow } from "@agent-console/chat";
import type { BackendDescriptor, Fix, Interaction, InteractionKindDescriptor } from "@agent-console/contracts";
import { Banner, Button, ConfirmDialog, Spinner, useShortcuts, useToast } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { FixButtons } from "../../app/fix";
import { ConnectedBackendChooserCard, unresolvedBackendOf, useSaveDefaultBackend, type UnresolvedBackend } from "../backendChoice";
import { describeError } from "../../app/errors";
import { messages as appMessages } from "../../app/messages";
import { useConnectionStatus } from "../../app/useConnectionStatus";
import { useStorage } from "../../app/StorageContext";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { delegationMessages as dm } from "../delegation";
import { countHandled, failedChildOf, hasRunningChild } from "./lib/progress";
import { usePageTitle } from "../../shell/titles";
import { ChatHeader } from "./ChatHeader";
import { useWorkspaceSettings } from "../../app/queries";
import { chatKeys, useAgentList, useBackendList, useChatGraph, useChatPlan, useConversationDetail, useEdgeTypeList, useGraphList, useInteractionKindList, useNodeTypeList, useQueueList } from "./chatData";
import { chatMessages } from "./chatMessages";
import { EmptyConversation } from "./EmptyViews";
import { InteractionItem } from "./InteractionItem";
import { badgeOfBackend, effectiveBackendId } from "./lib/backendBadge";
import { actorLabel as buildActorLabel, buildAgentView } from "./lib/actors";
import { answerTarget as findAnswerTarget, buildResponse, quoteForResend } from "./lib/answer";
import { resolveChatSettings } from "./lib/chatSettings";
import { lastUsedByGraph } from "./lib/conversations";
import { readDraft, writeDraft } from "./lib/drafts";
import { isActiveStatus } from "./lib/liveRun";
import { agentOfNode, hasEntry, indexById, summarizeTeam, type NamingContext } from "./lib/team";
import { chatPaths } from "./paths";
import { TeamPickerDialog } from "./TeamPickerDialog";
import { ResumeDialog } from "./ResumeDialog";
import { canOfferResume, isResumed } from "./lib/resume";
import { GraphIssuesPreview } from "../teams";
import { useConversationActions } from "./useConversationActions";
import { useConversationFeed } from "./useConversationFeed";
import { useInteractionRespond } from "../interactions";
import { useConversationList } from "./chatData";
import { useQueryClient } from "@tanstack/react-query";

const t = chatMessages;

export interface ChatPaneProps {
  conversationId: string;
  /** 현재 시각(ms). 호출자가 1초마다 갱신해 넘긴다 */
  nowMs: number;
  listOpen: boolean;
  onToggleList: () => void;
  /** 값이 바뀔 때마다 가장 오래된 응답 대기 카드로 이동·포커스(Alt+J) */
  focusPendingToken: number;
  /** 같은 팀 구성으로 새 대화 */
  onNewWithTeam: (graphId: string) => void;
  /** 이 대화가 사라졌을 때(삭제·404) */
  onGone: () => void;
}

const NO_PROGRESS: Record<string, never[]> = {};

type Notice = { text: string; tone: "info" | "warning" | "danger"; fix?: Fix | undefined };

/** 열린 대화 하나(컨테이너): 데이터·실시간 연결을 조립하고 `@agent-console/chat`의 표현 컴포넌트에 넘긴다. */
export function ChatPane(props: ChatPaneProps) {
  const { conversationId: id, nowMs } = props;
  const { rest, ws } = useApi();
  const storage = useStorage();
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const actions = useConversationActions();
  const connection = useConnectionStatus(ws);
  const connected = connection === "open";
  // 연동 부분(다른 기능과 이어져야 의미가 있는 곳). 꺼졌으면 그 부분만 빠지고 대화·기록·대기열은 그대로다.
  const cardPart = useLinkPart(LINK_PART_IDS.chatInteractionCard);
  const chipPart = useLinkPart(LINK_PART_IDS.chatDelegationChip);
  const sendPart = useLinkPart(LINK_PART_IDS.chatSend);
  const resumePart = useLinkPart(LINK_PART_IDS.chatResumeTurn);

  const conversation = useConversationDetail(id);
  const graphs = useGraphList();
  const list = useConversationList();
  const graph = useChatGraph(conversation.data?.graph_id);
  const plan = useChatPlan(conversation.data?.graph_id);
  const edgeTypes = useEdgeTypeList();
  const nodeTypes = useNodeTypeList();
  const agents = useAgentList();
  const kinds = useInteractionKindList();
  const settings = useWorkspaceSettings();
  const backendList = useBackendList();
  const queue = useQueueList(id);

  const kindMap = useMemo(() => indexById(edgeTypes.data), [edgeTypes.data]);
  const naming = useMemo<NamingContext>(() => ({ nodeTypes: indexById(nodeTypes.data), agents: indexById(agents.data) }), [nodeTypes.data, agents.data]);
  const descriptors = useMemo(() => indexById<InteractionKindDescriptor>(kinds.data), [kinds.data]);
  const descriptorRecord = useMemo(() => Object.fromEntries(descriptors), [descriptors]);
  const chat = useMemo(() => resolveChatSettings(settings.data?.value.chat, graph.data?.graph.settings?.chat), [settings.data, graph.data]);
  const replyDisplay = typeof chat.reply_display === "string" ? chat.reply_display : "separate";
  const answerEnabled = chat.answer_with_composer !== false;

  const feed = useConversationFeed({ conversationId: id, ws, graph: graph.data?.graph, plan: plan.data, kinds: kindMap, naming, interactions: cardPart.visible });
  const { turns } = feed;
  const notifyInfo = useCallback((text: string) => toast({ tone: "info", text }), [toast]);
  const respondState = useInteractionRespond({ applyInteraction: feed.applyInteraction, refresh: feed.refresh, notify: notifyInfo, messages: { failed: t.composer.answerFailed } });

  // ---- 파생 값 ----
  const team = graphs.data?.find((g) => g.id === conversation.data?.graph_id);
  const teamMissing = graphs.data !== undefined && conversation.data !== undefined && team === undefined;
  const noEntry = team !== undefined && hasEntry(team) === false;
  const archived = conversation.data?.archived === true;
  const title = conversation.data?.title || t.newConversationTitle;
  usePageTitle(title);
  const actorCtx = useMemo(() => ({ graph: graph.data?.graph, naming }), [graph.data, naming]);
  const defaultBackend = settings.data?.value.agent_defaults?.backend;
  const backendById = useMemo(() => indexById<BackendDescriptor>(backendList.data), [backendList.data]);
  const teamBackendRaw: unknown = graph.data?.graph.settings?.["backend"];
  const teamBackend = typeof teamBackendRaw === "string" && teamBackendRaw !== "" ? teamBackendRaw : undefined;
  const agentView = useMemo(
    () => buildAgentView(turns, actorCtx, feed.delegators, (agent, node) => badgeOfBackend(backendById, effectiveBackendId(agent, node, defaultBackend, teamBackend))),
    [turns, actorCtx, feed.delegators, backendById, defaultBackend, teamBackend],
  );
  // 팀이 칩이 붙는 백엔드로 도는지(문구는 디스크립터 데이터). 팀 노드 중 하나라도 해당하면 한 줄 안내를 보인다
  const teamBadge = useMemo(() => {
    for (const node of graph.data?.graph.nodes ?? []) {
      const agent = agentOfNode(node, naming);
      const badge = badgeOfBackend(backendById, effectiveBackendId(agent, node, defaultBackend, teamBackend));
      if (badge !== undefined) return badge;
    }
    return undefined;
  }, [graph.data, naming, backendById, defaultBackend, teamBackend]);
  const badgeNoteKey = `chat.backendNote.dismissed`;
  const [badgeNoteDismissed, setBadgeNoteDismissed] = useState(() => storage.get(badgeNoteKey) === "1");
  const [changingBackend, setChangingBackend] = useState(false);
  const labelOf = useCallback(
    (i: Interaction) => {
      // 중첩 팀 자식 실행 안 요청: 요청자 이름은 그 자식 그래프로 찾고, 앞에 부모 노드(중첩 팀)를 붙인다
      const nested = feed.nestedOrigin(i);
      if (nested === undefined) return buildActorLabel(i, actorCtx, { inside: t.interaction.actorInside });
      const own = buildActorLabel(i, { graph: nested.graph, naming }, { inside: t.interaction.actorInside });
      const names = nested.path.filter((n) => n !== "");
      return names.length === 0 ? own : dm.run.child.nestedActor(names.length > 3 ? `${names[0]} › … › ${names[names.length - 1]}` : names.join(" › "), own);
    },
    [actorCtx, naming, feed],
  );
  const pending = useMemo(() => (cardPart.visible ? turns.flatMap((turn) => (turn.interactions ?? []).filter((i) => i.status === "pending")) : []), [turns, cardPart.visible]);
  const activeTurn = useMemo(() => [...turns].reverse().find((turn) => isActiveStatus(turn.status)), [turns]);
  const target = useMemo(() => findAnswerTarget(pending, descriptors, answerEnabled), [pending, descriptors, answerEnabled]);
  const lastTurn = turns[turns.length - 1];
  const summary = useMemo(() => (plan.data ? summarizeTeam(plan.data, graph.data?.graph, naming) : undefined), [plan.data, graph.data, naming]);

  // ---- 입력창 ----
  const composer = useRef<ComposerHandle>(null);
  const [text, setText] = useState(() => readDraft(storage, id));
  useEffect(() => writeDraft(storage, id, text), [storage, id, text]);
  // 답변 모드 띠 상태는 그 요청에 묶인다(요청이 바뀌면 다시 "답하기"로)
  const targetId = target?.interaction.id;
  const [modeState, setModeState] = useState<{ id: string | undefined; mode: AnswerMode }>({ id: undefined, mode: ANSWER_MODES.answer });
  const mode = modeState.id === targetId ? modeState.mode : ANSWER_MODES.answer;
  const setMode = (next: AnswerMode) => setModeState({ id: targetId, mode: next });
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState<Notice | undefined>();
  // 거절 안내는 거절당한 그 실행이 진행 중인 동안만 보인다(끝나면 저절로 사라진다)
  const [rejectedAt, setRejectedAt] = useState<string | undefined>(undefined);
  const turnMark = (turn: { run_id: string; status: string } | undefined) => (turn ? `${turn.run_id}:${turn.status}` : "");
  const rejectBusy = rejectedAt !== undefined && rejectedAt === turnMark(activeTurn ?? turns[turns.length - 1]);

  const queuedRows = useMemo<QueuedRow[]>(
    () => (queue.data ?? []).map((q) => ({ key: q.id ?? String(q.position), text: q.text ?? "", position: q.position, ...(q.held === true ? { held: true } : {}) })),
    [queue.data],
  );
  const heldRows = queuedRows.filter((q) => q.held === true);

  // ---- 멈춘 대기열(재시작 뒤 `ask`): 실행·취소·입력창으로 가져오기. 낙관적 변경 없이 서버 응답 뒤 다시 읽는다 ----
  const [queuedBusy, setQueuedBusy] = useState<readonly string[]>([]);
  const [queuedErrors, setQueuedErrors] = useState<Record<string, string>>({});
  const [confirmCancelAll, setConfirmCancelAll] = useState(false);
  const runQueued = async (keys: readonly string[], op: (key: string) => Promise<unknown>): Promise<boolean> => {
    setQueuedBusy((cur) => [...cur, ...keys]);
    setQueuedErrors((cur) => Object.fromEntries(Object.entries(cur).filter(([k]) => !keys.includes(k))));
    let ok = true;
    for (const key of keys) {
      try {
        await op(key);
      } catch (e) {
        ok = false;
        setQueuedErrors((cur) => ({ ...cur, [key]: describeError(e, t.held.failed).message }));
        break;
      }
    }
    setQueuedBusy((cur) => cur.filter((k) => !keys.includes(k)));
    await queue.refetch();
    feed.refresh();
    return ok;
  };
  const releaseQueued = (keys: readonly string[]) => void runQueued(keys, (k) => rest.releaseQueuedMessage(id, k));
  const cancelQueued = (keys: readonly string[]) => void runQueued(keys, (k) => rest.cancelQueuedMessage(id, k));
  const recallQueued = (key: string) => {
    const row = queuedRows.find((q) => q.key === key);
    if (row === undefined) return;
    void runQueued([key], (k) => rest.cancelQueuedMessage(id, k)).then((ok) => {
      if (!ok) return;
      setText((cur) => (cur.trim() === "" ? row.text : `${cur}\n${row.text}`));
      setTimeout(() => composer.current?.focus(), 0);
    });
  };

  // ---- 끊긴 턴 이어 가기 ----
  const offerResume = chat.offer_resume;
  const [resumeFor, setResumeFor] = useState<string | null>(null);
  const renderTurnNotice = (turn: { run_id: string; status: string }) => {
    if (turn.status !== "interrupted") return null;
    if (isResumed(turn.run_id, turns)) return <div className="app-muted" role="status">{t.resume.resumedLine}</div>;
    if (!canOfferResume(turn, turns, offerResume)) return null;
    // 이어 가기 연동이 꺼졌으면 "끊김" 표시만 남긴다
    if (!resumePart.visible) return <div className="app-muted" role="status">{t.resume.interruptedBanner}</div>;
    return (
      <Banner tone="warning" actions={<Button size="sm" onClick={() => setResumeFor(turn.run_id)}>{t.resume.button}</Button>}>
        {t.resume.interruptedBanner}
      </Banner>
    );
  };

  const post = async (body: string) => {
    const res = await rest.postMessage(id, { text: body });
    if ("queued" in res) {
      toast({ tone: "info", text: t.composer.queuedToast(res.queued.position) });
      void queryClient.invalidateQueries({ queryKey: chatKeys.queue(id) });
    } else if (res.run.status === "cancelled") {
      // 시작하는 동안 대화가 지워졌을 수 있다(서버는 404로 알리지만 취소된 Run만 돌려주는 경로도 확인한다).
      await rest.getConversation(id);
    }
    feed.refresh();
  };

  const [unresolved, setUnresolved] = useState<UnresolvedBackend | null>(null);
  const [chooserError, setChooserError] = useState<string | undefined>(undefined);
  const [choosing, setChoosing] = useState(false);
  const saveDefaultBackend = useSaveDefaultBackend();
  const chooseBackend = async (backendId: string) => {
    setChoosing(true);
    setChooserError(undefined);
    try {
      await saveDefaultBackend(backendId);
    } catch (e) {
      setChooserError(describeError(e, appMessages.backendChooser.saveFailed).message);
      setChoosing(false);
      return;
    }
    setChoosing(false);
    if (changingBackend) {
      // 안내줄의 [백엔드 바꾸기]로 연 카드: 기본값만 바꾸고 메시지는 다시 보내지 않는다
      setChangingBackend(false);
      toast({ tone: "info", text: t.composer.backendChanged });
      return;
    }
    setUnresolved(null);
    await send(false);
  };

  const send = async (asMessage: boolean) => {
    const body = text;
    if (body.trim() === "" || sending) return;
    setSending(true);
    setNotice(undefined);
    setRejectedAt(undefined);
    setUnresolved(null);
    try {
      if (target !== null && mode === ANSWER_MODES.answer && !asMessage) {
        const ok = await respondState.respond(target.interaction, buildResponse(target.descriptor, body));
        if (!ok) return;
      } else {
        await post(body);
      }
      setText("");
    } catch (e) {
      if (e instanceof ApiError && e.isConversationBusy) setRejectedAt(turnMark(activeTurn ?? turns[turns.length - 1]));
      else if (e instanceof ApiError && e.status === 404) {
        toast({ tone: "info", text: t.conversation.deleted });
        props.onGone();
      } else if (unresolvedBackendOf(e) !== undefined) {
        // 백엔드 미지정은 실패가 아니다: 입력을 그대로 두고 해결 카드를 띄운다(고르면 같은 메시지를 다시 보낸다)
        setUnresolved(unresolvedBackendOf(e) ?? null);
        setChooserError(undefined);
      } else {
        const view = describeError(e, target !== null && mode === ANSWER_MODES.answer && !asMessage ? t.composer.answerFailed : t.composer.sendFailed);
        setNotice({ tone: "danger", text: view.message, fix: view.fix });
      }
    } finally {
      setSending(false);
    }
  };

  // ---- 중지 ----
  const [cancelling, setCancelling] = useState<readonly string[]>([]);
  const [confirmStop, setConfirmStop] = useState<{ runId: string; pending: number; nested: boolean } | null>(null);
  const cancelRun = async (runId: string) => {
    setCancelling((cur) => [...cur, runId]);
    try {
      await rest.cancelRun(runId);
      feed.refresh();
    } catch (e) {
      setCancelling((cur) => cur.filter((r) => r !== runId));
      toast({ tone: "danger", text: describeError(e, t.turn.stopFailed).message });
    }
  };
  const requestStop = (runId: string) => {
    const n = (turns.find((turn) => turn.run_id === runId)?.interactions ?? []).filter((i) => i.status === "pending").length;
    // 진행 중인 중첩 팀(자식 실행) 칩이 있으면 확인 문구에 한 줄을 더한다. 취소는 루트 실행 하나에 보낸다(서버가 후손에 전파)
    const nested = hasRunningChild(feed.progress[runId] ?? []);
    if (n > 0) setConfirmStop({ runId, pending: n, nested });
    else void cancelRun(runId);
  };
  const cancellingRunIds = cancelling.filter((runId) => isActiveStatus(turns.find((turn) => turn.run_id === runId)?.status));

  // ---- 카드 포커스·스크롤 ----
  const [focusId, setFocusId] = useState<string | undefined>();
  const focusOldestPending = useCallback(() => {
    const first = pending[0];
    if (!first) return;
    setFocusId(first.id);
    setTimeout(() => setFocusId(undefined), 50);
  }, [pending]);
  const lastToken = useRef(props.focusPendingToken);
  useEffect(() => {
    if (props.focusPendingToken !== lastToken.current) {
      lastToken.current = props.focusPendingToken;
      focusOldestPending();
    }
  }, [props.focusPendingToken, focusOldestPending]);
  // 대화를 열 때 마지막 응답 대기 카드가 있으면 거기로 스크롤(포커스는 입력창에 둔다)
  const scrolledOpen = useRef(false);
  useEffect(() => {
    if (scrolledOpen.current || feed.loading) return;
    scrolledOpen.current = true;
    const last = pending[pending.length - 1];
    if (last) document.querySelector<HTMLElement>(`[data-interaction-id="${CSS.escape(last.id)}"]`)?.scrollIntoView?.({ block: "center" });
  }, [feed.loading, pending]);

  // ---- 메뉴·대화상자 ----
  const [renaming, setRenaming] = useState(false);
  const [teamDialog, setTeamDialog] = useState(false);
  const [teamBusy, setTeamBusy] = useState(false);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const guarded = async (fn: () => Promise<unknown>, failed: string) => {
    try {
      await fn();
    } catch (e) {
      toast({ tone: "danger", text: describeError(e, failed).message });
    }
  };

  useShortcuts([
    { id: "chat.stop", scope: "chat", keys: "Ctrl+Shift+X", titleKey: "shortcuts.chatStop", modifierRequired: true, run: () => activeTurn && requestStop(activeTurn.run_id) },
    { id: "chat.focusComposer", scope: "chat", keys: "/", titleKey: "shortcuts.chatFocusComposer", run: () => {
        if (!document.activeElement?.closest(".chat-list")) composer.current?.focus();
      },
    },
  ]);

  // F2 = 제목 편집, `[` `]` = 이전/다음 턴으로 포커스(입력 중에는 글자 입력으로 처리)
  const onPaneKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.matches("input, textarea, select, [contenteditable], [data-ac-editable]") || target.closest("[data-ac-editable]")) return;
    if (e.key === "F2") {
      e.preventDefault();
      setRenaming(true);
    } else if ((e.key === "[" || e.key === "]") && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const articles = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("article[data-run-id]"));
      if (articles.length === 0) return;
      e.preventDefault();
      const current = articles.findIndex((a) => a.contains(document.activeElement));
      const next = articles[Math.min(articles.length - 1, Math.max(0, (current < 0 ? (e.key === "[" ? articles.length : -1) : current) + (e.key === "]" ? 1 : -1)))];
      next?.setAttribute("tabindex", "-1");
      next?.focus();
    }
  };
  const focusMessages = () => document.querySelector<HTMLElement>(".chat-pane [role='region']")?.focus();
  const resendAsMessage = (interaction: Interaction) => {
    setText(quoteForResend(interaction, labelOf(interaction), t.interaction.resendQuote, t.interaction.resendOptions));
    setMode(ANSWER_MODES.message);
    setTimeout(() => composer.current?.focus(), 0);
  };

  // ---- 상태별 화면 ----
  if (conversation.error instanceof ApiError && conversation.error.status === 404) {
    return (
      <div className="chat-pane">
        <div className="app-empty">
          <h2 className="app-block-title">{t.conversation.notFound}</h2>
          <Button variant="primary" onClick={props.onGone}>{t.conversation.toList}</Button>
        </div>
      </div>
    );
  }
  if (conversation.error) {
    const view = describeError(conversation.error, t.conversation.loadFailed);
    return (
      <div className="chat-pane">
        <ErrorBlock title={t.conversation.loadFailed} message={view.message} fix={view.fix} details={errorDetails(view)} detailsLabel={appMessages.common.details} retryLabel={appMessages.common.retry} onRetry={() => void conversation.refetch()} />
      </div>
    );
  }

  const replyLabelTable = appMessages.settings.replyDisplayPreview as Record<string, string>;
  const moreFooter = (
    <span className="chat-menu-readonly">
      {t.menu.replyDisplay(replyLabelTable[replyDisplay] ?? replyDisplay)} <Link to={`${chatPaths.settings()}#chat`}>{t.menu.replyDisplayLink}</Link>
    </span>
  );

  const lastRunId = conversation.data?.last_run_id ?? lastTurn?.run_id;
  // 답변 연결이 없으면 실행은 되지만 결과가 채팅에 나오지 않는다(막지는 않는다). 계획 요약이 읽힌 뒤에만 판단한다
  const noAnswer = !noEntry && !teamMissing && summary !== undefined && summary.answers.length === 0;
  const disabledReason = teamMissing ? t.composer.teamDeleted : noEntry ? t.composer.noEntryBanner : archived ? t.composer.archived : undefined;
  const inputDisabled = conversation.data === undefined || disabledReason !== undefined;
  const queuedCount = queuedRows.length - heldRows.length;
  const composerNotice: Notice | undefined = notice ?? (queuedCount > 0 ? { tone: "info", text: t.composer.queued(queuedCount) } : undefined);

  const errors: Record<string, string> = {};
  const errorActions: Record<string, { label: string; runId: string }> = {};
  const footerNotes: Record<string, string> = {};
  for (const turn of turns) {
    if (turn.status === "failed") {
      const message = feed.errors[turn.run_id] ?? t.turn.genericFailure;
      // 실패가 중첩 팀 자식 실행에서 났으면(자식 최종 상태 failed) 그 사실과 자식 실행으로 가는 단추를 보인다
      const failedChild = failedChildOf(feed.progress[turn.run_id] ?? []);
      errors[turn.run_id] = failedChild === undefined ? message : `${dm.chat.childFailed(failedChild.name)} — ${message}`;
      if (failedChild !== undefined) errorActions[turn.run_id] = { label: dm.chat.childFailedAction, runId: failedChild.runId };
    }
    const handled = countHandled(feed.progress[turn.run_id] ?? []);
    if (handled > 0) footerNotes[turn.run_id] = dm.chat.handledFooter(handled);
  }

  return (
    <div className="chat-pane" onKeyDown={onPaneKeyDown}>
      <ChatHeader
        title={title}
        renaming={renaming}
        onRenamingChange={setRenaming}
        onRename={(next) => void guarded(() => actions.rename(id, next), appMessages.common.requestFailed)}
        teamName={teamMissing ? undefined : team?.name}
        teamHref={team ? chatPaths.team(team.id) : undefined}
        runHref={lastRunId ? chatPaths.run(lastRunId) : undefined}
        waitingCount={pending.length}
        onJumpToPending={focusOldestPending}
        listOpen={props.listOpen}
        onToggleList={props.onToggleList}
        teamMenu={[{ id: "change-team", label: t.menu.changeTeam, disabled: activeTurn !== undefined, ...(activeTurn !== undefined ? { hint: t.switchTeam.blocked } : {}), onSelect: () => { setTeamError(null); setTeamDialog(true); } }]}
        moreMenu={[
          { id: "rename", label: t.menu.rename, onSelect: () => setRenaming(true) },
          { id: "same-team", label: t.menu.sameTeamNew, disabled: team === undefined, onSelect: () => conversation.data && props.onNewWithTeam(conversation.data.graph_id) },
          { id: "archive", label: archived ? t.menu.unarchive : t.menu.archive, onSelect: () => void guarded(() => actions.setArchived(id, !archived), appMessages.common.requestFailed) },
          { id: "runs", label: t.menu.runsFilter, onSelect: () => void navigate(chatPaths.runsOfConversation(id)) },
          { id: "delete", label: t.menu.delete, danger: true, onSelect: () => setConfirmDelete(true) },
        ]}
        moreFooter={moreFooter}
      />
      {teamBadge !== undefined && !badgeNoteDismissed ? (
        <Banner
          tone="info"
          actions={
            <>
              <Button size="sm" onClick={() => { setChooserError(undefined); setChangingBackend(true); }}>{t.composer.backendChange}</Button>
              <Button size="sm" variant="ghost" aria-label={t.composer.dismissNote} onClick={() => { storage.set(badgeNoteKey, "1"); setBadgeNoteDismissed(true); }}>×</Button>
            </>
          }
        >
          <span data-testid="backend-badge-note">{t.composer.backendBadgeNote(teamBadge)}</span>
        </Banner>
      ) : null}
      {feed.error && turns.length === 0 ? (
        <ErrorBlock title={t.conversation.turnsLoadFailed} message={describeError(feed.error, t.conversation.turnsLoadFailed).message} retryLabel={appMessages.common.retry} onRetry={feed.refetch} />
      ) : feed.loading ? (
        <div className="chat-loading" role="status" aria-busy="true"><Spinner /><span>{t.conversation.loading}</span></div>
      ) : (
        <MessageList
          turns={turns}
          replyDisplay={replyDisplay}
          streaming={feed.streaming}
          progress={chipPart.visible ? feed.progress : NO_PROGRESS}
          queued={queuedRows}
          onCancelQueued={(key) => cancelQueued([key])}
          onReleaseQueued={(key) => releaseQueued([key])}
          onRecallQueued={recallQueued}
          queuedBusy={queuedBusy}
          queuedErrors={queuedErrors}
          queuedDisabled={!connected}
          renderTurnNotice={renderTurnNotice}
          interactionDescriptors={descriptorRecord}
          renderInteraction={(interaction, descriptor) => !cardPart.visible ? null : (
            <InteractionItem
              interaction={interaction}
              descriptor={descriptor}
              now={nowMs / 1000}
              actorLabel={labelOf(interaction)}
              {...(feed.nestedOrigin(interaction) ? { contextChip: { text: dm.chat.nestedChip, title: dm.chat.nestedChipHint(feed.nestedOrigin(interaction)!.path.join(" › ")) } } : {})}
              onRespond={async (i, response) => void (await respondState.respond(i, response))}
              errors={respondState.errorsOf(interaction.id)}
              disabled={!connected}
              onEscape={() => composer.current?.focus()}
              {...(interaction.status === "expired" && interaction.close_reason === "interrupted" && lastTurn && lastTurn.interactions?.some((x) => x.id === interaction.id) ? { onResendAsMessage: resendAsMessage } : {})}
            />
          )}
          agentView={agentView}
          onOpenRun={(runId, nodeId, edgeId) => void navigate(chatPaths.run(runId, nodeId?.replace(/#\d+$/, ""), edgeId))}
          onCancelTurn={requestStop}
          cancellingRunIds={cancellingRunIds}
          onResendText={(value) => {
            setText(value);
            composer.current?.focus();
          }}
          onLoadOlder={feed.loadOlder}
          loadingOlder={feed.loadingOlder}
          hasMore={feed.hasMore}
          {...(focusId ? { focusInteractionId: focusId } : {})}
          errors={errors}
          errorActions={errorActions}
          footerNotes={footerNotes}
          now={nowMs / 1000}
          empty={<EmptyConversation teamName={team?.name} description={team?.description} summary={summary} summaryLoading={plan.isLoading} summaryFailed={plan.isError} onRetrySummary={() => void plan.refetch()} />}
        />
      )}
      <div className="chat-composer">
        {heldRows.length > 0 ? (
          <Banner
            tone="warning"
            actions={
              <>
                <Button size="sm" disabled={!connected || queuedBusy.length > 0} title={connected ? undefined : t.held.disconnected} onClick={() => releaseQueued(heldRows.map((q) => q.key))}>{t.held.releaseAll}</Button>
                <Button size="sm" disabled={!connected || queuedBusy.length > 0} title={connected ? undefined : t.held.disconnected} onClick={() => setConfirmCancelAll(true)}>{t.held.cancelAll}</Button>
              </>
            }
          >
            <span role="status">⏸ {t.held.banner(heldRows.length)}</span>
          </Banner>
        ) : null}
        {disabledReason !== undefined ? (
          <Banner
            tone="warning"
            actions={
              archived && !teamMissing && !noEntry ? (
                <Button size="sm" onClick={() => void guarded(() => actions.setArchived(id, false), appMessages.common.requestFailed)}>{t.composer.unarchive}</Button>
              ) : noEntry && team ? (
                <Link className="ac-btn" data-variant="secondary" data-size="sm" to={chatPaths.team(team.id)}>{t.composer.editTeam}</Link>
              ) : undefined
            }
          >
            {disabledReason}
          </Banner>
        ) : null}
        {noAnswer && team ? (
          <Banner tone="warning" actions={<Link className="ac-btn" data-variant="secondary" data-size="sm" to={chatPaths.team(team.id)}>{t.composer.connectInTeam}</Link>}>
            {t.composer.noAnswerBanner}
          </Banner>
        ) : null}
        {sendPart.off && sendPart.note !== undefined ? <Banner tone="warning">{sendPart.note}</Banner> : null}
        {rejectBusy ? (
          <Banner tone="info" actions={<Link className="ac-btn" data-variant="secondary" data-size="sm" to={`${chatPaths.settings()}#chat`}>{t.composer.viewSettings}</Link>}>
            {t.composer.rejectBusy}
          </Banner>
        ) : null}
        {unresolved !== null ? (
          <ConnectedBackendChooserCard options={unresolved.options} nodeLabels={unresolved.labels} busy={choosing} error={chooserError} onConfirm={(b) => void chooseBackend(b)} />
        ) : changingBackend ? (
          <ConnectedBackendChooserCard mode="change" options={backendList.data ?? []} initialId={teamBackend ?? defaultBackend} busy={choosing} error={chooserError} onConfirm={(b) => void chooseBackend(b)} />
        ) : null}
        {notice?.fix ? <FixButtons fix={notice.fix} /> : null}
        <Composer
          ref={composer}
          value={text}
          onChange={setText}
          onSend={() => void send(false)}
          sendKey={typeof chat.send_key === "string" ? chat.send_key : undefined}
          disabled={inputDisabled}
          sendDisabled={!connected || sendPart.disabled}
          {...(!connected ? { sendHint: t.composer.disconnected } : sendPart.note !== undefined ? { sendHint: sendPart.note } : {})}
          sending={sending}
          {...(composerNotice ? { busyNotice: composerNotice } : {})}
          {...(pending.length > 0 && target === null ? { pendingHint: t.composer.pendingHint(pending.length) } : {})}
          {...(target !== null ? { answerTarget: { label: labelOf(target.interaction), kindTitle: target.descriptor.title }, answerMode: mode } : {})}
          onSwitchToMessage={() => setMode(ANSWER_MODES.message)}
          onSwitchToAnswer={() => setMode(ANSWER_MODES.answer)}
          onSendAsMessage={() => {
            setMode(ANSWER_MODES.message);
            void send(true);
          }}
          onRecallLast={() => {
            const last = [...turns].reverse()[0];
            if (last) setText(last.user_text);
          }}
          onEscape={focusMessages}
          autoFocus
        />
      </div>
      <TeamPickerDialog
        open={teamDialog}
        title={t.switchTeam.title}
        confirmLabel={t.switchTeam.confirm}
        graphs={graphs.data ?? []}
        loading={graphs.isLoading}
        lastUsed={lastUsedByGraph(list.data ?? [])}
        preselectedId={conversation.data?.graph_id}
        currentId={conversation.data?.graph_id}
        notice={t.switchTeam.confirmBody}
        nowMs={nowMs}
        busy={teamBusy}
        error={teamError}
        teamsPath={chatPaths.teams()}
        renderIssues={(g) => <GraphIssuesPreview graph={g} />}
        onClose={() => setTeamDialog(false)}
        onConfirm={(graphId) => {
          setTeamBusy(true);
          setTeamError(null);
          actions
            .switchTeam(id, graphId)
            .then(() => {
              setTeamDialog(false);
              toast({ tone: "success", text: t.switchTeam.switchedToast(graphs.data?.find((g) => g.id === graphId)?.name ?? graphId) });
            })
            .catch((e: unknown) => setTeamError(describeError(e, t.switchTeam.failed).message))
            .finally(() => setTeamBusy(false));
        }}
      />
      <ConfirmDialog
        open={confirmDelete}
        danger
        title={t.remove.title}
        confirmLabel={t.remove.confirm}
        cancelLabel={appMessages.common.cancel}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          void guarded(async () => {
            await actions.remove(id);
            props.onGone();
          }, appMessages.common.requestFailed);
        }}
      >
        <p className="ac-text">{t.remove.body}</p>
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmCancelAll}
        danger
        title={t.held.cancelAllTitle}
        confirmLabel={t.held.cancelAllConfirm}
        cancelLabel={appMessages.common.cancel}
        onCancel={() => setConfirmCancelAll(false)}
        onConfirm={() => {
          setConfirmCancelAll(false);
          cancelQueued(heldRows.map((q) => q.key));
        }}
      >
        <p className="ac-text">{t.held.cancelAllBody(heldRows.length)}</p>
      </ConfirmDialog>
      {resumeFor !== null ? (
        <ResumeDialog
          open
          runId={resumeFor}
          onClose={() => setResumeFor(null)}
          onNotify={(text) => toast({ tone: "info", text })}
          onResumed={() => {
            setResumeFor(null);
            feed.refresh();
          }}
        />
      ) : null}
      <ConfirmDialog
        open={confirmStop !== null}
        danger
        title={t.turn.stopConfirmTitle}
        confirmLabel={t.turn.stopConfirm}
        cancelLabel={appMessages.common.cancel}
        onCancel={() => setConfirmStop(null)}
        onConfirm={() => {
          const run = confirmStop;
          setConfirmStop(null);
          if (run) void cancelRun(run.runId);
        }}
      >
        <p className="ac-text">{t.turn.stopConfirmBody(confirmStop?.pending ?? 0)}</p>
        {confirmStop?.nested ? <p className="ac-text">{dm.chat.stopNested}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
