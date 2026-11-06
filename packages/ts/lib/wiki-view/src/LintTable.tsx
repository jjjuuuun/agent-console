import type { WikiIssue } from "@agent-console/contracts/wiki";
import { ToneChip } from "@agent-console/markdown-doc";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { resolveDisplay, severityRank, type WikiDisplay } from "./display";
import { isComposingEvent, useDomId } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { VirtualList } from "./VirtualList";

export type LintSortKey = "severity" | "code" | "page";

/** 거르기 상태(심각도 여럿·코드 하나·페이지 경로 조각). 호출자가 주소 등에 저장하려고 주고받는다. */
export interface LintFilter {
  severities: readonly string[];
  code: string;
  page: string;
}

export interface LintTableProps {
  /** 처음 거르기 상태(예: 주소 인자). 이후는 표가 관리한다. */
  initialFilter?: Partial<LintFilter>;
  /** 거르기가 바뀔 때(처음 그릴 때는 부르지 않는다) */
  onFilterChange?: (filter: LintFilter) => void;
  issues: readonly WikiIssue[];
  display?: WikiDisplay;
  /** 심각도 순서(앞이 심각). 모르는 값은 뒤. 예: 서버 어휘 `["error","warning","info"]`를 앱 데이터로 준다. */
  severityOrder?: readonly string[];
  /** 이슈의 줄 번호. 기본은 `details.line`(숫자). */
  lineOf?: (issue: WikiIssue) => number | null;
  /** 이슈를 만든 규칙 id. 기본은 `details.rule_id`(문자열). 없으면 "–". */
  ruleOf?: (issue: WikiIssue) => string | null;
  /** 행 클릭·Enter: 그 페이지(+줄)를 연다. */
  onOpen?: (issue: WikiIssue, line: number | null) => void;
  /** Shift+F10·ContextMenu·우클릭: 행 메뉴(열기·경로 복사·규칙 열기) */
  onContextMenu?: (issue: WikiIssue, anchor: HTMLElement) => void;
  /** 점검이 일부 페이지만 했다는 서버 안내 등 표 위에 붙일 것 */
  notice?: React.ReactNode;
  rowHeight?: number;
  height?: number | string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

function defaultLine(issue: WikiIssue): number | null {
  const v = issue.details?.["line"];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function defaultRule(issue: WikiIssue): string | null {
  const v = issue.details?.["rule_id"];
  return typeof v === "string" && v !== "" ? v : null;
}

const collator = new Intl.Collator("ko", { numeric: true });

/**
 * 점검 표(가상 그리드). 열 6개(심각도·코드·페이지·줄·메시지·규칙)는 숨기지 않는다. 거르기 목록(심각도·코드)은 데이터에서 만들고
 * 모르는 심각도·코드는 원문 + 중립 톤이다. 정렬은 심각도(순서는 prop)·코드·페이지. 모든 거르기·정렬은 클라이언트다.
 */
export function LintTable({
  initialFilter, onFilterChange, issues, display, severityOrder = [], lineOf = defaultLine, ruleOf = defaultRule, onOpen, onContextMenu, notice, rowHeight = 32, height, messages, className,
}: LintTableProps) {
  const t = resolveMessages(messages);
  const base = useDomId();
  const [sevFilter, setSevFilter] = useState<ReadonlySet<string>>(() => new Set(initialFilter?.severities ?? []));
  const [codeFilter, setCodeFilter] = useState(initialFilter?.code ?? "");
  const [pageFilter, setPageFilter] = useState(initialFilter?.page ?? "");
  const notify = useRef(onFilterChange);
  const mounted = useRef(false);
  useEffect(() => {
    notify.current = onFilterChange;
  });
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    notify.current?.({ severities: [...sevFilter], code: codeFilter, page: pageFilter });
  }, [sevFilter, codeFilter, pageFilter]);
  const [sort, setSort] = useState<{ key: LintSortKey; dir: "asc" | "desc" }>({ key: "severity", dir: "asc" });
  const [active, setActive] = useState(0);

  const severities = useMemo(() => [...new Set(issues.map((i) => i.severity as string))].sort((a, b) => severityRank(a, severityOrder) - severityRank(b, severityOrder) || a.localeCompare(b)), [issues, severityOrder]);
  const codes = useMemo(() => [...new Set(issues.map((i) => i.code))].sort(collator.compare), [issues]);
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const i of issues) m.set(i.severity, (m.get(i.severity) ?? 0) + 1);
    return m;
  }, [issues]);

  const rows = useMemo(() => {
    const needle = pageFilter.trim().toLowerCase();
    const filtered = issues.filter(
      (i) => (sevFilter.size === 0 || sevFilter.has(i.severity)) && (codeFilter === "" || i.code === codeFilter) && (needle === "" || (i.path ?? "").toLowerCase().includes(needle)),
    );
    const dir = sort.dir === "asc" ? 1 : -1;
    const cmpPage = (a: WikiIssue, b: WikiIssue) => collator.compare(a.path ?? "", b.path ?? "");
    return [...filtered].sort((a, b) => {
      const c =
        sort.key === "severity"
          ? severityRank(a.severity, severityOrder) - severityRank(b.severity, severityOrder)
          : sort.key === "code"
            ? collator.compare(a.code, b.code)
            : cmpPage(a, b);
      if (c !== 0) return c * dir;
      return cmpPage(a, b) || (lineOf(a) ?? 0) - (lineOf(b) ?? 0);
    });
  }, [issues, sevFilter, codeFilter, pageFilter, sort, severityOrder, lineOf]);

  const filtered = sevFilter.size > 0 || codeFilter !== "" || pageFilter.trim() !== "";
  const shown = Math.min(Math.max(active, 0), Math.max(rows.length - 1, 0));
  const rowId = (i: number) => `${base}-r${i}`;
  const clear = () => {
    setSevFilter(new Set());
    setCodeFilter("");
    setPageFilter("");
  };
  const toggleSort = (key: LintSortKey) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  const ariaSort = (key: LintSortKey): "ascending" | "descending" | "none" => (sort.key === key ? (sort.dir === "asc" ? "ascending" : "descending") : "none");

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (rows.length === 0 || isComposingEvent(e)) return;
    const go = (to: number) => {
      e.preventDefault();
      setActive(Math.min(Math.max(0, to), rows.length - 1));
    };
    const row = rows[shown]!;
    if (e.key === "ArrowDown") return go(shown + 1);
    if (e.key === "ArrowUp") return go(shown - 1);
    if (e.key === "PageDown") return go(shown + 10);
    if (e.key === "PageUp") return go(shown - 10);
    if (e.key === "Home") return go(0);
    if (e.key === "End") return go(rows.length - 1);
    if (e.key === "Enter") {
      e.preventDefault();
      onOpen?.(row, lineOf(row));
    } else if ((e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) && onContextMenu) {
      e.preventDefault();
      const el = e.currentTarget.querySelector<HTMLElement>(`#${rowId(shown)}`);
      onContextMenu(row, el ?? e.currentTarget);
    }
  };

  const root = `ac-wk-root ac-wk-lint${className ? ` ${className}` : ""}`;
  if (issues.length === 0) {
    return (
      <div className={`${root} ac-wk-state-block`} role="status">
        <ToneChip label={t["lint.none"] ?? ""} tone="success" size="normal" />
        {notice}
      </div>
    );
  }
  const head = (key: LintSortKey, label: string) => (
    <div role="columnheader" aria-sort={ariaSort(key)} className="ac-wk-cell">
      <button type="button" className="ac-wk-sortbtn" onClick={() => toggleSort(key)}>
        {label}
        <span aria-hidden="true">{sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}</span>
      </button>
    </div>
  );
  return (
    <div className={root} style={{ display: "flex", flexDirection: "column", ...(height !== undefined ? { height } : {}) }}>
      <div className="ac-wk-inline ac-wk-lint-summary" role="group" aria-label={t["lint.summary"]}>
        {severities.map((s) => {
          const d = resolveDisplay(display?.severities, s);
          return (
            <button
              key={s}
              type="button"
              className="ac-wk-filterbtn"
              aria-pressed={sevFilter.has(s)}
              title={formatMessage(t["lint.filter.severity"], { severity: d.label })}
              onClick={() =>
                setSevFilter((prev) => {
                  const next = new Set(prev);
                  if (next.has(s)) next.delete(s);
                  else next.add(s);
                  return next;
                })
              }
            >
              <ToneChip label={d.label} tone={d.tone} />
              <span className="ac-wk-num">{counts.get(s) ?? 0}</span>
            </button>
          );
        })}
        <select className="ac-wk-input" aria-label={t["lint.filter.code"]} value={codeFilter} onChange={(e) => setCodeFilter(e.target.value)}>
          <option value="">{t["lint.filter.codeAll"]}</option>
          {codes.map((c) => (
            <option key={c} value={c}>{resolveDisplay(display?.codes, c).label}</option>
          ))}
        </select>
        <input type="search" className="ac-wk-input" aria-label={t["lint.filter.page"]} placeholder={t["lint.filter.page"]} value={pageFilter} onChange={(e) => setPageFilter(e.target.value)} />
      </div>
      {notice}
      <div
        role="grid"
        aria-label={t["lint.label"]}
        aria-rowcount={rows.length + 1}
        tabIndex={0}
        aria-activedescendant={rows.length > 0 ? rowId(shown) : undefined}
        onKeyDown={onKeyDown}
        className="ac-wk-grid"
        style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}
      >
        <div role="row" className="ac-wk-grid-row ac-wk-grid-head">
          {head("severity", t["lint.col.severity"] ?? "")}
          {head("code", t["lint.col.code"] ?? "")}
          {head("page", t["lint.col.page"] ?? "")}
          <div role="columnheader" className="ac-wk-cell ac-wk-right">{t["lint.col.line"]}</div>
          <div role="columnheader" className="ac-wk-cell">{t["lint.col.message"]}</div>
          <div role="columnheader" className="ac-wk-cell">{t["lint.col.rule"]}</div>
        </div>
        {rows.length === 0 ? (
          <p className="ac-wk-muted ac-wk-empty" role="status">
            {t["lint.noMatch"]}{" "}
            {filtered ? <button type="button" className="ac-wk-linkbtn" onClick={clear}>{t["lint.clearFilter"]}</button> : null}
          </p>
        ) : (
          <VirtualList
            items={rows}
            rowHeight={rowHeight}
            role="rowgroup"
            ariaLabel={t["lint.label"] ?? ""}
            activeIndex={shown}
            getKey={(r, i) => `${r.code}:${r.path ?? ""}:${i}`}
            renderRow={(issue, ctx) => {
              const sev = resolveDisplay(display?.severities, issue.severity);
              const code = resolveDisplay(display?.codes, issue.code);
              const line = lineOf(issue);
              const rule = ruleOf(issue);
              return (
                <div
                  id={rowId(ctx.index)}
                  role="row"
                  aria-rowindex={ctx.posInSet + 1}
                  data-active={ctx.index === shown || undefined}
                  className="ac-wk-grid-row ac-wk-grid-body"
                  style={ctx.style}
                  onClick={() => {
                    setActive(ctx.index);
                    onOpen?.(issue, line);
                  }}
                  onContextMenu={(e) => {
                    if (!onContextMenu) return;
                    e.preventDefault();
                    onContextMenu(issue, e.currentTarget);
                  }}
                >
                  <div role="gridcell" className="ac-wk-cell"><ToneChip label={sev.label} tone={sev.tone} /></div>
                  <div role="gridcell" className={`ac-wk-cell ac-wk-ellipsis${code.known ? "" : " ac-wk-mono"}`} title={`${issue.code}${code.hint ? `\n${code.hint}` : ""}`}>{code.label}</div>
                  <div role="gridcell" className="ac-wk-cell ac-wk-ellipsis ac-wk-mono" title={issue.path ?? undefined}>{issue.path ?? "–"}</div>
                  <div role="gridcell" className="ac-wk-cell ac-wk-right ac-wk-num">{line ?? "–"}</div>
                  <div role="gridcell" className="ac-wk-cell ac-wk-ellipsis" title={issue.message}>{issue.message}</div>
                  <div role="gridcell" className="ac-wk-cell ac-wk-ellipsis ac-wk-mono" title={rule ?? undefined}>{rule ?? "–"}</div>
                </div>
              );
            }}
          />
        )}
      </div>
    </div>
  );
}
