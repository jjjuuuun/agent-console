import { useId, useState, type ChangeEvent, type ReactNode } from "react";
import { Tag } from "@agent-console/ui";
import { SCOPE_VIEW_MODES, badgeLabel, defaultScopeFor, scopeBadge, type NewScopePreferences, type Scope, type ScopeViewMode } from "@agent-console/projects";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";
import { useWorkspaceSettings } from "../../app/queries";

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

export interface ProjectFieldProps {
  /** 지금 범위(null = 공용) */
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  /** 라벨 접두에 붙을 id 충돌 방지용(생략하면 자동) */
  id?: string;
}

const NEW_VALUE = "\u0000new";

/** 폼의 "프로젝트" 필드: 공용 + 프로젝트 목록 + [새 프로젝트…]. 프로젝트 기능이 꺼져 있으면 그리지 않는다. */
export function ProjectField({ value, onChange, disabled, id }: ProjectFieldProps) {
  const p = useProjects();
  const auto = useId();
  const fieldId = id ?? auto;
  if (!p.enabled) return null;
  const known = value === null || p.projects.some((x) => x.id === value);
  return (
    <div className="lib-field prj-field">
      <label htmlFor={fieldId}>{t.field.label}</label>
      <select
        id={fieldId}
        className="ac-input"
        value={value ?? ""}
        disabled={disabled}
        aria-describedby={`${fieldId}-note`}
        onChange={(e) => {
          if (e.target.value === NEW_VALUE) p.requestCreate((created) => onChange(created.id));
          else onChange(e.target.value === "" ? null : e.target.value);
        }}
      >
        <option value="">{t.field.shared}</option>
        {p.projects.map((x) => (
          <option key={x.id} value={x.id}>{x.name}</option>
        ))}
        {known ? null : <option value={value ?? ""}>{t.badge["scope.deleted_project"]?.replace("${project}", value ?? "") ?? value}</option>}
        <option value={NEW_VALUE}>{t.field.newProject}</option>
      </select>
      <span id={`${fieldId}-note`} className="app-muted lib-field-note">{t.field.hint}</span>
    </div>
  );
}

export interface NewScope {
  /** 정의 본문에 찍을 `project`(null = 공용, 필드를 넣지 않는다) */
  project: string | null;
  /** 만들기 대화상자의 `extra`에 끼울 필드(프로젝트 기능이 꺼져 있으면 null) */
  field: ReactNode;
  /** 정의 본문에 펼칠 조각: 공용이면 빈 객체 */
  patch: { project?: string };
}

/**
 * 새 정의의 범위 상태: 기본값 = 설정 `projects.new_definition_scope[kind]`와 현재 프로젝트(`defaultScopeFor`),
 * 모든 프로젝트 보기에서는 공용. 사용자가 필드에서 바꿀 수 있다. 호출자가 대화상자를 열 때마다 새로 마운트한다.
 * @param kind 정의 종류 이름(코드에 고정하지 않고 호출자가 계약에서 읽은 값을 준다)
 */
export function useNewScope(kind: string): NewScope {
  const p = useProjects();
  const settings = useWorkspaceSettings();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const preferences = (settings.data?.value.projects ?? undefined) as NewScopePreferences | undefined;
  const fallback = p.enabled ? defaultScopeFor(kind, p.current, preferences) : null;
  const project = p.enabled ? (picked === undefined ? fallback : picked) : null;
  return {
    project,
    patch: project === null ? {} : { project },
    field: p.enabled ? <ProjectField value={project} onChange={setPicked} /> : null,
  };
}
