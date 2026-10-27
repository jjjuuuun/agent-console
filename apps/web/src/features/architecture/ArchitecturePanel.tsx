import { useState, type ReactNode } from "react";
import "@agent-console/arch-view/styles.css";
import "./architecture.css";
import { ArchitectureDiagram, type ArchFitMode, type ArchViewMode, type ToolbarParts } from "@agent-console/arch-view";
import { Banner, Button } from "@agent-console/ui";
import { useStorage } from "../../app/StorageContext";
import { ARCH_LIMITS, ARCH_STORAGE } from "./archConfig";
import { allNotCollected, observedValue, sourceKinds } from "./archLib";
import { ArchitectureBreadcrumb } from "./ArchitectureBreadcrumb";
import { ArchitectureEmpty } from "./ArchitectureEmpty";
import { archMessages as t } from "./messages";
import type { ArchitectureController } from "./useArchitectureController";

export interface ArchitecturePanelProps {
  controller: ArchitectureController;
  /** 빵 부스러기 처음 항목 이름 */
  rootLabel?: string;
  /** 레인 필터가 걸려 있으면 그 이름들("레인 {이름} 기준" 칩) */
  laneNames?: readonly string[];
  /** 재생 중이라 숫자가 재생 위치가 아니라 범위 전체 값임을 알린다 */
  wholeRange?: boolean;
  /** 실행 중(수집이 이어지는) 범위 */
  live?: boolean;
  /** 다른 필터가 걸려 있는가(빈 상태 B의 [필터 지우기]) */
  hasFilters?: boolean;
  onClearFilters?: () => void;
  onFocusFilters?: () => void;
  /** 설정 › 구조도로 간다. 없으면 버튼을 그리지 않는다. */
  onOpenSettings?: () => void;
  /** 설정 › 로그 출처로 간다. */
  onOpenSources?: () => void;
  /** 건너뛰기 링크: 이벤트 표로 포커스 이동 */
  onSkip?: () => void;
  /** 뷰포트 폭(기본 보기 판정). 생략하면 창 폭. */
  viewportWidth?: number;
  /** 그림 도구줄 구성(생략하면 전부). 실행 상세 탭은 확대·맞춤 단추를 빼고 [그림|목록]·범례만 둔다. */
  toolbar?: boolean | ToolbarParts;
  /** 프로필이 하나이고 하위 구조도·레인 기준이 없으면 머리 줄(프로필·빵 부스러기)을 그리지 않는다 */
  hideEmptyHead?: boolean;
  /** 저장된 맞춤 선택이 없을 때의 맞춤(기본 폭 맞춤) */
  defaultFit?: ArchFitMode;
  /** 저장된 보기 선택이 없을 때의 보기(생략하면 뷰포트 폭으로 정한다) */
  defaultView?: ArchViewMode;
  /** 맞춤·보기 선택을 저장하는 localStorage 키(생략하면 세션 화면과 같은 키) */
  storageKeys?: { fit?: string; view?: string };
  /** 그림 영역(도구줄·캔버스·선택 정보 줄) 높이(px). 생략하면 부모가 준 높이의 남는 부분을 채운다. */
  diagramHeight?: number;
  /** 그림 도구줄 오른쪽에 덧붙일 컨트롤([크게 보기] 등) */
  toolbarExtra?: ReactNode;
  className?: string;
}

const readFit = (v: string | null, fallback: ArchFitMode): ArchFitMode => (v === "contain" || v === "width" || v === "none" ? v : fallback);

/**
 * 구조도 패널(화면 명세 §5): 프로필·빵 부스러기·상태 줄·그림/목록·빈 상태. 데이터와 동작은 `useArchitectureController`가 준다.
 * 부모가 높이를 정해 주면 그림이 남는 높이를 채운다.
 */
export function ArchitecturePanel(p: ArchitecturePanelProps) {
  const c = p.controller;
  const storage = useStorage();
  const fitKey = p.storageKeys?.fit ?? ARCH_STORAGE.fit;
  const viewKey = p.storageKeys?.view ?? ARCH_STORAGE.view;
  const [fit, setFit] = useState<ArchFitMode>(() => readFit(storage.get(fitKey), p.defaultFit ?? "width"));
  const [viewMode, setViewMode] = useState<ArchViewMode>(() => {
    const saved = storage.get(viewKey);
    if (saved === "diagram" || saved === "list") return saved;
    if (p.defaultView !== undefined) return p.defaultView;
    return (p.viewportWidth ?? (typeof window === "undefined" ? 1440 : window.innerWidth)) >= ARCH_LIMITS.listBelowWidth ? "diagram" : "list";
  });
  const [unavailableOpen, setUnavailableOpen] = useState(false);

  const view = c.view;
  if (c.error !== null) {
    return (
      <section className={joinClass("arch-panel", p.className)} aria-label={t.region}>
        <ArchitectureEmpty
          error={c.error}
          onRetry={c.refetch}
          {...(p.onOpenSettings === undefined ? {} : { onOpenSettings: p.onOpenSettings })}
          {...(p.onFocusFilters === undefined ? {} : { onFocusFilters: p.onFocusFilters })}
        />
      </section>
    );
  }
  if (view === undefined) {
    return (
      <section className={joinClass("arch-panel", p.className)} aria-label={t.region} aria-busy="true">
        <div className="arch-skeleton" role="status">
          <span className="arch-skeleton-text">{t.status.loading}</span>
        </div>
      </section>
    );
  }

  const profiles = (c.profiles?.profiles ?? []).filter((x) => x.disabled !== true);
  const unassignedCount = observedValue(view.unassigned?.metrics?.["count"]);
  const unavailable = view.unavailable ?? [];
  const noEvents = view.event_total === 0;
  const noSource = !noEvents && allNotCollected(view);
  const kinds = sourceKinds(view).join(", ");
  const notes = view.notes ?? [];

  const hideHead = p.hideEmptyHead === true && profiles.length < 2 && c.drill.length === 0 && (p.laneNames ?? []).length === 0;
  const lead = hideHead ? undefined : (
    <>
      {profiles.length >= 2 ? (
        <label className="arch-profile">
          <span>{t.profile}</span>
          <select value={view.profile} onChange={(e) => c.setProfile(e.target.value)}>
            {profiles.map((x) => (
              <option key={x.id} value={x.id}>{x.title || x.id}</option>
            ))}
          </select>
        </label>
      ) : null}
      <ArchitectureBreadcrumb rootLabel={p.rootLabel ?? t.breadcrumb.root} steps={c.drill.map((s) => s.label)} onGoTo={c.goTo} />
      {(p.laneNames ?? []).map((name) => (
        <span key={name} className="arch-basis">{t.status.laneBasis(name)}</span>
      ))}
    </>
  );
  const afterToolbar = (
    <>
      <div className="arch-status">
        <span>{t.status.events(view.event_total)}</span>
        {p.wholeRange === true ? <span className="arch-basis">{t.status.wholeRange}</span> : null}
        {unassignedCount !== undefined && unassignedCount > 0 && view.unassigned != null ? (
          <span>
            {t.status.unassigned(unassignedCount)}{" "}
            <button type="button" className="arch-link" onClick={() => c.select({ kind: "unassigned", id: "" })}>{t.status.unassignedView}</button>
          </span>
        ) : null}
        {unavailable.length > 0 ? (
          <span>
            {t.status.unavailable(unavailable.length)}{" "}
            <button type="button" className="arch-link" aria-expanded={unavailableOpen} onClick={() => setUnavailableOpen((o) => !o)}>
              {unavailableOpen ? t.status.unavailableClose : t.status.unavailableOpen} {unavailableOpen ? "▴" : "▾"}
            </button>
          </span>
        ) : null}
        {p.live === true && c.updatedAt !== null ? <span className="arch-live">{t.status.liveUpdated(new Date(c.updatedAt).toLocaleTimeString("ko-KR"))}</span> : null}
        {c.refreshing ? <span className="app-muted">{t.status.refreshing}</span> : null}
      </div>
      {unavailableOpen && unavailable.length > 0 ? (
        <ul className="arch-unavailable" aria-label={t.status.unavailable(unavailable.length)}>
          {unavailable.map((u, i) => (
            <li key={`${u.cell ?? ""}:${u.item}:${i}`}>{t.status.unavailableItem(u.item, u.reason ?? "")}</li>
          ))}
        </ul>
      ) : null}
    </>
  );

  return (
    <section className={joinClass("arch-panel", p.className)} aria-label={t.region} data-refreshing={c.refreshing ? "true" : undefined}>
      {notes.map((note) => (
        <Banner key={note.code} tone="info" className="arch-banner" {...(p.onOpenSettings !== undefined && note.code.endsWith("profile_issues") ? { actions: <Button size="sm" onClick={p.onOpenSettings}>{t.banner.openSettings}</Button> } : {})}>
          {note.message}
        </Banner>
      ))}
      {noEvents ? (
        <Banner tone="info" className="arch-banner" title={t.empty.noEvents.title} {...(p.hasFilters === true && p.onClearFilters !== undefined ? { actions: <Button size="sm" onClick={p.onClearFilters}>{t.empty.noEvents.action}</Button> } : {})}>
          {t.empty.noEvents.body}
        </Banner>
      ) : null}
      {noSource ? (
        <Banner tone="warning" className="arch-banner" title={t.empty.noSource.title} {...(p.onOpenSources !== undefined ? { actions: <Button size="sm" onClick={p.onOpenSources}>{t.empty.noSource.action}</Button> } : {})}>
          {t.empty.noSource.body(kinds)}
        </Banner>
      ) : null}

      <div className="arch-diagram" {...(p.diagramHeight === undefined ? {} : { style: { height: p.diagramHeight, flex: "none" } })}>
        {c.refreshing ? <div className="arch-progress" aria-hidden="true" /> : null}
        <ArchitectureDiagram
          view={view}
          selection={c.selection}
          highlight={c.highlight}
          onSelect={(s) => c.select(s)}
          onBlocked={(target, reason) => c.blocked(target, reason)}
          onDrill={c.drillInto}
          onBack={c.drill.length > 0 ? () => c.goTo(c.drill.length - 2) : undefined}
          {...(p.onSkip === undefined ? {} : { onSkip: p.onSkip })}
          {...(p.toolbar === undefined ? {} : { toolbar: p.toolbar })}
          {...(lead === undefined ? {} : { toolbarLead: lead })}
          afterToolbar={afterToolbar}
          {...(p.toolbarExtra === undefined ? {} : { toolbarExtra: p.toolbarExtra })}
          fitMode={fit}
          onFitModeChange={(m) => { setFit(m); if (m !== "none") storage.set(fitKey, m); }}
          viewMode={viewMode}
          onViewModeChange={(m) => { setViewMode(m); storage.set(viewKey, m); }}
        />
      </div>
      <span className="ac-sr-only" role="status" aria-live="polite" aria-atomic="true">{c.announcement}</span>
    </section>
  );
}

function joinClass(...names: (string | undefined)[]): string {
  return names.filter((n): n is string => n !== undefined && n !== "").join(" ");
}
