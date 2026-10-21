import { useState, type KeyboardEvent } from "react";
import { Btn } from "../shared/Button";
import { s } from "../shared/styles";
import { fill, isRecord } from "../shared/util";
import type { InteractionKindDescriptor, RendererComponent } from "./types";
import { isEditableTarget, onModEnter, parseJson, prettyJson, str } from "./util";

/**
 * 이 렌더러가 만드는 응답의 어휘. 도구 승인 종류 전용 컴포넌트이므로 값을 알고 있다(앱·엔진에는 없음).
 * 디스크립터 `ui_hints.decision_map`({allow, allow_for_run, deny} → 실제 값)이 있으면 그것이 우선한다.
 */
export const PERMISSION_DECISIONS = { allow: "allow", allow_for_run: "allow_for_run", deny: "deny" } as const;

export function decisionValues(descriptor: InteractionKindDescriptor | undefined): Record<keyof typeof PERMISSION_DECISIONS, string> {
  const map = descriptor?.ui_hints?.decision_map;
  const out: Record<keyof typeof PERMISSION_DECISIONS, string> = { ...PERMISSION_DECISIONS };
  if (isRecord(map)) for (const k of Object.keys(out) as (keyof typeof out)[]) if (typeof map[k] === "string") out[k] = map[k] as string;
  return out;
}

const PREVIEW_LINES = 8;

/** 도구 승인: 허용 / 이번 실행 동안 허용 / 거부(사유) / 입력 고쳐서 허용(payload.editable_input이 있을 때만). */
export const PermissionRenderer: RendererComponent = ({ interaction, descriptor, onSubmit, submitting, disabled, readOnly, messages, renderEditor }) => {
  const mp = messages.permission;
  const p = interaction.payload ?? {};
  const values = decisionValues(descriptor);
  const locked = disabled || readOnly || submitting;
  const [denyOpen, setDenyOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const editable = p.editable_input;
  const [editText, setEditText] = useState(() => prettyJson(editable));
  const parsed = editOpen ? parseJson(editText) : undefined;

  const name = str(p.display_name) ?? str(p.tool_name) ?? "";
  const title = str(p.title) ?? fill(mp.toolTitle, { name });
  const preview = prettyJson(p.input_preview);
  const lines = preview.split("\n");
  const longPreview = lines.length > PREVIEW_LINES;
  const shownPreview = longPreview && !showAll ? lines.slice(0, PREVIEW_LINES).join("\n") : preview;

  const decide = (decision: string, extra?: Record<string, unknown>) => {
    if (!locked) onSubmit({ decision, ...extra });
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    onModEnter(e, () => (denyOpen ? decide(values.deny, reason.trim() ? { message: reason.trim() } : undefined) : decide(values.allow)));
    if (locked || isEditableTarget(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === "y") decide(values.allow);
    else if (k === "a") decide(values.allow_for_run);
    else if (k === "n") setDenyOpen(true);
  };

  return (
    <div style={s.col("var(--ac-space-2)")} onKeyDown={onKey}>
      <div className="ac-text" style={{ fontSize: "var(--ac-text-md, 14px)", fontWeight: 600 }}>{title}</div>
      {str(p.description) ? <div className="ac-text" style={s.muted}>{str(p.description)}</div> : null}
      {str(p.decision_reason) ? <div className="ac-text" style={s.muted}>{fill(mp.reason, { reason: str(p.decision_reason) ?? "" })}</div> : null}
      {str(p.blocked_path) ? <code className="ac-mono-wrap" style={{ ...s.chip, alignSelf: "flex-start", whiteSpace: "normal" }}>{fill(mp.path, { path: str(p.blocked_path) ?? "" })}</code> : null}
      {p.input_preview !== undefined ? (
        <div style={s.col("var(--ac-space-1)")}>
          <pre style={s.code} data-testid="input-preview">{shownPreview}</pre>
          {longPreview ? (
            <Btn variant="ghost" size="sm" aria-expanded={showAll} onClick={() => setShowAll(!showAll)} style={{ alignSelf: "flex-start" }}>
              {showAll ? mp.showLess : mp.showAll}
            </Btn>
          ) : null}
        </div>
      ) : null}

      {readOnly ? (
        <div style={s.muted}>{PermissionRenderer.summarize?.(interaction, messages, descriptor)}</div>
      ) : (
        <>
          {denyOpen ? (
            <div style={s.col("var(--ac-space-1)")}>
              <textarea aria-label={mp.denyReasonLabel} placeholder={mp.denyReasonLabel} value={reason} rows={2} disabled={locked} style={s.input} onChange={(e) => setReason(e.target.value)} />
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--ac-space-2)" }}>
                <Btn variant="danger" disabled={locked} loading={submitting} onClick={() => decide(values.deny, reason.trim() ? { message: reason.trim() } : undefined)}>
                  {mp.denySend}
                </Btn>
              </div>
            </div>
          ) : null}
          {editable !== undefined ? (
            <div style={s.col("var(--ac-space-1)")}>
              <Btn variant="ghost" size="sm" aria-expanded={editOpen} onClick={() => setEditOpen(!editOpen)} style={{ alignSelf: "flex-start" }}>
                {editOpen ? "▾" : "▸"} {mp.editInput}
              </Btn>
              {editOpen ? (
                <>
                  {renderEditor ? (
                    renderEditor({ value: editText, onChange: setEditText, language: "json", label: mp.editInput, disabled: locked })
                  ) : (
                    <textarea aria-label={mp.editInput} value={editText} rows={6} disabled={locked} style={{ ...s.input, fontFamily: "var(--ac-font-mono)" }} onChange={(e) => setEditText(e.target.value)} />
                  )}
                  {parsed && !parsed.ok ? <span role="alert" style={{ color: "var(--ac-danger)", fontSize: "var(--ac-text-xs, 12px)" }}>{mp.invalidJson}</span> : null}
                  <Btn disabled={locked || !parsed?.ok} onClick={() => parsed?.ok && decide(values.allow, { updated_input: parsed.value })} style={{ alignSelf: "flex-end" }}>
                    {mp.editAndAllow}
                  </Btn>
                </>
              ) : null}
            </div>
          ) : null}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--ac-space-2)", flexWrap: "wrap" }}>
            <Btn variant="primary" disabled={locked} onClick={() => decide(values.allow)}>
              {mp.allow} <kbd style={s.kbd}>Y</kbd>
            </Btn>
            <Btn disabled={locked} onClick={() => decide(values.allow_for_run)}>
              {mp.allowForRun} <kbd style={s.kbd}>A</kbd>
            </Btn>
            <Btn variant="danger" disabled={locked} aria-expanded={denyOpen} onClick={() => setDenyOpen(true)}>
              {mp.deny} <kbd style={s.kbd}>N</kbd>
            </Btn>
          </div>
        </>
      )}
    </div>
  );
};

PermissionRenderer.summarize = (interaction, m, descriptor) => {
  const r = isRecord(interaction.response) ? interaction.response : {};
  const values = decisionValues(descriptor);
  const decision = str(r.decision);
  if (decision === values.allow) return m.permission.summaryAllow;
  if (decision === values.allow_for_run) return m.permission.summaryAllowForRun;
  if (decision === values.deny) {
    const msg = str(r.message)?.split("\n")[0];
    return msg ? fill(m.permission.summaryDeny, { reason: msg }) : m.permission.summaryDenyPlain;
  }
  return m.answeredGeneric;
};
