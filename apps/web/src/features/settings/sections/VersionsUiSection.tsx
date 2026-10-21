import { useMemo } from "react";
import { SchemaForm, type JsonSchema, type UiSchema } from "@agent-console/schema-form";
import { getContractSchema, type VersionUiSettings, type WorkspaceSettings } from "@agent-console/contracts";
import { messages as m } from "../../../app/messages";
import { DEFAULT_DIFF_LABEL_KEYS } from "../../../lib/itemLabelKeys";
import { STRING_TAGS_FIELD, StringTagsField } from "../widgets/StringTagsField";
import type { SectionEditProps } from "./FormSections";

const FIELDS = { [STRING_TAGS_FIELD]: StringTagsField };

export interface VersionsUiEditorProps {
  /** 저장 전 초안 값(없으면 상속 = 기본값) */
  value: VersionUiSettings | undefined;
  onChange: (next: VersionUiSettings | undefined) => void;
  errors?: SectionEditProps["errors"];
  disabled?: boolean;
}

/**
 * `ui.versions` 폼. 필드는 계약 스키마에서 그리고 목록 위젯만 주입한다.
 * 목록을 비우면 키를 지워 기본값(상속)으로 돌아간다.
 */
export function VersionsUiEditor({ value, onChange, errors, disabled }: VersionsUiEditorProps) {
  const schema = useMemo(() => {
    const copy: Record<string, unknown> = { ...(getContractSchema("VersionUiSettings") as Record<string, unknown>), additionalProperties: false };
    delete copy["title"];
    delete copy["description"];
    return copy as JsonSchema;
  }, []);
  const uiSchema = useMemo<UiSchema>(
    () => ({
      item_label_keys: {
        "ui:field": STRING_TAGS_FIELD,
        "ui:options": { suggestions: DEFAULT_DIFF_LABEL_KEYS, emptyNote: m.settings.versionsUi.inherit(DEFAULT_DIFF_LABEL_KEYS.join(", ")), removeLabel: m.settings.versionsUi.remove },
      },
    }),
    [],
  );
  const shown = { item_label_keys: value?.item_label_keys ?? [] };
  return (
    <SchemaForm
      schema={schema}
      uiSchema={uiSchema}
      value={shown}
      onChange={(next) => {
        const keys = (next as VersionUiSettings).item_label_keys ?? [];
        onChange(keys.length === 0 ? undefined : { item_label_keys: keys });
      }}
      customFields={FIELDS}
      rawJsonToggle={false}
      idPrefix="versions-ui"
      {...(errors ? { errors } : {})}
      {...(disabled === undefined ? {} : { disabled })}
    />
  );
}

/** 설정 화면 섹션: `ui.versions`만 편집하고 `ui`의 다른 키는 그대로 둔다. 비면 `versions` 키를 지운다. */
export function VersionsUiSection({ value, onChange, errors, disabled }: SectionEditProps) {
  return (
    <VersionsUiEditor
      value={value.ui?.versions ?? undefined}
      onChange={(next) => {
        const { versions: _drop, ...rest } = (value.ui ?? {}) as Record<string, unknown>;
        void _drop;
        const ui = next === undefined ? rest : { ...rest, versions: next };
        onChange({ ...value, ui: ui as WorkspaceSettings["ui"] });
      }}
      {...(errors ? { errors } : {})}
      {...(disabled === undefined ? {} : { disabled })}
    />
  );
}
