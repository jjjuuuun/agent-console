import { useState } from "react";
import type { ConditionOperatorDescriptor } from "@agent-console/contracts";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { actualPreview, delegationMessages as dm, formatRunOrdinal, type ConditionOutcomeView } from "../delegation";
import type { EdgeRecord, EdgeStatus } from "./edgeRecords";

export interface EdgeJudgementViewProps {
  fromLabel: string;
  toLabel: string;
  /** 연결 종류 제목과 추가 칩 글자(조건 요약·반복 한도 등). 편집기와 같은 문구 */
  kindTitle: string;
  chips: readonly string[];
  status: EdgeStatus;
  /** 마지막 평가 시각 문구 */
  statusTime?: string | undefined;
  /** 통과 횟수(순번 ②처럼 보일 때) */
  passes: number;
  /** 조건 근거: 해석한 모양 / 해석 불가(null) / 근거 없음(undefined) */
  condition?: ConditionOutcomeView | null | undefined;
  /** 해석할 수 없는 근거의 원본(JSON 폴백) */
  rawCondition?: unknown;
  /** 연산자 목록(없으면 연산자 id 그대로) */
  operators: readonly Pick<ConditionOperatorDescriptor, "id" | "title">[] | null;
  records: readonly EdgeRecord[];
  /** 반복 연결이면 회차 열과 "→ 도착 노드 n회차 시작" 링크를 보인다 */
  isCycle: boolean;
  timeText(ts: number): string;
  nodeLabel(nodeId: string): string;
  /** "→ 작성자 2회차 시작" 링크: 그 노드를 선택하고 그 회차 실행을 고정 */
  onSeeIteration?(nodeId: string, iteration: number): void;
  loading?: boolean;
  failed?: boolean;
  onRetry?(): void;
}

function Raw({ value }: { value: unknown }) {
  const text = (() => {
    try {
      return JSON.stringify(value, null, 2) ?? String(value);
    } catch {
      return String(value);
    }
  })();
  return <pre className="ac-pre app-json" style={{ maxHeight: "12em", overflow: "auto" }}>{text}</pre>;
}

/**
 * 연결 상세(실행 상세 노드·연결 탭, screen-delegation.md 3.3.3): 상태, 판정 근거(항목별 충족/불충족 + 실제 값), 지나간 기록.
 * 조건 근거 payload는 어댑터(`mapConditionOutcome`)가 푼 모양만 받고, 해석할 수 없으면 원본 JSON을 보인다. 읽기 전용이다.
 */
export function EdgeJudgementView(p: EdgeJudgementViewProps) {
  const [full, setFull] = useState<{ title: string; text: string } | null>(null);
  const opTitle = (id: string) => p.operators?.find((o) => o.id === id)?.title ?? id;
  const j = dm.run.judgement;
  if (p.loading) return <div className="app-loading" role="status">{j.loading}</div>;
  if (p.failed) {
    return (
      <Banner tone="danger" actions={p.onRetry ? <Button size="sm" onClick={p.onRetry}>{dm.condition.operatorRetry}</Button> : undefined}>
        {j.failed}
      </Banner>
    );
  }
  const statusText =
    p.status === "passed" ? `✓ ${j.passed}${p.passes > 1 ? ` ×${p.passes}` : ""}` : p.status === "skipped-condition" ? j.skippedCondition : p.status === "skipped-upstream" ? j.skippedUpstream : j.notYet;
  return (
    <div className="dlg-judge">
      <h3 className="app-block-subtitle">{j.title(p.fromLabel, p.toLabel)}</h3>
      <div className="dlg-crumbs" aria-label={p.kindTitle}>
        <span className="dlg-from-chip">{p.kindTitle}</span>
        {p.chips.map((c, i) => <span key={i} className="dlg-from-chip">{c}</span>)}
      </div>
      <p role="status">
        <strong>{j.state}:</strong> {statusText}
        {p.statusTime ? <span className="app-muted"> · {p.statusTime}</span> : null}
      </p>
      {p.status === "none" ? null : (
        <>
          {p.condition !== undefined ? (
            <section aria-label={j.basis}>
              <span className="lib-field-label">{j.basis}</span>
              {p.condition === null ? (
                <>
                  <p className="app-muted dlg-note">{j.rawFallback}</p>
                  <Raw value={p.rawCondition} />
                </>
              ) : (
                <>
                  <p>
                    {j.resultLine(p.condition.combinator === "any" ? j.any : p.condition.combinator === "all" ? j.all : "", p.condition.result ? j.resultPass : j.resultSkip)}
                    {p.condition.negate === true ? <span className="app-muted"> {j.negated}</span> : null}
                  </p>
                  <ul className="team-problem-list">
                    {(p.condition.items ?? []).map((item, i) => {
                      const actual = item.hasActual ? actualPreview(item.actual) : undefined;
                      return (
                        <li key={i} className="dlg-judge-item">
                          <span className="dlg-judge-icon" data-ok={item.result} aria-label={item.result ? j.itemOk : j.itemNo}>{item.result ? "✓" : "✕"}</span>
                          <span className="app-mono">{item.path}</span>
                          <span>{opTitle(item.op)}</span>
                          {item.value !== undefined ? <span className="app-mono">{typeof item.value === "string" ? `‘${item.value}’` : JSON.stringify(item.value)}</span> : null}
                          {actual !== undefined ? (
                            <span className="dlg-actual">
                              {j.actual} “{actual.text}”
                              {actual.truncated ? <> <button type="button" className="app-link-btn" onClick={() => setFull({ title: `${item.path} ${j.actual}`, text: actual.full })}>{j.showFull}</button></> : null}
                            </span>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </section>
          ) : null}
          <section aria-label={j.history}>
            <span className="lib-field-label">{j.history}</span>
            <div className="dlg-runlist-wrap">
              <table className="dlg-runlist">
                <thead>
                  <tr>
                    <th scope="col">{j.colSeq}</th>
                    <th scope="col">{j.colTime}</th>
                    {p.isCycle ? <th scope="col">{j.colIter}</th> : null}
                    <th scope="col">{j.colResult}</th>
                  </tr>
                </thead>
                <tbody>
                  {p.records.map((r) => (
                    <tr key={r.seq}>
                      <td className="ac-num">{r.seq}</td>
                      <td className="ac-num">{p.timeText(r.ts)}</td>
                      {p.isCycle ? <td>{r.kind === "iteration" ? formatRunOrdinal(r.iteration, "iteration") : "–"}</td> : null}
                      <td>
                        {r.kind === "passed" ? `✓ ${j.passed}` : r.kind === "skipped" ? (r.condition != null ? j.conditionFalse : j.skippedUpstream) : null}
                        {r.kind === "iteration" ? (
                          <button type="button" className="app-link-btn" onClick={() => p.onSeeIteration?.(r.nodeIds[0] ?? "", r.iteration)}>
                            {j.startsAt(r.nodeIds.map(p.nodeLabel).join(", "), formatRunOrdinal(r.iteration, "iteration"))}
                          </button>
                        ) : null}
                        {r.kind === "exhausted" ? <span className="dlg-warn">▲ {r.maxIterations === undefined ? j.exhaustedNoLimit : j.exhausted(r.maxIterations)}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
      <Dialog open={full !== null} title={full?.title ?? j.fullTitle} onClose={() => setFull(null)} wide actions={<Button onClick={() => setFull(null)}>{j.close}</Button>}>
        <pre className="ac-pre app-json" style={{ maxHeight: "60vh", overflow: "auto" }}>{full?.text}</pre>
      </Dialog>
    </div>
  );
}
