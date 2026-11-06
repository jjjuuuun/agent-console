/**
 * 섹션 목록 + 스키마 폼(규칙 편집의 공통 본문): 계약 JSON Schema(`x-ui`)에서 섹션을 만들고(`ruleSections`) 고른 섹션 하나를 `SchemaForm`으로 그린다.
 * 값·검사 이슈·선택 섹션은 props이고 서버를 모른다. 문서 틀 편집(`TemplateEditor`)이 쓴다.
 */
import "./sdd.css";
import { useMemo, type ComponentType, type ReactNode } from "react";
import { SchemaForm, type FormError, type SchemaFormFieldProps } from "@agent-console/schema-form";
import type { SpecIssue } from "@agent-console/contracts/sdd";
import type { SchemaNode } from "../../lib/schemaTools";
import { ConfigIssuesProvider } from "../delegation";
import { SDD_WIDGET_FIELDS } from "./widgets/fields";
import { SddWidgetEnvProvider, type SddWidgetEnv } from "./widgets/SddWidgetEnv";
import { widgetUiSchema } from "./widgets/widgetUi";
import { issueInSection, mergeSection, ruleSections, sectionValue, type RuleSection } from "./ruleSections";

type Obj = Record<string, unknown>;
const NO_FIELDS: Readonly<Record<string, ComponentType<SchemaFormFieldProps>>> = {};
const NO_NAMES: readonly string[] = [];
const NO_ENV: SddWidgetEnv = { refs: {}, variables: [] };

export interface RuleSectionsFormProps {
  /** 정의 모델 전체 JSON Schema(`$defs` 포함) */
  schema: SchemaNode;
  value: Obj;
  onChange: (next: Obj) => void;
  issues: readonly SpecIssue[];
  readonly: boolean;
  /** 고른 섹션 id(없거나 모르면 첫 섹션) */
  sectionId: string | null;
  onSectionChange: (id: string) => void;
  navLabel: string;
  /** 폼 요소 id 접두 */
  idPrefix: string;
  /** 규칙 위젯이 읽는 목록·변수(없으면 비어 있어 직접 입력만 받는다) */
  widgetEnv?: SddWidgetEnv;
  /** 값이 바뀌지 않아도 폼을 다시 만들고 싶을 때 올리는 번호 */
  formEpoch?: number;
  /** 섹션 제목 아래에 그릴 안내 */
  sectionNote?: (section: RuleSection) => ReactNode;
  /** 섹션별 읽기 전용 추가 조건 */
  readonlyFor?: (section: RuleSection) => boolean;
  /** 위젯 이름 → 필드 컴포넌트 추가(문서 틀 위젯 8종에 더한다. 같은 이름이면 이쪽이 이긴다). 다른 정의 종류가 자기 위젯을 꽂을 때 쓴다 */
  extraFields?: Readonly<Record<string, ComponentType<SchemaFormFieldProps>>>;
  /** 고급이어도 섹션으로 보일 최상위 속성 이름(`ruleSections`) */
  includeAdvanced?: readonly string[];
}

const errorsFor = (issues: readonly SpecIssue[], section: RuleSection): FormError[] => {
  const key = section.path[section.path.length - 1] as string;
  return issues
    .filter((i) => issueInSection(i.path, section))
    .map((i) => ({ path: `/${key}${(i.path as string).slice(section.pointer.length)}`, message: i.message, severity: i.severity === "error" ? ("error" as const) : ("warning" as const) }));
};

export function RuleSectionsForm({ schema, value, onChange, issues, readonly, sectionId, onSectionChange, navLabel, idPrefix, widgetEnv = NO_ENV, formEpoch = 0, sectionNote, readonlyFor, extraFields = NO_FIELDS, includeAdvanced = NO_NAMES }: RuleSectionsFormProps) {
  const sections = useMemo(() => ruleSections(schema, includeAdvanced), [schema, includeAdvanced]);
  const fields = useMemo(() => ({ ...SDD_WIDGET_FIELDS, ...extraFields }), [extraFields]);
  const section = sections.find((s) => s.id === sectionId) ?? sections[0];
  const sectionUi = useMemo(() => (section === undefined ? undefined : widgetUiSchema(section.schema, new Set(Object.keys(fields)))), [section, fields]);
  if (section === undefined) return null;
  const sectionErrors = errorsFor(issues, section);
  return (
    <div className="sdd-rules-body">
      <nav className="sdd-rules-nav" aria-label={navLabel}>
        <ul>
          {sections.map((s) => {
            const n = issues.filter((i) => issueInSection(i.path, s)).length;
            return (
              <li key={s.id}>
                <button type="button" aria-current={s.id === section.id ? "true" : undefined} onClick={() => onSectionChange(s.id)}>
                  <span className="ac-ellipsis">{s.title}</span>
                  {n > 0 ? <span className="sdd-dot" data-tone="danger" aria-label={`${n}`}>{n}</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="sdd-rules-form">
        <h3 className="sdd-section-title">{section.title}</h3>
        {sectionNote?.(section)}
        <SddWidgetEnvProvider env={widgetEnv}>
          <ConfigIssuesProvider issues={sectionErrors}>
            <SchemaForm
              key={`${section.id}:${formEpoch}`}
              schema={section.schema}
              uiSchema={sectionUi}
              customFields={fields}
              value={sectionValue(value, section)}
              onChange={(next) => onChange(mergeSection(value, section, next))}
              errors={sectionErrors}
              readonly={readonly || (readonlyFor?.(section) ?? false)}
              idPrefix={`${idPrefix}-${section.id.replace(/[^A-Za-z0-9_-]/g, "-")}`}
              rawJsonToggle={false}
            />
          </ConfigIssuesProvider>
        </SddWidgetEnvProvider>
      </div>
    </div>
  );
}
