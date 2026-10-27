import { getDefaultRegistry } from "@rjsf/core";
import type { FieldTemplateProps } from "@rjsf/utils";
import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { disabledMatch, fieldProvenance, getIn, previewValue, toPointer } from "./provenance";
import { parsePointer } from "./errors";
import { FieldHelpButton, FieldHelpPopover, FieldHelpTip, hasFieldHelp, isHelpKey, needsOwnLabel } from "./FieldHelp";
import { FieldDescription, ReadOnlyValue, RequiredChip, UnitWrap, XUiContext } from "./XUiParts";
import { humanizeEnumText, readXUi } from "./xui";
import type { ProvenanceBadgeInfo, ProvenanceLayer, SchemaFormMessages, SchemaFormProps } from "./types";

/** 출처 표시 모드에서 필드 템플릿이 읽는 값. SchemaForm이 Provider로 내려 준다(템플릿 컴포넌트 정체성을 안정시키려고 context 사용). */
export interface ProvenanceContextValue {
  messages: SchemaFormMessages;
  layers: readonly ProvenanceLayer[];
  provenance: Record<string, string>;
  layerValue: unknown;
  /** 지정된 필드만 배지·되돌리기 아이콘을 보이고, 나머지는 바로 편집(건드리면 이 층에서 지정) */
  compact?: boolean;
  props: Pick<
    SchemaFormProps,
    | "editLayerId"
    | "layerValues"
    | "onOverride"
    | "onInherit"
    | "disabledPaths"
    | "fieldWarnings"
    | "mergeNotes"
    | "onOpenLayer"
    | "renderProvenanceBadge"
  >;
}

export const ProvenanceContext = createContext<ProvenanceContextValue | null>(null);

const fill = (t: string, vars: Record<string, string | number>) =>
  t.replace(/\{(\w+)\}/g, (_, k: string) => (k in vars ? String(vars[k]) : `{${k}}`));

/** 내장 배지. 텍스트 라벨 필수, 색은 `--ac-layer-N` 토큰(층 인덱스 mod 6). 앱이 `renderProvenanceBadge`로 바꿀 수 있다. */
function DefaultBadge({ info }: { info: ProvenanceBadgeInfo }) {
  const slot = info.layer ? (info.layer.index % 6) + 1 : 1;
  return (
    <button
      type="button"
      className="ac-sf-badge"
      data-variant={info.variant}
      style={{ ["--ac-sf-layer" as string]: `var(--ac-layer-${slot}, #667085)` }}
      aria-expanded={info.expanded}
      aria-controls={info.popoverId}
      aria-label={`${info.text}: ${info.description}`}
      title={info.description}
      onClick={info.onClick}
    >
      <span className="ac-sf-badge-dot" aria-hidden="true" />
      {info.variant === "inherited" ? <span aria-hidden="true">↳ </span> : null}
      {info.text}
    </button>
  );
}

/**
 * 출처 표시 모드의 필드 행. 라벨 + 배지 + 위젯 + 동작 버튼.
 * 루트·배열 원소는 기본 템플릿 그대로 그린다(목록은 통째로 하나의 값이라 배지 하나).
 */
export function ProvenanceFieldTemplate(p: FieldTemplateProps) {
  const ctx = useContext(ProvenanceContext);
  const Default = getDefaultRegistry().templates.FieldTemplate;
  const path = p.fieldPathId.path as (string | number)[];
  if (!ctx || path.length === 0 || path.some((s) => typeof s === "number")) return <Default {...p} />;
  return <Row {...p} ctx={ctx} path={path} />;
}

function Row(p: FieldTemplateProps & { ctx: ProvenanceContextValue; path: (string | number)[] }) {
  const { ctx, path } = p;
  const { messages: m, layers, provenance, layerValue } = ctx;
  const { editLayerId, layerValues, onOverride, onInherit, disabledPaths, fieldWarnings, mergeNotes, onOpenLayer, renderProvenanceBadge } = ctx.props;
  const pointer = toPointer(path);
  const schema = p.schema as { type?: unknown; properties?: unknown };
  // `ui:field`로 통째 그리는 값(키-값 맵 등)은 폼 엔진이 값의 키를 `properties`로 펼쳐 줘도 하나의 값(잎)으로 본다.
  const customField = typeof (p.uiSchema as Record<string, unknown> | undefined)?.["ui:field"] === "string";
  const container = !customField && schema.type === "object" && typeof schema.properties === "object" && schema.properties !== null;
  const info = fieldProvenance({ pointer, container, provenance, layers, editLayerId, layerValue });
  const match = disabledMatch(disabledPaths, pointer);
  const disabledReason = match !== undefined ? disabledPaths?.[match] : undefined;
  const locked = disabledReason !== undefined;
  const showReason = locked && match === pointer;
  const compact = ctx.compact === true;
  const xctx = useContext(XUiContext);
  // 접을 수 있는 객체(`type: ["object","null"]`)는 행으로는 잎이지만 안쪽 객체 템플릿이 제목·설명을 그리므로 설명을 한 번 더 그리지 않는다.
  const schemaTypes = Array.isArray((schema as { type?: unknown }).type) ? ((schema as { type: unknown[] }).type) : [(schema as { type?: unknown }).type];
  const objectValued = !customField && !container && schemaTypes.includes("object") && typeof schema.properties === "object" && schema.properties !== null;
  const readOnlyLeaf = !container && (compact ? locked : info.state !== "set" || locked);

  const popId = useId();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const rowRef = useRef<HTMLDivElement>(null);
  const wantFocus = useRef(false);
  const prevState = useRef(info.state);
  useEffect(() => {
    if (wantFocus.current && prevState.current !== "set" && info.state === "set") {
      wantFocus.current = false;
      rowRef.current?.querySelector<HTMLElement>(".ac-sf-prov-body input, .ac-sf-prov-body select, .ac-sf-prov-body textarea")?.focus();
    }
    prevState.current = info.state;
  }, [info.state]);

  const layerOf = (id: string) => {
    const index = layers.findIndex((l) => l.id === id);
    return { id, label: layers[index]?.label ?? id, index: index === -1 ? layers.length : index };
  };
  const layer = info.layerId !== undefined ? layerOf(info.layerId) : undefined;

  const override = () => {
    if (locked || !onOverride) return;
    wantFocus.current = true;
    onOverride(pointer);
  };
  const inherit = () => {
    if (locked || !onInherit) return;
    onInherit(pointer);
  };

  const badgeInfo: ProvenanceBadgeInfo = {
    variant: info.state,
    layer,
    count: info.state === "mixed" ? info.layerIds.length : undefined,
    text: info.state === "mixed" ? fill(m.badgeMixed, { count: info.layerIds.length }) : info.state === "default" || !layer ? m.badgeDefault : layer.label,
    description:
      info.state === "mixed"
        ? info.layerIds.map((id) => layerOf(id).label).join(", ")
        : info.state === "default" || !layer
          ? m.badgeDefault
          : fill(info.state === "set" ? m.badgeSetHint : m.badgeInheritedHint, { layer: layer.label }),
    onClick: () => setOpen((o) => !o),
    expanded: open,
    popoverId: popId,
  };
  const badge = renderProvenanceBadge ? renderProvenanceBadge(badgeInfo) : <DefaultBadge info={badgeInfo} />;

  const provenanceList = (
    <>
      <p className="ac-sf-popover-title">{m.popoverTitle}</p>
      <ul>
        {layers.map((l) => {
          const raw = layerValues ? getIn(layerValues[l.id], parsePointer(pointer)) : undefined;
          const applied = !container && info.layerId === l.id;
          const text = `${l.label}: ${raw === undefined ? m.layerEmpty : previewValue(raw)}${applied ? ` ← ${m.layerApplied}` : ""}`;
          return (
            <li key={l.id} data-applied={applied || undefined}>
              {onOpenLayer ? (
                <button type="button" className="ac-sf-popover-row" aria-label={`${text}. ${fill(m.openLayer, { layer: l.label })}`} onClick={() => onOpenLayer(l.id)}>
                  {text}
                </button>
              ) : (
                <span>{text}</span>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
  const popover = open ? (
    xctx && !container ? (
      <FieldHelpPopover id={popId} schema={p.schema as Record<string, unknown>} formData={p.formData} readonly={p.readonly || readOnlyLeaf} disabled={p.disabled} messages={m} onFill={(v) => p.onChange(v as never, p.fieldPathId.path)}>
        {provenanceList}
      </FieldHelpPopover>
    ) : (
      <div id={popId} className="ac-sf-popover" role="group" aria-label={m.popoverTitle}>
        {provenanceList}
      </div>
    )
  ) : null;

  let action: ReactNode = null;
  if (compact) {
    if (!container && info.state === "set" && onInherit) {
      action = (
        <button type="button" data-ac-sf-action className="ac-sf-action ac-sf-action-icon" disabled={locked} aria-disabled={locked} aria-label={m.inheritBack} title={m.inheritBack} onClick={inherit}>
          <span aria-hidden="true">↺</span>
        </button>
      );
    }
  } else if (!container) {
    if (info.state === "set") {
      action = onInherit ? (
        <button type="button" data-ac-sf-action className="ac-sf-action" disabled={locked} aria-disabled={locked} onClick={inherit}>
          <span aria-hidden="true">↺ </span>
          {m.inheritBack}
        </button>
      ) : null;
    } else if (onOverride) {
      action = (
        <button type="button" data-ac-sf-action className="ac-sf-action" disabled={locked} aria-disabled={locked} title={locked ? disabledReason : undefined} onClick={override}>
          {info.state === "default" ? m.setHere : m.overrideHere}
        </button>
      );
    }
  }

  // Alt+I: 도움말(ⓘ) 팝오버 토글. Alt+Enter: 포커스된 필드의 덮어쓰기/되돌리기 토글(가장 안쪽 행만 처리)
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!container && isHelpKey(e)) {
      e.preventDefault();
      e.stopPropagation();
      setOpen((o) => !o);
      return;
    }
    if (container || !e.altKey || e.key !== "Enter") return;
    e.preventDefault();
    e.stopPropagation();
    if (info.state === "set") inherit();
    else override();
  };

  // 라벨 줄은 항상 둔다. 폼 엔진이 라벨을 안 그리는 필드(배열·`ui:field`)는 여기서 텍스트 라벨을 그리고 안쪽 제목은 CSS로 숨긴다.
  const ownLabel = !(p.displayLabel && p.label) && !!p.label && needsOwnLabel(p);
  const labelNode = p.label ? (
    <>
      {p.displayLabel ? (
        <label className="control-label ac-sf-help-target" htmlFor={p.id}>
          {p.label}
          {xctx ? null : p.required ? <span className="required">*</span> : null}
        </label>
      ) : ownLabel ? (
        <span className="control-label ac-sf-label-text ac-sf-help-target">{p.label}</span>
      ) : null}
      {xctx && p.required ? <RequiredChip messages={m} /> : null}
    </>
  ) : null;
  const chip = mergeNotes?.[pointer];
  const warning = fieldWarnings?.[pointer];
  const lock = locked ? (
    <span className="ac-sf-lock" title={disabledReason}>
      <span aria-hidden="true">🔒</span>
      <span className="ac-sf-sr-only">{m.disabledLock}</span>
    </span>
  ) : null;

  const showBadge = !compact || info.state === "set" || (container && info.state !== "default" && info.state !== "inherited");
  // ⓘ는 필드마다 하나. 값 출처(배지)·예시·기본값·바꾸는 때를 한 팝오버에 모은다.
  const helpButton = (
    <FieldHelpButton open={open} popoverId={popId} label={xctx ? m.helpToggle : m.popoverTitle} onToggle={() => setOpen((o) => !o)} />
  );
  // x-ui 폼은 라벨 말풍선(+Alt+I, 값 출처 배지 클릭)으로 알리고 버튼을 따로 두지 않는다. 그 밖의 간소 표시만 ⓘ가 열쇠다.
  const showHelp = !container && !xctx && compact && !showBadge;
  const tipped = !container && !!xctx && !!p.label && (p.displayLabel || ownLabel) && hasFieldHelp(p.schema as Record<string, unknown>, p.readonly || readOnlyLeaf);
  const stateNodes =
    lock || showBadge || (compact && info.state === "inherited" && layer) || chip || action ? (
      <span className="ac-sf-prov-state">
        {showBadge ? badge : null}
        {compact && info.state === "inherited" && layer ? <span className="ac-sf-inherited">{fill(m.inheritedFrom, { layer: layer.label })}</span> : null}
        {chip ? <span className="ac-sf-chip">{chip}</span> : null}
        {action ? <span className="ac-sf-prov-actions">{action}</span> : null}
      </span>
    ) : null;
  const header = (
    <div className="ac-sf-prov-head ac-sf-help-host" data-help={tipped || undefined}>
      {container ? null : labelNode}
      {lock}
      {showHelp ? helpButton : null}
      {tipped ? <FieldHelpTip schema={p.schema as Record<string, unknown>} readonly={p.readonly || readOnlyLeaf} messages={m} /> : null}
      {stateNodes}
    </div>
  );
  const status = (
    <>
      {popover}
      {warning ? (
        <p className="ac-sf-warning" role="status">
          <span aria-hidden="true">▲ </span>
          {warning}
        </p>
      ) : null}
      {showReason ? <p className="ac-sf-hint ac-sf-reason">{disabledReason}</p> : null}
    </>
  );

  const common = {
    ref: rowRef,
    className: "ac-sf-prov-row",
    "data-state": info.state,
    "data-disabled": showReason || undefined,
    "aria-disabled": locked || undefined,
    onKeyDown,
  } as const;

  if (container) {
    const bodyId = `${popId}-body`;
    return (
      <div {...common}>
        <div className="ac-sf-prov-head ac-sf-prov-summary">
          <button type="button" className="ac-sf-fold" aria-expanded={!collapsed} aria-controls={bodyId} onClick={() => setCollapsed((c) => !c)}>
            <span aria-hidden="true">{collapsed ? "▸" : "▾"} </span>
            {p.label}
          </button>
          {lock}
          {showBadge ? badge : null}
          {chip ? <span className="ac-sf-chip">{chip}</span> : null}
        </div>
        {status}
        <fieldset id={bodyId} className="ac-sf-prov-body ac-sf-prov-group" hidden={collapsed} disabled={locked || undefined}>
          {p.children}
        </fieldset>
      </div>
    );
  }
  const rawDesc = p.rawDescription ?? (typeof (p.schema as Record<string, unknown>)["description"] === "string" ? ((p.schema as Record<string, unknown>)["description"] as string) : undefined);
  const descNode = xctx && objectValued ? null : xctx ? <FieldDescription text={rawDesc === undefined ? undefined : humanizeEnumText(rawDesc, readXUi(p.schema).enumLabels)} /> : null;
  return (
    <div {...common} data-readonly={readOnlyLeaf || undefined} data-own-label={ownLabel || undefined}>
      {header}
      {xctx ? null : p.description}
      <fieldset className="ac-sf-prov-body" disabled={readOnlyLeaf || undefined}>
        {xctx && (p.schema as Record<string, unknown>)["readOnly"] === true ? (
          <ReadOnlyValue value={p.formData} messages={m} />
        ) : xctx ? (
          <UnitWrap unit={readXUi(p.schema).unit}>{p.children}</UnitWrap>
        ) : (
          p.children
        )}
      </fieldset>
      {descNode}
      {p.errors}
      {p.help}
      {status}
    </div>
  );
}
