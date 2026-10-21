import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useModalBackdrop } from "./modal";

export interface CommandItem {
  id: string;
  label: string;
  /** 보조 설명(오른쪽 흐린 글씨). */
  hint?: string;
  /** 앞 아이콘 슬롯. 이름으로 그리려면 호출자가 `<Icon name=…/>`을 넘긴다. */
  icon?: ReactNode;
  /** 칩 등 배지 슬롯(예: "응답 대기"). */
  badge?: ReactNode;
  /** 표시용 단축키 문자열(예: `formatKeyCombo` 결과). 키 바인딩 자체는 호출자 몫이다. */
  shortcut?: string;
  disabled?: boolean;
  /** 선택(Enter/클릭) 시 실행. 팔레트는 먼저 닫은 뒤 호출한다. */
  run: () => void;
}

export interface CommandGroup {
  id: string;
  title: string;
  items: readonly CommandItem[];
}

export interface CommandPaletteMessages {
  /** 다이얼로그 접근성 이름 */
  title: string;
  inputLabel: string;
  placeholder?: string;
  /** 결과가 하나도 없을 때 */
  empty: string;
  /** 그룹 로딩 중 한 줄 */
  loading: string;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  /** 이미 필터된 결과. 필터·원격 검색은 호출자가 한다(`filterCommandGroups` 참고). */
  groups: readonly CommandGroup[];
  query: string;
  onQueryChange: (query: string) => void;
  /** 그룹별 로딩 상태. true인 그룹은 항목 아래에 로딩 줄이 보인다. */
  loading?: Readonly<Record<string, boolean>>;
  messages: CommandPaletteMessages;
}

/** 부분 일치(대소문자 무시) 필터. 항목이 없어진 그룹은 뺀다. `maxPerGroup`로 그룹당 개수를 제한한다. */
export function filterCommandGroups(groups: readonly CommandGroup[], query: string, maxPerGroup?: number): CommandGroup[] {
  const q = query.trim().toLowerCase();
  const out: CommandGroup[] = [];
  for (const group of groups) {
    const matched = q === "" ? group.items : group.items.filter((i) => i.label.toLowerCase().includes(q) || (i.hint?.toLowerCase().includes(q) ?? false));
    const items = maxPerGroup === undefined ? matched : matched.slice(0, maxPerGroup);
    if (items.length > 0) out.push({ ...group, items });
  }
  return out;
}

/**
 * 명령 팔레트(빠른 이동). 항목·그룹은 전부 호출자 데이터이며 도메인을 모른다.
 * `role=combobox` 입력 + `listbox`, `↑↓` 이동, `Enter` 실행, `Esc` 닫기. 한글 조합(IME) 중의 Enter·방향키는 무시한다.
 * 여는 키는 `useKeyCombo`로 호출자가 연결한다.
 */
export function CommandPalette({ open, onClose, groups, query, onQueryChange, loading, messages }: CommandPaletteProps) {
  const base = useId();
  const backdropRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const composing = useRef(false);
  const [activeIndex, setActiveIndex] = useState(0);

  useModalBackdrop(open, backdropRef);

  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const enabledIndexes = useMemo(() => flat.map((item, i) => (item.disabled === true ? -1 : i)).filter((i) => i >= 0), [flat]);
  const clamped = Math.min(activeIndex, Math.max(0, flat.length - 1));
  // 비활성 항목에 놓였으면(첫 항목이 비활성 등) 첫 활성 항목으로
  const active = enabledIndexes.includes(clamped) ? clamped : (enabledIndexes[0] ?? clamped);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);
  // 검색어·결과가 바뀌면 첫 항목으로
  const [seen, setSeen] = useState({ query, open });
  if (seen.query !== query || seen.open !== open) {
    setSeen({ query, open });
    setActiveIndex(0);
  }
  useEffect(() => {
    if (!open) return;
    document.getElementById(`${base}-opt-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open, base]);

  if (!open) return null;

  const isComposing = (event: KeyboardEvent) => composing.current || event.nativeEvent.isComposing || event.keyCode === 229;

  const runItem = (item: CommandItem | undefined) => {
    if (item === undefined || item.disabled === true) return;
    onClose();
    item.run();
  };

  const step = (delta: number) => {
    if (enabledIndexes.length === 0) return;
    const pos = enabledIndexes.indexOf(active);
    const next = enabledIndexes[(pos + delta + enabledIndexes.length) % enabledIndexes.length];
    if (next !== undefined) setActiveIndex(next);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "Tab") {
      // 포커스는 입력에 머문다(목록 항목은 aria-activedescendant로 가리킨다).
      event.preventDefault();
      return;
    }
    if (isComposing(event)) return; // 조합 중 Enter는 글자 확정이다
    if (event.key === "ArrowDown") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      runItem(flat[active]);
    }
  };

  const starts = groups.reduce<number[]>((acc, g, i) => [...acc, i === 0 ? 0 : acc[i - 1]! + groups[i - 1]!.items.length], []);
  const hasLoading = loading !== undefined && Object.values(loading).some(Boolean);
  const listId = `${base}-list`;

  return createPortal(
    <div
      ref={backdropRef}
      className="ac-dialog-backdrop ac-palette-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div role="dialog" aria-modal="true" aria-label={messages.title} className="ac-palette" onKeyDown={onKeyDown}>
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={flat.length > 0 ? `${base}-opt-${active}` : undefined}
          aria-label={messages.inputLabel}
          placeholder={messages.placeholder}
          autoComplete="off"
          spellCheck={false}
          className="ac-palette-input"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            // 일부 브라우저는 compositionend가 확정 Enter keydown보다 먼저 와서, 한 틱 늦게 푼다.
            setTimeout(() => {
              composing.current = false;
            }, 0);
          }}
        />
        <div id={listId} role="listbox" aria-label={messages.title} aria-busy={hasLoading || undefined} className="ac-palette-list">
          {groups.map((group, groupIndex) => {
            const start = starts[groupIndex]!;
            const titleId = `${base}-g-${group.id}`;
            return (
              <div key={group.id} role="group" aria-labelledby={titleId} className="ac-palette-group">
                <div id={titleId} className="ac-palette-group-title" role="presentation">{group.title}</div>
                {group.items.map((item, i) => {
                  const index = start + i;
                  const isActive = index === active;
                  return (
                    <div
                      key={item.id}
                      id={`${base}-opt-${index}`}
                      role="option"
                      aria-selected={isActive}
                      aria-disabled={item.disabled || undefined}
                      data-active={isActive ? "true" : undefined}
                      className="ac-palette-item"
                      onMouseMove={() => {
                        if (!isActive && item.disabled !== true) setActiveIndex(index);
                      }}
                      onClick={() => runItem(item)}
                    >
                      {item.icon === undefined ? null : <span className="ac-palette-icon" aria-hidden="true">{item.icon}</span>}
                      <span className="ac-palette-label ac-ellipsis">{item.label}</span>
                      {item.badge === undefined ? null : <span className="ac-palette-badge">{item.badge}</span>}
                      {item.hint === undefined ? null : <span className="ac-palette-hint ac-ellipsis">{item.hint}</span>}
                      {item.shortcut === undefined ? null : <kbd className="ac-palette-kbd">{item.shortcut}</kbd>}
                    </div>
                  );
                })}
                {loading?.[group.id] === true ? <div className="ac-palette-loading" role="presentation">{messages.loading}</div> : null}
              </div>
            );
          })}
          {/* 항목이 아직 없는 로딩 그룹 */}
          {Object.entries(loading ?? {})
            .filter(([id, on]) => on && !groups.some((g) => g.id === id))
            .map(([id]) => (
              <div key={id} className="ac-palette-loading" role="presentation">{messages.loading}</div>
            ))}
          {flat.length === 0 && !hasLoading ? <div className="ac-palette-empty" role="presentation">{messages.empty}</div> : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
