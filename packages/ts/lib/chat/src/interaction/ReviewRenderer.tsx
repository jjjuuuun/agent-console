import { useState, type KeyboardEvent } from "react";
import type { ReviewDecision } from "@agent-console/contracts";
import { Btn } from "../shared/Button";
import { s } from "../shared/styles";
import { fill, isRecord } from "../shared/util";
import { Markdown } from "../messages/Markdown";
import { decisionButtonStyle } from "./decisionStyle";
import type { RendererComponent } from "./types";
import { isEditableTarget, onModEnter, str } from "./util";

/** payload.decisions를 읽는다. 라벨이 없으면 id를 보인다(라벨은 필수라 서버가 채운다). */
export function parseDecisions(payload: Record<string, unknown> | undefined): ReviewDecision[] {
  const raw = payload?.decisions;
  if (!Array.isArray(raw)) return [];
  return raw.filter(isRecord).flatMap((d) => {
    const id = str(d.id);
    if (!id) return [];
    return [{ id, label: str(d.label), edit: d.edit === true, feedback: d.feedback === true, ui_hints: isRecord(d.ui_hints) ? d.ui_hints : null } as ReviewDecision];
  });
}

/** 사용자 검토: 결정 버튼(순서·라벨·모양은 payload) + 선택 시 편집/의견 + 확정. 응답 `{decision, edited?, feedback?}`. */
export const ReviewRenderer: RendererComponent = ({ interaction, onSubmit, submitting, disabled, readOnly, messages, renderEditor }) => {
  const mr = messages.review;
  const p = interaction.payload ?? {};
  const decisions = parseDecisions(p);
  const content = typeof p.content === "string" ? p.content : "";
  const resp = isRecord(interaction.response) ? interaction.response : undefined;
  const [selected, setSelected] = useState<string | null>(readOnly ? (str(resp?.decision) ?? null) : null);
  const [edited, setEdited] = useState(content);
  const [feedback, setFeedback] = useState(typeof resp?.feedback === "string" ? resp.feedback : "");
  const [expandedContent, setExpandedContent] = useState(false);
  const locked = disabled || readOnly || submitting;
  const current = decisions.find((d) => d.id === selected);
  const labelOf = (d: ReviewDecision) => d.label || d.id;

  const confirm = () => {
    if (!current || locked) return;
    const out: Record<string, unknown> = { decision: current.id };
    if (current.edit && edited !== content) out.edited = edited;
    if (current.feedback && feedback.trim()) out.feedback = feedback.trim();
    onSubmit(out);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    onModEnter(e, confirm);
    if (locked || isEditableTarget(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (/^[1-9]$/.test(e.key)) {
      const d = decisions[Number(e.key) - 1];
      if (d) setSelected(d.id);
    }
  };

  const source = str(p.source_node);
  const showEditor = !!current?.edit && !readOnly;
  const shownContent = readOnly && typeof resp?.edited === "string" ? resp.edited : content;

  return (
    <div style={s.col("var(--ac-space-2)")} onKeyDown={onKey}>
      {source ? <span style={{ ...s.chip, alignSelf: "flex-start" }}>{fill(mr.sourceNode, { label: source })}</span> : null}
      {showEditor ? (
        renderEditor ? (
          renderEditor({ value: edited, onChange: setEdited, language: "markdown", label: mr.editLabel, disabled: locked })
        ) : (
          <textarea aria-label={mr.editLabel} value={edited} rows={10} disabled={locked} style={s.input} onChange={(e) => setEdited(e.target.value)} />
        )
      ) : (
        <div style={{ maxHeight: expandedContent ? "none" : 360, overflow: "auto" }}>
          <Markdown text={shownContent} />
        </div>
      )}
      {!showEditor && content.length > 0 ? (
        <Btn variant="ghost" size="sm" aria-expanded={expandedContent} onClick={() => setExpandedContent(!expandedContent)} style={{ alignSelf: "flex-start" }}>
          {expandedContent ? mr.collapseContent : mr.expandContent}
        </Btn>
      ) : null}

      <div role="group" aria-label={mr.decisionsLabel} style={s.row()}>
        {decisions.map((d, i) => {
          const isSel = d.id === selected;
          const { style, dataColor } = decisionButtonStyle(d.ui_hints, isSel);
          return (
            <button
              key={d.id}
              type="button"
              data-decision={d.id}
              data-color={dataColor}
              aria-pressed={isSel}
              disabled={locked}
              style={{ ...style, opacity: readOnly && !isSel ? 0.6 : undefined }}
              onClick={() => setSelected(d.id)}
              onKeyDown={(e) => {
                // 선택된 결정에서 Enter를 한 번 더 누르면 확정
                if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && isSel) {
                  e.preventDefault();
                  confirm();
                }
              }}
            >
              {d.ui_hints?.icon ? <span aria-hidden="true">{d.ui_hints.icon} </span> : null}
              {labelOf(d)}
              {i < 9 && !readOnly ? <> <kbd style={s.kbd}>{i + 1}</kbd></> : null}
            </button>
          );
        })}
      </div>

      {current?.feedback ? (
        <textarea aria-label={mr.feedbackLabel} placeholder={mr.feedbackLabel} value={feedback} rows={2} disabled={locked} style={s.input} onChange={(e) => setFeedback(e.target.value)} />
      ) : null}

      {readOnly ? null : current ? (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Btn variant="primary" disabled={locked} loading={submitting} onClick={confirm}>
            {fill(mr.confirm, { label: labelOf(current) })}
          </Btn>
        </div>
      ) : null}
    </div>
  );
};

ReviewRenderer.summarize = (interaction, m) => {
  const r = isRecord(interaction.response) ? interaction.response : {};
  const id = str(r.decision);
  if (!id) return m.answeredGeneric;
  const d = parseDecisions(interaction.payload).find((x) => x.id === id);
  return [d?.label || id, typeof r.edited === "string" ? m.review.edited : "", str(r.feedback) ? m.review.hasFeedback : ""].filter(Boolean).join(" · ");
};
