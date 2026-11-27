import { expect, expectTypeOf, test } from "vitest";

import type {
  BackendCapabilities,
  BackendModelCatalog,
  ModelDiscoveryInfo,
  ModelDiscoveryState,
  ModelInfo,
  ModelSource,
} from "@agent-console/contracts/runs";
import { getContractSchema, KNOWN_ISSUE_CODES } from "@agent-console/contracts";

// 계약 0.16.1: 모델 계정 조회는 더하기만이다. 옛 서버 응답(sources·model_discovery 없음)도 같은
// 타입으로 읽히고, 읽는 쪽은 없으면 빈 목록·false로 다룬다.
const sourcesOf = (model: ModelInfo): readonly ModelSource[] => model.sources ?? [];
const discovers = (caps: BackendCapabilities): boolean => caps.model_discovery ?? false;

test("옛 ModelInfo 응답(sources 없음)을 읽는다", () => {
  const old: ModelInfo = { id: "zz-model-1", title: "Zz" };
  expect(sourcesOf(old)).toEqual([]);
  expect(sourcesOf({ ...old, sources: ["config", "discovered"] })).toEqual(["config", "discovered"]);
  expectTypeOf<ModelInfo["sources"]>().toEqualTypeOf<ModelSource[] | undefined>();
  expectTypeOf<ModelSource>().toEqualTypeOf<"config" | "discovered">();
});

test("옛 BackendCapabilities 응답(model_discovery 없음)을 읽는다", () => {
  const old: BackendCapabilities = { streaming: true, status: true };
  expect(discovers(old)).toBe(false);
  expect(discovers({ ...old, model_discovery: true })).toBe(true);
  expectTypeOf<BackendCapabilities["model_discovery"]>().toEqualTypeOf<boolean | undefined>();
});

test("BackendModelCatalog 모양과 조회 상태 어휘", () => {
  const discovery: ModelDiscoveryInfo = { state: "failed" };
  const catalog: BackendModelCatalog = { backend_id: "zz-backend", discovery };
  expect(catalog.models ?? []).toEqual([]);
  expectTypeOf<ModelDiscoveryState>().toEqualTypeOf<"ok" | "stale" | "failed" | "disabled" | "unsupported">();
  const schema = getContractSchema("BackendModelCatalog") as { required?: string[] };
  expect(schema.required ?? []).toEqual(expect.arrayContaining(["backend_id", "discovery"]));
  expect(KNOWN_ISSUE_CODES.BACKEND_MODEL_DISCOVERY_FAILED).toBe("backend.model_discovery_failed");
});

test("스키마에서 새 필드는 선택이다", () => {
  for (const [name, field] of [["ModelInfo", "sources"], ["BackendCapabilities", "model_discovery"]] as const) {
    const schema = getContractSchema(name) as { properties?: Record<string, unknown>; required?: string[] };
    expect(schema.properties).toHaveProperty(field);
    expect(schema.required ?? []).not.toContain(field);
  }
});
