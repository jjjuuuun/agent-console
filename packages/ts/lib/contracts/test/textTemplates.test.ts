import { expect, expectTypeOf, test } from "vitest";

import type { TextTemplate } from "@agent-console/contracts/common";
import type { I18nInfo } from "@agent-console/contracts/i18n";
import type { BackendLoginSession, BackendLogoutResult, BackendProbeResult, BackendReadiness } from "@agent-console/contracts/runs";
import { CONTRACT_VERSIONS, getContractSchema } from "@agent-console/contracts";

// 계약 0.16.1: 원문 틀 + 값(text_templates)과 서버 원문 언어(source_language)는 더하기만이다.
// 옛 서버 응답(두 필드 없음)도 같은 타입으로 읽히고, 읽는 쪽은 없으면 빈 표·null로 다룬다.
const templatesOf = (r: { text_templates?: Record<string, TextTemplate[]> }): Record<string, TextTemplate[]> => r.text_templates ?? {};

test("옛 응답(text_templates 없음)을 읽는다", () => {
  const readiness: BackendReadiness = { backend_id: "zz", state: "x", tone: "ok", checked_at: 1 };
  const probe: BackendProbeResult = { backend_id: "zz", ok: true, finished_at: 1 };
  const login: BackendLoginSession = { session_id: "s", backend_id: "zz", method_id: "m", phase: "starting", started_at: 1, expires_at: 2 };
  const logout: BackendLogoutResult = { backend_id: "zz", ok: true, finished_at: 1 };
  for (const r of [readiness, probe, login, logout]) expect(templatesOf(r)).toEqual({});
  expectTypeOf<BackendReadiness["text_templates"]>().toEqualTypeOf<Record<string, TextTemplate[]> | undefined>();
});

test("TextTemplate는 스칼라·중첩 틀 값을 받는다", () => {
  const nested: TextTemplate = { template: "비밀 '{name}': {state}", params: { name: "k", state: { template: "있음" } } };
  const probe: BackendProbeResult = {
    backend_id: "zz",
    ok: false,
    message: "20초 안에 응답이 없었습니다.",
    finished_at: 1,
    text_templates: { "/message": [{ template: "{seconds}초 안에 응답이 없었습니다.", params: { seconds: 20 } }] },
  };
  expect(templatesOf(probe)["/message"]?.[0]?.params).toEqual({ seconds: 20 });
  expect(nested.params?.["state"]).toEqual({ template: "있음" });
  expectTypeOf<NonNullable<TextTemplate["params"]>[string]>().toEqualTypeOf<string | number | boolean | TextTemplate | null>();
});

test("옛 I18nInfo(source_language 없음)를 읽는다", () => {
  const old: I18nInfo = { languages: [], default_language: "ko", fallback_language: "en" };
  expect(old.source_language ?? null).toBeNull();
  expectTypeOf<I18nInfo["source_language"]>().toEqualTypeOf<string | null | undefined>();
  expect(CONTRACT_VERSIONS.i18n).toBe("1.1.0");
  expect(CONTRACT_VERSIONS.logs).toBe("2.1.0");
});

test("스키마에서 새 필드는 선택이다", () => {
  const cases = [
    ["BackendReadiness", "text_templates"],
    ["BackendProbeResult", "text_templates"],
    ["BackendLoginSession", "text_templates"],
    ["BackendLogoutResult", "text_templates"],
    ["I18nInfo", "source_language"],
    ["LogEvent", "text_templates"],
  ] as const;
  for (const [name, field] of cases) {
    const schema = getContractSchema(name) as { properties?: Record<string, unknown>; required?: string[] };
    expect(schema.properties).toHaveProperty(field);
    expect(schema.required ?? []).not.toContain(field);
  }
  const t = getContractSchema("TextTemplate") as { required?: string[] };
  expect(t.required).toEqual(["template"]);
});
