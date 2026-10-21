import { useState, type ReactNode } from "react";
import { Avatar } from "../shared/Avatar";
import { ChatIcon } from "../shared/Icon";
import { fill, mergeMessages } from "../shared/util";
import { Markdown } from "./Markdown";
import { defaultChatMessages, type ChatMessages } from "./messages";
import { isIntermediate, isReplyExpanded, normalizeReplyDisplay, selectVisibleReplies } from "./replyLogic";
import type { AgentView, ReplyItem } from "./types";

export interface ReplyGroupProps {
  replies: readonly ReplyItem[];
  /** `chat.reply_display` 값. 모르는 값은 `separate`. */
  display: string;
  /** 턴이 끝났는지. 끝나면 `final=false`가 자동 접힌다. */
  turnDone: boolean;
  agentView: (agentId: string) => AgentView;
  onOpenRun?: (nodeId: string) => void;
  /** 사용자가 직접 펼치거나 접은 것(edge_id → 펼침). 주면 제어형. */
  expanded?: Record<string, boolean>;
  onExpandedChange?: (next: Record<string, boolean>) => void;
  /** `final_only`의 "중간 결과 N개 숨김" 문구. 없으면 messages 템플릿. */
  hiddenCountText?: string;
  messages?: Partial<ChatMessages>;
}

function ReplyHeader({ reply, agentView, m, withLabelOnly, actions }: { reply: ReplyItem; agentView: ReplyGroupProps["agentView"]; m: ChatMessages; withLabelOnly?: boolean; actions?: ReactNode }) {
  const agentId = reply.agent_id ?? reply.node_id;
  const view = agentView(agentId);
  const name = view.delegatedBy ? fill(m.delegatedBy, { parent: view.delegatedBy, name: view.name }) : view.parentName ? fill(m.insideOf, { parent: view.parentName, name: view.name }) : view.name;
  if (withLabelOnly) return <span className="ac-chat-reply-name ac-chat-muted">{reply.label || name}</span>;
  return (
    <div className="ac-chat-reply-head">
      <Avatar agentId={agentId} name={view.name} avatar={view.avatar} />
      <span className="ac-chat-reply-name">{name}</span>
      {view.role ? <span className="ac-chat-muted">{view.role}</span> : null}
      {view.badge ? <span className="ac-chat-chip" data-testid="reply-badge">{view.badge}</span> : null}
      {reply.label ? <span className="ac-chat-chip">{reply.label}</span> : null}
      {isIntermediate(reply) ? <span className="ac-chat-chip">{m.intermediate}</span> : null}
      {actions ? <span className="ac-chat-reply-actions">{actions}</span> : null}
    </div>
  );
}

/**
 * 한 턴의 답변을 `chat.reply_display`에 맞춰 그린다.
 * - separate: 답변마다 카드(정렬은 `order`, 중간 결과는 점선·접기)
 * - merged: 카드 하나에 구분 머리 줄로 합침
 * - final_only: `final` 답변만, 숨긴 개수 한 줄
 */
export function ReplyGroup({ replies, display, turnDone, agentView, onOpenRun, expanded, onExpandedChange, hiddenCountText, messages }: ReplyGroupProps) {
  const m = mergeMessages(defaultChatMessages, messages);
  const mode = normalizeReplyDisplay(display);
  const [local, setLocal] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const choice = expanded ?? local;
  const toggle = (reply: ReplyItem) => {
    const next = { ...choice, [reply.edge_id]: !isReplyExpanded(reply, turnDone, choice) };
    if (onExpandedChange) onExpandedChange(next);
    if (expanded === undefined) setLocal(next);
  };
  const { visible, hidden } = selectVisibleReplies(replies, mode);

  const toggleButton = (reply: ReplyItem, open: boolean) => (
    <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" aria-expanded={open} onClick={() => toggle(reply)}>
      {open ? m.collapse : m.expand}
    </button>
  );
  // 응답 단위 동작: 머리 오른쪽 아이콘(복사). 실행 상세 링크는 턴 푸터에 하나만 둔다.
  const actionsOf = (reply: ReplyItem, inter: boolean, open: boolean) =>
    reply.streaming && reply.text === "" ? null : (
      <>
        {inter ? toggleButton(reply, open) : null}
        <button
          type="button"
          className="ac-btn ac-icon-btn"
          data-variant="ghost"
          data-size="sm"
          aria-label={copiedId === reply.edge_id ? m.copied : m.copyReply}
          title={copiedId === reply.edge_id ? m.copied : m.copyReply}
          onClick={() => {
            void navigator.clipboard?.writeText(reply.text);
            setCopiedId(reply.edge_id);
          }}
        >
          <ChatIcon name={copiedId === reply.edge_id ? "check" : "copy"} />
        </button>
      </>
    );
  const body = (reply: ReplyItem) => (
    <Markdown text={reply.text} streaming={reply.streaming} messages={{ copy: m.copy, copied: m.copied }} />
  );
  const caret = (reply: ReplyItem) => (reply.streaming ? <span className="ac-caret" aria-hidden="true" /> : null);
  const preview = (reply: ReplyItem) => <div className="ac-ellipsis ac-chat-muted">{reply.text.split("\n").find((l) => l.trim()) ?? ""}</div>;

  const hiddenLine =
    hidden > 0 ? (
      <div className="ac-chat-hidden-line">
        {hiddenCountText ?? fill(m.intermediateHidden, { n: hidden })}
        {onOpenRun ? (
          <>
            {" — "}
            <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" onClick={() => onOpenRun(visible[0]?.node_id ?? replies[0]?.node_id ?? "")}>
              {m.intermediateHiddenLink} ↗
            </button>
          </>
        ) : null}
      </div>
    ) : null;

  if (mode === "merged") {
    if (visible.length === 0) return null;
    return (
      <div data-reply-display="merged" className="ac-chat-merged">
        {visible.map((reply) => {
          const inter = isIntermediate(reply);
          const open = isReplyExpanded(reply, turnDone, choice);
          return (
            <div key={reply.edge_id} data-intermediate={inter || undefined} className="ac-chat-merged-part">
              <div className="ac-chat-spread">
                <ReplyHeader reply={reply} agentView={agentView} m={m} withLabelOnly />
                <span className="ac-chat-reply-actions">{actionsOf(reply, inter, open)}</span>
              </div>
              {open ? (
                <>
                  {body(reply)}
                  {caret(reply)}
                </>
              ) : (
                preview(reply)
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div data-reply-display={mode} className="ac-chat-replies">
      {visible.map((reply) => {
        const inter = isIntermediate(reply);
        const open = isReplyExpanded(reply, turnDone, choice);
        return (
          <section key={reply.edge_id} aria-label={agentView(reply.agent_id ?? reply.node_id).name} data-intermediate={inter || undefined} className="ac-chat-reply">
            <ReplyHeader reply={reply} agentView={agentView} m={m} actions={actionsOf(reply, inter, open)} />
            {open ? (
              <>
                {body(reply)}
                {caret(reply)}
              </>
            ) : (
              preview(reply)
            )}
          </section>
        );
      })}
      {hiddenLine}
    </div>
  );
}
