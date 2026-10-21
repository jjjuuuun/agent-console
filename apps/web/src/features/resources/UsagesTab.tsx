import { Link } from "react-router";
import { EmptyState } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useApiQuery } from "../../app/queries";
import { Skeleton } from "../settings";
import { DEFINITION_KINDS, libraryMessages as lm, definitionPath, routePath, ROUTE_ROLES } from "../library";
import { resourceMessages as t } from "./messages";

/** 종류(저장소 kind) -> 사용처 열의 표시 이름. 모르는 종류는 서버 문자열 그대로. */
function kindLabel(kind: string): string {
  if (kind === DEFINITION_KINDS.graph) return lm.usage.kindTeam;
  if (kind === DEFINITION_KINDS.agent) return lm.usage.kindAgent;
  if (kind === DEFINITION_KINDS.resource) return lm.usage.kindResource;
  return kind;
}

export function useResourceUsages(id: string) {
  return useApiQuery(["list", "resource-usages", id], (rest) => rest.listResourceUsages(id));
}

/** 이 리소스가 붙은 곳(팀 구성·에이전트·공통). */
export function ResourceUsagesTab({ id }: { id: string }) {
  const q = useResourceUsages(id);
  if (q.isLoading) return <Skeleton rows={3} />;
  if (q.isError) return <ErrorBlock title={t.usages.failed} message={q.error.message} retryLabel={lm.retry} onRetry={() => void q.refetch()} />;
  const rows = q.data ?? [];
  if (rows.length === 0) return <EmptyState title={t.usages.empty} action={<Link to={routePath(ROUTE_ROLES.graph)}>{t.usages.toTeams}</Link>} />;
  return (
    <table className="lib-grid" aria-label={t.tabs.usages}>
      <thead>
        <tr>
          <th>{t.usages.kind}</th>
          <th>{t.usages.name}</th>
          <th>{t.usages.layer}</th>
          <th>{t.usages.nodes}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const to = definitionPath(r.kind, r.id);
          return (
            <tr key={`${i}:${r.kind}:${r.id}`}>
              <td>{kindLabel(r.kind)}</td>
              <td>{to === undefined ? (r.name ?? r.id) : <Link to={to}>{r.name ?? r.id}</Link>}</td>
              <td>{r.layer ?? "–"}</td>
              <td className="app-wrap">{(r.node_ids ?? []).join(", ") || "–"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
