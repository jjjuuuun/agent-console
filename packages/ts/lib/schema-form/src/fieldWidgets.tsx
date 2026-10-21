import { getDefaultRegistry } from "@rjsf/core";
import type { WidgetProps } from "@rjsf/utils";
import { useContext, type ComponentType } from "react";
import { FieldHelpTip, hasFieldHelp } from "./FieldHelp";
import { XUiContext } from "./XUiParts";
import { readXUi } from "./xui";

/**
 * 불리언 위젯: "체크박스 + 라벨" 한 줄. 설명은 필드 행 템플릿이 아래에 한 번만 그린다(폼 엔진 기본 위젯은 설명을 위에 한 번 더 그린다).
 * `x-ui` 도움말이 있으면 라벨에 점선 밑줄과 호버·포커스 말풍선이 붙는다. 정렬은 `.ac-choice`와 같은 격자.
 */
export function CheckboxFieldWidget(p: WidgetProps) {
  const ctx = useContext(XUiContext);
  const schema = p.schema as Record<string, unknown>;
  const help = ctx !== null && hasFieldHelp(schema, !!p.readonly);
  const trueRequired = Array.isArray(schema["enum"]) && schema["enum"].length === 1 && schema["enum"][0] === true && p.required;
  return (
    <div className={`checkbox ac-sf-check${p.disabled || p.readonly ? " disabled" : ""}${help ? " ac-sf-help-host" : ""}`} data-help={help || undefined}>
      <label className="ac-choice ac-sf-choice">
        <input
          type="checkbox"
          id={p.id}
          name={p.htmlName ?? p.id}
          checked={p.value === undefined ? false : !!p.value}
          required={!!trueRequired}
          disabled={!!p.disabled || !!p.readonly}
          autoFocus={!!p.autofocus}
          onChange={(e) => p.onChange(e.target.checked)}
          onBlur={(e) => p.onBlur(p.id, e.target.checked)}
          onFocus={(e) => p.onFocus(p.id, e.target.checked)}
        />
        {p.hideLabel ? null : <span className="ac-sf-choice-text ac-sf-help-target">{p.label}{trueRequired ? <span className="required">*</span> : null}</span>}
      </label>
      {help && ctx ? <FieldHelpTip schema={schema} readonly={!!p.readonly} messages={ctx.messages} /> : null}
    </div>
  );
}

/** enum 값을 `x-ui.enum_labels`의 라벨로 바꿔 기본 위젯에 넘긴다(`oneOf`의 `title`은 폼 엔진이 이미 라벨로 쓴다). */
function withEnumLabels(name: "SelectWidget" | "RadioWidget") {
  return function LabeledEnumWidget(p: WidgetProps) {
    const Base = getDefaultRegistry().widgets[name] as ComponentType<WidgetProps>;
    const labels = readXUi(p.schema).enumLabels;
    const opts = p.options.enumOptions;
    if (labels === undefined || opts === undefined) return <Base {...p} />;
    const mapped = opts.map((o) => ({ ...o, label: labels[String(o.value)] ?? o.label }));
    return <Base {...p} options={{ ...p.options, enumOptions: mapped }} />;
  };
}
export const LabeledSelectWidget = withEnumLabels("SelectWidget");
export const LabeledRadioWidget = withEnumLabels("RadioWidget");
