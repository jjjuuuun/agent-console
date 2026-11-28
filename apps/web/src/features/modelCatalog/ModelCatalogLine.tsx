import { useRef, useState } from "react";
import { Button, Icon, IconButton, Menu, Popover, StatusIcon } from "@agent-console/ui";
import { useContainerWidth } from "../../app/useContainerWidth";
import type { CatalogLineState } from "./catalogView";
import "./modelCatalog.css";

export interface ModelCatalogLineProps {
  state: CatalogLineState;
  /** 상태에 맞는 한 줄(이미 화면 언어로 바뀐 문구) */
  text: string;
  /** 줄 끝에 이어 붙는 사유(`failed`). 말줄임 대상 */
  reason?: string | undefined;
  /** 모달 줄이면 `dialog`(툴팁 접두 없음 등 배치만 다르다) */
  variant?: "form" | "dialog";
  refreshLabel: string;
  /** 있으면 [새로 고침]을 그린다 */
  onRefresh?: (() => void) | undefined;
  refreshing?: boolean;
  checkLabel: string;
  /** 있으면 [연결 확인…]을 그린다(줄 폭이 `COLLAPSE_BELOW_PX` 미만이면 `…` 메뉴 안으로 접는다) */
  onCheck?: (() => void) | undefined;
  /** 접힌 메뉴 단추의 이름(`aria-label`). 접힐 수 있으면 필요하다 */
  moreLabel?: string | undefined;
  /** 스크린 리더에만 읽히는 결과 알림(새로 고침이 끝났을 때) */
  announcement?: string | undefined;
  "data-testid"?: string;
}

/** 줄(= 칸) 폭이 이 값 미만이면 [연결 확인…]을 `…` 메뉴로 접는다(docs/design/screen-backend-connect.md §7.1). */
export const COLLAPSE_BELOW_PX = 280;

const ICON: Record<CatalogLineState, "running" | "waiting" | "failed" | "pending" | null> = {
  fetching: "running",
  ok: null,
  stale: "waiting",
  failed: "failed",
  disabled: "pending",
  unsupported: "pending",
  signin: "pending",
};

/**
 * 모델 목록의 조회 상태 한 줄(12px, 말줄임 + 툴팁). 표현 전용: 데이터·동작은 props로 받는다.
 * 줄이 좁으면 글자를 먼저 말줄임하고 단추는 그대로 둔다.
 */
export function ModelCatalogLine({ state, text, reason, variant = "form", refreshLabel, onRefresh, refreshing = false, checkLabel, onCheck, moreLabel, announcement, ...rest }: ModelCatalogLineProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  // 레이아웃을 읽을 수 없으면(폭 0) 접지 않는다(넓은 것으로 본다)
  const width = useContainerWidth(rootRef, COLLAPSE_BELOW_PX);
  const collapse = onCheck !== undefined && width < COLLAPSE_BELOW_PX;
  const icon = ICON[state];
  const full = reason === undefined || reason === "" ? text : `${text} — ${reason}`;
  const busy = state === "fetching" || refreshing;
  return (
    <div ref={rootRef} className="app-mcl" data-state={state} data-variant={variant} data-testid={rest["data-testid"]} role="status" aria-busy={busy || undefined}>
      <span className="app-mcl-text ac-ellipsis" title={full}>
        {icon === null ? null : <StatusIcon status={icon} size={14} className="app-mcl-icon" />}
        <span className="app-mcl-body ac-ellipsis" title={full}>{full}</span>
      </span>
      {onCheck === undefined || collapse ? null : (
        <Button variant="ghost" size="sm" className="app-mcl-btn" onClick={onCheck}>{checkLabel}</Button>
      )}
      {onRefresh === undefined ? null : (
        <Button variant="ghost" size="sm" className="app-mcl-btn" icon={<Icon name="refresh" size={14} />} loading={refreshing} onClick={onRefresh}>{refreshLabel}</Button>
      )}
      {onCheck !== undefined && collapse ? (
        <Popover
          open={menuOpen}
          onOpenChange={setMenuOpen}
          panelRole="menu"
          panelLabel={moreLabel ?? checkLabel}
          align="end"
          renderTrigger={(props) => <IconButton {...props} size="sm" className="app-mcl-btn" label={moreLabel ?? checkLabel} icon={<Icon name="more" size={14} />} data-testid="model-catalog-more" />}
        >
          {({ close }) => <Menu onClose={close} items={[{ id: "check", label: checkLabel, onSelect: onCheck }]} />}
        </Popover>
      ) : null}
      {announcement === undefined || announcement === "" ? null : <span className="ac-sr-only" role="status">{announcement}</span>}
    </div>
  );
}
