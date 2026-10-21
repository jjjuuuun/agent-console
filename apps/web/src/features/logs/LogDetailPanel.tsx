import { useCallback, useImperativeHandle, useMemo, useRef, type KeyboardEvent, type Ref } from "react";
import { LogEventDetail, type DetailTab, type LogEventDetailHandle, type LogTaxonomyView } from "@agent-console/log-view";
import type { LogEvent } from "@agent-console/contracts";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { Drawer } from "./Drawer";
import { JsonView } from "./JsonView";
import { LOGS_LIMITS } from "./logsConfig";
import { errorBlockOf } from "./logsErrors";
import { isTypingTarget } from "./logsLib";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";
import { useLogEventDetail } from "./useLogsApi";
import { useLogLinks } from "./useLogLinks";

/** 상세 패널의 명령형 API. 표에서 `Enter`를 다시 누르면 앱이 패널로 포커스를 옮길 때 쓴다. */
export interface LogDetailPanelHandle {
  /** 패널의 탭 줄(현재 탭)에 포커스한다. @returns 탭 줄이 아직 없으면 false */
  focusTabs(): boolean;
}

export interface LogDetailPanelProps {
  ref?: Ref<LogDetailPanelHandle>;
  uid: string;
  /** 목록 행에서 이미 아는 이벤트(상세 로딩 중 개요를 먼저 그린다) */
  preview?: LogEvent | undefined;
  taxonomy: LogTaxonomyView;
  isError(event: LogEvent): boolean;
  originTime: number | null;
  laneLabelFor(thread: string): string | undefined;
  /** 근거·관련 항목 클릭 → 이동(같은 세션이면 표에서 선택, 다른 세션이면 그 세션 상세) */
  onOpenEvent(uid: string, session?: string): void;
  onClose(): void;
  /** 필터로 목록에서 사라진 이벤트인지("필터 밖의 이벤트" 칩) */
  filteredOut?: boolean;
  /** 실행 상세 드로어처럼 개요·상세·원문만 보일 때 */
  tabs?: readonly DetailTab[];
  width?: number;
  height?: number;
  /** 드로어(모달) 모드를 강제로 정한다. 기본은 화면 폭(1280 미만이면 드로어) */
  drawer?: boolean;
}

/** 선택한 이벤트의 상세 패널(`GET /logs/events/{uid}`) — 넓은 화면은 옆 패널, 좁으면 드로어. `1`~`5`로 탭 전환, `Esc`로 닫기. */
export function LogDetailPanel({ ref, ...p }: LogDetailPanelProps) {
  const wide = useMediaQuery(`(min-width: ${LOGS_LIMITS.drawerBelow}px)`);
  const asDrawer = p.drawer ?? !wide;
  const q = useLogEventDetail(p.uid);
  const links = useLogLinks();
  const detailRef = useRef<LogEventDetailHandle>(null);
  useImperativeHandle(ref, () => ({ focusTabs: () => detailRef.current?.focusTab() ?? false }), []);
  const copy = useCallback((uid: string) => void navigator.clipboard?.writeText(`${window.location.origin}${window.location.pathname}${window.location.search}#e=${encodeURIComponent(uid)}`), []);
  const error = q.isError && q.data === undefined ? errorBlockOf(q.error, t.loadFailed) : null;
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      p.onClose();
      return;
    }
    if (isTypingTarget(e.target) || e.ctrlKey || e.altKey || e.metaKey) return;
    const n = Number(e.key);
    if (Number.isInteger(n) && n >= 1 && n <= 5) {
      if (detailRef.current?.selectTabAt(n - 1) === true) e.preventDefault();
    }
  };
  const body = useMemo(
    () => (
      <LogEventDetail
        ref={detailRef}
        {...(q.data === undefined ? {} : { detail: q.data })}
        {...(p.preview === undefined ? {} : { preview: p.preview })}
        loading={q.isPending}
        error={error}
        onRetry={() => void q.refetch()}
        {...(p.tabs === undefined ? {} : { tabs: p.tabs })}
        onOpenEvent={p.onOpenEvent}
        onClose={p.onClose}
        onCopyUid={copy}
        renderCodeBlock={(value, o) => <JsonView value={value} language={o.language} label={t.detail.detailPanel} />}
        renderLinks={links}
        taxonomy={p.taxonomy}
        slotFor={slotFor}
        isError={p.isError}
        originTime={p.originTime}
        laneLabelFor={p.laneLabelFor}
        {...(p.height === undefined ? {} : { height: p.height })}
      />
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [q.data, q.isPending, error, p.preview, p.tabs, p.onOpenEvent, p.onClose, copy, links, p.taxonomy, p.isError, p.originTime, p.laneLabelFor, p.height],
  );
  const inner = (
    <div className="logs-detail" data-filtered-out={p.filteredOut ? "true" : undefined} onKeyDown={onKey}>
      {p.filteredOut ? <span className="logs-chip" role="status">{t.detail.filteredOutChip}</span> : null}
      {body}
    </div>
  );
  if (asDrawer) {
    return (
      <Drawer open title={t.detail.detailPanel} onClose={p.onClose} {...(p.width === undefined ? {} : { width: p.width })}>
        {inner}
      </Drawer>
    );
  }
  return <aside className="logs-detail-aside" aria-label={t.detail.detailPanel}>{inner}</aside>;
}
