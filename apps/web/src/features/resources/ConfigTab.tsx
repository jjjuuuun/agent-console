import { useMemo } from "react";
import { SchemaForm, type FormError } from "@agent-console/schema-form";
import { STRING_TAGS_FIELD, StringTagsField } from "../settings";
import { buildConfigUi } from "./configUi";
import type { ResourceTypeDescriptor } from "@agent-console/contracts";
import { Banner } from "@agent-console/ui";
import { resourceMessages as t } from "./messages";
import { plainSecretPaths, secretFieldsOf } from "./resourceLogic";

const FIELDS = { [STRING_TAGS_FIELD]: StringTagsField };

export interface ConfigTabProps {
  descriptor: ResourceTypeDescriptor;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  errors?: FormError[];
  disabled?: boolean;
}

/** 종류의 `config_schema`·`ui_schema`로 그리는 설정 폼. 출처 배지는 없다(리소스는 층 병합 대상이 아니다). */
export function ConfigTab({ descriptor, value, onChange, errors, disabled }: ConfigTabProps) {
  const schema = descriptor.config_schema;
  const hasFields = useMemo(() => {
    const props = schema?.["properties"];
    return typeof props === "object" && props !== null && Object.keys(props).length > 0;
  }, [schema]);
  const ui = useMemo(() => buildConfigUi(schema, descriptor.ui_schema as Record<string, unknown> | undefined), [schema, descriptor.ui_schema]);
  const secretFields = useMemo(() => secretFieldsOf(schema), [schema]);
  if (schema === undefined || !hasFields) return <p className="app-muted">{t.config.empty}</p>;
  const plain = plainSecretPaths(value, secretFields);
  const warnings = plain.map((path) => ({ path, message: t.config.plainSecretAt(path), severity: "warning" as const }));
  return (
    <>
      {plain.length > 0 ? (
        <Banner tone="warning" role="alert">
          {t.config.plainSecret}
          <ul className="lib-ref-list">
            {plain.map((p) => (
              <li key={p} className="lib-mono">{p}</li>
            ))}
          </ul>
        </Banner>
      ) : null}
    <SchemaForm
      schema={schema}
      uiSchema={ui}
      customFields={FIELDS}
      value={value}
      onChange={(next) => onChange((next ?? {}) as Record<string, unknown>)}
      errors={[...(errors ?? []), ...warnings.filter((w) => !(errors ?? []).some((e) => e.path === w.path))]}
      {...(disabled === undefined ? {} : { disabled })}
      idPrefix="resource-config"
    />
    </>
  );
}
