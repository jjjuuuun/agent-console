import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@agent-console/ui";
import { isImeKeyEvent, useImeGuard } from "../../lib/ime";
import { ActionMenu } from "../library";
import {
  conditionShape,
  forbidsValue,
  formMode,
  itemsOf,
  summarizeConditions,
  switchMode,
  withItems,
  withNegate,
  type ConditionItem,
  type ConditionMode,
  type ConditionOperatorDescriptor,
  type ConditionSpec,
} from "./conditions";
import { delegationMessages } from "./messages";
import { ValueEditor } from "./ValueEditor";

export type OperatorsState = "loading" | "ready" | "error" | "absent";

/** 서버 이슈를 행 단위로 매단 오류(경로는 조건 묶음 안 상대: `/all/1/value`). */
export interface ConditionError {
  path: string;
  message: string;
}

export interface ConditionListProps {
  value: ConditionSpec | null | undefined;
  onChange(next: ConditionSpec | undefined): void;
  /** 서버 연산자 목록. 없으면(로딩·오류·연동 꺼짐) null */
  operators: readonly ConditionOperatorDescriptor[] | null;
  operatorsState: OperatorsState;
  onRetryOperators?: (() => void) | undefined;
  /** 대상 경로 제안(스키마 `examples`, 제목은 `ui:options.path_titles`) */
  pathSuggestions?: readonly { value: string; title?: string }[] | undefined;
  errors?: readonly ConditionError[] | undefined;
  disabled?: boolean | undefined;
  /** 접근성 이름(필드 라벨) */
  label?: string | undefined;
  idPrefix?: string | undefined;
  messages?: typeof delegationMessages.condition;
  /** 이 개수를 넘으면 안내를 보인다(기본 20) */
  manyThreshold?: number;
}

const DEFAULT_MANY = 20;

/**
 * 조건 목록 위젯(표현 전용, screen-delegation.md 2.4.3). 모드 라디오·결과 뒤집기·조건 행·요약 줄.
 * 데이터는 모두 props이고 서버를 부르지 않는다. 연산자 목록이 없으면(로딩·오류·꺼짐) 연산자를 자유 입력으로 받는다.
 * `all`·`any`가 함께 있는 값은 폼으로 그릴 수 없어 JSON 편집만 열어 두고 데이터는 그대로 보존한다.
 */
export function ConditionList(p: ConditionListProps) {
  const m = p.messages ?? delegationMessages.condition;
  const uid = useId();
  const prefix = p.idPrefix ?? `cond-${uid}`;
  const root = useRef<HTMLDivElement>(null);
  const [live, setLive] = useState("");
  const [focusAt, setFocusAt] = useState<{ index: number; token: number } | null>(null);
  const spec = p.value ?? undefined;
  const shape = conditionShape(spec);
  const mode = formMode(spec);
  const items = itemsOf(spec);
  const disabled = p.disabled === true;
  const titles = Object.fromEntries((p.pathSuggestions ?? []).filter((s) => s.title !== undefined).map((s) => [s.value, s.title as string]));

  useEffect(() => {
    if (focusAt === null) return;
    const el = root.current?.querySelector<HTMLElement>(`[data-row="${focusAt.index}"] [data-field="path"]`);
    el?.focus();
  }, [focusAt]);

  if (shape === "both") return <MixedModes {...p} messages={m} idPrefix={prefix} />;

  const emit = (nextMode: ConditionMode, next: readonly ConditionItem[]) => p.onChange(withItems(spec, nextMode, next));
  const setItem = (i: number, patch: Partial<ConditionItem>) => {
    const cur = items[i];
    if (cur === undefined) return;
    const merged: Record<string, unknown> = { ...cur, ...patch };
    for (const k of Object.keys(patch)) if (merged[k] === undefined) delete merged[k];
    emit(mode, items.map((x, j) => (j === i ? (merged as unknown as ConditionItem) : x)));
  };
  const insertAt = (index: number, item: ConditionItem) => {
    const next = [...items];
    next.splice(index, 0, item);
    emit(mode, next);
    setLive(m.row.added(index + 1));
    setFocusAt((cur) => ({ index, token: (cur?.token ?? 0) + 1 }));
  };
  const remove = (i: number) => {
    emit(mode, items.filter((_, j) => j !== i));
    setLive(m.row.removed(i + 1));
    const target = Math.max(0, Math.min(i, items.length - 2));
    if (items.length > 1) setFocusAt((cur) => ({ index: target, token: (cur?.token ?? 0) + 1 }));
  };
  const move = (i: number, delta: -1 | 1) => {
    const to = i + delta;
    if (to < 0 || to >= items.length) return;
    const next = [...items];
    const [x] = next.splice(i, 1);
    next.splice(to, 0, x!);
    emit(mode, next);
    setLive(m.row.moved(to + 1, delta < 0 ? "up" : "down"));
    root.current?.querySelector<HTMLElement>(`[data-row="${to}"]`)?.focus();
  };
  const blank = (): ConditionItem => ({ path: "", op: "" });

  const summary = summarizeConditions(spec, p.operators, titles, m.summary);
  const rowError = (i: number) => (p.errors ?? []).filter((e) => e.path.startsWith(`/${mode}/${i}`));

  return (
    <div ref={root} className="dlg-cond" role="group" aria-label={p.label ?? m.title} data-state={p.operatorsState}>
      <div className="dlg-cond-head">
        <fieldset className="dlg-cond-mode">
          <legend className="ac-sr-only">{m.mode.label}</legend>
          {(["all", "any"] as const).map((k) => (
            <label key={k} className="app-check">
              <input type="radio" name={`${prefix}-mode`} checked={mode === k} disabled={disabled} onChange={() => p.onChange(switchMode(spec, k))} />
              {m.mode[k]}
            </label>
          ))}
        </fieldset>
        <label className="app-check">
          <input type="checkbox" checked={spec?.negate === true} disabled={disabled} onChange={(e) => p.onChange(withNegate(spec, e.target.checked))} />
          {m.negate}
        </label>
      </div>

      {p.operatorsState === "error" ? (
        <p className="app-muted dlg-note" role="status">
          {m.operatorError}
          {p.onRetryOperators ? <> <button type="button" className="app-link-btn" onClick={p.onRetryOperators}>{m.operatorRetry}</button></> : null}
        </p>
      ) : null}

      {items.length === 0 ? <p className="app-muted dlg-note">{m.empty}</p> : null}
      <div className="dlg-cond-rows">
        {items.map((item, i) => (
          <ConditionRow
            key={i}
            index={i}
            total={items.length}
            item={item}
            id={`${prefix}-${i}`}
            operators={p.operators}
            operatorsState={p.operatorsState}
            suggestions={p.pathSuggestions}
            errors={rowError(i)}
            disabled={disabled}
            messages={m}
            onItem={(patch) => setItem(i, patch)}
            onMove={(d) => move(i, d)}
            onInsertBelow={() => insertAt(i + 1, blank())}
            onDuplicate={() => insertAt(i + 1, { ...item })}
            onRemove={() => remove(i)}
          />
        ))}
      </div>
      <div className="dlg-cond-foot">
        <Button size="sm" disabled={disabled} onClick={() => insertAt(items.length, blank())}>+ {m.add}</Button>
      </div>
      {items.length > (p.manyThreshold ?? DEFAULT_MANY) ? <p className="app-muted dlg-note">{m.many}</p> : null}
      <p className={summary.empty ? "dlg-note dlg-warn" : "app-muted dlg-note"} aria-label={m.summary.label}>
        {summary.empty ? m.emptySummary : summary.full}
      </p>
      <span className="ac-sr-only" role="status" aria-live="polite">{live}</span>
    </div>
  );
}

function MixedModes({ value, onChange, disabled, messages: m, idPrefix, label }: ConditionListProps & { messages: typeof delegationMessages.condition; idPrefix: string }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [bad, setBad] = useState(false);
  return (
    <div className="dlg-cond" role="group" aria-label={label ?? m.title}>
      <p className="app-muted dlg-note" role="status">
        {m.mixedModes}{" "}
        {!editing ? <button type="button" className="app-link-btn" disabled={disabled} onClick={() => setEditing(true)}>{m.editJson}</button> : null}
      </p>
      {editing ? (
        <>
          <textarea
            id={`${idPrefix}-json`}
            className="ac-input ac-mono dlg-json"
            rows={8}
            aria-label={m.jsonLabel}
            aria-invalid={bad}
            value={text}
            disabled={disabled}
            onChange={(e) => {
              setText(e.target.value);
              try {
                onChange(JSON.parse(e.target.value) as ConditionSpec);
                setBad(false);
              } catch {
                setBad(true);
              }
            }}
          />
          {bad ? <span className="lib-field-error" role="alert">{m.jsonInvalid}</span> : null}
        </>
      ) : (
        <pre className="ac-pre app-json">{JSON.stringify(value, null, 2)}</pre>
      )}
    </div>
  );
}

interface RowProps {
  index: number;
  total: number;
  item: ConditionItem;
  id: string;
  operators: readonly ConditionOperatorDescriptor[] | null;
  operatorsState: OperatorsState;
  suggestions: readonly { value: string; title?: string }[] | undefined;
  errors: readonly ConditionError[];
  disabled: boolean;
  messages: typeof delegationMessages.condition;
  onItem(patch: Partial<ConditionItem>): void;
  onMove(delta: -1 | 1): void;
  onInsertBelow(): void;
  onDuplicate(): void;
  onRemove(): void;
}

function ConditionRow(r: RowProps) {
  const m = r.messages;
  const ime = useImeGuard();
  const listId = `${r.id}-paths`;
  const pathBad = r.item.path !== "" && !r.item.path.startsWith("/");
  const known = r.operators?.find((o) => o.id === r.item.op);
  const unknownOp = r.operatorsState === "ready" && r.item.op !== "" && known === undefined;
  const opErrors = r.errors.filter((e) => e.path.endsWith("/op"));
  const valueErrors = r.errors.filter((e) => e.path.endsWith("/value"));

  // 행 자신에 포커스가 있을 때만 단축키를 쓴다(입력 칸 안에서는 쓰지 않는다). 한글 조합 중에는 모두 멈춘다.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget || isImeKeyEvent(e) || ime.isIme(e)) return;
    if (e.key === "Enter") {
      e.preventDefault(); // 폼 제출 방지: 입력 밖에서 Enter는 아무 동작도 하지 않는다
    } else if (e.key === "Delete") {
      e.preventDefault();
      if (!r.disabled) r.onRemove();
    } else if (e.key === "Insert") {
      e.preventDefault();
      if (!r.disabled) r.onInsertBelow();
    } else if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      if (!r.disabled) r.onMove(e.key === "ArrowUp" ? -1 : 1);
    }
  };

  return (
    <div
      className="dlg-cond-row"
      role="group"
      tabIndex={0}
      data-row={r.index}
      aria-label={m.row.group(r.index + 1, r.total)}
      aria-keyshortcuts="Delete Insert Alt+ArrowUp Alt+ArrowDown"
      onKeyDown={onKeyDown}
    >
      <div className="dlg-cond-cell dlg-cond-path">
        <label className="ac-sr-only" htmlFor={`${r.id}-path`}>{m.row.path}</label>
        <input
          id={`${r.id}-path`}
          data-field="path"
          className="ac-input ac-mono"
          list={r.suggestions && r.suggestions.length > 0 ? listId : undefined}
          placeholder={m.row.pathPlaceholder}
          value={r.item.path}
          disabled={r.disabled}
          aria-invalid={pathBad}
          {...(pathBad ? { "aria-describedby": `${r.id}-path-err` } : {})}
          {...ime.handlers}
          onChange={(e) => r.onItem({ path: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.preventDefault();
          }}
        />
        {r.suggestions && r.suggestions.length > 0 ? (
          <datalist id={listId}>
            {r.suggestions.map((s) => (
              <option key={s.value} value={s.value} label={s.title ?? s.value}>{s.title ?? s.value}</option>
            ))}
          </datalist>
        ) : null}
        {pathBad ? <span id={`${r.id}-path-err`} className="lib-field-error" role="alert">{m.pathInvalid}</span> : null}
      </div>
      <div className="dlg-cond-cell dlg-cond-op">
        <label className="ac-sr-only" htmlFor={`${r.id}-op`}>{m.row.operator}</label>
        {r.operatorsState === "loading" ? (
          <div className="app-skeleton-row dlg-skel" role="status" aria-label={m.operatorLoading} />
        ) : r.operatorsState === "ready" && r.operators !== null ? (
          <select
            id={`${r.id}-op`}
            data-field="op"
            value={r.item.op}
            disabled={r.disabled}
            aria-invalid={unknownOp}
            onChange={(e) => {
              const next = r.operators?.find((o) => o.id === e.target.value);
              // 값이 필요 없는 연산자로 바꾸면 값을 비운다
              r.onItem({ op: e.target.value, ...(next !== undefined && forbidsValue(next.value_schema) ? { value: undefined } : {}) });
            }}
          >
            {r.item.op === "" ? <option value="">{m.row.operatorUnset}</option> : null}
            {unknownOp ? <option value={r.item.op}>{m.operatorUnknown(r.item.op)}</option> : null}
            {r.operators.map((o) => (
              <option key={o.id} value={o.id} title={o.description}>{o.title}</option>
            ))}
          </select>
        ) : (
          <input
            id={`${r.id}-op`}
            data-field="op"
            className="ac-input ac-mono"
            placeholder={m.operatorFree}
            value={r.item.op}
            disabled={r.disabled}
            {...ime.handlers}
            onChange={(e) => r.onItem({ op: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.preventDefault();
            }}
          />
        )}
        {known?.description ? <span className="app-muted dlg-note ac-ellipsis">{known.description}</span> : null}
        {unknownOp ? <span className="dlg-warn" role="alert">▲ {m.operatorUnknownWarn(r.item.op)}</span> : null}
        {opErrors.map((e, i) => <span key={i} className="dlg-warn" role="alert">▲ {e.message}</span>)}
      </div>
      <div className="dlg-cond-cell dlg-cond-val">
        <ValueEditor
          id={`${r.id}-value`}
          label={m.row.value}
          value={r.item.value}
          operator={known}
          disabled={r.disabled}
          error={valueErrors[0]?.message}
          messages={m}
          onChange={(v) => r.onItem({ value: v })}
        />
      </div>
      <div className="dlg-cond-menu">
        <ActionMenu
          label={`${m.row.menu}: ${m.row.group(r.index + 1, r.total)}`}
          items={[
            { id: "up", label: m.row.moveUp, disabled: r.disabled || r.index === 0, onSelect: () => r.onMove(-1) },
            { id: "down", label: m.row.moveDown, disabled: r.disabled || r.index === r.total - 1, onSelect: () => r.onMove(1) },
            { id: "dup", label: m.row.duplicate, disabled: r.disabled, onSelect: r.onDuplicate },
            { id: "del", label: m.row.remove, danger: true, disabled: r.disabled, onSelect: r.onRemove },
          ]}
        >
          ⋮
        </ActionMenu>
      </div>
    </div>
  );
}
