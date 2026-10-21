import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { DiffChange } from "@agent-console/contracts";
import { Icon } from "@agent-console/ui";
import { versionMessages as t } from "./messages";
import { countOps, matchesQuery, previewValue, type DiffOpName } from "./versionsLogic";

export interface DiffTableProps {
  changes: readonly DiffChange[];
  /** 변경의 읽는 경로(없으면 원문 경로). 표시 전용 */
  readable?: (change: DiffChange) => string;
}

const OPS: readonly DiffOpName[] = ["add", "remove", "replace"];

function ValueCell({ change, side, expanded }: { change: DiffChange; side: "before" | "after"; expanded: boolean }) {
  const value = side === "before" ? change.before : change.after;
  if (value === undefined && !(change.secret === true)) return <span className="app-muted" aria-hidden="true">–</span>;
  const preview = previewValue(value);
  if (preview.complex && expanded) return <pre className="ac-pre ver-json">{preview.full}</pre>;
  return (
    <span className={preview.complex ? "lib-mono" : "app-wrap"} title={preview.truncated || preview.complex ? preview.full : undefined}>
      {preview.text}
    </span>
  );
}

/**
 * 필드 변경 표(`DefinitionDiff.changes`). 동작은 아이콘+텍스트, 비밀(`secret`) 행은 서버가 준 값을 그대로 보이고 칩을 붙인다.
 * 필터(동작)·검색(경로·값)·정렬은 서버 순서 유지. 도메인·API를 모른다.
 */
export function DiffTable({ changes, readable }: DiffTableProps) {
  const [ops, setOps] = useState<ReadonlySet<DiffOpName>>(new Set());
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const [active, setActive] = useState(0);
  const search = useRef<HTMLInputElement>(null);
  const rows = useRef(new Map<number, HTMLTableRowElement>());

  const counts = useMemo(() => countOps(changes), [changes]);
  const labelOf = (c: DiffChange) => readable?.(c) ?? c.path;
  const visible = useMemo(
    () =>
      changes
        .map((change, index) => ({ change, index }))
        .filter(({ change }) => (ops.size === 0 || ops.has(change.op)) && matchesQuery(change, readable?.(change) ?? change.path, query)),
    [changes, ops, query, readable],
  );

  const toggleOp = (op: DiffOpName) =>
    setOps((prev) => {
      const next = new Set(prev);
      if (next.has(op)) next.delete(op);
      else next.add(op);
      return next;
    });
  const toggleOpen = (index: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  const focusRow = (position: number) => {
    const target = visible[position];
    if (target === undefined) return;
    setActive(position);
    rows.current.get(target.index)?.focus();
  };
  const onRowKey = (e: KeyboardEvent, position: number, index: number, complex: boolean) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      focusRow(Math.min(position + 1, visible.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusRow(Math.max(position - 1, 0));
    } else if (e.key === "Enter" && complex) {
      e.preventDefault();
      toggleOpen(index);
    }
  };
  const onRegionKey = (e: KeyboardEvent) => {
    const el = e.target as HTMLElement;
    if (e.key === "/" && el.tagName !== "INPUT" && el.tagName !== "TEXTAREA") {
      e.preventDefault();
      search.current?.focus();
    }
  };

  if (changes.length === 0) return <p className="app-muted">{t.fields.none}</p>;
  const activePos = Math.min(active, Math.max(visible.length - 1, 0));

  return (
    <div className="ver-diff" onKeyDown={onRegionKey}>
      <div className="ver-diff-tools">
        <span className="app-muted ac-num">{t.fields.counts(counts.add, counts.remove, counts.replace)}</span>
        <div role="group" aria-label={t.fields.filterLabel} className="ver-filter">
          {OPS.map((op) => (
            <button key={op} type="button" className="ac-btn" data-size="sm" data-variant={ops.has(op) ? "primary" : "secondary"} aria-pressed={ops.has(op)} onClick={() => toggleOp(op)}>
              <span className="ac-btn-label">
                <span aria-hidden="true">{t.fields.opIcons[op]}</span> {t.fields.ops[op]}
              </span>
            </button>
          ))}
        </div>
        <input ref={search} type="search" className="ac-input ver-search" aria-label={t.fields.searchLabel} placeholder={t.fields.searchPlaceholder} value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      {visible.length === 0 ? (
        <p className="app-muted">{t.fields.noMatch}</p>
      ) : (
        <table className="lib-grid ver-table" aria-label={t.fields.table}>
          <thead>
            <tr>
              <th scope="col">{t.fields.op}</th>
              <th scope="col">{t.fields.path}</th>
              <th scope="col">{t.fields.before}</th>
              <th scope="col">{t.fields.after}</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(({ change, index }, position) => {
              const complex = [change.before, change.after].some((v) => previewValue(v).complex);
              const expanded = open.has(index);
              const secret = change.secret === true;
              return (
                <tr
                  key={index}
                  ref={(el) => {
                    if (el) rows.current.set(index, el);
                    else rows.current.delete(index);
                  }}
                  tabIndex={position === activePos ? 0 : -1}
                  className="ver-row"
                  data-op={change.op}
                  data-secret={secret ? "true" : undefined}
                  aria-label={secret ? `${labelOf(change)} — ${t.fields.secretRow}` : undefined}
                  onFocus={() => setActive(position)}
                  onKeyDown={(e) => onRowKey(e, position, index, complex)}
                >
                  <td className="ver-op">
                    <span aria-hidden="true">{t.fields.opIcons[change.op] ?? "?"}</span> {t.fields.ops[change.op] ?? change.op}
                  </td>
                  <td className="ver-path">
                    <span className="app-wrap">{labelOf(change)}</span>
                    {labelOf(change) !== change.path ? <span className="lib-mono app-muted ver-pointer">{change.path}</span> : null}
                  </td>
                  <td>
                    <ValueCell change={change} side="before" expanded={expanded} />
                  </td>
                  <td>
                    <ValueCell change={change} side="after" expanded={expanded} />
                    {secret ? <span className="ver-secret"> <Icon name="lock" size={12} fallbackText="L" /> {t.fields.secretChip}</span> : null}
                    {complex ? (
                      <button type="button" className="app-link-btn ver-expand" aria-expanded={expanded} onClick={() => toggleOpen(index)}>
                        {expanded ? t.fields.collapse : t.fields.expand}
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
