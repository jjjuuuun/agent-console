import { useId, useState, type KeyboardEvent, type ReactNode } from "react";
import { MiddleEllipsisPath } from "@agent-console/folder-picker";
import { Button, Icon, Popover } from "@agent-console/ui";
import { projectMessages as t } from "./messages";
import { projectInitial } from "./projectRegionLib";

/** 영역이 그리는 프로젝트 한 줄에 필요한 값(계약 `Project`의 부분집합이라 어떤 출처도 넣을 수 있다). */
export interface RegionProject {
  id: string;
  name: string;
  /** 로컬 폴더 절대 경로. null/빈 값 = 폴더 미지정 */
  folder: string | null;
}

export interface ProjectRegionProps {
  projects: readonly RegionProject[];
  /** 현재 프로젝트 id(없으면 null) */
  currentId: string | null;
  /** 접힘 레일(사이드바가 접힘): 이니셜 배지 버튼 + 팝오버 */
  rail?: boolean;
  /** 영역 접힘(펼침 모양에서만) */
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  onSelect: (id: string) => void;
  /** [+ 폴더 추가] */
  onAdd: () => void;
  /** 첫 조회 중이며 200ms가 지났을 때만 true로 넘긴다(스켈레톤) */
  loadingSlow?: boolean;
  /** 조회 오류 */
  error?: boolean;
  onRetry?: () => void;
  /** 제어형 레일 팝오버(단축키로 열기). 없으면 내부 상태 */
  railOpen?: boolean | undefined;
  onRailOpenChange?: ((open: boolean) => void) | undefined;
}

function RowIcon() {
  return <Icon name="projects" size={16} />;
}

function Row({ project, current, onSelect, popover }: { project: RegionProject; current: boolean; onSelect: () => void; popover?: boolean }) {
  const path = project.folder ?? "";
  const unset = path === "";
  return (
    <button
      type="button"
      className="prj-row"
      role={popover ? "menuitemradio" : undefined}
      aria-checked={popover ? current : undefined}
      aria-current={popover ? undefined : current ? "true" : undefined}
      data-current={current ? "true" : undefined}
      title={t.region.rowTitle(project.name, path)}
      onClick={onSelect}
    >
      <span className="prj-row-icon" aria-hidden="true"><RowIcon /></span>
      <span className="prj-row-text">
        <span className="prj-row-name ac-ellipsis">{project.name}</span>
        {unset ? <span className="prj-row-path" data-unset="true">{t.region.folderUnset}</span> : <MiddleEllipsisPath path={path} className="prj-row-path" />}
      </span>
    </button>
  );
}

/** 목록 키보드: ↑↓·Home·End로 같은 목록(이벤트가 붙은 요소) 안의 항목 사이 이동. */
function listKeyDown(e: KeyboardEvent<HTMLElement>) {
  const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>(".prj-row"));
  const i = items.indexOf(document.activeElement as HTMLElement);
  let next: number | undefined;
  if (e.key === "ArrowDown") next = i < 0 ? 0 : Math.min(items.length - 1, i + 1);
  else if (e.key === "ArrowUp") next = i <= 0 ? 0 : i - 1;
  else if (e.key === "Home") next = 0;
  else if (e.key === "End") next = items.length - 1;
  if (next === undefined) return;
  e.preventDefault();
  items[next]?.focus();
}

/**
 * 사이드바 프로젝트 영역(표현 전용, 명세 screen-projects §2). 데이터·콜백은 props다.
 * 펼침: 접기 머리(현재 이름 굵게) + 두 줄 항목(이름·가운데 줄인 경로) + [+ 폴더 추가].
 * 레일: 이니셜 배지 버튼 + 팝오버. 영역을 그릴지(역할 유무)는 호출한 쪽이 정한다.
 */
export function ProjectRegion(p: ProjectRegionProps) {
  const headId = useId();
  const listId = useId();
  const current = p.projects.find((x) => x.id === p.currentId);
  const [railState, setRailState] = useState(false);
  const railOpen = p.railOpen ?? railState;
  const setRailOpen = (open: boolean) => {
    setRailState(open);
    p.onRailOpenChange?.(open);
  };

  if (p.rail) {
    return (
      <section className="prj-region" data-rail="true" aria-label={t.region.label}>
        <Popover
          open={railOpen}
          onOpenChange={setRailOpen}
          panelRole="menu"
          panelLabel={t.region.railMenuLabel}
          panelClassName="prj-rail-panel"
          className="prj-rail-pop"
          renderTrigger={(tp) => (
            <button type="button" {...tp} className="prj-rail-btn" aria-label={t.region.railLabel(current?.name)} title={t.region.railLabel(current?.name)}>
              <Icon name="projects" size={18} />
              {current === undefined ? null : <span className="prj-badge" aria-hidden="true">{projectInitial(current.name)}</span>}
            </button>
          )}
        >
          {({ close }) => (
            <div className="prj-rail-body" onKeyDown={listKeyDown}>
              <div className="prj-rail-head">{t.region.label}</div>
              {p.projects.map((x) => (
                <Row key={x.id} project={x} current={x.id === p.currentId} popover onSelect={() => { close(); p.onSelect(x.id); }} />
              ))}
              {p.projects.length === 0 ? <p className="prj-note">{t.region.empty}</p> : null}
              <button type="button" role="menuitem" className="prj-add" onClick={() => { close(); p.onAdd(); }}>
                <Icon name="plus" size={14} />
                <span>{t.region.add}</span>
              </button>
            </div>
          )}
        </Popover>
      </section>
    );
  }

  const body: ReactNode = p.error ? (
    <div className="prj-note" data-tone="danger">
      <span>{t.region.loadFailed}</span>
      {p.onRetry === undefined ? null : <Button size="sm" variant="ghost" onClick={p.onRetry}>{t.region.retry}</Button>}
    </div>
  ) : p.loadingSlow ? (
    <div className="prj-skeleton" aria-hidden="true"><span className="app-skeleton-row" /><span className="app-skeleton-row" /></div>
  ) : p.projects.length === 0 ? (
    <>
      <p className="prj-note">{t.region.empty}</p>
      <Button size="sm" variant="secondary" className="prj-add-full" onClick={p.onAdd}>{t.region.add}</Button>
    </>
  ) : (
    <>
      <div className="prj-list" role="list" aria-label={t.region.listLabel} onKeyDown={listKeyDown}>
        {p.projects.map((x) => (
          <div role="listitem" key={x.id}>
            <Row project={x} current={x.id === p.currentId} onSelect={() => p.onSelect(x.id)} />
          </div>
        ))}
      </div>
      <button type="button" className="prj-add" onClick={p.onAdd}>
        <Icon name="plus" size={14} />
        <span>{t.region.add}</span>
      </button>
    </>
  );

  return (
    <section className="prj-region" aria-labelledby={headId} data-collapsed={p.collapsed ? "true" : "false"}>
      <div className="prj-head">
        <button
          type="button"
          className="prj-toggle"
          aria-expanded={!p.collapsed}
          aria-controls={listId}
          title={p.collapsed ? t.region.expand : t.region.collapse}
          onClick={() => p.onCollapsedChange(!p.collapsed)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft" && !p.collapsed) { e.preventDefault(); p.onCollapsedChange(true); }
            else if (e.key === "ArrowRight" && p.collapsed) { e.preventDefault(); p.onCollapsedChange(false); }
          }}
        >
          <span className="prj-chevron" data-open={p.collapsed ? "false" : "true"} aria-hidden="true"><Icon name="chevron-down" size={14} /></span>
          <span id={headId} className="prj-head-label">{t.region.label}</span>
          {current !== undefined ? (
            <>
              <span className="prj-head-dot" aria-hidden="true">·</span>
              <span className="prj-head-name ac-ellipsis" title={current.name}>{current.name}</span>
            </>
          ) : null}
          <span className="prj-head-count ac-num">{p.projects.length}</span>
        </button>
        {p.collapsed ? (
          <button type="button" className="prj-head-add" aria-label={t.region.addLabel} title={t.region.addLabel} onClick={p.onAdd}>
            <Icon name="plus" size={14} />
          </button>
        ) : null}
      </div>
      <div id={listId} className="prj-body-region" hidden={p.collapsed}>{p.collapsed ? null : body}</div>
    </section>
  );
}
