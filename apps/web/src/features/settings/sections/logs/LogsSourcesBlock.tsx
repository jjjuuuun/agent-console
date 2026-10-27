import { useEffect, useMemo, useRef, useState } from "react";
import { InlineMarkdown, SchemaForm, type UiSchema } from "@agent-console/schema-form";
import { Button, ConfirmDialog, Disclosure, StatusChip, useToast } from "@agent-console/ui";
import type { LogSourceInfo, LogSourceSetting, WorkspaceSettings } from "@agent-console/contracts";
import { ErrorBlock } from "../../../../app/ErrorBlock";
import { messages as m } from "../../../../app/messages";
import { useNow } from "../../../../app/useNow";
import { describeSourceStatus, logsMessages as t, useLogClassifiers, useLogScan, useLogSources } from "../../../logs";
import { CHOICE_SELECT_WIDGET, ChoiceSelectWidget } from "../../widgets/ChoiceSelectWidget";
import { errorsUnder, messagesAt } from "../../errorPaths";
import { Skeleton } from "../../Skeleton";
import { isHttpUrl, patchLogs, without } from "./helpers";
import type { SectionEditProps } from "../FormSections";

const CUSTOM_WIDGETS = { [CHOICE_SELECT_WIDGET]: ChoiceSelectWidget };

export interface LogsSourcesBlockProps extends SectionEditProps {
  /** 설정 문서 전체에 저장 안 된 변경이 있는지(있으면 [지금 수집]을 막는다 — 서버는 저장된 설정만 읽는다) */
  dirty: boolean;
  /** 주소 `#logs?source=<id>`가 가리키는 출처(펼치고 스위치에 포커스) */
  focusSource: string | null;
  /** 관측 수집기 설정 스키마가 있을 때만 안내 링크를 보인다 */
  observeHref: string | undefined;
}

/**
 * 출처의 켜짐 값: 설정에 `enabled`가 있으면 그 값, 없으면 "기본값"이다. 기본값은 서버가 준 유효 값(`info.enabled`,
 * 이 PC에 로그가 있어 자동으로 켜진 것 포함)을 불러올 때 한 번 기억해 둔 것(`baseline`)이고, 모르면 디스크립터 `default_enabled`다.
 * (저장된 설정에 이미 `enabled`가 있었다면 `info.enabled`는 기본값이 아니라 그 값이라 기억하지 않는다.)
 */
export function effectiveEnabled(info: LogSourceInfo, s: LogSourceSetting | undefined, baseline?: ReadonlyMap<string, boolean>): boolean {
  return s?.enabled ?? baseline?.get(info.descriptor.id) ?? info.descriptor.default_enabled ?? false;
}

/** 수집 출처: 서버 디스크립터 카드(스위치·상태·[지금 수집]·설정 폼). 출처 이름을 코드에 두지 않는다. */
export function LogsSourcesBlock({ value, onChange, errors, disabled, dirty, focusSource, observeHref }: LogsSourcesBlockProps) {
  const sources = useLogSources();
  const classifiers = useLogClassifiers();
  const toast = useToast();
  const scan = useLogScan(sources.data, { toast: false });
  const nowMs = useNow(true, 15_000);
  const settings: readonly LogSourceSetting[] = value.logs?.sources ?? [];
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [confirm, setConfirm] = useState<LogSourceInfo | null>(null);
  const [scanningId, setScanningId] = useState<string | null>(null);
  const switchRefs = useRef(new Map<string, HTMLInputElement>());
  // 처음 불러온 시점의 기본값(서버 유효 값). 저장된 설정에 enabled가 없던 출처만 기억한다.
  const [baseline, setBaseline] = useState<ReadonlyMap<string, boolean>>(new Map());
  if (sources.data !== undefined) {
    // 렌더 중 파생 상태 갱신(조건이 바뀔 때만 한 번): 새로 보인 출처의 기본값을 기억한다.
    const fresh = sources.data.filter((info) => !baseline.has(info.descriptor.id) && (value.logs?.sources ?? []).find((x) => x.id === info.descriptor.id)?.enabled === undefined);
    if (fresh.length > 0) setBaseline(new Map([...baseline, ...fresh.map((info) => [info.descriptor.id, info.enabled] as const)]));
  }

  const setSources = (next: LogSourceSetting[]) => onChange({ ...value, logs: patchLogs(value.logs, { sources: next.length === 0 ? undefined : next }) } as WorkspaceSettings);
  const update = (id: string, patch: (cur: LogSourceSetting) => LogSourceSetting) => {
    const exists = settings.some((s) => s.id === id);
    const nextOne = patch(settings.find((s) => s.id === id) ?? { id });
    const list = exists ? settings.map((s) => (s.id === id ? nextOne : s)) : [...settings, nextOne];
    // id만 남은 항목(= 아무것도 지정하지 않음)은 없앤다
    setSources(list.filter((s) => s.id !== id || Object.keys(s).some((k) => k !== "id")));
  };
  const needsConfirm = (info: LogSourceInfo) => info.descriptor.reads_paths === true && info.descriptor.default_enabled !== true;
  const setEnabled = (info: LogSourceInfo, on: boolean) => {
    update(info.descriptor.id, (c) => ({ ...c, enabled: on }));
    if (on) setOpen((cur) => new Set(cur).add(info.descriptor.id));
  };
  const toggle = (info: LogSourceInfo, on: boolean) => {
    if (on && needsConfirm(info) && !effectiveEnabled(info, settings.find((s) => s.id === info.descriptor.id), baseline)) setConfirm(info);
    else setEnabled(info, on);
  };
  const reset = (info: LogSourceInfo) => update(info.descriptor.id, (c) => without(c, "enabled") as LogSourceSetting);

  // 주소가 가리키는 출처의 스위치로 포커스(펼침은 렌더에서 `focusSource`로 판단한다)
  useEffect(() => {
    if (focusSource === null || sources.data === undefined) return;
    if (sources.data.some((s) => s.descriptor.id === focusSource)) requestAnimationFrame(() => switchRefs.current.get(focusSource)?.focus());
  }, [focusSource, sources.data]);

  const classifierChoices = useMemo(() => (classifiers.data ?? []).map((c) => ({ value: c.id, label: c.title })), [classifiers.data]);
  const uiFor = (info: LogSourceInfo): UiSchema | undefined => {
    const props = (info.descriptor.config_schema?.["properties"] ?? {}) as Record<string, unknown>;
    return "classifier" in props && classifierChoices.length > 0 ? { classifier: { "ui:widget": CHOICE_SELECT_WIDGET, "ui:options": { choices: classifierChoices, emptyLabel: "" } } } : undefined;
  };

  const runScan = async (info: LogSourceInfo) => {
    setScanningId(info.descriptor.id);
    const report = await scan.run([info.descriptor.id]);
    setScanningId(null);
    const mine = report?.sources?.find((s) => s.source_id === info.descriptor.id);
    if (mine === undefined) return;
    if (mine.error_code != null) toast({ tone: "warning", text: t.settings.sources.scanError(mine.message ?? mine.error_code) });
    else toast({ tone: "success", text: t.settings.sources.scanNew(mine.new_events ?? 0) });
  };

  if (sources.isPending) return <Skeleton rows={3} />;
  if (sources.isError) return <ErrorBlock title={t.settings.sources.loadFailed} message={sources.error.message} retryLabel={m.common.retry} onRetry={() => void sources.refetch()} />;
  const list = sources.data;
  if (list.length === 0) return <p className="app-muted">{t.settings.sources.empty}</p>;
  const known = new Set(list.map((s) => s.descriptor.id));
  const groups = [
    { id: "plugin", title: t.settings.sources.groupPlugin, items: list.filter((s) => s.origin !== "runtime") },
    { id: "runtime", title: t.settings.sources.groupRuntime, items: list.filter((s) => s.origin === "runtime") },
  ].filter((g) => g.items.length > 0);
  const unknown = settings.filter((s) => !known.has(s.id));
  const on = list.filter((s) => effectiveEnabled(s, settings.find((x) => x.id === s.descriptor.id), baseline)).length;
  const roots = (info: LogSourceInfo): string[] => {
    const cfg = settings.find((s) => s.id === info.descriptor.id)?.config as Record<string, unknown> | null | undefined;
    const r = cfg?.["roots"];
    return Array.isArray(r) ? r.filter((x): x is string => typeof x === "string").slice(0, 3) : [];
  };

  return (
    <div className="logs-settings-sources">
      <p className="app-muted">{t.settings.sources.summary(on, list.length - on)}</p>
      {groups.map((g) => (
        <section key={g.id} aria-label={g.title}>
          <h4 className="app-block-subtitle">{g.title}</h4>
          <ul className="logs-source-list">
            {g.items.map((info) => {
              const d = info.descriptor;
              const setting = settings.find((s) => s.id === d.id);
              const index = settings.findIndex((s) => s.id === d.id);
              const enabled = effectiveEnabled(info, setting, baseline);
              const autoOn = setting?.enabled === undefined && d.default_enabled !== true && (baseline.get(d.id) ?? info.enabled) === true;
              const unsaved = enabled !== info.enabled;
              const expanded = open.has(d.id) || focusSource === d.id;
              const view = describeSourceStatus({ info, enabled, dirty: unsaved, scanning: scanningId === d.id, nowMs });
              const at = `/logs/sources/${index}`;
              const cfgErrors = index < 0 ? [] : errorsUnder(errors, `${at}/config`);
              const ownErrors = index < 0 ? [] : [...messagesAt(errors, at), ...messagesAt(errors, `${at}/config`), ...messagesAt(errors, `${at}/enabled`)];
              const hasConfig = d.config_schema !== undefined && Object.keys(d.config_schema).length > 0;
              return (
                <li key={d.id} className="logs-source" data-source-card={d.id} data-expanded={expanded ? "true" : undefined}>
                  <div className="logs-source-head">
                    <button type="button" className="logs-linkbtn" aria-expanded={expanded} aria-label={t.settings.sources.expand(d.title)} onClick={() => setOpen((cur) => { const n = new Set(cur); if (n.has(d.id)) n.delete(d.id); else n.add(d.id); return n; })}>
                      {expanded ? "▾" : "▸"}
                    </button>
                    <strong className="ac-ellipsis" title={d.title}>{d.title}</strong>
                    <code className="logs-mono app-muted">{d.id}</code>
                    <span className="logs-spacer" />
                    {d.reads_paths === true ? <span className="logs-chip" title={t.settings.sources.readOnlyTip}>🔒 {t.settings.sources.readOnlyChip}</span> : null}
                    {setting?.enabled === undefined ? (
                      <span className="logs-chip" title={autoOn ? t.settings.sources.autoOnTip : undefined}>{autoOn ? t.settings.sources.autoOn : (d.default_enabled ?? false) ? t.settings.sources.defaultOn : t.settings.sources.defaultOff}</span>
                    ) : (
                      <>
                        <span className="logs-chip">{t.settings.sources.specified}</span>
                        <Button size="sm" variant="ghost" aria-label={`${d.title} ${t.settings.sources.resetDefault}`} disabled={disabled} onClick={() => reset(info)}>↺</Button>
                      </>
                    )}
                    <label className="app-check logs-switch">
                      <input
                        ref={(el) => { if (el) switchRefs.current.set(d.id, el); else switchRefs.current.delete(d.id); }}
                        type="checkbox"
                        checked={enabled}
                        disabled={disabled}
                        aria-label={t.settings.sources.enable(d.title)}
                        onChange={(e) => toggle(info, e.target.checked)}
                      />
                      {t.settings.sources.switchLabel}
                    </label>
                  </div>
                  {d.description ? <p className={`app-muted app-wrap ${expanded ? "" : "logs-clamp-2"}`}><InlineMarkdown text={d.description} /></p> : null}
                  <div className="logs-source-status" data-kind={view.kind}>
                    <span className="app-muted">{view.kind === "off" ? null : "상태"}</span>
                    {view.chip ? <StatusChip status={view.kind === "error" ? "failed" : view.kind === "ok" ? "succeeded" : "pending"} label={view.chip} /> : null}
                    {view.code ? <code className="logs-mono">{view.code}</code> : null}
                    {view.errorText ? <span className="app-wrap">{view.errorText}</span> : null}
                    {view.parts.map((p, i) => <span key={i} className={view.kind === "unsaved" ? "logs-warn" : "app-muted"}>{p}</span>)}
                    {view.pending ? <span title={t.sourceStatus.pendingTip}>ⓘ {view.pending}</span> : null}
                    {view.kind === "error" ? <span className="app-muted">{t.sourceStatus.errorNote}</span> : null}
                    <span className="logs-spacer" />
                    {enabled ? (
                      <Button size="sm" loading={scanningId === d.id} disabled={dirty || disabled} title={dirty ? t.settings.sources.scanDirtyTip : undefined} onClick={() => void runScan(info)}>{t.settings.sources.scan}</Button>
                    ) : null}
                  </div>
                  {ownErrors.map((msg, i) => <p key={i} className="app-field-error" role="alert">{msg}</p>)}
                  {expanded ? (
                    <div className="logs-source-body">
                      {d.setup_help ? (
                        <>
                          <div className="logs-setup-help app-wrap" role="note"><InlineMarkdown text={d.setup_help} /></div>
                          <p className="app-muted logs-note">{t.settings.sources.setupHelpNote}</p>
                        </>
                      ) : null}
                      {isHttpUrl(d.docs_url) ? <a href={d.docs_url} target="_blank" rel="noopener noreferrer">{t.settings.sources.docs}</a> : d.docs_url ? <span className="app-muted app-wrap">{d.docs_url}</span> : null}
                      {hasConfig ? (
                        <Disclosure summary={t.settings.sources.configTitle} {...(cfgErrors.length > 0 ? { open: true } : { defaultOpen: true })}>
                          <SchemaForm
                            schema={d.config_schema as Record<string, unknown>}
                            value={setting?.config ?? {}}
                            idPrefix={`logs-src-${d.id}`}
                            advancedStorageKey={`logs-source:${d.id}`}
                            rawJsonToggle={false}
                            customWidgets={CUSTOM_WIDGETS}
                            {...(uiFor(info) === undefined ? {} : { uiSchema: uiFor(info) as UiSchema })}
                            errors={cfgErrors}
                            {...(disabled === undefined ? {} : { disabled })}
                            onChange={(v) => update(d.id, (c) => ({ ...c, config: v as Record<string, unknown> }))}
                          />
                        </Disclosure>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {unknown.length > 0 ? (
        <section aria-label={t.settings.sources.groupUnknown}>
          <h4 className="app-block-subtitle">{t.settings.sources.groupUnknown}</h4>
          <ul className="logs-source-list">
            {unknown.map((s) => (
              <li key={s.id} className="logs-source">
                <code className="logs-mono">{s.id}</code> <span className="logs-chip">{t.settings.sources.unknownChip}</span>{" "}
                <Button size="sm" disabled={disabled} onClick={() => setSources(settings.filter((x) => x.id !== s.id))}>{t.settings.sources.unknownRemove}</Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {observeHref !== undefined ? (
        <p className="app-muted logs-note">ⓘ {t.settings.sources.observeNote} <a href={observeHref}>{t.settings.sources.observeAction}</a></p>
      ) : null}
      <ConfirmDialog
        open={confirm !== null}
        title={t.settings.sources.confirmTitle(confirm?.descriptor.title ?? "")}
        confirmLabel={t.settings.sources.confirmOk}
        cancelLabel={t.settings.sources.confirmCancel}
        onConfirm={() => {
          if (confirm !== null) {
            setEnabled(confirm, true);
            const id = confirm.descriptor.id;
            requestAnimationFrame(() => switchRefs.current.get(id)?.focus());
          }
          setConfirm(null);
        }}
        onCancel={() => setConfirm(null)}
      >
        <p>{t.settings.sources.confirmBody}</p>
        {confirm !== null && roots(confirm).length > 0 ? (
          <p>
            {t.settings.sources.confirmRoots}: {roots(confirm).map((r) => <code key={r} className="logs-mono app-wrap">{r}</code>)}
          </p>
        ) : null}
        {value.secrets?.redact_suspected_in_logs === false ? <p className="logs-warn">{t.settings.sources.redactOff}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
