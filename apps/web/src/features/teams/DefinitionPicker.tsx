import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "@agent-console/ui";
import { teamMessages as t } from "./messages";

export interface DefinitionPickItem {
  id: string;
  name: string;
  /** 이름 옆 muted(역할·종류 등) */
  description?: string | undefined;
  /** 이미 팀에 있는 개수(0이면 칩 없음) */
  usageCount?: number | undefined;
  /** 묶음 키(`groups`에 있는 값). 없으면 묶음 없음 */
  group?: string | undefined;
  /** 이름 뒤에 붙는 태그(프로젝트 태그 등) */
  tag?: ReactNode;
  disabled?: boolean | undefined;
}

export interface DefinitionPickerGroup {
  key: string;
  label: string;
}

export interface DefinitionPickerProps {
  /** 목록의 접근성 이름(정의 종류 표시 이름) */
  label: string;
  items: readonly DefinitionPickItem[];
  /** 최근에 고른 id(가장 최근이 앞). 이 항목들이 먼저 나온다 */
  recentIds?: readonly string[];
  /** 묶음 소제목 순서. 비우면 묶음을 그리지 않는다 */
  groups?: readonly DefinitionPickerGroup[];
  onPick: (item: DefinitionPickItem) => void;
  /** 있으면 목록 아래에 [새로 만들기…] */
  onCreate?: () => void;
  /** 검색창 아래 줄에 끼울 내용(붙일 곳 라디오 등) */
  footer?: ReactNode;
}

/** 최근 사용을 앞으로, 나머지는 이름 순(한국어). 검색어는 이름·설명·id 부분 일치. */
export function sortPickItems(items: readonly DefinitionPickItem[], recentIds: readonly string[], query: string): DefinitionPickItem[] {
  const q = query.trim().toLowerCase();
  const rank = new Map(recentIds.map((id, i) => [id, i]));
  return items
    .filter((it) => q === "" || `${it.name} ${it.description ?? ""} ${it.id}`.toLowerCase().includes(q))
    .sort((a, b) => {
      const ra = rank.get(a.id);
      const rb = rank.get(b.id);
      if (ra !== undefined || rb !== undefined) return (ra ?? Infinity) - (rb ?? Infinity);
      return a.name.localeCompare(b.name, "ko");
    });
}

/**
 * 정의 고르기 목록(팝오버 안 내용, 폭 360): 검색(자동 포커스) + 목록 + 최근 사용 먼저 + 묶음 소제목.
 * ↑↓ 이동, Enter 추가. Esc는 감싼 팝오버가 닫는다. 정의 종류를 모른다(항목과 문구는 호출자가 준다).
 */
export function DefinitionPicker({ label, items, recentIds = [], groups, onPick, onCreate, footer }: DefinitionPickerProps) {
  const uid = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  const sorted = useMemo(() => sortPickItems(items, recentIds, query), [items, recentIds, query]);
  const rows = useMemo(() => {
    if (groups === undefined || groups.length === 0) return [{ key: "", label: "", items: sorted }];
    const out = groups.map((g) => ({ key: g.key, label: g.label, items: sorted.filter((it) => it.group === g.key) }));
    const known = new Set(groups.map((g) => g.key));
    const rest = sorted.filter((it) => it.group === undefined || !known.has(it.group));
    return [...out.filter((g) => g.items.length > 0), ...(rest.length > 0 ? [{ key: "", label: "", items: rest }] : [])];
  }, [sorted, groups]);
  const flat = rows.flatMap((g) => g.items);
  const current = Math.min(active, Math.max(0, flat.length - 1));
  const optionId = (id: string) => `${uid}-opt-${id}`;

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (flat.length === 0) return;
      const next = (current + (e.key === "ArrowDown" ? 1 : -1) + flat.length) % flat.length;
      setActive(next);
      const id = flat[next]?.id;
      if (id !== undefined) document.getElementById(optionId(id))?.scrollIntoView?.({ block: "nearest" });
    } else if (e.key === "Enter") {
      const item = flat[current];
      if (item !== undefined && item.disabled !== true && (e.target as HTMLElement).tagName !== "BUTTON") {
        e.preventDefault();
        onPick(item);
      }
    }
  };

  return (
    <div className="team-picker" onKeyDown={onKeyDown}>
      <input
        type="search"
        className="ac-input"
        aria-label={t.add.pickerSearch}
        placeholder={t.add.pickerSearch}
        role="combobox"
        aria-expanded="true"
        aria-controls={`${uid}-list`}
        aria-activedescendant={flat[current] === undefined ? undefined : optionId(flat[current].id)}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
        }}
        autoFocus
      />
      {footer}
      {items.length === 0 ? (
        <p className="app-muted team-picker-empty">{t.add.pickerEmpty}</p>
      ) : flat.length === 0 ? (
        <p className="app-muted team-picker-empty" role="status">{t.add.pickerNoMatch}</p>
      ) : (
        <ul ref={listRef} id={`${uid}-list`} role="listbox" aria-label={label} className="team-picker-list">
          {rows.map((g) => (
            <li key={g.key || "_"} role="presentation" className="team-picker-group">
              {g.label ? <div className="team-picker-group-title app-muted" role="presentation">{g.label}</div> : null}
              <ul role="presentation" className="team-picker-rows">
                {g.items.map((it) => (
                  <li
                    key={it.id}
                    id={optionId(it.id)}
                    role="option"
                    aria-selected={flat[current]?.id === it.id}
                    aria-disabled={it.disabled === true ? true : undefined}
                    className="team-picker-row"
                    data-active={flat[current]?.id === it.id ? "true" : undefined}
                    onMouseMove={() => setActive(flat.findIndex((x) => x.id === it.id))}
                    onClick={() => {
                      if (it.disabled !== true) onPick(it);
                    }}
                  >
                    <span className="team-picker-name ac-ellipsis" title={it.name}>{it.name || it.id}</span>
                    {it.description ? <span className="app-muted team-picker-desc ac-ellipsis" title={it.description}>{it.description}</span> : null}
                    {it.tag}
                    {it.usageCount !== undefined && it.usageCount > 0 ? <span className="team-picker-chip">{t.add.already(it.usageCount)}</span> : null}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {onCreate === undefined ? null : (
        <div className="team-picker-foot">
          <Button size="sm" onClick={onCreate}>{t.add.pickerCreate}</Button>
        </div>
      )}
    </div>
  );
}
