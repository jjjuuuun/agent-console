import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { LogSessionSummary } from "@agent-console/contracts/logs";
import { fullTimeTitle, mergeFormatters, shortId } from "./format";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { listStateBlock, NeutralChip } from "./parts";
import type { ColumnSpec, Formatters, ListSlots } from "./types";
import { useVirtualRows } from "./virtual";
import type { RowMenuAnchor } from "./LogEventTable";

export interface SessionListProps extends ListSlots {
  sessions: readonly LogSessionSummary[];
  /** 열 정의(앱 데이터). `sessionColumns`로 기본 열을 만들 수 있다. */
  columns: readonly ColumnSpec<LogSessionSummary>[];
  selectedId?: string | null | undefined;
  /**
   * 키보드 커서가 놓인 행(`aria-activedescendant`)의 세션 id가 바뀔 때 알린다. 목록이 비면 null.
   * 앱이 "현재 행"(예: `C`로 id 복사)을 DOM에서 읽지 않고 이 값을 쓴다.
   */
  onActiveChange?: (id: string | null) => void;
  onOpen: (id: string) => void;
  onRowMenu?: (id: string, anchor: RowMenuAnchor) => void;
  /** 시작 시각 정렬 방향. 시작 열 머리 클릭으로만 바뀐다(다른 열은 정렬하지 않는다). */
  order: "asc" | "desc";
  onOrderChange?: (order: "asc" | "desc") => void;
  /** 서버 상한에 닿았는지(아래 안내). */
  limitReached?: boolean;
  limit?: number;
  /** 열 id 중 시작 열의 id(정렬 버튼이 붙는 열). */
  startColumnId?: string;
  /** 현재 시각(ms, 주입). 오늘 이전 세션은 날짜를 함께 보인다. */
  now?: () => number;
  /** 출처 id -> 표시 이름. 없으면 id. */
  sourceLabelFor?: (id: string) => string | undefined;
  /** 토큰 툴팁의 [사용량에서 보기] 같은 연동 슬롯. */
  renderTokenExtra?: (session: LogSessionSummary) => ReactNode;
  height?: number;
  formatters?: Partial<Formatters>;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

const w = (n: number | string) => (typeof n === "number" ? `${n}px` : n);

/** 기본 열 id 목록 -> ColumnSpec(머리글은 messages.sessionColumns). */
export function sessionColumns(ids: readonly string[], messages?: DeepPartial<LogViewMessages>, widths: Readonly<Record<string, number | string>> = {}): ColumnSpec<LogSessionSummary>[] {
  const m = mergeMessages(messages);
  const base: Record<string, number | string> = { start: 112, session: 96, project: 160, threads: 72, events: 80, errors: 64, models: 160, tokens: 88, length: 80, source: 120 };
  const endAligned = new Set(["events", "errors", "tokens", "length", "threads"]);
  return ids.map((id) => ({ id, header: m.sessionColumns[id] ?? id, width: widths[id] ?? base[id] ?? "minmax(0,1fr)", align: endAligned.has(id) ? "end" : "start" }));
}

/** 세션 표(가상 스크롤, `role="grid"`). 값이 없으면 0이 아니라 "–". 오류가 있으면 아이콘 + 색. */
export function SessionList(props: SessionListProps) {
  const { sessions, columns, selectedId, onActiveChange, onOpen, onRowMenu, order, onOrderChange, limitReached, limit, startColumnId = "start", height = 480, ariaLabel, sourceLabelFor, renderTokenExtra } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const formatters = useMemo(() => mergeFormatters(props.formatters), [props.formatters]);
  const now = props.now ?? Date.now;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<string | null>(null);
  const virt = useVirtualRows({ count: sessions.length, rowHeight: 32, scrollRef, fallbackHeight: height });
  const template = columns.map((c) => w(c.width)).join(" ");
  const activeIdx = Math.max(0, sessions.findIndex((s) => s.session === (active ?? selectedId)));

  const activeId = sessions[activeIdx]?.session ?? null;
  const activeChangeRef = useRef(onActiveChange);
  useEffect(() => {
    activeChangeRef.current = onActiveChange;
  });
  useEffect(() => activeChangeRef.current?.(activeId), [activeId]);

  const move = (i: number) => {
    const t = sessions[Math.min(sessions.length - 1, Math.max(0, i))];
    if (!t) return;
    setActive(t.session);
    virt.scrollToIndex(Math.min(sessions.length - 1, Math.max(0, i)));
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const page = Math.max(1, Math.floor(height / 32) - 1);
    const cur = sessions[activeIdx];
    if (e.key === "ArrowDown") { e.preventDefault(); move(activeIdx + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(activeIdx - 1); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(sessions.length - 1); }
    else if (e.key === "PageDown") { e.preventDefault(); move(activeIdx + page); }
    else if (e.key === "PageUp") { e.preventDefault(); move(activeIdx - page); }
    else if (e.key === "Enter" && cur) { e.preventDefault(); onOpen(cur.session); }
    else if ((e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) && cur) {
      e.preventDefault();
      onRowMenu?.(cur.session, { x: 0, y: 0 });
    }
  };

  const cell = (id: string, s: LogSessionSummary): ReactNode => {
    switch (id) {
      case "start": {
        if (s.first_time == null) return m.none;
        const d = new Date(s.first_time * 1000);
        const today = new Date(now());
        const p = (n: number) => String(n).padStart(2, "0");
        const hm = `${p(d.getHours())}:${p(d.getMinutes())}`;
        const text = d.toDateString() === today.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
        return <span className="ac-lv-num" title={fullTimeTitle(s.first_time)}>{text}</span>;
      }
      case "session":
        return <span className="ac-lv-mono" title={s.session}>{shortId(s.session)}</span>;
      case "project":
        return s.project ? <span className="ac-lv-ellipsis" title={s.project.id}>{s.project.label || s.project.id}</span> : m.none;
      case "threads":
        return s.thread_count == null ? m.none : <span className="ac-lv-num">{s.thread_count}</span>;
      case "events":
        return <span className="ac-lv-num">{formatters.number(s.events ?? 0)}</span>;
      case "errors": {
        const n = s.errors ?? 0;
        return n > 0 ? (
          <span className="ac-lv-num" data-tone="danger">
            <span aria-hidden="true">⚠ </span>
            {n}
          </span>
        ) : (
          <span className="ac-lv-num ac-lv-muted">0</span>
        );
      }
      case "models": {
        const list = s.models ?? [];
        if (list.length === 0) return m.none;
        return (
          <span className="ac-lv-chiprow">
            <NeutralChip title={list.join(", ")}>{list[0]}</NeutralChip>
            {list.length > 1 ? <span className="ac-lv-muted ac-lv-nowrap" title={list.join(", ")}>{fmt(m.multiMore, { n: list.length - 1 })}</span> : null}
          </span>
        );
      }
      case "tokens": {
        const t = s.tokens;
        if (t?.total == null) return m.none;
        const n = (v: number | null | undefined) => (v == null ? m.none : formatters.number(v));
        const tip = `${formatters.number(t.total)} · ${fmt(m.tokenTip, { input: n(t.input), output: n(t.output), read: n(t.cache_read), creation: n(t.cache_creation) })} · ${m.tokenOnce}`;
        return <span className="ac-lv-num ac-lv-nowrap" title={tip}>{formatters.tokens(t.total)}{renderTokenExtra?.(s)}</span>;
      }
      case "length":
        return s.first_time != null && s.last_time != null ? <span className="ac-lv-num">{formatters.duration(Math.max(0, (s.last_time - s.first_time) * 1000))}</span> : m.none;
      case "source": {
        const list = s.sources ?? [];
        return list.length ? <span className="ac-lv-chiprow">{list.slice(0, 1).map((x) => <NeutralChip key={x}>{sourceLabelFor?.(x) ?? x}</NeutralChip>)}{list.length > 1 ? <span className="ac-lv-muted ac-lv-nowrap" title={list.map((x) => sourceLabelFor?.(x) ?? x).join(", ")}>{fmt(m.multiMore, { n: list.length - 1 })}</span> : null}</span> : m.none;
      }
      default: {
        const v = (s as unknown as Record<string, unknown>)[id];
        return v == null || v === "" ? m.none : String(v);
      }
    }
  };

  const state = listStateBlock(props, sessions.length, m);
  return (
    <div className="ac-lv-table">
      {state && sessions.length === 0 ? (
        state
      ) : (
        <div role="grid" tabIndex={0} className="ac-lv-grid-table" aria-label={ariaLabel ?? m.sessionList} aria-rowcount={sessions.length + 1} aria-activedescendant={sessions[activeIdx] ? `lv-ses-${sessions[activeIdx]?.session}` : undefined} onKeyDown={onKeyDown}>
          <div role="row" aria-rowindex={1} className="ac-lv-rowhead" style={{ gridTemplateColumns: template }}>
            {columns.map((c) => (
              <div key={c.id} role="columnheader" data-align={c.align ?? "start"} className="ac-lv-ellipsis" aria-sort={c.id === startColumnId ? (order === "asc" ? "ascending" : "descending") : undefined}>
                {c.id === startColumnId && onOrderChange ? (
                  <button type="button" className="ac-lv-linkbtn" title={order === "asc" ? m.sortStartAsc : m.sortStartDesc} onClick={() => onOrderChange(order === "asc" ? "desc" : "asc")}>
                    {c.header} {order === "asc" ? "↑" : "↓"}
                  </button>
                ) : (
                  c.header
                )}
              </div>
            ))}
          </div>
          <div ref={scrollRef} className="ac-lv-scroll" style={{ height }}>
            <div style={{ height: virt.getTotalSize(), position: "relative" }}>
              {virt.getVirtualItems().map((v) => {
                const s = sessions[v.index];
                if (!s) return null;
                return (
                  <div
                    key={s.session}
                    id={`lv-ses-${s.session}`}
                    role="row"
                    aria-rowindex={v.index + 2}
                    aria-selected={s.session === selectedId}
                    data-selected={s.session === selectedId || undefined}
                    data-active={s.session === sessions[activeIdx]?.session || undefined}
                    className="ac-lv-row"
                    style={{ gridTemplateColumns: template, height: 32, transform: `translateY(${v.start}px)` }}
                    onClick={() => { setActive(s.session); onOpen(s.session); }}
                    onContextMenu={(e) => { if (!onRowMenu) return; e.preventDefault(); onRowMenu(s.session, { x: e.clientX, y: e.clientY, element: e.currentTarget }); }}
                  >
                    {columns.map((c) => (
                      <div key={c.id} role="gridcell" data-align={c.align ?? "start"} className="ac-lv-cell">
                        {c.render ? c.render(s) : cell(c.id, s)}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
          {limitReached ? <p className="ac-lv-muted">{fmt(m.sessionLimit, { n: limit ?? sessions.length })}</p> : null}
        </div>
      )}
      {state && sessions.length > 0 ? state : null}
    </div>
  );
}
