import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Btn } from "../shared/Button";
import { Markdown } from "../messages/Markdown";
import { s } from "../shared/styles";
import { fill, formatCountdown, formatSeconds, mergeMessages } from "../shared/util";
import { FallbackRenderer } from "./FallbackRenderer";
import { defaultInteractionMessages, type InteractionMessages } from "./messages";
import { answerCardIds } from "./answerSurface";
import { defaultRenderers } from "./renderers";
import type { FallbackArgs, FieldError, Interaction, InteractionKindDescriptor, RenderEditor, RendererComponent } from "./types";

export interface InteractionCardProps {
  interaction: Interaction;
  /** 종류 디스크립터. 없으면 종류 `title` 자리에 `interaction.kind` 원문을 쓴다. */
  descriptor: InteractionKindDescriptor | undefined;
  /** 응답 전송. reject되면 카드가 오류 영역에 메시지를 보인다. 카드 상태는 이 함수의 결과가 아니라 `interaction` prop으로만 바뀐다. */
  onRespond: (response: unknown) => Promise<void>;
  /** renderer 이름 → 컴포넌트. 기본 표(`defaultRenderers`)에 더하거나 덮어쓴다. */
  renderers?: Record<string, RendererComponent>;
  /** 표에 없는 renderer용(앱이 SchemaForm 주입). 없으면 내장 JSON 폴백. */
  renderFallback?: (args: FallbackArgs) => ReactNode;
  /** "PL · 설계" / "PL 안의 백엔드 리더" — 앱이 계산한다. */
  actorLabel?: string;
  /** 현재 시각(epoch 초). `Date.now()`를 직접 쓰지 않는다. */
  now: number;
  /** `interrupted`(서버 재시작 끊김) 카드에 [답을 새 메시지로 보내기]를 제공한다. */
  serverRestartHint?: { onResendAsMessage: () => void };
  /** 422 필드 오류. */
  errors?: readonly FieldError[];
  /** WS 끊김 등. 대기 상태는 유지하고 입력만 막는다. */
  disabled?: boolean;
  autoFocus?: boolean;
  /** Esc: 카드에서 입력창으로 포커스를 옮기는 일은 앱이 한다. */
  onEscape?: () => void;
  renderEditor?: RenderEditor;
  /**
   * 답 입력칸의 위치. 기본 `inline`(카드 안). `external`이면 입력 요소와 제출 버튼을 그리지 않고 질문 본문과 힌트 줄만 보인다
   * (입력창이 답을 받는다). 판정은 앱이 `resolveAnswerSurface`로 하고, 카드는 종류를 모른다.
   */
  answerVia?: "inline" | "external";
  /** `external`일 때 입력창이 "새 메시지" 모드라 이 요청이 아직 답을 기다리는 중임을 힌트 줄에 알린다. */
  answerPaused?: boolean;
  /** 자유 텍스트 초안이 바뀔 때(렌더러가 지원할 때만). 카드 → 입력창 전환 때 초안을 옮기는 데 쓴다. */
  onDraftChange?: (text: string) => void;
  messages?: Partial<InteractionMessages>;
  /**
   * 요청자 옆 작은 칩(예: 중첩 팀 안의 요청이면 `중첩 팀`, 자식 실행 출처). 문구는 앱이 정한다. `href`나 `onClick`이 있으면 누를 수 있다.
   * 없으면 그리지 않는다.
   */
  contextChip?: { text: string; title?: string; href?: string; onClick?: () => void };
}

function ContextChip({ chip }: { chip: NonNullable<InteractionCardProps["contextChip"]> }) {
  const style = { ...s.chip, font: "inherit", cursor: chip.href || chip.onClick ? "pointer" : "default", color: "inherit", textDecoration: "none" };
  if (chip.href) return <a href={chip.href} title={chip.title} data-part="context-chip" style={style} onClick={chip.onClick ? (e) => { e.preventDefault(); chip.onClick?.(); } : undefined}>{chip.text}</a>;
  if (chip.onClick) return <button type="button" title={chip.title} data-part="context-chip" style={{ ...style, background: "transparent" }} onClick={chip.onClick}>{chip.text}</button>;
  return <span title={chip.title} data-part="context-chip" style={style}>{chip.text}</span>;
}

type CardKind = "pending" | "answered" | "timeout" | "interrupted" | "cancelled" | "other";

export function cardKind(i: Interaction): CardKind {
  if (i.status === "pending") return "pending";
  if (i.status === "answered") return "answered";
  if (i.status === "cancelled") return "cancelled";
  if (i.status === "expired") return i.close_reason === "interrupted" ? "interrupted" : "timeout";
  return "other";
}

/** 카드 상태 → 토큰 `data-status` (tokens.md 5.5). */
function statusAttrs(kind: CardKind, raw: string): { "data-status": string; "data-status-kind"?: string } {
  switch (kind) {
    case "pending":
      return { "data-status": "waiting" };
    case "answered":
      return { "data-status": "succeeded" };
    case "timeout":
      return { "data-status": "skipped" };
    case "interrupted":
      return { "data-status": "interrupted", "data-status-kind": "run" };
    case "cancelled":
      return { "data-status": "cancelled" };
    default:
      return { "data-status": raw };
  }
}

/**
 * 상호작용 카드. 종류 id를 모른다: `descriptor.ui_hints.renderer` 문자열로 렌더러 표에서 컴포넌트를 찾고,
 * 없으면 `renderFallback`(없으면 내장 JSON 폴백)으로 그린다.
 */
export function InteractionCard(props: InteractionCardProps) {
  const { interaction, descriptor, onRespond, now, serverRestartHint, errors = [], disabled = false } = props;
  const m = mergeMessages(defaultInteractionMessages, props.messages);
  const kind = cardKind(interaction);
  const pending = kind === "pending";
  const [open, setOpen] = useState(kind === "interrupted");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const body = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (props.autoFocus && pending) body.current?.querySelector<HTMLElement>("input, textarea, button:not([disabled])")?.focus();
  }, [props.autoFocus, pending]);

  const submit = (response: unknown) => {
    setSubmitting(true);
    setError(undefined);
    onRespond(response)
      .catch((e: unknown) => setError(e instanceof Error && e.message ? e.message : m.sendFailed))
      .finally(() => setSubmitting(false));
  };

  const rendererName = descriptor?.ui_hints?.renderer;
  const table: Record<string, RendererComponent> = { ...defaultRenderers, ...props.renderers };
  const Renderer = typeof rendererName === "string" && Object.hasOwn(table, rendererName) ? table[rendererName] : undefined;

  const title = descriptor?.title ?? interaction.kind;
  const actor = props.actorLabel ?? "";
  const stateKey = kind === "interrupted" ? "interrupted" : interaction.status;
  const stateLabel = m.stateLabels[stateKey] ?? interaction.status;
  const created = interaction.created_at;
  const waited = pending ? now - created : (interaction.closed_at ?? now) - created;
  const remaining = pending && interaction.expires_at != null ? interaction.expires_at - now : undefined;
  const dur = (sec: number) => formatSeconds(sec, m.units);
  const readOnly = !pending;
  const external = pending && props.answerVia === "external";
  const ids = answerCardIds(interaction.id);

  const rendererProps = {
    interaction,
    descriptor,
    onSubmit: submit,
    submitting,
    errors,
    disabled: disabled || submitting,
    readOnly,
    readOnlyInput: external,
    messages: m,
    renderEditor: props.renderEditor,
    ...(props.onDraftChange ? { onDraftChange: props.onDraftChange } : {}),
  };
  // 입력창이 답을 받을 때 앱 주입 폴백(스키마 폼)은 입력을 그리므로 쓰지 않고 내장 폴백으로 요청 내용만 보인다
  const bodyNode = Renderer ? (
    <Renderer {...rendererProps} />
  ) : props.renderFallback && !external ? (
    props.renderFallback({ interaction, descriptor, onSubmit: submit, submitting, errors, disabled: disabled || submitting, readOnly })
  ) : (
    <FallbackRenderer interaction={interaction} descriptor={descriptor} onSubmit={submit} submitting={submitting} errors={errors} disabled={disabled || submitting} readOnly={readOnly} readOnlyInput={external} messages={m} />
  );

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape" && props.onEscape) {
      e.stopPropagation();
      props.onEscape();
    }
  };

  const summary = (): string => {
    switch (kind) {
      case "answered": {
        const text = Renderer?.summarize?.(interaction, m, descriptor) ?? m.answeredGeneric;
        const by = interaction.answered_by && interaction.answered_by !== "user" ? ` · ${m.answeredBy[interaction.answered_by] ?? interaction.answered_by}` : "";
        return fill(m.answeredLine, { summary: text, duration: dur(waited) }) + by;
      }
      case "timeout":
        return fill(m.expiredLine, { duration: dur(waited) });
      case "cancelled": {
        const reason = interaction.close_reason ? (m.closeReasons[interaction.close_reason] ?? interaction.close_reason) : "";
        return fill(m.cancelledLine, { reason });
      }
      case "interrupted":
        return m.interruptedTitle;
      default:
        return m.stateLabels[interaction.status] ?? interaction.status;
    }
  };

  const icon = <span className="ac-status-icon" aria-hidden="true" />;
  const rootProps = {
    role: "group" as const,
    "aria-label": external ? fill(m.answer.cardLabelExternal, { label: fill(m.cardLabel, { title, actor, state: stateLabel }) }) : fill(m.cardLabel, { title, actor, state: stateLabel }),
    "aria-busy": submitting || undefined,
    "data-interaction-id": interaction.id,
    "data-card-state": kind,
    className: "ac-status-box",
    ...statusAttrs(kind, interaction.status),
    onKeyDown,
    style: { ...s.card, padding: 0, borderLeft: pending ? "3px solid var(--ac-status-waiting)" : undefined, background: "var(--ac-surface-1)" },
  };

  if (!pending && kind !== "interrupted") {
    return (
      <div {...rootProps}>
        <button
          type="button"
          data-card-toggle=""
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          style={{ ...s.row(), width: "100%", minHeight: 32, padding: "0 var(--ac-space-3)", background: "transparent", border: 0, font: "inherit", color: "var(--ac-text-muted)", textAlign: "left", cursor: "pointer", flexWrap: "nowrap" }}
        >
          {icon}
          <span style={{ fontWeight: 600 }}>{title}</span>
          <span className="ac-ellipsis" style={{ flex: 1 }}>{summary()}</span>
        </button>
        {props.contextChip ? <div style={{ padding: "0 var(--ac-space-3) var(--ac-space-1)" }}><ContextChip chip={props.contextChip} /></div> : null}
        {open ? (
          <div ref={body} style={{ ...s.col(), padding: "var(--ac-space-2) var(--ac-space-3)" }}>
            {kind === "timeout" ? <div style={s.muted}>{m.expiredDetail}</div> : null}
            {interaction.message ? <Markdown text={interaction.message} /> : null}
            {bodyNode}
          </div>
        ) : null}
      </div>
    );
  }

  const errorLines = [...(error ? [error] : []), ...errors.map((e) => (e.path ? `${e.path}: ${e.message}` : e.message))];
  return (
    <div {...rootProps}>
      <div className="ac-status-header" style={{ ...s.row(), justifyContent: "space-between", padding: "var(--ac-space-2) var(--ac-space-3)" }}>
        <span style={s.row()}>
          {icon}
          <span style={{ fontWeight: 600 }}>{title}</span>
          {actor ? <span style={s.muted}>· {actor}</span> : null}
          {props.contextChip ? <ContextChip chip={props.contextChip} /> : null}
          {disabled && pending ? <span style={s.chip}>{m.disconnected}</span> : null}
        </span>
        {pending ? (
          <span style={s.row()}>
            <span className="ac-num" style={s.muted}>{fill(m.waitingFor, { duration: dur(waited) })}</span>
            {remaining != null ? (
              <span className="ac-num" style={{ ...s.muted, color: remaining < 60 ? "var(--ac-warning)" : undefined }}>
                {remaining < 60 ? "▲ " : ""}
                {fill(m.remaining, { time: formatCountdown(remaining) })}
              </span>
            ) : null}
          </span>
        ) : null}
      </div>
      <div ref={body} style={{ ...s.col("var(--ac-space-2)"), padding: "var(--ac-space-2) var(--ac-space-3) var(--ac-space-3)" }}>
        {kind === "interrupted" ? (
          <div role="note" style={s.banner("warning")}>
            <div style={{ fontWeight: 600 }}>{m.interruptedTitle}</div>
            <div className="ac-text">{m.interruptedBody}</div>
          </div>
        ) : null}
        {interaction.title ? <div className="ac-text" style={{ fontWeight: 600 }}>{interaction.title}</div> : null}
        <div id={external ? ids.body : undefined} style={s.col("var(--ac-space-2)")}>
          {interaction.message ? <Markdown text={interaction.message} /> : null}
          {bodyNode}
        </div>
        {external ? (
          <div id={ids.hint} data-part="answer-hint" style={s.muted}>
            {props.answerPaused ? m.answer.hintCardPaused : m.answer.hintComposer}
          </div>
        ) : null}
        {errorLines.length > 0 ? (
          <div role="alert" style={s.banner("danger")}>
            {errorLines.map((l, i) => (
              <div key={i} className="ac-text">{l}</div>
            ))}
          </div>
        ) : null}
        {kind === "interrupted" && serverRestartHint ? (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Btn onClick={serverRestartHint.onResendAsMessage}>{m.resendAsMessage}</Btn>
          </div>
        ) : null}
      </div>
    </div>
  );
}
