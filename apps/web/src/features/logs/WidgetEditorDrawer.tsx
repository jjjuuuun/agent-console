import { useEffect, useMemo, useState } from "react";
import { WidgetEditor, DashboardGrid, validateWidget, type WidgetRegistry, type WidgetResult } from "@agent-console/log-view";
import { SchemaForm } from "@agent-console/schema-form";
import type { LogDimensionInfo, LogMetricInfo, LogWidget } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { defaultLogViewMessages } from "@agent-console/log-view";
import { Drawer } from "./Drawer";
import { LogFilters, type FilterOptionsData } from "./LogFilters";
import { LOGS_LIMITS } from "./logsConfig";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";
import { ApiError } from "@agent-console/api-client";
import type { LogFilterValue } from "@agent-console/log-view";

export interface WidgetEditorDrawerProps {
  /** 편집 중인 위젯 사본(새 위젯이면 기본값으로 만든 것). 닫으면 undefined */
  initial: LogWidget;
  isNew: boolean;
  registry: WidgetRegistry;
  dimensions: readonly LogDimensionInfo[] | undefined;
  metrics: readonly LogMetricInfo[] | undefined;
  filterOptions: FilterOptionsData;
  tz: string;
  onApply(widget: LogWidget): void;
  onCancel(): void;
}

function toFilterValue(filter: Record<string, unknown> | undefined): LogFilterValue {
  const out: LogFilterValue = {};
  for (const [k, v] of Object.entries(filter ?? {})) {
    if (typeof v === "string") out[k] = v;
    else if (typeof v === "number") out[k] = String(v);
    else if (Array.isArray(v)) out[k] = v.map(String);
  }
  return out;
}

/**
 * 위젯 추가·편집 드로어(포커스 가둠·`Esc`로 닫기): `WidgetEditor`에 서버 차원·지표 목록(없으면 자유 입력), 필터 막대, 옵션 폼(SchemaForm),
 * 미리보기(400ms 디바운스 집계)를 주입한다. [위젯 적용]은 로컬 복사본에만 반영하고 서버 저장은 아니다.
 */
export function WidgetEditorDrawer(p: WidgetEditorDrawerProps) {
  const { rest } = useApi();
  const [draft, setDraft] = useState<LogWidget>(p.initial);
  // 미리보기 결과는 어떤 질의의 것인지 함께 둔다(질의가 바뀌면 이전 결과는 "불러오는 중"으로 본다)
  const [previewState, setPreviewState] = useState<{ key: string; result: WidgetResult } | null>(null);
  const descriptors = useMemo(() => [...p.registry.values()], [p.registry]);
  const problems = validateWidget(draft, p.registry.get(draft.kind), p.dimensions, defaultLogViewMessages);
  const ready = problems.length === 0;
  const queryKey = JSON.stringify([draft.query, p.tz]);
  const preview: WidgetResult = previewState?.key === queryKey ? previewState.result : { loading: true, ...(previewState?.result.rows ? { rows: previewState.result.rows } : {}) };

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const handle = setTimeout(() => {
      rest
        .aggregateLogs({ group_by: draft.query.group_by ?? [], metric: draft.query.metric, filter: draft.query.filter ?? {}, tz: p.tz })
        .then((rows) => !cancelled && setPreviewState({ key: queryKey, result: { rows, loading: false, updatedAt: Date.now() } }))
        .catch((e: unknown) => {
          if (cancelled) return;
          const err = e instanceof ApiError ? { message: e.message, code: e.code } : { message: e instanceof Error ? e.message : String(e) };
          setPreviewState({ key: queryKey, result: { loading: false, error: err } });
        });
    }, LOGS_LIMITS.previewDebounceMs);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // 질의가 바뀔 때만 다시 부른다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, ready, rest]);

  const descriptor = p.registry.get(draft.kind);
  const previewWidget: LogWidget = { ...draft, options: { ...(draft.options ?? {}), w: 12, h: 3 } };
  return (
    <Drawer open title={p.isNew ? t.dashboards.editorTitleNew : t.dashboards.editorTitleEdit} onClose={p.onCancel} width={440}>
      <WidgetEditor
        value={draft}
        onChange={setDraft}
        descriptors={descriptors}
        dimensions={p.dimensions}
        metrics={p.metrics}
        onApply={p.onApply}
        onCancel={p.onCancel}
        filterBar={
          <div
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.target instanceof HTMLInputElement) e.preventDefault();
            }}
          >
            <LogFilters
              value={toFilterValue(draft.query.filter)}
              onChange={(next) => setDraft({ ...draft, query: { ...draft.query, filter: next } })}
              options={p.filterOptions}
              compact
            />
            <p className="app-muted logs-note">{t.dashboards.filterRangeNote}</p>
          </div>
        }
        renderOptionsForm={(schema, value, onChange) => {
          const { w: _w, h: _h, ...rest2 } = value;
          void _w;
          void _h;
          return <SchemaForm schema={schema} value={rest2} idPrefix="logs-widget-opts" rawJsonToggle={false} onChange={(v) => onChange(v as Record<string, unknown>)} />;
        }}
        preview={
          ready && descriptor !== undefined ? (
            <div className="logs-preview">
              <DashboardGrid widgets={[previewWidget]} registry={p.registry} results={{ [draft.id]: preview }} columns={6} rowHeight={60} slotFor={slotFor} metrics={p.metrics ?? []} dimensions={p.dimensions ?? []} ariaLabel={t.dashboards.editorTitleEdit} />
            </div>
          ) : (
            <p className="app-muted">{t.dashboards.previewHint}</p>
          )
        }
      />
    </Drawer>
  );
}
