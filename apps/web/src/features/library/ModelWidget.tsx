import { useMemo, useState } from "react";
import type { ModelInfo } from "@agent-console/contracts";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";
import { useAppMessages } from "../../app/appMessages";
import { useBackendConnectMessages } from "../backendConnect";
import { modelSources, ModelCatalogStatus, useBackendModelCatalog } from "../modelCatalog";
import { useLibraryMessages } from "./messages";

/** `ui:widget` 이름. */
export const MODEL_WIDGET = "model-select";

export interface ModelOptions {
  /** 고른 백엔드가 알려 준 모델(없으면 직접 입력만) */
  models: readonly ModelInfo[];
  /** 목록을 불러오다 실패했다 */
  failed: boolean;
  emptyLabel: string;
  customLabel: string;
  failedNote: string;
  /** 모델 목록을 읽은 백엔드 id. 있으면 칸 아래에 조회 상태 줄을 그린다 */
  backendId?: string | null;
  /** 옵션 끝에 붙는 출처 표시(예: "설정"). 빈 문자열이면 붙이지 않는다 */
  sourceLabel?: (model: ModelInfo) => string;
  /** 출처 표시의 툴팁(`title`) */
  sourceTip?: (model: ModelInfo) => string;
}

/**
 * 모델 칸 위젯 옵션(`ui:options`): 고른 백엔드의 합친 모델 목록, 출처 표시, 직접 입력·실패 문구.
 * 에이전트 설정 폼과 공통 설정(에이전트 기본값) 폼이 같이 쓴다. 백엔드를 못 정했으면 목록이 비고 상태 줄도 없다.
 */
export function useModelFieldOptions(backendId: string | null): ModelOptions {
  const app = useAppMessages();
  const t = useLibraryMessages();
  const bc = useBackendConnectMessages();
  const catalog = useBackendModelCatalog(backendId);
  const { data, isError } = catalog;
  return useMemo(() => ({
    models: data?.models ?? [],
    failed: isError,
    backendId,
    sourceLabel: sourceText((k) => bc.source[k]),
    sourceTip: sourceText((k) => (k === "config" ? bc.source.configTip : bc.source.discoveredTip)),
    emptyLabel: app.settings.unset,
    customLabel: t.agentForm.customModel,
    failedNote: t.agentForm.modelsFailed,
  }), [data, isError, backendId, bc, app, t]);
}

const sourceText = (pick: (k: "config" | "discovered") => string) => (model: ModelInfo) => modelSources(model).map(pick).join(" / ");

const CUSTOM = "\u0000custom";

/** 옵션 글자: `이름 (id)` + 출처 표시. 기본 `<option>`은 글자만 담을 수 있어 칩 대신 글자 꼬리로 붙인다. */
function optionText(model: ModelInfo, source: string): string {
  const base = model.title ? `${model.title} (${model.id})` : model.id;
  return source === "" ? base : `${base} — ${source}`;
}

/** 모델: 백엔드가 준 목록에서 고르거나 "직접 입력". 목록에 없는 현재 값은 직접 입력으로 보인다. */
export function ModelWidget({ id, value, onChange, onBlur, label, disabled, readonly, options, errors }: SchemaFormWidgetProps) {
  const opts = options as unknown as ModelOptions;
  const current = typeof value === "string" ? value : "";
  const known = opts.models.some((m) => m.id === current);
  const [forceCustom, setForceCustom] = useState(false);
  const custom = forceCustom || (current !== "" && !known) || (opts.models.length === 0 && current !== "");
  const locked = disabled || readonly;
  return (
    <span className="lib-model">
      {opts.models.length > 0 || !custom ? (
        <select
          id={id}
          aria-label={label}
          value={custom ? CUSTOM : current}
          disabled={locked}
          aria-invalid={errors.length > 0 || undefined}
          onBlur={onBlur}
          onChange={(e) => {
            if (e.target.value === CUSTOM) {
              setForceCustom(true);
              return;
            }
            setForceCustom(false);
            onChange(e.target.value === "" ? null : e.target.value);
          }}
        >
          <option value="">{opts.emptyLabel}</option>
          {opts.models.map((m) => (
            <option key={m.id} value={m.id} title={opts.sourceTip?.(m) || undefined}>
              {optionText(m, opts.sourceLabel?.(m) ?? "")}
            </option>
          ))}
          <option value={CUSTOM}>{opts.customLabel}</option>
        </select>
      ) : null}
      {custom ? (
        <input
          className="ac-input"
          aria-label={opts.customLabel}
          value={current}
          disabled={locked}
          onBlur={onBlur}
          onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        />
      ) : null}
      {opts.failed ? <span className="app-muted lib-field-note">{opts.failedNote}</span> : null}
      {opts.backendId == null ? null : (
        <span className="lib-model-status">
          <ModelCatalogStatus backendId={opts.backendId} />
        </span>
      )}
    </span>
  );
}
