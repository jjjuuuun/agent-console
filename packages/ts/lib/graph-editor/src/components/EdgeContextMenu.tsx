/**
 * 연결선 우클릭 메뉴(graph-edges §1.4·§2.4, 키보드 대안 `Shift+F10`/ContextMenu 키).
 * 데이터와 콜백을 props로만 받는 표현 컴포넌트다. 모양 목록은 `shapes`(레지스트리)에서 온다.
 * 여러 연결선이 선택된 상태에서 열면 모든 항목이 선택 전체에 적용되고, [경로 초기화]는 확인 단계를 거친다.
 */
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import { defaultMessages, format } from "../messages";
import type { GraphEditorMessages } from "../messages";
import type { EdgeShapeDescriptor } from "../shapes/types";

export interface EdgeContextMenuProps {
  /** 메뉴를 놓을 자리(부모 상자 기준 px) */
  at: { x: number; y: number };
  /** 대상 연결선 수(2 이상이면 다중) */
  count: number;
  shapes: readonly EdgeShapeDescriptor[];
  /** 대상 연결선의 `layout.shape`가 모두 같으면 그 값(상속이면 `""`), 다르면 `null` */
  shape: string | null;
  /** 경로 초기화로 실제 지워질 연결선 수 */
  resettable: number;
  /** 경로 편집 모드로 들어갈 수 있는가(연결선 1개이고 모양이 경유점을 지원) */
  canEditPath: boolean;
  readOnly?: boolean;
  messages?: GraphEditorMessages;
  onShape: (shapeId: string | null) => void;
  onResetPaths: () => void;
  onEditPath: () => void;
  onDelete: () => void;
  /** 닫기(항목을 고르거나 Esc/바깥 클릭). 포커스를 되돌리는 일은 호출 쪽이 한다 */
  onClose: () => void;
  className?: string;
}

export function EdgeContextMenu(props: EdgeContextMenuProps): ReactNode {
  const { at, count, shapes, shape, resettable, canEditPath, readOnly = false, onClose } = props;
  const m = props.messages ?? defaultMessages;
  const rootRef = useRef<HTMLDivElement>(null);
  const [confirm, setConfirm] = useState(false);
  const many = count > 1;

  useEffect(() => {
    rootRef.current?.querySelector<HTMLElement>('[role^="menuitem"]')?.focus();
  }, []);
  useEffect(() => {
    // 바깥을 누르면 닫는다
    const down = (e: PointerEvent): void => {
      if (rootRef.current !== null && e.target instanceof Node && !rootRef.current.contains(e.target)) onClose();
    };
    document.addEventListener("pointerdown", down, true);
    return () => document.removeEventListener("pointerdown", down, true);
  }, [onClose]);

  const pick = (fn: () => void): void => {
    onClose();
    fn();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLElement>): void => {
    e.stopPropagation(); // 캔버스 단축키(S·X·Delete 등)가 메뉴 안에서 동작하지 않게
    const items = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not(:disabled), [data-menu-focus]') ?? []);
    const cur = items.indexOf(document.activeElement as HTMLElement);
    let to: number;
    if (e.key === "ArrowDown") to = (cur + 1) % items.length;
    else if (e.key === "ArrowUp") to = (cur - 1 + items.length) % items.length;
    else if (e.key === "Home") to = 0;
    else if (e.key === "End") to = items.length - 1;
    else if (e.key === "Escape") {
      e.preventDefault();
      if (confirm) setConfirm(false);
      else onClose();
      return;
    } else if (e.key === "Tab") {
      e.preventDefault();
      onClose();
      return;
    } else return;
    e.preventDefault();
    items[to]?.focus();
  };

  const style: CSSProperties = { left: at.x, top: at.y };
  const title = many ? format(m.selectedCount, { count }) : m.edgeMenuLabel;
  return (
    <div ref={rootRef} className={["ac-ge-menu", props.className].filter(Boolean).join(" ")} style={style} role="menu" aria-label={m.edgeMenuLabel} data-testid="edge-menu" onKeyDown={onKeyDown}>
      <div className="ac-ge-menu-head" aria-hidden="true">
        {title}
      </div>
      {confirm ? (
        <div role="alertdialog" aria-label={m.edgeLayoutResetPath} className="ac-ge-tidy-confirm">
          <span>{format(m.routeResetConfirm, { n: resettable })}</span>
          <button type="button" className="ac-ge-btn ac-ge-btn--danger" data-menu-focus autoFocus onClick={() => pick(props.onResetPaths)}>
            {m.routeResetConfirmYes}
          </button>
          <button type="button" className="ac-ge-btn" data-menu-focus onClick={() => setConfirm(false)}>
            {m.tidyCancel}
          </button>
        </div>
      ) : (
        <>
          <div className="ac-ge-menu-sub" role="presentation">
            {m.edgeMenuShapeHeading}
          </div>
          <button type="button" role="menuitemradio" aria-checked={shape === ""} className="ac-ge-menu-item" disabled={readOnly} onClick={() => pick(() => props.onShape(null))}>
            {m.nodeLayoutInherit}
          </button>
          {shapes.map((s) => (
            <button key={s.id} type="button" role="menuitemradio" aria-checked={shape === s.id} className="ac-ge-menu-item" disabled={readOnly} onClick={() => pick(() => props.onShape(s.id))}>
              {s.title}
            </button>
          ))}
          <hr className="ac-ge-menu-sep" />
          {canEditPath && (
            <button type="button" role="menuitem" className="ac-ge-menu-item" disabled={readOnly} onClick={() => pick(props.onEditPath)}>
              {m.edgeMenuEditPath}
            </button>
          )}
          <button
            type="button"
            role="menuitem"
            className="ac-ge-menu-item"
            disabled={readOnly}
            onClick={() => {
              if (!many) pick(props.onResetPaths);
              else if (resettable === 0) pick(props.onResetPaths); // 지울 것이 없으면 확인 없이 안내만(호출 쪽이 처리)
              else setConfirm(true);
            }}
          >
            {m.edgeLayoutResetPath}
          </button>
          <button type="button" role="menuitem" className="ac-ge-menu-item ac-ge-menu-item--danger" disabled={readOnly} onClick={() => pick(props.onDelete)}>
            {m.edgeMenuDelete}
          </button>
        </>
      )}
    </div>
  );
}
