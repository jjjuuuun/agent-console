import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { Banner, Button, EmptyState, Icon, MiddleEllipsis } from "@agent-console/ui";
import { MenuPopover } from "./MenuPopover";
import "./targetPicker.css";
import { targetPickerMessages as m } from "./targetPickerMessages";

/** 고를 수 있는 시작 대상 하나(팀 구성 등). 종류 이름은 모른다 — 호출자가 데이터를 이 모양으로 만들어 준다. */
export interface TargetOption {
  id: string;
  name: string;
  description?: string | undefined;
  /** 12px 보조 줄(노드 수 · 마지막 사용 등) */
  meta?: string | undefined;
  /** 시작할 수 없는 대상(실행을 막는 문제 등): 라디오는 `aria-disabled`, 선택되지 않는다 */
  blocked?: boolean | undefined;
  /** 사유 칩·문제 보기 같은 행 아래 줄(라디오 밖에 그려 안의 컨트롤이 비활성이 되지 않게 한다) */
  reason?: ReactNode;
  /** 문제 보기를 펼쳤을 때 본문 */
  expanded?: ReactNode;
  /** 그 대상의 사본 편집 화면(막힌 행의 [구성 편집 →]) */
  editHref?: string | undefined;
}

/** 폴더 줄이 보일 프로젝트 하나(대화상자의 대상 후보). */
export interface TargetProject {
  id: string;
  name: string;
  dir: string;
}

export interface ProjectTargetPickerProps {
  /** 대화상자의 대상 프로젝트 */
  project: TargetProject | undefined;
  /** [바꾸기] 목록(시작할 수 있는 프로젝트) */
  projects: readonly TargetProject[];
  onProjectChange: (id: string) => void;
  /** 대상이 전역 현재 프로젝트와 다르면 12px 안내 */
  switchesCurrent?: boolean;
  /** 폴더 문제(상태 문구). 있으면 폴더 줄이 경고 톤이 되고 [경로 다시 지정]이 붙는다 */
  folderProblem?: { text: string; tone: "warning" | "danger" } | undefined;
  onRepath?: (() => void) | undefined;
  options: readonly TargetOption[];
  loading?: boolean;
  /** 목록을 읽지 못함: 목록 자리에 오류 줄 + [다시 시도] */
  error?: boolean;
  onRetry?: (() => void) | undefined;
  value: string | undefined;
  onChange: (id: string | undefined) => void;
  /** 이 개수 이상일 때만 검색 입력을 보인다(기본 8) */
  searchFrom?: number;
  /** ＋ 공용에서 가져오기… (목록 끝 고정 행) */
  onImport: () => void;
  /** 막힘 이유(구성을 쓸 수 없는 폴더 등): 있으면 가져오기 행이 `aria-disabled` + 이유 */
  importBlockedReason?: string | undefined;
  /** 구성 0개일 때 [이 프로젝트에서 새로 만들기] 링크 주소(없으면 링크 없음) */
  createHref?: string | undefined;
  onNavigate?: (() => void) | undefined;
  /** 구성 목록 라벨 */
  listLabel?: string;
  /** 목록 아래에 항상 보이는 부분(제목 입력 등). 목록은 자체 스크롤이라 이 영역은 늘 보인다 */
  children?: ReactNode;
  /** 행 편집 단축키(E) 등 키보드 동작을 호출자가 붙일 때 */
  onEdit?: ((option: TargetOption) => void) | undefined;
}

/**
 * 시작 대상 고르기(screen-projects §5.4, 채팅·실행이 함께 쓰는 부품): 폴더 줄 + 구성 라디오 목록 + 공용에서 가져오기 행.
 * 표현 전용이다 — 프로젝트·구성 목록·가져오기 동작은 모두 props로 받는다.
 * 목록은 최대 높이에서 스크롤하고 `children`(제목 입력)은 늘 보인다.
 */
export function ProjectTargetPicker(p: ProjectTargetPickerProps) {
  const uid = useId();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const list = useRef<HTMLUListElement>(null);
  const q = query.trim().toLowerCase();
  const filtered = useMemo(() => (q === "" ? p.options : p.options.filter((o) => o.name.toLowerCase().includes(q) || (o.description ?? "").toLowerCase().includes(q))), [p.options, q]);
  const usable = (o: TargetOption) => o.blocked !== true;
  const preselect = p.options.find(usable)?.id;
  const picked = p.value !== undefined && p.options.some((o) => o.id === p.value && usable(o)) ? p.value : preselect;
  const selectable = filtered.filter(usable);
  const tabStop = (selectable.some((o) => o.id === picked) ? picked : selectable[0]?.id) ?? filtered[0]?.id;
  const showSearch = p.options.length >= (p.searchFrom ?? 8);

  const move = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const focused = e.target instanceof HTMLElement ? e.target.closest<HTMLElement>("[data-option-id]")?.dataset["optionId"] : undefined;
    const i = filtered.findIndex((o) => o.id === (focused ?? picked));
    const next = filtered[Math.min(filtered.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next === undefined) return;
    if (usable(next)) p.onChange(next.id);
    list.current?.querySelector<HTMLElement>(`[data-option-id="${CSS.escape(next.id)}"]`)?.focus();
  };
  const toggle = (id: string) =>
    setExpanded((cur) => {
      const next = new Set(cur);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const importBlocked = p.importBlockedReason !== undefined;
  const importRow = (primary: boolean) => (
    <Button
      variant={primary ? "primary" : "ghost"}
      size={primary ? "md" : "sm"}
      className="tp-import"
      aria-disabled={importBlocked ? "true" : undefined}
      title={p.importBlockedReason}
      onClick={() => !importBlocked && p.onImport()}
    >
      {primary ? m.config.importPrimary : m.config.import}
    </Button>
  );

  return (
    <div className="tp" data-testid="project-target-picker">
      <div className="tp-folder" data-problem={p.folderProblem?.tone}>
        <span className="tp-label app-muted">{m.folder.label}</span>
        {p.project === undefined ? null : (
          <>
            <Icon name={p.folderProblem === undefined ? "folder" : "folder-alert"} size={16} />
            <strong className="tp-folder-name ac-ellipsis" title={p.project.name}>{p.project.name}</strong>
            <MiddleEllipsis value={p.project.dir} head={14} tail={20} className="tp-folder-dir" />
          </>
        )}
        {p.projects.length > 1 ? (
          <MenuPopover
            label={m.folder.changeLabel}
            triggerLabel={m.folder.changeLabel}
            triggerClassName="tp-change"
            items={p.projects.map((x) => ({ id: x.id, label: x.name, title: x.dir, onSelect: () => p.onProjectChange(x.id) }))}
          >
            {m.folder.change}
          </MenuPopover>
        ) : null}
      </div>
      {p.folderProblem === undefined ? null : (
        <p className="tp-problem" data-tone={p.folderProblem.tone} role="status">
          {p.folderProblem.text}
          {p.onRepath === undefined ? null : <> <button type="button" className="app-link-btn" onClick={p.onRepath}>{m.folder.repath}</button></>}
        </p>
      )}
      {p.switchesCurrent === true && p.project !== undefined ? <p className="tp-switch app-muted">{m.folder.willSwitch(p.project.name)}</p> : null}

      <div className="tp-config">
        <span className="tp-label app-muted">{m.config.label}</span>
        <div className="tp-config-body">
          {showSearch ? (
            <input type="search" className="ac-input" aria-label={m.config.search} placeholder={m.config.searchPlaceholder} value={query} onChange={(e) => setQuery(e.target.value)} />
          ) : null}
          {p.loading ? (
            <p className="app-muted" role="status">{m.config.loading}</p>
          ) : p.error ? (
            <Banner tone="danger">
              {m.config.loadFailed}{" "}
              {p.onRetry === undefined ? null : <Button size="sm" variant="ghost" onClick={p.onRetry}>{m.config.retry}</Button>}
            </Banner>
          ) : p.options.length === 0 ? (
            <EmptyState
              title={m.config.emptyTitle}
              action={
                <div className="tp-empty-actions">
                  {importRow(true)}
                  {p.createHref === undefined ? null : <Link to={p.createHref} onClick={p.onNavigate}>{m.config.createHere}</Link>}
                </div>
              }
            />
          ) : (
            <>
              {filtered.length === 0 ? <p className="app-muted">{m.config.noMatches}</p> : null}
              <ul ref={list} role="radiogroup" aria-label={p.listLabel ?? m.config.list} className="tp-list" onKeyDown={move}>
                {filtered.map((o) => {
                  const ok = usable(o);
                  return (
                    <li key={o.id} role="presentation" className="tp-item" data-selected={picked === o.id ? "true" : undefined} data-disabled={ok ? undefined : "true"}>
                      <div
                        role="radio"
                        aria-checked={picked === o.id}
                        aria-disabled={ok ? undefined : true}
                        data-option-id={o.id}
                        tabIndex={o.id === tabStop ? 0 : -1}
                        className="tp-row"
                        onClick={() => ok && p.onChange(o.id)}
                        onKeyDown={(e) => {
                          if (e.target !== e.currentTarget || e.ctrlKey || e.metaKey || e.altKey) return;
                          if (e.key === " " || e.key === "Enter") {
                            e.preventDefault();
                            if (ok) p.onChange(o.id);
                            else if (e.key === "Enter" && o.expanded !== undefined) toggle(o.id);
                          } else if ((e.key === "e" || e.key === "E") && p.onEdit !== undefined) {
                            e.preventDefault();
                            p.onEdit(o);
                          }
                        }}
                      >
                        <strong className="ac-ellipsis" title={o.name}>{o.name}</strong>
                        {o.description ? <span className="app-muted ac-ellipsis">{o.description}</span> : null}
                        {o.meta ? <span className="app-muted tp-meta">{o.meta}</span> : null}
                      </div>
                      {o.reason !== undefined || o.editHref !== undefined || o.expanded !== undefined ? (
                        <div className="tp-reason" data-blocked={ok ? undefined : "true"}>
                          {o.reason}
                          {o.expanded === undefined ? null : (
                            <button type="button" className="app-link-btn" aria-expanded={expanded.has(o.id)} aria-controls={`${uid}-x-${o.id}`} onClick={() => toggle(o.id)}>
                              {expanded.has(o.id) ? m.config.hideIssues : m.config.showIssues} {expanded.has(o.id) ? "▴" : "▾"}
                            </button>
                          )}
                          {!ok && o.editHref !== undefined ? <Link to={o.editHref} onClick={p.onNavigate}>{m.config.editConfig}</Link> : null}
                        </div>
                      ) : null}
                      {o.expanded !== undefined && expanded.has(o.id) ? <div id={`${uid}-x-${o.id}`}>{o.expanded}</div> : null}
                    </li>
                  );
                })}
              </ul>
              <div className="tp-import-row">{importRow(false)}</div>
            </>
          )}
        </div>
      </div>
      {p.children}
    </div>
  );
}
