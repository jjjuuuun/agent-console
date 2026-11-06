import type { ParsedStage, ParsedTask, SddTaskChangedDetails, TaskLink } from "@agent-console/contracts/sdd";
import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { statusTone, taskTitle, type StatusLike } from "./display";
import { useVirtualRows } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { flattenTaskRows, groupByStage, progressRatio, type TaskRow } from "./stages";
import { TaskFieldChips } from "./TaskFieldChips";
import { TaskRunChips } from "./TaskRunChips";
import { TaskStatusMenu } from "./TaskStatusMenu";
import { ToneChip } from "./ToneChip";

export const TASK_ROW_HEIGHT = 32;
export const STAGE_ROW_HEIGHT = 32;
/** 펼친 상세가 차지하는 높이(처음 추정값, 실제 높이로 다시 잰다). */
export const TASK_DETAIL_HEIGHT = 132;

export interface TaskTableProps {
  tasks: readonly ParsedTask[];
  /** 작업 상태 정의(`SpecView.task_statuses`). 이름·톤·끝남 여부는 서버 데이터. */
  statuses: readonly StatusLike[];
  /** 단계 순서(문서 순서). 없으면 작업에 나온 순서. */
  stages?: readonly ParsedStage[];
  /** 작업 문법이 꺼져 있거나 비었다(`EffectiveSyntax.empty`). 표 대신 안내를 보인다. */
  syntaxEmpty?: boolean;
  onOpenRules?: () => void;
  /** 읽기 전용(폴더 쓰기 불가 등). 상태 칩이 눌리지 않는다. */
  readOnly?: boolean;
  /** 상태 바꾸기가 막힌 이유(관문 등). 주면 칩은 보이되 눌러도 열리지 않는다. */
  blockedReason?: string;
  /** 상태 고르기. 줄 해시는 `task.line_hash`로 호출자가 쓴다. 표는 낙관적으로 바꾸지 않는다. */
  onStatusChange?: (task: ParsedTask, statusId: string) => void;
  /** 줄 충돌(409 `sdd.task_changed`) 알림: 작업 키 → 최신 줄 정보. */
  conflicts?: Readonly<Record<string, SddTaskChangedDetails>>;
  onDismissConflict?: (taskKey: string) => void;
  onOpenDocument?: (task: ParsedTask) => void;
  /** 문서 id → 이름(상세에 보임). 없으면 id 원문. */
  documentTitles?: Readonly<Record<string, string>>;
  /** 실행 연동이 있을 때만 연결 열을 그린다(꺼지면 false). 기본 true */
  showLinks?: boolean;
  openableKinds?: readonly string[];
  onOpenLink?: (link: TaskLink) => void;
  /** 연결 상태 라벨·톤(실행 상태 등) */
  linkStatuses?: readonly StatusLike[];
  /** 행 오른쪽 동작 자리([실행 ▾] 등). 앱이 연동 동작 목록으로 만든다. */
  renderActions?: (task: ParsedTask) => ReactNode;
  /** 펼친 작업 키(제어형). 없으면 안에서 관리 */
  expandedKey?: string | null;
  onExpandedChange?: (key: string | null) => void;
  height?: number | "fill";
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 작업 표(가상 목록, 단계 묶음). 한 번에 하나만 행 아래 인라인으로 펼친다(S8).
 * 상태·단계·필드 이름은 전부 props 데이터이고, 상태를 바꾸는 조작은 `onStatusChange`로만 알린다.
 */
export function TaskTable(props: TaskTableProps) {
  const {
    tasks, statuses, stages, syntaxEmpty = false, onOpenRules, readOnly = false, blockedReason, onStatusChange, conflicts, onDismissConflict, onOpenDocument,
    documentTitles, showLinks = true, openableKinds, onOpenLink, linkStatuses, renderActions, expandedKey, onExpandedChange, height = "fill", messages, className,
  } = props;
  const text = resolveMessages(messages);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [innerExpanded, setInnerExpanded] = useState<string | null>(null);
  const expanded = expandedKey !== undefined ? expandedKey : innerExpanded;
  const setExpanded = (key: string | null) => {
    setInnerExpanded(key);
    onExpandedChange?.(key);
  };

  const doneIds = useMemo(() => new Set(statuses.filter((s) => s.done === true).map((s) => s.id)), [statuses]);
  const groups = useMemo(() => groupByStage(tasks, (s) => doneIds.has(s), stages), [tasks, doneIds, stages]);
  const rows = useMemo(() => flattenTaskRows(groups, collapsed), [groups, collapsed]);
  const rowHeight = (i: number): number => {
    const row = rows[i];
    if (!row) return TASK_ROW_HEIGHT;
    if (row.type === "stage") return STAGE_ROW_HEIGHT;
    return row.task.key === expanded ? TASK_ROW_HEIGHT + TASK_DETAIL_HEIGHT : TASK_ROW_HEIGHT;
  };
  const virtual = useVirtualRows({ count: rows.length, rowHeight, scrollRef, measureKey: `${expanded ?? ""}|${rows.length}` });
  const root = `ac-sdd-root${className ? ` ${className}` : ""}`;

  if (syntaxEmpty) {
    return (
      <div className={`${root} ac-sdd-empty`} role="status" data-state="no-syntax">
        <p className="ac-sdd-empty-title">{text["tasks.noSyntax.title"]}</p>
        <p className="ac-sdd-muted">{text["tasks.noSyntax.body"]}</p>
        {onOpenRules ? (
          <button type="button" className="ac-sdd-btn" onClick={onOpenRules}>
            {text["tasks.noSyntax.action"]}
          </button>
        ) : null}
      </div>
    );
  }
  if (tasks.length === 0) {
    return (
      <div className={`${root} ac-sdd-empty`} role="status" data-state="empty">
        <p className="ac-sdd-empty-title">{text["tasks.empty.title"]}</p>
        <p className="ac-sdd-muted">{text["tasks.empty.body"]}</p>
      </div>
    );
  }

  const focusSibling = (e: KeyboardEvent<HTMLElement>, delta: number) => {
    const nodes = Array.from(scrollRef.current?.querySelectorAll<HTMLElement>("[data-sdd-rowfocus]") ?? []);
    const at = nodes.indexOf(e.currentTarget);
    const next = nodes[at + delta];
    if (next) {
      e.preventDefault();
      next.focus();
    }
  };
  const onRowKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "ArrowDown") focusSibling(e, 1);
    else if (e.key === "ArrowUp") focusSibling(e, -1);
  };

  const renderRow = (row: TaskRow) => {
    if (row.type === "stage") {
      const { group } = row;
      const isCollapsed = collapsed.has(group.key);
      const title = group.stage ? (group.stage.title ?? group.stage.id) : text["tasks.stage.none"];
      return (
        <button
          type="button"
          className="ac-sdd-stage"
          data-rowfocus-host=""
          data-sdd-rowfocus=""
          aria-expanded={!isCollapsed}
          aria-label={`${formatMessage(text["tasks.stage.toggle"], { stage: title })}, ${formatMessage(text["tasks.stage.progress"], { done: group.done, total: group.total })}`}
          onKeyDown={onRowKey}
          onClick={() => {
            const next = new Set(collapsed);
            if (isCollapsed) next.delete(group.key);
            else next.add(group.key);
            setCollapsed(next);
          }}
        >
          <span className="ac-sdd-caret" data-open={!isCollapsed || undefined} aria-hidden="true" />
          <span className="ac-sdd-stage-title ac-sdd-ellipsis">{title}</span>
          <span className="ac-sdd-progress" aria-hidden="true">
            <span className="ac-sdd-progress-fill" style={{ width: `${progressRatio(group.done, group.total) * 100}%` }} />
          </span>
          <span className="ac-sdd-muted ac-sdd-num">{formatMessage(text["tasks.stage.progress"], { done: group.done, total: group.total })}</span>
        </button>
      );
    }
    const { task } = row;
    const title = taskTitle(task);
    const shown = statusTone(task.status, statuses);
    const open = expanded === task.key;
    const conflict = conflicts?.[task.key];
    const readiness = task.ready ? text["tasks.ready"] : text["tasks.blocked"];
    const issues = task.issues ?? [];
    return (
      <div className="ac-sdd-task" data-ready={task.ready ? "" : undefined} data-open={open || undefined}>
        <div className="ac-sdd-task-line">
          <button
            type="button"
            className="ac-sdd-task-title"
            data-sdd-rowfocus=""
            aria-expanded={open}
            aria-label={`${formatMessage(text["tasks.row"], { title, status: shown.label, readiness })}. ${open ? text["tasks.collapse"] : text["tasks.expand"]}`}
            onKeyDown={onRowKey}
            onClick={() => setExpanded(open ? null : task.key)}
          >
            <span className="ac-sdd-caret" data-open={open || undefined} aria-hidden="true" />
            {task.id ? <span className="ac-sdd-mono ac-sdd-muted">{task.id}</span> : null}
            <span className="ac-sdd-ellipsis">{title}</span>
          </button>
          <span className="ac-sdd-task-cell">
            <TaskStatusMenu
              status={task.status}
              statuses={statuses}
              taskTitle={title}
              readOnly={readOnly}
              {...(blockedReason !== undefined ? { blockedReason } : {})}
              {...(onStatusChange ? { onSelect: (id: string) => onStatusChange(task, id) } : {})}
              messages={text}
            />
            <ToneChip label={readiness} tone={task.ready ? "info" : "neutral"} />
          </span>
          <TaskFieldChips fields={task.fields} messages={text} />
          {showLinks ? <TaskRunChips links={task.links} {...(openableKinds ? { openableKinds } : {})} {...(onOpenLink ? { onOpen: onOpenLink } : {})} {...(linkStatuses ? { statuses: linkStatuses } : {})} messages={text} /> : null}
          {renderActions ? <span className="ac-sdd-task-actions">{renderActions(task)}</span> : null}
        </div>
        {conflict ? (
          <div className="ac-sdd-banner" data-tone="warning" role="alert">
            <strong>{text["tasks.conflict.title"]}</strong> {text["tasks.conflict.body"]}
            {conflict.text ? (
              <span className="ac-sdd-mono">
                {text["tasks.conflict.latest"]}: {conflict.text}
              </span>
            ) : null}
            {onDismissConflict ? (
              <button type="button" className="ac-sdd-btn" onClick={() => onDismissConflict(task.key)}>
                {text["common.close"]}
              </button>
            ) : null}
          </div>
        ) : null}
        {open ? (
          <dl className="ac-sdd-detail">
            <dt>{text["tasks.detail.document"]}</dt>
            <dd>
              {documentTitles?.[task.document] ?? task.document} · {formatMessage(text["tasks.detail.line"], { line: task.line })}
              {onOpenDocument ? (
                <button type="button" className="ac-sdd-link" onClick={() => onOpenDocument(task)}>
                  {text["tasks.detail.open"]}
                </button>
              ) : null}
            </dd>
            {(task.requirements ?? []).length > 0 ? (
              <>
                <dt>{text["tasks.detail.requirements"]}</dt>
                <dd className="ac-sdd-mono">{(task.requirements ?? []).join(", ")}</dd>
              </>
            ) : null}
            {(task.dependencies ?? []).length > 0 ? (
              <>
                <dt>{text["tasks.detail.dependencies"]}</dt>
                <dd className="ac-sdd-mono">{(task.dependencies ?? []).join(", ")}</dd>
              </>
            ) : null}
            {issues.length > 0 ? (
              <>
                <dt>{text["tasks.detail.issues"]}</dt>
                <dd>{issues.map((i) => i.message).join(" / ")}</dd>
              </>
            ) : null}
          </dl>
        ) : null}
      </div>
    );
  };

  return (
    <div ref={scrollRef} className={`${root} ac-sdd-scroll`} style={{ height: height === "fill" ? "100%" : height }}>
      <ul className="ac-sdd-vlist" role="list" aria-label={text["tasks.table"]} style={{ height: virtual.getTotalSize() }}>
        {virtual.getVirtualItems().map((item) => {
          const row = rows[item.index] as TaskRow;
          return (
            <li
              key={row.key}
              ref={row.type === "task" && row.task.key === expanded ? virtual.measureElement : undefined}
              data-index={item.index}
              className="ac-sdd-vrow ac-sdd-vrow-auto"
              style={{ transform: `translateY(${item.start}px)`, minHeight: row.type === "stage" ? STAGE_ROW_HEIGHT : TASK_ROW_HEIGHT }}
              aria-setsize={rows.length}
              aria-posinset={item.index + 1}
            >
              {renderRow(row)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
