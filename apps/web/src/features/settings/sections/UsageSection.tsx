import { useMemo, useState } from "react";
import { contractsSchema, getContractSchema, type UsageSourceInfo, type UsageSourceSetting, type UsageWindowSnapshot, type WorkspaceSettings } from "@agent-console/contracts";
import { InlineMarkdown, SchemaForm } from "@agent-console/schema-form";
import { Button, ConfirmDialog, Disclosure, TrustBadge } from "@agent-console/ui";
import { messages as m } from "../../../app/messages";
import { formatDateTime } from "../../../lib/format";
import type { SchemaNode } from "../../../lib/schemaTools";
import { UserSettingsForm } from "../UserSettingsForm";
import { errorsUnder, messagesAt } from "../errorPaths";
import type { FormError } from "@agent-console/schema-form";
import { Skeleton } from "../Skeleton";
import { useUsageReport, useUsageSources } from "../settingsData";
import { COMMON_LAYER_ID, type SectionEditProps } from "./FormSections";
import { UsageIndicatorEditor } from "./UsageIndicatorEditor";
import { useNow } from "../../../app/useNow";
import { ROUTE_ROLES, routePath } from "../../library";
/** 신뢰 등급 어휘(계약 문서화 상수) 중 확인이 필요한 등급. */
const UNOFFICIAL_TRUST = "unofficial";

/** `usage` 중 창 이름·오래된 관측 기준만 그리는 스키마(출처·우선순위는 아래 전용 편집기가 맡는다). */
function usageFormSchema(): SchemaNode {
  const base = getContractSchema("WorkspaceSettings") as SchemaNode;
  const def = contractsSchema.$defs["UsageSettings"] as SchemaNode;
  const props = def["properties"] as Record<string, SchemaNode>;
  const subset = { ...def, properties: { window_labels: props["window_labels"], stale_after_seconds: props["stale_after_seconds"] } };
  return { ...base, properties: { usage: subset } };
}

const NO_LABELS: Readonly<Record<string, string>> = {};
const NO_WINDOWS: readonly UsageWindowSnapshot[] = [];
const NO_SOURCES: readonly UsageSourceInfo[] = [];
const NO_ORDER: readonly string[] = [];

function upsert(list: readonly UsageSourceSetting[], id: string, patch: Partial<UsageSourceSetting>): UsageSourceSetting[] {
  const found = list.some((s) => s.id === id);
  return found ? list.map((s) => (s.id === id ? { ...s, ...patch } : s)) : [...list, { id, ...patch }];
}

export interface UsageSourcesEditorProps {
  sources: readonly UsageSourceInfo[];
  settings: readonly UsageSourceSetting[];
  onChange: (next: UsageSourceSetting[]) => void;
  disabled?: boolean;
  /** 서버 422 필드 오류(문서 기준 경로 `/usage/sources/<i>/config/…`). 해당 출처의 설정 폼 필드에 표시한다 */
  errors?: readonly FormError[];
}

/** 출처 디스크립터 목록을 행으로: 신뢰 배지·설명·사용 스위치·출처 설정 폼. 비공식 출처를 켜면 확인한다. */
export function UsageSourcesEditor({ sources, settings, onChange, disabled, errors }: UsageSourcesEditorProps) {
  const [confirm, setConfirm] = useState<UsageSourceInfo | null>(null);
  const t = m.settings.usage;
  if (sources.length === 0) return <p className="app-muted">{t.sourcesEmpty}</p>;
  return (
    <>
      <ul className="app-source-list">
        {sources.map((info) => {
          const d = info.descriptor;
          const setting = settings.find((s) => s.id === d.id);
          const enabled = setting === undefined ? (info.enabled ?? false) : setting.enabled !== false;
          const at = `/usage/sources/${settings.findIndex((x) => x.id === d.id)}`;
          const configErrors = setting === undefined ? [] : errorsUnder(errors, `${at}/config`);
          const ownErrors = setting === undefined ? [] : messagesAt(errors, at).concat(messagesAt(errors, `${at}/config`));
          return (
            <li key={d.id} className="app-source-row">
              <div className="app-source-head">
                <label className="app-check">
                  <input
                    type="checkbox"
                    checked={enabled}
                    disabled={disabled}
                    aria-label={t.enable(d.title)}
                    onChange={(e) => {
                      if (e.target.checked && d.trust === UNOFFICIAL_TRUST) setConfirm(info);
                      else onChange(upsert(settings, d.id, { enabled: e.target.checked }));
                    }}
                  />
                  <strong>{d.title}</strong>
                </label>
                <TrustBadge trust={d.trust} />
                {info.last_observed_at == null ? null : <span className="app-muted">{t.lastObserved(formatDateTime(info.last_observed_at))}</span>}
              </div>
              {d.description ? <p className="app-muted app-source-desc"><InlineMarkdown text={d.description} /></p> : null}
              {info.error ? <p className="app-field-error" role="alert">{t.sourceError}: {info.error.message}</p> : null}
              {ownErrors.map((msg, i) => <p key={i} className="app-field-error" role="alert">{msg}</p>)}
              {d.setup_help ? <p className="app-muted app-source-desc app-wrap"><InlineMarkdown text={d.setup_help} /></p> : null}
              {d.docs_url && /^https?:\/\//.test(d.docs_url) ? (
                <a href={d.docs_url} target="_blank" rel="noreferrer noopener">{t.docs}</a>
              ) : null}
              {d.config_schema && Object.keys(d.config_schema).length > 0 ? (
                <Disclosure summary={t.config} {...(configErrors.length > 0 ? { open: true } : {})}>
                  <SchemaForm
                    schema={d.config_schema}
                    value={setting?.config ?? info.config ?? {}}
                    idPrefix={`usage-src-${d.id}`}
                    advancedStorageKey={`usage-source:${d.id}`}
                    errors={configErrors}
                    rawJsonToggle={false}
                    {...(disabled === undefined ? {} : { disabled })}
                    onChange={(v) => onChange(upsert(settings, d.id, { config: v as Record<string, unknown> }))}
                  />
                </Disclosure>
              ) : null}
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        open={confirm !== null}
        title={t.unofficialTitle}
        confirmLabel={t.unofficialConfirm}
        cancelLabel={m.common.cancel}
        onConfirm={() => {
          if (confirm !== null) onChange(upsert(settings, confirm.descriptor.id, { enabled: true }));
          setConfirm(null);
        }}
        onCancel={() => setConfirm(null)}
      >
        {confirm?.descriptor.description || t.unofficialBody}
      </ConfirmDialog>
    </>
  );
}

export interface PrimaryOrderEditorProps {
  sources: readonly UsageSourceInfo[];
  order: readonly string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

/** 대표값 우선순위: 체크한 출처만 목록에 들어가고 ↑↓ 버튼으로 순서를 바꾼다(키보드 가능). 비우면 가장 최근 공식 값. */
export function PrimaryOrderEditor({ sources, order, onChange, disabled }: PrimaryOrderEditorProps) {
  const t = m.settings.usage;
  const title = (id: string) => sources.find((s) => s.descriptor.id === id)?.descriptor.title ?? id;
  const unselected = sources.map((s) => s.descriptor.id).filter((id) => !order.includes(id));
  const move = (i: number, d: number) => {
    const next = [...order];
    const [item] = next.splice(i, 1);
    next.splice(i + d, 0, item!);
    onChange(next);
  };
  return (
    <ol className="app-order">
      {order.map((id, i) => (
        <li key={id} className="app-order-row">
          <label className="app-check">
            <input type="checkbox" checked disabled={disabled} aria-label={t.primaryUse(title(id))} onChange={() => onChange(order.filter((x) => x !== id))} />
            {title(id)}
          </label>
          <Button size="sm" disabled={disabled || i === 0} aria-label={t.primaryUp(title(id))} onClick={() => move(i, -1)}>↑</Button>
          <Button size="sm" disabled={disabled || i === order.length - 1} aria-label={t.primaryDown(title(id))} onClick={() => move(i, 1)}>↓</Button>
        </li>
      ))}
      {unselected.map((id) => (
        <li key={id} className="app-order-row">
          <label className="app-check">
            <input type="checkbox" checked={false} disabled={disabled} aria-label={t.primaryUse(title(id))} onChange={() => onChange([...order, id])} />
            {title(id)}
          </label>
        </li>
      ))}
    </ol>
  );
}

/** ③ 사용량 섹션: 창 이름·오래된 관측(스키마 폼) + 출처 + 대표값 우선순위. */
export function UsageSection({ value, onChange, errors, disabled }: SectionEditProps) {
  const sources = useUsageSources();
  const report = useUsageReport();
  const schema = useMemo(() => usageFormSchema(), []);
  const usage = (value.usage ?? {}) as NonNullable<WorkspaceSettings["usage"]>;
  const windowIds = useMemo(() => [...new Set((report.data?.windows ?? []).map((w) => w.window))], [report.data]);
  const options = useMemo(() => ({ windowIds }), [windowIds]);
  const layers = useMemo(() => [{ id: COMMON_LAYER_ID, label: m.settings.layerCommon }], []);
  const setUsage = (patch: Partial<NonNullable<WorkspaceSettings["usage"]>>) => onChange({ ...value, usage: { ...usage, ...patch } });

  const nowMs = useNow(true, 15_000);
  return (
    <>
      <UsageIndicatorEditor
        value={value.ui?.usage_indicator}
        onChange={(next) => onChange({ ...value, ui: { ...(value.ui ?? {}), usage_indicator: next } as WorkspaceSettings["ui"] })}
        windowIds={windowIds}
        labels={usage.window_labels ?? NO_LABELS}
        windows={report.data?.windows ?? NO_WINDOWS}
        sources={sources.data ?? NO_SOURCES}
        primaryOrder={usage.primary_source_order ?? NO_ORDER}
        staleAfterSeconds={usage.stale_after_seconds ?? null}
        nowMs={nowMs}
        usageHref={routePath(ROUTE_ROLES.usage)}
        {...(disabled === undefined ? {} : { disabled })}
      />
      <UserSettingsForm
        sections={["usage"]}
        rootSchema={schema}
        value={{ usage: { window_labels: usage.window_labels, stale_after_seconds: usage.stale_after_seconds } } as Record<string, unknown>}
        onChange={(next) => {
          const u = (next["usage"] ?? {}) as Record<string, unknown>;
          const { window_labels: _w, stale_after_seconds: _s, ...rest } = usage;
          void _w;
          void _s;
          onChange({ ...value, usage: { ...rest, ...u } as NonNullable<WorkspaceSettings["usage"]> });
        }}
        layers={layers}
        editLayerId={COMMON_LAYER_ID}
        options={options}
        idPrefix="usage-form"
        flat
        {...(errors ? { errors } : {})}
        {...(disabled === undefined ? {} : { disabled })}
      />
      <p className="app-muted">{m.settings.usage.windowLabelsHelp}</p>
      <h3 className="app-block-subtitle">{m.settings.usage.sources}</h3>
      <p className="app-muted">{m.settings.usage.sourcesHelp}</p>
      {sources.isLoading ? (
        <Skeleton rows={2} />
      ) : sources.error ? (
        <p className="app-field-error" role="alert">{m.settings.optionsFailed}</p>
      ) : (
        <UsageSourcesEditor sources={sources.data ?? []} settings={usage.sources ?? []} onChange={(next) => setUsage({ sources: next })} {...(errors === undefined ? {} : { errors })} {...(disabled === undefined ? {} : { disabled })} />
      )}
      <h3 className="app-block-subtitle">{m.settings.usage.primary}</h3>
      <p className="app-muted">{m.settings.usage.primaryHelp}</p>
      <PrimaryOrderEditor sources={sources.data ?? []} order={usage.primary_source_order ?? []} onChange={(next) => setUsage({ primary_source_order: next })} {...(disabled === undefined ? {} : { disabled })} />
      <p className="app-muted">{m.settings.usage.noHome}</p>
    </>
  );
}
