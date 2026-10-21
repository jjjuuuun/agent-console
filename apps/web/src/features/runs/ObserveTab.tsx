import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { RunEvent } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { messages as appMessages } from "../../app/messages";
import { runsMessages as t } from "./messages";
import { buildObserveRows, formatMs, observeStats, type ObserveRow } from "./runsLib";

export interface ObserveTabProps {
  events: readonly RunEvent[];
  status: "loading" | "ready" | "error";
  onRetry(): void;
  /** 모을 이벤트 type 접두(앱 설정 데이터) */
  prefixes: readonly string[];
  agentName(id: string): string;
  startedAt: number | undefined;
  /** 설정 화면 경로(빈 상태 안내 링크) */
  settingsHref: string;
  /** 행의 위임 흐름 span 보기(tool_use_id가 있을 때) */
  onSeeTrace?(toolUseId: string): void;
}

/** 탭 ③ hook·MCP: 접두 세그먼트(데이터에서 생성) + 표 + 집계 줄 + 상세 드로어. 비밀은 서버가 가리며 화면에서 다시 가공하지 않는다. */
export function ObserveTab(p: ObserveTabProps) {
  const [prefix, setPrefix] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [actor, setActor] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const all = useMemo(() => buildObserveRows(p.events, p.prefixes), [p.events, p.prefixes]);
  const present = useMemo(() => [...new Set(all.map((r) => r.prefix))], [all]);
  const actors = useMemo(() => [...new Set(all.map((r) => r.event.actor ?? "").filter((a) => a !== ""))], [all]);
  const rows = useMemo(() => all.filter((r) => (prefix === "" || r.prefix === prefix) && (!errorsOnly || r.error) && (actor === "" || r.event.actor === actor)), [all, prefix, errorsOnly, actor]);
  const stats = useMemo(() => observeStats(rows), [rows]);

  if (p.status === "loading" && p.events.length === 0) return <div className="app-loading" role="status">{t.observe.loading}</div>;
  if (p.status === "error" && p.events.length === 0) return <ErrorBlock title={t.observe.loadFailed} retryLabel={appMessages.common.retry} onRetry={p.onRetry} />;
  if (all.length === 0) {
    return (
      <div className="app-empty">
        <p>{t.observe.empty}</p>
        <Link to={p.settingsHref}>{t.observe.openSettings}</Link>
      </div>
    );
  }

  const selectedRow = selected === null ? undefined : rows.find((r) => r.event.seq === selected);
  const name = (x: string) => x.replace(/\.$/, "");
  const statLine = t.observe.stats(
    Object.entries(stats.byPrefix)
      .map(([k, n]) => t.observe.statPart(name(k), n))
      .join(" · "),
    stats.errors,
    stats.avgMs === undefined ? "" : formatMs(stats.avgMs),
  );

  return (
    <div className="runs-observe">
      <div className="runs-observe-tools">
        <div role="group" aria-label={t.observe.segmentLabel} className="runs-segment">
          {["", ...present].map((x) => (
            <Button key={x} size="sm" variant={prefix === x ? "primary" : "secondary"} aria-pressed={prefix === x} onClick={() => setPrefix(x)}>
              {x === "" ? t.observe.all : name(x)}
            </Button>
          ))}
        </div>
        <label className="app-check"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />{t.observe.errorsOnly}</label>
        <label className="runs-filter">
          <span className="app-muted">{t.observe.actor}</span>
          <select value={actor} onChange={(e) => setActor(e.target.value)}>
            <option value="">{t.observe.anyActor}</option>
            {actors.map((a) => (
              <option key={a} value={a}>{p.agentName(a)}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="app-muted runs-note" aria-live="polite">{statLine}</p>
      {rows.length === 0 ? (
        <p className="app-muted" role="status">{t.observe.noMatch}</p>
      ) : (
        <table className="app-table" aria-label={t.observe.tableLabel}>
          <thead>
            <tr>
              <th scope="col">{t.observe.columns.time}</th>
              <th scope="col">{t.observe.columns.actor}</th>
              <th scope="col">{t.observe.columns.kind}</th>
              <th scope="col">{t.observe.columns.duration}</th>
              <th scope="col">{t.observe.columns.result}</th>
              <th scope="col">{t.observe.columns.summary}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <ObserveRowView key={r.event.seq} row={r} start={p.startedAt} agentName={p.agentName} selected={selected === r.event.seq} onSelect={() => setSelected(r.event.seq)} />
            ))}
          </tbody>
        </table>
      )}
      {selectedRow ? (
        <aside className="runs-drawer" aria-label={t.observe.detail}>
          <h3 className="app-block-subtitle">{selectedRow.event.type}</h3>
          <pre className="ac-pre app-wrap runs-event-json">{JSON.stringify({ payload: selectedRow.event.payload, raw: selectedRow.event.raw }, null, 2)}</pre>
          <div className="runs-span-links">
            {typeof selectedRow.event.payload?.["tool_use_id"] === "string" && p.onSeeTrace ? (
              <Button size="sm" onClick={() => p.onSeeTrace?.(selectedRow.event.payload?.["tool_use_id"] as string)}>{t.observe.toTrace}</Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>{t.observe.detailClose}</Button>
          </div>
        </aside>
      ) : null}
    </div>
  );
}

function ObserveRowView({ row, start, agentName, selected, onSelect }: { row: ObserveRow; start: number | undefined; agentName(id: string): string; selected: boolean; onSelect(): void }) {
  const e = row.event;
  const d = e.ts - (start ?? e.ts);
  return (
    <tr
      tabIndex={0}
      aria-selected={selected}
      data-error={row.error ? "true" : undefined}
      onClick={onSelect}
      onKeyDown={(ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          onSelect();
        }
      }}
    >
      <td className="ac-num">{`+${d.toFixed(1)}s`}</td>
      <td className="ac-ellipsis">{e.actor ? agentName(e.actor) : "–"}</td>
      <td className="ac-ellipsis" title={e.type}>
        <code className="app-mono">{e.type}</code> {row.kind}
      </td>
      <td className="ac-num">{row.durationMs === undefined ? "–" : formatMs(row.durationMs)}</td>
      <td>
        <span className={row.error ? "runs-result-error" : undefined}>{row.error ? `▲ ${t.observe.error}` : `✓ ${t.observe.ok}`}</span>
      </td>
      <td className="ac-ellipsis">{row.summary}</td>
    </tr>
  );
}
