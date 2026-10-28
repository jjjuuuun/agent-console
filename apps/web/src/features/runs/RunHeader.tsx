import { FixButtons } from "../../app/fix";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Run } from "@agent-console/contracts";
import { Banner, Button, MiddleEllipsis, StatusChip } from "@agent-console/ui";
import { formatCount, formatElapsed, formatDuration } from "../../lib/format";
import { runStatusLabels, runsMessages as t } from "./messages";
import { CANCELLABLE_RUN_STATUSES, EVENT_IDLE_SECONDS, INTERRUPTED_RUN_STATUS, WAITING_RUN_STATUS } from "./runsConfig";
import { formatTokensShort, runDurationMs, totalTokens } from "./runsLib";

export interface RunHeaderProps {
  run: Run;
  nowSec: number;
  graphName: string | undefined;
  graphHref: string;
  listHref: string;
  conversation?: { title: string; href: string };
  nodeProgress: { done: number; total: number };
  /** 사용자 대기 누적(초). 0이면 문구 생략 */
  userWaitSeconds: number;
  waitingCount: number;
  /** 서브에이전트 사용량이 합계에 섞였을 수 있는지(안내 문구용) */
  hasSubagents: boolean;
  runningNode?: { id: string; label: string };
  failedNode?: { id: string; label: string };
  onFocusNode(id: string): void;
  onSeeInteractions(): void;
  onCancel(): void;
  cancelling: boolean;
  /** 실시간 연결이 끊겼는가 */
  disconnected: boolean;
  /** 마지막 이벤트로부터 지난 초(없으면 undefined) */
  idleSeconds: number | undefined;
  /** 자식 실행의 위치(`RunBreadcrumb`). 루트 실행이면 생략 */
  breadcrumb?: ReactNode;
  /** 자식 실행이면 상위 실행 링크 한 줄과 [상위 실행에서 취소 ↗](자식에는 취소 단추가 없다, D4) */
  parent?: { text: string; href: string; openLabel: string; cancelLabel: string };
  /** "자식 실행 n개 ▾"(`ChildRunsMenu`). 자식이 없으면 생략 */
  childMenu?: ReactNode;
  /** 응답 대기 배너 뒤에 붙는 문구("응답 대기 n건(자식 실행 포함)") */
  waitingSuffix?: string | undefined;
  /** 중단 배너에 더하는 문구("자식 실행도 중단되었습니다") */
  interruptedNote?: string | undefined;
  /** 둘째 줄 끝에 붙는 칩 자리(다른 기능이 꽂는다, 예: 메모리 쓰기·읽기 칩) */
  extra?: ReactNode;
  /** 보조 줄 문구: 자식 실행 실패 요약, 실패 처리됨 등 */
  notes?: readonly { key: string; text: string; tone: "danger" | "info" }[];
}

/** 실행 상세 헤더(2줄) + 상태별 배너. 데이터·콜백은 props. */
export function RunHeader(p: RunHeaderProps) {
  const { run } = p;
  const cancellable = CANCELLABLE_RUN_STATUSES.includes(run.status);
  const waiting = run.status === WAITING_RUN_STATUS;
  const statusLabel = runStatusLabels[run.status] ?? run.status;
  const elapsed = runDurationMs(run, p.nowSec);
  const totals = run.totals;
  const tokenText = totals && (totals.input_tokens != null || totals.output_tokens != null)
    ? t.detail.tokens(formatCount(totals.input_tokens), formatCount(totals.output_tokens))
    : totalTokens(totals) !== undefined
      ? t.detail.tokensTotalOnly(formatTokensShort(totalTokens(totals)))
      : undefined;
  const showIdle = !waiting && cancellable && p.idleSeconds !== undefined && p.idleSeconds >= EVENT_IDLE_SECONDS;
  return (
    <div className="runs-header">
      <div className="runs-header-line">
        <Link to={p.listHref} className="app-back">← {t.detail.back}</Link>
        <h1 className="runs-header-title app-mono" aria-label={run.id}><MiddleEllipsis value={run.id} copyLabel={t.detail.copyRunId} /></h1>
        <StatusChip status={run.status} kind="run" label={statusLabel} />
        {p.disconnected ? <span className="runs-ws-chip" role="status">{t.detail.wsDown}</span> : null}
        <span className="ac-ellipsis">
          <Link to={p.graphHref}>{p.graphName ?? run.graph_id}</Link>
          {p.conversation ? <> · <Link to={p.conversation.href}>{p.conversation.title}</Link></> : null}
        </span>
        <span className="app-spacer" />
        {p.parent !== undefined ? <Link className="ac-btn" data-variant="secondary" data-size="sm" to={p.parent.href}>{p.parent.cancelLabel}</Link> : null}
        {run.status !== INTERRUPTED_RUN_STATUS && !cancellable ? <Link className="ac-btn" data-variant="ghost" data-size="sm" to={p.graphHref}>{t.detail.editGraph}</Link> : null}
        {cancellable && p.parent === undefined ? (
          <Button variant="danger" size="sm" loading={p.cancelling} onClick={p.onCancel}>
            {p.cancelling ? t.detail.cancelling : t.detail.cancel}
          </Button>
        ) : null}
      </div>
      {p.breadcrumb !== undefined ? <div className="runs-header-line">{p.breadcrumb}</div> : null}
      {p.parent !== undefined ? (
        <div className="runs-header-line app-muted">
          <span>{p.parent.text}</span>
          <Link to={p.parent.href} className="app-link-btn">{p.parent.openLabel}</Link>
        </div>
      ) : null}
      <div className="runs-header-line app-muted">
        <span className="ac-num">
          {t.detail.elapsed(elapsed === undefined ? "–" : formatElapsed(elapsed))}
          {p.userWaitSeconds > 0 ? ` ${t.detail.elapsedWait(formatDuration(p.userWaitSeconds * 1000))}` : ""}
        </span>
        <span className="ac-num">{t.detail.nodes(p.nodeProgress.done, p.nodeProgress.total)}</span>
        {tokenText ? <span className="ac-num">{tokenText}</span> : null}
        {p.hasSubagents ? <span title={t.detail.subagentNote}>ⓘ {t.detail.subagentNote}</span> : null}
        {p.runningNode ? <button type="button" className="app-link-btn" onClick={() => p.onFocusNode(p.runningNode!.id)}>{t.detail.running(p.runningNode.label)}</button> : null}
        {showIdle ? <span>{t.detail.idle(Math.floor(p.idleSeconds!))}</span> : null}
        {p.childMenu}
        {p.extra}
        {(p.notes ?? []).map((n) => (
          <span key={n.key} className="runs-header-note" data-tone={n.tone} role="status">
            <span aria-hidden="true">{n.tone === "danger" ? "▲ " : "ⓘ "}</span>
            {n.text}
          </span>
        ))}
      </div>
      {run.status === "failed" && (run.error || p.failedNode) ? (
        <Banner tone="danger" title={t.detail.errorSummary} actions={<>{p.failedNode ? <Button size="sm" onClick={() => p.onFocusNode(p.failedNode!.id)}>{t.detail.failedNode}</Button> : null}<FixButtons fix={run.error?.fix} /></>}>
          {run.error?.message}
        </Banner>
      ) : null}
      {waiting || p.waitingCount > 0 ? (
        <Banner tone="warning" actions={<Button size="sm" onClick={p.onSeeInteractions}>{t.detail.waitingBannerAction}</Button>}>
          {t.detail.waitingBanner(p.waitingCount)}
          {p.waitingSuffix ? ` (${p.waitingSuffix})` : ""}
        </Banner>
      ) : null}
      {run.status === INTERRUPTED_RUN_STATUS ? <Banner tone="info">{t.detail.interruptedBanner}{p.interruptedNote ? ` ${p.interruptedNote}` : ""}</Banner> : null}
    </div>
  );
}
