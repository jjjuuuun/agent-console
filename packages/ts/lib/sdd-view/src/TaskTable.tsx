import type { ParsedStage, ParsedTask, SddTaskChangedDetails, TaskLink } from "@agent-console/contracts/sdd";
import { useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
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

/** 행 컨텍스트 메뉴 항목 */
export interface TaskRowMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
  disabled?: boolean;
}

/** 표 바깥(단축키 처리기)이 쓰는 손잡이. 키 이름은 모르고 "지금 포커스된 행에 무엇을 할지"만 안다. */
export interface TaskTableHandle {
  /** 포커스가 있는 작업 행의 키(없으면 null) */
  activeTaskKey(): string | null;
  /** 그 행의 상태 메뉴를 연다(막혀 있으면 아무 일도 없다) */
  openStatusMenu(taskKey: string): void;
  /** 그 행의 동작 메뉴(`renderActions`가 그린 단추)를 연다 */
  openActionsMenu(taskKey: string): void;
  /** 그 행 아래 컨텍스트 메뉴를 연다 */
  openRowMenu(taskKey: string): void;
}

/** 인라인 알림이 있는 행의 처음 높이 추정(실제 높이로 다시 잰다) */
const NOTICE_HEIGHT = 56;

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
  /** 행 체크박스 선택을 그린다(머리 체크박스 = 보이는 준비된 작업만, "{n}개 선택"·[선택 해제]). 준비 여부는 표가 상태 정의의 `done`과 `task.ready`로 안다. */
  selectable?: boolean;
  /** 선택한 작업 키(제어형). 없으면 안에서 관리 */
  selectedKeys?: ReadonlySet<string>;
  onSelectedChange?: (keys: ReadonlySet<string>) => void;
  /** 단계 접힘을 사용자가 바꾼 것만 담은 표(단계 키 → 접힘 여부, 제어형). 없는 단계는 기본값(모두 끝난 단계는 접힘, 나머지는 펼침). 저장은 호출자 몫 */
  collapsedOverrides?: Readonly<Record<string, boolean>>;
  onCollapsedChange?: (overrides: Readonly<Record<string, boolean>>) => void;
  /** 작업 행 바로 아래 인라인 알림 자리(관문 안내·실행 오류 등). 행마다 하나만 둔다 */
  renderRowNotice?: (task: ParsedTask) => ReactNode;
  /** 행 컨텍스트 메뉴 항목(`openRowMenu`나 `Shift+F10`을 앱이 등록한 단축키로 연결). 없으면 메뉴가 없다 */
  rowMenuItems?: (task: ParsedTask) => readonly TaskRowMenuItem[];
  /** 앱의 단축키 처리기가 행 동작을 부르는 손잡이 */
  ref?: Ref<TaskTableHandle>;
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
    selectable = false, selectedKeys, onSelectedChange, collapsedOverrides, onCollapsedChange, renderRowNotice, rowMenuItems, ref,
  } = props;
  const text = resolveMessages(messages);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [innerOverrides, setInnerOverrides] = useState<Readonly<Record<string, boolean>>>({});
  const overrides = collapsedOverrides ?? innerOverrides;
  const [innerSelected, setInnerSelected] = useState<ReadonlySet<string>>(new Set());
  const selected = selectedKeys ?? innerSelected;
  const [menuKey, setMenuKey] = useState<string | null>(null);
  const setSelected = (next: ReadonlySet<string>) => {
    setInnerSelected(next);
    onSelectedChange?.(next);
  };
  const setOverrides = (next: Readonly<Record<string, boolean>>) => {
    setInnerOverrides(next);
    onCollapsedChange?.(next);
  };
  const [innerExpanded, setInnerExpanded] = useState<string | null>(null);
  const expanded = expandedKey !== undefined ? expandedKey : innerExpanded;
  const setExpanded = (key: string | null) => {
    setInnerExpanded(key);
    onExpandedChange?.(key);
  };

  const doneIds = useMemo(() => new Set(statuses.filter((s) => s.done === true).map((s) => s.id)), [statuses]);
  const groups = useMemo(() => groupByStage(tasks, (s) => doneIds.has(s), stages), [tasks, doneIds, stages]);
  // 기본: 모두 끝난 단계는 접힘, 나머지는 펼침. 사용자가 바꾼 단계만 덮어쓴다.
  const collapsed = useMemo(() => new Set(groups.filter((g) => overrides[g.key] ?? (g.total > 0 && g.done === g.total)).map((g) => g.key)), [groups, overrides]);
  const rows = useMemo(() => flattenTaskRows(groups, collapsed), [groups, collapsed]);
    const readyVisible = useMemo(() => tasks.filter((t) => t.ready === true && !doneIds.has(t.status)), [tasks, doneIds]);
  const selectedCount = tasks.filter((t) => selected.has(t.key)).length;
  const allReadySelected = readyVisible.length > 0 && readyVisible.every((t) => selected.has(t.key));
  const toggleSelect = (key: string, on: boolean) => {
    const next = new Set(selected);
    if (on) next.add(key);
    else next.delete(key);
    setSelected(next);
  };
  const selectAllReady = (on: boolean) => {
    const next = new Set(selected);
    for (const t of readyVisible) {
      if (on) next.add(t.key);
      else next.delete(t.key);
    }
    setSelected(next);
  };
  const noticeKeys = renderRowNotice ? tasks.filter((t) => renderRowNotice(t) != null).map((t) => t.key).join("|") : "";
  const hasNotice = (task: ParsedTask) => noticeKeys.split("|").includes(task.key);
  const rowHeight = (i: number): number => {
    const row = rows[i];
    if (!row) return TASK_ROW_HEIGHT;
    if (row.type === "stage") return STAGE_ROW_HEIGHT;
    const extra = (row.task.key === expanded ? TASK_DETAIL_HEIGHT : 0) + (renderRowNotice && hasNotice(row.task) ? NOTICE_HEIGHT : 0) + (menuKey === row.task.key ? NOTICE_HEIGHT : 0);
    return TASK_ROW_HEIGHT + extra;
  };
  const virtual = useVirtualRows({ count: rows.length, rowHeight, scrollRef, measureKey: `${expanded ?? ""}|${rows.length}|${noticeKeys}|${menuKey ?? ""}` });
  const taskEl = (key: string) => Array.from(scrollRef.current?.querySelectorAll<HTMLElement>("[data-sdd-task-key]") ?? []).find((el) => el.dataset["sddTaskKey"] === key);
  useImperativeHandle(
    ref,
    () => ({
      activeTaskKey: () => (typeof document === "undefined" ? null : (document.activeElement?.closest<HTMLElement>("[data-sdd-task-key]")?.dataset["sddTaskKey"] ?? null)),
      openStatusMenu: (key) => taskEl(key)?.querySelector<HTMLElement>('[data-sdd-trigger="status"]')?.click(),
      openActionsMenu: (key) => taskEl(key)?.querySelector<HTMLElement>('[data-sdd-trigger="actions"] button')?.click(),
      openRowMenu: (key) => {
        if (rowMenuItems) setMenuKey(key);
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 손잡이는 DOM만 읽고 rowMenuItems 유무만 본다
    [rowMenuItems === undefined],
  );
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
  const focusEdge = (e: KeyboardEvent<HTMLElement>, to: "first" | "last" | number) => {
    const nodes = Array.from(scrollRef.current?.querySelectorAll<HTMLElement>("[data-sdd-rowfocus]") ?? []);
    const at = nodes.indexOf(e.currentTarget);
    const next = to === "first" ? nodes[0] : to === "last" ? nodes[nodes.length - 1] : nodes[Math.min(nodes.length - 1, Math.max(0, at + to))];
    if (next) {
      e.preventDefault();
      next.focus();
    }
  };
  /** 행 공통 키: 이동(↑↓ Home End PageUp/Down). 행 종류별 키는 각 행에서 더한다. */
  const onRowKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "ArrowDown") focusSibling(e, 1);
    else if (e.key === "ArrowUp") focusSibling(e, -1);
    else if (e.key === "Home") focusEdge(e, "first");
    else if (e.key === "End") focusEdge(e, "last");
    else if (e.key === "PageDown") focusEdge(e, 10);
    else if (e.key === "PageUp") focusEdge(e, -10);
  };
  const setStageCollapsed = (key: string, value: boolean) => setOverrides({ ...overrides, [key]: value });

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
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" && isCollapsed) setStageCollapsed(group.key, false);
            else if (e.key === "ArrowLeft" && !isCollapsed) setStageCollapsed(group.key, true);
            else onRowKey(e);
          }}
          onClick={() => setStageCollapsed(group.key, !isCollapsed)}
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
    const notice = renderRowNotice?.(task);
    const menu = menuKey === task.key && rowMenuItems ? rowMenuItems(task) : null;
    const closeMenu = () => {
      setMenuKey(null);
      taskEl(task.key)?.querySelector<HTMLElement>("[data-sdd-rowfocus]")?.focus();
    };
    return (
      <div className="ac-sdd-task" data-sdd-task-key={task.key} data-ready={task.ready ? "" : undefined} data-open={open || undefined} data-selected={selected.has(task.key) || undefined}>
        <div className="ac-sdd-task-line">
          {selectable ? (
            <input
              type="checkbox"
              className="ac-sdd-check"
              checked={selected.has(task.key)}
              aria-label={formatMessage(text["tasks.select.row"], { title })}
              onChange={(e) => toggleSelect(task.key, e.target.checked)}
            />
          ) : null}
          <button
            type="button"
            className="ac-sdd-task-title"
            data-sdd-rowfocus=""
            aria-expanded={open}
            aria-label={`${formatMessage(text["tasks.row"], { title, status: shown.label, readiness })}. ${open ? text["tasks.collapse"] : text["tasks.expand"]}`}
            onKeyDown={(e) => {
              if (e.target !== e.currentTarget) return;
              if (selectable && e.key === " " && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                toggleSelect(task.key, !selected.has(task.key));
              } else if (selectable && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
                e.preventDefault();
                selectAllReady(true);
              } else if (e.key === "ArrowRight" && !open) setExpanded(task.key);
              else if (e.key === "ArrowLeft" && open) setExpanded(null);
              else if (e.key === "Escape") {
                if (menu) closeMenu();
                else if (open) setExpanded(null);
                else if (selectedCount > 0) setSelected(new Set());
              } else onRowKey(e);
            }}
            onKeyUp={(e) => {
              // Space는 선택 토글이다. 버튼의 기본 동작(keyup 클릭)이 펼침을 열지 않게 막는다.
              if (selectable && e.key === " ") e.preventDefault();
            }}
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
          {renderActions ? <span className="ac-sdd-task-actions" data-sdd-trigger="actions">{renderActions(task)}</span> : null}
        </div>
        {notice != null ? <div className="ac-sdd-row-notice" data-sdd-row-notice="">{notice}</div> : null}
        {menu ? (
          <ul
            className="ac-sdd-rowmenu"
            role="menu"
            aria-label={formatMessage(text["tasks.rowMenu"], { title })}
            ref={(el) => el?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus()}
            onKeyDown={(e) => {
              const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])'));
              const at = items.indexOf(document.activeElement as HTMLElement);
              if (e.key === "Escape") {
                e.preventDefault();
                closeMenu();
              } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                items[(at + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
              } else if (e.key === "Tab") setMenuKey(null);
            }}
          >
            {menu.map((item) => (
              <li key={item.id} role="none">
                <button
                  type="button"
                  role="menuitem"
                  className="ac-sdd-menu-item"
                  disabled={item.disabled}
                  onClick={() => {
                    closeMenu();
                    item.onSelect();
                  }}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
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
      {selectable ? (
        <div className="ac-sdd-selbar" data-sdd-selbar="">
          <input
            type="checkbox"
            className="ac-sdd-check"
            checked={allReadySelected}
            disabled={readyVisible.length === 0}
            aria-label={text["tasks.select.all"]}
            onChange={(e) => selectAllReady(e.target.checked)}
          />
          <span className="ac-sdd-muted">{selectedCount > 0 ? formatMessage(text["tasks.select.count"], { n: selectedCount }) : text["tasks.select.all"]}</span>
          {selectedCount > 0 ? (
            <button type="button" className="ac-sdd-link" onClick={() => setSelected(new Set())}>
              {text["tasks.select.clear"]}
            </button>
          ) : null}
        </div>
      ) : null}
      <ul className="ac-sdd-vlist" role="list" aria-label={text["tasks.table"]} style={{ height: virtual.getTotalSize() }}>
        {virtual.getVirtualItems().map((item) => {
          const row = rows[item.index] as TaskRow;
          return (
            <li
              key={row.key}
              ref={row.type === "task" && (row.task.key === expanded || hasNotice(row.task) || menuKey === row.task.key) ? virtual.measureElement : undefined}
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
