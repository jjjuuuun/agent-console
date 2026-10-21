import type { UiSchema } from "@agent-console/schema-form";
import { STRING_TAGS_FIELD } from "../settings";
import { resourceMessages as t } from "./messages";

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

function typeIs(schema: Obj, name: string): boolean {
  return schema["type"] === name || (Array.isArray(schema["type"]) && schema["type"].includes(name));
}

function strings(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

/**
 * 종류 `config_schema` 모양만 보고 만드는 입력 보강(필드 이름·종류 이름을 모른다). 서버가 준 `ui_schema`가 먼저다.
 * - 문자열 배열 -> 태그 입력(제안 = 항목 스키마 `examples`, placeholder = 첫 예시).
 * - `examples`가 있는 문자열 -> 입력 위 제안 목록(브라우저 datalist, 목록에 없는 값도 입력 가능)과 한 줄 안내.
 */
export function buildConfigUi(schema: Obj | undefined, serverUi: Obj | undefined): UiSchema {
  const out: Obj = { ...(serverUi ?? {}) };
  const props = schema?.["properties"];
  if (!isObj(props)) return out as UiSchema;
  for (const [key, raw] of Object.entries(props)) {
    if (!isObj(raw) || isObj(out[key]) && Object.keys(out[key] as Obj).length > 0) continue;
    if (typeIs(raw, "array") && isObj(raw["items"]) && typeIs(raw["items"], "string")) {
      const examples = strings((raw["items"] as Obj)["examples"]);
      out[key] = {
        "ui:field": STRING_TAGS_FIELD,
        "ui:options": {
          suggestions: examples,
          addLabel: examples[0] === undefined ? t.config.tagAdd : t.config.tagAddExample(examples[0]),
          addButtonLabel: t.config.tagAddButton,
          removeLabel: t.config.tagRemove,
        },
      };
    } else if (typeIs(raw, "string") && strings(raw["examples"]).length > 0 && raw["enum"] === undefined) {
      out[key] = { "ui:help": t.config.freeInputNote };
    }
  }
  return out as UiSchema;
}
