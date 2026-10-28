import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Button, EmptyState } from "@agent-console/ui";
import type { LogSourceInfo } from "@agent-console/contracts";
import { useHint } from "../../app/hints";
import { useNow } from "../../app/useNow";
import { useStorage } from "../../app/StorageContext";
import { ROUTE_ROLES, routeIconNode } from "../library";
import { LINK_ROLES, pathForRole } from "./routeLinks";
import { LOGS_STORAGE, NOTICE_PRIORITY } from "./logsConfig";
import type { LogNotice } from "./NoticeBar";
import { firstUseSources, offReadingSources } from "./logsLib";
import { logsMessages as t } from "./messages";
import { sourceStatusLine } from "./sourceStatus";

/** 설정 화면의 로그 출처 섹션 주소(`#logs`, 출처 카드를 펼치려면 `?source=<id>`). */
export function settingsLogsHref(sourceId?: string): string {
  return `${pathForRole(LINK_ROLES.settings)}#logs${sourceId === undefined ? "" : `?source=${encodeURIComponent(sourceId)}`}`;
}

const MAX_CARDS = 5;

/** A: 켜진 출처가 0개 — 첫 사용 카드. 출처 카드는 전부 서버 디스크립터에서 온다(이름을 코드에 두지 않는다). */
export function FirstUseCard({ sources }: { sources: readonly LogSourceInfo[] }) {
  const storage = useStorage();
  const [all, setAll] = useState(false);
  const [openHelp, setOpenHelp] = useState<ReadonlySet<string>>(new Set());
  const cards = useMemo(() => firstUseSources(sources), [sources]);
  const shown = all ? cards : cards.slice(0, MAX_CARDS);
  const opened = storage.get(LOGS_STORAGE.openedSession) !== null;
  const scanned = sources.some((s) => s.status?.last_scan_at != null);
  const f = t.first;
  if (sources.length === 0) return <div className="logs-first"><EmptyState icon={routeIconNode(ROUTE_ROLES.logs)} title={f.title} description={f.noSources} /></div>;
  return (
    <div className="logs-first" data-testid="logs-first-use">
      <EmptyState
        icon={routeIconNode(ROUTE_ROLES.logs)}
        title={f.title}
        description={f.body}
        steps={f.steps.map((s, i) => ({ label: `${s.title} — ${s.body}`, done: i === 0 ? sources.some((x) => x.enabled) : i === 1 ? scanned : opened }))}
        doneLabel="완료"
      />
      <section className="logs-first-sources" aria-label={f.available}>
        <h3 className="app-block-subtitle">{f.available}</h3>
        <ul className="logs-source-cards">
          {shown.map((s) => {
            const d = s.descriptor;
            const help = d.setup_help;
            const expanded = openHelp.has(d.id);
            return (
              <li key={d.id} className="logs-source-card">
                <div className="logs-source-card-head">
                  <strong className="ac-ellipsis" title={d.title}>{d.title}</strong>
                  {d.reads_paths === true ? <span className="logs-chip">{f.readOnly}</span> : null}
                  <Link className="logs-source-card-link" to={settingsLogsHref(d.id)}>{f.enableInSettings}</Link>
                </div>
                {d.description ? <p className="app-muted logs-clamp-2 app-wrap">{d.description}</p> : null}
                {help ? (
                  <p className={`app-muted app-wrap ${expanded ? "" : "logs-clamp-1"}`}>
                    {help}
                    {!expanded ? (
                      <>
                        {" "}
                        <button type="button" className="logs-linkbtn" onClick={() => setOpenHelp(new Set(openHelp).add(d.id))}>{f.moreHelp}</button>
                      </>
                    ) : null}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
        {cards.length > MAX_CARDS && !all ? (
          <p className="app-muted">
            {f.more(cards.length - MAX_CARDS)} <button type="button" className="logs-linkbtn" onClick={() => setAll(true)}>{f.showAll}</button>
          </p>
        ) : null}
      </section>
      <p className="app-muted logs-first-privacy"><span aria-hidden="true">ⓘ </span>{f.privacy}</p>
    </div>
  );
}

export interface EmptyBProps {
  sources: readonly LogSourceInfo[];
  scanning: boolean;
  onScan: () => void;
}

/** B: 켜진 출처는 있는데 이벤트가 0건 — 출처별 상태 한 줄 + [지금 수집] + 설정 링크. */
export function EmptyNoLogs({ sources, scanning, onScan }: EmptyBProps) {
  const nowMs = useNow(true, 30_000);
  const enabled = sources.filter((s) => s.enabled);
  return (
    <div className="logs-empty" data-testid="logs-empty-b">
      <EmptyState
        icon={routeIconNode(ROUTE_ROLES.logs)}
        title={t.empty.bTitle}
        description={
          <>
            <p>{t.empty.bBody}</p>
            <ul className="logs-empty-sources">
              {enabled.map((s) => (
                <li key={s.descriptor.id} className="app-wrap">{t.empty.sourceLine(s.descriptor.title, sourceStatusLine(s, nowMs))}</li>
              ))}
            </ul>
          </>
        }
        action={<Button variant="primary" loading={scanning} onClick={onScan}>{t.scan}</Button>}
        secondaryAction={<Link className="logs-linkbtn" to={settingsLogsHref()}>{t.empty.openSettings}</Link>}
      />
    </div>
  );
}

export interface EmptyCProps {
  /** 필터가 걸려 있어 지울 수 있는지 */
  onClearFilters?: (() => void) | undefined;
  /** 기본 기간이 걸려 있으면 [기간 전체로 보기] */
  onAllRange?: (() => void) | undefined;
}

/** C: 이벤트는 있는데 필터 결과가 0건. */
export function EmptyNoMatch({ onClearFilters, onAllRange }: EmptyCProps) {
  return (
    <div className="logs-empty" data-testid="logs-empty-c">
      <EmptyState
        icon={routeIconNode(ROUTE_ROLES.logs)}
        title={t.empty.cTitle}
        action={onClearFilters ? <Button onClick={onClearFilters}>{t.clearFilters}</Button> : undefined}
        secondaryAction={onAllRange ? <Button onClick={onAllRange}>{t.filters.rangeAll}</Button> : undefined}
      />
    </div>
  );
}

/**
 * D: 이벤트가 있고 외부 파일을 읽는 출처가 꺼져 있을 때의 안내(닫으면 다시 안 보인다). 알림 줄에 넣을 데이터를 돌려준다(없으면 null).
 * `active`가 false면 아무것도 내지 않는다(예: 목록이 비어 있을 때).
 */
export function useOtherSourcesNotice(sources: readonly LogSourceInfo[] | undefined, active: boolean): LogNotice | null {
  const hint = useHint(LOGS_STORAGE.hintOtherSources);
  const off = offReadingSources(sources);
  if (!active || !hint.visible || off.length === 0) return null;
  const titles = off.slice(0, 2).map((s) => s.descriptor.title).join(", ");
  const plain = t.empty.hintD(titles, Math.max(0, off.length - 2));
  return {
    id: "other-sources",
    priority: NOTICE_PRIORITY.hint,
    tone: "info",
    text: <>{plain} <Link to={settingsLogsHref()}>{t.empty.hintDAction}</Link></>,
    title: plain,
    onDismiss: hint.dismiss,
  };
}

/** 새 이벤트가 수집됐다는 알림의 바탕(버튼은 호출자가 `action`으로 더한다). 라이브 이동 알림도 같은 모양이다. */
export function freshNotice(id: string, text: string): LogNotice {
  return { id, priority: NOTICE_PRIORITY.fresh, tone: "info", text, title: text, className: "logs-new-banner" };
}
