import { Link, useNavigate } from "react-router";
import { StepGuide, type StepGuideStep } from "@agent-console/ui";
import type { Project } from "@agent-console/contracts/projects";
import { ROUTE_ROLES, routePath } from "../library";
import { projectMessages as t } from "./messages";

export interface ProjectGuideProps {
  projects: readonly Project[];
  /** 안내가 가리키는 프로젝트(현재 프로젝트, 없으면 첫 프로젝트) */
  project: Project | undefined;
  /** 이 프로젝트로 시작한 대화가 있는가 */
  hasConversation: boolean;
  onCreate: () => void;
  /** 설정 단계 동작(프로젝트 편집 칸으로 포커스) */
  onConfigure: () => void;
  onDismiss: () => void;
}

/** 단계 데이터(순수): 완료 여부는 서버 데이터로만 계산한다. */
export function guideSteps(p: Pick<ProjectGuideProps, "projects" | "project" | "hasConversation">): { id: string; done: boolean }[] {
  const configured = p.project !== undefined && ((p.project.working_directory ?? "") !== "" || (p.project.log_projects ?? []).length > 0);
  return [
    { id: "create", done: p.projects.length > 0 },
    { id: "configure", done: configured },
    { id: "start", done: p.hasConversation },
  ];
}

/**
 * 첫 프로젝트 3단계 안내(만들기 -> 작업 폴더·로그 연결 -> 대화 시작). 모두 끝나면 아무것도 그리지 않는다.
 * 단계 이름·설명은 문구 표(`guide.steps`)의 키이고 순서는 `guideSteps`가 정한다.
 */
export function ProjectGuide(props: ProjectGuideProps) {
  const navigate = useNavigate();
  const status = guideSteps(props);
  if (status.every((s) => s.done)) return null;
  const chatPath = routePath(ROUTE_ROLES.conversations);
  const steps: StepGuideStep[] = status.map((s) => {
    const label = t.guide.steps[s.id];
    const action = s.id === "create" ? props.onCreate : s.id === "configure" ? props.onConfigure : () => void navigate(chatPath);
    return { id: s.id, done: s.done, label: label?.label ?? s.id, ...(label ? { hint: label.hint, actionLabel: label.action } : {}), onAction: action };
  });
  return (
    <section className="prj-guide" aria-label={t.guide.title}>
      <div className="prj-guide-head">
        <h3 className="prj-guide-title">{t.guide.title}</h3>
        <button type="button" className="prj-link" onClick={props.onDismiss}>{t.guide.dismiss}</button>
      </div>
      <StepGuide
        steps={steps}
        messages={{ stepsLabel: t.guide.stepsLabel, go: t.guide.go, done: t.guide.done }}
        renderLink={({ to, className, children, dataAttrs }) => <Link to={to} className={className} {...dataAttrs}>{children}</Link>}
        layout="row"
      />
    </section>
  );
}
