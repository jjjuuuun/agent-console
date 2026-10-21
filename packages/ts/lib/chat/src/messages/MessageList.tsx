import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ChatIcon } from "../shared/Icon";
import { fill, mergeMessages } from "../shared/util";
import { defaultChatMessages, type ChatMessages } from "./messages";
import { TurnView } from "./TurnView";
import type { AgentView, ChatTurn, Interaction, InteractionKindDescriptor, ProgressStep, QueuedRow } from "./types";

export interface MessageListProps {
  turns: readonly ChatTurn[];
  /** `chat.reply_display` 값. 모르는 값은 `separate`. */
  replyDisplay: string;
  /** 스트리밍 중인 텍스트(답변 노드 id → 텍스트). */
  streaming?: Record<string, string>;
  /** 실행 id → 진행 줄 단계. 방식 라벨은 앱이 연결 종류 `title`에서 채운다. */
  progress?: Record<string, readonly ProgressStep[]>;
  queued?: readonly QueuedRow[];
  /** 대기열 항목 취소 API가 있을 때만 넘긴다. */
  onCancelQueued?: (key: string) => void;
  /** 멈춘(`held`) 대기열 항목 실행. 없으면 [실행] 버튼을 그리지 않는다. */
  onReleaseQueued?: (key: string) => void;
  /** 멈춘 항목의 텍스트를 입력창으로 가져오고 항목은 취소한다. */
  onRecallQueued?: (key: string) => void;
  /** 처리 중인 대기열 항목 key(버튼 비활성). */
  queuedBusy?: readonly string[];
  /** 대기열 항목 key -> 서버 오류 문구(행 아래 한 줄). */
  queuedErrors?: Record<string, string>;
  /** 버튼 비활성(예: 연결 끊김). */
  queuedDisabled?: boolean;
  /** 턴 푸터 위에 붙는 앱 알림(끊긴 턴의 이어 가기 배너 등). */
  renderTurnNotice?: (turn: ChatTurn) => ReactNode;
  interactionDescriptors?: Record<string, InteractionKindDescriptor>;
  renderInteraction?: (interaction: Interaction, descriptor: InteractionKindDescriptor | undefined) => ReactNode;
  agentView: (agentId: string) => AgentView;
  onOpenRun?: (runId: string, nodeId?: string, edgeId?: string) => void;
  /** 진행 줄 중첩 팀 칩의 [실행 상세 ↗](자식 Run id). */
  onOpenChildRun?: (runId: string) => void;
  onCancelTurn?: (runId: string) => void;
  cancellingRunIds?: readonly string[];
  onResendText?: (text: string) => void;
  onLoadOlder?: () => void;
  loadingOlder?: boolean;
  hasMore?: boolean;
  /** 지정한 상호작용 카드로 스크롤하고 첫 입력 요소에 포커스한다. */
  focusInteractionId?: string;
  /** 실행 id → 실패 오류 문구. */
  errors?: Record<string, string>;
  /** 실행 id → 오류 블록 단추를 돌릴 곳(중첩 팀 자식 실행의 실패 등). */
  errorActions?: Record<string, { label: string; runId: string }>;
  /** 실행 id → 턴 푸터 muted 문구(예: "실패 1건 처리됨"). */
  footerNotes?: Record<string, string>;
  /** 현재 시각(epoch 초). */
  now?: number;
  /** 내 메시지 시각 문구(epoch 초 -> 문자열). */
  formatTime?: (epochSeconds: number) => string;
  /** 턴이 없을 때 보일 내용. */
  empty?: ReactNode;
  /** 맨 아래로 간주하는 여유 픽셀. */
  bottomThreshold?: number;
  messages?: Partial<ChatMessages>;
}

/** 맨 아래에 붙어 있는지. */
export function isNearBottom(el: { scrollHeight: number; scrollTop: number; clientHeight: number }, threshold = 24): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}

/** 대화의 턴 목록. 맨 아래에 붙어 있을 때만 따라가고, 아니면 pill을 보인다. */
export function MessageList(props: MessageListProps) {
  const { turns, queued, interactionDescriptors, onLoadOlder, loadingOlder, hasMore, focusInteractionId, bottomThreshold = 24 } = props;
  const m = mergeMessages(defaultChatMessages, props.messages);
  const scroller = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const [showNew, setShowNew] = useState(false);
  const [showPending, setShowPending] = useState(false);
  const seenPending = useRef<Set<string> | null>(null);
  const firstPendingId = useRef<string | undefined>(undefined);

  const scrollToBottom = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    atBottom.current = true;
    setShowNew(false);
    setShowPending(false);
  }, []);

  const scrollToInteraction = useCallback((id: string, focus: boolean) => {
    const card = scroller.current?.querySelector<HTMLElement>(`[data-interaction-id="${CSS.escape(id)}"]`);
    if (!card) return;
    card.scrollIntoView?.({ block: "center" });
    if (focus) card.querySelector<HTMLElement>("input, textarea, button, [tabindex]")?.focus();
    setShowPending(false);
  }, []);

  // 내용이 바뀔 때: 붙어 있으면 따라가고, 아니면 pill.
  const contentKey = `${turns.length}|${props.streaming ? Object.values(props.streaming).join("").length : 0}|${turns.reduce((n, t) => n + (t.replies?.length ?? 0) + (t.interactions?.length ?? 0), 0)}|${queued?.length ?? 0}`;
  const prevKey = useRef(contentKey);
  useLayoutEffect(() => {
    if (prevKey.current === contentKey) return;
    prevKey.current = contentKey;
    if (atBottom.current) scrollToBottom();
    else setShowNew(true);
  }, [contentKey, scrollToBottom]);

  // 새 응답 대기 카드: 맨 아래면 카드로 스크롤(포커스는 옮기지 않음), 아니면 pill 전환.
  const pendingIds = turns.flatMap((t) => (t.interactions ?? []).filter((i) => i.status === "pending").map((i) => i.id));
  const pendingKey = pendingIds.join(",");
  useEffect(() => {
    if (seenPending.current === null) {
      seenPending.current = new Set(pendingIds);
      firstPendingId.current = pendingIds[0];
      return;
    }
    const fresh = pendingIds.filter((id) => !seenPending.current?.has(id));
    pendingIds.forEach((id) => seenPending.current?.add(id));
    firstPendingId.current = pendingIds[0];
    const target = fresh[0];
    if (!target) return;
    if (atBottom.current) scrollToInteraction(target, false);
    else setShowPending(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingKey]);

  useEffect(() => {
    if (focusInteractionId) scrollToInteraction(focusInteractionId, true);
  }, [focusInteractionId, scrollToInteraction]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    atBottom.current = isNearBottom(el, bottomThreshold);
    if (atBottom.current) {
      setShowNew(false);
      setShowPending(false);
    }
    if (el.scrollTop <= 0 && hasMore && !loadingOlder) onLoadOlder?.();
  };

  const cancelling = new Set(props.cancellingRunIds);

  // ↑↓: 턴(article) 사이 이동. 입력 요소 안에서는 건드리지 않는다.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if ((e.key !== "ArrowUp" && e.key !== "ArrowDown") || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    const target = e.target as HTMLElement;
    if (target.matches("input, textarea, select, button, a, [contenteditable]")) return;
    const turnsEls = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("article.ac-chat-turn"));
    if (turnsEls.length === 0) return;
    const at = turnsEls.indexOf(target.closest<HTMLElement>("article.ac-chat-turn") as HTMLElement);
    const next = turnsEls[at < 0 ? (e.key === "ArrowUp" ? turnsEls.length - 1 : 0) : Math.min(turnsEls.length - 1, Math.max(0, at + (e.key === "ArrowUp" ? -1 : 1)))];
    if (next && next !== target) {
      e.preventDefault();
      next.focus();
    }
  };

  return (
    <div className="ac-chat-list">
      <div ref={scroller} onScroll={onScroll} onKeyDown={onKeyDown} role="region" aria-label={m.listLabel} tabIndex={0} className="ac-chat-scroller">
        <div className="ac-chat-col">
          {loadingOlder ? <div className="ac-chat-note">{m.loadingOlder}</div> : null}
          {!hasMore && !loadingOlder && turns.length > 0 ? <div className="ac-chat-note">{m.startOfConversation}</div> : null}
          {turns.length === 0 && (queued?.length ?? 0) === 0 ? props.empty : null}
          {turns.map((turn, index) => (
            <TurnView
              key={turn.run_id}
              notice={props.renderTurnNotice?.(turn)}
              continuation={!!turn.resumed_from && turns[index - 1]?.run_id === turn.resumed_from}
              turn={turn}
              replyDisplay={props.replyDisplay}
              streaming={props.streaming}
              progress={props.progress?.[turn.run_id]}
              interactionDescriptors={interactionDescriptors}
              renderInteraction={props.renderInteraction}
              agentView={props.agentView}
              onOpenRun={props.onOpenRun}
              onOpenChildRun={props.onOpenChildRun}
              onCancelTurn={props.onCancelTurn}
              cancelling={cancelling.has(turn.run_id)}
              onResendText={props.onResendText}
              errorText={props.errors?.[turn.run_id]}
              {...(props.errorActions?.[turn.run_id] ? { errorAction: props.errorActions[turn.run_id]! } : {})}
              {...(props.footerNotes?.[turn.run_id] ? { footerNote: props.footerNotes[turn.run_id]! } : {})}
              {...(props.formatTime ? { formatTime: props.formatTime } : {})}
              now={props.now}
              messages={props.messages}
            />
          ))}
          {(queued ?? []).map((q) => {
            const busy = props.queuedBusy?.includes(q.key) === true;
            const error = props.queuedErrors?.[q.key];
            const off = busy || props.queuedDisabled === true;
            return (
              <div
                key={q.key}
                className="ac-chat-me"
                data-queued="true"
                data-held={q.held ? "true" : undefined}
                tabIndex={q.held ? 0 : undefined}
                onKeyDown={
                  q.held
                    ? (e) => {
                        if (e.target !== e.currentTarget || off) return;
                        if (e.key === "Enter" && props.onReleaseQueued) {
                          e.preventDefault();
                          props.onReleaseQueued(q.key);
                        } else if (e.key === "Delete" && props.onCancelQueued) {
                          e.preventDefault();
                          props.onCancelQueued(q.key);
                        }
                      }
                    : undefined
                }
              >
                <div className="ac-chat-bubble ac-pre" role="group" aria-label={m.yourMessage}>
                  {q.text}
                </div>
                <div className="ac-chat-queue">
                  <span className="ac-chat-chip">
                    {q.held ? <span aria-hidden="true">⏸ </span> : null}
                    {fill(q.held ? m.queuedHeldChip : m.queuedChip, { n: q.position })}
                  </span>
                  {q.held && props.onReleaseQueued ? (
                    <button type="button" className="ac-btn" data-variant="primary" data-size="sm" disabled={off} aria-busy={busy || undefined} onClick={() => props.onReleaseQueued?.(q.key)}>
                      {m.queuedRelease}
                    </button>
                  ) : null}
                  {props.onCancelQueued ? (
                    <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" disabled={off} onClick={() => props.onCancelQueued?.(q.key)}>
                      {q.held ? m.queuedCancelHeld : m.queuedCancel}
                    </button>
                  ) : null}
                  {q.held && props.onRecallQueued ? (
                    <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" disabled={off} onClick={() => props.onRecallQueued?.(q.key)}>
                      {m.queuedRecall}
                    </button>
                  ) : null}
                </div>
                {error === undefined ? null : (
                  <div role="alert" className="ac-chat-muted ac-chat-danger">
                    {error}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div aria-live="polite">
        {showPending ? (
          <button type="button" className="ac-btn ac-chat-float" data-tone="waiting" onClick={() => firstPendingId.current && scrollToInteraction(firstPendingId.current, true)}>
            ⏸ {m.jumpToPending}
          </button>
        ) : showNew ? (
          <button type="button" className="ac-btn ac-chat-float" onClick={scrollToBottom}>
            <ChatIcon name="chevron-down" /> {m.newContent}
          </button>
        ) : null}
      </div>
    </div>
  );
}
