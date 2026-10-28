import { useMemo, useState } from "react";
import type { Issue } from "@agent-console/contracts";
import { Badge, Banner, Button, ConfirmDialog, Spinner } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { deleteProfile, disableProfile, removeKey, setProfile, suggestCloneId } from "../architectureSettings";
import { KindEditorDialog, type KindEditorMode, type KindEditorValue } from "./KindEditorDialog";
import { kindActions, originText, type KindAction, type KindRow } from "./kindRows";
import { KIND_SPEC_KEYS } from "./memorySettingsConfig";
import { memorySettingsMessages as t } from "./messages";

type Obj = Record<string, unknown>;

export interface ScopeKindsPanelProps {
  /** 설정 초안의 `scope_kinds` 맵 */
  kinds: Obj;
  /** 저장된 설정의 `scope_kinds` 맵(지우기 방식·저장 전 표시) */
  saved: Obj;
  onChange: (next: Obj) => void;
  rows: readonly KindRow[];
  disabledRows: readonly KindRow[];
  includeDefaults: boolean;
  onEnableDefaults: () => void;
  status: "loading" | "error" | "ready";
  error?: Error | null;
  onRetry: () => void;
  /** 목록 응답의 기본 범위 종류 사용 값과 초안이 다르면 알림을 보인다 */
  defaultsPending: boolean;
  /** 틀 입력 아래 칩(서버 스키마 예시) */
  examples: readonly string[];
  /** 종류 id → 서버 검사 문제 수 */
  problemCounts: ReadonlyMap<string, number>;
  /** 편집 중인 종류를 설정 섹션에 넣어 서버 검사한다 */
  check: (id: string, spec: Obj) => Promise<readonly Issue[]>;
  disabled?: boolean;
  checkDelayMs?: number;
}

type DialogState =
  | { kind: "editor"; mode: KindEditorMode; title: string; initial: KindEditorValue }
  | { kind: "confirm"; action: "disable" | "remove"; row: KindRow }
  | null;

const specOf = (v: KindEditorValue): Obj => ({ [KIND_SPEC_KEYS.label]: v.label.trim(), ...(v.description.trim() === "" ? {} : { [KIND_SPEC_KEYS.description]: v.description.trim() }), ...(v.template === "" ? {} : { [KIND_SPEC_KEYS.template]: v.template }) });

function Row({ row, problems, onAction, disabled }: { row: KindRow; problems: number; onAction: (a: KindAction, row: KindRow) => void; disabled: boolean | undefined }) {
  const acts = kindActions(row);
  const tip = row.description === "" ? row.label : `${row.label} — ${row.description}`;
  return (
    <li className="memset-row" data-row-id={row.id}>
      <span className="memset-cell memset-cell-label">
        {row.dirty ? <span className="memset-dot" role="img" aria-label={t.kinds.unsaved} title={t.kinds.unsaved} /> : null}
        <span className="memset-strong ac-ellipsis" title={tip}>{row.label}</span>
      </span>
      <span className="memset-cell memset-mono memset-muted ac-ellipsis" title={row.id}>{row.id}</span>
      <span className="memset-cell memset-mono memset-muted ac-ellipsis" title={row.template ?? undefined}>{row.template === null ? t.kinds.computed : row.template === "" ? t.kinds.noTemplate : row.template}</span>
      <span className="memset-cell"><Badge className="memset-origin">{originText(row, t.kinds.origin)}</Badge></span>
      <span className="memset-cell memset-num">{row.entries}</span>
      <span className="memset-cell">
        {row.disabled ? t.kinds.off : t.kinds.on}
        {problems > 0 ? <span className="memset-warn-inline"> <span className="app-sev" data-severity="warning" aria-hidden="true">▲</span> {t.kinds.problems(problems)}</span> : null}
      </span>
      <span className="memset-cell memset-actions" role="group" aria-label={t.kinds.actionsFor(row.label)}>
        {acts.map((a) => (
          <Button key={a} size="sm" variant={a === "remove" ? "danger" : "secondary"} disabled={disabled === true && a !== "view"} onClick={() => onAction(a, row)}>{t.kinds[a]}</Button>
        ))}
      </span>
    </li>
  );
}

/** 범위 종류 표 + 편집기(표현 전용). 설정 문서에는 초안(`scope_kinds`)만 바꾸고 파일 기록은 설정 화면의 [저장]이 한다. */
export function ScopeKindsPanel(p: ScopeKindsPanelProps) {
  const [dialog, setDialog] = useState<DialogState>(null);
  const [showDisabled, setShowDisabled] = useState(false);
  const taken = useMemo(() => new Set([...p.rows, ...p.disabledRows].map((r) => r.id)), [p.rows, p.disabledRows]);
  const toValue = (r: KindRow, id = r.id): KindEditorValue => ({ id, label: r.label, description: r.description, template: r.template ?? "" });

  const apply = (action: "disable" | "remove", row: KindRow) => p.onChange(action === "disable" ? disableProfile(p.kinds, row.id) : deleteProfile(p.kinds, row.id, p.saved));
  const onAction = (a: KindAction, row: KindRow) => {
    switch (a) {
      case "view": return setDialog({ kind: "editor", mode: "view", title: t.kindEditor.viewTitle(row.id), initial: toValue(row) });
      case "edit": return setDialog({ kind: "editor", mode: "edit", title: t.kindEditor.editTitle(row.id), initial: toValue(row) });
      case "clone": return setDialog({ kind: "editor", mode: "clone", title: t.kindEditor.cloneTitle(row.label), initial: toValue(row, suggestCloneId(row.id, taken)) });
      case "enable":
      case "revert": return p.onChange(removeKey(p.kinds, row.id));
      case "disable":
      case "remove": return row.entries > 0 ? setDialog({ kind: "confirm", action: a, row }) : apply(a, row);
    }
  };
  const total = p.rows.length;
  return (
    <section className="memset-panel" aria-label={t.kinds.label} data-testid="memset-kinds">
      <div className="memset-listhead">
        <h3 className="memset-title">{t.kinds.title(total)}</h3>
        <Button size="sm" disabled={p.disabled === true} onClick={() => setDialog({ kind: "editor", mode: "new", title: t.kindEditor.newTitle, initial: { id: "", label: "", description: "", template: "" } })}>+ {t.kinds.add}</Button>
      </div>
      {p.defaultsPending ? <p className="memset-note app-muted" role="status">{t.kinds.defaultsPending}</p> : null}
      {p.status === "loading" ? (
        <div className="memset-loading" role="status"><Spinner /><span className="ac-sr-only">{t.loading}</span></div>
      ) : p.status === "error" ? (
        <ErrorBlock title={t.kinds.loadFailed} {...(p.error ? { message: p.error.message } : {})} retryLabel={t.retry} onRetry={p.onRetry} />
      ) : total === 0 ? (
        <div className="memset-empty">
          <p className="memset-strong">{t.kinds.empty}</p>
          <p className="app-muted memset-note">{t.kinds.emptyBody}</p>
          {!p.includeDefaults ? <Button size="sm" onClick={p.onEnableDefaults}>{t.kinds.enableDefaults}</Button> : null}
        </div>
      ) : (
        <div className="memset-table">
          <div className="memset-head" aria-hidden="true">
            {Object.values(t.kinds.col).slice(0, -1).map((c) => <span key={c}>{c}</span>)}
          </div>
          <ul className="memset-rows">
            {p.rows.map((r) => <Row key={r.id} row={r} problems={p.problemCounts.get(r.id) ?? 0} onAction={onAction} disabled={p.disabled} />)}
          </ul>
        </div>
      )}
      {p.disabledRows.length === 0 ? null : (
        <div className="memset-disabled">
          <Button size="sm" variant="ghost" aria-expanded={showDisabled} onClick={() => setShowDisabled(!showDisabled)}>
            {t.kinds.disabledTitle(p.disabledRows.length)} {showDisabled ? "▴" : "▾"}
          </Button>
          {showDisabled ? (
            <ul className="memset-rows" aria-label={t.kinds.disabledTitle(p.disabledRows.length)}>
              {p.disabledRows.map((r) => <Row key={r.id} row={r} problems={0} onAction={onAction} disabled={p.disabled} />)}
            </ul>
          ) : null}
        </div>
      )}
      {dialog?.kind === "editor" ? (
        <KindEditorDialog
          mode={dialog.mode}
          title={dialog.title}
          initial={dialog.initial}
          takenIds={dialog.mode === "edit" ? new Set() : taken}
          examples={p.examples}
          check={(v) => p.check(v.id, specOf(v))}
          onClose={() => setDialog(null)}
          onApply={(v) => {
            p.onChange(setProfile(p.kinds, v.id, specOf(v)));
            setDialog(null);
          }}
          {...(p.checkDelayMs === undefined ? {} : { checkDelayMs: p.checkDelayMs })}
        />
      ) : null}
      {dialog?.kind === "confirm" ? (
        <ConfirmDialog
          open
          title={t.kinds.confirmTitle(t.kinds[dialog.action])}
          confirmLabel={t.kinds[dialog.action]}
          cancelLabel={t.cancel}
          danger
          onCancel={() => setDialog(null)}
          onConfirm={() => {
            apply(dialog.action, dialog.row);
            setDialog(null);
          }}
        >
          <Banner tone="warning">{t.kinds.confirmBody(dialog.row.entries)}</Banner>
        </ConfirmDialog>
      ) : null}
    </section>
  );
}
