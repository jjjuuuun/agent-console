import { useId } from "react";
import { DECISION_COLOR_TOKENS, decisionButtonStyle } from "@agent-console/chat";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { Button, Disclosure, useIconRegistry } from "@agent-console/ui";
import { teamMessages as t } from "../messages";

/** `ui:field` 이름. */
export const REVIEW_DECISIONS_FIELD = "review-decisions";

interface Hints {
  color?: string | null;
  icon?: string | null;
  dashed?: boolean | null;
}
interface Decision {
  id: string;
  label?: string;
  edit?: boolean;
  feedback?: boolean;
  ui_hints?: Hints | null;
  [k: string]: unknown;
}

export interface DecisionsOptions {
  /** 결정 id(= 포트 이름) 규칙. 스키마 정규식이 없으면 영문자·숫자·밑줄·하이픈 */
  idPattern?: string;
}

const DEFAULT_ID = /^[A-Za-z0-9_-]+$/;

/** 다음 새 결정의 id(`d1`, `d2` …). */
export function nextDecisionId(decisions: readonly { id: string }[]): string {
  const used = new Set(decisions.map((d) => d.id));
  for (let n = 1; n < 1000; n += 1) if (!used.has(`d${n}`)) return `d${n}`;
  return `d${used.size + 1}`;
}

/**
 * 검토 결정 목록 편집: 행마다 id·라벨·"고쳐서 확정"·"의견 입력"·모양(색 토큰·아이콘·점선)과 버튼 미리보기, ↑↓ 순서·삭제.
 * 결정 id는 출력 포트 이름이라 중복·형식 오류를 즉시 알린다. 색은 토큰 이름만 고를 수 있다(자유 입력 없음).
 */
export function ReviewDecisionsField({ id, value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const opts = options as unknown as DecisionsOptions;
  const rows: Decision[] = Array.isArray(value) ? (value as Decision[]) : [];
  const uid = useId();
  const registry = useIconRegistry();
  const locked = disabled || readonly;
  const pattern = opts.idPattern === undefined ? DEFAULT_ID : new RegExp(opts.idPattern);
  const set = (i: number, patch: Partial<Decision>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const setHint = (i: number, patch: Partial<Hints>) => {
    const next: Hints = { ...(rows[i]?.ui_hints ?? {}), ...patch };
    for (const k of Object.keys(next) as (keyof Hints)[]) if (next[k] === null || next[k] === undefined || next[k] === "" || next[k] === false) delete next[k];
    const row = { ...rows[i]! } as Decision;
    if (Object.keys(next).length === 0) delete row.ui_hints;
    else row.ui_hints = next;
    onChange(rows.map((r, j) => (j === i ? row : r)));
  };
  const move = (i: number, delta: number) => {
    const to = i + delta;
    if (to < 0 || to >= rows.length) return;
    const next = [...rows];
    const [m] = next.splice(i, 1);
    next.splice(to, 0, m!);
    onChange(next);
  };
  return (
    <div id={id} role="group" aria-label={label} className="team-decisions">
      <span className="lib-field-label">{label}</span>
      {rows.map((r, i) => {
        const dup = rows.some((x, j) => j !== i && x.id === r.id);
        const bad = r.id === "" || !pattern.test(r.id);
        const { style } = decisionButtonStyle(r.ui_hints, false);
        return (
          <div key={i} className="team-decision-row">
            <div className="team-decision-main">
              <label className="lib-field">
                <span>{t.review.decisionId}</span>
                <input className="ac-input ac-mono" value={r.id} disabled={locked} aria-invalid={dup || bad} onChange={(e) => set(i, { id: e.target.value })} />
                {dup || bad ? <span className="lib-field-error" role="alert">{dup ? t.review.duplicateId : t.review.invalidId}</span> : null}
              </label>
              <label className="lib-field">
                <span>{t.review.decisionLabel}</span>
                <input className="ac-input" value={r.label ?? ""} disabled={locked} onChange={(e) => set(i, { label: e.target.value })} />
              </label>
            </div>
            <div className="team-decision-flags">
              <label className="app-check">
                <input type="checkbox" checked={r.edit === true} disabled={locked} onChange={(e) => set(i, { edit: e.target.checked })} />
                {t.review.decisionEdit}
              </label>
              <label className="app-check">
                <input type="checkbox" checked={r.feedback === true} disabled={locked} onChange={(e) => set(i, { feedback: e.target.checked })} />
                {t.review.decisionFeedback}
              </label>
              <span className="team-decision-actions">
              <Button size="sm" variant="ghost" disabled={locked || i === 0} aria-label={`${t.review.moveUp}: ${r.label || r.id}`} onClick={() => move(i, -1)}>↑</Button>
              <Button size="sm" variant="ghost" disabled={locked || i === rows.length - 1} aria-label={`${t.review.moveDown}: ${r.label || r.id}`} onClick={() => move(i, 1)}>↓</Button>
              <Button size="sm" variant="ghost" disabled={locked} aria-label={`${t.review.remove}: ${r.label || r.id}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}>×</Button>
              </span>
            </div>
            <Disclosure summary={t.review.shape}>
              <div className="team-decision-shape">
                <label className="lib-field">
                  <span>{t.review.color}</span>
                  <select value={r.ui_hints?.color ?? ""} disabled={locked} onChange={(e) => setHint(i, { color: e.target.value === "" ? null : e.target.value })}>
                    <option value="">{t.review.colorDefault}</option>
                    {DECISION_COLOR_TOKENS.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <label className="lib-field">
                  <span>{t.review.icon}</span>
                  <input className="ac-input" list={`${uid}-icons-${i}`} placeholder={t.review.iconPlaceholder} value={r.ui_hints?.icon ?? ""} disabled={locked} onChange={(e) => setHint(i, { icon: e.target.value })} />
                  <datalist id={`${uid}-icons-${i}`}>
                    {registry.names().map((n) => (
                      <option key={n} value={n} />
                    ))}
                  </datalist>
                </label>
                <label className="app-check">
                  <input type="checkbox" checked={r.ui_hints?.dashed === true} disabled={locked} onChange={(e) => setHint(i, { dashed: e.target.checked })} />
                  {t.review.dashed}
                </label>
                <div className="team-decision-preview" aria-label={t.review.preview}>
                  <span className="app-muted lib-field-note">{t.review.preview}</span>
                  <button type="button" style={style} tabIndex={-1} aria-hidden="true">
                    {r.ui_hints?.icon ? `${r.ui_hints.icon} ` : ""}
                    {r.label || r.id}
                  </button>
                </div>
              </div>
            </Disclosure>
          </div>
        );
      })}
      {locked ? null : (
        <Button size="sm" onClick={() => onChange([...rows, { id: nextDecisionId(rows), label: "" }])}>
          + {t.review.addDecision}
        </Button>
      )}
    </div>
  );
}
