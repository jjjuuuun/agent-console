import type { ModuleOptionsView, PluginOptionsView } from "@agent-console/contracts";
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
          hideRootTitle
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

const tp = m.modules.pluginOptions;

/** 확장 옵션 하나의 읽기 전용 표시(스키마 폼 disabled, 설정됨 여부, YAML 조각 복사). */
export function PluginOptionsReadOnly({ item }: { item: PluginOptionsView }) {
  const values = item.values ?? {};
  const snippet = item.yaml_snippet ?? "";
  const hasValues = Object.keys(values).length > 0;
  return (
    <div className="app-mod-options">
      <p className="app-muted app-mod-options-hint">
        {tp.place} <code>{item.settings_key}</code> · {item.configured ? tp.configured : tp.notConfigured}
      </p>
      {item.schema == null ? (
        <p className="app-muted">{tp.noSchema}</p>
      ) : !hasValues && snippet === "" ? (
        <p className="app-muted">{tp.empty}</p>
      ) : (
        <SchemaForm
          schema={item.schema as JsonSchema}
          value={values}
          onChange={noop}
          disabled
          rawJsonToggle={false}
          hideRootTitle
          idPrefix={`plugopt-${item.extension}-${item.name}`}
          customWidgets={SETTINGS_WIDGETS}
          customFields={SETTINGS_FIELDS}
        />
      )}
      {snippet === "" ? null : <CopyButton text={snippet} label={tp.copyYaml} copiedLabel={tp.yamlCopied} />}
    </div>
  );
}

/** "확장 옵션" 묶음. 목록이 비면 아무것도 그리지 않는다(옛 서버는 필드가 없다). */
export function PluginOptionsGroup({ items }: { items: readonly PluginOptionsView[] }) {
  if (items.length === 0) return null;
  return (
    <section className="app-mod-plugin-options" aria-labelledby="plugin-options-title">
      <h3 id="plugin-options-title">{tp.title}</h3>
      <p className="app-muted app-mod-options-hint">{tp.hint}</p>
      {items.map((item) => (
        <details key={`${item.extension}/${item.name}`} className="app-mod-plugin-item" open>
          <summary>
            <code>{item.name}</code> <span className="app-muted">{item.extension}</span>
          </summary>
          <PluginOptionsReadOnly item={item} />
        </details>
      ))}
    </section>
  );
}
