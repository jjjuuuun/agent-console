import { useState, type ReactNode } from "react";
import { ActionButton } from "./ActionButton";
import { Icon } from "./Icon";
import { Menu, Popover, type MenuItemDef } from "./Popover";
import { joinClass } from "./Status";

export interface PageHeaderProps {
  title: string;
  breadcrumb?: readonly { label: string; href?: string }[];
  /** 저장 상태 등 제목 옆 슬롯. */
  status?: ReactNode;
  /** 오른쪽 액션 슬롯(주 액션: 항상 보인다). */
  actions?: ReactNode;
  /**
   * 보조 액션 데이터. 헤더(컨테이너) 폭이 640px 이상이면 `actions` 앞에 아이콘+글자 버튼으로,
   * 미만이면 `more` 메뉴 하나로 접힌다(뷰포트가 아니라 컨테이너 쿼리).
   */
  secondaryActions?: readonly (MenuItemDef & { label: string })[];
  /** `more` 메뉴 버튼의 이름. 기본 "더 보기". */
  moreLabel?: string;
  /** `breadcrumb`가 있을 때 nav 접근성 이름. */
  breadcrumbLabel?: string;
  className?: string;
}

/** 화면 상단 고정 헤더(48px). 제목은 `h1`. 마지막 breadcrumb 항목이 현재 위치(`aria-current`). */
export function PageHeader({ title, breadcrumb, status, actions, secondaryActions = [], moreLabel = "더 보기", breadcrumbLabel, className }: PageHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const hasCrumbs = breadcrumb !== undefined && breadcrumb.length > 0;
  return (
    <header className={joinClass("ac-pageheader", className)}>
      <div className="ac-pageheader-main">
        {hasCrumbs ? (
          <nav aria-label={breadcrumbLabel}>
            <ol className="ac-breadcrumb">
              {breadcrumb.map((crumb, index) => {
                const last = index === breadcrumb.length - 1;
                return (
                  <li key={`${index}:${crumb.label}`} aria-current={last ? "page" : undefined}>
                    {crumb.href !== undefined && !last ? <a href={crumb.href}>{crumb.label}</a> : <span>{crumb.label}</span>}
                    {last ? null : <span className="ac-breadcrumb-sep" aria-hidden="true">/</span>}
                  </li>
                );
              })}
            </ol>
          </nav>
        ) : null}
        <h1 className="ac-pageheader-title ac-ellipsis" title={title}>{title}</h1>
        {status === undefined ? null : <div className="ac-pageheader-status">{status}</div>}
      </div>
      {actions === undefined && secondaryActions.length === 0 ? null : (
        <div className="ac-pageheader-actions">
          {secondaryActions.length === 0 ? null : (
            <>
              <div className="ac-pageheader-secondary">
                {secondaryActions.map((a) => (
                  <ActionButton key={a.id} icon={a.icon} label={a.label} display={a.icon === undefined ? "label" : "icon-label"} size="sm" disabled={a.disabled} onClick={a.onSelect} />
                ))}
              </div>
              <Popover
                className="ac-pageheader-more"
                open={menuOpen}
                onOpenChange={setMenuOpen}
                panelRole="menu"
                panelLabel={moreLabel}
                align="end"
                renderTrigger={(props) => (
                  <button {...props} type="button" className="ac-btn ac-icon-btn" data-variant="ghost" data-size="md" aria-label={moreLabel} title={moreLabel}>
                    <Icon name="more" />
                  </button>
                )}
              >
                {({ close }) => <Menu items={secondaryActions} onClose={close} />}
              </Popover>
            </>
          )}
          {actions}
        </div>
      )}
    </header>
  );
}
