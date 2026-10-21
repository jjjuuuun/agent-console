import { ConditionListField, UnknownWidgetField, pathTitlesOf } from "./ConditionListField";
import { summarizeConditions, type ConditionSpec } from "./conditions";
import { delegationMessages } from "./messages";
import { UNKNOWN_WIDGET_FIELD, type WidgetRegistry } from "./widgetRegistry";

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** 조건 목록 위젯의 `ui:widget` 이름(서버 `ui_schema`가 지정하는 데이터 이름). 레지스트리에 한 줄 등록한다. */
export const CONDITION_WIDGET_NAME = "condition-list";

/**
 * 앱이 아는 설정 위젯 레지스트리(screen-delegation.md 2.4.4). 이름은 서버 `ui_schema`에서 오고,
 * 여기 없는 이름이 객체·배열 필드에 지정되면 JSON 폴백 + 안내로 그려진다. `summary`가 있는 위젯은 연결 칩을 만든다.
 */
export const CONFIG_WIDGETS: WidgetRegistry = {
  [CONDITION_WIDGET_NAME]: {
    Component: ConditionListField,
    summary: (value, ctx) => {
      const spec = isObj(value) ? (value as ConditionSpec) : undefined;
      const s = summarizeConditions(spec, ctx.operators, pathTitlesOf(ctx.options));
      if (s.empty) return { title: delegationMessages.edge.conditionEmpty, fullTitle: delegationMessages.condition.emptySummary, iconName: "filter", tone: "warning" };
      return { title: s.text, fullTitle: s.full, iconName: "filter", tone: "neutral" };
    },
  },
};

/** `SchemaForm`에 넘기는 `ui:field` 표(레지스트리 위젯 + 모르는 위젯 폴백). */
export const CONFIG_FIELDS = {
  ...Object.fromEntries(Object.entries(CONFIG_WIDGETS).map(([name, w]) => [name, w.Component])),
  [UNKNOWN_WIDGET_FIELD]: UnknownWidgetField,
};
