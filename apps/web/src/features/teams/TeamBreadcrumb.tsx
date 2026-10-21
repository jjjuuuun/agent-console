import { Link } from "react-router";
import { buildBreadcrumb, type OpenedFrom } from "./openedFrom";
import { teamMessages as t } from "./messages";

export interface TeamBreadcrumbProps {
  rootLabel: string;
  rootHref: string;
  from: OpenedFrom;
  current: string;
  /** 정의 id -> 그 편집 화면 경로(없으면 링크 없음) */
  hrefOf(id: string): string | undefined;
}

/**
 * 중첩 팀 [열기]로 들어온 편집기의 위치 줄: `팀 구성 / 개발 팀 / 검토 파이프라인`. 앞 항목은 라우터 링크이고 마지막이 현재 화면이다.
 * 깊어지면 가까운 3단계만 보이고 앞쪽은 `…`(툴팁에 이름)로 접는다. 부모로 돌아가는 링크는 부모 자신의 `openedFrom`을 이어 준다.
 */
export function TeamBreadcrumb({ rootLabel, rootHref, from, current, hrefOf }: TeamBreadcrumbProps) {
  const { crumbs, hidden } = buildBreadcrumb({ root: { label: rootLabel, href: rootHref }, from, current, hrefOf });
  return (
    <nav aria-label={t.editor.breadcrumbLabel} className="team-crumbs">
      <ol className="ac-breadcrumb">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={`${i}:${c.label}`} aria-current={last ? "page" : undefined}>
              {c.href !== undefined && !last ? (
                <Link to={c.href} {...(c.state === undefined ? {} : { state: c.state })}>{c.label}</Link>
              ) : (
                <span title={c.label === "…" ? hidden.join(" / ") : undefined}>{c.label}</span>
              )}
              {last ? null : <span className="ac-breadcrumb-sep" aria-hidden="true">/</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
