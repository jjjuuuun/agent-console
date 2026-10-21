import { useState } from "react";
import { Link } from "react-router";
import type { UsageSourceInfo } from "@agent-console/contracts";
import { Markdown } from "@agent-console/chat";
import { Disclosure, TrustBadge } from "@agent-console/ui";
import { formatDateTime, formatRelative } from "../../lib/format";
import { usageMessages as t } from "./messages";

export interface SourcesPanelProps {
  sources: readonly UsageSourceInfo[];
  nowMs: number;
  settingsHref: string;
  /** 이 출처에 지금 보이는 창 값이 있는가(없으면 설정 안내를 펼쳐 둔다) */
  hasObservation(sourceId: string): boolean;
  /** 이 출처 창들의 가장 최근 관측 시각(서버 출처 상태에 마지막 관측이 없을 때 대신 쓴다) */
  latestObservedAt?(sourceId: string): number | undefined;
}

/** 출처 목록: 디스크립터 title·id·신뢰 등급·사용 여부·마지막 관측·오류. 켜고 끄는 일은 설정 화면에서 한다. */
export function SourcesPanel({ sources, nowMs, settingsHref, hasObservation, latestObservedAt }: SourcesPanelProps) {
  if (sources.length === 0) {
    return (
      <p className="app-muted" role="status">
        {t.sources.empty} <Link to={settingsHref}>{t.sources.enableInSettings}</Link>
      </p>
    );
  }
  const rows = (list: readonly UsageSourceInfo[]) => (
    <ul className="usage-sources">
      {list.map((s) => (
        <SourceRow key={s.descriptor.id} info={s} nowMs={nowMs} settingsHref={settingsHref} observed={hasObservation(s.descriptor.id)} lastSeen={s.last_observed_at ?? latestObservedAt?.(s.descriptor.id)} />
      ))}
    </ul>
  );
  // 시험용(`test_only`) 출처는 "개발용" 접힘 안에만 둔다.
  const normal = sources.filter((s) => !s.descriptor.test_only);
  const dev = sources.filter((s) => s.descriptor.test_only);
  return (
    <>
      {rows(normal)}
      {dev.length > 0 ? <Disclosure className="usage-dev-sources" summary={t.sources.devOnly(dev.length)}>{rows(dev)}</Disclosure> : null}
    </>
  );
}

function SourceRow({ info, nowMs, settingsHref, observed, lastSeen }: { info: UsageSourceInfo; nowMs: number; settingsHref: string; observed: boolean; lastSeen: number | undefined }) {
  const d = info.descriptor;
  // 연결 조각이 있는 출처의 안내는 화면 위쪽 연결 안내 패널이 맡는다(같은 글을 두 번 보이지 않는다).
  const guided = (d.setup_snippets?.length ?? 0) > 0;
  const hasHelp = Boolean(d.setup_help) && !guided;
  const [open, setOpen] = useState(!observed && hasHelp);
  const enabled = info.enabled !== false;
  const state = info.error ? t.sources.errorLine(info.error.message) : lastSeen == null ? t.sources.noValue : t.sources.ok;
  return (
    <li className="usage-source-row">
      <div className="usage-source-head">
        <strong>{d.title}</strong>
        <code className="app-mono app-muted">{d.id}</code>
        <TrustBadge trust={d.trust} label={t.trust[d.trust] ?? d.trust} />
        <span>{enabled ? t.sources.enabled : t.sources.disabled}</span>
        <span className="app-muted" title={formatDateTime(lastSeen)}>
          {lastSeen == null ? t.sources.neverSeen : t.sources.lastSeen(formatRelative(lastSeen, nowMs))}
        </span>
        <span className={info.error ? "runs-result-error" : "app-muted"}>{state}</span>
        <Link to={settingsHref}>{t.sources.changeInSettings}</Link>
      </div>
      {d.description ? <p className="app-muted usage-source-desc">{d.description}</p> : null}
      {guided ? <p className="app-muted usage-source-desc">{t.sources.setupInGuide}</p> : null}
      {hasHelp || d.docs_url ? (
        <div className="usage-setup">
          {hasHelp ? (
            <button type="button" className="app-link-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? "▾" : "▸"} {t.sources.setup}
            </button>
          ) : null}
          {open && hasHelp && d.setup_help ? (
            <div className="usage-setup-body">
              <Markdown text={d.setup_help} />
              <p className="app-muted">{t.sources.setupNote}</p>
            </div>
          ) : null}
          {d.docs_url && /^https?:\/\//.test(d.docs_url) ? (
            <a href={d.docs_url} target="_blank" rel="noreferrer noopener">{t.sources.docs}</a>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
