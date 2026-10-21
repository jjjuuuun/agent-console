import { useEffect, useImperativeHandle, useRef, type KeyboardEvent, type Ref } from "react";
import { Btn } from "../shared/Button";
import { s } from "../shared/styles";
import { fill, mergeMessages } from "../shared/util";

export interface ComposerMessages {
  inputLabel: string;
  placeholder: string;
  answerPlaceholder: string;
  send: string;
  answer: string;
  sending: string;
  /** 전송 키 안내. 키: 해석된 전송 키(`enter` | `mod_enter`). */
  keyHint: Record<string, string>;
  answeringTo: string; // {target}, {kind}
  switchToMessage: string;
  messageMode: string;
  switchToAnswer: string;
}

export const defaultComposerMessages: ComposerMessages = {
  inputLabel: "메시지 입력",
  placeholder: "메시지를 입력하세요…",
  answerPlaceholder: "답을 입력하세요…",
  send: "전송",
  answer: "답하기",
  sending: "전송 중",
  keyHint: { enter: "Enter 전송 · Shift+Enter 줄바꿈", mod_enter: "Ctrl+Enter 전송 · Enter 줄바꿈" },
  answeringTo: "{target}의 {kind}에 답하는 중",
  switchToMessage: "새 메시지로 보내기",
  messageMode: "새 메시지 모드",
  switchToAnswer: "질문에 답하기",
};

/** 답변 모드 띠 상태: `answer` = 대기 요청에 답하기, `message` = 새 메시지로 보내기. 앱이 문자열을 직접 쓰지 않게 상수로도 낸다. */
export const ANSWER_MODES = { answer: "answer", message: "message" } as const;
export type AnswerMode = (typeof ANSWER_MODES)[keyof typeof ANSWER_MODES];

export interface ComposerHandle {
  focus(): void;
}

export interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /** `chat.send_key` 값. `ctrl_enter`·`mod_enter`는 Ctrl/Cmd+Enter 전송, 그 외·모름은 Enter 전송. */
  sendKey?: string;
  disabled?: boolean;
  /** 입력창 비활성 사유(위 배너 자리). */
  disabledReason?: string;
  /** 입력은 되지만 전송만 막을 때(예: WS 끊김). */
  sendDisabled?: boolean;
  sendHint?: string;
  sending?: boolean;
  busyNotice?: { text: string; tone: "info" | "warning" | "danger" };
  /** 대기 카드가 여럿이거나 입력창 답변이 불가할 때의 안내 줄. */
  pendingHint?: string;
  /**
   * 있으면 답변 모드 띠를 보이고 [전송]을 [답하기]로 바꾼다.
   * `label`은 "{요청자} · {종류 title}" 등 앱이 만든 문구.
   */
  answerTarget?: { label: string; kindTitle: string };
  /** 띠 상태(제어형). 기본 `answer`. */
  answerMode?: AnswerMode;
  onSwitchToMessage?: () => void;
  onSwitchToAnswer?: () => void;
  /** Ctrl+Shift+Enter: 답변 모드에서 이번 전송을 새 메시지로. 없으면 `onSwitchToMessage`만 부른다. */
  onSendAsMessage?: () => void;
  onRecallLast?: () => void;
  onEscape?: () => void;
  placeholder?: string;
  autoFocus?: boolean;
  maxRows?: number;
  ref?: Ref<ComposerHandle>;
  messages?: Partial<ComposerMessages>;
}

export function resolveSendKey(sendKey: string | undefined): "enter" | "mod_enter" {
  return sendKey === "ctrl_enter" || sendKey === "mod_enter" ? "mod_enter" : "enter";
}

/** 키 이벤트가 IME 조합 중이거나 조합 확정 직후의 Enter인지. */
function isImeEvent(e: KeyboardEvent, justEnded: boolean): boolean {
  const ne = e.nativeEvent as { isComposing?: boolean; keyCode?: number };
  return justEnded || !!ne.isComposing || e.keyCode === 229 || ne.keyCode === 229;
}

/**
 * 채팅 입력창. 제어형. 한글 IME 조합 중 Enter는 전송하지 않는다.
 * 전송·초안 보존·답변 여부는 앱이 정한다(이 컴포넌트는 UI와 키 처리만).
 */
export function Composer(props: ComposerProps) {
  const { value, onChange, onSend, disabled, answerTarget, answerMode = "answer", maxRows = 8, ref } = props;
  const m = mergeMessages(defaultComposerMessages, props.messages);
  const sendKey = resolveSendKey(props.sendKey);
  const area = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const justEnded = useRef(false);
  const answering = !!answerTarget && answerMode === "answer";

  useImperativeHandle(ref, () => ({ focus: () => area.current?.focus() }), []);
  // 처음 그릴 때 입력창이 비활성이면 포커스가 안 간다. 활성이 되는 순간, 다른 곳에 포커스가 없을 때만 다시 준다.
  useEffect(() => {
    if (!props.autoFocus || disabled) return;
    const active = document.activeElement;
    if (active === null || active === document.body || active === area.current) area.current?.focus();
  }, [props.autoFocus, disabled]);
  // 내용에 맞춰 높이를 늘린다(최대 maxRows줄).
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    const line = parseFloat(getComputedStyle(el).lineHeight) || 20;
    const max = line * maxRows;
    if (el.scrollHeight) el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [value, maxRows]);

  const canSend = !disabled && !props.sendDisabled && !props.sending && value.trim().length > 0;
  const trySend = () => {
    if (canSend) onSend();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      props.onEscape?.();
      return;
    }
    if (e.key === "ArrowUp" && value === "" && props.onRecallLast) {
      e.preventDefault();
      props.onRecallLast();
      return;
    }
    if (e.key !== "Enter") return;
    if (isImeEvent(e, justEnded.current) || composing.current) return;
    if (e.ctrlKey && e.shiftKey && answerTarget) {
      e.preventDefault();
      if (props.onSendAsMessage) props.onSendAsMessage();
      else props.onSwitchToMessage?.();
      return;
    }
    const mod = e.ctrlKey || e.metaKey;
    const send = sendKey === "enter" ? !e.shiftKey && !mod : mod;
    if (send) {
      e.preventDefault();
      trySend();
    }
  };

  const strip = answerTarget ? (
    <div
      data-testid="answer-strip"
      data-answer-mode={answerMode}
      style={{ ...s.row(), minHeight: 28, padding: "0 var(--ac-space-2)", borderLeft: "3px solid var(--ac-status-waiting)", background: "var(--ac-status-waiting-bg)", fontSize: "var(--ac-text-xs, 12px)" }}
    >
      {answering ? (
        <>
          <span>⏸ {fill(m.answeringTo, { target: answerTarget.label, kind: answerTarget.kindTitle })}</span>
          <span aria-hidden="true">—</span>
          <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" onClick={props.onSwitchToMessage}>
            {m.switchToMessage}
          </button>
        </>
      ) : (
        <>
          <span>{m.messageMode}</span>
          <span aria-hidden="true">—</span>
          <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" onClick={props.onSwitchToAnswer}>
            {m.switchToAnswer}
          </button>
        </>
      )}
    </div>
  ) : null;

  return (
    <div style={s.col("var(--ac-space-1)")}>
      {props.disabledReason ? (
        <div role="note" style={s.banner("warning")}>
          {props.disabledReason}
        </div>
      ) : null}
      {props.busyNotice ? (
        <div role="status" style={s.banner(props.busyNotice.tone)}>
          {props.busyNotice.text}
        </div>
      ) : null}
      {props.pendingHint ? <div style={s.muted}>{props.pendingHint}</div> : null}
      {strip}
      <div style={{ display: "flex", gap: "var(--ac-space-2)", alignItems: "flex-end" }}>
        <textarea
          ref={area}
          aria-label={m.inputLabel}
          value={value}
          disabled={disabled}
          rows={1}
          placeholder={props.placeholder ?? (answering ? m.answerPlaceholder : m.placeholder)}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
            // 일부 브라우저는 조합 확정 직후 같은 Enter keydown이 온다. 한 틱 무시.
            justEnded.current = true;
            setTimeout(() => {
              justEnded.current = false;
            }, 0);
          }}
          style={{ ...s.input, resize: "none", minHeight: "var(--ac-composer-min-h, 44px)", maxHeight: "var(--ac-composer-max-h, 200px)", overflowY: "auto" }}
        />
        <Btn variant="primary" size="lg" disabled={!canSend} loading={props.sending} onClick={trySend}>
          {answering ? m.answer : m.send}
        </Btn>
      </div>
      <div style={{ ...s.row(), justifyContent: "space-between", ...s.muted }}>
        <span>{props.sendHint ?? ""}</span>
        <span>{m.keyHint[sendKey]}</span>
      </div>
    </div>
  );
}
