import { useRef, useState, type KeyboardEvent } from "react";
import { Btn } from "../shared/Button";
import { s } from "../shared/styles";
import { fill, isRecord } from "../shared/util";
import type { RendererComponent } from "./types";
import { isEditableTarget, onModEnter, str } from "./util";

export interface ChoiceQuestion {
  question: string;
  header?: string;
  options: { label: string; description?: string }[];
  multi: boolean;
}

/** payload에서 질문 목록을 읽는다. 질문 배열이 없으면 자유 질문 하나. */
export function parseQuestions(payload: Record<string, unknown> | undefined): ChoiceQuestion[] {
  const raw = payload?.questions;
  if (Array.isArray(raw) && raw.length > 0) {
    return raw.filter(isRecord).map((q) => ({
      question: str(q.question) ?? "",
      header: str(q.header),
      options: (Array.isArray(q.options) ? q.options : []).filter(isRecord).map((o) => ({ label: str(o.label) ?? "", description: str(o.description) })),
      multi: q.multi_select === true || q.multiSelect === true,
    }));
  }
  return [{ question: str(payload?.text) ?? "", options: [], multi: false }];
}

interface QState {
  sel: number[];
  custom: boolean;
  text: string;
}

const emptyState = (): QState => ({ sel: [], custom: false, text: "" });

function fromResponse(questions: ChoiceQuestion[], response: unknown): QState[] {
  const answers = isRecord(response) && isRecord(response.answers) ? response.answers : {};
  return questions.map((q) => {
    const st = emptyState();
    const a = answers[q.question];
    const values = Array.isArray(a) ? a.map(String) : a === undefined ? [] : [String(a)];
    if (q.options.length === 0) {
      st.text = values[0] ?? "";
      return st;
    }
    for (const v of values) {
      const idx = q.options.findIndex((o) => o.label === v);
      if (idx >= 0) st.sel.push(idx);
      else {
        st.custom = true;
        st.text = v;
      }
    }
    return st;
  });
}

function isComplete(q: ChoiceQuestion, st: QState): boolean {
  if (q.options.length === 0) return st.text.trim() !== "";
  return st.sel.length > 0 || (st.custom && st.text.trim() !== "");
}

function buildAnswers(questions: ChoiceQuestion[], states: QState[]): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {};
  questions.forEach((q, i) => {
    const st = states[i] ?? emptyState();
    if (q.options.length === 0) {
      out[q.question] = st.text.trim();
      return;
    }
    const labels = st.sel.map((k) => q.options[k]?.label ?? "");
    const custom = st.custom && st.text.trim() ? [st.text.trim()] : [];
    if (q.multi) out[q.question] = [...labels, ...custom];
    else out[q.question] = custom[0] ?? labels[0] ?? "";
  });
  return out;
}

/** 질문 배열 → 라디오/체크 타일 + 직접 입력. 응답 `{answers}`. */
export const ChoicesRenderer: RendererComponent = ({ interaction, onSubmit, submitting, disabled, readOnly, messages }) => {
  const mc = messages.choices;
  const questions = parseQuestions(interaction.payload);
  const [states, setStates] = useState<QState[]>(() => (readOnly ? fromResponse(questions, interaction.response) : questions.map(emptyState)));
  const root = useRef<HTMLDivElement>(null);
  const locked = disabled || readOnly || submitting;
  const ready = questions.every((q, i) => isComplete(q, states[i] ?? emptyState()));

  const update = (i: number, fn: (st: QState) => QState) => setStates((prev) => prev.map((st, k) => (k === i ? fn(st) : st)));
  const toggleOption = (qi: number, oi: number) => {
    const q = questions[qi];
    if (!q || locked) return;
    update(qi, (st) => {
      if (q.multi) return { ...st, sel: st.sel.includes(oi) ? st.sel.filter((x) => x !== oi) : [...st.sel, oi] };
      return { sel: [oi], custom: false, text: st.text };
    });
  };
  const toggleCustom = (qi: number) => {
    const q = questions[qi];
    if (!q || locked) return;
    update(qi, (st) => (q.multi ? { ...st, custom: !st.custom } : { sel: [], custom: !st.custom, text: st.text }));
  };
  const submit = () => {
    if (ready && !locked) onSubmit({ answers: buildAnswers(questions, states) });
  };

  const onBlockKey = (qi: number, e: KeyboardEvent<HTMLElement>) => {
    const q = questions[qi];
    if (!q || isEditableTarget(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (/^[1-9]$/.test(e.key)) {
      const n = Number(e.key) - 1;
      if (n < q.options.length) toggleOption(qi, n);
      else if (n === q.options.length) toggleCustom(qi);
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const tiles = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[data-tile]"));
      const at = tiles.indexOf(e.target as HTMLElement);
      if (at < 0) return;
      e.preventDefault();
      tiles[(at + (e.key === "ArrowDown" ? 1 : -1) + tiles.length) % tiles.length]?.focus();
    }
  };

  const tile = (qi: number, key: string, num: number, selected: boolean, multi: boolean, label: string, description: string | undefined, onClick: () => void) => (
    <button
      key={key}
      type="button"
      data-tile=""
      role={multi ? "checkbox" : "radio"}
      aria-checked={selected}
      disabled={locked}
      onClick={onClick}
      style={{ ...s.tile, ...(selected ? s.tileSelected : null) }}
    >
      {num <= 9 ? <kbd style={s.kbd}>{num}</kbd> : null}
      <span style={{ ...s.col("2px"), flex: 1 }}>
        <span className="ac-text">{label}</span>
        {description ? <span className="ac-clamp-2" style={s.muted}>{description}</span> : null}
      </span>
      {selected ? <span aria-hidden="true">✓</span> : null}
    </button>
  );

  return (
    <div ref={root} style={s.col("var(--ac-space-3)")} onKeyDown={(e) => onModEnter(e, submit)}>
      {questions.map((q, qi) => {
        const st = states[qi] ?? emptyState();
        const free = q.options.length === 0;
        return (
          <div key={qi} data-question={qi} style={s.col("var(--ac-space-1)")} onKeyDown={(e) => onBlockKey(qi, e)}>
            {q.header ? <span style={{ ...s.chip, alignSelf: "flex-start" }}>{q.header}</span> : null}
            {q.question ? <div className="ac-text" style={{ fontSize: "var(--ac-text-sm, 13px)", fontWeight: 600 }}>{q.question}</div> : null}
            {free ? (
              <textarea
                aria-label={q.question || mc.freePlaceholder}
                placeholder={mc.freePlaceholder}
                value={st.text}
                disabled={locked}
                rows={2}
                style={s.input}
                onChange={(e) => update(qi, (x) => ({ ...x, text: e.target.value }))}
              />
            ) : (
              <div role={q.multi ? "group" : "radiogroup"} aria-label={q.question || undefined} style={s.col("var(--ac-space-1)")}>
                {q.options.map((o, oi) => tile(qi, `o${oi}`, oi + 1, st.sel.includes(oi), q.multi, o.label, o.description, () => toggleOption(qi, oi)))}
                {tile(qi, "custom", q.options.length + 1, st.custom, q.multi, mc.customOption, undefined, () => toggleCustom(qi))}
                {st.custom ? (
                  <textarea
                    aria-label={mc.customPlaceholder}
                    placeholder={mc.customPlaceholder}
                    value={st.text}
                    disabled={locked}
                    rows={1}
                    style={s.input}
                    onChange={(e) => update(qi, (x) => ({ ...x, text: e.target.value }))}
                  />
                ) : null}
              </div>
            )}
          </div>
        );
      })}
      {readOnly ? null : (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Btn variant="primary" disabled={!ready || locked} loading={submitting} title={ready ? undefined : mc.allRequired} onClick={submit}>
            {mc.submit}
          </Btn>
        </div>
      )}
    </div>
  );
};

ChoicesRenderer.summarize = (interaction, m) => {
  const questions = parseQuestions(interaction.payload);
  const answers = isRecord(interaction.response) && isRecord(interaction.response.answers) ? interaction.response.answers : {};
  const flat = questions.flatMap((q) => {
    const a = answers[q.question];
    return Array.isArray(a) ? a.map(String) : a === undefined ? [] : [String(a)];
  });
  const first = flat[0] ?? "";
  if (!first) return m.answeredGeneric;
  return questions.length > 1 ? fill(m.choices.answerSummaryMore, { first, n: questions.length - 1 }) : flat.length > 1 ? fill(m.choices.answerSummaryMore, { first, n: flat.length - 1 }) : fill(m.choices.answerSummary, { first });
};
