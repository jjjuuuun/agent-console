import { useId, type ChangeEvent, type ReactNode } from "react";
import { Tag } from "@agent-console/ui";
import { SCOPE_VIEW_MODES, badgeLabel, createProjectsText, scopeBadge, type Scope, type ScopeViewMode } from "@agent-console/projects";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";
import { useSpace } from "./SpaceScope";

/**
 * 목록 머리의 범위 필터 한 줄: 칩 `프로젝트: 앱 개편 ✕`(✕ = 모든 프로젝트 보기) + 보기 범위 선택
 * (공용 + 이 프로젝트 / 이 프로젝트만 / 공용만). 프로젝트 기능이 꺼져 있거나 모든 프로젝트 보기면 아무것도 그리지 않는다.
 * 선택값은 모든 목록이 공유한다(`ProjectsProvider`의 `viewMode`).
 */
export function ScopeFilter({ className }: { className?: string }) {
  const p = useProjects();
  const selectId = useId();
  if (!p.enabled || p.current === null) return null;
  const name = p.names.get(p.current) ?? p.current;
  return (
    <div className={["prj-filter", className].filter(Boolean).join(" ")} role="group" aria-label={t.filter.label}>
      <button type="button" className="prj-chip" onClick={() => p.setCurrent(null)} title={t.filter.clear} aria-label={`${t.filter.chip(name)}. ${t.filter.clear}`}>
        <span className="ac-ellipsis">{t.filter.chip(name)}</span>
        <span aria-hidden="true">✕</span>
      </button>
      <label htmlFor={selectId} className="ac-sr-only">{t.filter.label}</label>
      <select id={selectId} className="ac-input prj-mode" value={p.viewMode} onChange={(e: ChangeEvent<HTMLSelectElement>) => p.setViewMode(e.target.value as ScopeViewMode)}>
        {SCOPE_VIEW_MODES.map((m) => (
          <option key={m} value={m}>{t.filter.modes[m] ?? m}</option>
        ))}
      </select>
    </div>
  );
}

/** 목록 행 옆 범위 태그(12px 칩, 말줄임). 모든 프로젝트 보기에서는 "공용"/프로젝트 이름, 특정 프로젝트 보기에서는 그 프로젝트 전용 태그를 숨긴다. */
export function ProjectTag({ scope, showOwn = false }: { scope: Scope; showOwn?: boolean }) {
  const p = useProjects();
  if (!p.enabled || p.projects.length === 0) return null;
  const badge = scopeBadge(scope, p.current, { projectNames: p.names, showOwn });
  if (badge === null) return null;
  const label = badge.kind === "shared" ? t.tag.shared : badgeLabel(badge, t.badge);
  return (
    <Tag className="prj-tag" data-tone={badge.tone} data-kind={badge.kind} title={badge.kind === "shared" ? t.tag.sharedTitle : label}>
      {label}
    </Tag>
  );
}

export interface NewScope {
  /** 정의 본문에 펼칠 조각. 새 정의의 저장 위치는 화면(공간)이 정하므로 항상 빈 객체다(본문에 `project`를 찍지 않는다) */
  patch: { project?: string };
  /** 만들기 대화상자의 `extra`에 끼울 읽기 전용 한 줄 "저장 위치: 프로젝트 {이름}"(프로젝트 사본 화면에서만, 공용이면 null) */
  field: ReactNode;
}

const spaceText = createProjectsText();

/**
 * 새 정의의 저장 위치 표시(screen-projects §5.3). 범위를 고르는 입력은 없다: 공용 구성 화면에서 만들면 공용,
 * 프로젝트 사본(`?prj=`) 화면에서 만들면 그 프로젝트에 저장된다. 호출자가 대화상자를 열 때마다 새로 마운트한다.
 */
export function useNewScope(): NewScope {
  const space = useSpace();
  return {
    patch: {},
    field:
      space === null ? null : (
        <p className="lib-field-note app-muted" data-testid="save-location">
          {spaceText({ key: "space.save_location", params: { name: space.project.name } })}
        </p>
      ),
  };
}
