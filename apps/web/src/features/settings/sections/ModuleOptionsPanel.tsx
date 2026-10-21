import type { ModuleOptionsView } from "@agent-console/contracts";
import { SchemaForm, type JsonSchema } from "@agent-console/schema-form";
import { Banner } from "@agent-console/ui";
import { ApiError } from "@agent-console/api-client";
import { messages as m } from "../../../app/messages";
import { useApiQuery } from "../../../app/queries";
import { CopyButton } from "../CopyButton";
import { SETTINGS_FIELDS, SETTINGS_WIDGETS } from "../LayerForm";

const t = m.modules.options;
const noop = () => {};

export interface ModuleOptionsViewProps {
  view: ModuleOptionsView;
}

/** 모듈 옵션의 읽기 전용 표시: 스키마가 있으면 같은 폼 렌더(비활성), 없으면 안내. 아래에 [YAML 조각 복사]. */
export function ModuleOptionsReadOnly({ view }: ModuleOptionsViewProps) {
  const values = view.values ?? {};
  const snippet = view.yaml_snippet ?? "";
  return (
    <div className="app-mod-options">
      {view.schema == null ? (
        <p className="app-muted">{t.noSchema}</p>
      ) : Object.keys(values).length === 0 && snippet === "" ? (
        <p className="app-muted">{t.empty}</p>
      ) : (
        <SchemaForm
          schema={view.schema as JsonSchema}
          value={values}
          onChange={noop}
          disabled
          rawJsonToggle={false}
          idPrefix={`modopt-${view.module_id}`}
          customWidgets={SETTINGS_WIDGETS}
          customFields={SETTINGS_FIELDS}
        />
      )}
      {snippet === "" ? null : <CopyButton text={snippet} label={t.copyYaml} copiedLabel={t.yamlCopied} />}
      <p className="app-muted app-mod-options-hint">{t.hint}</p>
    </div>
  );
}

/** 컨테이너: 모듈 옵션을 읽는다(행을 펼쳤을 때만 마운트되므로 그때 한 번 부른다). 쓰기는 없다. */
export function ModuleOptionsPanel({ id }: { id: string }) {
  const q = useApiQuery(["module-options", id], (rest) => rest.getModuleOptions(id), { retry: false });
  if (q.isLoading) return <p className="app-muted" role="status">{t.loading}</p>;
  if (q.error) {
    const unsupported = q.error instanceof ApiError && q.error.status === 404;
    return <Banner tone={unsupported ? "info" : "warning"}>{unsupported ? t.unavailable : t.loadFailed}</Banner>;
  }
  return q.data === undefined ? null : <ModuleOptionsReadOnly view={q.data} />;
}
