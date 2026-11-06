import { useId } from "react";
import { useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";
import type { WikiSummary } from "@agent-console/contracts/wiki";
import { useApi } from "../../app/ApiContext";
import { CURRENT_PROJECT_PARAM, useProjectId } from "../../app/projectScope";
import { useProjects } from "../projects";
import { WIKI_REF } from "./integrationConfig";
import { wikiLinkMessages as t } from "./integrationMessages";

/**
 * 스키마 `x-ui.widget: wiki-ref` 위젯: 위키 id를 고르는 콤보박스(직접 입력도 된다). 값은 문자열이고 비우면 필수가 아니면 null이다.
 * 목록의 원천은 이 리소스가 놓인 공간이다 — 주소 `?prj=`(프로젝트 사본 편집)가 있으면 그 프로젝트의 위키, 없으면(공용) 위키가 없는 공간이라
 * 직접 입력 + 현재 프로젝트의 위키 제안 + 안내 한 줄. 목록을 못 읽으면 직접 입력만 된다.
 * 목록에 없는 id의 경고는 서버 검사 이슈(필드 오류)가 그리며 이 위젯은 판단하지 않는다.
 */
export function WikiRefWidget({ id, value, onChange, onBlur, label, required, disabled, readonly, placeholder }: SchemaFormWidgetProps) {
  const { wiki } = useApi();
  const [params] = useSearchParams();
  const current = useProjectId();
  const projects = useProjects();
  const copyOf = params.get(CURRENT_PROJECT_PARAM);
  // 목록을 읽을 공간: 사본 편집이면 그 프로젝트, 공용이면 사이드바의 현재 프로젝트(제안용)
  const space = copyOf ?? current;
  const library = copyOf === null;
  const list = useQuery<WikiSummary[], Error>({
    queryKey: ["wiki", space ?? "", "wikis", "widget"],
    queryFn: () => wiki(space).listWikis(),
    enabled: space !== null,
    retry: false,
    staleTime: WIKI_REF.staleMs,
    meta: { silentBackgroundError: true },
  });
  const listId = useId();
  const text = typeof value === "string" ? value : "";
  const wikis = list.data ?? [];
  const projectName = space === null ? undefined : projects.views.find((v) => v.project.id === space)?.project.name;
  return (
    <span className="wiki-refwidget">
      <input
        id={id}
        className="wiki-refwidget-input"
        list={wikis.length > 0 ? listId : undefined}
        value={text}
        placeholder={placeholder ?? t.widget.placeholder}
        aria-label={label}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled || readonly}
        onBlur={onBlur}
        onChange={(e) => onChange(e.target.value === "" && !required ? null : e.target.value)}
      />
      {wikis.length > 0 ? (
        <datalist id={listId} aria-label={library && projectName !== undefined ? t.widget.suggestGroup(projectName) : t.widget.listLabel}>
          {wikis.map((w) => (
            <option key={w.id} value={w.id} label={t.widget.option(w.name ?? "", w.id)} />
          ))}
        </datalist>
      ) : null}
      {library && wikis.length > 0 && projectName !== undefined ? <span className="wiki-refwidget-note app-muted">{t.widget.suggestions(projectName, wikis.map((w) => w.id))}</span> : null}
      {library ? <span className="wiki-refwidget-note app-muted">{t.widget.libraryNote}</span> : null}
      {list.isError ? <span className="wiki-refwidget-note app-muted">{t.widget.loadFailed}</span> : null}
    </span>
  );
}
