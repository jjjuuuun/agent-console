
import { Link } from "react-router";
import { Button, EmptyState, type MenuItemDef } from "@agent-console/ui";
import { MenuPopover } from "./MenuPopover";
import { folderHomeMessages as m } from "./folderHomeMessages";
import { relativeTime } from "./projectHomeLib";
import type { ConfigRow } from "./useProjectHomeData";

export interface ProjectConfigCardProps {
  rows: readonly ConfigRow[];
  loading: boolean;
  /** 읽지 못한 종류(그 줄만 오류 + [다시 시도]) */
  failed: readonly { kind: string; title: string }[];
  onRetry: (kind: string) => void;
  /** 폴더를 읽을 수 없어 구성 표를 한 줄 안내로 바꾼다 */
  unreadable: boolean;
  /** 막힌 이유(가져오기·새로 만들기). undefined = 허용 */
  blockedReason?: string | undefined;
  /** 새로 만들기 메뉴 항목(종류 제목 + 이동 주소) */
  creatable: readonly { kind: string; title: string; href: string }[];
  onNew: (item: { kind: string; title: string; href: string }) => void;
  /** [공용에서 가져오기…]를 눌렀을 때(복사 계획 대화상자는 호출자가 연다). 없으면 버튼이 없다 */
  onImport?: (() => void) | undefined;
  /** 행 `⋯` 메뉴를 확장하는 슬롯(공용에 저장·삭제) */
  rowMenu?: ((row: ConfigRow) => readonly MenuItemDef[]) | undefined;
  /** 방금 가져온 행의 키(`ConfigRow.key`): 1.5초 강조 */
  highlightKey?: string | undefined;
  /** 구성 사본 열기 */
  onOpen: (href: string) => void;
  nowMs: number;
}

/**
 * "이 프로젝트의 구성" 카드(표현 전용, screen-projects §4.4 ②). 종류 이름은 코드에 없고 행이 가진 `kindTitle`을 그대로 보인다.
 * 가져오기·행 동작의 실제 대화상자는 슬롯으로 받는다.
 */
export function ProjectConfigCard(p: ProjectConfigCardProps) {
  const blocked = p.blockedReason;
  const importBtn = (primary: boolean) => p.onImport === undefined ? null : (
    <Button
      size="sm"
      variant={primary ? "primary" : "secondary"}
      aria-disabled={blocked !== undefined ? "true" : undefined}
      title={blocked}
      onClick={() => {
        if (blocked !== undefined) return;
        p.onImport?.();
      }}
    >
      {m.home.configImport}
    </Button>
  );
  const newMenu = (
    <MenuPopover label={m.home.configNew} blockedReason={blocked} items={p.creatable.map((c) => ({ id: c.kind, label: c.title, onSelect: () => p.onNew(c) }))}>
      {m.home.configNew} ▾
    </MenuPopover>
  );
  const empty = !p.unreadable && !p.loading && p.rows.length === 0 && p.failed.length === 0;

  return (
    <section className="prj-card prj-config" aria-labelledby="prj-config-title" data-testid="project-config-card">
      <header className="prj-card-head">
        <h2 id="prj-config-title" className="prj-card-title">
          {m.home.configTitle}
          {p.unreadable ? null : <span className="prj-card-count app-muted">{m.home.configCount(p.rows.length)}</span>}
        </h2>
        {empty || p.unreadable ? null : (
          <div className="prj-card-actions">
            {importBtn(false)}
            {newMenu}
          </div>
        )}
      </header>
      {p.unreadable ? (
        <p className="app-muted">{m.home.configUnreadable}</p>
      ) : empty ? (
        <EmptyState title={m.home.configEmptyTitle} description={m.home.configEmptyBody} action={<div className="prj-card-actions">{importBtn(true)}{newMenu}</div>} />
      ) : (
        <>
          {p.failed.map((f) => (
            <p key={f.kind} className="prj-row-error" role="alert">
              {m.home.configLoadFailed(f.title)} <Button size="sm" variant="ghost" onClick={() => p.onRetry(f.kind)}>{m.home.retry}</Button>
            </p>
          ))}
          <table className="prj-table">
            <thead>
              <tr>
                <th scope="col">{m.home.configColName}</th>
                <th scope="col">{m.home.configColKind}</th>
                <th scope="col">{m.home.configColModified}</th>
                <th scope="col"><span className="ac-sr-only">{m.home.configRowMenu("")}</span></th>
              </tr>
            </thead>
            <tbody>
              {p.rows.map((r) => (
                <tr key={r.key} data-highlight={p.highlightKey === r.key ? "true" : undefined}>
                  <td className="prj-cell-name">{r.href === undefined ? <span className="ac-ellipsis" title={r.name}>{r.name}</span> : <Link className="ac-ellipsis" to={r.href} title={r.name}>{r.name}</Link>}</td>
                  <td><span className="prj-kind-chip ac-ellipsis" title={r.kindTitle}>{r.kindTitle}</span></td>
                  <td className="app-muted" title={r.modifiedAt === undefined ? undefined : new Date(r.modifiedAt * 1000).toLocaleString("ko")}>{relativeTime(p.nowMs, r.modifiedAt)}</td>
                  <td>
                    {p.rowMenu === undefined && r.href === undefined ? null : (
                      <MenuPopover
                        label={m.home.configRowMenu(r.name)}
                        triggerLabel={m.home.configRowMenu(r.name)}
                        triggerClassName="prj-row-more"
                        items={[
                          ...(r.href === undefined ? [] : [{ id: "open", label: m.home.configOpen, onSelect: () => p.onOpen(r.href as string) }]),
                          ...(p.rowMenu?.(r) ?? []),
                        ]}
                      >
                        ⋯
                      </MenuPopover>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {p.loading ? <p className="app-muted">{m.home.loading}</p> : null}
        </>
      )}
    </section>
  );
}
