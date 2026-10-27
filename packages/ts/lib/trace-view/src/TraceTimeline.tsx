import { useEffect, useId, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import type { Trace, TraceLink, TraceSpan } from "@agent-console/contracts";
import { compactCount, computeTimeScale, defaultExpandedGroups, flattenRows, formatDuration, formatTailDuration, isCallSpan, isSameSession, isUserWait, niceTicks, spanOrdinals, visibleHandoffs, type TraceGroupInfo, type TraceRow } from "./layout";
import { defaultTraceMessages, type TraceMessages } from "./messages";

export interface SpanLabel {
  title: string;
  sub?: string;
}

export interface MethodBadge {
  /** 방식 아이콘 이름(연결 종류 디스크립터의 `ui_hints.icon`). 없으면 기본 연결 아이콘. 그리는 일은 `renderIcon`이 한다. */
  iconName?: string;
  /** 방식 문구(연결 종류·위임 방식 `title`을 앱이 그대로 전달). */
  text: string;
  /** 세션 문구. 없으면 span 필드로 판정해 messages의 같은/별도 세션을 쓴다. */
  sessionText?: string;
}

/** 자식 Run 묶음 행의 제목·배지(앱이 팀 구성 이름 등을 채운다). */
export interface GroupBadge {
  title: string;
  sub?: string;
  /** 묶음 행에 붙는 배지 문구(예: 상태가 아닌 종류 표시). */
  badge?: string;
}

/** span 사이 화살표 칩. 앱이 연결 종류 디스크립터에서 채운다(예: 반복 연결 아이콘과 순번). */
export interface LinkBadge {
  text: string;
  /** 칩 앞에 붙는 짧은 글리프(아이콘 이름이 아니라 그릴 글자). */
  iconName?: string;
  dashed?: boolean;
}

export interface TraceTimelineProps {
  trace: Trace;
  /** 현재 시각(epoch 초, 주입). 실행 중 막대 길이 계산용. */
  now?: number;
  running?: boolean;
  selectedSpanId?: string | null;
  onSelect?: (spanId: string | null) => void;
  /** 그래프 선택과 연동: 이 노드의 행을 강조한다. */
  highlightNodeId?: string | null;
  /** 노드 label·에이전트 이름·역할 해석(앱). 없으면 node_id · actor를 그대로 보인다. */
  labelFor?: (span: TraceSpan) => SpanLabel;
  /** 방식 배지 문구(앱). 없으면 세션 배지만 보인다. */
  methodBadgeFor?: (span: TraceSpan) => MethodBadge | undefined;
  /** 자식 Run 묶음 행의 제목·배지(앱). 없으면 `자식 실행 {짧은 id}`. */
  groupBadgeFor?: (group: TraceGroupInfo) => GroupBadge | undefined;
  /** span 사이 화살표 칩(앱). 없으면 칩 없음. */
  linkBadgeFor?: (link: TraceLink) => LinkBadge | undefined;
  /** 펼친 자식 Run 묶음 id(= 자식 Run id) 목록. 주면 제어형(기본값 계산은 앱). 생략하면 화면이 `실행 중이면 펼침, 끝났으면 접힘`으로 시작하고 사용자의 선택을 유지한다. */
  expandedGroupIds?: readonly string[];
  onGroupToggle?: (groupId: string, expanded: boolean) => void;
  /** 묶음 행 `Ctrl+Enter`·[열기] */
  onOpenChildRun?: (runId: string) => void;
  showUserWait?: boolean;
  onShowUserWaitChange?: (v: boolean) => void;
  timeScale?: number;
  onTimeScaleChange?: (v: number) => void;
  follow?: boolean;
  onFollowChange?: (v: boolean) => void;
  /** 선택한 span의 상세(앱이 링크 포함해 채움). 있으면 아래 드로어로 보인다. */
  renderDetail?: (span: TraceSpan) => ReactNode;
  /** 위임 방식 문구를 아이콘 옆에 글자로도 보인다(기본 끔, 앱이 로컬 저장). */
  showMethodText?: boolean;
  onShowMethodTextChange?: (v: boolean) => void;
  /** 라벨 칸 폭(px) 조절값. 없으면 컨테이너 폭에 맞춰 240~320. 있으면 200~360으로 자른다. */
  labelWidth?: number;
  /** 아이콘 그리기(앱이 아이콘 레지스트리로 주입). 기본값은 글리프 문자. `size`는 px. */
  renderIcon?: (name: string, size: number) => ReactNode;
  /** 아이콘의 짧은 설명. 기본값은 `title` 속성. 라벨 칸이 넘침을 자르므로 주입하는 툴팁은 칸 밖으로 나가지 않아야 한다. */
  renderTooltip?: (content: string, children: ReactNode) => ReactNode;
  messages?: Partial<TraceMessages>;
}

/** 기본 글리프 표. 이름이 없거나 모르면 `link`(↪). */
const DEFAULT_GLYPHS: Readonly<Record<string, string>> = { "external-link": "↗", link: "↪" };
const defaultRenderIcon = (name: string): ReactNode => <span aria-hidden="true">{DEFAULT_GLYPHS[name] ?? DEFAULT_GLYPHS["link"]}</span>;
const defaultRenderTooltip = (content: string, children: ReactNode): ReactNode => <span title={content}>{children}</span>;
const MAX_INDENT_STEPS = 3;
const LINK_MIN_ROOM = 56;

const MIN_ZOOM = 1;
const MAX_ZOOM = 16;

function barStatus(span: TraceSpan): string {
  return span.status ?? "unknown";
}

/**
 * 위임 흐름 타임라인: 왼쪽 트리(이름·방식·세션 배지) + 오른쪽 시간 막대.
 * 서브에이전트(`parent_id`가 있는 span)는 들여 쓴 자식 행 + 같은 세션, 독립은 최상위 행 + 별도 세션 + 넘기기 화살표.
 * 종류 id 문자열을 비교하지 않는다. 판정은 span 필드(`parent_id`, `session_id`, `interaction_id`, `order`)와 `trace.links`로 한다.
 */
export function TraceTimeline(props: TraceTimelineProps) {
  const { trace, now, running = false, selectedSpanId, onSelect, highlightNodeId, labelFor, methodBadgeFor, linkBadgeFor, showUserWait = true, timeScale = 1, follow = false } = props;
  const m = { ...defaultTraceMessages, ...props.messages };
  const spans = useMemo(() => trace.spans ?? [], [trace.spans]);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [groupChoice, setGroupChoice] = useState<ReadonlyMap<string, boolean>>(new Map());
  const expandedGroups = useMemo<ReadonlySet<string>>(() => {
    if (props.expandedGroupIds) return new Set(props.expandedGroupIds);
    const base = defaultExpandedGroups(spans, trace.run_id);
    for (const [id, open] of groupChoice) {
      if (open) base.add(id);
      else base.delete(id);
    }
    return base;
  }, [props.expandedGroupIds, spans, trace.run_id, groupChoice]);
  const rows = useMemo(() => flattenRows(spans, { collapsed, showUserWait, runId: trace.run_id, expandedGroups }), [spans, collapsed, showUserWait, trace.run_id, expandedGroups]);
  const ordinals = useMemo(() => spanOrdinals(spans), [spans]);
  const scale = useMemo(() => computeTimeScale(spans, { now, running, showUserWait }), [spans, now, running, showUserWait]);
  const handoffs = useMemo(() => visibleHandoffs(trace, rows), [trace, rows]);
  const byId = useMemo(() => new Map(spans.map((s) => [s.id, s])), [spans]);
  const [focusIdx, setFocusIdx] = useState(0);
  const rowEls = useRef<(HTMLDivElement | null)[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const markerId = useId();
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, timeScale));
  const laneRef = useRef<HTMLDivElement>(null);
  const [laneW, setLaneW] = useState(0);
  const hasSpans = spans.length > 0;

  useEffect(() => {
    const el = laneRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setLaneW(el.clientWidth));
    ro.observe(el);
    setLaneW(el.clientWidth);
    return () => ro.disconnect();
  }, [hasSpans]);

  useEffect(() => {
    if (follow && running && scroller.current) scroller.current.scrollLeft = scroller.current.scrollWidth;
  }, [follow, running, now, zoom, spans]);

  if (spans.length === 0) {
    return (
      <div role="status" style={{ color: "var(--ac-text-muted)", padding: "var(--ac-space-4)" }}>
        {m.empty}
      </div>
    );
  }

  const labelOf = (span: TraceSpan): SpanLabel => labelFor?.(span) ?? { title: span.node_id ?? span.id, sub: span.actor ?? undefined };
  const endOf = (span: TraceSpan): number | undefined => (span.ended_at ?? (running && now != null && span.started_at != null ? Math.max(now, span.started_at) : span.started_at ?? undefined));
  const durationOf = (span: TraceSpan): number | undefined => (span.started_at != null && endOf(span) != null ? (endOf(span) as number) - span.started_at : undefined);

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleGroup = (runId: string, open: boolean) => {
    if (!props.expandedGroupIds) setGroupChoice((prev) => new Map(prev).set(runId, open));
    props.onGroupToggle?.(runId, open);
  };

  const focusRow = (i: number) => {
    const clamped = Math.max(0, Math.min(rows.length - 1, i));
    setFocusIdx(clamped);
    rowEls.current[clamped]?.focus();
  };
  const zoomBy = (factor: number) => props.onTimeScaleChange?.(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom * factor)));

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>, i: number, row: TraceRow) => {
    if (row.group && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) props.onOpenChildRun?.(row.group.runId);
      else toggleGroup(row.group.runId, !row.expanded);
      return;
    }
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        focusRow(i + 1);
        break;
      case "ArrowUp":
        e.preventDefault();
        focusRow(i - 1);
        break;
      case "ArrowRight":
        e.preventDefault();
        if (row.group && !row.expanded) toggleGroup(row.group.runId, true);
        else if (row.hasChildren && collapsed.has(row.span.id)) toggle(row.span.id);
        else if (row.hasChildren) focusRow(i + 1);
        break;
      case "ArrowLeft":
        e.preventDefault();
        if (row.group && row.expanded) toggleGroup(row.group.runId, false);
        else if (row.hasChildren && !row.group && !collapsed.has(row.span.id)) toggle(row.span.id);
        else if (row.parentId) focusRow(rows.findIndex((r) => r.span.id === row.parentId));
        break;
      case "Home":
        e.preventDefault();
        focusRow(0);
        break;
      case "End":
        e.preventDefault();
        focusRow(rows.length - 1);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        onSelect?.(row.span.id);
        break;
      case "Escape":
        if (selectedSpanId) onSelect?.(null);
        break;
      case "+":
      case "=":
        zoomBy(1.5);
        break;
      case "-":
        zoomBy(1 / 1.5);
        break;
      default:
    }
  };

  const ticks = niceTicks(scale.total);
  const selected = selectedSpanId ? byId.get(selectedSpanId) : undefined;
  const renderIcon = props.renderIcon ?? defaultRenderIcon;
  const renderTooltip = props.renderTooltip ?? defaultRenderTooltip;
  const showMethodText = props.showMethodText ?? false;
  const treeStyle: CSSProperties & Record<string, string | number> = { minWidth: `${zoom * 100}%` };
  if (props.labelWidth != null) treeStyle["--trace-label-col"] = `clamp(200px, ${props.labelWidth}px, 360px)`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-2)", minWidth: 0 }}>
      <div style={{ display: "flex", gap: "var(--ac-space-3)", alignItems: "center", flexWrap: "wrap", color: "var(--ac-text-muted)", fontSize: "var(--ac-text-xs, 12px)" }}>
        {props.onShowUserWaitChange ? (
          <label className="ac-trace-opt">
            <input type="checkbox" checked={showUserWait} onChange={(e) => props.onShowUserWaitChange?.(e.target.checked)} /> {m.showUserWait}
          </label>
        ) : null}
        {props.onShowMethodTextChange ? (
          <label className="ac-trace-opt">
            <input type="checkbox" data-trace-method-text-toggle="true" checked={showMethodText} onChange={(e) => props.onShowMethodTextChange?.(e.target.checked)} /> {m.showMethodText}
          </label>
        ) : null}
        {props.onFollowChange ? (
          <label className="ac-trace-opt">
            <input type="checkbox" checked={follow} onChange={(e) => props.onFollowChange?.(e.target.checked)} /> {m.follow}
          </label>
        ) : null}
        {props.onTimeScaleChange ? (
          <span style={{ display: "inline-flex", gap: 4 }}>
            <button type="button" className="ac-btn" data-size="sm" aria-label={m.zoomOut} disabled={zoom <= MIN_ZOOM} onClick={() => zoomBy(1 / 1.5)}>
              −
            </button>
            <button type="button" className="ac-btn" data-size="sm" aria-label={m.zoomIn} disabled={zoom >= MAX_ZOOM} onClick={() => zoomBy(1.5)}>
              +
            </button>
          </span>
        ) : null}
      </div>

      <div ref={scroller} className="ac-trace-scroller" data-trace-scroller="true">
        <div role="tree" aria-label={m.treeLabel} className="ac-trace-tree" style={treeStyle}>
          <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}>
            <defs>
              <marker id={markerId} markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse">
                <path d="M0,1 L11,6 L0,11 Z" fill="var(--ac-edge-active)" />
              </marker>
            </defs>
          </svg>
          {/* 시간 눈금: 행과 같은 grid 열 정의를 쓴다 */}
          <div aria-hidden="true" className="ac-trace-grid ac-trace-head" data-trace-head="true">
            <div className="ac-trace-cell ac-trace-labelcell" />
            <div className="ac-trace-cell ac-trace-barcell" data-trace-barcell="true">
              <div ref={laneRef} className="ac-trace-lane">
                {ticks.map((t) => {
                  const pct = scale.total > 0 ? (t / scale.total) * 100 : 0;
                  return (
                    <span key={t} className="ac-trace-tick" style={pct > 90 ? { right: `${100 - pct}%` } : { left: `${pct}%` }}>
                      {formatDuration(t, m.units)}
                    </span>
                  );
                })}
              </div>
            </div>
            <div className="ac-trace-cell ac-trace-tailcell" />
          </div>

          {rows.map((row, i) => {
            const span = row.span;
            const grp = row.group;
            const wait = !grp && isUserWait(span);
            const ord = ordinals.get(span.id);
            const baseLab = grp ? (props.groupBadgeFor?.(grp) ?? { title: m.childRunTitle.replace("{id}", grp.runId.slice(0, 6)), sub: m.groupSpanCount.replace("{n}", String(grp.spans.length)) }) : labelOf(span);
            const suffix = `${ord?.iteration !== undefined ? m.iterationSuffix.replace("{n}", String(ord.iteration + 1)) : ""}${ord?.call !== undefined ? m.callSuffix.replace("{n}", String(ord.call + 1)) : ""}`;
            const lab = { title: `${baseLab.title}${suffix}`, sub: baseLab.sub };
            const badge = wait ? undefined : grp ? (baseLab as GroupBadge).badge ? { text: (baseLab as GroupBadge).badge as string } : undefined : methodBadgeFor?.(span);
            const call = !grp && isCallSpan(span);
            const same = !grp && !call && isSameSession(span, row.parentId ? byId.get(row.parentId) : span.parent_id ? byId.get(span.parent_id) : undefined);
            const sessionText = wait || grp ? undefined : (badge?.sessionText ?? (same ? m.sameSession : m.separateSession));
            const collapsedNow = grp ? !row.expanded : collapsed.has(span.id);
            const start = span.started_at;
            const end = endOf(span);
            const left = start != null ? scale.at(start) * 100 : 0;
            const width = start != null && end != null ? Math.max(0, (scale.at(end) - scale.at(start)) * 100) : 0;
            const dur = durationOf(span);
            const durText = dur != null ? formatDuration(dur, m.units) : "";
            const statusText = span.status ? (m.statusText[span.status] ?? span.status) : "";
            const nameText = wait ? m.userWait.replace("{duration}", durText) : lab.title;
            const ariaName = (grp ? `${m.childRunLabel} ` : "") + m.rowLabel
              .replace("{name}", nameText)
              .replace("{method}", [badge?.text, sessionText].filter(Boolean).join(" "))
              .replace("{status}", statusText)
              .replace("{duration}", wait ? "" : durText);
            const isSelected = span.id === selectedSpanId;
            const isHighlighted = Boolean(highlightNodeId && span.node_id === highlightNodeId);
            const incoming = handoffs.find((h) => h.targetRow === i);
            const tokens = span.usage?.total_tokens ?? (span.usage?.input_tokens != null || span.usage?.output_tokens != null ? (span.usage?.input_tokens ?? 0) + (span.usage?.output_tokens ?? 0) : undefined);
            const tokensTitle = tokens != null ? m.tokensTitle.replace("{n}", String(tokens)) : "";
            const tailTitle = [wait ? statusText : durText, tokensTitle].filter(Boolean).join(" · ");
            const chip = incoming && linkBadgeFor ? linkBadgeFor(incoming.link) : undefined;
            const chipRoom = (laneW * left) / 100 - 8;
            const chipVisible = chip !== undefined && (laneW === 0 || chipRoom >= LINK_MIN_ROOM);
            const titleText = grp ? `▣ ${lab.title}` : wait ? `⏸ ${nameText}` : baseLab.title;
            const showSuffix = !wait && suffix !== "";
            const methodText = [badge?.text, sessionText].filter(Boolean).join(" · ");
            const rowStyle: CSSProperties & Record<string, string> = { cursor: "pointer" };
            const rowBg = isSelected ? "var(--ac-accent-bg)" : isHighlighted ? "var(--ac-surface-3)" : undefined;
            if (rowBg) rowStyle["--trace-row-bg"] = rowBg;
            const openLabel = `${m.openChildRun}: ${lab.title}`;
            const subText = showMethodText ? Boolean(methodText) : Boolean(lab.sub && !wait);
            // 부제 글자가 없고 아이콘만 있으면 이름과 같은 줄에 둔다(좁은 칸에서 아이콘이 이름 아래로 떨어지지 않게).
            const subInline = !subText && (Boolean(badge) || Boolean(sessionText));
            const subNode = (
                    <div className={subInline ? "ac-trace-sub ac-trace-sub--inline" : "ac-trace-sub"} data-trace-icons="true">
                      {badge ? (
                        <>
                          {renderTooltip(
                            badge.text,
                            <span className="ac-trace-icon" role="img" aria-label={badge.text} data-trace-method="true">
                              {renderIcon(badge.iconName ?? "link", 12)}
                            </span>,
                          )}
                        </>
                      ) : null}
                      {sessionText
                        ? renderTooltip(
                            sessionText,
                            <span className="ac-trace-icon ac-trace-session" role="img" aria-label={sessionText} data-session-badge={same ? "same" : "separate"} />,
                          )
                        : null}
                      {showMethodText ? (
                        methodText ? (
                          <span className="ac-ellipsis ac-trace-subtext" data-trace-method-text="true" title={methodText}>
                            {methodText}
                          </span>
                        ) : null
                      ) : lab.sub && !wait ? (
                        <span className="ac-ellipsis ac-trace-subtext" title={lab.sub}>
                          {lab.sub}
                        </span>
                      ) : null}
                    </div>
            );
            return (
              <div
                key={span.id}
                ref={(el) => {
                  rowEls.current[i] = el;
                }}
                role="treeitem"
                className="ac-trace-row ac-trace-grid"
                aria-level={row.depth + 1}
                aria-selected={isSelected}
                aria-expanded={row.hasChildren ? !collapsedNow : undefined}
                aria-label={ariaName}
                tabIndex={i === Math.min(focusIdx, rows.length - 1) ? 0 : -1}
                data-span-id={span.id}
                data-group={grp ? grp.runId : undefined}
                data-call={call ? "true" : undefined}
                data-depth={row.depth}
                data-session={wait ? undefined : same ? "same" : "separate"}
                data-selected={isSelected ? "true" : undefined}
                data-highlighted={isHighlighted ? "true" : undefined}
                onFocus={() => setFocusIdx(i)}
                onClick={() => (grp ? toggleGroup(grp.runId, !row.expanded) : onSelect?.(span.id))}
                onKeyDown={(e) => onKeyDown(e, i, row)}
                style={rowStyle}
              >
                <div className="ac-trace-cell ac-trace-labelcell" data-trace-labelcell="true" data-open={grp && props.onOpenChildRun ? "true" : "false"} style={{ "--trace-steps": Math.min(row.depth, MAX_INDENT_STEPS) } as CSSProperties}>
                  <span className="ac-trace-indent" data-guide={row.depth > 0 ? "true" : undefined} aria-hidden="true" />
                  {row.hasChildren ? (
                    <button
                      type="button"
                      tabIndex={-1}
                      aria-label={collapsedNow ? m.expand : m.collapse}
                      className="ac-btn ac-trace-iconbtn"
                      data-variant="ghost"
                      data-size="sm"
                      data-trace-toggle="true"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (grp) toggleGroup(grp.runId, !row.expanded);
                        else toggle(span.id);
                      }}
                    >
                      {collapsedNow ? "▸" : "▾"}
                    </button>
                  ) : (
                    <span className="ac-trace-slot" aria-hidden="true" />
                  )}
                  {incoming?.order != null ? (
                    <span className="ac-trace-order" data-trace-order="true" data-order={incoming.order} data-wide={incoming.order > 99 ? "true" : undefined}>
                      {incoming.order > 99 ? "99+" : incoming.order}
                    </span>
                  ) : (
                    <span className="ac-trace-slot" aria-hidden="true" />
                  )}
                  <div className="ac-trace-text">
                    <div className="ac-trace-title" data-trace-label="true">
                      <span className="ac-ellipsis" title={wait || grp ? titleText : lab.title}>
                        {titleText}
                      </span>
                      {showSuffix ? <span className="ac-trace-suffix">{suffix}</span> : null}
                      {subInline ? subNode : null}
                    </div>
                    {subInline ? null : subNode}
                  </div>
                  {grp && props.onOpenChildRun ? (
                    <button
                      type="button"
                      tabIndex={-1}
                      className="ac-btn ac-trace-iconbtn"
                      data-size="sm"
                      data-trace-open="true"
                      data-open-child={grp.runId}
                      aria-label={openLabel}
                      title={openLabel}
                      onClick={(e) => {
                        e.stopPropagation();
                        props.onOpenChildRun?.(grp.runId);
                      }}
                    >
                      {renderIcon("external-link", 14)}
                    </button>
                  ) : null}
                </div>
                <div className="ac-trace-cell ac-trace-barcell" data-trace-barcell="true">
                  <div className="ac-trace-lane">
                    {incoming && start != null ? (
                      <svg aria-hidden="true" width="100%" height="100%" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
                        <line
                          data-handoff={incoming.link.source}
                          x1={`${(() => {
                            const src = rows[incoming.sourceRow]?.span;
                            const e = src ? endOf(src) : undefined;
                            return e != null ? scale.at(e) * 100 : left;
                          })()}%`}
                          x2={`${left}%`}
                          y1="50%"
                          y2="50%"
                          stroke="var(--ac-edge-active)"
                          strokeWidth="1.5"
                          markerEnd={`url(#${markerId})`}
                        />
                      </svg>
                    ) : null}
                    {chip && chipVisible ? <LinkChip badge={chip} left={left} /> : null}
                    {start != null ? (
                      <div
                        className={`ac-trace-bar ac-status-box${wait ? " ac-trace-wait" : ""}`}
                        data-trace-bar="true"
                        data-status={wait ? "waiting" : barStatus(span)}
                        data-running={span.ended_at == null && running ? "true" : undefined}
                        style={{ left: `${left}%`, width: `max(${width}%, 4px)` }}
                      >
                        {call && span.task_preview ? (
                          <span aria-hidden="true" data-task-preview="true" className="ac-ellipsis ac-trace-task">
                            {span.task_preview}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="ac-trace-cell ac-trace-tailcell" data-trace-tail="true" title={tailTitle || undefined}>
                  <span className="ac-num ac-trace-dur" data-trace-dur="true">
                    {start == null ? "—" : wait ? statusText : dur != null ? formatTailDuration(dur, m.units) : ""}
                  </span>
                  <span className="ac-num ac-trace-tok" data-trace-tok="true">
                    {tokens != null ? `${compactCount(tokens)} ${m.tokensUnit}` : ""}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {selected && props.renderDetail ? (
        <aside aria-label={m.detailLabel} style={{ border: "1px solid var(--ac-border)", borderRadius: "var(--ac-radius-lg)", padding: "var(--ac-space-3)", background: "var(--ac-surface-1)" }}>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button type="button" className="ac-btn" data-size="sm" onClick={() => onSelect?.(null)}>
              {m.closeDetail}
            </button>
          </div>
          {props.renderDetail(selected)}
        </aside>
      ) : null}
    </div>
  );
}

/** 막대 시작 왼쪽에 붙는 연결 칩. 막대 칸(lane) 안에서만 배치하고 `max-width`로 왼쪽 여백 안에 가둔다. */
function LinkChip({ badge, left }: { badge: LinkBadge; left: number }) {
  return (
    <span
      className="ac-trace-chip"
      data-link-badge="true"
      data-trace-link="true"
      data-dashed={badge.dashed ? "true" : undefined}
      style={{ right: `calc(100% - ${left}%)`, maxWidth: `calc(${left}% - 8px)` }}
    >
      {badge.iconName ? <span aria-hidden="true">{badge.iconName} </span> : null}
      {badge.text}
    </span>
  );
}
