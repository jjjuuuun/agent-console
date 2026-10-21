import { useMemo } from "react";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { Banner } from "@agent-console/ui";
import { resolveFieldSchema } from "./widgetRegistry";
import type { SchemaNode } from "../../lib/schemaTools";
import { resolveRef } from "../../lib/schemaTools";
import { ConditionList, type ConditionError } from "./ConditionList";
import { useConfigIssuesUnder } from "./ConfigIssuesContext";
import type { ConditionSpec } from "./conditions";
import { delegationMessages } from "./messages";
import { useConditionOperators } from "./useConditionOperators";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** 조건 항목 `path` 필드 스키마의 `examples`(제안 경로)를 필드 스키마에서 찾는다. 항목 모양은 계약 `ConditionItem`이 정한다. */
export function pathExamples(fieldSchema: SchemaNode, root: SchemaNode): string[] {
  const seen = new Set<unknown>();
  const found: string[] = [];
  const walk = (node: unknown, depth: number) => {
    if (!isObj(node) || depth > 8 || seen.has(node)) return;
    seen.add(node);
    const resolved = resolveRef(node, root);
    const props = resolved["properties"];
    if (isObj(props) && isObj(props["path"])) {
      const examples = (resolveRef(props["path"] as SchemaNode, root))["examples"];
      if (Array.isArray(examples)) for (const e of examples) if (typeof e === "string" && !found.includes(e)) found.push(e);
    }
    for (const key of ["items", "anyOf", "oneOf", "allOf"]) {
      const child = resolved[key];
      if (Array.isArray(child)) child.forEach((c) => walk(c, depth + 1));
      else walk(child, depth + 1);
    }
    if (isObj(props)) for (const v of Object.values(props)) walk(v, depth + 1);
  };
  walk(fieldSchema, 0);
  return found;
}

/** `ui:options.path_titles`(경로 → 제목) 표. 문자열 값만 받는다. */
export function pathTitlesOf(options: Obj): Record<string, string> {
  const raw = options["path_titles"];
  if (!isObj(raw)) return {};
  return Object.fromEntries(Object.entries(raw).filter((e): e is [string, string] => typeof e[1] === "string"));
}

/**
 * 스키마 폼의 `ui:field`로 꽂는 조건 목록 필드(위젯 레지스트리 `condition-list`). 연산자 목록은 훅이 읽고,
 * 서버 이슈는 설정 이슈 문맥에서 자기 위치(`ui:options.$pointer`) 아래 것을 받는다.
 */
export function ConditionListField({ id, value, onChange, label, disabled, readonly, schema, options }: SchemaFormFieldProps) {
  const ops = useConditionOperators();
  const root = (isObj(options["$rootSchema"]) ? options["$rootSchema"] : schema) as SchemaNode;
  const pointer = typeof options["$pointer"] === "string" ? options["$pointer"] : undefined;
  const issues = useConfigIssuesUnder(pointer);
  const titles = useMemo(() => pathTitlesOf(options), [options]);
  const suggestions = useMemo(
    () => pathExamples(resolveFieldSchema(schema as SchemaNode, root), root).map((v) => ({ value: v, ...(titles[v] !== undefined ? { title: titles[v] } : {}) })),
    [schema, root, titles],
  );
  const errors = useMemo<ConditionError[]>(() => issues.map((i) => ({ path: i.path, message: i.message })), [issues]);
  const spec = isObj(value) ? (value as ConditionSpec) : undefined;
  return (
    <ConditionList
      value={spec}
      onChange={(next) => onChange(next)}
      operators={ops.operators}
      operatorsState={ops.state}
      onRetryOperators={ops.retry}
      pathSuggestions={suggestions}
      errors={errors}
      disabled={disabled || readonly}
      label={label}
      idPrefix={id}
    />
  );
}

/** 이름을 모르는 위젯이 지정된 객체 필드: 안내와 원본 JSON(읽기 전용)을 보인다. 값은 그대로 보존한다. */
export function UnknownWidgetField({ id, value, label }: SchemaFormFieldProps) {
  return (
    <div id={id} role="group" aria-label={label}>
      <Banner tone="info">{delegationMessages.condition.unknownWidget}</Banner>
      <pre className="ac-pre app-json">{JSON.stringify(value ?? null, null, 2)}</pre>
    </div>
  );
}
