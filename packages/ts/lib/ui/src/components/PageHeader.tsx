import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ActionButton } from "./ActionButton";
import { Icon } from "./Icon";
import { Menu, Popover, type MenuItemDef } from "./Popover";
import { defaultUiMessages, type UiMessages } from "../messages";
import { joinClass } from "./Status";

/** 제목에 남겨 둘 최소 폭(px). 보조 액션이 이만큼도 못 남기면 `more` 메뉴로 접는다(문구가 길어지는 언어 대비). */
const MIN_TITLE_PX = 120;

/**
 * 측정 기반 접기: 컨테이너 폭이 충분(640px 이상)해도 보조 액션 때문에 제목이 `MIN_TITLE_PX`보다 좁아지면 접는다.
 * 접은 뒤 펼 때는 접을 때 잰 보조 액션 폭만큼 컨테이너가 넓어져야 한다(깜박임 방지).
 */
function useCollapseByTitle(hasSecondary: boolean) {
  const headerRef = useRef<HTMLElement | null>(null);
  const titleRef = useRef<HTMLHeadingElement | null>(null);
  const secondaryRef = useRef<HTMLDivElement | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const memo = useRef<{ width: number; extra: number } | null>(null);

  const measure = () => {
    const header = headerRef.current;
    const title = titleRef.current;
    if (header === null || title === null || !hasSecondary) return;
    const width = header.clientWidth;
    if (!collapsed) {
      const visible = secondaryRef.current?.offsetWidth ?? 0; // 0 = 이미 CSS(컨테이너 쿼리)가 접었다
      if (visible > 0 && title.clientWidth < Math.min(MIN_TITLE_PX, title.scrollWidth)) {
        memo.current = { width, extra: visible };
        setCollapsed(true);
      }
    } else if (memo.current !== null && width >= memo.current.width + memo.current.extra) {
      memo.current = null;
      setCollapsed(false);
    }
  };

  useLayoutEffect(() => {
    measure();
  });
  useLayoutEffect(() => {
    const header = headerRef.current;
    if (header === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(header);
    return () => observer.disconnect();
    // `measure`는 렌더마다 새로 만들어지지만 위의 효과가 렌더마다 다시 측정한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSecondary, collapsed]);

  return { headerRef, titleRef, secondaryRef, collapsed: hasSecondary && collapsed };
}

export interface PageHeaderProps {
  title: string;
  breadcrumb?: readonly { label: string; href?: string }[];
  /** 제목 앞 슬롯(라우터 링크 같은 사용자 정의 상위 이동). `breadcrumb`와 함께 쓰면 breadcrumb 뒤, 제목 앞이다. */
  leading?: ReactNode;
  /** 저장 상태 등 제목 옆 슬롯. */
  status?: ReactNode;
  /** 오른쪽 액션 슬롯(주 액션: 항상 보인다). */
  actions?: ReactNode;
  /**
   * 보조 액션 데이터. 헤더(컨테이너) 폭이 640px 이상이면 `actions` 앞에 아이콘+글자 버튼으로,
   * 미만이면 `more` 메뉴 하나로 접힌다(뷰포트가 아니라 컨테이너 쿼리). 640px 이상이어도 버튼이 길어
   * 제목에 120px을 남기지 못하면 측정해서 접는다(영어처럼 문구가 긴 언어 대비).
   */
  secondaryActions?: readonly (MenuItemDef & { label: string })[];
  /** `more` 메뉴 버튼의 이름. 기본 `messages.more`("더 보기"). */
  moreLabel?: string;
  /** 기본 문구 덮어쓰기(`@agent-console/ui/locales/en` 등). */
  messages?: Partial<UiMessages>;
  /** `breadcrumb`가 있을 때 nav 접근성 이름. */
  breadcrumbLabel?: string;
  className?: string;
}

/** 화면 상단 고정 헤더(48px). 제목은 `h1`. 마지막 breadcrumb 항목이 현재 위치(`aria-current`). */
export function PageHeader({ title, breadcrumb, leading, status, actions, secondaryActions = [], moreLabel: moreLabelProp, messages, breadcrumbLabel, className }: PageHeaderProps) {
  const moreLabel = moreLabelProp ?? messages?.more ?? defaultUiMessages.more;
  const [menuOpen, setMenuOpen] = useState(false);
  const hasCrumbs = breadcrumb !== undefined && breadcrumb.length > 0;
  const { headerRef, titleRef, secondaryRef, collapsed } = useCollapseByTitle(secondaryActions.length > 0);
  return (
    <header ref={headerRef} className={joinClass("ac-pageheader", className)} data-collapsed={collapsed ? "true" : undefined}>
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
        {leading === undefined ? null : <div className="ac-pageheader-leading">{leading}</div>}
        <h1 ref={titleRef} className="ac-pageheader-title ac-ellipsis" title={title}>{title}</h1>
        {status === undefined ? null : <div className="ac-pageheader-status">{status}</div>}
      </div>
      {actions === undefined && secondaryActions.length === 0 ? null : (
        <div className="ac-pageheader-actions">
          {secondaryActions.length === 0 ? null : (
            <>
              <div ref={secondaryRef} className="ac-pageheader-secondary">
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
