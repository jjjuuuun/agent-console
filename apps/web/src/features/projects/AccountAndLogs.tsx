import { Tag } from "@agent-console/ui";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";

/**
 * 사용량 화면 머리의 "계정 전체" 표시. 구독 사용량은 프로젝트와 무관한 계정 기준이라, 프로젝트를 고른 상태에서만 알려 준다.
 * 프로젝트 기능이 꺼져 있거나 모든 프로젝트 보기면 아무것도 그리지 않는다.
 */
export function AccountWideNote() {
  const p = useProjects();
  if (!p.enabled || p.current === null) return null;
  return <Tag className="prj-tag" data-tone="neutral" title={t.usage.accountWideTitle}>{t.usage.accountWide}</Tag>;
}
