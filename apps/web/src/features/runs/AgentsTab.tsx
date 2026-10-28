import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { RunEvent } from "@agent-console/contracts";
import { Button, Tag } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { messages as appMessages } from "../../app/messages";
import { formatCount } from "../../lib/format";
import { runsMessages as t } from "./messages";
import { EVENT_PAGE_SIZE, TEXT_DELTA_EVENT } from "./runsConfig";
import { buildEventRows, collectPrefixes, isErrorEvent, summarizeActors, summarizeEvent, truncate, type EventRow } from "./runsLib";

export interface AgentsTabProps {
  events: readonly RunEvent[];
  status: "loading" | "ready" | "error";
  onRetry(): void;
  /** 선택한 actor들(빈 배열 = 전체) */
  actors: readonly string[];
  onActorsChange(next: string[]): void;
  agentName(id: string): string;
  /** 이 actor가 서브에이전트(위임으로 불린 쪽)인가 — 칩·들여쓰기용 */
  isSubagent(actor: string): boolean;
  /** actor 하나의 마지막 상태(StatusChip용). 없으면 아이콘 생략 */
  statusOf?(actor: string): string | undefined;
  /** 실행 시작 시각(epoch 초) — 상대 시각 계산용 */
  startedAt: number | undefined;
  running: boolean;
  /** 이벤트 한 줄 요약을 앱이 대신 정한다(반복·자식 실행 이벤트). 문구가 없으면 기본 요약 */
  summaryOf?(event: RunEvent): string | undefined;
  /** actor 이름 뒤에 붙는 덧말(`(← 위임자 위임)`). 없으면 생략 */
  actorNote?(actor: string): string | undefined;
  /** 이벤트 type 접두 필터 값을 밖(주소)이 정한다. 생략하면 이 탭이 상태를 가진다 */
  typePrefix?: string;
  onTypePrefixChange?(next: string): void;
  /** 이벤트 목록 위의 안내(활성 자식 실행의 이벤트는 각 실행 화면에서 본다) */
  topNote?: ReactNode;
}

/** actor가 없는 이벤트(실행 전체에 관한 반복·자식 실행 이벤트)를 가리키는 필터 값. 에이전트 id가 아니라 이 화면이 정한 값이다. */
export const RUN_WIDE_ACTOR = "@run";

function relTime(ts: number, start: number | undefined): string {
  const d = ts - (start ?? ts);
  return `${d >= 0 ? "+" : "-"}${Math.abs(d).toFixed(1)}s`;
}

/** 탭 ② 에이전트: 왼쪽 actor 목록, 오른쪽 이벤트 목록(필터·합친 텍스트 행·JSON 펼침). 데이터는 props. */
export function AgentsTab(p: AgentsTabProps) {
  const [localPrefix, setLocalPrefix] = useState("");
  const prefix = p.typePrefix ?? localPrefix;
  const setPrefix = (next: string) => {
    setLocalPrefix(next);
    p.onTypePrefixChange?.(next);
  };
  const [text, setText] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [follow, setFollow] = useState(p.running);
  const [limit, setLimit] = useState(EVENT_PAGE_SIZE);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [seenLength, setSeenLength] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);

  const summaryOf = p.summaryOf;
  const actors = useMemo(() => summarizeActors(p.events), [p.events]);
  const runWide = useMemo(() => p.events.filter((e) => !e.actor && summaryOf?.(e) !== undefined).length, [p.events, summaryOf]);
  const prefixes = useMemo(() => collectPrefixes(p.events), [p.events]);
  const filtered = useMemo(() => {
    const q = text.trim().toLowerCase();
    return p.events.filter((e) => {
      if (p.actors.length > 0 && !p.actors.includes(e.actor ?? RUN_WIDE_ACTOR)) return false;
      if (prefix !== "" && !e.type.startsWith(prefix)) return false;
      if (errorsOnly && !isErrorEvent(e)) return false;
      return q === "" || `${e.type} ${summaryOf?.(e) ?? summarizeEvent(e, 400)}`.toLowerCase().includes(q);
    });
  }, [p.events, p.actors, prefix, errorsOnly, text, summaryOf]);
  const rows = useMemo(() => buildEventRows(filtered), [filtered]);
  const shown = rows.length > limit ? rows.slice(rows.length - limit) : rows;
  const hasFilter = p.actors.length > 0 || prefix !== "" || errorsOnly || text !== "";

  useEffect(() => {
    const el = scroller.current;
    if (el !== null && follow) el.scrollTop = el.scrollHeight;
  }, [rows.length, follow]);
  const newBelow = p.running && !follow && rows.length > seenLength;
  const setFollowing = (next: boolean) => {
    setFollow(next);
    if (!next) setSeenLength(rows.length);
  };

  if (p.status === "loading" && p.events.length === 0) return <div className="app-loading" role="status">{t.agents.loading}</div>;
  if (p.status === "error" && p.events.length === 0) return <ErrorBlock title={t.agents.loadFailed} retryLabel={appMessages.common.retry} onRetry={p.onRetry} />;

  const toggleActor = (actor: string | null, additive: boolean) => {
    if (actor === null) return p.onActorsChange([]);
    if (additive) return p.onActorsChange(p.actors.includes(actor) ? p.actors.filter((a) => a !== actor) : [...p.actors, actor]);
    p.onActorsChange(p.actors.length === 1 && p.actors[0] === actor ? [] : [actor]);
  };
  const clear = () => {
    p.onActorsChange([]);
    setPrefix("");
    setText("");
    setErrorsOnly(false);
  };
  const onScroll = () => {
    const el = scroller.current;
    if (el === null) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom) setFollowing(true);
    else if (follow) setFollowing(false);
  };
  const toggle = (key: string) => setOpen((cur) => (cur.has(key) ? new Set([...cur].filter((k) => k !== key)) : new Set(cur).add(key)));

  return (
    <div className="runs-agents">
      <nav className="runs-actors" aria-label={t.agents.listLabel}>
        <ul role="listbox" aria-multiselectable="true" aria-label={t.agents.listLabel}>
          <li role="option" aria-selected={p.actors.length === 0}>
            <button type="button" onClick={() => toggleActor(null, false)}>
              {t.agents.all} <span className="ac-num app-muted">({formatCount(p.events.length)})</span>
            </button>
          </li>
          {runWide > 0 ? (
            <li role="option" aria-selected={p.actors.includes(RUN_WIDE_ACTOR)}>
              <button type="button" onClick={(e) => toggleActor(RUN_WIDE_ACTOR, e.ctrlKey || e.metaKey)}>
                {t.agents.runWide} <span className="ac-num app-muted">({formatCount(runWide)})</span>
              </button>
            </li>
          ) : null}
          {actors.map((a) => {
            const sub = p.isSubagent(a.actor);
            return (
              <li key={a.actor} role="option" aria-selected={p.actors.includes(a.actor)} className={sub ? "runs-actor-sub" : undefined}>
                <button type="button" onClick={(e) => toggleActor(a.actor, e.ctrlKey || e.metaKey)}>
                  <span className="ac-ellipsis">{p.agentName(a.actor)}{p.actorNote?.(a.actor) ? ` ${p.actorNote(a.actor)}` : ""}</span> <span className="ac-num app-muted">({formatCount(a.count)})</span>
                </button>
                {sub ? <Tag title={t.agents.totalOnlyTitle}>{t.agents.subagentChip}</Tag> : null}
                {sub ? <Tag title={t.agents.totalOnlyTitle}>{t.agents.totalOnlyChip}</Tag> : null}
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="runs-events">
        <div className="runs-events-tools">
          <label className="runs-filter">
            <span className="app-muted">{t.agents.typeFilter}</span>
            <select value={prefix} onChange={(e) => setPrefix(e.target.value)}>
              <option value="">{t.agents.anyPrefix}</option>
              {prefix !== "" && !prefixes.includes(prefix) ? <option value={prefix}>{prefix}</option> : null}
              {prefixes.map((x) => (
                <option key={x} value={x}>{x}</option>
              ))}
            </select>
          </label>
          <label className="runs-filter">
            <span className="app-muted">{t.agents.textFilter}</span>
            <input type="search" value={text} placeholder={t.agents.textPlaceholder} onChange={(e) => setText(e.target.value)} />
          </label>
          <label className="app-check"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />{t.agents.errorsOnly}</label>
          {p.running ? <label className="app-check"><input type="checkbox" checked={follow} onChange={(e) => setFollowing(e.target.checked)} />{t.agents.follow}</label> : null}
        </div>
        {p.topNote}
        <p className="app-muted runs-note">{t.agents.subagentTextNote}</p>
        {rows.length === 0 ? (
          <div className="app-empty">
            <p>{hasFilter ? t.agents.noMatch : t.agents.empty}</p>
            {hasFilter ? <Button onClick={clear}>{t.agents.clear}</Button> : null}
          </div>
        ) : (
          <div ref={scroller} className="runs-events-scroll" onScroll={onScroll} role="list" aria-label={t.agents.eventsLabel}>
            {rows.length > shown.length ? <Button size="sm" onClick={() => setLimit((n) => n + EVENT_PAGE_SIZE)}>{t.agents.more(rows.length - shown.length)}</Button> : null}
            {shown.map((row) => (
              <EventRowView key={row.key} row={row} start={p.startedAt} agentName={p.agentName} summaryOf={p.summaryOf} open={open.has(row.key)} onToggle={() => toggle(row.key)} />
            ))}
          </div>
        )}
        {newBelow ? (
          <Button
            className="runs-new-events"
            size="sm"
            variant="primary"
            onClick={() => setFollowing(true)}
          >
            ↓ {t.agents.newEvents}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function EventRowView({ row, start, agentName, summaryOf, open, onToggle }: { row: EventRow; start: number | undefined; agentName(id: string): string; summaryOf: ((event: RunEvent) => string | undefined) | undefined; open: boolean; onToggle(): void }) {
  const e = row.event;
  const isText = e.type === TEXT_DELTA_EVENT;
  const summary = isText ? t.agents.textRow((row.text ?? "").length) : (summaryOf?.(e) ?? summarizeEvent(e));
  return (
    <div role="listitem" className="runs-event" data-error={isErrorEvent(e) ? "true" : undefined}>
      <button type="button" className="runs-event-line" aria-expanded={open} aria-label={`${e.type} ${truncate(summary, 80)}`} onClick={onToggle}>
        <span className="ac-num app-muted">{relTime(e.ts, start)}</span>
        <Tag>{e.actor ? agentName(e.actor) : t.agents.system}</Tag>
        <code className="app-mono ac-ellipsis">{e.type}</code>
        <span className="ac-ellipsis">{summary}</span>
      </button>
      {open ? <pre className="ac-pre runs-event-json app-wrap">{isText ? (row.text ?? "") : JSON.stringify({ seq: e.seq, node_path: e.node_path, payload: e.payload }, null, 2)}</pre> : null}
    </div>
  );
}
