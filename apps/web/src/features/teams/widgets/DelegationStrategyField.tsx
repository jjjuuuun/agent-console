import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { DelegationStrategyDescriptor } from "@agent-console/contracts";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { Button } from "@agent-console/ui";
import { ATTRIBUTE_ROWS, SessionChip, attributeRows, attributeSummary, hasAttributes, sessionOf, type AttributeCell } from "../../delegation";
import { teamMessages } from "../messages";

const m = teamMessages.sessions;

/** `ui:field` 이름(스키마 `ui_schema`·앱 빌더가 지정하는 데이터 이름). 방식 이름은 코드에 없다. */
export const DELEGATION_STRATEGY_FIELD = "delegation-strategy";

/** 목록 불러오기 상태(컨테이너가 채운다). */
export interface StrategiesStatus {
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
}

/** `ui:options`로 넘어오는 데이터. 함수·목록은 앱(`EdgeConfigForm`)이 채운다. */
export interface DelegationStrategyOptions {
  /** 서버 순서의 방식 목록 */
  strategies: readonly DelegationStrategyDescriptor[];
  status?: StrategiesStatus;
  /** 연결 종류가 정한 기본 방식 id */
  defaultId: string;
  delegatorLabel?: string;
  /** 비교표 열 머리로 방식을 바꿀 때(되돌리기 토스트를 앱이 붙인다). 없으면 일반 변경 */
  onPickFromCompare?: (id: string) => void;
}

const isOptions = (o: Record<string, unknown>): o is Record<string, unknown> & DelegationStrategyOptions => Array.isArray(o["strategies"]) && typeof o["defaultId"] === "string";

/** 값 한 칸: 알 수 없는 원문은 mono. */
function Value({ cell }: { cell: AttributeCell }) {
  return cell.unknownValue ? <span className="app-mono">{cell.long}</span> : <span>{cell.long}</span>;
}

/** "동작 방식" 블록(현재 방식의 속성 행) + 접힌 비교표. 속성이 하나도 없으면 아무것도 그리지 않는다. */
export function StrategyBehavior({ strategies, current, delegatorLabel, onPick, disabled }: { strategies: readonly DelegationStrategyDescriptor[]; current: DelegationStrategyDescriptor; delegatorLabel: string; onPick: (id: string) => void; disabled: boolean }) {
  const [compare, setCompare] = useState(false);
  const tableId = useId();
  const rows = attributeRows(current, delegatorLabel);
  const columns = useMemo(() => [current, ...strategies.filter((s) => s.id !== current.id)], [current, strategies]);
  const columnRows = useMemo(() => columns.map((s) => new Map(attributeRows(s, delegatorLabel).map((r) => [r.key, r]))), [columns, delegatorLabel]);
  const rowKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const map of columnRows) for (const k of map.keys()) keys.add(k);
    return ATTRIBUTE_ROWS.filter((k) => keys.has(k));
  }, [columnRows]);
  if (rows.length === 0) return null;
  const sessionValue = sessionOf(current);
  return (
    <section className="ses-block" aria-label={m.panelTitle}>
      <h4 className="ses-block-title">{m.panelTitle}</h4>
      <dl className="ses-rows">
        {rows.map((r) => (
          <div key={r.key} className="ses-row" data-attr={r.key}>
            <dt>{r.label}</dt>
            <dd>
              {r.key === "session" && sessionValue !== undefined ? <SessionChip value={sessionValue} delegatorLabel={delegatorLabel} /> : null} <Value cell={r} />
            </dd>
          </div>
        ))}
      </dl>
      {strategies.length > 1 ? (
        <>
          <button type="button" className="app-link-btn" aria-expanded={compare} aria-controls={tableId} onClick={() => setCompare((v) => !v)}>
            {compare ? m.compareHide : m.compare} {compare ? "▾" : "▸"}
          </button>
          {compare ? (
            <div className="ses-compare" id={tableId} role="region" aria-label={m.compare} tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col" className="ses-sticky" />
                    {columns.map((s, i) => (
                      <th key={s.id} scope="col" data-current={i === 0 ? "true" : undefined}>
                        {i === 0 ? (
                          <strong>{s.title}</strong>
                        ) : (
                          <button type="button" className="app-link-btn" disabled={disabled} title={m.compareColumns(s.title)} onClick={() => onPick(s.id)}>
                            {s.title}
                          </button>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rowKeys.map((k) => (
                    <tr key={k}>
                      <th scope="row" className="ses-sticky">{[...columnRows.map((c) => c.get(k)).filter((c): c is AttributeCell => c !== undefined)][0]?.label}</th>
                      {columnRows.map((c, i) => {
                        const cell = c.get(k);
                        return <td key={columns[i]!.id}>{cell === undefined ? "–" : cell.unknownValue ? <span className="app-mono">{cell.long}</span> : (cell.short ?? cell.long)}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

/**
 * 위임 방식 필드: 2줄 옵션(방식 title + 속성 요약)의 목록 상자 + 현재 방식의 "동작 방식" 블록.
 * 방식 이름·속성은 모두 디스크립터 데이터이고, 속성이 없는 방식은 요약 줄·블록이 없다(screen-delegation.md §14.4.2·§14.4.6).
 */
export function DelegationStrategyField({ id, value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const o = isOptions(options) ? options : undefined;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (root.current !== null && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  if (o === undefined) return null;
  const locked = disabled || readonly;
  const delegator = o.delegatorLabel ?? "";
  const status = o.status;
  const chosen = typeof value === "string" && value !== "" ? value : undefined;
  const effectiveId = chosen ?? o.defaultId;
  const defaultStrategy = o.strategies.find((s) => s.id === o.defaultId);
  const current = o.strategies.find((s) => s.id === effectiveId);
  // 선택지: [종류 기본, ...서버 순서 방식]
  const choices: { value: string; title: string; summary: string; description: string | undefined }[] = [
    { value: "", title: defaultStrategy === undefined ? m.strategyDefaultUnknown : m.strategyDefault(defaultStrategy.title), summary: attributeSummary(defaultStrategy), description: defaultStrategy?.description },
    ...o.strategies.map((s) => ({ value: s.id, title: s.title, summary: attributeSummary(s), description: s.description })),
  ];
  const selectedIndex = choices.findIndex((c) => c.value === (chosen ?? ""));
  const shownTitle = chosen === undefined ? choices[0]!.title : (current?.title ?? chosen);
  const pick = (v: string) => {
    onChange(v === "" ? null : v);
    setOpen(false);
  };
  const onKey = (e: KeyboardEvent) => {
    if (locked) return;
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      setActive(Math.max(0, selectedIndex));
      setOpen(true);
    } else if (open && e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(choices.length - 1, a + 1));
    } else if (open && e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (open && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      pick(choices[active]!.value);
    } else if (open && e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
    }
  };
  return (
    <div className="ses-strategy" ref={root}>
      <span className="lib-field-label" id={`${id}-label`}>{label}</span>
      {status?.loading === true ? (
        <div className="ses-skeleton" aria-busy="true" role="status" aria-label={m.panelTitle}>
          {[0, 1, 2, 3].map((i) => <span key={i} className="ses-skeleton-row" />)}
        </div>
      ) : (
        <>
          <button
            type="button"
            id={id}
            className="ses-select ac-input"
            role="combobox"
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-controls={listId}
            aria-labelledby={`${id}-label`}
            aria-activedescendant={open ? `${listId}-${active}` : undefined}
            disabled={locked}
            onClick={() => {
              setActive(Math.max(0, selectedIndex));
              setOpen((v) => !v);
            }}
            onKeyDown={onKey}
          >
            <span className="ac-ellipsis">{shownTitle}</span>
            <span aria-hidden="true">▾</span>
          </button>
          {open ? (
            <ul className="ses-options" id={listId} role="listbox" aria-label={m.strategyList}>
              {choices.map((c, i) => (
                <li
                  key={c.value === "" ? "default" : c.value}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === selectedIndex}
                  data-active={i === active ? "true" : undefined}
                  title={c.description}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pick(c.value)}
                >
                  <span className="ses-option-title">{c.title}</span>
                  {c.summary !== "" ? <span className="ses-option-sub">{c.summary}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {current !== undefined && hasAttributes(current) ? (
            <p className="app-muted lib-field-note" data-ses-summary="">{attributeSummary(current)}</p>
          ) : null}
        </>
      )}
      {status?.error === true ? (
        <p className="app-muted lib-field-note" role="status">
          ⓘ {m.strategyLoadFailed}{" "}
          {status.onRetry !== undefined ? <Button size="sm" variant="ghost" onClick={status.onRetry}>{m.strategyRetry}</Button> : null}
        </p>
      ) : null}
      {status?.loading !== true && status?.error !== true && current === undefined ? (
        <p className="app-muted lib-field-note" role="status">{m.strategyUnknown(effectiveId)}</p>
      ) : null}
      {status?.loading !== true && current !== undefined ? (
        <StrategyBehavior strategies={o.strategies} current={current} delegatorLabel={delegator} disabled={locked} onPick={o.onPickFromCompare ?? pick} />
      ) : null}
    </div>
  );
}
