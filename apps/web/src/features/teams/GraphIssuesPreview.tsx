import type { GraphSummary } from "@agent-console/contracts";
import { useApiQuery } from "../../app/queries";
import { IssuePreview } from "./ValidationChip";

/**
 * 팀 구성 하나의 검증 이슈 펼침(데이터 연결): `POST /graphs/{id}/validate`를 마운트 때 한 번 호출한다.
 * 저장된 상태만 있으므로(저장 안 된 편집은 편집기에서) 저장본 기준이다.
 */
export function GraphIssuesPreview({ graph }: { graph: GraphSummary }) {
  const q = useApiQuery(["graph-issues", graph.id, graph.version_hash ?? ""], (rest) => rest.validateGraph(graph.id), { staleTime: 0, retry: false });
  return (
    <IssuePreview
      issues={q.data}
      loading={q.isLoading}
      failed={q.isError}
      blocked={graph.validation?.blocks_run === true}
      codes={graph.validation?.codes}
      onRetry={() => void q.refetch()}
    />
  );
}
