import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { Project } from "@agent-console/contracts/projects";
import { Button, Icon, Popover } from "@agent-console/ui";
import type { CurrentProject } from "@agent-console/projects";
import { projectMessages as t } from "./messages";

export interface ProjectSwitcherProps {
  projects: readonly Project[];
  /** 현재 프로젝트 id. null = 모든 프로젝트 */
  current: CurrentProject;
  onSelect: (id: CurrentProject) => void;
  /** [+ 새 프로젝트…] (프로젝트가 0개일 때는 유일한 버튼) */
  onCreate: () => void;
  /** [관리…]. 없으면 버튼을 그리지 않는다 */
  onManage?: (() => void) | undefined;
  /** 접힘 레일(이니셜 타일) */
  collapsed?: boolean;
  /** 트리거 툴팁·이름에 덧붙일 단축키 표기 */
  shortcutHint?: string | undefined;
  /** 제어형 열림(단축키·팔레트로 열기). 없으면 내부 상태 */
  open?: boolean | undefined;
  onOpenChange?: ((open: boolean) => void) | undefined;
}

/** 이니셜 한 글자(이름의 첫 글자, 비면 id). */
function initialOf(project: Project | undefined): string {
  const source = (project?.name ?? "").trim() || project?.id || "";
  return Array.from(source)[0]?.toUpperCase() ?? "?";
}

/**
 * 프로젝트 전환기(표현 전용): 트리거 + 검색 + 목록 + [+ 새 프로젝트…]·[관리…].
 * 데이터와 콜백은 props다. 프로젝트가 0개면 [프로젝트 만들기] 버튼 하나만 그린다.
 * 키보드: 트리거 ↓ 또는 Enter로 열기, 목록 ↑↓·Home·End 이동, Enter 선택, Esc 닫기(트리거로 포커스 복귀).
 */
export function ProjectSwitcher({ projects, current, onSelect, onCreate, onManage, collapsed = false, shortcutHint, open: openProp, onOpenChange }: ProjectSwitcherProps) {
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = (next: boolean) => {
    setOpenState(next);
    onOpenChange?.(next);
  };
  const [query, setQuery] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const searchId = useId();
  const currentProject = current === null ? undefined : projects.find((p) => p.id === current);
  const currentName = current === null ? t.switcher.all : (currentProject?.name ?? current);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return projects.filter((p) => q === "" || `${p.name} ${p.id}`.toLowerCase().includes(q));
  }, [projects, query]);
  const showAll = query.trim() === "" || t.switcher.all.includes(query.trim());

  if (projects.length === 0) {
    return (
      <div className="prj-switcher" data-collapsed={collapsed ? "true" : "false"} data-empty="true">
        <Button size="sm" variant="ghost" onClick={onCreate} title={t.switcher.createFirstHint} aria-label={t.switcher.createFirst}>
          <Icon name="plus" size={14} />
          <span className="prj-label">{t.switcher.createFirst}</span>
        </Button>
      </div>
    );
  }

  const options = () => Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);
  const onListKey = (e: KeyboardEvent<HTMLElement>) => {
    const items = options();
    const i = items.indexOf(document.activeElement as HTMLElement);
    let next: number | undefined;
    if (e.key === "ArrowDown") next = i < 0 ? 0 : Math.min(items.length - 1, i + 1);
    else if (e.key === "ArrowUp") next = i <= 0 ? 0 : i - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    if (next === undefined) return;
    e.preventDefault();
    items[next]?.focus();
  };
  const choose = (id: CurrentProject, close: () => void) => {
    onSelect(id);
    setQuery("");
    close();
  };
  const triggerLabel = t.switcher.triggerLabel(currentName, shortcutHint);

  return (
    <div className="prj-switcher" data-collapsed={collapsed ? "true" : "false"}>
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setQuery("");
        }}
        panelLabel={t.switcher.region}
        panelClassName="prj-panel"
        className="prj-pop"
        renderTrigger={(p) => (
          <button type="button" {...p} className="prj-trigger" aria-label={triggerLabel} title={triggerLabel} data-all={current === null ? "true" : "false"}>
            {collapsed ? (
              <span className="prj-tile" aria-hidden="true">{current === null ? <Icon name="projects" size={14} /> : initialOf(currentProject)}</span>
            ) : (
              <>
                <span className="prj-kicker">{t.switcher.label}</span>
                <span className="prj-name ac-ellipsis">{currentName}</span>
                <Icon name="chevron-down" size={12} />
              </>
            )}
          </button>
        )}
      >
        {({ close }) => (
          <div className="prj-body" onKeyDown={onListKey}>
            {projects.length > 5 ? (
              <input
                id={searchId}
                type="search"
                className="ac-input prj-search"
                aria-label={t.switcher.search}
                placeholder={t.switcher.searchPlaceholder}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    options()[0]?.focus();
                  }
                }}
              />
            ) : null}
            <div ref={listRef} role="listbox" aria-label={t.switcher.listLabel} className="prj-list">
              {showAll ? (
                <button type="button" role="option" aria-selected={current === null} className="prj-option" onClick={() => choose(null, close)} title={t.switcher.allHint}>
                  <span className="prj-option-name ac-ellipsis">{t.switcher.all}</span>
                  {current === null ? <span aria-hidden="true">✓</span> : null}
                </button>
              ) : null}
              {rows.map((p) => (
                <button key={p.id} type="button" role="option" aria-selected={current === p.id} className="prj-option" onClick={() => choose(p.id, close)} title={p.description || p.name}>
                  <span className="prj-option-name ac-ellipsis">{p.name}</span>
                  {current === p.id ? <span aria-hidden="true">✓</span> : null}
                </button>
              ))}
              {rows.length === 0 && !showAll ? <p className="app-muted prj-empty">{t.switcher.noMatch}</p> : null}
            </div>
            <div className="prj-foot">
              <Button size="sm" variant="ghost" onClick={() => { close(); onCreate(); }}>{t.switcher.newProject}</Button>
              {onManage === undefined ? null : <Button size="sm" variant="ghost" onClick={() => { close(); onManage(); }}>{t.switcher.manage}</Button>}
            </div>
          </div>
        )}
      </Popover>
    </div>
  );
}
