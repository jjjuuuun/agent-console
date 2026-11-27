import type { GraphSummary } from "@agent-console/contracts";
import { useApiQuery } from "../../app/queries";
import { useStartErrorView } from "../projects";
import { IssuePreview } from "./ValidationChip";

/**
 * 팀 구성 하나의 검증 이슈 펼침(데이터 연결): `POST /graphs/{id}/validate`(project가 있으면 `?project=`)를 마운트 때 한 번 호출한다.
 * 저장된 상태만 있으므로(저장 안 된 편집은 편집기에서) 저장본 기준이다.
 */
export function GraphIssuesPreview({ graph, project }: { graph: GraphSummary; project?: string | null }) {
  const startErrorView = useStartErrorView();
  const q = useApiQuery(["graph-issues", project ?? "", graph.id, graph.version_hash ?? ""], (rest) => rest.validateGraph(graph.id, undefined, { project }), { staleTime: 0, retry: false });
  // 프로젝트 기준 검증이 실행 연동 꺼짐(409)이면 실패 대신 서버 문구를 안내로 보인다
  const notice = q.isError ? startErrorView(q.error) : null;
  if (notice !== null && notice.tone === "info") return <p className="app-muted" role="status" data-testid="graph-issues-notice">{notice.message}</p>;
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
