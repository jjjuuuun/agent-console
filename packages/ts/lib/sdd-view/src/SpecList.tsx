import type { SpecSummary } from "@agent-console/contracts/sdd";
import { useRef, type ReactNode } from "react";
import { useVirtualRows } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { progressRatio } from "./stages";
import { DocumentStateChip } from "@agent-console/markdown-doc";

export const SPEC_ROW_HEIGHT = 40;

/** 목록 열(순서 고정, 표 머리·행이 같은 격자를 쓴다). 열 이름은 `specs.col.<id>` 문구이고, 정렬 가능 여부는 `sortColumns`에 id가 있는지로 정한다. */
export const SPEC_COLUMNS = ["name", "progress", "stage", "documents", "ready", "updated"] as const;

/** 열 머리 정렬 열 하나. id·라벨은 앱이 준다. */
export interface SpecSortColumn {
  id: string;
  label: string;
}

/** 지금 정렬(열 id + 방향). */
export interface SpecSortState {
  id: string;
  direction: "asc" | "desc";
}

export interface SpecListProps {
  specs: readonly SpecSummary[];
  selectedId?: string | null;
  onOpen?: (spec: SpecSummary) => void;
  loading?: boolean;
  /** 빈 상태에 붙이는 버튼(새 스펙·폴더에서 가져오기 등). 앱이 준다. */
  emptyActions?: ReactNode;
  /** 시각 표시(앱의 시간 서식). 없으면 ISO 날짜. */
  formatTime?: (epochSeconds: number) => string;
  /** 열 머리 정렬 열(없으면 머리 줄을 그리지 않는다). 정렬은 앱이 한다 */
  sortColumns?: readonly SpecSortColumn[];
  /** 지금 정렬(없으면 어느 열도 정렬 표시 없음) */
  sort?: SpecSortState | null;
  /** 열 머리를 눌렀다(방향을 어떻게 바꿀지는 앱이 정한다) */
  onSortChange?: (columnId: string) => void;
  /** 행 오른쪽 메뉴 slot(예: `⋯` 메뉴 버튼). 행 버튼 밖에 놓여 키보드로 따로 닿는다 */
  renderRowMenu?: (spec: SpecSummary) => ReactNode;
  /** 목록 높이(px 또는 'fill') */
  height?: number | "fill";
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

interface DocumentStateGroup {
  key: string;
  state: string | null;
  label: string;
  tone: string | null;
  count: number;
}

/** 문서 상태를 서로 다른 상태끼리 묶는다(처음 나온 순서). 상태 이름·톤은 서버 데이터. */
function groupDocumentStates(docs: NonNullable<SpecSummary["documents"]>): DocumentStateGroup[] {
  const groups = new Map<string, DocumentStateGroup>();
  for (const d of docs) {
    const key = d.state ?? "";
    const g = groups.get(key);
    if (g) g.count += 1;
    else groups.set(key, { key, state: d.state ?? null, label: d.state_label ?? d.state ?? "", tone: d.tone ?? null, count: 1 });
  }
  return [...groups.values()];
}

function defaultTime(seconds: number): string {
  return new Date(seconds * 1000).toISOString().slice(0, 10);
}

/** 스펙 목록(가상 목록). 진행·지금 단계·문서 상태·준비된 작업 수를 한 줄에 보인다. 스펙 이름·문서 종류는 데이터다. */
export function SpecList({ specs, selectedId, onOpen, loading = false, emptyActions, sortColumns, sort, onSortChange, renderRowMenu, formatTime = defaultTime, height = "fill", messages, className }: SpecListProps) {
  const text = resolveMessages(messages);
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtual = useVirtualRows({ count: specs.length, rowHeight: SPEC_ROW_HEIGHT, scrollRef });
  if (specs.length === 0) {
    return (
      <div className={`ac-sdd-root ac-sdd-empty${className ? ` ${className}` : ""}`} role="status">
        <p className="ac-sdd-empty-title">{loading ? text["common.loading"] : text["specs.empty.title"]}</p>
        {loading ? null : <p className="ac-sdd-muted">{text["specs.empty.body"]}</p>}
        {loading ? null : emptyActions}
      </div>
    );
  }
  return (
    <div
      ref={scrollRef}
      className={`ac-sdd-root ac-sdd-scroll${className ? ` ${className}` : ""}`}
      style={{ height: height === "fill" ? "100%" : height }}
      aria-busy={loading || undefined}
    >
      <div role="table" aria-label={text["specs.sort.label"]} className="ac-sdd-sorthead-table">
        <div role="row" className="ac-sdd-sorthead ac-sdd-spec-grid">
          {SPEC_COLUMNS.map((id) => {
            const label = text[`specs.col.${id}`] ?? id;
            const sortable = sortColumns?.some((c) => c.id === id) === true;
            const current = sort?.id === id ? sort.direction : null;
            return (
              <div key={id} role="columnheader" data-col={id} {...(sortable ? { "aria-sort": current === "asc" ? "ascending" : current === "desc" ? "descending" : "none" } : {})}>
                {sortable ? (
                  <button type="button" className="ac-sdd-sortbtn" data-active={current !== null || undefined} onClick={() => onSortChange?.(id)}>
                    <span>{label}</span>
                    <span aria-hidden="true">{current === "asc" ? "▲" : current === "desc" ? "▼" : ""}</span>
                  </button>
                ) : (
                  <span className="ac-sdd-colhead">{label}</span>
                )}
              </div>
            );
          })}
          {renderRowMenu === undefined ? null : <div role="columnheader" data-col="menu"><span className="ac-sdd-sr-only">{text["specs.col.menu"]}</span></div>}
        </div>
      </div>
      <ul className="ac-sdd-vlist" role="list" aria-label={text["specs.list"]} style={{ height: virtual.getTotalSize() }}>
        {virtual.getVirtualItems().map((item) => {
          const spec = specs[item.index] as SpecSummary;
          const total = spec.tasks_total ?? 0;
          const done = spec.tasks_done ?? 0;
          const selected = spec.id === selectedId;
          return (
            <li
              key={spec.id}
              className="ac-sdd-vrow"
              style={{ transform: `translateY(${item.start}px)`, height: SPEC_ROW_HEIGHT }}
              aria-setsize={specs.length}
              aria-posinset={item.index + 1}
              onContextMenu={renderRowMenu === undefined ? undefined : (e) => {
                // 우클릭·Shift+F10: 행 메뉴를 연다(`⋯`은 마우스를 올리거나 포커스가 있을 때만 보인다)
                const trigger = e.currentTarget.querySelector<HTMLElement>(".ac-sdd-spec-menu button");
                if (trigger) {
                  e.preventDefault();
                  trigger.click();
                }
              }}
            >
              <button type="button" className="ac-sdd-spec ac-sdd-spec-grid" data-menu={renderRowMenu !== undefined || undefined} data-selected={selected || undefined} aria-current={selected ? "true" : undefined} title={spec.directory || undefined} onClick={() => onOpen?.(spec)}>
                <span className="ac-sdd-spec-name ac-sdd-ellipsis" data-col="name">
                  {spec.name && spec.name !== "" ? spec.name : spec.id}
                  {(spec.issues ?? 0) > 0 ? <span className="ac-sdd-num ac-sdd-spec-issues" data-tone="warning"> {formatMessage(text["specs.issues"], { n: spec.issues ?? 0 })}</span> : null}
                </span>
                <span className="ac-sdd-spec-progress" data-col="progress">
                  <span
                    className="ac-sdd-progress"
                    role="progressbar"
                    aria-label={total > 0 ? formatMessage(text["specs.progress"], { done, total }) : text["specs.noTasks"]}
                    aria-valuemin={0}
                    aria-valuemax={Math.max(total, 1)}
                    aria-valuenow={done}
                  >
                    <span className="ac-sdd-progress-fill" style={{ width: `${progressRatio(done, total) * 100}%` }} />
                  </span>
                  <span className="ac-sdd-muted ac-sdd-num">{total > 0 ? `${done}/${total}` : text["specs.noTasks"]}</span>
                </span>
                <span className="ac-sdd-ellipsis ac-sdd-muted" data-col="stage">{spec.current_stage ? (spec.current_stage.title ?? spec.current_stage.id) : text["specs.stage.none"]}</span>
                <span className="ac-sdd-spec-docs" data-col="documents">
                  {groupDocumentStates(spec.documents ?? []).map((g) => (
                    <DocumentStateChip key={g.key} state={g.state} label={g.count > 1 ? `${g.label} ${g.count}` : g.label} tone={g.tone} />
                  ))}
                </span>
                <span className="ac-sdd-num" data-col="ready" title={formatMessage(text["specs.ready"], { n: spec.ready ?? 0 })}>{(spec.ready ?? 0) > 0 ? spec.ready : <span className="ac-sdd-muted">{text["specs.stage.none"]}</span>}</span>
                <span className="ac-sdd-muted ac-sdd-ellipsis" data-col="updated">{spec.updated_at ? formatTime(spec.updated_at) : text["specs.stage.none"]}</span>
              </button>
              {renderRowMenu === undefined ? null : <span className="ac-sdd-spec-menu">{renderRowMenu(spec)}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
