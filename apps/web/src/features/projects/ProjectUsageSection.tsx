import { queryKeys, useApiQuery } from "../../app/queries";
import { ProjectChip } from "./ProjectChip";
import { useProjects } from "./ProjectsContext";
import { scopeMessages } from "./scopeMessages";

/**
 * 사용량 화면의 "이 프로젝트" 구역(screen-projects §7.5): 계정 창과 별도로 현재 프로젝트의 실행 수를 보인다.
 * 프로젝트가 0개이거나 기능이 꺼져 있으면 아무것도 그리지 않는다(계정 전체 창만 남는다).
 * 토큰 합계는 서버가 프로젝트별 사용량을 주지 않아 아직 없다(실행 수만).
 */
export function ProjectUsageSection() {
  const p = useProjects();
  const id = p.enabled ? p.current : null;
  const counts = useApiQuery(queryKeys.list("run-project-counts"), (rest) => rest.getRunProjectCounts(), { enabled: id !== null, retry: false, meta: { silentBackgroundError: true } });
  if (id === null || p.currentProject === undefined) return null;
  const runs = counts.data?.by_project?.[id] ?? 0;
  return (
    <section className="prj-usage" aria-labelledby="prj-usage-title">
      <h2 id="prj-usage-title" className="prj-usage-title">{scopeMessages.usage.title}</h2>
      <ProjectChip />
      <dl className="prj-usage-stats">
        <div><dt>{scopeMessages.usage.runs}</dt><dd>{counts.data === undefined ? "–" : runs.toLocaleString("ko-KR")}</dd></div>
      </dl>
    </section>
  );
}
