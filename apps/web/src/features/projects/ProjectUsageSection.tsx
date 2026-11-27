import { queryKeys, useApiQuery } from "../../app/queries";
import { ProjectChip } from "./ProjectChip";
import { useProjects } from "./ProjectsContext";
import { useScopeMessages } from "./scopeMessages";
import { useT } from "@agent-console/i18n";

/** 사용량 화면의 "이 프로젝트" 구역(screen-projects §7.5, 범위 screen-runs-usage §3.9): 현재 프로젝트의 루트 실행 수를 보인다 (GET /runs/project-counts — 앱 DB + 보관하지 않은 프로젝트 기록 DB, 기간과 무관). 토큰 합계는 이 구역이 아니라 같은 화면의 토큰 집계 표가 GET /usage?project=로 그 프로젝트 실행만 보인다. 프로젝트가 0개이거나 기능이 꺼져 있으면 아무것도 그리지 않는다(계정 전체 창만 남는다). */
export function ProjectUsageSection() {
  const language = useT("shell").language;
  const scopeMessages = useScopeMessages();
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
        <div><dt>{scopeMessages.usage.runs}</dt><dd>{counts.data === undefined ? "–" : runs.toLocaleString(language)}</dd></div>
      </dl>
    </section>
  );
}
