import type { Agent, DelegationStrategyDescriptor, EdgeTypeDescriptor, Graph, InteractionKindDescriptor, Issue, IssueSuggestion, NodeTypeDescriptor, ResourceSummary, ResourceTypeDescriptor, TeamPlanSummary, WorkspaceSettings } from "@agent-console/contracts";
import type { NestedInfo } from "../delegation";
import type { DraftPreviewResult } from "./useDraftPreview";

/** 오른쪽 패널들이 공유하는 읽기 전용 데이터와 편집 콜백. 서버·라우터를 모르고, 컨테이너(`TeamEditorPage`)가 채운다. */
export interface TeamPanelContext {
  graphId: string;
  /** 편집 중인 초안 */
  graph: Graph;
  /** 서버에 저장된 노드 id(저장 전 노드는 유효 설정을 계산할 수 없다) */
  savedNodeIds: ReadonlySet<string>;
  /** 저장된 문서의 버전(저장하면 바뀐다 → 유효 설정을 다시 읽는다) */
  savedVersion: string | undefined;
  dirty: boolean;
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  agents: readonly Agent[];
  resources: readonly ResourceSummary[];
  resourceTypes: readonly ResourceTypeDescriptor[];
  interactionKinds: readonly InteractionKindDescriptor[];
  strategies: readonly DelegationStrategyDescriptor[];
  /** 공통 설정(읽기 전용) */
  workspace: WorkspaceSettings | undefined;
  issues: readonly Issue[];
  /** 계획 요약(입구·답변 자리·허용 노드). 로딩·실패 상태를 함께 준다 */
  plan: DraftPreviewResult<TeamPlanSummary>;
  /** 저장이 거부된 사유(문서 기준 경로의 필드 오류). 첨부 줄 등에 표시한다 */
  fieldErrors?: readonly { path: string; message: string }[];
  disabled: boolean;
  /** 초안 그래프를 바꾼다(편집기 `onChange`와 같은 정리를 거친다) */
  onGraphChange: (next: Graph) => void;
  /** 되돌리기 가능한 변경(토스트의 [되돌리기]가 이전 그래프로 돌린다) */
  onUndoableChange: (next: Graph, text: string) => void;
  onApplySuggestion: (issue: Issue, suggestion: IssueSuggestion) => void;
  /** 이 노드의 번들 미리보기를 연다 */
  onPreviewBundle: (nodeId: string) => void;
  /** 다른 화면으로(저장 안 됨이면 이탈 확인은 `UnsavedGuard`가 한다) */
  navigateTo: (path: string) => void;
  /**
   * 중첩 노드(`binds.kind`가 지금 편집 중인 정의 종류와 같은 노드) 문맥. 후보 정의 정보와 [열기]. 없으면 중첩 노드 표시를 하지 않는다.
   * `open`이 없으면(정의 종류 라우트가 없음) [열기]만 숨는다.
   */
  nested?: { currentKind: string | undefined; infos: readonly NestedInfo[] | undefined; kindTitle: string | undefined; open: ((id: string) => void) | undefined };
}
