import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Icon } from "./Icon";
import { Menu, Popover } from "./Popover";
import { joinClass } from "./Status";
import { useOverflowFit } from "./useOverflowFit";

export interface TabItem {
  id: string;
  label: ReactNode;
  content: ReactNode;
  disabled?: boolean;
  /** 전체 이름 툴팁(탭이 말줄임될 때). 라벨이 문자열이면 기본값이 라벨이다. */
  title?: string;
}

export interface TabsProps {
  tabs: readonly TabItem[];
  /** 제어형 선택 id. 생략하면 비제어(첫 탭). */
  activeId?: string;
  onChange?: (id: string) => void;
  /** tablist 접근성 이름. */
  ariaLabel: string;
  /** true면 한 번도 선택되지 않은 탭 내용은 렌더하지 않는다(선택 후에는 유지). */
  lazy?: boolean;
  className?: string;
  /** 넘친 탭을 담는 메뉴 버튼의 이름. 기본 "더 보기". */
  moreLabel?: string;
}

/**
 * 탭: `role=tablist`, `←→ Home End` 이동(자동 활성화). 탭 목록은 호출자 데이터.
 * 한 줄에 다 안 들어가면 넘친 탭을 오른쪽 끝 "더 보기 ▾" 메뉴로 보낸다(가로 스크롤 없음). 활성 탭은 항상 보이는 쪽이다.
 */
export function Tabs({ tabs, activeId, onChange, ariaLabel, lazy = false, className, moreLabel = "더 보기" }: TabsProps) {
  const base = useId();
  const [inner, setInner] = useState<string | undefined>(undefined);
  const [visited, setVisited] = useState<ReadonlySet<string>>(new Set());
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const current = activeId ?? inner ?? tabs.find((t) => !t.disabled)?.id;
  const [menuOpen, setMenuOpen] = useState(false);
  const pendingFocus = useRef<string | undefined>(undefined);
  const { rootRef, moreRef, itemRef, hidden } = useOverflowFit({
    keys: tabs.map((t) => t.id),
    priorityKeys: current === undefined ? [] : [current],
    gap: 4,
    fallbackMoreWidth: 88,
  });
  const hiddenTabs = tabs.filter((t) => hidden.has(t.id));
  useEffect(() => {
    // 넘친 탭을 고르면 승격된 뒤에 포커스를 준다.
    const id = pendingFocus.current;
    if (id !== undefined && !hidden.has(id)) {
      pendingFocus.current = undefined;
      refs.current.get(id)?.focus();
    }
  });

  const select = (id: string) => {
    setVisited((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
    if (activeId === undefined) setInner(id);
    onChange?.(id);
    pendingFocus.current = id;
    refs.current.get(id)?.focus();
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const enabled = tabs.filter((t) => !t.disabled);
    const index = enabled.findIndex((t) => t.id === current);
    let next: number | undefined;
    if (event.key === "ArrowRight") next = (index + 1) % enabled.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + enabled.length) % enabled.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = enabled.length - 1;
    if (next === undefined || enabled.length === 0) return;
    event.preventDefault();
    select(enabled[next]!.id);
  };

  return (
    <div className={joinClass("ac-tabs", className)}>
      <div ref={rootRef} className="ac-tabs-bar">
        <div role="tablist" aria-label={ariaLabel} className="ac-tabs-list" onKeyDown={onKeyDown}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              ref={(el) => {
                itemRef(tab.id)(el);
                if (el) refs.current.set(tab.id, el);
                else refs.current.delete(tab.id);
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${tab.id}`}
              aria-selected={tab.id === current}
              aria-controls={`${base}-panel-${tab.id}`}
              tabIndex={tab.id === current ? 0 : -1}
              disabled={tab.disabled}
              title={tab.title ?? (typeof tab.label === "string" ? tab.label : undefined)}
              className="ac-tab"
              data-hidden={hidden.has(tab.id) ? "true" : undefined}
              onClick={() => select(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {hiddenTabs.length === 0 ? null : (
          <span ref={moreRef} className="ac-tabs-more">
            <Popover
              open={menuOpen}
              onOpenChange={setMenuOpen}
              panelRole="menu"
              panelLabel={moreLabel}
              align="end"
              renderTrigger={(props) => (
                <button {...props} type="button" className="ac-tab ac-tab-more">
                  <span>{moreLabel}</span>
                  <Icon name="chevron-down" size={12} />
                </button>
              )}
            >
              {({ close }) => (
                <Menu
                  onClose={close}
                  items={hiddenTabs.map((t) => ({
                    id: t.id,
                    label: t.label,
                    title: t.title,
                    disabled: t.disabled,
                    onSelect: () => select(t.id),
                  }))}
                />
              )}
            </Popover>
          </span>
        )}
      </div>
      {tabs.map((tab) => {
        const active = tab.id === current;
        const render = !lazy || active || visited.has(tab.id);
        return (
          <div key={tab.id} role="tabpanel" id={`${base}-panel-${tab.id}`} aria-labelledby={`${base}-tab-${tab.id}`} hidden={!active} className="ac-tab-panel">
            {render ? tab.content : null}
          </div>
        );
      })}
    </div>
  );
}
