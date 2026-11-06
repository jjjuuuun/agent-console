import type { DelegationStrategyDescriptor } from "@agent-console/contracts";
import { KNOWN_DELEGATION_SESSIONS as SESSIONS } from "@agent-console/contracts/constants";
import { SessionChip, attributeRows } from "../delegation";
import { teamMessages } from "./messages";
import type { NodeSessionMode } from "./sessionView";

const m = teamMessages.sessions;

export interface SessionWhereProps {
  mode: NodeSessionMode;
  strategies: readonly DelegationStrategyDescriptor[];
  /** [연결 보기]: 그 연결을 고른다(위임자 노드 id와 함께). 없으면 단추가 숨는다 */
  onViewEdge?: (edgeId: string, sourceNodeId: string) => void;
}

/**
 * 노드 패널 "역할" 탭 첫 줄: 같은 세션 안에서 실행되면 "실행 위치: {위임자} 세션 안 · {백엔드 문구}"와 [연결 보기],
 * 같은 세션과 다른 세션이 섞였으면 연결별 세션 목록. 별도 세션뿐이면 아무것도 그리지 않는다. 문구는 모두 메시지 표와 디스크립터 값이다.
 */
export function SessionWhere({ mode, strategies, onViewEdge }: SessionWhereProps) {
  if (mode.mode === "none") return null;
  if (mode.mode === "mixed") {
    return (
      <section className="ses-where" data-session-where="mixed" aria-label={m.nodeSessionList}>
        <span className="lib-field-label">{m.nodeSessionList}</span>
        <ul className="team-problem-list">
          {mode.items.map((i) => (
            <li key={i.edge.id}>
              <SessionChip value={i.session} delegatorLabel={i.delegatorLabel} /> {i.delegatorLabel}{" "}
              {onViewEdge === undefined ? null : (
                <button type="button" className="app-link-btn" onClick={() => onViewEdge(i.edge.id, i.delegatorId)}>{m.nodeViewEdge}</button>
              )}
            </li>
          ))}
        </ul>
      </section>
    );
  }
  const first = mode.delegators[0] ?? "";
  const line = mode.delegators.length > 1 ? m.nodeRoleMore(first, mode.delegators.length - 1) : m.nodeRole(first);
  const strategy = mode.strategyId === undefined ? undefined : strategies.find((s) => s.id === mode.strategyId);
  const backend = attributeRows(strategy, first).find((r) => r.key === "backend");
  return (
    <section className="ses-where" data-session-where="same" aria-label={m.nodeRole(first)}>
      <p className="ses-where-line">
        <SessionChip value={SESSIONS.SAME} delegatorLabel={first} /> {line}
        {backend === undefined ? null : <>{m.nodeBackendSep}{backend.long}</>}{" "}
        {onViewEdge === undefined ? null : (
          <button type="button" className="app-link-btn" onClick={() => onViewEdge(mode.edgeId, mode.delegatorId)}>{m.nodeViewEdge}</button>
        )}
      </p>
    </section>
  );
}
