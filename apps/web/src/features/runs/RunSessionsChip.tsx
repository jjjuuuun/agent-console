import { useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { Icon, Popover, useIconRegistry } from "@agent-console/ui";
import { formatCount, formatDuration } from "../../lib/format";
import { runsMessages as t } from "./messages";
import type { RunSessions, SessionInfo } from "./runSessions";

export interface RunSessionsChipProps {
  sessions: RunSessions;
  /** 그래프에서 강조 중인 세션 id(없으면 null) */
  selectedId: string | null;
  onSelect(id: string | null): void;
  /** [로그 보기] 링크. 로그 연동이 꺼져 있으면 생략(열이 없다) */
  logHref?: ((sessionId: string) => string) | undefined;
  /** 이 시각(epoch 초) 기준 `+N초`로 세션 시작을 보인다. 없으면 첫 세션 시작 */
  originSec?: number | undefined;
  nowSec: number;
}

/** 세션 번호 배지: 색 점(8px) + `S{n}`. 색만으로 뜻을 전하지 않는다(번호가 같이 간다). */
export function SessionBadge({ session, className }: { session: Pick<SessionInfo, "number" | "color">; className?: string | undefined }) {
  return (
    <span className={["ses-badge", className].filter(Boolean).join(" ")}>
      <span className="ses-dot" aria-hidden="true" style={{ background: session.color }} />
      {t.sessions.badge(session.number)}
    </span>
  );
}

/**
 * 실행 머리의 `세션 N개` 칩과 세션 목록 팝오버(열: 세션·이름·백엔드·시작·소요·서브·[로그 보기]). 세션 id를 아는 실행이 없으면 아무것도 그리지 않는다.
 * 행을 고르면 그래프가 그 세션의 노드를 강조한다(`Esc`로 해제). 백엔드 이름은 데이터에 없어 `–`로 보인다.
 */
export function RunSessionsChip({ sessions, selectedId, onSelect, logHref, originSec, nowSec }: RunSessionsChipProps) {
  const [open, setOpen] = useState(false);
  const registry = useIconRegistry();
  if (sessions.list.length === 0) return null;
  const origin = originSec ?? sessions.list.find((s) => s.startedAt !== undefined)?.startedAt;
  const unknownTitle = sessions.unknownCount > 0 ? t.sessions.unknown(sessions.unknownCount) : undefined;
  const moveFocus = (e: KeyboardEvent<HTMLElement>, id: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(selectedId === id ? null : id);
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const rows = [...(e.currentTarget.closest("tbody")?.querySelectorAll<HTMLElement>("tr[data-session-row]") ?? [])];
      const at = rows.indexOf(e.currentTarget);
      rows[(at + (e.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length]?.focus();
    }
  };
  return (
    <span className="runs-sessions" data-sessions="">
      <Popover
        open={open}
        onOpenChange={setOpen}
        panelLabel={t.sessions.title}
        panelClassName="runs-sessions-panel"
        renderTrigger={(trigger) => (
          <button type="button" {...trigger} className="ac-btn runs-sessions-chip" data-variant="ghost" data-size="sm" title={unknownTitle}>
            {registry.has("layers") ? <Icon name="layers" size={14} /> : null} {t.sessions.chip(sessions.list.length)} <span aria-hidden="true">▾</span>
          </button>
        )}
      >
        <table className="runs-sessions-table" aria-label={t.sessions.title} onKeyDown={(e) => e.key === "Escape" && onSelect(null)}>
          <thead>
            <tr>
              <th scope="col">{t.sessions.col.session}</th>
              <th scope="col">{t.sessions.col.name}</th>
              <th scope="col">{t.sessions.col.backend}</th>
              <th scope="col">{t.sessions.col.start}</th>
              <th scope="col">{t.sessions.col.duration}</th>
              <th scope="col">{t.sessions.col.sub}</th>
              {logHref !== undefined ? <th scope="col"><span className="ac-sr-only">{t.sessions.log}</span></th> : null}
            </tr>
          </thead>
          <tbody>
            {sessions.list.map((s) => (
              <tr
                key={s.id}
                data-session-row=""
                tabIndex={0}
                aria-selected={selectedId === s.id}
                data-selected={selectedId === s.id ? "true" : undefined}
                onClick={() => onSelect(selectedId === s.id ? null : s.id)}
                onKeyDown={(e) => moveFocus(e, s.id)}
              >
                <td><SessionBadge session={s} /></td>
                <td className="ac-ellipsis" title={s.name}>{s.name}</td>
                <td>–</td>
                <td className="ac-num">{origin === undefined || s.startedAt === undefined ? "–" : t.sessions.relativeStart(formatDuration((s.startedAt - origin) * 1000))}</td>
                <td className="ac-num">{s.startedAt === undefined ? "–" : formatDuration(((s.endedAt ?? nowSec) - s.startedAt) * 1000)}</td>
                <td className="ac-num">{s.subCalls > 0 ? formatCount(s.subCalls) : "–"}</td>
                {logHref !== undefined ? (
                  <td>
                    <Link to={logHref(s.id)} onClick={(e) => e.stopPropagation()}>{t.sessions.log}</Link>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        {unknownTitle !== undefined ? <p className="app-muted runs-note">{unknownTitle}</p> : null}
      </Popover>
      {sessions.subTotal > 0 ? <span className="app-muted">· {t.sessions.sub(sessions.subTotal)}</span> : null}
    </span>
  );
}
