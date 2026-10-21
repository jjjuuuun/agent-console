import { useMemo, type ReactNode } from "react";
import { GraphEditor, type BindSummary, type NodeAvatar, type ChipView, type EdgeBadge, type NodeRunBadge, type Selection } from "@agent-console/graph-editor";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, Graph, NodeTypeDescriptor, PortSpec } from "@agent-console/contracts";
import { Banner } from "@agent-console/ui";
import { runsMessages as t } from "./messages";
import type { RunOverlay } from "./runsLib";

export interface RunGraphPaneProps {
  graph: Graph;
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  overlay: RunOverlay;
  /** 실행 당시 버전이 아닌 현재 버전을 그리고 있는가 */
  versionMissing: boolean;
  showResources: boolean;
  onShowResourcesChange(show: boolean): void;
  onSelectNode(nodeId: string | null): void;
  /** 연결을 골랐을 때(노드·연결 탭에 연결 상세). 노드를 고르면 `null` */
  onSelectEdge?(edgeId: string | null): void;
  /** 노드 회차·호출 배지(실행이 2개 이상인 노드만) */
  nodeRunBadges?: Readonly<Record<string, NodeRunBadge>>;
  /** 연결 배지(`↻×2`·한도 도달·`✕`) */
  edgeBadges?: Readonly<Record<string, readonly EdgeBadge[]>>;
  /** 연결 위 추가 칩(종류 속성에서 온 반복 한도·조건 요약; 편집기와 같은 문구) */
  edgeExtraChips?: Readonly<Record<string, readonly ChipView[]>>;
  /** 중첩 노드 카드의 자식 실행 한 줄과 [열기 ↗] */
  bindSummaries?: Readonly<Record<string, BindSummary>>;
  /** 노드별 아바타(에이전트 표시 설정에서 해석한 결과) */
  nodeAvatars?: Readonly<Record<string, NodeAvatar>>;
  delegationStrategies?: readonly Pick<DelegationStrategyDescriptor, "id">[];
  edgeStrategyIds?: Readonly<Record<string, string>>;
  renderIcon?: (name: string) => ReactNode;
  /** 노드 헤더에 더하는 텍스트 배지(예: 처리됨). 서브에이전트 호출 횟수 배지와 합쳐 보인다 */
  extraNodeBadges?: Readonly<Record<string, readonly string[]>>;
  focusRequest?: { nodeId: string; token: number };
  nowMs: number;
  /** 동적 포트 노드의 포트 계산(편집기와 같은 함수). 없으면 계산하지 못했다고 표시된다. */
  resolvePorts?: ((typeId: string, config: unknown) => Promise<PortSpec>) | undefined;
  showMinimap?: boolean;
}

/** 실행 상태를 얹은 읽기 전용 팀 구성 그래프. 상태·강조는 모두 props(`overlay`)로 받는다. */
export function RunGraphPane(p: RunGraphPaneProps) {
  const { overlay } = p;
  const badges = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const [id, n] of Object.entries(overlay.subagentCalls)) if (n > 1) out[id] = [t.common.callCount(n)];
    for (const [id, list] of Object.entries(p.extraNodeBadges ?? {})) out[id] = [...(out[id] ?? []), ...list];
    return out;
  }, [overlay.subagentCalls, p.extraNodeBadges]);
  return (
    <div className="runs-graph" role="region" aria-label={t.detail.graphLabel}>
      {p.versionMissing ? <Banner tone="info">{t.detail.versionMissing}</Banner> : null}
      <div className="runs-graph-canvas">
        <GraphEditor
          mode="readonly-run"
          graph={p.graph}
          nodeTypes={p.nodeTypes}
          edgeTypes={p.edgeTypes}
          nodeStates={overlay.nodeStates}
          edgeStates={overlay.edgeStates}
          edgeOrder={overlay.edgeOrder}
          edgeCounts={overlay.edgeCounts}
          waitingNodes={overlay.waitingNodes}
          nodeBadgesOverride={badges}
          showResources={p.showResources}
          onShowResourcesChange={p.onShowResourcesChange}
          showMinimap={p.showMinimap ?? false}
          nowMs={p.nowMs}
          {...(p.resolvePorts ? { resolvePorts: p.resolvePorts } : {})}
          onSelectionChange={(sel: Selection) => {
            // URL을 바꾸는 호출은 한 번만 한다(라우터의 검색 인자 갱신은 같은 틱 안에서 서로 덮어쓴다):
            // 연결만 골랐으면 연결 선택, 그 밖에는 노드 선택(노드를 고르면 연결 선택은 거기서 풀린다), 비웠으면 둘 다 비운다
            if (sel.nodeIds.length === 0 && sel.edgeIds.length > 0 && p.onSelectEdge) {
              p.onSelectEdge(sel.edgeIds[0]!);
              return;
            }
            p.onSelectNode(sel.nodeIds[0] ?? null);
            if (sel.nodeIds.length === 0) p.onSelectEdge?.(null);
          }}
          {...(p.nodeRunBadges ? { nodeRunBadges: p.nodeRunBadges } : {})}
          {...(p.edgeBadges ? { edgeBadges: p.edgeBadges } : {})}
          {...(p.edgeExtraChips ? { edgeExtraChips: p.edgeExtraChips } : {})}
          {...(p.bindSummaries ? { bindSummaries: p.bindSummaries } : {})}
          {...(p.nodeAvatars ? { nodeAvatars: p.nodeAvatars } : {})}
          {...(p.delegationStrategies ? { delegationStrategies: p.delegationStrategies } : {})}
          {...(p.edgeStrategyIds ? { edgeStrategyIds: p.edgeStrategyIds } : {})}
          {...(p.renderIcon ? { renderIcon: p.renderIcon } : {})}
          {...(p.focusRequest ? { focusRequest: p.focusRequest } : {})}
        />
      </div>
    </div>
  );
}
