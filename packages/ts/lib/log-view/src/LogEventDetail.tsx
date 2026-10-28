import { useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import type { LogEvent, LogEventDetail as LogEventDetailData } from "@agent-console/contracts/logs";
import { fullTimeTitle, mergeFormatters, shortPath } from "./format";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { CategoryChip, ErrorBlock, ErrorIcon, NeutralChip, Skeleton } from "./parts";
import { colorFor } from "./taxonomy";
import type { Formatters, LogTaxonomyView, SlotFor } from "./types";
import { useVirtualRows } from "./virtual";

export type DetailTab = "overview" | "detail" | "raw" | "evidence" | "related";
const ALL_TABS: readonly DetailTab[] = ["overview", "detail", "raw", "evidence", "related"];

/** 상세의 명령형 API(`ref`로 받는다). 앱이 탭 DOM을 클릭하지 않고 탭을 바꾸고 포커스를 옮긴다. */
export interface LogEventDetailHandle {
  /** 보이는 탭 중 `index`번째(0부터)로 바꾸고 그 탭 버튼에 포커스한다. @returns 그 위치에 탭이 없으면 false */
  selectTabAt(index: number): boolean;
  /** 현재(활성) 탭 버튼에 포커스한다. 탭 줄이 아직 없으면(로딩·오류) false */
  focusTab(): boolean;
  /** 지금 보이는 탭 id(순서대로) */
  visibleTabs(): readonly DetailTab[];
}

export interface LogEventDetailProps {
  ref?: Ref<LogEventDetailHandle>;
  /** 활성 탭을 밖에서 정한다(제어형). 없으면 내부 상태이고 처음은 첫 탭. 보이지 않는 탭 id면 첫 탭. */
  activeTab?: DetailTab;
  onActiveTabChange?: (tab: DetailTab) => void;
  /** 계약 `LogEventDetail`(`GET /logs/events/{uid}`). 로딩 중에는 없어도 된다. */
  detail?: LogEventDetailData | undefined;
  /** 목록 행에서 이미 아는 이벤트(상세 로딩 중 개요를 먼저 그린다). */
  preview?: LogEvent | undefined;
  loading?: boolean;
  error?: { message: string; detail?: string } | null;
  onRetry?: () => void;
  /** 보일 탭과 순서(기본 5개 전부). 내용이 없는 탭은 [개요]를 빼고 자동으로 숨긴다. */
  tabs?: readonly DetailTab[];
  onOpenEvent?: (uid: string, session?: string) => void;
  onClose?: () => void;
  onCopyUid?: (uid: string) => void;
  /** JSON 보기 슬롯(앱이 읽기 전용 CodeBlock/TextEditor를 주입). 없으면 기본 `<pre>`. */
  renderCodeBlock?: (value: unknown, opts: { language: string }) => ReactNode;
  /** 링크 슬롯: 연동 대상(실행·세션 화면)이 있을 때만 링크로 바꾼다. undefined면 텍스트. */
  renderLinks?: (kind: "run" | "session", id: string) => ReactNode | undefined;
  taxonomy: LogTaxonomyView;
  slotFor: SlotFor;
  isError: (event: LogEvent) => boolean;
  originTime?: number | null | undefined;
  laneLabelFor?: (thread: string) => string | undefined;
  formatters?: Partial<Formatters>;
  messages?: DeepPartial<LogViewMessages>;
  height?: number;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="ac-lv-kv">
      <dt className="ac-lv-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const nonEmpty = (v: unknown): boolean => v != null && v !== "" && !(Array.isArray(v) && v.length === 0);

/**
 * 이벤트 상세(개요·상세 JSON·원문 JSON·근거·관련). 필드 이름(계약)으로 그릴 뿐 범주·출처 값으로 분기하지 않는다.
 * "가려진 사본" 안내와 잘림 경고는 내부, JSON 보기·링크는 슬롯으로 받는다.
 */
export function LogEventDetail({ ref, ...props }: LogEventDetailProps) {
  const { detail, preview, loading, error, onRetry, onOpenEvent, onClose, onCopyUid, renderCodeBlock, renderLinks, taxonomy, slotFor, isError, originTime, laneLabelFor, height = 240, messages, activeTab, onActiveTabChange, tabs, formatters: formatterOverrides } = props;
  const m = useMemo(() => mergeMessages(messages), [messages]);
  const formatters = useMemo(() => mergeFormatters(formatterOverrides), [formatterOverrides]);
  const event = detail?.event ?? preview;
  const [inner, setInner] = useState<DetailTab>("overview");
  const active = activeTab ?? inner;
  const setActive = (tab: DetailTab) => {
    setInner(tab);
    onActiveTabChange?.(tab);
  };
  const tabsRef = useRef<HTMLDivElement>(null);

  const counts = {
    evidence: detail?.evidence_links?.length ?? 0,
    related: detail?.related?.length ?? 0,
  };
  const available = useMemo(
    () =>
      (tabs ?? ALL_TABS).filter((t) => {
        if (t === "overview" || t === "detail") return true;
        if (t === "raw") return event?.raw != null;
        return counts[t] > 0;
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tabs, event?.raw, counts.evidence, counts.related],
  );
  const current = available.includes(active) ? active : (available[0] ?? "overview");

  useImperativeHandle(
    ref,
    () => ({
      selectTabAt(index) {
        const tab = available[index];
        if (tab === undefined) return false;
        setActive(tab);
        tabsRef.current?.querySelector<HTMLElement>(`[data-tab="${tab}"]`)?.focus();
        return true;
      },
      focusTab() {
        const el = tabsRef.current?.querySelector<HTMLElement>(`[data-tab="${current}"]`);
        el?.focus();
        return el != null;
      },
      visibleTabs: () => available,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [available, current],
  );

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = available.indexOf(current);
    let to: number | undefined;
    if (e.key === "ArrowRight") to = (i + 1) % available.length;
    else if (e.key === "ArrowLeft") to = (i - 1 + available.length) % available.length;
    else if (e.key === "Home") to = 0;
    else if (e.key === "End") to = available.length - 1;
    if (to === undefined) return;
    e.preventDefault();
    const next = available[to] as DetailTab;
    setActive(next);
    tabsRef.current?.querySelector<HTMLElement>(`[data-tab="${next}"]`)?.focus();
  };

  const code = (value: unknown) => (renderCodeBlock ? renderCodeBlock(value, { language: "json" }) : <pre className="ac-lv-mono-wrap ac-lv-code">{JSON.stringify(value, null, 2)}</pre>);

  if (!event && error) return <ErrorBlock error={error} onRetry={onRetry} m={m} />;
  if (!event) return loading ? <Skeleton label={m.loading} rows={5} /> : <p className="ac-lv-empty">{m.detailEmpty}</p>;

  const err = isError(event);
  const lane = event.thread ?? event.actor;
  const timeLine = [
    event.time != null ? formatters.dateTime(event.time) : null,
    event.time != null && originTime != null ? `(${formatters.relativeTime((event.time - originTime) * 1000)})` : null,
    event.duration_ms != null ? fmt("· {d}", { d: formatters.duration(event.duration_ms) }) : null,
    lane ? `· ${laneLabelFor?.(lane) ?? lane}` : null,
  ].filter(Boolean);
  const link = (kind: "run" | "session", id: string) => renderLinks?.(kind, id) ?? <span className="ac-lv-mono">{id}</span>;
  const usage = detail?.usage;
  const tokenParts = usage
    ? [usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens, usage.cache_creation_input_tokens].map((n) => (n == null ? m.none : formatters.number(n)))
    : null;

  const overview: [string, ReactNode][] = (
    [
      ["source", <NeutralChip key="s">{event.source}</NeutralChip>, nonEmpty(event.source)],
      ["ref", <span key="r" className="ac-lv-mono">{event.ref}</span>, nonEmpty(event.ref)],
      ["lane", lane ? (laneLabelFor?.(lane) ?? lane) : null, nonEmpty(lane)],
      ["route", `${(event.from ?? []).join(", ") || m.none} → ${(event.to ?? []).join(", ") || m.none}${event.via ? ` (via ${event.via})` : ""}`, nonEmpty(event.from) || nonEmpty(event.to)],
      ["tool", <span key="t" className="ac-lv-mono">{event.tool}</span>, nonEmpty(event.tool)],
      ["call_id", <span key="c" className="ac-lv-mono">{event.call_id}</span>, nonEmpty(event.call_id)],
      ["turn_id", <span key="tu" className="ac-lv-mono">{event.turn_id}</span>, nonEmpty(event.turn_id)],
      ["message_id", <span key="mi" className="ac-lv-mono">{event.message_id}</span>, nonEmpty(event.message_id)],
      ["session", event.session ? link("session", event.session) : null, nonEmpty(event.session)],
      ["cwd", event.cwd ? <span key="cw" title={event.cwd}>{shortPath(event.cwd)}</span> : null, nonEmpty(event.cwd)],
      ["model", event.model, nonEmpty(event.model)],
      ["run_id", event.run_id ? link("run", event.run_id) : null, nonEmpty(event.run_id)],
      ["node_path", (event.node_path ?? []).join(" / "), nonEmpty(event.node_path)],
      ["stage", event.stage ? (m.values[`stage.${event.stage}`] ?? event.stage) : null, nonEmpty(event.stage)],
      ["status", event.status ? (m.values[`status.${event.status}`] ?? event.status) : null, nonEmpty(event.status)],
      ["evidence", event.evidence ? <NeutralChip key="e">{event.evidence}</NeutralChip> : null, nonEmpty(event.evidence)],
      ["tags", <span key="tg" className="ac-lv-chiprow">{(event.tags ?? []).map((t) => <NeutralChip key={t}>{taxonomy.get(t).name}</NeutralChip>)}</span>, nonEmpty(event.tags)],
      [
        "usage",
        tokenParts ? (
          <span key="u">
            {fmt(m.tokenTip, { input: tokenParts[0], output: tokenParts[1], read: tokenParts[2], creation: tokenParts[3] })} <span className="ac-lv-muted">{m.usageNote}</span>
          </span>
        ) : null,
        usage != null,
      ],
      ["observed_at", <span key="o" title={fullTimeTitle(event.observed_at)}>{formatters.absoluteTime(event.observed_at)}</span>, event.observed_at != null],
      [
        "documents",
        <ul key="d" className="ac-lv-plain">
          {(event.documents ?? []).map((d, i) => (
            <li key={i}>
              {d.kind ? <NeutralChip>{d.kind}</NeutralChip> : null} <span className="ac-lv-mono">{d.path}</span>
              {d.action ? <span className="ac-lv-muted"> {d.action}</span> : null}
            </li>
          ))}
        </ul>,
        nonEmpty(event.documents),
      ],
    ] as [string, ReactNode, boolean][]
  )
    .filter(([, , show]) => show)
    .map(([id, node]) => [m.overview[id] ?? id, node]);

  const tabLabel = (t: DetailTab) => `${m.detailTabs[t] ?? t}${t === "evidence" && counts.evidence ? ` (${counts.evidence})` : ""}${t === "related" && counts.related ? ` (${counts.related})` : ""}`;

  return (
    <section className="ac-lv-detail" aria-label={m.detailTitle} data-error={err || undefined}>
      <header className="ac-lv-detailhead">
        <div className="ac-lv-detailtitle">
          <CategoryChip name={taxonomy.get(event.category).name} color={colorFor(event.category, taxonomy, slotFor)} title={event.category} />
          <strong className="ac-lv-ellipsis" title={event.title}>{event.title}</strong>
          {err ? (
            <span className="ac-lv-chip" data-tone="danger">
              <ErrorIcon />
              {m.errorBadge}
            </span>
          ) : null}
        </div>
        <div className="ac-lv-row-actions">
          {onCopyUid ? (
            <button type="button" className="ac-lv-iconbtn" aria-label={`${m.copy} uid`} title={event.uid} onClick={() => onCopyUid(event.uid)}>
              ⧉
            </button>
          ) : null}
          {onClose ? (
            <button type="button" className="ac-lv-iconbtn" aria-label={m.close} onClick={onClose}>
              ✕
            </button>
          ) : null}
        </div>
      </header>
      <p className="ac-lv-muted">{timeLine.join(" ")}</p>
      <div ref={tabsRef} role="tablist" aria-label={m.detailTitle} className="ac-lv-tabs" onKeyDown={onTabKey}>
        {available.map((t) => (
          <button key={t} type="button" role="tab" data-tab={t} id={`lv-tab-${t}`} aria-selected={current === t} aria-controls={`lv-panel-${t}`} tabIndex={current === t ? 0 : -1} onClick={() => setActive(t)}>
            {tabLabel(t)}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`lv-panel-${current}`} aria-labelledby={`lv-tab-${current}`} className="ac-lv-tabpanel">
        {error ? <ErrorBlock error={error} onRetry={onRetry} m={m} /> : null}
        {current === "overview" ? (
          loading && !detail ? (
            <Skeleton label={m.loading} rows={4} />
          ) : (
            <dl className="ac-lv-kvlist">
              {overview.map(([label, node]) => (
                <Row key={label} label={label}>
                  {node}
                </Row>
              ))}
            </dl>
          )
        ) : null}
        {current === "detail" || current === "raw" ? (
          <>
            {detail?.detail_truncated ? <p className="ac-lv-warn" role="status">{m.detailTruncated}</p> : null}
            {current === "raw" ? <p className="ac-lv-info">{m.redactedNotice}</p> : null}
            {current === "detail" && event.detail == null ? <p className="ac-lv-muted">{m.noDetail}</p> : code(current === "detail" ? event.detail : event.raw)}
          </>
        ) : null}
        {current === "evidence" ? (
          <>
            <p className="ac-lv-muted">{m.evidenceNotice}</p>
            <ul className="ac-lv-plain">
              {(detail?.evidence_links ?? []).map((l, i) => (
                <li key={`${l.uid}-${i}`}>
                  <button type="button" className="ac-lv-linkrow" onClick={() => onOpenEvent?.(l.uid)}>
                    <NeutralChip>{l.basis}</NeutralChip> <span className="ac-lv-mono ac-lv-ellipsis">{l.value}</span>
                    {l.title ? <span className="ac-lv-muted ac-lv-ellipsis"> {l.title}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {current === "related" ? (
          <>
            {detail?.truncated ? <p className="ac-lv-warn" role="status">{m.relatedTruncated}</p> : null}
            <RelatedList events={detail?.related ?? []} taxonomy={taxonomy} slotFor={slotFor} formatters={formatters} originTime={originTime} onOpen={(e) => onOpenEvent?.(e.uid, e.session)} height={height} m={m} />
          </>
        ) : null}
      </div>
    </section>
  );
}

function RelatedList({ events, taxonomy, slotFor, formatters, originTime, onOpen, height, m }: { events: readonly LogEvent[]; taxonomy: LogTaxonomyView; slotFor: SlotFor; formatters: Formatters; originTime: number | null | undefined; onOpen: (e: LogEvent) => void; height: number; m: LogViewMessages }) {
  const ref = useRef<HTMLDivElement>(null);
  const virt = useVirtualRows({ count: events.length, rowHeight: 32, scrollRef: ref, fallbackHeight: height });
  return (
    <div ref={ref} className="ac-lv-scroll" style={{ height }} role="list" aria-label={m.detailTabs["related"] ?? "related"}>
      <div style={{ height: virt.getTotalSize(), position: "relative" }}>
        {virt.getVirtualItems().map((v) => {
          const e = events[v.index];
          if (!e) return null;
          return (
            <button key={e.uid} type="button" role="listitem" className="ac-lv-relrow" style={{ transform: `translateY(${v.start}px)` }} onClick={() => onOpen(e)}>
              <span className="ac-lv-num">{e.time == null ? m.none : originTime != null ? formatters.relativeTime((e.time - originTime) * 1000) : formatters.absoluteTime(e.time)}</span>
              <CategoryChip name={taxonomy.get(e.category).name} color={colorFor(e.category, taxonomy, slotFor)} title={e.category} />
              <span className="ac-lv-ellipsis" title={e.title}>{e.title}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
