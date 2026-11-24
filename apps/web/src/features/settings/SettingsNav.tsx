import type { KeyboardEvent, ReactNode, RefObject } from "react";
import { Icon } from "@agent-console/ui";
import { messages as m } from "../../app/messages";

/** 목록 한 줄. 어느 섹션이 있는지는 부모가 정해 주며, 이 컴포넌트는 섹션 id·이름을 모른다. */
export interface NavItem {
  id: string;
  title: string;
  /** 제목 뒤에 붙는 표시(오류·변경 점 등) */
  marks?: ReactNode;
}
export interface NavGroup {
  group: string;
  title: string;
  items: readonly NavItem[];
}

export interface SettingsNavProps {
  groups: readonly NavGroup[];
  active: string;
  onPick: (id: string) => void;
  query: string;
  onQueryChange: (q: string) => void;
  searchRef: RefObject<HTMLInputElement | null>;
  /** 접힌 묶음 id */
  collapsed: ReadonlySet<string>;
  onToggleGroup: (group: string) => void;
  /** 좁은 폭: 목록 대신 드롭다운 */
  narrow: boolean;
}

/** 섹션 목록의 검색 칸. `Esc`로 비우고 `Enter`는 첫 일치 섹션으로 간다. */
function SearchBox({ query, onQueryChange, searchRef, onEnter }: Pick<SettingsNavProps, "query" | "onQueryChange" | "searchRef"> & { onEnter: () => void }) {
  const t = m.settings.nav;
  return (
    <div className="app-settings-search">
      <input
        ref={searchRef}
        type="search"
        className="ac-input"
        aria-label={t.searchLabel}
        placeholder={t.searchPlaceholder}
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && query !== "") {
            e.preventDefault();
            e.stopPropagation();
            onQueryChange("");
          } else if (e.key === "Enter") {
            e.preventDefault();
            onEnter();
          }
        }}
      />
      {query === "" ? <kbd className="app-settings-search-key" aria-hidden="true">{t.searchHint}</kbd> : null}
    </div>
  );
}

/** 설정 섹션 목록(검색 + 묶음 접기). 폭이 좁으면 같은 데이터를 드롭다운으로 그린다. */
export function SettingsNav({ groups, active, onPick, query, onQueryChange, searchRef, collapsed, onToggleGroup, narrow }: SettingsNavProps) {
  const t = m.settings.nav;
  const searching = query.trim() !== "";
  const first = groups[0]?.items[0];
  const search = <SearchBox query={query} onQueryChange={onQueryChange} searchRef={searchRef} onEnter={() => first && onPick(first.id)} />;
  const none = groups.length === 0 ? <p className="app-muted app-settings-nomatch" role="status">{t.noMatch}</p> : null;

  const onNavKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const links = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("a"));
    const i = links.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    links[(i + (e.key === "ArrowDown" ? 1 : -1) + links.length) % links.length]?.focus();
  };

  if (narrow) {
    // 현재 섹션은 검색에 걸리지 않아도 값으로 남겨 둔다(select 값이 비지 않게).
    return (
      <nav className="app-settings-nav" aria-label={m.settings.sectionNav}>
        <div className="app-settings-navtop">
          {search}
          <select className="ac-input app-settings-picker" aria-label={t.picker} value={active} onChange={(e) => onPick(e.target.value)}>
            {groups.map((g) => (
              <optgroup key={g.group} label={g.title}>
                {g.items.map((it) => <option key={it.id} value={it.id}>{it.title}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
        {none}
      </nav>
    );
  }

  return (
    <nav className="app-settings-nav" aria-label={m.settings.sectionNav} onKeyDown={onNavKey}>
      <div className="app-settings-navtop">{search}</div>
      {none}
      {groups.map((g) => {
        // 현재 섹션이 든 묶음과 검색에 걸린 묶음은 늘 펼친다.
        const open = searching || g.items.some((it) => it.id === active) || !collapsed.has(g.group);
        const locked = searching || g.items.some((it) => it.id === active);
        return (
          <div key={g.group} className="app-settings-navgroup">
            <h3 id={`settings-group-${g.group}`} className="app-settings-grouptitle">
              <button
                type="button"
                className="app-settings-grouptoggle"
                data-open={open ? "true" : "false"}
                aria-expanded={open}
                aria-controls={`settings-group-list-${g.group}`}
                aria-disabled={locked ? "true" : undefined}
                title={locked ? undefined : t.groupToggle(g.title, open)}
                onClick={() => {
                  if (!locked) onToggleGroup(g.group);
                }}
              >
                <Icon name="chevron-down" size={12} className="app-settings-chev" />
                {g.title}
              </button>
            </h3>
            <ul id={`settings-group-list-${g.group}`} aria-labelledby={`settings-group-${g.group}`} hidden={!open}>
              {g.items.map((it) => (
                <li key={it.id}>
                  <a
                    href={`#${it.id}`}
                    aria-current={active === it.id ? "location" : undefined}
                    onClick={(e) => {
                      e.preventDefault();
                      onPick(it.id);
                    }}
                  >
                    {it.title}
                    {it.marks}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
