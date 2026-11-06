import { useCallback, useEffect, useImperativeHandle, useRef, type CSSProperties, type KeyboardEventHandler, type ReactNode, type Ref } from "react";
import { useVirtualRows } from "./hooks";

export interface VirtualListHandle {
  /** 행이 보이도록 스크롤한다. */
  scrollToIndex: (index: number) => void;
}

/** 행 하나를 그릴 때 받는 값. `style`은 행 요소에 그대로 단다(위치·높이). */
export interface VirtualRowContext {
  style: CSSProperties;
  index: number;
  /** 접근성: 전체 수와 순번(1부터) — 가상 목록은 DOM에 일부만 있으므로 알려 준다 */
  setSize: number;
  posInSet: number;
}

export interface VirtualListProps<T> {
  items: readonly T[];
  /** 고정 높이 또는 행마다 높이 */
  rowHeight: number | ((item: T, index: number) => number);
  getKey: (item: T, index: number) => string;
  renderRow: (item: T, ctx: VirtualRowContext) => ReactNode;
  ariaLabel: string;
  /** 컨테이너 역할(예: `tree`, `listbox`, `list`, `rowgroup`). 기본 `list` */
  role?: string;
  /** 높이(px 또는 CSS 값). 생략하면 부모를 채운다. */
  height?: number | string;
  maxHeight?: number | string;
  /** 키보드 포커스를 받는 컨테이너(활성 행 방식)일 때 */
  tabIndex?: number;
  activeDescendant?: string | undefined;
  /** 이 행이 보이게 스크롤(활성 행이 바뀔 때) */
  activeIndex?: number | null;
  onKeyDown?: KeyboardEventHandler<HTMLDivElement>;
  onFocus?: () => void;
  ariaMultiselectable?: boolean;
  ariaBusy?: boolean;
  overscan?: number;
  fallbackHeight?: number;
  className?: string;
  handleRef?: Ref<VirtualListHandle>;
}

/**
 * 가상 목록(보이는 행 + 위아래 여유만 DOM에 둔다). 행 모양과 키보드는 호출자가 정한다.
 * 데이터·API를 모른다. `renderRow`가 돌려주는 요소에 `ctx.style`을 달아야 위치가 잡힌다.
 */
export function VirtualList<T>({
  items, rowHeight, getKey, renderRow, ariaLabel, role = "list", height, maxHeight, tabIndex, activeDescendant, activeIndex, onKeyDown, onFocus,
  ariaMultiselectable, ariaBusy, overscan, fallbackHeight, className, handleRef,
}: VirtualListProps<T>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  });
  const heightOf = useCallback(
    (index: number): number => {
      if (typeof rowHeight === "number") return rowHeight;
      const item = itemsRef.current[index] ?? items[index];
      return item === undefined ? 0 : rowHeight(item, index);
    },
    // 행 높이 함수는 호출자가 안정적인 참조로 준다. 목록은 ref로 읽어 목록이 바뀌어도 함수 참조가 바뀌지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rowHeight],
  );
  const v = useVirtualRows({
    count: items.length,
    rowHeight: heightOf,
    scrollRef,
    ...(overscan !== undefined ? { overscan } : {}),
    ...(fallbackHeight !== undefined ? { fallbackHeight } : {}),
  });
  const variable = typeof rowHeight !== "number";
  useEffect(() => {
    if (variable) v.measure();
    // 행마다 높이가 다른 목록은 목록이 바뀌면 캐시된 크기를 버린다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, variable]);
  useImperativeHandle(handleRef, () => ({ scrollToIndex: (i: number) => v.scrollToIndex(i) }), [v]);
  useEffect(() => {
    if (activeIndex !== null && activeIndex !== undefined && activeIndex >= 0 && activeIndex < items.length) v.scrollToIndex(activeIndex);
    // v는 안정적이지 않아도 인덱스가 바뀔 때만 움직이면 된다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex]);
  const style: CSSProperties = { overflow: "auto", position: "relative", minHeight: 0, ...(height !== undefined ? { height } : { height: "100%" }), ...(maxHeight !== undefined ? { maxHeight } : {}) };
  return (
    <div
      ref={scrollRef}
      role={role}
      aria-label={ariaLabel}
      aria-activedescendant={activeDescendant}
      aria-multiselectable={ariaMultiselectable}
      aria-busy={ariaBusy || undefined}
      aria-rowcount={role === "grid" || role === "treegrid" ? items.length : undefined}
      tabIndex={tabIndex}
      className={className}
      style={style}
      onKeyDown={onKeyDown}
      onFocus={onFocus}
    >
      <div style={{ height: v.getTotalSize(), position: "relative", width: "100%" }} role="presentation">
        {v.getVirtualItems().map((vi) => {
          const item = items[vi.index];
          if (item === undefined) return null;
          return (
            <VirtualRow key={getKey(item, vi.index)}>
              {renderRow(item, {
                index: vi.index,
                setSize: items.length,
                posInSet: vi.index + 1,
                style: { position: "absolute", top: 0, left: 0, width: "100%", height: vi.size, transform: `translateY(${vi.start}px)` },
              })}
            </VirtualRow>
          );
        })}
      </div>
    </div>
  );
}

/** key를 붙이기 위한 투명 래퍼(행 요소가 부모 role 구조를 그대로 이음). */
function VirtualRow({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
