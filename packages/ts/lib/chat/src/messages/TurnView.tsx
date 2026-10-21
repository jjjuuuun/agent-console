import { useState, type KeyboardEvent, type ReactNode } from "react";
import { ChatIcon } from "../shared/Icon";
import { fill, mergeMessages, showDuration } from "../shared/util";
import { defaultChatMessages, type ChatMessages } from "./messages";
import { ProgressStrip } from "./ProgressStrip";
import { ReplyGroup } from "./ReplyGroup";
import type { AgentView, ChatTurn, Interaction, InteractionKindDescriptor, ProgressStep, ReplyItem } from "./types";

const ACTIVE = new Set(["running", "waiting", "paused", "queued"]);

export interface TurnViewProps {
  turn: ChatTurn;
  replyDisplay: string;
  /** 노드 id → 스트리밍 중인 텍스트. 같은 `node_id`의 답변 본문을 대신하고 캐럿을 붙인다(활성 턴만). */
  streaming?: Record<string, string>;
  progress?: readonly ProgressStep[];
  interactionDescriptors?: Record<string, InteractionKindDescriptor>;
  /** 상호작용 카드를 그린다. 앱이 `InteractionCard`로 주입한다. 없으면 카드를 그리지 않는다. */
  renderInteraction?: (interaction: Interaction, descriptor: InteractionKindDescriptor | undefined) => ReactNode;
  agentView: (agentId: string) => AgentView;
  onOpenRun?: (runId: string, nodeId?: string, edgeId?: string) => void;
  /** 진행 줄 중첩 팀 칩의 [실행 상세 ↗](자식 Run id). 없으면 링크(`child.href`)가 그대로 열린다. */
  onOpenChildRun?: (runId: string) => void;
  onCancelTurn?: (runId: string) => void;
  /** 중지 요청이 진행 중. */
  cancelling?: boolean;
  onResendText?: (text: string) => void;
  /** 실패 턴에 보일 서버 오류 문구. */
  errorText?: string;
  /** 현재 시각(epoch 초). 활성 턴 경과 시간 계산용. */
  now?: number;
  /** 실패 턴 오류 블록의 [원인 보기] 단추를 다른 실행으로 돌린다(예: 중첩 팀 자식 실행의 실패). 문구는 앱이 정한다. */
  errorAction?: { label: string; runId: string };
  /** 푸터 한 줄에 더하는 muted 문구(예: "실패 1건 처리됨"). */
  footerNote?: string;
  /** 푸터 위에 붙는 앱 알림(예: 끊긴 턴의 이어 가기 배너). */
  notice?: ReactNode;
  /** 이 턴이 바로 앞 턴을 이어 간 것이면 true: 같은 사용자 메시지를 다시 그리지 않는다. */
  continuation?: boolean;
  /** 내 메시지 아래 시각 문구(epoch 초 -> 문자열). 기본은 24시간 `HH:mm`(로캘 무관). */
  formatTime?: (epochSeconds: number) => string;
  messages?: Partial<ChatMessages>;
}

/** 기본 시각 문구. */
const defaultFormatTime = (sec: number) => {
  const d = new Date(sec * 1000);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

/** 한 턴: 내 메시지(오른쪽 말풍선) + 진행 요약 + 답변 + 상호작용 카드 + 푸터(실행 상세 링크는 턴당 하나). 표현 전용. */
export function TurnView(props: TurnViewProps) {
  const { turn, replyDisplay, streaming, progress, interactionDescriptors, renderInteraction, agentView, onOpenRun, onCancelTurn, cancelling, onResendText, errorText, now, notice, continuation } = props;
  const m = mergeMessages(defaultChatMessages, props.messages);
  const active = ACTIVE.has(turn.status);
  const [textOpen, setTextOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [stripOpen, setStripOpen] = useState<boolean | undefined>(undefined);

  const replies: ReplyItem[] = (turn.replies ?? []).map((r) => {
    const live = active ? streaming?.[r.node_id] : undefined;
    return live !== undefined ? { ...r, text: live, streaming: true } : r;
  });
  const interactions = [...(turn.interactions ?? [])].sort((a, b) => a.created_at - b.created_at);
  const pendingCount = interactions.filter((i) => i.status === "pending").length;
  const longText = turn.user_text.split("\n").length > 12;
  const collapsedStrip = stripOpen === undefined ? !active : !stripOpen;

  const end = turn.ended_at ?? (active ? now : undefined);
  const elapsed = turn.started_at != null && end != null ? end - turn.started_at : undefined;
  const u = turn.usage;
  const tokens = u ? (u.total_tokens ?? (u.input_tokens != null || u.output_tokens != null ? (u.input_tokens ?? 0) + (u.output_tokens ?? 0) : undefined)) : undefined;
  const totalOnly = !!u && u.total_tokens != null && u.input_tokens == null && u.output_tokens == null;

  const toolbar = (
    <div className="ac-chat-me-meta" data-reveal="hover">
      {longText ? (
        <button type="button" className="ac-btn ac-icon-btn" data-variant="ghost" data-size="sm" aria-expanded={textOpen} aria-label={textOpen ? m.showLess : m.showMore} title={textOpen ? m.showLess : m.showMore} onClick={() => setTextOpen(!textOpen)}>
          <ChatIcon name="expand" />
        </button>
      ) : null}
      {turn.started_at != null ? (
        <time dateTime={new Date(turn.started_at * 1000).toISOString()} title={new Date(turn.started_at * 1000).toLocaleString()}>
          {(props.formatTime ?? defaultFormatTime)(turn.started_at)}
        </time>
      ) : null}
      <button
        type="button"
        className="ac-btn ac-icon-btn"
        data-variant="ghost"
        data-size="sm"
        aria-label={copied ? m.copied : m.copy}
        title={copied ? m.copied : m.copy}
        onClick={() => {
          void navigator.clipboard?.writeText(turn.user_text);
          setCopied(true);
        }}
      >
        <ChatIcon name={copied ? "check" : "copy"} />
      </button>
      {onResendText ? (
        <button type="button" className="ac-btn ac-icon-btn" data-variant="ghost" data-size="sm" aria-label={m.resend} title={m.resend} onClick={() => onResendText(turn.user_text)}>
          <ChatIcon name="undo" />
        </button>
      ) : null}
    </div>
  );
  // 응답 대기 카드가 보이는 동안은 카드가 이미 말하므로 푸터의 대기 개수·경과 시간은 숨긴다(§7.6).
  const cardsSpeak = pendingCount > 0 && !!renderInteraction;
  const dur = cardsSpeak ? null : showDuration(elapsed != null ? elapsed * 1000 : undefined, m.units);

  // 턴에 포커스가 있을 때만: C 복사, R 다시 보내기, Alt+Enter 실행 상세(§7.8). ↑↓ 이동은 MessageList가 맡는다.
  const onTurnKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.target !== e.currentTarget || e.ctrlKey || e.metaKey) return;
    if (e.altKey && e.key === "Enter" && onOpenRun) {
      e.preventDefault();
      onOpenRun(turn.run_id);
    } else if (!e.altKey && (e.key === "c" || e.key === "C")) {
      void navigator.clipboard?.writeText(turn.user_text);
      setCopied(true);
    } else if (!e.altKey && (e.key === "r" || e.key === "R") && onResendText) {
      e.preventDefault();
      onResendText(turn.user_text);
    }
  };

  return (
    <article data-run-id={turn.run_id} data-status={turn.status} aria-label={turn.user_text.slice(0, 40)} className="ac-chat-turn" tabIndex={0} onKeyDown={onTurnKey}>
      {continuation ? null : (
        <div className="ac-chat-me">
          <div className="ac-chat-bubble ac-pre" role="group" aria-label={m.yourMessage} data-clamped={longText && !textOpen ? "true" : undefined}>
            {turn.user_text}
          </div>
          {toolbar}
        </div>
      )}

      {turn.resumed_from ? (
        <button type="button" className="ac-chat-chip ac-chat-resumed" data-tone="info" data-testid="resumed-chip" disabled={!onOpenRun} onClick={() => onOpenRun?.(turn.resumed_from as string)}>
          <ChatIcon name="undo" size={12} />
          {fill(m.resumedChip, { run: turn.resumed_from.slice(0, 8) })}
        </button>
      ) : null}

      {progress && progress.length > 0 ? (
        <ProgressStrip
          steps={progress}
          collapsed={collapsedStrip}
          onToggle={() => setStripOpen(collapsedStrip)}
          onOpen={onOpenRun ? (step) => onOpenRun(step.openTarget?.runId ?? turn.run_id, step.openTarget?.nodeId ?? (step.openTarget?.edgeId === undefined ? step.key : undefined), step.openTarget?.edgeId) : undefined}
          onOpenChild={props.onOpenChildRun ? (child) => props.onOpenChildRun?.(child.runId) : undefined}
          messages={props.messages}
        />
      ) : null}

      {replies.length > 0 ? (
        <ReplyGroup replies={replies} display={replyDisplay} turnDone={!active} agentView={agentView} onOpenRun={onOpenRun ? (nodeId) => onOpenRun(turn.run_id, nodeId) : undefined} messages={props.messages} />
      ) : null}

      {turn.status === "failed" && errorText ? (
        <div role="alert" className="ac-chat-error">
          <div className="ac-clamp-2">{errorText}</div>
          {onOpenRun ? (
            <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" onClick={() => onOpenRun(props.errorAction?.runId ?? turn.run_id)}>
              {props.errorAction?.label ?? m.errorOpenRun}
              <ChatIcon name="external-link" size={12} />
            </button>
          ) : null}
        </div>
      ) : null}

      {renderInteraction && interactions.length > 0 ? (
        <div className="ac-chat-cards">
          {interactions.map((i) => (
            <div key={i.id}>{renderInteraction(i, interactionDescriptors?.[i.kind])}</div>
          ))}
        </div>
      ) : null}

      {notice}

      <div className="ac-chat-footer">
        <span className="ac-status-icon" data-status={turn.status} data-status-kind="run" data-size="14" aria-hidden="true" />
        <span data-testid="turn-status">{m.turnStatus[turn.status] ?? turn.status}</span>
        {dur ? <span className="ac-num">· {dur}</span> : null}
        {props.footerNote ? <span data-part="footer-note">· {props.footerNote}</span> : null}
        {tokens != null ? (
          <span className="ac-num">
            · {fill(m.tokens, { n: tokens.toLocaleString("en-US") })}
            {totalOnly ? ` (${m.someTokensTotalOnly})` : ""}
          </span>
        ) : null}
        {onOpenRun ? (
          <button type="button" className="ac-chat-footer-link" onClick={() => onOpenRun(turn.run_id)}>
            {m.openRun}
            <ChatIcon name="external-link" size={12} />
          </button>
        ) : null}
        {active && onCancelTurn ? (
          <button type="button" className="ac-btn" data-variant="danger" data-size="sm" disabled={cancelling} aria-busy={cancelling || undefined} onClick={() => onCancelTurn(turn.run_id)}>
            {cancelling ? null : <ChatIcon name="stop" size={12} />}
            {cancelling ? m.stopping : m.stop}
          </button>
        ) : null}
      </div>
    </article>
  );
}
