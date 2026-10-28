import { useEffect, useId, useImperativeHandle, useRef, useState, type KeyboardEvent, type Ref } from "react";
import { Btn } from "../shared/Button";
import { s } from "../shared/styles";
import { fill, mergeMessages } from "../shared/util";

export interface ComposerMessages {
  inputLabel: string;
  placeholder: string;
  send: string;
  sending: string;
  /** 전송 키 안내. 키: 해석된 전송 키(`enter` | `mod_enter`). */
  keyHint: Record<string, string>;
  /** 되묻기 답변 모드(`chat.answer.*`). */
  answer: {
    /** 띠 문구. {target}, {kind} */
    strip: string;
    /** 토글이 "새 메시지"일 때의 띠 문구. */
    stripMessage: string;
    /** 토글 그룹 접근성 이름. */
    modeGroup: string;
    modeAnswer: string;
    modeMessage: string;
    /** 답변 모드 placeholder. */
    placeholder: string;
    /** 답변 모드 키 안내(전송 키별). */
    keyHint: Record<string, string>;
    /** 스크린리더 낭독. {target} */
    srEnterAnswer: string;
    srEnterMessage: string;
  };
}

export const defaultComposerMessages: ComposerMessages = {
  inputLabel: "메시지 입력",
  placeholder: "메시지를 입력하세요…",
  send: "전송",
  sending: "전송 중",
  keyHint: { enter: "Enter 전송 · Shift+Enter 줄바꿈", mod_enter: "Ctrl+Enter 전송 · Enter 줄바꿈" },
  answer: {
    strip: "{target}의 {kind}에 답하는 중",
    stripMessage: "새 메시지로 보내는 중 — 질문은 대기 중",
    modeGroup: "보내는 방식",
    modeAnswer: "답하기",
    modeMessage: "새 메시지",
    placeholder: "답을 입력하세요…",
    keyHint: { enter: "Enter 답하기 · Ctrl+Shift+Enter 새 메시지로", mod_enter: "Ctrl+Enter 답하기 · Ctrl+Shift+Enter 새 메시지로" },
    srEnterAnswer: "{target}의 질문에 답하는 입력창입니다",
    srEnterMessage: "새 메시지 입력창입니다",
  },
};

/** 답변 모드 전환 단축키 표시용. */
export const ANSWER_TOGGLE_SHORTCUT = "Alt+Shift+A";

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
  /**
   * 입력창 위 안내 줄. 호환용으로만 남겼고 앱은 `placeholderHint`를 쓴다.
   * @deprecated 입력칸 안내는 `placeholderHint`로.
   */
  pendingHint?: string;
  /** 일반 입력일 때 placeholder 안내(예: 질문은 위 카드에서 답하세요). 답변 모드·`placeholder`가 있으면 무시한다. */
  placeholderHint?: string;
  /**
   * 있으면 답변 모드 띠(두 칸 토글)를 보이고 [전송]을 [답하기]로 바꾼다.
   * `label`은 "{요청자}" 등 앱이 만든 문구. `describedBy`는 입력창 `aria-describedby`에 더할 DOM id(질문 본문 등, 답변 모드일 때만).
   */
  answerTarget?: { label: string; kindTitle: string; describedBy?: string };
  /** 띠 상태(제어형). 기본 `answer`. */
  answerMode?: AnswerMode;
  onSwitchToMessage?: () => void;
  onSwitchToAnswer?: () => void;
  /** Ctrl+Shift+Enter: 답변 모드에서 이번 전송만 새 메시지로(토글 선택은 바꾸지 않는다). */
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
  const stripId = useId();
  const toggleRefs = useRef<Record<AnswerMode, HTMLButtonElement | null>>({ answer: null, message: null });
  // 모드 전환·답변 입력창 진입을 한 번씩 낭독한다(같은 상태가 이어지는 동안 다시 읽지 않는다)
  const [announce, setAnnounce] = useState("");
  const lastAnnounced = useRef<string>("");
  const announceKey = answerTarget ? `${answerMode}:${answerTarget.label}` : "";
  useEffect(() => {
    if (announceKey === lastAnnounced.current) return;
    lastAnnounced.current = announceKey;
    setAnnounce(answerTarget ? fill(answerMode === "answer" ? m.answer.srEnterAnswer : m.answer.srEnterMessage, { target: answerTarget.label }) : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- announceKey가 모드·대상을 대표한다
  }, [announceKey]);
  const toggleMode = () => {
    if (!answerTarget) return;
    if (answerMode === "answer") props.onSwitchToMessage?.();
    else props.onSwitchToAnswer?.();
  };

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
    if (e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey && e.code === "KeyA" && answerTarget) {
      e.preventDefault();
      toggleMode();
      return;
    }
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
      props.onSendAsMessage?.();
      return;
    }
    const mod = e.ctrlKey || e.metaKey;
    const send = sendKey === "enter" ? !e.shiftKey && !mod : mod;
    if (send) {
      e.preventDefault();
      trySend();
    }
  };

  const onToggleKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.altKey && e.shiftKey && e.code === "KeyA") {
      e.preventDefault();
      toggleMode();
      return;
    }
    if (e.key === "Escape") {
      e.stopPropagation();
      area.current?.focus();
      return;
    }
    if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault();
      const next: AnswerMode = answerMode === "answer" ? "message" : "answer";
      (next === "answer" ? props.onSwitchToAnswer : props.onSwitchToMessage)?.();
      toggleRefs.current[next]?.focus();
    }
  };
  const radio = (mode: AnswerMode, label: string, onSelect: (() => void) | undefined) => {
    const checked = answerMode === mode;
    return (
      <button
        key={mode}
        ref={(el) => {
          toggleRefs.current[mode] = el;
        }}
        type="button"
        role="radio"
        aria-checked={checked}
        tabIndex={checked ? 0 : -1}
        data-mode={mode}
        title={`${label} (${ANSWER_TOGGLE_SHORTCUT})`}
        aria-keyshortcuts="Alt+Shift+A"
        className="ac-composer-mode"
        onClick={() => {
          if (!checked) onSelect?.();
        }}
        onKeyDown={onToggleKey}
      >
        {label}
      </button>
    );
  };
  const stripText = answerTarget ? (answering ? fill(m.answer.strip, { target: answerTarget.label, kind: answerTarget.kindTitle }) : m.answer.stripMessage) : "";
  const strip = answerTarget ? (
    <div role="group" aria-label={m.answer.modeGroup} className="ac-composer-strip" data-testid="answer-strip" data-answer-mode={answerMode}>
      <span className="ac-composer-strip-text" id={stripId} title={stripText}>
        <span aria-hidden="true">⏸ </span>
        {stripText}
      </span>
      <span role="radiogroup" aria-label={m.answer.modeGroup} className="ac-composer-modes">
        {radio("answer", m.answer.modeAnswer, props.onSwitchToAnswer)}
        {radio("message", m.answer.modeMessage, props.onSwitchToMessage)}
      </span>
    </div>
  ) : null;
  const describedBy = answerTarget && answering ? [stripId, answerTarget.describedBy].filter(Boolean).join(" ") : undefined;
  const keyHint = answering ? m.answer.keyHint[sendKey] : m.keyHint[sendKey];

  return (
    <div className="ac-composer" style={s.col("var(--ac-space-1)")}>
      <div className="ac-sr-only" aria-live="polite" role="status">
        {announce}
      </div>
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
          placeholder={props.placeholder ?? (answering ? m.answer.placeholder : (props.placeholderHint ?? m.placeholder))}
          aria-describedby={describedBy}
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
          {answering ? m.answer.modeAnswer : m.send}
        </Btn>
      </div>
      <div style={{ ...s.row(), justifyContent: "space-between", ...s.muted }}>
        <span>{props.sendHint ?? ""}</span>
        <span className="ac-composer-keyhint" title={keyHint}>{keyHint}</span>
      </div>
    </div>
  );
}
