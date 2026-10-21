import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { InteractionCard, type FallbackArgs, type FieldError, type RenderEditor, type RendererComponent } from "@agent-console/chat";
import type { Interaction, InteractionKindDescriptor } from "@agent-console/contracts";
import { Button, StatusChip } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { messages as appMessages } from "../../app/messages";
import { formatDateTime, formatDuration } from "../../lib/format";
import { InteractionSchemaForm } from "../interactions";
import { runsMessages as t, interactionStateKey } from "./messages";
import { interactionStats, isInterruptedInteraction, sortInteractions, waitSeconds } from "./runsLib";

export interface InteractionsTabProps {
  interactions: readonly Interaction[];
  status: "loading" | "ready" | "error";
  onRetry(): void;
  kindOf(id: string): InteractionKindDescriptor | undefined;
  /** "PL" / "PL 안의 백엔드 리더" 같은 요청자 표기(앱이 계산) */
  actorLabel(i: Interaction): string;
  agentName(id: string): string;
  /** 현재 시각(epoch 초, 주입) */
  nowSec: number;
  onRespond(interaction: Interaction, response: unknown): Promise<void>;
  errorsOf(id: string): readonly FieldError[];
  /** 연결이 끊겼을 때 입력만 막는다 */
  disabled?: boolean;
  /** 끊김 카드의 [채팅에서 이어 말하기] 링크 대상(대화가 없으면 undefined) */
  conversationHref?: string;
  /** 노드 id로 필터(그래프 선택 연동). null이면 전체 */
  nodeFilter: string | null;
  /** 강조할 요청 id(스팬·노드에서 넘어온) */
  focusId?: string | null;
  renderEditor?: RenderEditor;
  renderers?: Record<string, RendererComponent>;
  /** 모르는 renderer용. 기본은 스키마 폼(`InteractionSchemaForm`) */
  renderFallback?: Parameters<typeof InteractionCard>[0]["renderFallback"];
  /** 자식 실행 안의 요청이면 요청자 옆 출처 칩(`자식 실행 r-7c1b · 팀`, 누르면 그 실행 화면). 이 실행 자신의 요청이면 undefined */
  contextChipOf?(i: Interaction): { text: string; title?: string; href?: string } | undefined;
  /** 목록 끝 안내(자식 실행의 지난 요청은 각 실행 화면에서 본다) */
  footer?: ReactNode;
}

const renderSchemaFallback = (args: FallbackArgs) => <InteractionSchemaForm {...args} className="runs-schema-form" actionsClassName="runs-span-links" />;

const STATE_FILTERS = ["all", "pending", "answered", "expired", "cancelled"] as const;

/** 탭 ④ 상호작용: 대기 중인 요청은 채팅과 같은 `InteractionCard`로 여기서도 답한다. 닫힌 요청은 대기 시간·응답자 한 줄 + 읽기 전용 카드. */
export function InteractionsTab(p: InteractionsTabProps) {
  const [state, setState] = useState<string>("all");
  const [actor, setActor] = useState("");

  const stats = useMemo(() => interactionStats(p.interactions), [p.interactions]);
  const actors = useMemo(() => [...new Set(p.interactions.map((i) => i.actor ?? "").filter((a) => a !== ""))], [p.interactions]);
  const list = useMemo(
    () =>
      sortInteractions(p.interactions).filter(
        (i) => (state === "all" || i.status === state) && (actor === "" || i.actor === actor) && (p.nodeFilter === null || i.node_id === p.nodeFilter || (i.node_path ?? []).includes(p.nodeFilter)),
      ),
    [p.interactions, state, actor, p.nodeFilter],
  );

  if (p.status === "loading" && p.interactions.length === 0) return <div className="app-loading" role="status">{t.interactions.loading}</div>;
  if (p.status === "error" && p.interactions.length === 0) return <ErrorBlock title={t.interactions.loadFailed} retryLabel={appMessages.common.retry} onRetry={p.onRetry} />;
  if (p.interactions.length === 0) return <div className="app-empty"><p>{t.interactions.empty}</p></div>;

  return (
    <div className="runs-interactions">
      <p className="runs-note" aria-live="polite">
        {t.interactions.summary(stats.total, stats.waiting, stats.avgWaitSec === undefined ? "" : formatDuration(stats.avgWaitSec * 1000))}
      </p>
      <div className="runs-interactions-tools" role="group" aria-label={t.interactions.filterLabel}>
        {STATE_FILTERS.map((s) => (
          <Button key={s} size="sm" variant={state === s ? "primary" : "secondary"} aria-pressed={state === s} onClick={() => setState(s)}>
            {t.interactions.stateFilters[s]}
          </Button>
        ))}
        <label className="runs-filter">
          <span className="app-muted">{t.interactions.actor}</span>
          <select value={actor} onChange={(e) => setActor(e.target.value)}>
            <option value="">{t.interactions.anyActor}</option>
            {actors.map((a) => (
              <option key={a} value={a}>{p.agentName(a)}</option>
            ))}
          </select>
        </label>
      </div>
      {list.length === 0 ? (
        <p className="app-muted" role="status">{t.interactions.noMatch}</p>
      ) : (
        <ul className="runs-interaction-list">
          {list.map((i) => {
            const pending = i.status === "pending";
            const key = interactionStateKey(i);
            const kind = p.kindOf(i.kind);
            return (
              <li key={i.id} className="runs-interaction" data-focus={p.focusId === i.id ? "true" : undefined} id={`interaction-${i.id}`}>
                {pending ? null : (
                  <div className="runs-interaction-meta">
                    <StatusChip status={key === "interrupted" ? "interrupted" : i.status === "answered" ? "succeeded" : i.status === "expired" ? "skipped" : "cancelled"} kind={key === "interrupted" ? "run" : "node"} label={t.interactions.states[key] ?? key} />
                    <span>{kind?.title ?? i.kind}</span>
                    <span className="app-muted">{p.actorLabel(i)}</span>
                    <span className="app-muted" title={formatDateTime(i.created_at)}>{t.interactions.requestedAt(formatDateTime(i.created_at))}</span>
                    <span className="ac-num">{t.interactions.waited(formatDuration(waitSeconds(i, p.nowSec) * 1000))}</span>
                    {i.answered_by ? <span>{t.interactions.responder(t.interactions.responders[i.answered_by] ?? i.answered_by)}</span> : null}
                    {i.close_reason ? <span className="app-muted">{t.interactions.closeReason(t.interactions.closeReasons[i.close_reason] ?? i.close_reason)}</span> : null}
                  </div>
                )}
                <InteractionCard
                  interaction={i}
                  descriptor={kind}
                  actorLabel={p.actorLabel(i)}
                  now={p.nowSec}
                  onRespond={(response) => p.onRespond(i, response)}
                  errors={p.errorsOf(i.id)}
                  {...(p.contextChipOf?.(i) ? { contextChip: p.contextChipOf(i)! } : {})}
                  {...(p.disabled !== undefined ? { disabled: p.disabled } : {})}
                  {...(p.renderEditor ? { renderEditor: p.renderEditor } : {})}
                  {...(p.renderers ? { renderers: p.renderers } : {})}
                  renderFallback={p.renderFallback ?? renderSchemaFallback}
                />
                {isInterruptedInteraction(i) ? (
                  <p className="app-muted runs-note">
                    {t.interactions.interruptedNote}
                    {p.conversationHref ? <> · <Link to={p.conversationHref}>{t.interactions.continueInChat}</Link></> : null}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {p.footer}
    </div>
  );
}
