import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import { teamMessages as t } from "./messages";
import { incomingInvocations, nodeLabel, nodesOf, strategyOfInvocation } from "./teamsLogic";

/**
 * 위임 방식이 쓰지 않는 필드의 이유 줄 문구 -> `SchemaForm.disabledPaths`(경로 -> 이유).
 * 위임자(들어오는 호출 연결의 시작 노드)와 방식 이름을 문구에 넣는다. 방식을 모르면 일반 문구.
 * 5.7R.38이 만들고 5.7R.34(연결 패널)가 같은 문구로 다시 쓴다.
 */
export function ignoredFieldReasons(
  inapplicable: readonly string[],
  nodeId: string,
  graph: Graph,
  edgeTypes: readonly EdgeTypeDescriptor[],
  strategies: readonly DelegationStrategyDescriptor[],
): Record<string, string> {
  const first = incomingInvocations(nodeId, graph, edgeTypes)[0];
  const strategy = first === undefined ? undefined : strategies.find((s) => s.id === strategyOfInvocation(first.edge, first.kind));
  const delegator = first === undefined ? undefined : nodesOf(graph).find((n) => n.id === first.edge.source.node);
  const reason =
    strategy === undefined ? t.settings.inapplicableGeneric : t.settings.inapplicable(strategy.title, delegator === undefined ? undefined : nodeLabel(delegator));
  return Object.fromEntries(inapplicable.map((p) => [p, reason]));
}

/** `/a/b` 위치의 값이 객체 안에 있는가 */
function hasPointer(root: Record<string, unknown>, pointer: string): boolean {
  let cur: unknown = root;
  for (const k of pointer.replace(/^\//, "").split("/")) {
    if (cur === null || typeof cur !== "object" || !(k in (cur as Record<string, unknown>))) return false;
    cur = (cur as Record<string, unknown>)[k];
  }
  return true;
}

export interface IgnoredValueClearProps {
  /** 비활성 경로 -> 이유 줄(`ignoredFieldReasons` 결과) */
  reasons: Record<string, string>;
  /** 노드가 직접 가진 값(덮어쓰기). 여기에 값이 있는 경로만 [비우기]가 나온다(출처를 모르면 숨김) */
  ownValue: Record<string, unknown>;
  /** 노드 설정이 아닌 다른 층에서 온 값은 지울 수 없으므로 호출자가 필드 라벨을 준다 */
  labelOf?: (path: string) => string;
  disabled?: boolean;
  onClear: (path: string) => void;
}

/** 무시되지만 노드에 값이 남은 필드 목록과 [비우기] 버튼(노드 덮어쓰기 값일 때만). 없으면 아무것도 그리지 않는다. */
export function IgnoredValueClear({ reasons, ownValue, labelOf, disabled, onClear }: IgnoredValueClearProps) {
  const paths = Object.keys(reasons).filter((p) => hasPointer(ownValue, p));
  if (paths.length === 0) return null;
  return (
    <ul className="team-ignored-list" aria-label={t.settings.ignoredClear}>
      {paths.map((p) => (
        <li key={p}>
          <span className="lib-mono">{labelOf?.(p) ?? p}</span> <span className="app-muted">{reasons[p]}</span>{" "}
          <Button size="sm" variant="secondary" disabled={disabled === true} onClick={() => onClear(p)}>{t.settings.ignoredClear}</Button>
        </li>
      ))}
    </ul>
  );
}
