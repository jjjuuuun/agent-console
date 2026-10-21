import { useMemo, useState } from "react";
import type { ExporterDescriptor, ExportSelection } from "@agent-console/contracts";
import { getDefaultValue, SchemaForm, type FormError, type JsonSchema } from "@agent-console/schema-form";
import { Button, Tag } from "@agent-console/ui";
import { useApiQuery } from "../../app/queries";
import { applyFormEdit } from "../../lib/formEdit";
import { exporterSupports } from "./exportLogic";
import { ITEM_SOURCES, kindLabel, sourceKind, type ItemSource } from "./exportSources";
import { exportMessages as t } from "./messages";

export interface ItemsStepProps {
  exporter: ExporterDescriptor;
  items: readonly ExportSelection[];
  /** 항목 id -> 표시 이름 조회(없으면 id) */
  nameOf: (item: ExportSelection) => string;
  itemErrors: ReadonlyMap<number, string>;
  onAdd: (item: ExportSelection) => void;
  onRemove: (index: number) => void;
  options: Record<string, unknown>;
  onOptionsChange: (next: Record<string, unknown>) => void;
  optionErrors: readonly FormError[];
}

function ItemPicker({ exporter, items, onAdd, onClose }: { exporter: ExporterDescriptor; items: readonly ExportSelection[]; onAdd: (item: ExportSelection) => void; onClose: () => void }) {
  const [source, setSource] = useState<ItemSource>(ITEM_SOURCES[0]!);
  const [query, setQuery] = useState("");
  const list = useApiQuery(["list", "export-pick", source.model], (rest) => source.load(rest), { retry: false });
  const kind = sourceKind(source) ?? "";
  const supported = exporterSupports(exporter, kind);
  const q = query.trim().toLowerCase();
  const rows = (list.data ?? []).filter((r) => q === "" || r.id.toLowerCase().includes(q) || r.name.toLowerCase().includes(q));
  return (
    <div className="exp-picker" role="group" aria-label={t.items.pickerTitle}>
      <div className="exp-picker-head">
        <select className="ac-input" aria-label={t.items.pickerKind} value={source.model} onChange={(e) => setSource(ITEM_SOURCES.find((s) => s.model === e.target.value) ?? source)}>
          {ITEM_SOURCES.map((s) => {
            const k = sourceKind(s);
            return (
              <option key={s.model} value={s.model}>
                {k === undefined ? s.model : kindLabel(k)}
              </option>
            );
          })}
        </select>
        <input type="search" className="ac-input" aria-label={t.items.pickerSearch} placeholder={t.items.pickerSearch} value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button size="sm" onClick={onClose}>
          {t.items.pickerClose}
        </Button>
      </div>
      {!supported ? <p className="app-muted exp-note">{t.items.unsupported}</p> : null}
      {list.isError ? <p role="alert">{t.items.pickerFailed}</p> : null}
      {list.isSuccess && rows.length === 0 ? <p className="app-muted">{t.items.pickerEmpty}</p> : null}
      <ul className="exp-picker-list">
        {rows.map((r) => {
          const added = items.some((i) => i.kind === kind && i.id === r.id);
          return (
            <li key={r.id}>
              <button type="button" className="exp-pick-row" disabled={!supported || added} aria-disabled={!supported || added} onClick={() => onAdd({ kind, id: r.id })}>
                <span className="ac-ellipsis">{r.name}</span> <span className="lib-mono app-muted">{r.id}</span>
                {added ? <Tag>{t.items.pickerAdded}</Tag> : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** ② 항목·옵션: 왼쪽 내보낼 정의 목록, 오른쪽 형식의 `config_schema` 폼(바꾼 값만 `options`에 담는다). */
export function ItemsStep({ exporter, items, nameOf, itemErrors, onAdd, onRemove, options, onOptionsChange, optionErrors }: ItemsStepProps) {
  const [picking, setPicking] = useState(false);
  const schema = exporter.config_schema as JsonSchema | undefined;
  const hasOptions = useMemo(() => {
    const props = (schema as { properties?: Record<string, unknown> } | undefined)?.properties;
    return props !== undefined && Object.keys(props).length > 0;
  }, [schema]);
  const shown = useMemo(() => (schema === undefined || !hasOptions ? {} : getDefaultValue(schema, options)), [schema, options, hasOptions]);
  return (
    <div className="exp-items-step">
      <section className="exp-items" aria-label={t.items.title}>
        <h3 className="app-block-title">{t.items.title}</h3>
        {items.length === 0 ? <p className="app-muted">{t.items.none}</p> : null}
        <ul className="exp-item-list">
          {items.map((item, i) => {
            const ok = exporterSupports(exporter, item.kind);
            const serverError = itemErrors.get(i);
            return (
              <li key={`${item.kind}:${item.id}`} className="exp-item" aria-disabled={!ok || undefined} data-problem={!ok || serverError !== undefined ? "true" : undefined}>
                <Tag>{kindLabel(item.kind)}</Tag>
                <span className="ac-ellipsis" title={item.id}>
                  {nameOf(item)}
                </span>
                {!ok ? (
                  <span className="exp-item-note">
                    <span aria-hidden="true">⚠</span> {t.items.unsupported}
                  </span>
                ) : null}
                {serverError !== undefined ? <span className="exp-item-note app-wrap">{serverError}</span> : null}
                <Button size="sm" onClick={() => onRemove(i)} aria-label={`${nameOf(item)} ${ok ? t.items.remove : t.items.exclude}`}>
                  {ok ? t.items.remove : t.items.exclude}
                </Button>
              </li>
            );
          })}
        </ul>
        <Button onClick={() => setPicking(!picking)} aria-expanded={picking}>
          {t.items.add}
        </Button>
        {picking ? <ItemPicker exporter={exporter} items={items} onAdd={onAdd} onClose={() => setPicking(false)} /> : null}
      </section>
      <section className="exp-options" aria-label={t.options.title}>
        <h3 className="app-block-title">{t.options.title}</h3>
        {!hasOptions || schema === undefined ? (
          <p className="app-muted">{t.options.none}</p>
        ) : (
          <>
            <p className="app-muted exp-note">{t.options.hint}</p>
            <SchemaForm
              schema={schema}
              value={shown}
              onChange={(next) => onOptionsChange(applyFormEdit(schema, options, next, { unsetOnDefault: true }))}
              errors={[...optionErrors]}
              rawJsonToggle={false}
              idPrefix="export-options"
            />
          </>
        )}
      </section>
    </div>
  );
}
